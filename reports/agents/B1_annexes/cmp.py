"""Compare variants vs a base: means, CI, paired diff, changed questions."""
import gzip, json, sys, statistics
from pathlib import Path
from rag_sfar.evaluation.harness import paired_bootstrap_diff, bootstrap_ci
RES = Path(sys.argv.pop(1)) if len(sys.argv) > 2 and Path(sys.argv[1]).is_dir() else Path(__file__).parent / "res"
def _rows(path):
    """Rows of a result file (.json, or the committed .json.gz copy)."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())["rows"]
    gz = Path(str(path) + ".gz")
    return json.loads(gzip.open(gz).read())["rows"] if gz.exists() else None

METRIC = {"abpe171": ["sufficiency", "evidence_recall", "passage_hit"], "abp171": ["passage_hit"], "multirfe_synth": ["passage_hit"]}
def load(n, s):
    p = RES / f"{n}__{s}.json"
    rows = _rows(p)
    return {r["id"]: r for r in rows} if rows else None
base = sys.argv[1]
for other in sys.argv[2:]:
    print(f"== {other} vs {base}")
    for s, mets in METRIC.items():
        A, B = load(base, s), load(other, s)
        if not A or not B: continue
        line = [s]
        for m in mets:
            ids = [i for i in A if A[i].get(m) is not None and B.get(i, {}).get(m) is not None]
            a = [A[i][m] for i in ids]; b = [B[i][m] for i in ids]
            d = paired_bootstrap_diff(a, b)
            lo, hi = bootstrap_ci(b)
            line.append(f"{m} {100*sum(a)/len(a):.1f}->{100*sum(b)/len(b):.1f} [{100*lo:.0f}-{100*hi:.0f}] d={100*d['diff']:+.1f}[{100*d['ci_low']:+.1f};{100*d['ci_high']:+.1f}]")
            if m == mets[0]:
                lost = [i for i in ids if A[i][m] > B[i][m]]; won = [i for i in ids if A[i][m] < B[i][m]]
        ca = statistics.mean(r["n_chars"] for r in A.values()); cb = statistics.mean(r["n_chars"] for r in B.values())
        la = statistics.median(r["latency_ms"] for r in A.values()); lb = statistics.median(r["latency_ms"] for r in B.values())
        line.append(f"chars {ca:.0f}->{cb:.0f} lat {la:.0f}->{lb:.0f}")
        print("  " + " | ".join(line)); print(f"    won={won} lost={lost}")
