"""Recompute B2's paired dev differences from the saved per-question rows (no retrieval rerun)."""
import glob, json, sys
from rag_sfar.evaluation.harness import paired_bootstrap_diff

STEPS = ["b2_base", "b2_v4t", "b2_v4c", "b2_v4h", "b2_v4r", "b2_v4"]
SUITES = ["abpe171", "multirfe_synth", "abp171"]

def load(suite, tag):
    f = glob.glob(f"reports/eval/*_{suite}_dev_{tag}.json")
    assert len(f) == 1, (suite, tag, f)
    return json.load(open(f[0]))

def metric(row, m):
    if m == "hit@8":
        r = row.get("passage_rank")
        return None if row.get("passage_hit") is None else float(r is not None and r <= 8)
    return row.get(m)

def compare(suite, a_tag, b_tag, out):
    A, B = load(suite, a_tag), load(suite, b_tag)
    for ra, rb in zip(A["runs"], B["runs"]):
        assert ra["config"] == rb["config"]
        cfg = "C9" if "context_window" not in ra["config"] else "C9+fenetres"
        ia = {r["id"]: r for r in ra["rows"]}; ib = {r["id"]: r for r in rb["rows"]}
        ids = [i for i in ia if i in ib]
        for m in ["sufficiency", "evidence_recall", "passage_hit", "hit@8", "obsolete_intrusion", "doc_hit"]:
            a = [metric(ia[i], m) for i in ids]; b = [metric(ib[i], m) for i in ids]
            pa = [x for x, y in zip(a, b) if x is not None and y is not None]
            pb = [y for x, y in zip(a, b) if x is not None and y is not None]
            if not pa: continue
            d = paired_bootstrap_diff(a, b)
            out.append((suite, cfg, m, len(pa), 100*sum(pa)/len(pa), 100*sum(pb)/len(pb), 100*d["diff"], 100*d["ci_low"], 100*d["ci_high"], a_tag, b_tag))

out = []
for s in SUITES:
    compare(s, "b2_base", "b2_v4", out)
    for x, y in zip(STEPS[:-1], STEPS[1:]):
        if y == "b2_v4": x = "b2_v4c"
        compare(s, x, y, out)
print("suite\tconfig\tmetric\tn\ta\tb\tdiff\tci_low\tci_high\tfrom\tto")
for r in out:
    print("\t".join(str(round(x, 1)) if isinstance(x, float) else str(x) for x in r))
