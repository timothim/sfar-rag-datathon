"""Reproduce B1's headline numbers and paired differences from B1's saved per-question rows."""
import sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import rows, SUITES
from rag_sfar.evaluation.harness import paired_bootstrap_diff, bootstrap_ci
import statistics

MET = {"abpe171": ["sufficiency", "evidence_recall"], "abp171": ["passage_hit"], "multirfe_synth": ["passage_hit"]}
def mean(v): return 100 * sum(v) / len(v)
for prefix in ["", "v4_"]:
    print("=== index", "tas_v4" if prefix else "tas_v3_errata")
    for s in SUITES:
        R = {n: rows(prefix + n, s) for n in ["C9", "C9W", "C10"]}
        for m in MET[s]:
            ids = [i for i in R["C9"] if R["C9"][i].get(m) is not None]
            line = f"{s:15s} {m:16s} n={len(ids)}"
            for n in R:
                v = [R[n][i][m] for i in ids]
                lo, hi = bootstrap_ci(v)
                line += f" | {n} {mean(v):.1f} [{100*lo:.0f}-{100*hi:.0f}]"
            d = paired_bootstrap_diff([R["C9W"][i][m] for i in ids], [R["C10"][i][m] for i in ids])
            won = [i for i in ids if R["C10"][i][m] > R["C9W"][i][m]]
            lost = [i for i in ids if R["C10"][i][m] < R["C9W"][i][m]]
            line += f" | C10-C9W {100*d['diff']:+.1f} [{100*d['ci_low']:+.1f};{100*d['ci_high']:+.1f}] won={len(won)} lost={lost}"
            print(line)
        for n in R:
            print(f"   {n}: chars mean {statistics.mean(r['n_chars'] for r in R[n].values()):.0f} max {max(r['n_chars'] for r in R[n].values())} chunks {statistics.mean(r['n_chunks'] for r in R[n].values()):.1f}")
