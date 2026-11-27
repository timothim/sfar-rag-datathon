import json, sqlite3, sys
sys.path.insert(0, "scripts")
from build_chunk_links import cell_line
L = json.load(open("index/tas_v6_links/links.json"))
con = sqlite3.connect("index/tas_v6/metadata.sqlite")
def get(cid): return json.loads(con.execute("select payload_json from chunks where chunk_id=?", (cid,)).fetchone()[0])
kind = sys.argv[1]
i = 0
for s, links in sorted(L[kind].items()):
    a = get(s)
    for l in links:
        i += 1; b = get(l["target"])
        if kind == "counterparts":
            print(f"[{i}] {l['source_population']}->{l['target_population']} {l['match']}  {a['table_id'][-4:]}->{b['table_id'][-4:]}")
            print("  S:", a["section_path"][-70:], "||", cell_line(a["text"])[:230])
            print("  T:", b["section_path"][-70:], "||", cell_line(b["text"])[:230])
        else:
            print(f"[{i}] {l['marks']}  {a['doc_id'][:40]}")
            print("  S:", a["text"].replace("\n", " // ")[-250:])
            print("  N:", b["text"][:250].replace("\n", " // "))
