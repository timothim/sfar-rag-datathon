"""Recompute B1's post-review numbers (C10 frozen = F0) from reports/agents/B1_annexes/res/*.json.gz."""
import gzip, json, statistics, collections
from pathlib import Path
from rag_sfar.evaluation.harness import paired_bootstrap_diff, bootstrap_ci
D = Path("reports/agents/B1_annexes/res")
def rows(n, s):
    p = D / f"{n}__{s}.json.gz"
    return {r["id"]: r for r in json.load(gzip.open(p))["rows"]} if p.exists() else None
MET = {"abpe171": ["sufficiency", "evidence_recall"], "abp171": ["passage_hit"], "multirfe_synth": ["passage_hit"]}
for pre in ("", "tas_v6_"):
    print("=== index", pre or "tas_v3_errata")
    for s, mets in MET.items():
        A, B = rows(pre + "C9W", s), rows(pre + "F0", s)
        for m in mets:
            ids = [i for i in A if A[i].get(m) is not None]
            a = [A[i][m] for i in ids]; b = [B[i][m] for i in ids]
            d = paired_bootstrap_diff(a, b); lo, hi = bootstrap_ci(b)
            print(f"{s:15s} {m:16s} n={len(ids)} C9W {100*statistics.mean(a):.1f} F0 {100*statistics.mean(b):.1f} [{100*lo:.0f}-{100*hi:.0f}] "
                  f"d={100*d['diff']:+.1f} [{100*d['ci_low']:+.1f};{100*d['ci_high']:+.1f}] won={[i for i in ids if B[i][m] > A[i][m]]} lost={[i for i in ids if B[i][m] < A[i][m]]}")
        dup = sum(1 for r in B.values() if len(r["chunks"]) != len(set(r["chunks"])))
        print(f"   F0 {s}: chars {statistics.mean(r['n_chars'] for r in B.values()):.0f} max {max(r['n_chars'] for r in B.values())} chunks {statistics.mean(r['n_chunks'] for r in B.values()):.1f} max {max(r['n_chunks'] for r in B.values())} dup-ids {dup} reasons {collections.Counter(x for r in B.values() for x in r['reasons'])}")
