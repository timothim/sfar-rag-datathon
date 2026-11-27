"""Contrast: links a looser rule (at least one shared act item instead of 'every act of the
source covered') would add on top of the strict sidecar. Printed for reading."""
import json, sqlite3, sys, collections
sys.path.insert(0, "scripts")
from build_chunk_links import row_label, label_items, informative, population_class, cell_line
from rag_sfar.schemas import Chunk
con = sqlite3.connect("index/tas_v6/metadata.sqlite")
chunks = [Chunk.model_validate_json(r[0]) for r in con.execute("select payload_json from chunks where chunk_type='table_row_card' order by idx")]
strict = json.load(open("index/tas_v6_links/links.json"))["counterparts"]
S = {(s, l["target"]) for s, ls in strict.items() for l in ls}
rows = collections.defaultdict(list); seen = set()
for c in chunks:
    if not (c.is_latest_edition and c.is_active): continue
    p = population_class(c); h, lab = row_label(c.text); it = label_items(lab)
    if not p or not h or not informative(it): continue
    k = (c.doc_id, cell_line(c.text).lower())
    if k in seen: continue
    seen.add(k); rows[c.doc_id].append((c, p, h, it))
i = 0; src_loose = set()
for d, L in rows.items():
    for a in L:
        for b in L:
            if a[1] == b[1] or a[0].table_id == b[0].table_id or a[2] != b[2]: continue
            if (a[3] & b[3]) and (a[0].chunk_id, b[0].chunk_id) not in S:
                i += 1; src_loose.add(a[0].chunk_id)
                print(f"[L{i}] {a[1]}->{b[1]}  shared={len(a[3]&b[3])} src_items={len(a[3])} tgt_items={len(b[3])}")
                print("  S:", cell_line(a[0].text)[:220]); print("  T:", cell_line(b[0].text)[:220])
print("loose-only links", i, "sources", len(src_loose), "sources with strict", len(strict),
      "linkable single-pop rows in docs with >=2 classes", sum(len(L) for L in rows.values() if len({x[1] for x in L}) > 1))
