import sqlite3, json, sys
con = sqlite3.connect("index/tas_v6/metadata.sqlite")
cid = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
p = json.loads(con.execute("select payload_json from chunks where chunk_id=?", (cid,)).fetchone()[0])
doc, i = p["doc_id"], p["chunk_index"]
for r in con.execute("select payload_json from chunks where doc_id=? order by idx", (doc,)):
    q = json.loads(r[0])
    if i - 2 <= q["chunk_index"] <= i + n:
        print(q["chunk_index"], q["chunk_type"], q.get("table_id","")[-4:], "|", q["text"][:260].replace("\n", " // "))
