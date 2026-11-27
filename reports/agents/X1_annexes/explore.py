import sqlite3, json, collections, sys, re
sys.path.insert(0, "src")
from rag_sfar.retrieval.pipeline import _act_tokens
c = sqlite3.connect('index/tas_v6/metadata.sqlite')
rows = [json.loads(r[0]) for r in c.execute("select payload_json from chunks where chunk_type='table_row_card' order by idx")]
def label(t):
    lines = [l for l in t.splitlines() if l.strip()]
    line = next((l for l in lines if " | " in l), lines[-1] if lines else "")
    cell = line.split(" | ")[0]
    h, _, v = cell.partition(" : ")
    return h, v
doc = sys.argv[1]
for r in rows:
    if doc not in r['doc_id']: continue
    h, v = label(r['text'])
    print(r['chunk_index'], r['table_id'][-5:], ','.join(r.get('populations') or []), r.get('population_source'), '|', r['section_path'][-60:], '|', h[:30], '=>', v[:70])
