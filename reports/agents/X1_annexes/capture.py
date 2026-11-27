"""X1: run the frozen retrieval (C10_context_notes, index/tas_v6) on dev suites and cache the full
output per question (chunk ids, scores, reasons, query population, latency). Optionally run the
same retriever through the structural-links wrapper (--links DIR) to measure it end to end."""
import argparse, gzip, json, sys, time
from pathlib import Path
from rag_sfar.evaluation.harness import load_retrievers, select_configs, retrieval_metrics
from rag_sfar.evaluation.datasets import load_suite
from rag_sfar.config import Settings

RES = Path(__file__).parent / "res"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--suites", default="abpe171,multirfe_synth")
    ap.add_argument("--links", default="")
    ap.add_argument("--policy", default="{}")
    a = ap.parse_args()
    cfg = select_configs("C10_context_notes")[0]
    retr = load_retrievers(Path("index"), ["table_aware_sota"], "cross_encoder", Settings().reranker_model,
                           index_map={"table_aware_sota": "tas_v6"})["table_aware_sota"]
    if a.links:
        from rag_sfar.retrieval.links import LinkedRetriever, LinkPolicy
        retr = LinkedRetriever(retr, Path(a.links), LinkPolicy(**json.loads(a.policy)))
    for suite in a.suites.split(","):
        rows = []
        for it in load_suite(suite, "dev"):
            q = it.formatted_query()
            t0 = time.perf_counter()
            ret, an, tm = retr.retrieve(q, config=cfg)
            lat = (time.perf_counter() - t0) * 1000
            m = retrieval_metrics(it, ret, 64)
            m.update(id=it.id, tags=it.tags, qtype=it.question_type, latency_ms=lat, population=an.population,
                     chunks=[r.chunk.chunk_id for r in ret], reasons=[r.expansion_reason for r in ret],
                     scores=[r.final_score for r in ret], ce=[r.rerank_score for r in ret],
                     expanded=[r.is_expanded_context for r in ret],
                     n_chars=sum(len(r.chunk.text) for r in ret), links_ms=tm.get("links_ms"))
            rows.append(m)
        out = RES / f"{a.name}__{suite}.json.gz"
        with gzip.open(out, "wt") as f:
            json.dump({"config": cfg.name, "links": a.links, "policy": a.policy, "rows": rows}, f, ensure_ascii=False, default=str)
        print(a.name, suite, len(rows), flush=True)

if __name__ == "__main__":
    main()
