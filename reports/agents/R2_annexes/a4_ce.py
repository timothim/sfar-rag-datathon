"""Cross-encoder score of each guaranteed passage (population / MCQ) vs relevance (evidence / gold)."""
import sys, os, statistics
sys.path.insert(0, os.path.dirname(__file__))
from common import rows, items, chunks, SUITES
from a2_rules import relevant  # noqa
byid, _ = chunks()
for s in SUITES:
    R = rows("C10", s); I = items(s)
    for kind in ("population:pediatrie", "population:adulte", "mcq_option"):
        rel, irr, gd = [], [], []
        for qid, row in R.items():
            for cid, r, ce in zip(row["chunks"], row["reasons"], row["ce"]):
                if r and r.startswith(kind):
                    ok = relevant(I[qid], cid)
                    (rel if ok else irr).append(ce if ce is not None else -1)
        if rel or irr:
            q = lambda v: [round(x, 3) for x in statistics.quantiles(v, n=4)] if len(v) >= 4 else [round(x,3) for x in v]
            print(f"{s:15s} {kind:22s} relevant n={len(rel)} CE quartiles {q(rel)} | not relevant n={len(irr)} CE quartiles {q(irr)} | <0.2: rel {sum(x<0.2 for x in rel)} irr {sum(x<0.2 for x in irr)}")
