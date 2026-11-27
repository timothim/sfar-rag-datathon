import gzip, json, sys, statistics
from pathlib import Path
from rag_sfar.evaluation.harness import bootstrap_ci
RES = Path(sys.argv.pop(1)) if len(sys.argv) > 2 and Path(sys.argv[1]).is_dir() else Path(__file__).parent / "res"
def _rows(path):
    """Rows of a result file (.json, or the committed .json.gz copy)."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())["rows"]
    gz = Path(str(path) + ".gz")
    return json.loads(gzip.open(gz).read())["rows"] if gz.exists() else None

for n in sys.argv[1:]:
    cells = [n]
    for s, m in [("abpe171", "sufficiency"), ("abpe171", "evidence_recall"), ("abp171", "passage_hit"), ("multirfe_synth", "passage_hit")]:
        rows = _rows(RES / f"{n}__{s}.json")
        v = [r[m] for r in rows if r.get(m) is not None]
        lo, hi = bootstrap_ci(v)
        cells.append(f"{100*sum(v)/len(v):.1f} [{100*lo:.0f}–{100*hi:.0f}]")
    allrows = [r for s in ("abpe171", "abp171", "multirfe_synth") for r in _rows(RES / f"{n}__{s}.json")]
    cells.append(f"{statistics.mean(r['n_chars'] for r in allrows):,.0f}".replace(",", " "))
    cells.append(f"{statistics.mean(r['n_chunks'] for r in allrows):.1f}")
    cells.append(f"{statistics.median(r['latency_ms'] for r in allrows):.0f}")
    cells.append(f"{max(r['n_chars'] for r in allrows):,.0f}".replace(",", " "))
    print("| " + " | ".join(cells) + " |")
