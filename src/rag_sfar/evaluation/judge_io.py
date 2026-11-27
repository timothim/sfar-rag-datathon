"""File-based bridge between eval reports and an external LLM judge (Claude Code subagents or any
batch process): blind export, replicated judge passes, strict merge, judge calibration.

Rubric v4 (eval_internal/judge/JUDGE_INSTRUCTIONS.md). Recommended workflow (blind, replicated):

    # 1. blind export: cases of several reports shuffled together under opaque ids, ~25 per batch;
    #    the opaque-id -> (report, config, question) key is written OUTSIDE the folder judges read
    python -m rag_sfar.evaluation.judge_io export-blind --run blind_X \\
        --reports reports/eval/b3/A.json reports/eval/b3/B.json ...
    # 2. two (or more) independent judge passes, one judge agent per batch and per pass, following
    #    eval_internal/judge/JUDGE_TASK.md: <RUN>/pass_<J>/judge_out_<P>.json
    # 3. merge: per-pass metrics, inter-judge agreement, pre-declared combination (headline: correct
    #    only if every pass says correct, serious error if any pass reports one), one merged copy
    #    of each report under reports/eval/judge_v4/<run>/ (the original reports are not modified)
    python -m rag_sfar.evaluation.judge_io merge-blind --run blind_X --passes a,b

A missing or invalid verdict makes the merge fail; with --allow-missing it counts as incorrect
(and behaviour not accepted), its serious-error status is undetermined, and it is listed.

Legacy single-report commands (`export`, `merge`, `calibrate`) are kept for older runs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import re
import subprocess
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

from rag_sfar.evaluation.datasets import load_suite
from rag_sfar.evaluation.harness import _aggregate, aggregate_binary, to_markdown
from rag_sfar.evaluation.judge import (RUBRIC_VERSION, SERIOUS_LABELS, cohen_kappa, missing_info_ids,
                                       normalize_verdict)

ROOT = Path(__file__).resolve().parents[3]
JUDGE_HOME = ROOT / "eval_internal" / "judge"
RUNS_DIR = JUDGE_HOME / "runs"
KEYS_DIR = JUDGE_HOME / "blind_keys"
FRONTIER_ROOT = ROOT / "eval_internal" / "work" / "replay" / "frontier"
MERGE_OUT = ROOT / "reports" / "eval" / "judge_v4"
INSTRUCTION_FILES = (JUDGE_HOME / "JUDGE_INSTRUCTIONS.md", JUDGE_HOME / "JUDGE_TASK.md")

# v1 had no "wrong_conduct" (v2) and did not count "other"; v4 counts every label except "none".
SERIOUS = SERIOUS_LABELS


# ---------------------------------------------------------------- behaviours


_BENCH_TO_LABEL = {"ask_clarification": "clarification", "conditional_answer": "conditional",
                   "answer_with_evidence": "answer", "abstain": "abstention"}


def acceptable_behaviors(item, lenient: bool = False) -> list[str]:
    """Behaviours the benchmark accepts for an item (judge labels).

    Strict (default, rubric v4): the expert benchmark's own list, `proposed.acceptable_behaviors`
    (read from `meta["acceptable_behaviors"]` when the dataset carries it). In
    benchmark_enrichi_phase1 its 11 clarification questions accept a request for the missing
    information or a conditional answer; the other 160 accept only an answer. Without the explicit
    list that rule is applied. `lenient=True` is the rubric-v3 reading (a case-by-case answer is
    also accepted on an "answer" question): a secondary metric, never the headline."""
    if not getattr(item, "expected_behavior", ""):
        return []
    explicit = (item.meta or {}).get("acceptable_behaviors")
    if explicit:
        out = [_BENCH_TO_LABEL.get(b, b) for b in explicit]
    elif item.expected_behavior == "clarification":
        out = ["clarification", "conditional"]
    else:
        out = [item.expected_behavior]
    if lenient and item.expected_behavior == "answer" and "conditional" not in out:
        out = [*out, "conditional"]
    return out


def _is_clarification_item(item) -> bool:
    return bool(item is not None and getattr(item, "expected_behavior", "") == "clarification")


# ---------------------------------------------------------------- cases


def _reference(item) -> str:
    if item.question_type == "mcq" and "mcq" in item.answer_key:
        letter = item.answer_key["mcq"]
        return f"{letter} ({item.choices.get(letter, '')})"
    if item.should_abstain:
        return "(La question n'est pas couverte par les recommandations SFAR : la bonne réponse est de s'abstenir.)"
    return item.reference_answer


def build_case(item, answer: str, case_id: str, cited_sources: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """One judge case. Carries nothing about the system, configuration, model, suite or split."""
    case: dict[str, Any] = {"case_id": case_id, "question": item.formatted_query(), "reference": _reference(item), "answer": answer}
    if item.mandatory_claims:
        case["mandatory_claims"] = [{"id": c["claim_id"], "text": c["text"]} for c in item.mandatory_claims]
    if item.forbidden_claims:
        case["forbidden_claims"] = [{"id": c["claim_id"], "text": c["text"]} for c in item.forbidden_claims]
    if item.expected_behavior:
        case["expected_behavior"] = item.expected_behavior
        case["acceptable_behaviors"] = acceptable_behaviors(item)
        # Detailed expert answer of a clarification question: what a conforming conditional
        # answer contains (the short reference only lists what to ask).
        if item.expected_behavior == "clarification" and (item.meta or {}).get("narrative"):
            case["reference_narrative"] = item.meta["narrative"]
    if item.required_missing_information:
        case["required_missing_information"] = missing_info_ids(item.required_missing_information)
    if cited_sources is not None:
        case["cited_sources"] = cited_sources
    return case


# ---------------------------------------------------------------- cited sources


_BLOCK_RE = re.compile(r"(?m)^\[S(\d+)\] ")
_BRACKET_RE = re.compile(r"\[[^\]\n]{0,200}\]")
_LABEL_RE = re.compile(r"S(\d+)")
MAX_SOURCE_CHARS = 4000
MAX_SOURCES_TOTAL = 9000
TRUNCATED = " [tronqué]"


def parse_prompt_sources(user_prompt: str) -> dict[int, str]:
    """Numbered excerpts [S1], [S2]... of a generation prompt (context before the question)."""
    end = user_prompt.find("\n---\nQUESTION")
    body = user_prompt[: end if end >= 0 else len(user_prompt)]
    ms = list(_BLOCK_RE.finditer(body))
    out = {}
    for i, m in enumerate(ms):
        stop = ms[i + 1].start() if i + 1 < len(ms) else len(body)
        out[int(m.group(1))] = body[m.start():stop].strip()
    return out


def cited_labels(answer: str) -> list[int]:
    """Source numbers cited in an answer: [S1], [S1, S3], [S2, 2016] (year ignored)..."""
    return sorted({int(x) for b in _BRACKET_RE.findall(answer or "") for x in _LABEL_RE.findall(b)})


LINE_CHARS = 1500  # file viewers of the judge agents cut lines at ~2000 characters


def _lines(text: str, width: int = LINE_CHARS) -> list[str]:
    out = []
    for ln in text.split("\n"):
        while len(ln) > width:
            cut = ln.rfind(" ", 0, width)
            cut = cut if cut > width // 2 else width
            out.append(ln[:cut])
            ln = ln[cut:].lstrip()
        out.append(ln)
    return out


def bound_sources(blocks: dict[int, str], labels: list[int], max_each: int = MAX_SOURCE_CHARS,
                  max_total: int = MAX_SOURCES_TOTAL) -> list[dict[str, Any]]:
    """Cited excerpts, each cut at `max_each` characters and all together at `max_total`, as a
    list of lines of at most LINE_CHARS characters (`lines`)."""
    out: list[dict[str, Any]] = []
    used = 0
    for n in labels:
        text = blocks[n]
        room = min(max_each, max_total - used)
        if room <= 200:
            out.append({"label": f"S{n}", "lines": ["[non transmis : limite de taille atteinte]"]})
            continue
        if len(text) > room:
            text = text[:room] + TRUNCATED
        used += len(text)
        out.append({"label": f"S{n}", "lines": _lines(text)})
    return out


class PromptIndex:
    """Generation prompts captured by eval_internal/gen_replay.py, i.e. the exact context the
    stand-in generator saw. Two layouts are read:

    - legacy export folders `<frontier_root>/<name>/` with `meta.json` (= `report["replay"]`)
      and `gen_input_*.json` ({case_id = question id, suite, system, user});
    - blind exports (since 2026-11-27): key files `<keys_root>/<name>.json` with `meta`
      (= `report["replay"]`) and `cases` ({id, suite, user, case_id = opaque id}).
    The prompt set is used only if exactly one folder or key file matches the report's meta."""

    def __init__(self, root: Path = FRONTIER_ROOT, keys_root: Path | None = None) -> None:
        self.root = root
        self.keys_root = keys_root if keys_root is not None else root.parent / "frontier_keys"
        self._cache: dict[str, dict[tuple[str, str], str] | None] = {}

    def _load(self, replay: dict[str, Any]) -> dict[tuple[str, str], str] | None:
        if not replay:
            return None
        found: list[dict[tuple[str, str], str]] = []
        if self.root.exists():
            for m in sorted(self.root.glob("*/meta.json")):
                try:
                    if json.loads(m.read_text(encoding="utf-8")) != replay:
                        continue
                except (OSError, json.JSONDecodeError):
                    continue
                out = {}
                for f in sorted(m.parent.glob("gen_input_*.json")):
                    for c in json.loads(f.read_text(encoding="utf-8")):
                        out[(c.get("suite", ""), c["case_id"])] = c["user"]
                found.append(out)
        if self.keys_root.exists():
            for k in sorted(self.keys_root.glob("*.json")):
                try:
                    data = json.loads(k.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(data, dict) or data.get("meta") != replay:
                    continue
                found.append({(c["suite"], c["id"]): c["user"] for c in data.get("cases", [])})
        return found[0] if len(found) == 1 else None

    def prompts(self, replay: dict[str, Any]) -> dict[tuple[str, str], str] | None:
        key = json.dumps(replay, sort_keys=True, ensure_ascii=False, default=str)
        if key not in self._cache:
            self._cache[key] = self._load(replay)
        return self._cache[key]


def cited_sources_for(report: dict[str, Any], row: dict[str, Any], item, index: PromptIndex) -> tuple[list[dict[str, str]] | None, str]:
    """(cited excerpts, status). Excerpts are given only when recovery is unambiguous: the prompt
    folder matches the report, the prompt contains the question, the excerpt numbering is 1..n
    and matches the row's `n_passages`, and every cited number exists."""
    prompts = index.prompts(report.get("replay") or {})
    if prompts is None:
        return None, "no_prompt_folder"
    user = prompts.get((row.get("suite") or report.get("suite", ""), row["id"]))
    if user is None:
        return None, "no_prompt_for_case"
    if item.formatted_query() not in user:
        return None, "question_not_in_prompt"
    blocks = parse_prompt_sources(user)
    if sorted(blocks) != list(range(1, len(blocks) + 1)):
        return None, "bad_numbering"
    if row.get("n_passages") is not None and int(row["n_passages"]) != len(blocks):
        return None, "n_passages_mismatch"
    labels = cited_labels(row.get("answer", ""))
    if any(n not in blocks for n in labels):
        return None, "cites_unknown_label"
    return bound_sources(blocks, labels), ("ok" if labels else "ok_no_citation")


# ---------------------------------------------------------------- per-verdict metrics


def apply_v4_consistency(item, verdict: dict[str, Any]) -> dict[str, Any]:
    """Pre-declared consistency rules of rubric v4, applied after judging. They can only lower
    `correctness`; each change is recorded in `v4_overrides` and counted in the merge output.

    1. "correct" requires every mandatory claim (non-clarification questions).
    2. Clarification question: a single conduct ("answer") is at most "partial"; a clarification
       is "correct" only if it asks for every required missing information, "incorrect" if it asks
       for none; an abstention is "incorrect".
    3. An abstention on a question the corpus covers is "incorrect"."""
    v = dict(verdict)
    if v.get("technical_failure") or item is None:
        return v
    notes = []

    def cap(level: str, why: str) -> None:
        order = {"incorrect": 0, "partial": 1, "correct": 2}
        if order[v["correctness"]] > order[level]:
            notes.append(f"{v['correctness']}->{level}: {why}")
            v["correctness"] = level

    clar = _is_clarification_item(item)
    if not clar and item.mandatory_claims and "claims_satisfied" in v:
        ids = {c["claim_id"] for c in item.mandatory_claims}
        if not ids <= set(v["claims_satisfied"]):
            cap("partial", "mandatory claim not satisfied")
    if clar:
        b = v.get("behavior")
        if b == "answer":
            cap("partial", "single conduct on a clarification question")
        elif b == "abstention":
            cap("incorrect", "abstention on a clarification question")
        elif b == "clarification" and item.required_missing_information and "missing_info_requested" in v:
            req = {m["id"] for m in missing_info_ids(item.required_missing_information)}
            got = req & set(v["missing_info_requested"])
            if not got:
                cap("incorrect", "clarification asks for none of the required information")
            elif got != req:
                cap("partial", "clarification asks for part of the required information")
    if not getattr(item, "should_abstain", False) and v.get("abstained") is True:
        cap("incorrect", "abstention on a covered question")
    if notes:
        v["v4_overrides"] = notes
    return v


# keys where 1 is good (combined: all passes) and keys where 1 is bad (combined: any pass)
GOOD_KEYS = ("judge_correct", "judge_correct_or_partial", "judge_no_omission", "judge_behavior_ok",
             "judge_behavior_ok_lenient", "judge_behavior_ok_case_by_case", "judge_faithful",
             "judge_missing_info_complete")
BAD_KEYS = ("judge_serious_error", "judge_forbidden_violation", "judge_false_abstention",
            "judge_missing_abstention", "judge_technical_failure")
MEAN_KEYS = ("judge_claims_rate",)
STRUCTURED_METRICS = ("judge_claims_rate", "judge_no_omission", "judge_forbidden_violation", "judge_behavior_ok")


def structured_row_metrics(item, verdict: dict[str, Any]) -> dict[str, float]:
    """Claim / behaviour metrics of one judged answer; empty when the item or the verdict has no
    structured fields (older reports and suites stay unchanged)."""
    out: dict[str, float] = {}
    if item is None:
        return out
    if item.mandatory_claims and "claims_satisfied" in verdict:
        ids = {c["claim_id"] for c in item.mandatory_claims}
        sat = ids & set(verdict.get("claims_satisfied") or [])
        out["judge_claims_rate"] = len(sat) / len(ids)
        out["judge_no_omission"] = 1.0 if sat == ids else 0.0
    if item.forbidden_claims and "forbidden_violated" in verdict:
        ids = {c["claim_id"] for c in item.forbidden_claims}
        out["judge_forbidden_violation"] = 1.0 if ids & set(verdict.get("forbidden_violated") or []) else 0.0
    if item.expected_behavior and verdict.get("behavior"):
        b = verdict["behavior"]
        strict = b in acceptable_behaviors(item)
        out["judge_behavior_ok"] = 1.0 if strict else 0.0
        out["judge_behavior_ok_lenient"] = 1.0 if b in acceptable_behaviors(item, lenient=True) else 0.0
        out["judge_behavior_ok_case_by_case"] = 1.0 if (strict or verdict.get("alternative_justified") is True) else 0.0
    if _is_clarification_item(item) and item.required_missing_information and verdict.get("behavior") == "clarification" \
            and "missing_info_requested" in verdict:
        req = {m["id"] for m in missing_info_ids(item.required_missing_information)}
        out["judge_missing_info_complete"] = 1.0 if req <= set(verdict["missing_info_requested"]) else 0.0
    return out


def row_metrics(item, verdict: dict[str, Any]) -> dict[str, float]:
    """All judge metrics of one verdict (after `apply_v4_consistency`). A technical failure
    counts as incorrect and as behaviour not accepted; its safety status is undetermined."""
    if verdict.get("technical_failure"):
        out = {"judge_correct": 0.0, "judge_correct_or_partial": 0.0, "judge_technical_failure": 1.0}
        if item is not None and item.expected_behavior:
            out.update({"judge_behavior_ok": 0.0, "judge_behavior_ok_lenient": 0.0, "judge_behavior_ok_case_by_case": 0.0})
        return out
    c = verdict["correctness"]
    out = {"judge_correct": 1.0 if c == "correct" else 0.0,
           "judge_correct_or_partial": 1.0 if c in ("correct", "partial") else 0.0,
           "judge_serious_error": 1.0 if verdict.get("serious_error") in SERIOUS else 0.0,
           "judge_technical_failure": 0.0}
    if item is not None:
        abst = verdict.get("abstained") is True or verdict.get("behavior") == "abstention"
        if item.should_abstain:
            out["judge_missing_abstention"] = 0.0 if abst else 1.0
        else:
            out["judge_false_abstention"] = 1.0 if abst else 0.0
    if isinstance(verdict.get("faithful"), bool):
        out["judge_faithful"] = 1.0 if verdict["faithful"] else 0.0
    out.update(structured_row_metrics(item, verdict))
    return out


def combine_passes(per_pass: list[dict[str, float]]) -> dict[str, float]:
    """Pre-declared combination of several judges' metrics for one answer.

    Headline (conservative): a "good" outcome (correct, behaviour accepted, ...) only if every
    pass gives it; a "bad" outcome (serious error, violation, ...) if any pass gives it; claims
    rate = minimum. Spread: `<good>_any` (either judge) and `<bad>_all` (every judge),
    `judge_claims_rate_max`. A key absent from a pass (undetermined there) is decided by the
    passes that have it."""
    out: dict[str, float] = {}
    for k in GOOD_KEYS:
        vals = [m[k] for m in per_pass if k in m]
        if vals:
            out[k] = min(vals)
            out[k + "_any"] = max(vals)
    for k in BAD_KEYS:
        vals = [m[k] for m in per_pass if k in m]
        if vals:
            out[k] = max(vals)
            out[k + "_all"] = min(vals)
    for k in MEAN_KEYS:
        vals = [m[k] for m in per_pass if k in m]
        if vals:
            out[k] = min(vals)
            out[k + "_max"] = max(vals)
    return out


def summarize_judge(rows: list[dict[str, Any]], keys: list[str]) -> dict[str, Any]:
    """Exact Clopper-Pearson CI for 0/1 metrics, bootstrap for the others."""
    out = {}
    for k in keys:
        vals = [r[k] for r in rows if k in r and r[k] is not None]
        if not vals:
            continue
        if all(v in (0.0, 1.0) for v in vals) and not k.startswith("judge_claims_rate"):
            out[k] = aggregate_binary(vals)
        else:
            out[k] = _aggregate([{k: v} for v in vals], k)
    return out


# ---------------------------------------------------------------- agreement


def agreement(verdicts_a: dict[str, dict[str, Any]], verdicts_b: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Inter-judge agreement over the cases both judges decided: Cohen's kappa and raw agreement
    on correctness (3 classes), serious error (yes/no) and behaviour label."""
    ids = sorted(i for i in verdicts_a if i in verdicts_b
                 and not verdicts_a[i].get("technical_failure") and not verdicts_b[i].get("technical_failure"))
    res: dict[str, Any] = {"n": len(ids)}

    def block(fa, fb, keep=lambda i: True):
        sel = [i for i in ids if keep(i)]
        a = [fa(verdicts_a[i]) for i in sel]
        b = [fb(verdicts_b[i]) for i in sel]
        if not sel:
            return {"n": 0, "raw": None, "kappa": None, "disagreements": []}
        k = cohen_kappa(a, b)
        return {"n": len(sel), "raw": sum(x == y for x, y in zip(a, b)) / len(sel),
                "kappa": None if k != k else k,
                "confusion": dict(Counter(f"{x}|{y}" for x, y in zip(a, b))),
                "disagreements": [i for i, x, y in zip(sel, a, b) if x != y]}

    res["correctness"] = block(lambda v: v["correctness"], lambda v: v["correctness"])
    res["serious_error"] = block(lambda v: v["serious_error"] in SERIOUS, lambda v: v["serious_error"] in SERIOUS)
    res["behavior"] = block(lambda v: v.get("behavior"), lambda v: v.get("behavior"),
                            keep=lambda i: bool(verdicts_a[i].get("behavior") and verdicts_b[i].get("behavior")))
    return res


# ---------------------------------------------------------------- helpers


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def assert_git_ignored(path: Path) -> None:
    """Judge batches contain benchmark text: refuse to write them where git would track them."""
    probe = path / "judge_input_0.json"
    try:
        r = subprocess.run(["git", "check-ignore", "-q", str(probe)], cwd=ROOT, capture_output=True)
    except OSError:
        return
    if r.returncode == 1:
        raise SystemExit(f"{path} is not git-ignored; judge batches contain benchmark text. Use a run name "
                         f"starting with 'blind_' (ignored by .gitignore) or add an ignore rule.")


def _opaque_ids(n: int, rng: random.Random) -> list[str]:
    seen: set[str] = set()
    out = []
    while len(out) < n:
        x = f"x{rng.getrandbits(40):010x}"
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _split_even(cases: list[Any], batch_size: int) -> list[list[Any]]:
    n_batches = max(1, -(-len(cases) // batch_size))
    base, extra = divmod(len(cases), n_batches)
    out, i = [], 0
    for b in range(n_batches):
        size = base + (1 if b < extra else 0)
        out.append(cases[i:i + size])
        i += size
    return out


def _write_batches(cases: list[dict[str, Any]], run_dir: Path, batch_size: int) -> list[dict[str, Any]]:
    batches = []
    for p, part in enumerate(_split_even(cases, batch_size)):
        f = run_dir / f"judge_input_{p}.json"
        f.write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8")
        batches.append({"part": p, "file": f.name, "n": len(part), "case_ids": [c["case_id"] for c in part]})
    return batches


# ---------------------------------------------------------------- blind export


def export_blind(reports: list[Path], run: str, batch_size: int = 25, seed: int = 20261127, sources: str = "auto",
                 runs_dir: Path = RUNS_DIR, keys_dir: Path = KEYS_DIR, frontier_root: Path = FRONTIER_ROOT,
                 check_ignored: bool = True) -> dict[str, Any]:
    """Cases of every report shuffled together under opaque ids, in batches of ~batch_size.

    Judges read only `<runs_dir>/<run>/judge_input_<P>.json`. The key (opaque id -> report,
    config, question id, split) and the manifest go to `<keys_dir>/<run>/`."""
    run_dir, key_dir = runs_dir / run, keys_dir / run
    if run_dir.exists() and any(run_dir.glob("judge_input_*.json")):
        raise SystemExit(f"{run_dir} already holds judge batches; choose a new run name")
    if check_ignored:
        run_dir.mkdir(parents=True, exist_ok=True)
        assert_git_ignored(run_dir)
    rng = random.Random(seed)
    index = PromptIndex(frontier_root)
    entries = []
    source_status: Counter[str] = Counter()
    for rp in reports:
        rep = json.loads(rp.read_text(encoding="utf-8"))
        items = {it.id: it for it in load_suite(rep["suite"], rep["split"])}
        for ri, run_ in enumerate(rep["runs"]):
            for row in run_["rows"]:
                if "answer" not in row:
                    continue
                it = items[row["id"]]
                cited, status = (None, "off") if sources == "off" else cited_sources_for(rep, row, it, index)
                source_status[status] += 1
                entries.append({"report": str(rp), "run_index": ri, "config": run_["config"], "row_id": row["id"],
                                "suite": rep["suite"], "split": rep["split"], "sources_status": status,
                                "_case": build_case(it, row["answer"], "", cited)})
    if not entries:
        raise SystemExit("no answers to judge in these reports")
    rng.shuffle(entries)
    for e, oid in zip(entries, _opaque_ids(len(entries), rng)):
        e["opaque_id"] = oid
        e["_case"]["case_id"] = oid
    run_dir.mkdir(parents=True, exist_ok=True)
    key_dir.mkdir(parents=True, exist_ok=True)
    batches = _write_batches([e["_case"] for e in entries], run_dir, batch_size)
    mapping = {e["opaque_id"]: {k: v for k, v in e.items() if not k.startswith("_") and k != "opaque_id"} for e in entries}
    manifest = {
        "run": run, "rubric": RUBRIC_VERSION, "created": dt.datetime.now().isoformat(timespec="seconds"),
        "git": _git_rev(), "seed": seed, "batch_size": batch_size, "n_cases": len(entries),
        "reports": [str(r) for r in reports], "run_dir": str(run_dir), "sources": sources,
        "sources_status": dict(source_status),
        "instructions_sha256": {f.name: _sha256(f) for f in INSTRUCTION_FILES},
        "batches": [{k: v for k, v in b.items()} for b in batches],
        "batch_sha256": {b["file"]: _sha256(run_dir / b["file"]) for b in batches},
    }
    (key_dir / "mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    (key_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(entries)} cases from {len(reports)} reports in {len(batches)} batches -> {run_dir}")
    print(f"key and manifest -> {key_dir} (do not show to judges); sources: {dict(source_status)}")
    return manifest


# ---------------------------------------------------------------- reading judge outputs


def read_pass(run_dir: Path, pass_id: str, batches: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Verdicts of one judge pass (`<run_dir>/pass_<id>/judge_out_<P>.json`), validated against
    the batches. Returns (verdicts by case id, problems). A problem is a missing file, an
    unparseable file, a missing case, a case id not in the batch, or an invalid verdict."""
    pdir = run_dir / f"pass_{pass_id}"
    verdicts: dict[str, dict[str, Any]] = {}
    problems: list[dict[str, Any]] = []
    for b in batches:
        f = pdir / f"judge_out_{b['part']}.json"
        expected = list(b["case_ids"])
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("not a JSON list")
        except (OSError, ValueError) as exc:
            problems += [{"pass": pass_id, "case_id": cid, "part": b["part"], "problem": f"batch output unreadable: {type(exc).__name__}"} for cid in expected]
            continue
        got = {}
        for obj in data:
            cid = obj.get("case_id") if isinstance(obj, dict) else None
            if cid not in expected:
                problems.append({"pass": pass_id, "case_id": cid, "part": b["part"], "problem": "case id not in batch"})
                continue
            if cid in got:
                problems.append({"pass": pass_id, "case_id": cid, "part": b["part"], "problem": "duplicate verdict"})
                continue
            got[cid] = normalize_verdict(obj)
        for cid in expected:
            v = got.get(cid)
            if v is None:
                problems.append({"pass": pass_id, "case_id": cid, "part": b["part"], "problem": "missing verdict"})
            elif v.get("technical_failure"):
                problems.append({"pass": pass_id, "case_id": cid, "part": b["part"], "problem": v["justification"]})
                verdicts[cid] = v
            else:
                verdicts[cid] = v
    return verdicts, problems


def _failure(reason: str) -> dict[str, Any]:
    return {"correctness": None, "abstained": None, "serious_error": None, "faithful": None,
            "justification": reason, "technical_failure": True}


# ---------------------------------------------------------------- blind merge


def _fmt(a: dict[str, Any] | None, n: bool = False) -> str:
    if not a:
        return "—"
    s = f"{a['mean'] * 100:.1f} [{a['ci_low'] * 100:.1f}–{a['ci_high'] * 100:.1f}]"
    if n:
        s += f" ({a.get('k', round(a['mean'] * a['n']))}/{a['n']})" if a.get("k") is not None else f" (n={a['n']})"
    return s


HEADLINE = ["judge_correct", "judge_correct_or_partial", "judge_serious_error", "judge_behavior_ok",
            "judge_false_abstention", "judge_missing_abstention", "judge_faithful", "judge_technical_failure"]


def merge_blind(run: str, passes: list[str], allow_missing: bool = False, label: str = "claude-haiku (subagents)",
                runs_dir: Path = RUNS_DIR, keys_dir: Path = KEYS_DIR, out_root: Path = MERGE_OUT,
                in_place: bool = False) -> dict[str, Any]:
    run_dir, key_dir = runs_dir / run, keys_dir / run
    manifest = json.loads((key_dir / "manifest.json").read_text(encoding="utf-8"))
    mapping = json.loads((key_dir / "mapping.json").read_text(encoding="utf-8"))
    batches = manifest["batches"]
    changed = {n: h for n, h in manifest["instructions_sha256"].items() if _sha256(JUDGE_HOME / n) != h}
    if changed:
        print(f"WARNING: judge instructions changed since export: {sorted(changed)}")
    raw: dict[str, dict[str, dict[str, Any]]] = {}
    problems: list[dict[str, Any]] = []
    for p in passes:
        raw[p], pr = read_pass(run_dir, p, batches)
        problems += pr
    if problems and not allow_missing:
        lines = "\n".join(f"  pass {x['pass']} part {x['part']} {x['case_id']}: {x['problem']}" for x in problems[:50])
        raise SystemExit(f"{len(problems)} missing or invalid verdicts (re-judge them, or pass --allow-missing to "
                         f"count them as incorrect):\n{lines}")
    for p in passes:
        for cid in mapping:
            raw[p].setdefault(cid, _failure("missing verdict"))

    out_dir = out_root / run
    out_dir.mkdir(parents=True, exist_ok=True)
    by_report: dict[str, list[str]] = {}
    for cid, m in mapping.items():
        by_report.setdefault(m["report"], []).append(cid)
    overrides: Counter[str] = Counter()
    final: dict[str, dict[str, dict[str, Any]]] = {p: {} for p in passes}  # verdicts after the v4 consistency rules
    summary_reports = []
    all_keys = [*HEADLINE, *[k for k in (*GOOD_KEYS, *BAD_KEYS, *MEAN_KEYS) if k not in HEADLINE]]
    all_keys += [k + "_any" for k in GOOD_KEYS] + [k + "_all" for k in BAD_KEYS] + [k + "_max" for k in MEAN_KEYS]
    for rpath, cids in by_report.items():
        rep = json.loads(Path(rpath).read_text(encoding="utf-8"))
        items = {it.id: it for it in load_suite(rep["suite"], rep["split"])}
        index = {(mapping[c]["run_index"], mapping[c]["row_id"]): c for c in cids}
        for ri, run_ in enumerate(rep["runs"]):
            for row in run_["rows"]:
                cid = index.get((ri, row["id"]))
                if cid is None:
                    continue
                it = items.get(row["id"])
                if "judge" in row:
                    row["judge_previous"] = row.pop("judge")
                for k in [k for k in row if k.startswith("judge_") and k != "judge_previous"]:
                    row.pop(k)
                per_pass, verdicts = [], {}
                for p in passes:
                    v = apply_v4_consistency(it, raw[p][cid])
                    final[p][cid] = v
                    overrides.update(o.split(":")[1].strip() for o in v.get("v4_overrides", []))
                    verdicts[p] = v
                    m = row_metrics(it, v)
                    per_pass.append(m)
                    for k, val in m.items():
                        row[f"{k}@{p}"] = val
                row["judge_v4"] = {"rubric": RUBRIC_VERSION, "run": run, "opaque_id": cid, "passes": verdicts}
                row.update(combine_passes(per_pass))
            pass_keys = [f"{k}@{p}" for p in passes for k in HEADLINE]
            summ = run_["summary"]
            for k in [k for k in summ if k.startswith("judge_")]:
                summ.pop(k)
            summ.update(summarize_judge(run_["rows"], all_keys + pass_keys))
            summ["judge_serious_error_types"] = {p: dict(Counter(
                r["judge_v4"]["passes"][p].get("serious_error") for r in run_["rows"]
                if "judge_v4" in r and r["judge_v4"]["passes"][p].get("serious_error") in SERIOUS)) for p in passes}
            summ["judge_agreement"] = {f"{a}-{b}": agreement(
                {r["judge_v4"]["opaque_id"]: r["judge_v4"]["passes"][a] for r in run_["rows"] if "judge_v4" in r},
                {r["judge_v4"]["opaque_id"]: r["judge_v4"]["passes"][b] for r in run_["rows"] if "judge_v4" in r})
                for a, b in combinations(passes, 2)}
        rep_problems = [x for x in problems if x["case_id"] in set(cids)]
        rep["judge"] = {"rubric": RUBRIC_VERSION, "label": label, "run": run, "run_dir": str(run_dir), "passes": passes,
                        "combination": "headline: correct/behaviour accepted only if every pass agrees; serious error if any pass reports one; "
                                       "'_any' = either judge (good outcomes), '_all' = every judge (bad outcomes)",
                        "missing_or_invalid": len(rep_problems), "problems": rep_problems,
                        "instructions_changed_since_export": sorted(changed), "merged": dt.datetime.now().isoformat(timespec="seconds")}
        target = Path(rpath) if in_place else out_dir / Path(rpath).name
        target.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        target.with_suffix(".md").write_text(to_markdown(rep) + "\n" + _judge_markdown(rep, passes) + "\n", encoding="utf-8")
        for run_ in rep["runs"]:
            summary_reports.append({"report": rpath, "suite": rep["suite"], "split": rep["split"], "config": run_["config"],
                                    "merged": str(target), "summary": {k: v for k, v in run_["summary"].items() if k.startswith("judge_")}})
    overall = {f"{a}-{b}": agreement(final[a], final[b]) for a, b in combinations(passes, 2)}
    result = {"run": run, "rubric": RUBRIC_VERSION, "passes": passes, "label": label, "n_cases": len(mapping),
              "missing_or_invalid": len(problems), "problems": problems, "consistency_overrides": dict(overrides),
              "agreement": overall, "instructions_changed_since_export": sorted(changed), "reports": summary_reports}
    (out_dir / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "summary.md").write_text(_summary_markdown(result), encoding="utf-8")
    print(f"merged {len(passes)} passes over {len(mapping)} cases ({len(problems)} missing/invalid) -> {out_dir}")
    return result


def _agreement_lines(agr: dict[str, Any]) -> list[str]:
    lines = ["| Juges | n | Correctness (3 classes) : accord brut / κ | Erreur grave : accord brut / κ | Comportement : accord brut / κ |",
             "|---|---:|---|---|---|"]
    def f(b: dict[str, Any] | None) -> str:
        if not b or b["raw"] is None:
            return "—"
        kap = "—" if b["kappa"] is None else f"{b['kappa']:.2f}"
        return f"{b['raw'] * 100:.1f} % / {kap} (n={b['n']})"

    for pair, a in agr.items():
        lines.append(f"| {pair} | {a['n']} | {f(a['correctness'])} | {f(a['serious_error'])} | {f(a['behavior'])} |")
    return lines


def _judge_markdown(rep: dict[str, Any], passes: list[str]) -> str:
    j = rep["judge"]
    lines = [f"## Juge LLM — grille {j['rubric']}, {len(passes)} passes à l'aveugle ({j['label']}, lot `{j['run']}`)", "",
             f"Combinaison déclarée d'avance : {j['combination']}. Verdicts manquants ou invalides : {j['missing_or_invalid']}. "
             "IC exacts de Clopper-Pearson pour les taux (0/1), bootstrap pour le taux de faits.", "",
             "| Config | Correct (tous) | Correct (un juge) | Correct ou partiel | Erreur grave (un juge) | Erreur grave (tous) | Comportement strict | Comportement élargi | Comportement au cas par cas | Abstention à tort | Abstention manquante | Fidèle aux extraits |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for run_ in rep["runs"]:
        s = run_["summary"]
        g = lambda k: _fmt(s.get(k), n=True)
        lines.append(f"| `{run_['config']}` | {g('judge_correct')} | {g('judge_correct_any')} | {g('judge_correct_or_partial')} | "
                     f"{g('judge_serious_error')} | {g('judge_serious_error_all')} | {g('judge_behavior_ok')} | {g('judge_behavior_ok_lenient')} | "
                     f"{g('judge_behavior_ok_case_by_case')} | {g('judge_false_abstention')} | {g('judge_missing_abstention')} | {g('judge_faithful')} |")
    lines += ["", "Par juge :", "", "| Config | Juge | Correct | Correct ou partiel | Erreur grave | Comportement strict | Types d'erreurs graves |", "|---|---|---|---|---|---|---|"]
    for run_ in rep["runs"]:
        s = run_["summary"]
        for p in passes:
            lines.append(f"| `{run_['config']}` | {p} | {_fmt(s.get(f'judge_correct@{p}'), True)} | {_fmt(s.get(f'judge_correct_or_partial@{p}'), True)} | "
                         f"{_fmt(s.get(f'judge_serious_error@{p}'), True)} | {_fmt(s.get(f'judge_behavior_ok@{p}'), True)} | "
                         f"{s.get('judge_serious_error_types', {}).get(p, {})} |")
    for run_ in rep["runs"]:
        if run_["summary"].get("judge_agreement"):
            lines += ["", f"Accord entre juges (`{run_['config']}`) :", "", *_agreement_lines(run_["summary"]["judge_agreement"])]
    return "\n".join(lines)


def _summary_markdown(res: dict[str, Any]) -> str:
    lines = [f"# Jugement à l'aveugle `{res['run']}` — grille {res['rubric']}", "",
             f"{res['n_cases']} réponses, passes {', '.join(res['passes'])} ({res['label']}). Verdicts manquants ou invalides : "
             f"**{res['missing_or_invalid']}**. Corrections de cohérence v4 (ne peuvent que baisser correctness) : {res['consistency_overrides'] or 'aucune'}.", "",
             "Combinaison déclarée d'avance : correct et comportement accepté seulement si tous les juges l'accordent ; erreur grave si un juge en signale une. "
             "« un juge » / « tous » donnent l'écart. IC 95 % exacts (Clopper-Pearson).", "",
             "| Rapport | Split | n | Correct (tous) | Correct (un juge) | Correct ou partiel (tous) | Erreur grave (un juge) | Erreur grave (tous) | Comportement strict | Comportement élargi | Abstention à tort | Abstention manquante | Échec technique |",
             "|---|---|---:|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["reports"]:
        s = r["summary"]
        g = lambda k: _fmt(s.get(k), n=True)
        n = (s.get("judge_correct") or {}).get("n", "—")
        lines.append(f"| {Path(r['report']).stem} | {r['split']} | {n} | {g('judge_correct')} | {g('judge_correct_any')} | {g('judge_correct_or_partial')} | "
                     f"{g('judge_serious_error')} | {g('judge_serious_error_all')} | {g('judge_behavior_ok')} | {g('judge_behavior_ok_lenient')} | "
                     f"{g('judge_false_abstention')} | {g('judge_missing_abstention')} | {g('judge_technical_failure')} |")
    lines += ["", "## Accord entre juges (toutes réponses)", "", *_agreement_lines(res["agreement"])]
    if res["problems"]:
        lines += ["", "## Verdicts manquants ou invalides (comptés incorrects, sécurité indéterminée)", ""]
        lines += [f"- passe {x['pass']}, lot {x['part']}, `{x['case_id']}` : {x['problem']}" for x in res["problems"]]
    if res["instructions_changed_since_export"]:
        lines += ["", f"**Attention** : consignes modifiées depuis l'export : {res['instructions_changed_since_export']}"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- blind calibration


def export_calibration_blind(run: str, calib_dir: Path = JUDGE_HOME, suite: str = "abp171", batch_size: int = 25,
                             seed: int = 20261127, runs_dir: Path = RUNS_DIR, keys_dir: Path = KEYS_DIR,
                             check_ignored: bool = True) -> dict[str, Any]:
    """Calibration cases (deterministic truth) and the length probe, restricted to dev questions,
    as blind batches for the v4 judges."""
    run_dir, key_dir = runs_dir / run, keys_dir / run
    if run_dir.exists() and any(run_dir.glob("judge_input_*.json")):
        raise SystemExit(f"{run_dir} already holds judge batches; choose a new run name")
    if check_ignored:
        run_dir.mkdir(parents=True, exist_ok=True)
        assert_git_ignored(run_dir)
    dev = {it.id for it in load_suite(suite, "dev")}
    cases = [c for c in json.loads((calib_dir / "calibration_cases.json").read_text(encoding="utf-8")) if c["qid"] in dev]
    keep = {c["case_id"] for c in cases}
    pairs = [p for p in json.loads((calib_dir / "length_probe_pairs.json").read_text(encoding="utf-8")) if p[0] in keep and p[1] in keep]
    rng = random.Random(seed)
    rng.shuffle(cases)
    ids = _opaque_ids(len(cases), rng)
    mapping = {oid: {"calib_id": c["case_id"], "src": c["src"], "qid": c["qid"], "truth": int(c["truth"])} for oid, c in zip(ids, cases)}
    judge_cases = [{"case_id": oid, "question": c["question"], "reference": c["reference"], "answer": c["answer"]} for oid, c in zip(ids, cases)]
    run_dir.mkdir(parents=True, exist_ok=True)
    key_dir.mkdir(parents=True, exist_ok=True)
    batches = _write_batches(judge_cases, run_dir, batch_size)
    rev = {m["calib_id"]: oid for oid, m in mapping.items()}
    manifest = {"run": run, "rubric": RUBRIC_VERSION, "kind": "calibration", "created": dt.datetime.now().isoformat(timespec="seconds"),
                "git": _git_rev(), "seed": seed, "n_cases": len(cases), "suite_filter": f"{suite} dev",
                "length_pairs": [[rev[a], rev[b]] for a, b in pairs], "batches": batches,
                "instructions_sha256": {f.name: _sha256(f) for f in INSTRUCTION_FILES}}
    (key_dir / "mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    (key_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(cases)} calibration cases ({len(pairs)} length pairs) in {len(batches)} batches -> {run_dir}; key -> {key_dir}")
    return manifest


def calibrate_blind(run: str, passes: list[str], allow_missing: bool = False, runs_dir: Path = RUNS_DIR,
                    keys_dir: Path = KEYS_DIR, out_root: Path = MERGE_OUT) -> dict[str, Any]:
    """Per pass: kappa / agreement of `correct` against the deterministic key (padded copies of
    the length probe excluded) and verdicts changed by the padding; between passes: test-retest."""
    run_dir, key_dir = runs_dir / run, keys_dir / run
    manifest = json.loads((key_dir / "manifest.json").read_text(encoding="utf-8"))
    mapping = json.loads((key_dir / "mapping.json").read_text(encoding="utf-8"))
    raw, problems = {}, []
    for p in passes:
        raw[p], pr = read_pass(run_dir, p, manifest["batches"])
        problems += pr
    if problems and not allow_missing:
        raise SystemExit(f"{len(problems)} missing or invalid verdicts; re-judge or pass --allow-missing")
    pairs = manifest["length_pairs"]
    padded = {b for _, b in pairs}
    res: dict[str, Any] = {"run": run, "rubric": RUBRIC_VERSION, "passes": {}, "missing_or_invalid": len(problems), "problems": problems}
    for p in passes:
        truth, pred, per_src = [], [], {}
        for oid, m in mapping.items():
            if oid in padded:
                continue
            v = raw[p].get(oid) or _failure("missing verdict")
            y = 1 if v.get("correctness") == "correct" else 0
            truth.append(m["truth"])
            pred.append(y)
            per_src.setdefault(m["src"], []).append((m["truth"], y))
        k = cohen_kappa(truth, pred)
        changed = sum(1 for a, b in pairs if (raw[p].get(a) or {}).get("correctness") != (raw[p].get(b) or {}).get("correctness"))
        res["passes"][p] = {
            "n": len(truth), "agreement": sum(a == b for a, b in zip(truth, pred)) / max(1, len(truth)), "kappa": None if k != k else k,
            "confusion": {"tp": sum(1 for a, b in zip(truth, pred) if a and b), "tn": sum(1 for a, b in zip(truth, pred) if not a and not b),
                          "fp": sum(1 for a, b in zip(truth, pred) if not a and b), "fn": sum(1 for a, b in zip(truth, pred) if a and not b)},
            "by_source": {s: {"n": len(v), "agreement": sum(a == b for a, b in v) / len(v)} for s, v in per_src.items()},
            "length_probe": {"pairs": len(pairs), "verdict_changed": changed},
            "serious_errors": dict(Counter(v.get("serious_error") for v in raw[p].values() if v.get("serious_error") in SERIOUS)),
        }
    res["test_retest"] = {f"{a}-{b}": agreement(raw[a], raw[b]) for a, b in combinations(passes, 2)}
    out_dir = out_root / run
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "calibration_v4.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Calibration du juge, grille {RUBRIC_VERSION} (`{run}`)", "",
             f"Vérité = clé déterministe (lettre du QCM ou molécules), {manifest['suite_filter']} seulement. Verdicts manquants ou invalides : {len(problems)}.", "",
             "| Juge | n | Accord | κ | VP | VN | FP | FN | Sonde de longueur (verdicts changés) |", "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for p, r in res["passes"].items():
        c = r["confusion"]
        kap = "—" if r["kappa"] is None else f"{r['kappa']:.2f}"
        lines.append(f"| {p} | {r['n']} | {r['agreement'] * 100:.1f} % | {kap} | {c['tp']} | {c['tn']} | {c['fp']} | {c['fn']} | "
                     f"{r['length_probe']['verdict_changed']}/{r['length_probe']['pairs']} |")
    lines += ["", "Test-retest entre juges :", "", *_agreement_lines(res["test_retest"])]
    (out_dir / "calibration_v4.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({p: {k: r[k] for k in ("n", "agreement", "kappa", "length_probe")} for p, r in res["passes"].items()}, indent=1))
    return res


def show(run: str, part: int, start: int = 0, count: int = 25, runs_dir: Path = RUNS_DIR, width: int = 150,
         max_chars: int = 20000) -> str:
    """Readable rendering of the cases of a batch from `start` (long lines wrapped), for judge
    agents whose file viewer cuts long lines. Stops before `max_chars` (always at least one case)
    and says where to continue."""
    import textwrap

    cases = json.loads((runs_dir / run / f"judge_input_{part}.json").read_text(encoding="utf-8"))
    blocks: list[str] = []
    for i, c in enumerate(cases[start:start + count], start):
        out: list[str] = [f"\n===== case {i} | case_id {c['case_id']} ====="]
        _show_case(c, out, width, textwrap)
        text = "\n".join(out)
        if blocks and sum(len(b) for b in blocks) + len(text) > max_chars:
            break
        blocks.append(text)
    end = start + len(blocks)
    head = f"# batch {part}: cases {start}..{end - 1} of {len(cases)} (0-based)"
    tail = f"\n# next: --start {end}" if end < len(cases) else "\n# end of batch"
    return head + "\n".join(blocks) + tail


def _show_case(c: dict[str, Any], out: list[str], width: int, textwrap) -> None:
    def put(label: str, text: str) -> None:
        out.append(f"{label}:")
        for ln in str(text).split("\n"):
            out.extend(textwrap.wrap(ln, width, initial_indent="  ", subsequent_indent="  ") or [""])

    for k in ("question", "reference", "reference_narrative", "answer"):
        if k in c:
            put(k, c[k])
    for k in ("mandatory_claims", "forbidden_claims", "required_missing_information"):
        if k in c:
            put(k, "\n".join(f"{x['id']} : {x['text']}" for x in c[k]))
    for k in ("expected_behavior", "acceptable_behaviors"):
        if k in c:
            put(k, c[k] if isinstance(c[k], str) else ", ".join(c[k]))
    if "cited_sources" in c:
        put("cited_sources", "\n".join("\n".join(s.get("lines") or [f"[{s['label']}] " + s.get("text", "")]) for s in c["cited_sources"])
            or "(aucun extrait cité)")


# ---------------------------------------------------------------- legacy single-report commands


def export(report_path: Path, out_dir: Path, parts: int) -> None:
    """Legacy (not blind): case ids show the configuration. Use export-blind for conclusions."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    items = {it.id: it for it in load_suite(report["suite"], report["split"])}
    cases = [build_case(items[row["id"]], row["answer"], f"{run['config']}::{row['id']}")
             for run in report["runs"] for row in run["rows"] if "answer" in row]
    out_dir.mkdir(parents=True, exist_ok=True)
    size = -(-len(cases) // parts)
    for i in range(parts):
        part = cases[i * size: (i + 1) * size]
        (out_dir / f"judge_input_{i}.json").write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(cases)} cases in {parts} batches -> {out_dir} (legacy, not blind)")


def _read_verdicts(judge_dir: Path) -> dict[str, dict[str, Any]]:
    out = {}
    for f in sorted(judge_dir.glob("judge_out_*.json")):
        for v in json.loads(f.read_text(encoding="utf-8")):
            out[v["case_id"]] = v
    return out


def merge(report_path: Path, judge_dir: Path, judge_label: str, allow_missing: bool = False) -> None:
    """Legacy single-pass merge into the report (in place), with the v4 metrics. A missing or
    invalid verdict fails unless `allow_missing` (then: incorrect, safety undetermined, listed)."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    verdicts = _read_verdicts(judge_dir)
    try:
        items = {it.id: it for it in load_suite(report["suite"], report["split"])}
    except Exception:  # noqa: BLE001 - a missing suite only disables the structured metrics
        items = {}
    problems = []
    for run in report["runs"]:
        for row in run["rows"]:
            if "answer" not in row:
                continue
            cid = f"{run['config']}::{row['id']}"
            v = normalize_verdict(verdicts[cid]) if cid in verdicts else _failure("missing verdict")
            if v.get("technical_failure"):
                problems.append(f"{cid}: {v['justification']}")
    if problems and not allow_missing:
        raise SystemExit(f"{len(problems)} missing or invalid verdicts:\n" + "\n".join(problems[:50]))
    keys = [*HEADLINE, "judge_no_omission", "judge_claims_rate", "judge_forbidden_violation", "judge_behavior_ok_lenient",
            "judge_behavior_ok_case_by_case", "judge_missing_info_complete"]
    for run in report["runs"]:
        for row in run["rows"]:
            if "answer" not in row:
                continue
            cid = f"{run['config']}::{row['id']}"
            it = items.get(row["id"])
            v = apply_v4_consistency(it, normalize_verdict(verdicts[cid]) if cid in verdicts else _failure("missing verdict"))
            for k in [k for k in row if k.startswith("judge_")]:
                row.pop(k)
            row["judge"] = v
            row.update(row_metrics(it, v))
        summ = run["summary"]
        for k in [k for k in summ if k.startswith("judge_")]:
            summ.pop(k)
        summ.update(summarize_judge(run["rows"], keys))
        summ["judge_serious_error_types"] = dict(Counter(
            r["judge"].get("serious_error") for r in run["rows"] if "judge" in r and r["judge"].get("serious_error") in SERIOUS))
    report["judge"] = {"rubric": RUBRIC_VERSION, "label": judge_label, "dir": str(judge_dir), "missing": len(problems),
                       "problems": problems, "blind": False}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md = to_markdown(report)
    lines = ["", f"## Juge LLM ({judge_label}, grille {RUBRIC_VERSION}, non aveugle)", "",
             "| Config | Correct | Correct ou partiel | Erreurs graves | Comportement strict | Abstention à tort | Types |", "|---|---|---|---|---|---|---|"]
    for run in report["runs"]:
        s = run["summary"]
        lines.append(f"| `{run['config']}` | {_fmt(s.get('judge_correct'), True)} | {_fmt(s.get('judge_correct_or_partial'), True)} | "
                     f"{_fmt(s.get('judge_serious_error'), True)} | {_fmt(s.get('judge_behavior_ok'), True)} | "
                     f"{_fmt(s.get('judge_false_abstention'), True)} | {s.get('judge_serious_error_types', {})} |")
    report_path.with_suffix(".md").write_text(md + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"merged {len(verdicts)} verdicts into {report_path} ({len(problems)} missing or invalid)")


def calibrate(judge_dir: Path) -> dict[str, Any]:
    """Legacy rubric-v1 calibration (judge_out_*.json next to calibration_cases.json)."""
    cases = {c["case_id"]: c for c in json.loads((judge_dir / "calibration_cases.json").read_text(encoding="utf-8"))}
    verdicts = _read_verdicts(judge_dir)
    pairs = json.loads((judge_dir / "length_probe_pairs.json").read_text(encoding="utf-8"))
    padded = {p[1] if "Il convient par ailleurs" in cases[p[1]]["answer"] else p[0] for p in pairs}
    truth, pred = [], []
    per_src: dict[str, list] = {}
    disagreements = []
    for cid, c in cases.items():
        if cid in padded or cid not in verdicts:
            continue
        p = 1 if verdicts[cid]["correctness"] == "correct" else 0
        truth.append(c["truth"])
        pred.append(p)
        per_src.setdefault(c["src"], []).append((c["truth"], p))
        if p != c["truth"]:
            disagreements.append({"case_id": cid, "src": c["src"], "qid": c["qid"], "truth": c["truth"],
                                  "judge": verdicts[cid]["correctness"], "reference": c["reference"],
                                  "answer": c["answer"][:300], "justification": verdicts[cid].get("justification", "")})
    changed = sum(1 for a, b in pairs if a in verdicts and b in verdicts and verdicts[a]["correctness"] != verdicts[b]["correctness"])
    res = {
        "n": len(truth),
        "agreement": sum(1 for a, b in zip(truth, pred) if a == b) / max(1, len(truth)),
        "kappa": cohen_kappa(truth, pred),
        "confusion": {"tp": sum(1 for a, b in zip(truth, pred) if a and b), "tn": sum(1 for a, b in zip(truth, pred) if not a and not b),
                      "fp": sum(1 for a, b in zip(truth, pred) if not a and b), "fn": sum(1 for a, b in zip(truth, pred) if a and not b)},
        "by_source": {s: {"n": len(v), "agreement": sum(1 for a, b in v if a == b) / len(v), "kappa": cohen_kappa([a for a, _ in v], [b for _, b in v])} for s, v in per_src.items()},
        "length_probe": {"pairs": len(pairs), "verdict_changed": changed},
        "disagreements": disagreements,
    }
    (judge_dir / "calibration_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


# ---------------------------------------------------------------- CLI


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    eb = sub.add_parser("export-blind", help="mix the answers of several reports into blind batches")
    eb.add_argument("--run", required=True, help="run name; must start with 'blind_' (git-ignored folder)")
    eb.add_argument("--reports", type=Path, nargs="+", required=True)
    eb.add_argument("--batch-size", type=int, default=25)
    eb.add_argument("--seed", type=int, default=20261127)
    eb.add_argument("--sources", choices=["auto", "off"], default="auto", help="pass the excerpts the answer cites (recovered from the replay prompts)")
    mb = sub.add_parser("merge-blind", help="merge two or more judge passes of a blind run")
    mb.add_argument("--run", required=True)
    mb.add_argument("--passes", default="a,b")
    mb.add_argument("--allow-missing", action="store_true", help="count missing/invalid verdicts as incorrect instead of failing")
    mb.add_argument("--label", default="claude-haiku (subagents)")
    mb.add_argument("--in-place", action="store_true", help="write the merged verdicts into the original reports")
    ec = sub.add_parser("export-calibration", help="blind batches of the calibration cases and the length probe (dev only)")
    ec.add_argument("--run", required=True)
    ec.add_argument("--batch-size", type=int, default=25)
    ec.add_argument("--seed", type=int, default=20261127)
    cb = sub.add_parser("calibrate-blind")
    cb.add_argument("--run", required=True)
    cb.add_argument("--passes", default="a,b")
    cb.add_argument("--allow-missing", action="store_true")
    sh = sub.add_parser("show", help="print cases of a batch with wrapped lines (for judge agents)")
    sh.add_argument("--run", required=True)
    sh.add_argument("--part", type=int, required=True)
    sh.add_argument("--start", type=int, default=0)
    sh.add_argument("--count", type=int, default=25)
    sh.add_argument("--max-chars", type=int, default=20000)
    e = sub.add_parser("export", help="legacy, not blind")
    e.add_argument("--report", type=Path, required=True)
    e.add_argument("--out-dir", type=Path, required=True)
    e.add_argument("--parts", type=int, default=4)
    m = sub.add_parser("merge", help="legacy single pass, in place")
    m.add_argument("--report", type=Path, required=True)
    m.add_argument("--judge-dir", type=Path, required=True)
    m.add_argument("--judge-label", default="claude-haiku (subagent)")
    m.add_argument("--allow-missing", action="store_true")
    c = sub.add_parser("calibrate", help="legacy rubric-v1 calibration")
    c.add_argument("--dir", type=Path, default=JUDGE_HOME)
    a = ap.parse_args()
    if a.cmd == "export-blind":
        export_blind(a.reports, a.run, a.batch_size, a.seed, a.sources)
    elif a.cmd == "merge-blind":
        merge_blind(a.run, a.passes.split(","), a.allow_missing, a.label, in_place=a.in_place)
    elif a.cmd == "export-calibration":
        export_calibration_blind(a.run, batch_size=a.batch_size, seed=a.seed)
    elif a.cmd == "calibrate-blind":
        calibrate_blind(a.run, a.passes.split(","), a.allow_missing)
    elif a.cmd == "show":
        print(show(a.run, a.part, a.start, a.count, max_chars=a.max_chars))
    elif a.cmd == "export":
        export(a.report, a.out_dir, a.parts)
    elif a.cmd == "merge":
        merge(a.report, a.judge_dir, a.judge_label, a.allow_missing)
    else:
        r = calibrate(a.dir)
        print(json.dumps({k: v for k, v in r.items() if k != "disagreements"}, ensure_ascii=False, indent=1))
        print(f"{len(r['disagreements'])} disagreements -> {a.dir / 'calibration_result.json'}")


if __name__ == "__main__":
    _cli()
