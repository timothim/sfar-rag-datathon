import json, sys, statistics
from pathlib import Path
from rag_sfar.evaluation.harness import bootstrap_ci
RES = Path(__file__).parent / "res"
for n in sys.argv[1:]:
    cells = [n]
    for s, m in [("abpe171", "sufficiency"), ("abpe171", "evidence_recall"), ("abp171", "passage_hit"), ("multirfe_synth", "passage_hit")]:
        rows = json.loads((RES / f"{n}__{s}.json").read_text())["rows"]
        v = [r[m] for r in rows if r.get(m) is not None]
        lo, hi = bootstrap_ci(v)
        cells.append(f"{100*sum(v)/len(v):.1f} [{100*lo:.0f}–{100*hi:.0f}]")
    allrows = [r for s in ("abpe171", "abp171", "multirfe_synth") for r in json.loads((RES / f"{n}__{s}.json").read_text())["rows"]]
    cells.append(f"{statistics.mean(r['n_chars'] for r in allrows):,.0f}".replace(",", " "))
    cells.append(f"{statistics.mean(r['n_chunks'] for r in allrows):.1f}")
    cells.append(f"{statistics.median(r['latency_ms'] for r in allrows):.0f}")
    cells.append(f"{max(r['n_chars'] for r in allrows):,.0f}".replace(",", " "))
    print("| " + " | ".join(cells) + " |")
