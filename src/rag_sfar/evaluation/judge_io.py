"""File-based bridge between eval reports and an external LLM judge (Claude Code subagents or
any batch process), plus judge calibration from files.

    # 1. export the answers of an eval report into judge batches
    python -m rag_sfar.evaluation.judge_io export --report reports/eval/X.json --out-dir eval_internal/judge/runs/X --parts 4
    # 2. (judges write judge_out_*.json next to judge_input_*.json, following
    #     eval_internal/judge/JUDGE_INSTRUCTIONS.md)
    # 3. merge verdicts back into the report (adds judge_* metrics with bootstrap CIs)
    python -m rag_sfar.evaluation.judge_io merge --report reports/eval/X.json --judge-dir eval_internal/judge/runs/X --judge-label haiku
    # calibration (kappa vs deterministic truth + length-bias probe)
    python -m rag_sfar.evaluation.judge_io calibrate --dir eval_internal/judge
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from rag_sfar.evaluation.datasets import load_suite
from rag_sfar.evaluation.harness import _aggregate, to_markdown
from rag_sfar.evaluation.judge import cohen_kappa

# "wrong_conduct" added 2026-11-27 (rubric v2): reports judged before that date coded opposite conducts as "other".
SERIOUS = ("wrong_drug", "wrong_dose", "wrong_conduct", "obsolete_as_current", "unsupported_claim", "missing_abstention")


def _reference(item) -> str:
    if item.question_type == "mcq" and "mcq" in item.answer_key:
        letter = item.answer_key["mcq"]
        return f"{letter} ({item.choices.get(letter, '')})"
    if item.should_abstain:
        return "(La question n'est pas couverte par les recommandations SFAR : la bonne réponse est de s'abstenir.)"
    return item.reference_answer


def export(report_path: Path, out_dir: Path, parts: int) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    items = {it.id: it for it in load_suite(report["suite"], report["split"]) }
    cases = []
    for run in report["runs"]:
        for row in run["rows"]:
            if "answer" not in row:
                continue
            it = items[row["id"]]
            case = {
                "case_id": f"{run['config']}::{row['id']}",
                "question": it.formatted_query(),
                "reference": _reference(it),
                "answer": row["answer"],
            }
            # Structured expectations (benchmark-enrichi), only when the item has them.
            if it.mandatory_claims:
                case["mandatory_claims"] = [{"id": c["claim_id"], "text": c["text"]} for c in it.mandatory_claims]
            if it.forbidden_claims:
                case["forbidden_claims"] = [{"id": c["claim_id"], "text": c["text"]} for c in it.forbidden_claims]
            if it.expected_behavior:
                case["expected_behavior"] = it.expected_behavior
            if it.required_missing_information:
                case["required_missing_information"] = it.required_missing_information
            cases.append(case)
    out_dir.mkdir(parents=True, exist_ok=True)
    size = -(-len(cases) // parts)
    for i in range(parts):
        part = cases[i * size : (i + 1) * size]
        (out_dir / f"judge_input_{i}.json").write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(cases)} cases in {parts} batches -> {out_dir}")


def _read_verdicts(judge_dir: Path) -> dict[str, dict[str, Any]]:
    out = {}
    for f in sorted(judge_dir.glob("judge_out_*.json")):
        for v in json.loads(f.read_text(encoding="utf-8")):
            out[v["case_id"]] = v
    return out


STRUCTURED_METRICS = ("judge_claims_rate", "judge_no_omission", "judge_forbidden_violation", "judge_behavior_ok")


def structured_row_metrics(item, verdict: dict[str, Any]) -> dict[str, float]:
    """Claim / behavior metrics of one judged answer; empty when the item or the verdict has no
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
        out["judge_behavior_ok"] = 1.0 if verdict["behavior"] == item.expected_behavior else 0.0
    return out


def merge(report_path: Path, judge_dir: Path, judge_label: str) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    verdicts = _read_verdicts(judge_dir)
    try:
        items = {it.id: it for it in load_suite(report["suite"], report["split"])}
    except Exception:  # noqa: BLE001 - a missing suite only disables the structured metrics
        items = {}
    missing = 0
    for run in report["runs"]:
        for row in run["rows"]:
            v = verdicts.get(f"{run['config']}::{row['id']}")
            if v is None:
                if "answer" in row:
                    missing += 1
                continue
            row["judge"] = v
            row["judge_correct"] = 1.0 if v["correctness"] == "correct" else 0.0
            row["judge_correct_or_partial"] = 1.0 if v["correctness"] in ("correct", "partial") else 0.0
            row["judge_serious_error"] = 1.0 if v.get("serious_error") in SERIOUS else 0.0
            row.update(structured_row_metrics(items.get(row["id"]), v))
        summ = run["summary"]
        for k in ("judge_correct", "judge_correct_or_partial", "judge_serious_error", *STRUCTURED_METRICS):
            agg = _aggregate(run["rows"], k)
            if agg:
                summ[k] = agg
        summ["judge_serious_error_types"] = dict(Counter(
            r["judge"].get("serious_error") for r in run["rows"] if "judge" in r and r["judge"].get("serious_error") in SERIOUS
        ))
    report["judge"] = {"label": judge_label, "dir": str(judge_dir), "missing": missing}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md = to_markdown(report)
    lines = ["", f"## Juge LLM ({judge_label})", "", "| Config | Correct (juge) | Correct ou partiel | Erreurs graves | Types |", "|---|---:|---:|---:|---|"]
    for run in report["runs"]:
        s = run["summary"]
        f = lambda a: f"{a['mean'] * 100:.1f} [{a['ci_low'] * 100:.0f}–{a['ci_high'] * 100:.0f}]" if a else "—"
        lines.append(f"| `{run['config']}` | {f(s.get('judge_correct'))} | {f(s.get('judge_correct_or_partial'))} | "
                     f"{f(s.get('judge_serious_error'))} | {s.get('judge_serious_error_types', {})} |")
    if any(k in run["summary"] for run in report["runs"] for k in STRUCTURED_METRICS):
        lines += ["", "### Faits obligatoires, affirmations interdites, comportement (juge)", "",
                  "| Config | Faits obligatoires satisfaits | Sans omission | Violation interdite | Comportement attendu |",
                  "|---|---:|---:|---:|---:|"]
        for run in report["runs"]:
            s = run["summary"]
            f = lambda a: f"{a['mean'] * 100:.1f} [{a['ci_low'] * 100:.0f}–{a['ci_high'] * 100:.0f}] (n={a['n']})" if a else "—"
            lines.append(f"| `{run['config']}` | " + " | ".join(f(s.get(k)) for k in STRUCTURED_METRICS) + " |")
    report_path.with_suffix(".md").write_text(md + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"merged {len(verdicts)} verdicts into {report_path} ({missing} answers without verdict)")


def calibrate(judge_dir: Path) -> dict[str, Any]:
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


def _cli() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--report", type=Path, required=True)
    e.add_argument("--out-dir", type=Path, required=True)
    e.add_argument("--parts", type=int, default=4)
    m = sub.add_parser("merge")
    m.add_argument("--report", type=Path, required=True)
    m.add_argument("--judge-dir", type=Path, required=True)
    m.add_argument("--judge-label", default="claude-haiku (subagent)")
    c = sub.add_parser("calibrate")
    c.add_argument("--dir", type=Path, default=Path("eval_internal/judge"))
    a = ap.parse_args()
    if a.cmd == "export":
        export(a.report, a.out_dir, a.parts)
    elif a.cmd == "merge":
        merge(a.report, a.judge_dir, a.judge_label)
    else:
        r = calibrate(a.dir)
        print(json.dumps({k: v for k, v in r.items() if k != "disagreements"}, ensure_ascii=False, indent=1))
        print(f"{len(r['disagreements'])} disagreements -> {a.dir / 'calibration_result.json'}")


if __name__ == "__main__":
    _cli()
