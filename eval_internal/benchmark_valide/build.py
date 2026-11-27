"""V1: experts' validated release (AlpaRagSfar commit 7d1e7fc) -> local suites abpv171 / abpvern.

    .venv/bin/python eval_internal/benchmark_valide/build.py

1. Field-level diff draft (questions_enriched_draft.jsonl, source of abpe171) vs validated
   standard (revision_v31/data/standard.jsonl == the 171 standard rows of questions_validated.jsonl
   up to approval metadata). Ids and counts only -> eval_internal/benchmark_valide/diff_ids.json.
2. Conversion with `convert_enriched_benchmark` (same code as abpe171):
   - abpv171: questions_validated.jsonl, reformulations ("-V") skipped;
   - abpvern: revision_v31/data/vernaculaire.jsonl (171), meta/tags `wording_changed` (88, from
     the manifest), `paired_149` (vernacular_main_ids), `in_release_200` (the 29 "-V").
   Split by id from abpe171: dev = ids of eval/splits/abpe171/dev.jsonl, test = complement (the
   abpe171 test file is not opened). The test part is written as `test_posthoc.jsonl`, not
   `test.jsonl`: it is the abpe171 test, already used once, and LOCKBOX.md is not modified.
3. Mapping coverage on index/tas_v6 (same function as `datasets coverage`), dev and test.
No benchmark text is printed or written outside git-ignored files.
"""

from __future__ import annotations

import json
from pathlib import Path

from rag_sfar.evaluation.datasets import (
    DATASETS_DIR, SPLITS_DIR, convert_enriched_benchmark, mapping_coverage, read_jsonl, write_jsonl,
)

ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / "data/benchmark_alparagsfar_20261127/benchmark_enrichi_phase1"
DRAFT = ROOT / "data/benchmark_enrichi_alparagsfar/benchmark_enrichi_phase1/questions_enriched_draft.jsonl"
HERE = Path(__file__).resolve().parent
INDEX = ROOT / "index/tas_v6"

FIELDS = {
    "question": lambda r: (r.get("proposed") or {}).get("question"),
    "choices": lambda r: (r.get("proposed") or {}).get("choices"),
    "expected_behavior": lambda r: (r.get("proposed") or {}).get("expected_behavior"),
    "acceptable_behaviors": lambda r: (r.get("proposed") or {}).get("acceptable_behaviors"),
    "answerability": lambda r: (r.get("proposed") or {}).get("answerability"),
    "mcq_key_or_policy": lambda r: [(r.get("proposed") or {}).get(k) for k in ("mcq_correct_option", "mcq_option_status", "mcq_policy")],
    "mandatory_claims": lambda r: (r.get("reference_answer") or {}).get("mandatory_claims"),
    "optional_claims": lambda r: (r.get("reference_answer") or {}).get("optional_claims"),
    "forbidden_claims": lambda r: (r.get("reference_answer") or {}).get("forbidden_claims"),
    "required_missing_information": lambda r: (r.get("reference_answer") or {}).get("required_missing_information"),
    "individualization_information": lambda r: (r.get("reference_answer") or {}).get("individualization_information"),
    "acceptable_alternatives": lambda r: (r.get("reference_answer") or {}).get("acceptable_alternatives"),
    "evidence_fragments": lambda r: [(e.get("evidence_id"), [f.get("text") for f in e.get("exact_fragments") or []]) for e in r.get("evidence_current") or []],
    "evidence_sets": lambda r: r.get("evidence_sets"),
    "reference_short_answer": lambda r: (r.get("reference_answer") or {}).get("short_answer"),
    "reference_narrative": lambda r: (r.get("reference_answer") or {}).get("narrative_fr"),
    "classification": lambda r: r.get("classification"),
}


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> None:
    draft = {r["legacy_id"]: r for r in load(DRAFT)}
    std = {r["legacy_id"]: r for r in load(NEW / "revision_v31/data/standard.jsonl")}
    validated = load(NEW / "questions_validated.jsonl")
    man = json.loads((NEW / "revision_v31/data/manifest.json").read_text(encoding="utf-8"))
    rel = json.loads((NEW / "manifests/benchmark_validated.json").read_text(encoding="utf-8"))
    dev_ids = {json.loads(l)["id"] for l in (SPLITS_DIR / "abpe171/dev.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    all_ids = set(draft)
    assert set(std) == all_ids and len(dev_ids) == 102 and dev_ids <= all_ids
    test_ids = all_ids - dev_ids
    qid2leg = {r["question_id"]: r["legacy_id"] for r in std.values()}

    # 1. diff
    changed = {f: sorted((i for i in all_ids if fn(draft[i]) != fn(std[i])), key=lambda x: int(x[1:])) for f, fn in FIELDS.items()}
    any_changed = sorted({i for v in changed.values() for i in v}, key=lambda x: int(x[1:]))
    clinical = sorted((qid2leg[q] for q in man["clinical"]), key=lambda x: int(x[1:]))
    wording = sorted((qid2leg[q] for q in man["wording"]), key=lambda x: int(x[1:]))
    paired = sorted((qid2leg[q] for q in man["vernacular_main_ids"]), key=lambda x: int(x[1:]))
    released_v = sorted((qid2leg[p] for p in rel["parent_question_ids"].values()), key=lambda x: int(x[1:]))
    split = lambda ids: {"all": len(ids), "dev": len(set(ids) & dev_ids), "test": len(set(ids) & test_ids)}
    diff = {
        "draft": str(DRAFT.relative_to(ROOT)), "validated": "benchmark_enrichi_phase1/revision_v31/data/standard.jsonl (= questions_validated.jsonl 171 standard rows)",
        "counts": {f: split(v) for f, v in changed.items()} | {"any_field": split(any_changed), "manifest_clinical": split(clinical)},
        "ids": {f: v for f, v in changed.items() if v} | {"manifest_clinical": clinical},
        "vernacular": {"wording_changed": split(wording), "paired_149": split(paired), "in_release_200": split(released_v),
                       "wording_changed_and_paired": split(set(wording) & set(paired)),
                       "in_release_200_ids": released_v, "wording_changed_ids": wording,
                       "not_in_paired_149_ids": sorted(all_ids - set(paired), key=lambda x: int(x[1:]))},
        "dev_ids_n": len(dev_ids), "test_ids_n": len(test_ids),
    }
    (HERE / "diff_ids.json").write_text(json.dumps(diff, indent=1), encoding="utf-8")

    # 2. conversion
    std_items = convert_enriched_benchmark(NEW / "questions_validated.jsonl", suite="abpv171",
                                           source="benchmark_enrichi_phase1/questions_validated.jsonl (sfar-abp-v31.2-200, standard rows)",
                                           skip_reformulations=True)
    vern_items = convert_enriched_benchmark(NEW / "revision_v31/data/vernaculaire.jsonl", suite="abpvern",
                                            source="benchmark_enrichi_phase1/revision_v31/data/vernaculaire.jsonl (sfar-abp-v31.1-valide)")
    assert [i.id for i in std_items] == [i.id for i in vern_items] and len(std_items) == 171
    for it in vern_items:
        flags = {"wording_changed": it.id in wording, "paired_149": it.id in paired, "in_release_200": it.id in released_v}
        it.meta.update(flags)
        it.tags += [f"vern:{k}" for k, v in flags.items() if v]
    for it in std_items:
        it.meta["clinical_revision_v31"] = it.id in clinical
        if it.id in clinical:
            it.tags.append("v31:grid_revised")
    stats = {}
    for name, items in (("abpv171", std_items), ("abpvern", vern_items)):
        write_jsonl(items, DATASETS_DIR / f"{name}.jsonl")
        d = SPLITS_DIR / name
        dev = [i for i in items if i.id in dev_ids]
        test = [i for i in items if i.id in test_ids]
        write_jsonl(dev, d / "dev.jsonl")
        write_jsonl(test, d / "test_posthoc.jsonl")
        (d / "split_info.json").write_text(json.dumps({"split_like": "abpe171 (dev ids; test = complement)", "n_dev": len(dev),
                                                       "n_test_posthoc": len(test)}, indent=1), encoding="utf-8")
        # 3. coverage
        for part, its in (("dev", dev), ("test_posthoc", test)):
            cov = mapping_coverage(its, INDEX)
            stats[f"{name}/{part}"] = {k: v for k, v in cov.items() if k not in ("unmatched", "per_item")}
    # retrieval-relevant equality with abpe171 (question text + evidence), via converted items
    old = {i.id: i for i in read_jsonl(DATASETS_DIR / "abpe171.jsonl")}
    same_ev = sum(1 for i in std_items if old[i.id].evidence == i.evidence and old[i.id].evidence_sets == i.evidence_sets and old[i.id].gold_passages == i.gold_passages)
    same_q = sum(1 for i in std_items if old[i.id].formatted_query() == i.formatted_query())
    stats["abpv171_vs_abpe171"] = {"same_evidence_and_sets": same_ev, "same_query": same_q}
    stats["abpvern_vs_abpv171"] = {"same_query": sum(1 for a, b in zip(std_items, vern_items) if a.formatted_query() == b.formatted_query()),
                                   "same_evidence": sum(1 for a, b in zip(std_items, vern_items) if a.evidence == b.evidence and a.evidence_sets == b.evidence_sets)}
    (HERE / "build_stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(json.dumps(diff["counts"], indent=0))
    print(json.dumps(diff["vernacular"] | {"in_release_200_ids": "...", "wording_changed_ids": "...", "not_in_paired_149_ids": "..."}))
    print(json.dumps(stats, indent=0))


if __name__ == "__main__":
    main()
