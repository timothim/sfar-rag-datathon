import collections, json, re, sys
from bs4 import BeautifulSoup
from rag_sfar.config import Settings
from rag_sfar.ingestion import chunker, table_parser
from rag_sfar.ingestion.loader import load_sfar_corpus
stats = collections.Counter()
orig = chunker.parse_html_table
def wrapped(html, *a, **kw):
    pt = orig(html, *a, **kw)
    tr = BeautifulSoup(html, "html.parser").find("tr")
    cells = tr.find_all(["th", "td"]) if tr else []
    banner = bool(tr) and len([c for c in cells if c.get_text(strip=True)]) == 1 and bool(tr.find("th"))
    stats["tables"] += 1
    if banner: stats["banner_first_row"] += 1
    if pt.inherited_headers:
        stats["inherited_headers"] += 1
        if banner: stats["inherited_via_banner"] += 1
    return pt
chunker.parse_html_table = wrapped
s = Settings()
docs = load_sfar_corpus(s.corpus_dir)
chunks = chunker.chunk_corpus(docs, strategy="table_aware_sota")
types = collections.Counter(c.chunk_type for c in chunks)
fn_rec = sum(1 for c in chunks if c.chunk_type == "callout_footnote" and chunker.REC_ID_RE.search(c.text) and chunker.GRADE_RE.search(c.text))
v = [(d.metadata.doc_id, d.metadata.is_latest_edition, d.metadata.version_label, d.metadata.superseded_by) for d in docs if "antibioprophylaxie-2023_V3" in d.metadata.doc_id]
print(json.dumps({"docs": len(docs), "chunks": len(chunks), "types": types, "footnotes_that_are_rec_boxes": fn_rec, "tables": stats, "abp_v3": v}, ensure_ascii=False, indent=1, default=str))
