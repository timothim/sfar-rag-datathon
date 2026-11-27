"""Identity of HEAD reruns (res2/) with saved rows: C9 vs R2's pre-correction C9 and B1's C9; C10_context_notes vs B1's F0."""
import gzip, json
from pathlib import Path
A = Path("reports/agents/R2_annexes"); B = Path("reports/agents/B1_annexes/res")
def load(p):
    if not p.exists(): return None
    d = json.load(gzip.open(p)) if p.suffix == ".gz" else json.loads(p.read_text())
    return {r["id"]: r["chunks"] for r in d["rows"]}
for index, pre in (("tas_v3_errata", ""), ("tas_v6", "tas_v6_")):
    for s in ("abpe171", "abp171", "multirfe_synth"):
        c9 = load(A / "res2" / f"{index}_C9_simple_hybrid_rerank__{s}.json")
        c10 = load(A / "res2" / f"{index}_C10_context_notes__{s}.json")
        refs = {"B1 C9": load(B / f"{pre}C9__{s}.json.gz"), "R2 C9 (pre-correction HEAD)": load(A / "res" / f"C9__{s}.json") if not pre else None,
                "B1 F0": load(B / f"{pre}F0__{s}.json.gz")}
        for lab, ref in refs.items():
            new = c10 if "F0" in lab else c9
            if ref is None or new is None: continue
            print(f"{index:14s} {s:15s} HEAD vs {lab:28s} identical {sum(ref[i] == new[i] for i in ref)}/{len(ref)}")
