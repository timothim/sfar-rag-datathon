"""Retrieval-only robustness runs (dev only) on the clean and perturbed question sets.

    scripts/with_gpu_lock.sh Q1 env HF_HUB_OFFLINE=1 .venv/bin/python eval_internal/robustness/run_retrieval.py --config frozen

One invocation = one configuration over every (suite, perturbation) set; rows are appended to
eval_internal/robustness/results/<config>.jsonl (rewritten at each run). Same metric code and
same call as `rag-sfar-eval --retrieval-only` (`harness.retrieval_metrics(item, retrieved, k)` on
`retriever.retrieve(item.formatted_query(), config=cfg)`), plus the size of the returned context
and the latency of the `retrieve` call alone.

Configurations: the frozen `C10_context_notes` and variants built with `harness.ablation_variants`
(no code change); `glossary` = frozen configuration, the query being expanded beforehand by
`rag_sfar.retrieval.corpus_glossary.GlossaryExpander` (corpus glossary, entries defined in >= 2
documents; `glossary_a2l`: abbreviation -> long form only); `lexicon_plain` = frozen configuration,
query expanded beforehand with the 60 plain acronym entries of the hand-written lexicon (abbreviation
-> long form, the 13 entries that add molecules or topic words removed). The retrieval pipeline
itself is not modified.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from rag_sfar.config import Settings
from rag_sfar.evaluation import harness
from rag_sfar.evaluation.datasets import read_jsonl
from rag_sfar.retrieval.corpus_glossary import GlossaryExpander, load_glossary, usable_entries

HERE = Path(__file__).resolve().parent
SUITES = ("abpe171", "multirfe_synth")
PERTURBATIONS = ("clean", "typo1", "typo3", "noaccent", "abbr", "expand", "telegraphic", "abbr_user")
VARIANTS = {
    "frozen": "",
    "subword": "use_subword=true",
    "lexicon": "use_medical_lexicon=true",
    "subword_lexicon": "use_subword=true+use_medical_lexicon=true",
    "bm25_only": "use_dense=false+use_reranker=false",
    "dense_only": "use_bm25=false",
    "glossary": "",
    "glossary_a2l": "",
    "lexicon_plain": "",
}

# Hand-written lexicon entries that add terms beyond the acronym's long form (molecules, topic
# words): classified by reading `medical_lexicon.MEDICAL_ACRONYMS` (Q1 report, section 4).
LEXICON_BOOST_ENTRIES = {"ATB", "IIA", "C1G", "C2G", "C3G", "BLSE", "AOD", "AVK", "AAP", "HBPM", "DFG", "ClCr", "IMC"}
K = 64


def build_config(name: str):
    base = harness.select_configs("C10_context_notes")[0]
    assert base.name == "C10_context_notes"
    spec = VARIANTS[name]
    return harness.ablation_variants(base, spec)[0] if spec else base


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, choices=list(VARIANTS))
    ap.add_argument("--index-root", default="index")
    ap.add_argument("--index", default="tas_v6")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    s = Settings()
    cfg = build_config(args.config)
    retrievers = harness.load_retrievers(
        Path(args.index_root), [cfg.chunking_strategy], s.reranker_provider, s.reranker_model,
        index_map={cfg.chunking_strategy: args.index},
    )
    retriever = retrievers[cfg.chunking_strategy]
    expander = None
    if args.config in ("glossary", "glossary_a2l"):
        expander = GlossaryExpander(usable_entries(load_glossary(HERE / "glossary_tas_v6.json"), min_docs=2),
                                    long_to_abbr=args.config == "glossary")
    elif args.config == "lexicon_plain":  # plain acronym expansions of the hand-written lexicon only
        from rag_sfar.retrieval.medical_lexicon import MEDICAL_ACRONYMS

        plain = [{"abbr": a, "long_form": lf, "variants": [lf]} for a, lf in MEDICAL_ACRONYMS.items() if a not in LEXICON_BOOST_ENTRIES]
        expander = GlossaryExpander(plain, long_to_abbr=False)
    retriever.retrieve("antibioprophylaxie chirurgie", config=cfg)  # warm-up (model load, caches)
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    out = (out_dir / f"{args.config}.jsonl").open("w", encoding="utf-8")
    t_all = time.perf_counter()
    for suite in SUITES:
        for pert in PERTURBATIONS:
            items = read_jsonl(HERE / "sets" / suite / f"{pert}.jsonl")
            if args.limit:
                items = items[: args.limit]
            for it in items:
                query = it.formatted_query()
                added = {}
                if expander is not None:
                    query, added = expander.expand(query)
                t0 = time.perf_counter()
                retrieved, _analysis, _timings = retriever.retrieve(query, config=cfg)
                lat = (time.perf_counter() - t0) * 1000
                m = harness.retrieval_metrics(it, retrieved, K)
                row = {
                    "config": args.config, "config_name": cfg.name, "suite": suite, "perturbation": pert,
                    "id": it.id, "changed": it.meta.get("perturbation", {}).get("changed", False),
                    "latency_ms": lat, "n_chunks": len(retrieved),
                    "ctx_chars": sum(len(rc.chunk.text) for rc in retrieved),
                    "expansion": added,
                }
                for key in ("sufficiency", "evidence_recall", "passage_hit", "doc_hit"):
                    if key in m:
                        row[key] = m[key]
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            print(f"{args.config} {suite} {pert} done ({time.perf_counter() - t_all:.0f}s)", flush=True)
    out.close()


if __name__ == "__main__":
    main()
