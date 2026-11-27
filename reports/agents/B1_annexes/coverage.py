"""Calibrate the coverage signal: positives = answerable dev questions of the 3 suites,
negatives = multirfe abstention questions + hand-written out-of-domain queries."""
import json, sys
from pathlib import Path
from rag_sfar.evaluation.harness import load_retrievers, select_configs
from rag_sfar.evaluation.datasets import load_suite
from rag_sfar.config import Settings
S = Path(__file__).parent
name = sys.argv[1]  # result set to read (e.g. C9)
rer = sys.argv[2] if len(sys.argv) > 2 else Settings().reranker_model
pos, neg_abst = [], []
for suite in ["abpe171", "abp171", "multirfe_synth"]:
    items = {i.id: i for i in load_suite(suite, "dev")}
    for r in json.loads((S / "res" / f"{name}__{suite}.json").read_text())["rows"]:
        v = r["cov"]
        (neg_abst if items[r["id"]].should_abstain else pos).append(v)
ood_path = S / f"ood_{name}.json"
if not ood_path.exists():
    cfg = select_configs("C9")[0]
    retr = load_retrievers(Path("index"), ["table_aware_sota"], "cross_encoder", rer, index_map={"table_aware_sota": "tas_v3_errata"})["table_aware_sota"]
    qs = [l.strip() for l in open("reports/agents/B1_annexes/ood_queries.txt") if l.strip()]
    ood = []
    for q in qs:
        _, _, tm = retr.retrieve(q, config=cfg)
        ood.append({k: tm[k] for k in ("coverage_score", "channel_agreement", "dense_top_score")})
    ood_path.write_text(json.dumps(ood))
ood = json.loads(ood_path.read_text())
neg = neg_abst + ood
def pr(key, negs, label):
    print(f"--- {key} ({label}: pos={len(pos)} neg={len(negs)})")
    vals = sorted({round(v[key], 3) for v in pos + negs})
    best = None
    for t in [0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9] if key == "coverage_score" else [x / 100 for x in range(70, 96, 2)] if key == "dense_top_score" else [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]:
        tp = sum(v[key] >= t for v in pos); fn = len(pos) - tp
        fp = sum(v[key] >= t for v in negs); tn = len(negs) - fp
        # "not covered" detection: precision/recall of predicting negative
        p_nc = tn / (tn + fn) if tn + fn else float("nan"); r_nc = tn / len(negs)
        print(f"  t={t:<5} covered-recall={tp/len(pos):.3f}  not-covered: precision={p_nc:.3f} recall={r_nc:.3f} (fn={fn}, tn={tn})")
for key in ("coverage_score", "dense_top_score", "channel_agreement"):
    pr(key, ood, "OOD only")
    pr(key, neg_abst, "multirfe abstention only")
