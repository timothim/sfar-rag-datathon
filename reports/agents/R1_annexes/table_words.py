"""R1: word-level coverage of source table cells in the table chunks of an index.
For each source cell, every word of >= 4 letters must occur in one table chunk of the same doc
that also contains the cell's first 3 words (local co-occurrence, not just anywhere in the doc).
Reports cells with missing words. CPU only."""
import collections, json, re, sqlite3, sys, unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
from rag_sfar.ingestion import loader as L
from rag_sfar.ingestion.text_cleaning import replace_math, decode_entities

def norm(s):
    s = unicodedata.normalize("NFKC", decode_entities(replace_math(s))).replace("’", "'").lower()
    return re.sub(r"\s+", " ", s)
W = re.compile(r"[a-zàâäéèêëîïôöùûüç]{4,}")
idx = sys.argv[1]
docs = L.load_sfar_corpus(Path("data/sfar_recommendations/output"), updates_dir=Path("data/corpus_updates"), use_corpus_updates=True)
con = sqlite3.connect(f"{idx}/metadata.sqlite")
tabs = collections.defaultdict(list)
for did, ct, p in con.execute("select doc_id, chunk_type, payload_json from chunks where chunk_type in ('table_markdown','table_row_card','callout_allergy')"):
    tabs[did].append(norm(json.loads(p)["text"]))
miss_cells = collections.Counter(); cells_n = 0; out = []
for d in docs:
    did = d.metadata.doc_id
    chunks = tabs.get(did, [])
    for tm in re.finditer(r"<table\b.*?</table>", d.text, flags=re.S | re.I):
        soup = BeautifulSoup(tm.group(0), "html.parser")
        for c in soup.find_all(["td", "th"]):
            if c.find(["td", "th"]):
                continue
            t = norm(c.get_text(" ", strip=True))
            ws = W.findall(t)
            if len(ws) < 2:
                continue
            cells_n += 1
            head = ws[:3]
            local = [k for k in chunks if all(h in k for h in head)]
            pool = local or chunks
            missing = [w for w in dict.fromkeys(ws) if not any(w in k for k in pool)]
            if missing:
                miss_cells[did] += 1
                out.append(f"{did}\t{'LOCAL' if local else 'NOLOCAL'}\tmissing={missing[:6]}\tcell={t[:220]}")
with open(f"reports/agents/R1_annexes/table_words_{Path(idx).name}.txt", "w") as f:
    f.write(f"cells checked {cells_n}, cells with missing words {sum(miss_cells.values())}, docs {len(miss_cells)}\n")
    f.write(json.dumps(miss_cells.most_common(50), ensure_ascii=False) + "\n")
    f.write("\n".join(out))
print(idx, cells_n, sum(miss_cells.values()), len(miss_cells))
