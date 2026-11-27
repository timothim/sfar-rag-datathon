"""Corpus-wide reach of the two note rules added back after single questions regressed:
(a) scope note ("... ce tableau", linked, no call mark); (b) page-break continuation (a following
table_markdown with the same header row is treated as the same table).
Runs the real `_called_notes` on every table chunk of the current editions, with and without
continuation, and counts tables / documents affected. Usage: python ... <index> [sample_n]"""
import sys, os, re, random, collections, gzip, json
sys.path.insert(0, os.path.dirname(__file__))
from common import chunks
from rag_sfar.retrieval import pipeline as P

index = sys.argv[1] if len(sys.argv) > 1 else "tas_v3_errata"
byid, allc = chunks(index)

class Store:
    def get_chunk(self, cid): return byid.get(cid)
class Fake:
    store = Store()
    no_cont = False
    def _table_header(self, c):
        return "" if self.no_cont else P.SfarRagRetriever._table_header(self, c)
f = Fake()
def notes(c, scope, cont):
    f.no_cont = not cont
    return {n.chunk_id for n in P.SfarRagRetriever._called_notes(f, c, 1200, scope)}

ABP = "antibioprophylaxie"
tabs = [c for c in allc if c.chunk_type in ("table_row_card", "table_markdown") and c.is_latest_edition and c.is_active]
scope_t, scope_d, cont_t, cont_d, cont_notes = set(), set(), set(), set(), collections.defaultdict(set)
generic_hdr = collections.Counter()
for c in tabs:
    base = notes(c, False, False)
    with_scope = notes(c, True, False)
    with_cont = notes(c, False, True)
    tkey = (c.doc_id, P._first_line(c.text) if c.chunk_type == "table_markdown" else c.prev_chunk_id)
    if with_scope - base:
        scope_t.add(c.chunk_id); scope_d.add(c.doc_id)
    if with_cont - base:
        cont_t.add(c.chunk_id); cont_d.add(c.doc_id)
        for n in with_cont - base: cont_notes[n].add(c.chunk_id)
        hdr = P.SfarRagRetriever._table_header(f, c)
        generic_hdr["placeholder header (Col 1 | Col 2 ...)" if re.search(r"\|\s*Col \d+\s*\|", hdr) else "real header"] += 1
def split(ids, docs):
    abp = sum(1 for d in docs if ABP in d.lower())
    return f"{len(ids)} table chunks in {len(docs)} documents (ABP: {abp} doc)"
print(index, "current-edition table chunks:", len(tabs), "in", len({c.doc_id for c in tabs}), "documents")
print("scope note attaches something:", split(scope_t, scope_d))
print("   non-ABP documents:", sorted(d[:60] for d in scope_d if ABP not in d.lower()))
print("page-break continuation attaches extra notes:", split(cont_t, cont_d))
print("   non-ABP documents:", sorted(d[:60] for d in cont_d if ABP not in d.lower()))
print("   header kind of the anchors' tables:", dict(generic_hdr))
print("   distinct notes added by continuation:", len(cont_notes))
random.seed(1)
non_abp = [(n, a) for n, a in cont_notes.items() if ABP not in byid[n].doc_id.lower()]
for n, anchors in random.sample(non_abp, min(int(sys.argv[2]) if len(sys.argv) > 2 else 8, len(non_abp))):
    a = byid[sorted(anchors)[0]]; nn = byid[n]
    print(f"--- doc {nn.doc_id[:60]}\n    anchor [{a.chunk_type}] header={P.SfarRagRetriever._table_header(f, a)[:90]!r}\n    anchor text: {a.text[:160]!r}\n    note: {nn.text[:220]!r}")
