"""Sufficiency after the generation-side selection (select_within_budget) of the 'wide' and 'small'
presets, applied to the saved retrieval contexts."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import rows, items, chunks
from rag_sfar.schemas import RetrievedChunk
from rag_sfar.evaluation.harness import evidence_metrics, passage_match
from rag_sfar.generation.context import select_within_budget
from rag_sfar.evaluation.harness import paired_bootstrap_diff
byid, _ = chunks()
def ok(it, ret):
    if it.evidence_sets:
        m = evidence_metrics(it, ret); return m.get("sufficiency") if m else None
    if it.gold_passages:
        return float(any(passage_match(gp.quote, r.chunk.text) for gp in it.gold_passages for r in ret))
for suite in ("abpe171", "abp171", "multirfe_synth"):
    I = items(suite)
    res = {}
    for name in ("C9W", "WN", "C10"):
        R = rows(name, suite)
        for lab, (mc, mx) in {"full": (10**6, 10**9), "wide40/30k": (40, 30000)}.items():
            v = {}
            for qid, row in R.items():
                ret = [RetrievedChunk(chunk=byid[c], final_score=0.0) for c in row["chunks"]]
                sel = select_within_budget(ret, mc, mx)
                x = ok(I[qid], sel)
                if x is not None: v[qid] = x
            res[(name, lab)] = v
    ids = sorted(res[("C10", "full")])
    for k, v in res.items():
        print(f"{suite:15s} {k[0]:4s} {k[1]:11s} {100*sum(v[i] for i in ids)/len(ids):.1f}")
    a = [res[("C10", "full")][i] for i in ids]; b = [res[("C10", "wide40/30k")][i] for i in ids]
    print("   lost by wide selection:", [i for i in ids if res[("C10","full")][i] > res[("C10","wide40/30k")][i]])
    d = paired_bootstrap_diff([res[("C9W", "wide40/30k")][i] for i in ids], b)
    print(f"   C10 vs C9W after wide selection: {100*d['diff']:+.1f} [{100*d['ci_low']:+.1f};{100*d['ci_high']:+.1f}]")
