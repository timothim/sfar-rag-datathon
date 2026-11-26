"""Normalized evaluation datasets, dev/test splits and the test lockbox.

Format spec: eval/README.md. CLI:
    python -m rag_sfar.evaluation.datasets import --input F --suite S --provenance P [--map k=v ...]
    python -m rag_sfar.evaluation.datasets convert-abp
    python -m rag_sfar.evaluation.datasets split --suite S [--test-fraction 0.4] [--holdout-doc-fraction 0.2]
    python -m rag_sfar.evaluation.datasets lockbox
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

EVAL_DIR = Path("eval")
DATASETS_DIR = EVAL_DIR / "datasets"
SPLITS_DIR = EVAL_DIR / "splits"
LOCKBOX_PATH = EVAL_DIR / "LOCKBOX.md"
INTERNAL_DIR = Path("eval_internal")

QuestionType = Literal["open", "mcq", "clinical_case", "comparison", "table", "abstention"]
Provenance = Literal["physician_validated", "external_benchmark", "llm_synthetic", "team_written"]


class GoldPassage(BaseModel):
    doc_id: str
    quote: str


class EvalItem(BaseModel):
    id: str
    suite: str
    question: str
    question_type: QuestionType
    provenance: Provenance
    choices: dict[str, str] = Field(default_factory=dict)
    reference_answer: str = ""
    answer_key: dict[str, Any] = Field(default_factory=dict)
    should_abstain: bool = False
    gold_doc_ids: list[str] = Field(default_factory=list)
    gold_passages: list[GoldPassage] = Field(default_factory=list)
    current_edition_required: bool = True
    source_doc_ids: list[str] = Field(default_factory=list)
    group: str = ""
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    def formatted_query(self) -> str:
        if not self.choices:
            return self.question
        return self.question + "\n" + "\n".join(f"{k}. {v}" for k, v in self.choices.items())


# ---------------------------------------------------------------- IO


def read_jsonl(path: Path) -> list[EvalItem]:
    items = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(EvalItem.model_validate_json(line))
    return items


def write_jsonl(items: Iterable[EvalItem], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it.model_dump(), ensure_ascii=False, sort_keys=True) + "\n")


def suite_dataset_path(suite: str) -> Path:
    for base in (DATASETS_DIR, INTERNAL_DIR / "datasets"):
        p = base / f"{suite}.jsonl"
        if p.exists():
            return p
    return DATASETS_DIR / f"{suite}.jsonl"


def split_path(suite: str, split: str) -> Path:
    base = SPLITS_DIR if (DATASETS_DIR / f"{suite}.jsonl").exists() else INTERNAL_DIR / "splits"
    return base / suite / f"{split}.jsonl"


def available_suites() -> list[str]:
    names = set()
    for base in (SPLITS_DIR, INTERNAL_DIR / "splits"):
        if base.exists():
            names |= {p.name for p in base.iterdir() if p.is_dir()}
    return sorted(names)


def load_suite(suite: str, split: Literal["dev", "test", "all"]) -> list[EvalItem]:
    """Load a split. `suite="full"` concatenates every suite that has splits."""
    if split == "test":
        verify_lockbox(raise_on_error=True)
    suites = available_suites() if suite == "full" else [suite]
    out: list[EvalItem] = []
    for s in suites:
        parts = ["dev", "test"] if split == "all" else [split]
        for part in parts:
            p = split_path(s, part)
            if not p.exists():
                raise FileNotFoundError(f"Missing split {p}; run `datasets split --suite {s}` first.")
            out.extend(read_jsonl(p))
    return out


# ---------------------------------------------------------------- text helpers


def fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def _stable_hash(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:12], 16)


# ---------------------------------------------------------------- import / convert


def import_file(input_path: Path, suite: str, provenance: str, mapping: dict[str, str]) -> list[EvalItem]:
    """Import an external benchmark (JSON list, {"questions": [...]}, JSONL or CSV)."""
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        with input_path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    elif suffix == ".jsonl":
        rows = [json.loads(l) for l in input_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        rows = data.get("questions", data) if isinstance(data, dict) else data
    items = []
    for i, row in enumerate(rows):
        rec: dict[str, Any] = {}
        for field in EvalItem.model_fields:
            src = mapping.get(field, field)
            if src in row and row[src] not in (None, ""):
                rec[field] = row[src]
        for list_field in ("gold_doc_ids", "source_doc_ids", "tags"):
            if isinstance(rec.get(list_field), str):
                rec[list_field] = [x.strip() for x in re.split(r"[;|]", rec[list_field]) if x.strip()]
        for json_field in ("choices", "answer_key", "gold_passages", "meta"):
            if isinstance(rec.get(json_field), str):
                rec[json_field] = json.loads(rec[json_field])
        rec.setdefault("id", f"{suite}-{i + 1:04d}")
        rec["id"] = str(rec["id"])
        rec["suite"] = suite
        rec["provenance"] = provenance
        rec.setdefault("question_type", "mcq" if rec.get("choices") else "open")
        if rec["question_type"] == "mcq" and "answer_key" not in rec and rec.get("reference_answer"):
            letter = str(rec["reference_answer"]).strip().upper()[:1]
            rec["answer_key"] = {"mcq": letter}
        items.append(EvalItem.model_validate(rec))
    return items


ABP_BENCHMARK = Path("data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json")


def convert_abp_benchmark(path: Path = ABP_BENCHMARK, gold_doc_ids: list[str] | None = None) -> list[EvalItem]:
    """Convert the official 171-question antibioprophylaxis benchmark to the common format.

    The deterministic key reproduces the benchmark's own scorers (all molecules present for open
    questions, letter for MCQ). Gold documents are given by the caller (the current edition)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for q in data["questions"]:
        ans = q.get("réponse", "").strip()
        qtype = "mcq" if q.get("type") == "mcq" else "open"
        tags = []
        if "allerg" in fold(q["question"] + " " + q.get("titre", "")):
            tags.append("allergy")
        if re.search(r"\b(enfant|pediatr|nourrisson|neonat)", fold(q["question"])):
            tags.append("pediatric")
        if qtype == "mcq":
            key = {"mcq": ans.upper()}
        elif fold(ans) in ("pas d'antibioprophylaxie", "hors perimetre"):
            key = {"label": fold(ans)}
            tags.append("no_abp" if "pas" in fold(ans) else "out_of_scope")
        else:
            key = {"all_of": [p.strip() for p in re.split(r"[+/]", ans) if p.strip()]}
        items.append(
            EvalItem(
                id=q["id"],
                suite="abp171",
                question=q["question"],
                question_type=qtype,
                provenance="external_benchmark",
                choices=q.get("choices") or {},
                reference_answer=ans,
                answer_key=key,
                should_abstain=fold(ans) == "hors perimetre",
                gold_doc_ids=list(gold_doc_ids or []),
                tags=tags,
                meta={"titre": q.get("titre", ""), "source": data.get("source", ""), "benchmark_version": data.get("version", "")},
            )
        )
    return items


# ---------------------------------------------------------------- split


def _near_duplicate_groups(items: list[EvalItem], threshold: float = 0.6) -> dict[str, str]:
    """Union-find over question token Jaccard similarity; explicit `group` fields are kept."""
    parent = {it.id: (it.group or it.id) for it in items}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    for it in items:
        parent.setdefault(it.group or it.id, it.group or it.id)
    # Ignore template words shared by many questions ("quelle est la recommandation ...").
    raw = {it.id: set(tokens(it.formatted_query())) for it in items}
    df: dict[str, int] = defaultdict(int)
    for ts in raw.values():
        for t in ts:
            df[t] += 1
    max_df = max(2, int(0.15 * len(items)))
    toks = {k: {t for t in ts if df[t] <= max_df} for k, ts in raw.items()}
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            ta, tb = toks[a.id], toks[b.id]
            if ta and tb and len(ta & tb) / len(ta | tb) >= threshold:
                ra, rb = find(a.id), find(b.id)
                if ra != rb:
                    parent[rb] = ra
    return {it.id: find(it.id) for it in items}


def make_split(
    items: list[EvalItem],
    test_fraction: float = 0.4,
    holdout_doc_fraction: float = 0.0,
    seed: str = "sfar-2026",
    strata_fn=None,
) -> tuple[list[EvalItem], list[EvalItem], dict[str, Any]]:
    """Deterministic stratified split.

    1. If `holdout_doc_fraction` > 0, a fraction of source documents is held out entirely:
       every question citing one of them goes to test (tag `unseen_doc`).
    2. Remaining questions are grouped (near-duplicates together) and, within each stratum
       (question_type + first source doc + answer class), groups are assigned to test in a
       seeded order until the stratum reaches `test_fraction`.
    """
    strata_fn = strata_fn or (
        lambda it: (
            it.question_type,
            (it.source_doc_ids or ["-"])[0],
            next(iter(it.answer_key), "-"),
            "allergy" in it.tags,
        )
    )
    info: dict[str, Any] = {"seed": seed, "test_fraction": test_fraction}

    held_docs: set[str] = set()
    if holdout_doc_fraction > 0:
        docs = sorted({d for it in items for d in it.source_doc_ids})
        docs.sort(key=lambda d: _stable_hash(seed, "doc", d))
        held_docs = set(docs[: max(1, round(len(docs) * holdout_doc_fraction))])
        info["holdout_docs"] = sorted(held_docs)

    test_ids: set[str] = set()
    for it in items:
        if held_docs & set(it.source_doc_ids):
            test_ids.add(it.id)

    rest = [it for it in items if it.id not in test_ids]
    groups = _near_duplicate_groups(rest)
    by_group: dict[str, list[EvalItem]] = defaultdict(list)
    for it in rest:
        by_group[groups[it.id]].append(it)

    strata: dict[tuple, list[str]] = defaultdict(list)
    for g, members in by_group.items():
        strata[strata_fn(members[0])].append(g)
    for key, gs in sorted(strata.items(), key=lambda kv: str(kv[0])):
        gs.sort(key=lambda g: _stable_hash(seed, g))
        total = sum(len(by_group[g]) for g in gs)
        target = test_fraction * total
        taken = 0
        for g in gs:
            if taken + len(by_group[g]) / 2 > target:
                break
            for it in by_group[g]:
                test_ids.add(it.id)
            taken += len(by_group[g])

    dev = [it for it in items if it.id not in test_ids]
    test = []
    for it in items:
        if it.id in test_ids:
            if held_docs & set(it.source_doc_ids) and "unseen_doc" not in it.tags:
                it = it.model_copy(update={"tags": it.tags + ["unseen_doc"]})
            test.append(it)
    info.update(
        n_dev=len(dev),
        n_test=len(test),
        n_groups=len(by_group),
        n_multi_member_groups=sum(1 for m in by_group.values() if len(m) > 1),
    )
    return dev, test, info


# ---------------------------------------------------------------- lockbox


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _all_test_files() -> list[Path]:
    files = []
    for base in (SPLITS_DIR, INTERNAL_DIR / "splits"):
        if base.exists():
            files += sorted(base.glob("*/test.jsonl"))
    return files


def write_lockbox(note: str = "") -> str:
    lines = [
        "# LOCKBOX — empreintes des jeux de test",
        "",
        "Ces fichiers ne doivent pas être modifiés après leur mise sous coffre-fort, ni évalués pendant la mise au point.",
        "Vérification automatique : `pytest tests/test_lockbox.py`. Toute modification exige l'accord de l'utilisateur",
        "et une nouvelle entrée datée ci-dessous expliquant pourquoi.",
        "",
        "| Fichier | Questions | SHA-256 |",
        "|---|---:|---|",
    ]
    for p in _all_test_files():
        n = sum(1 for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
        lines.append(f"| `{p.as_posix()}` | {n} | `{sha256_file(p)}` |")
    if note:
        lines += ["", "## Historique", "", note]
    text = "\n".join(lines) + "\n"
    LOCKBOX_PATH.write_text(text, encoding="utf-8")
    return text


def read_lockbox() -> dict[str, str]:
    if not LOCKBOX_PATH.exists():
        return {}
    out = {}
    for m in re.finditer(r"\| `([^`]+)` \| \d+ \| `([0-9a-f]{64})` \|", LOCKBOX_PATH.read_text(encoding="utf-8")):
        out[m.group(1)] = m.group(2)
    return out


def verify_lockbox(raise_on_error: bool = False) -> list[str]:
    """Return a list of problems (missing, modified or unregistered test files)."""
    registered = read_lockbox()
    problems = []
    for rel, digest in registered.items():
        p = Path(rel)
        if not p.exists():
            problems.append(f"missing: {rel}")
        elif sha256_file(p) != digest:
            problems.append(f"modified: {rel}")
    for p in _all_test_files():
        if p.as_posix() not in registered:
            problems.append(f"unregistered: {p.as_posix()}")
    if problems and raise_on_error:
        raise RuntimeError("Lockbox check failed: " + "; ".join(problems))
    return problems


# ---------------------------------------------------------------- CLI


def _cli() -> None:
    ap = argparse.ArgumentParser(description="RAG-SFAR evaluation datasets")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_imp = sub.add_parser("import")
    p_imp.add_argument("--input", type=Path, required=True)
    p_imp.add_argument("--suite", required=True)
    p_imp.add_argument("--provenance", required=True, choices=list(Provenance.__args__))
    p_imp.add_argument("--map", nargs="*", default=[], help="field=source_column pairs")
    p_imp.add_argument("--out-dir", type=Path, default=DATASETS_DIR)

    p_abp = sub.add_parser("convert-abp")
    p_abp.add_argument("--gold-doc-id", action="append", default=[])

    p_split = sub.add_parser("split")
    p_split.add_argument("--suite", required=True)
    p_split.add_argument("--test-fraction", type=float, default=0.4)
    p_split.add_argument("--holdout-doc-fraction", type=float, default=0.0)
    p_split.add_argument("--seed", default="sfar-2026")
    p_split.add_argument("--force", action="store_true", help="Overwrite an existing test split (needs user approval once locked).")

    sub.add_parser("lockbox")
    sub.add_parser("verify")

    args = ap.parse_args()
    if args.cmd == "import":
        mapping = dict(kv.split("=", 1) for kv in args.map)
        items = import_file(args.input, args.suite, args.provenance, mapping)
        out = args.out_dir / f"{args.suite}.jsonl"
        write_jsonl(items, out)
        print(f"{len(items)} questions -> {out}")
    elif args.cmd == "convert-abp":
        items = convert_abp_benchmark(gold_doc_ids=args.gold_doc_id)
        write_jsonl(items, DATASETS_DIR / "abp171.jsonl")
        print(f"{len(items)} questions -> {DATASETS_DIR / 'abp171.jsonl'}")
    elif args.cmd == "split":
        src = suite_dataset_path(args.suite)
        items = read_jsonl(src)
        test_p = split_path(args.suite, "test")
        if test_p.exists() and test_p.as_posix() in read_lockbox() and not args.force:
            raise SystemExit(f"{test_p} is locked; re-splitting needs the user's approval (--force).")
        dev, test, info = make_split(items, args.test_fraction, args.holdout_doc_fraction, args.seed)
        write_jsonl(dev, split_path(args.suite, "dev"))
        write_jsonl(test, test_p)
        (test_p.parent / "split_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(info, ensure_ascii=False))
    elif args.cmd == "lockbox":
        print(write_lockbox())
    elif args.cmd == "verify":
        problems = verify_lockbox()
        print("OK" if not problems else "\n".join(problems))
        raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    _cli()
