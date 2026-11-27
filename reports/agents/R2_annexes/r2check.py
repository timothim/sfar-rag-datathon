"""R2 counter-check: rerun C9 and the frozen C10_context_notes on HEAD (dev suites) on a given index.
Usage: HF_HUB_OFFLINE=1 .venv/bin/python reports/agents/R2_annexes/r2check.py <index>"""
import dataclasses, json, sys, time
from pathlib import Path
from rag_sfar.evaluation.harness import load_retrievers, retrieval_metrics, select_configs
from rag_sfar.evaluation.datasets import load_suite
from rag_sfar.config import Settings
RES = Path(__file__).parent / "res2"
index = sys.argv[1]
retr = load_retrievers(Path("index"), ["table_aware_sota"], "cross_encoder", Settings().reranker_model,
                       index_map={"table_aware_sota": index})["table_aware_sota"]
for cfg in select_configs("C9,C10"):
    for suite in ("abpe171", "abp171", "multirfe_synth"):
        out = RES / f"{index}_{cfg.name}__{suite}.json"
        if out.exists():
            continue
        rows = []
        for it in load_suite(suite, "dev"):
            t0 = time.perf_counter()
            ret, an, tm = retr.retrieve(it.formatted_query(), config=cfg)
            m = retrieval_metrics(it, ret, 64)
            m.update(id=it.id, latency_ms=(time.perf_counter() - t0) * 1000, n_chunks=len(ret),
                     n_chars=sum(len(r.chunk.text) for r in ret), chunks=[r.chunk.chunk_id for r in ret],
                     reasons=[r.expansion_reason for r in ret])
            rows.append(m)
        out.write_text(json.dumps({"config": dataclasses.asdict(cfg), "rows": rows}, ensure_ascii=False, default=str))
        print(index, cfg.name, suite, len(rows), flush=True)
