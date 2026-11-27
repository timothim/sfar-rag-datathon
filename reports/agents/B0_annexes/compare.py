"""Paired before/after comparison of two retrieval-only eval reports (same suite, same configs).
usage: compare.py before.json after.json"""
import json, sys, statistics
sys.path.insert(0, "/Users/tim/Me/SFAR-datathon/src")
from rag_sfar.evaluation.harness import paired_bootstrap_diff

A = json.load(open(sys.argv[1])); B = json.load(open(sys.argv[2]))
print(f"## {A['suite']} dev (n={A['n_items']})  before={sys.argv[1].split('/')[-1]}  after={sys.argv[2].split('/')[-1]}")
def derived(row):
    r = row.get("passage_rank")
    d = {"passage_hit@8": row.get("passage_hit"), "passage_mrr": row.get("passage_mrr"),
         "hit_ctx": None if "passage_rank" not in row else (1.0 if r is not None else 0.0)}
    for k in ("evidence_hit", "evidence_recall", "sufficiency", "doc_hit", "obsolete_intrusion"):
        if k in row: d[k] = row[k]
    return d
for ra, rb in zip(A["runs"], B["runs"]):
    assert ra["config"] == rb["config"]
    print(f"\n### {ra['config']}")
    ia = {r["id"]: r for r in ra["rows"]}; ib = {r["id"]: r for r in rb["rows"]}
    ids = [i for i in ia if i in ib]
    da = {i: derived(ia[i]) for i in ids}; db = {i: derived(ib[i]) for i in ids}
    print("| métrique | avant | après | diff [IC95] | P(après<=avant) |\n|---|---:|---:|---:|---:|")
    for m in da[ids[0]]:
        xa = [da[i].get(m) for i in ids]; xb = [db[i].get(m) for i in ids]
        if all(v is None for v in xa): continue
        res = paired_bootstrap_diff(xa, xb)
        ma = statistics.mean(v for v in xa if v is not None); mb = statistics.mean(v for v in xb if v is not None)
        print(f"| {m} | {ma:.3f} | {mb:.3f} | {res['diff']:+.3f} [{res['ci_low']:+.3f}, {res['ci_high']:+.3f}] | {res['p_le_zero']:.2f} |")
    ranks_a = [ia[i].get("passage_rank") for i in ids]; ranks_b = [ib[i].get("passage_rank") for i in ids]
    if any(r is not None for r in ranks_a):
        fa = [r for r in ranks_a if r is not None]; fb = [r for r in ranks_b if r is not None]
        print(f"\nRang du passage (trouvés) : médiane {statistics.median(fa)} -> {statistics.median(fb)}, moyenne {statistics.mean(fa):.2f} -> {statistics.mean(fb):.2f}")
    ca = ra["summary"].get("passage_hit_curve"); cb = rb["summary"].get("passage_hit_curve")
    if ca: print("Courbe passage hit@k : " + ", ".join(f"@{k} {ca[k]:.3f}->{cb[k]:.3f}" for k in ca))
    for cur in ("evidence_recall_curve", "sufficiency_curve"):
        ca = ra["summary"].get(cur); cb = rb["summary"].get(cur)
        if ca: print(f"Courbe {cur} : " + ", ".join(f"@{k} {ca[k]:.3f}->{cb[k]:.3f}" for k in ca))
    changed = [(i, ranks_a[n], ranks_b[n]) for n, i in enumerate(ids) if ranks_a[n] != ranks_b[n]]
    worse = [c for c in changed if (c[2] is None) or (c[1] is not None and c[2] > c[1])]
    better = [c for c in changed if c not in worse]
    print(f"Rang changé : {len(changed)} questions ; meilleur {len(better)}, pire {len(worse)}")
    print("  pire : " + ", ".join(f"{i}:{a}->{b}" for i, a, b in worse))
    print("  meilleur : " + ", ".join(f"{i}:{a}->{b}" for i, a, b in better))
