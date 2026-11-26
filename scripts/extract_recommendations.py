"""Extract graded recommendation units from the French SFAR corpus.

Usage:
    HF_HUB_OFFLINE=1 .venv/bin/python scripts/extract_recommendations.py \
        [--metadata index/table_aware_sota/metadata.sqlite] [--out data_derived/recommendations.jsonl]

Writes one JSON line per unit and prints statistics (units, documents covered, strength
distribution, by period) plus the comparison with the number of recommendations each
document announces ("... a abouti à N recommandations").
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_sfar.ingestion.reco_extractor import (  # noqa: E402
    DEFAULT_METADATA,
    declared_recommendation_count,
    extract_corpus,
    load_documents,
)


def period(y: int | None) -> str:
    if y is None:
        return "inconnue"
    if y < 2005:
        return "2000-2004"
    if y < 2010:
        return "2005-2009"
    if y < 2015:
        return "2010-2014"
    if y < 2020:
        return "2015-2019"
    if y < 2023:
        return "2020-2022"
    return "2023-2026"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata", default=str(ROOT / DEFAULT_METADATA))
    ap.add_argument("--out", default=str(ROOT / "data_derived" / "recommendations.jsonl"))
    args = ap.parse_args()

    docs = load_documents(args.metadata)
    units = extract_corpus(documents=docs, root=ROOT)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for u in units:
            fh.write(u.model_dump_json() + "\n")

    fr_docs = [d for d in docs if d.get("language") in ("fr", "bilingual") and d.get("doc_role") != "traduction_en"]
    per_doc = collections.Counter(u.doc_id for u in units)
    primary = [u for u in units if u.duplicate_of is None]
    stats: dict = {
        "n_units": len(units),
        "n_units_primary": len(primary),
        "n_cross_doc_duplicates": len(units) - len(primary),
        "n_docs_scanned": len(fr_docs),
        "n_docs_with_units": len(per_doc),
        "n_docs_with_5plus_units": sum(1 for n in per_doc.values() if n >= 5),
        "strength": dict(collections.Counter(u.strength for u in units).most_common()),
        "strength_primary": dict(collections.Counter(u.strength for u in primary).most_common()),
        "strength_source": dict(collections.Counter(u.strength_source for u in units).most_common()),
        "mode": dict(collections.Counter(u.extraction_mode for u in units).most_common()),
        "with_label": sum(1 for u in units if u.reco_label),
        "with_agreement": sum(1 for u in units if u.agreement),
        "with_field": sum(1 for u in units if u.field),
        "with_section": sum(1 for u in units if u.section),
        "latest_edition": sum(1 for u in units if u.is_latest_edition),
    }
    by_period: dict[str, dict] = {}
    for p in sorted({period(d.get("effective_year")) for d in fr_docs}):
        pd = [d for d in fr_docs if period(d.get("effective_year")) == p]
        pu = [u for u in units if period(u.year) == p]
        by_period[p] = {
            "docs": len(pd),
            "docs_with_units": sum(1 for d in pd if per_doc.get(d["doc_id"])),
            "units": len(pu),
            "units_primary": sum(1 for u in pu if u.duplicate_of is None),
            "graded": sum(1 for u in pu if u.strength.startswith("grade")),
            "expert_opinion": sum(1 for u in pu if u.strength == "expert_opinion"),
            "unknown": sum(1 for u in pu if u.strength == "unknown"),
        }
    stats["by_period"] = by_period

    # announced vs extracted
    declared = []
    for d in fr_docs:
        p = ROOT / d["md_path"]
        if not p.exists():
            continue
        n = declared_recommendation_count(p.read_text(encoding="utf-8", errors="ignore"))
        if n:
            got = per_doc.get(d["doc_id"], 0)
            declared.append(
                {"doc_id": d["doc_id"], "doc_role": d.get("doc_role"), "declared": n, "extracted": got,
                 "rel_gap": round(abs(got - n) / n, 3)}
            )
    if declared:
        gaps = [x["rel_gap"] for x in declared]
        stats["declared"] = {
            "n_docs": len(declared),
            "median_rel_gap": round(statistics.median(gaps), 3),
            "within_10pct": sum(1 for g in gaps if g <= 0.10),
            "within_20pct": sum(1 for g in gaps if g <= 0.20),
            "exact": sum(1 for x in declared if x["declared"] == x["extracted"]),
            "detail": sorted(declared, key=lambda x: -x["rel_gap"]),
        }
    (out.parent / "recommendations_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    show = {k: v for k, v in stats.items() if k not in ("declared", "by_period")}
    print(json.dumps(show, ensure_ascii=False, indent=1))
    print("\nPar période :")
    for p, v in by_period.items():
        print(f"  {p:10} {v}")
    if declared:
        dd = stats["declared"]
        print(
            f"\nNombre annoncé : {dd['n_docs']} documents, écart relatif médian {dd['median_rel_gap']:.1%}, "
            f"<10 % : {dd['within_10pct']}/{dd['n_docs']}, <20 % : {dd['within_20pct']}/{dd['n_docs']}, exact : {dd['exact']}"
        )
        for x in dd["detail"]:
            print(f"  annoncé={x['declared']:>4} extrait={x['extracted']:>4} écart={x['rel_gap']:.0%}  {x['doc_id']}")
    print(f"\nÉcrit : {out} ({out.stat().st_size / 1e6:.1f} Mo)")


if __name__ == "__main__":
    main()
