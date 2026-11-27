"""Latency alone: same 40 dev questions, warm-up, median/p90 per config and reranker."""
import sys, time, statistics, dataclasses
from pathlib import Path
from rag_sfar.evaluation.harness import load_retrievers, select_configs
from rag_sfar.evaluation.datasets import load_suite
idx, rer = sys.argv[1], sys.argv[2]
r = load_retrievers(Path("index"), ["table_aware_sota"], "cross_encoder", rer, index_map={"table_aware_sota": idx})["table_aware_sota"]
qs = [i.formatted_query() for i in load_suite("abpe171", "dev")[:20] + load_suite("multirfe_synth", "dev")[:20]]
c9 = select_configs("C9")[0]
cfgs = {"C9": c9, "C9W": dataclasses.replace(c9, final_top_k=16, context_window=1, expand_table_parent=True), "C10": select_configs("C10")[0]}
for q in qs[:3]:
    r.retrieve(q, config=cfgs["C10"])
for name, cfg in cfgs.items():
    ts = []
    for q in qs:
        t = time.perf_counter(); r.retrieve(q, config=cfg); ts.append((time.perf_counter() - t) * 1000)
    ts.sort()
    print(f"{idx} {rer.split('/')[-1]} {name}: median {statistics.median(ts):.0f} ms, p90 {ts[int(0.9*len(ts))]:.0f} ms")
