"""K2 — tas_v6 (rows of retrieval_rows.jsonl) vs tas_v7b (retrieval_rows_tas_v7b.jsonl), same
script and frozen configuration; paired bootstrap (b minus a), won / lost."""
import json
from pathlib import Path
from rag_sfar.evaluation.harness import paired_bootstrap_diff
D = Path(__file__).resolve().parent
rows = [json.loads(l) for l in (D / "retrieval_rows.jsonl").open() if '"tas_v6"' in l]
rows += [json.loads(l) for l in (D / "retrieval_rows_tas_v7b.jsonl").open()]
METRIC = {"abpe171": "sufficiency", "abpvern": "sufficiency", "multirfe_synth": "passage_hit"}
out = {}
for suite, met in METRIC.items():
    a = {r["id"]: r.get(met) for r in rows if r["suite"] == suite and r["index"] == "tas_v6"}
    b = {r["id"]: r.get(met) for r in rows if r["suite"] == suite and r["index"] == "tas_v7b"}
    ids = [i for i in a if i in b and a[i] is not None and b[i] is not None]
    xa = [float(a[i]) for i in ids]; xb = [float(b[i]) for i in ids]
    d = paired_bootstrap_diff(xa, xb)
    o = out[suite] = {"metric": met, "n": len(ids), "tas_v6": 100 * sum(xa) / len(ids), "tas_v7b": 100 * sum(xb) / len(ids),
                      "diff_pts": 100 * d["diff"], "ci_low": 100 * d["ci_low"], "ci_high": 100 * d["ci_high"],
                      "won": [i for i in ids if b[i] > a[i]], "lost": [i for i in ids if b[i] < a[i]]}
    print(f"{suite:15s} {met:12s} n={o['n']} v6={o['tas_v6']:.1f} v7b={o['tas_v7b']:.1f} diff={o['diff_pts']:+.1f} [{o['ci_low']:+.1f};{o['ci_high']:+.1f}] won={o['won']} lost={o['lost']}")
(D / "retrieval_summary_v7b.json").write_text(json.dumps(out, indent=1))
