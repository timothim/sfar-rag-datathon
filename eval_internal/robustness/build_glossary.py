"""Extract the abbreviation glossary from the current editions of an index (no model loaded).

    .venv/bin/python eval_internal/robustness/build_glossary.py [--index index/tas_v6]

Writes eval_internal/robustness/glossary_tas_v6.json and a 50-entry audit sample
(glossary_sample50.csv, glossary_sample50_usable.csv) to be labelled by hand (column `correct`);
existing samples are kept unless --resample.
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path

from rag_sfar.retrieval.corpus_glossary import build_glossary, save_glossary, usable_pairs
from rag_sfar.retrieval.vector_store import LocalVectorStore

HERE = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="index/tas_v6")
    ap.add_argument("--out", default=str(HERE / "glossary_tas_v6.json"))
    ap.add_argument("--seed", type=int, default=20261127)
    ap.add_argument("--resample", action="store_true", help="rewrite the audit samples (erases the hand labels)")
    args = ap.parse_args()
    store = LocalVectorStore.load(Path(args.index))
    mask = store.build_filter_mask()  # current editions, active, French preferred, no references
    chunks = [c for c, ok in zip(store.chunks, mask) if ok]
    g = build_glossary(chunks)
    g["source"] = {"index": args.index, "chunks_scanned": len(chunks), "documents": len({c.doc_id for c in chunks})}
    pats = Counter()
    for e in g["entries"].values():
        for lf in e["long_forms"]:
            pats.update(lf["patterns"])
    g["pattern_counts"] = dict(pats)
    g["n_pairs"] = sum(len(e["long_forms"]) for e in g["entries"].values())
    g["n_usable_min_docs_2"] = len(usable_pairs(g, min_docs=2))
    g["n_usable_min_docs_1"] = len(usable_pairs(g, min_docs=1))
    save_glossary(g, Path(args.out))
    print(f"abbreviations={g['n_abbreviations']} pairs={g['n_pairs']} usable(>=2 docs)={g['n_usable_min_docs_2']} "
          f"usable(>=1 doc)={g['n_usable_min_docs_1']} patterns={dict(pats)}")
    if (HERE / "glossary_sample50.csv").exists() and not args.resample:
        return  # keep the hand-labelled audit samples
    # audit sample: primary long form of 50 random abbreviations (all supports)
    rng = random.Random(args.seed)
    abbrs = sorted(g["entries"])
    sample = rng.sample(abbrs, min(50, len(abbrs)))
    with (HERE / "glossary_sample50.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["abbr", "long_form", "docs", "count", "patterns", "correct"])
        for a in sample:
            lf = g["entries"][a]["long_forms"][0]
            w.writerow([a, lf["long_form"], lf["docs"], lf["count"], "+".join(sorted(lf["patterns"])), ""])
    # second sample: among the entries used for perturbation and expansion (>= 2 documents)
    from rag_sfar.retrieval.corpus_glossary import usable_entries

    usable = usable_entries(g, min_docs=2)
    sample2 = random.Random(args.seed + 1).sample(usable, min(50, len(usable)))
    with (HERE / "glossary_sample50_usable.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["abbr", "long_form", "docs", "correct"])
        for e in sample2:
            w.writerow([e["abbr"], e["long_form"], e["docs"], ""])


if __name__ == "__main__":
    main()
