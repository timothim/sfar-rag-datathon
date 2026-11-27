"""B1 driver: load retriever once, run C9-based variants on the three dev suites, cache rows."""
import argparse, dataclasses, json, sys, time, statistics
from pathlib import Path
from rag_sfar.evaluation.harness import load_retrievers, retrieval_metrics, select_configs, paired_bootstrap_diff, bootstrap_ci
from rag_sfar.evaluation.datasets import load_suite
from rag_sfar.config import Settings

RES = Path(__file__).parent / "res"
SUITES = ["abpe171", "abp171", "multirfe_synth"]

def parse_variant(spec, base):
    name, _, body = spec.partition(":")
    changes = {}
    for part in [p for p in body.split("+") if p]:
        f, _, raw = part.partition("=")
        cur = getattr(base, f)
        if isinstance(cur, bool):
            changes[f] = raw.lower() in ("1", "true", "yes")
        else:
            changes[f] = type(cur)(raw)
    return name, dataclasses.replace(base, name=name, **changes)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variants", nargs="+")
    ap.add_argument("--base", default="C9")
    ap.add_argument("--suites", default=",".join(SUITES))
    ap.add_argument("--reranker", default=Settings().reranker_model)
    ap.add_argument("--index", default="tas_v3_errata")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    base = select_configs(a.base)[0]
    t = time.time()
    retr = load_retrievers(Path("index"), ["table_aware_sota"], "cross_encoder", a.reranker, index_map={"table_aware_sota": a.index})["table_aware_sota"]
    print(f"loaded {time.time()-t:.1f}s", flush=True)
    for spec in a.variants:
        name, cfg = parse_variant(spec, base)
        for suite in a.suites.split(","):
            out = RES / f"{name}__{suite}.json"
            if out.exists() and not a.force:
                continue
            items = load_suite(suite, "dev")
            rows = []
            for it in items:
                t0 = time.perf_counter()
                ret, an, tm = retr.retrieve(it.formatted_query(), config=cfg)
                lat = (time.perf_counter() - t0) * 1000
                m = retrieval_metrics(it, ret, 64)
                m.update(id=it.id, qtype=it.question_type, tags=it.tags, latency_ms=lat,
                         n_chunks=len(ret), n_chars=sum(len(r.chunk.text) for r in ret),
                         chunks=[r.chunk.chunk_id for r in ret],
                         ce=[r.rerank_score for r in ret], pop=an.population,
                         cov={k: tm[k] for k in ("coverage_score", "channel_agreement", "dense_top_score") if k in tm},
                         reasons=[r.expansion_reason for r in ret])
                rows.append(m)
            out.write_text(json.dumps({"config": dataclasses.asdict(cfg), "rows": rows}, ensure_ascii=False, default=str))
            print(name, suite, summarize(rows), flush=True)

def summarize(rows):
    def mean(k):
        v = [r[k] for r in rows if k in r and r[k] is not None]
        return round(100 * sum(v) / len(v), 1) if v else None
    s = {k: mean(k) for k in ("sufficiency", "evidence_recall", "passage_hit") if mean(k) is not None}
    s["chars"] = round(statistics.mean(r["n_chars"] for r in rows))
    s["chunks"] = round(statistics.mean(r["n_chunks"] for r in rows), 1)
    s["lat"] = round(statistics.median(r["latency_ms"] for r in rows))
    return s

if __name__ == "__main__":
    main()
