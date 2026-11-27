"""Coverage signal on held-out negatives (threshold NOT re-tuned): share flagged 'not covered'.
usage: cov_holdout.py <index> <queries.txt> [config]"""
import sys, statistics
from pathlib import Path
from rag_sfar.evaluation.harness import load_retrievers, select_configs
from rag_sfar.config import Settings
idx, qfile = sys.argv[1], sys.argv[2]
cfg = select_configs(sys.argv[3] if len(sys.argv) > 3 else "C10")[0]
r = load_retrievers(Path("index"), ["table_aware_sota"], "cross_encoder", Settings().reranker_model, index_map={"table_aware_sota": idx})["table_aware_sota"]
qs = [l.strip() for l in open(qfile) if l.strip()]
scores = []
for q in qs:
    _, _, tm = r.retrieve(q, config=cfg)
    scores.append(tm["coverage_score"])
    print(f"{tm['coverage_score']:.3f}  {q}")
flag = sum(s < cfg.coverage_threshold for s in scores)
print(f"{qfile}: {flag}/{len(qs)} flagged not covered at threshold {cfg.coverage_threshold}; median score {statistics.median(scores):.3f}")
