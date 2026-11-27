"""Synthetic recall of the plausibility detector (D1) for micro-sign loss.

For every dose of the corpus written in µg and attributed to a drug, simulate the conversion error
(µg -> mg, i.e. x1000) and check whether the D1 range test would flag it. Also simulates the
reverse error (mg -> µg, /1000) on mg doses, and a lost decimal separator (x10) on doses < 1.
Read-only; prints a table. Usage: .venv/bin/python reports/agents/D1_annexes/recall_test.py
"""
import collections
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from detect_doses import DRUGS  # noqa: E402


def flagged(drug, dtype, ug):
    rng = DRUGS[drug].get(dtype)
    if not rng or ug <= 0:
        return None
    lo, hi = rng
    return ug < lo / 10 or ug > hi * 10


rows = list(csv.DictReader(open(HERE / "doses_extracted.tsv", encoding="utf-8"), delimiter="\t"))
res = collections.defaultdict(lambda: [0, 0, 0])  # scenario -> [testable, flagged_after, flagged_before]
for r in rows:
    ug, d, t = float(r["ug"]), r["drug"], r["dtype"]
    scen = []
    if r["unit"] == "µg":
        scen.append(("µg→mg (x1000)", ug * 1000))
    if r["unit"] == "mg":
        scen.append(("mg→µg (/1000)", ug / 1000))
        scen.append(("mg→g (x1000)", ug * 1000))
    if float(r["value"]) < 1:
        scen.append(("virgule perdue 0,5→5 (x10)", ug * 10))
    for name, new in scen:
        before, after = flagged(d, t, ug), flagged(d, t, new)
        if before is None:
            continue
        res[name][0] += 1
        res[name][1] += bool(after)
        res[name][2] += bool(before)
print("scénario | doses testables | détectées après corruption | déjà signalées avant")
for k, (n, a, b) in res.items():
    print(f"{k} | {n} | {a} ({100 * a / n:.0f} %) | {b}")
