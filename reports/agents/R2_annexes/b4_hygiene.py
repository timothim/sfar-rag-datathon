"""Duplicated text (normalised as in _dedup_by_text), budget and guaranteed passages in saved contexts."""
import sys, os, re, gzip, json, collections
sys.path.insert(0, os.path.dirname(__file__))
from common import chunks
D = "reports/agents/B1_annexes/res"
def rows(n, s): return json.load(gzip.open(f"{D}/{n}__{s}.json.gz"))["rows"]
norm = lambda t: re.sub(r"\W+", " ", t.lower()).strip()
for index, pre in (("tas_v3_errata", ""), ("tas_v6", "tas_v6_")):
    byid, _ = chunks(index)
    for name in (["C10", "F0"] if not pre else ["F0"]):
        out = []
        for s in ("abpe171", "abp171", "multirfe_synth"):
            R = rows(pre + name, s)
            dup = sum(1 for r in R if len({norm(byid[c].text) for c in r["chunks"]}) < len(r["chunks"]))
            g = sum(1 for r in R for x in r["reasons"] if x and x.split(":")[0] in ("population", "mcq_option"))
            over = sum(1 for r in R if r["n_chars"] > 30000); big = sum(1 for r in R if r["n_chunks"] > 40)
            out.append(f"{s}: dup-text {dup}, guaranteed {g}, >30k chars {over}, >40 chunks {big}")
        print(index, pre + name, " | ".join(out))
