"""R2 driver: rerun C9 / C10 and leave-one-rule-out variants of C10 on the dev suites (current HEAD).
Rows keep the full context (chunk ids, expansion reasons) for offline analysis.
Usage: HF_HUB_OFFLINE=1 .venv/bin/python reports/agents/R2_annexes/r2eval.py [--suites ...]"""
import argparse, dataclasses, json, time
from pathlib import Path
from rag_sfar.evaluation.harness import load_retrievers, retrieval_metrics, select_configs
from rag_sfar.evaluation.datasets import load_suite
from rag_sfar.config import Settings

RES = Path(__file__).parent / "res"
VARIANTS = {
    "C9": ("C9", {}),
    "C10": ("C10", {}),
    "C10_noPop": ("C10", {"population_quota": 0}),
    "C10_noCounterpart": ("C10", {"population_counterpart": False}),
    "C10_noNotes": ("C10", {"attach_table_notes": False}),
    "C10_cap7": ("C10", {"max_chunks_per_doc": 7}),
    "C10_noMCQ": ("C10", {"mcq_option_quota": 0}),
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", default="multirfe_synth,abpe171,abp171")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--index", default="tas_v3_errata")
    a = ap.parse_args()
    retr = load_retrievers(Path("index"), ["table_aware_sota"], "cross_encoder", Settings().reranker_model,
                           index_map={"table_aware_sota": a.index})["table_aware_sota"]
    for name in a.variants.split(","):
        base, ch = VARIANTS[name]
        cfg = dataclasses.replace(select_configs(base)[0], name=name, **ch)
        for suite in a.suites.split(","):
            out = RES / f"{name}__{suite}.json"
            if out.exists():
                continue
            rows = []
            for it in load_suite(suite, "dev"):
                t0 = time.perf_counter()
                ret, an, tm = retr.retrieve(it.formatted_query(), config=cfg)
                m = retrieval_metrics(it, ret, 64)
                m.update(id=it.id, qtype=it.question_type, tags=it.tags, latency_ms=(time.perf_counter() - t0) * 1000,
                         n_chunks=len(ret), n_chars=sum(len(r.chunk.text) for r in ret),
                         chunks=[r.chunk.chunk_id for r in ret], ce=[r.rerank_score for r in ret],
                         reasons=[r.expansion_reason for r in ret], pop=an.population,
                         cov={k: tm.get(k) for k in ("coverage_score", "coverage_supported")})
                rows.append(m)
            out.write_text(json.dumps({"config": dataclasses.asdict(cfg), "rows": rows}, ensure_ascii=False, default=str))
            print(name, suite, len(rows), flush=True)

if __name__ == "__main__":
    main()
