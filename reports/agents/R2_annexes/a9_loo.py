"""Leave-one-rule-out from C10 (R2 runs on HEAD) + identity checks against B1's saved rows."""
import sys, os, statistics
sys.path.insert(0, os.path.dirname(__file__))
from common import rows, items, chunks, B1RES, R2RES, SUITES
from rag_sfar.evaluation.harness import paired_bootstrap_diff
byid, _ = chunks()
MET = {"abpe171": "sufficiency", "abp171": "passage_hit", "multirfe_synth": "passage_hit"}
for s in SUITES:
    for n in ("C9", "C10"):
        a, b = rows(n, s, B1RES), rows(n, s, R2RES)
        if a and b:
            same = sum(a[i]["chunks"] == b[i]["chunks"] for i in a)
            print(f"identity {s:15s} {n}: B1 rows vs R2 rerun (HEAD) identical contexts {same}/{len(a)}")
for s in SUITES:
    m = MET[s]; I = items(s)
    base = rows("C10", s, R2RES)
    if not base: continue
    ids = [i for i in base if base[i].get(m) is not None]
    print(f"== {s} ({m}, n={len(ids)}) C10 = {100*statistics.mean(base[i][m] for i in ids):.1f}, chars {statistics.mean(r['n_chars'] for r in base.values()):.0f}, chunks {statistics.mean(r['n_chunks'] for r in base.values()):.1f}")
    for v in ("C10_noPop", "C10_noCounterpart", "C10_noNotes", "C10_cap7", "C10_noMCQ"):
        R = rows(v, s, R2RES)
        if not R: continue
        d = paired_bootstrap_diff([R[i][m] for i in ids], [base[i][m] for i in ids])
        won = [i for i in ids if base[i][m] > R[i][m]]; lost = [i for i in ids if base[i][m] < R[i][m]]
        gold = lambda row, it: (sum(len(byid[c].text) for c in row["chunks"] if byid[c].doc_id in set(it.gold_doc_ids)) / max(1, row["n_chars"])) if it.gold_doc_ids else None
        gs = [(gold(R[i], I[i]), gold(base[i], I[i])) for i in R if gold(R[i], I[i]) is not None]
        dg = paired_bootstrap_diff([x for x, _ in gs], [y for _, y in gs]) if gs else None
        print(f"  rule removed: {v:18s} C10 - variant = {100*d['diff']:+.1f} [{100*d['ci_low']:+.1f};{100*d['ci_high']:+.1f}] rule wins {won} rule loses {lost} | "
              f"chars added by rule {statistics.mean(base[i]['n_chars'] for i in R) - statistics.mean(R[i]['n_chars'] for i in R):+.0f} | "
              f"chunks {statistics.mean(base[i]['n_chunks'] for i in R) - statistics.mean(R[i]['n_chunks'] for i in R):+.1f} | "
              + (f"gold-doc share {100*dg['diff']:+.1f} [{100*dg['ci_low']:+.1f};{100*dg['ci_high']:+.1f}] | " if dg else "")
              + f"latency median {statistics.median(base[i]['latency_ms'] for i in R) - statistics.median(R[i]['latency_ms'] for i in R):+.0f} ms")
