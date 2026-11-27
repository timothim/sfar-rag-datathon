"""How often does the structure behind each re-added rule exist in the corpus (current editions)?
- continuation: table_markdown whose table is followed (after its row cards) by another table_markdown
  with the same first line; split by real vs placeholder ("Col 1 | Col 2") header
- scope notes: linked callouts (any doc) whose first 200 chars say "ce(s) tableau(x)" and have no call mark."""
import sys, os, re, collections
sys.path.insert(0, os.path.dirname(__file__))
from common import chunks
from rag_sfar.retrieval import pipeline as P
index = sys.argv[1] if len(sys.argv) > 1 else "tas_v3_errata"
byid, allc = chunks(index)
cur_ed = [c for c in allc if c.is_latest_edition and c.is_active]
cont = collections.Counter(); cont_docs = collections.defaultdict(set)
for c in cur_ed:
    if c.chunk_type != "table_markdown": continue
    hdr = P._first_line(c.text); nxt = byid.get(c.next_chunk_id) if c.next_chunk_id else None
    while nxt is not None and nxt.chunk_type == "table_row_card" and nxt.doc_id == c.doc_id:
        nxt = byid.get(nxt.next_chunk_id) if nxt.next_chunk_id else None
    if nxt is not None and nxt.doc_id == c.doc_id and nxt.chunk_type == "table_markdown" and P._first_line(nxt.text) == hdr:
        kind = "placeholder" if re.search(r"\|\s*Col \d+\s*\|", hdr) else "real"
        cont[kind] += 1; cont_docs[kind].add(c.doc_id)
print(index, "tables directly followed by a table with the same header row:",
      {k: f"{v} tables / {len(cont_docs[k])} docs" for k, v in cont.items()})
linked = {cid for c in cur_ed for cid in c.linked_callout_ids}
scope = [byid[i] for i in linked if i in byid and P._SCOPE_NOTE_RE.search(byid[i].text[:200]) and not P._note_marks(byid[i].text)]
print("linked scope notes:", len(scope), "in docs:", sorted({c.doc_id[:50] for c in scope}))
callouts = [c for c in cur_ed if c.chunk_type == "callout_footnote"]
print("callout_footnote chunks:", len(callouts), "in", len({c.doc_id for c in callouts}), "docs; linked to a table:", len(linked & {c.chunk_id for c in callouts}),
      "in", len({byid[i].doc_id for i in linked if i in byid and byid[i].chunk_type == 'callout_footnote'}), "docs")
