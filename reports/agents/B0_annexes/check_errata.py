"""Check the V3.1 overlay errata passages in an index (argv[1] = index dir)."""
import sqlite3, sys, re
con = sqlite3.connect(f"{sys.argv[1]}/metadata.sqlite")
import json

rows = [(a, b, json.loads(c)["text"]) for a, b, c in con.execute("SELECT chunk_id, chunk_type, payload_json FROM chunks WHERE doc_id LIKE ?", ("%V3_1%",))]
low = [r for r in rows if "faible risque" in r[2].lower() and "aucun des crit" in r[2].lower()]
print(f"chunks V3.1 avec 'faible risque : aucun des critères' : {len(low)}")
for cid, ct, t in low:
    if ct != "table_row_card": continue
    seg = t[t.lower().find("faible risque"):][:200].replace("\n", " ")
    has_cef = bool(re.search(r"c[ée]fazoline", t, re.I)); has_pas = "PAS D" in t.upper()
    print(f"  {ct} {cid[-14:]} céfazoline={has_cef} pas_d_ABP={has_pas} :: {seg}")
cefox = [r for r in rows if re.search(r"Si c[ée]foxitine\s*:\s*\**gentamicine", r[2])]
cefot = [r for r in rows if re.search(r"Si c[ée]fotaxime\s*:", r[2])]
print(f"'Si céfoxitine : gentamicine' : {len(cefox)} chunks ; 'Si céfotaxime :' : {len(cefot)} chunks")
