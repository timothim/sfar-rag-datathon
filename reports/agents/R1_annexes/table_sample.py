"""R1: stratified sample of source tables (seed 11) printed next to the tas_v4 chunks that contain
their first data cell, for manual side-by-side review. Strata: one table per document, documents
spread over years; tables with rowspan/colspan, footnote calls and Mermaid flowcharts favoured."""
import collections, json, random, re, sqlite3, unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
from rag_sfar.ingestion import loader as L
from rag_sfar.ingestion.text_cleaning import clean_chunk_text

def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip().lower()
docs = L.load_sfar_corpus(Path("data/sfar_recommendations/output"), updates_dir=Path("data/corpus_updates"), use_corpus_updates=True)
con = sqlite3.connect("index/tas_v4/metadata.sqlite")
ch_by_doc = collections.defaultdict(list)
for did, ct, p in con.execute("select doc_id, chunk_type, payload_json from chunks where chunk_type in ('table_markdown','table_row_card','callout_allergy','prose','callout_footnote')"):
    c = json.loads(p); ch_by_doc[did].append((ct, c["text"], c["populations"]))
rng = random.Random(11)
cands = []
for d in docs:
    tabs = re.findall(r"<table\b.*?</table>", d.text, flags=re.S | re.I)
    if tabs:
        merged = [t for t in tabs if re.search(r"rowspan|colspan", t) and re.search(r"\d", t)]
        pool = merged or tabs
        cands.append((d, rng.choice(pool)))
rng.shuffle(cands)
cands.sort(key=lambda x: x[0].metadata.effective_year or 0)
# take every k-th to spread over years, 42 tables
step = max(1, len(cands) // 42)
sel = cands[::step][:42]
for i, (d, t) in enumerate(sel, 1):
    soup = BeautifulSoup(t, "html.parser")
    rows = []
    for tr in soup.find_all("tr")[:7]:
        cells = []
        for c in tr.find_all(["td", "th"], recursive=False):
            span = ("" if c.get("rowspan", "1") == "1" else f"[rs{c.get('rowspan')}]") + ("" if c.get("colspan", "1") == "1" else f"[cs{c.get('colspan')}]")
            cells.append(span + re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:90])
        rows.append(" || ".join(cells))
    first = ""
    for tr in soup.find_all("tr"):
        for c in tr.find_all("td"):
            tx = clean_chunk_text(re.sub(r"\s+", " ", c.get_text(" ", strip=True)))
            tx = re.sub(r"^[▪■•○◦\-–—]+\s*", "", tx)
            if len(tx) >= 12:
                first = norm(tx)[:30]; break
        if first: break
    hits = [(ct, tx) for ct, tx, pops in ch_by_doc[d.metadata.doc_id] if first and first in norm(tx)]
    print(f"===== T{i} doc={d.metadata.doc_id[:70]} year={d.metadata.effective_year} key={first!r}")
    print("SOURCE:"); [print("   ", r[:400]) for r in rows]
    for ct, tx in hits[:3]:
        print(f"CHUNK[{ct}]:", tx[:700].replace("\n", " ⏎ "))
    if not hits: print("CHUNK: none found")
