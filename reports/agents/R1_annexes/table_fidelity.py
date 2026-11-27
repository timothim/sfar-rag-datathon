"""R1: automated fidelity check of table content between the loaded source Markdown (HTML tables)
and the chunk text of an index (table_markdown, table_row_card, callout_allergy chunks).

For every source <table>, clinical tokens are extracted from each cell (numbers with units or
comparators, ranges, exponents, 'pas d'antibioprophylaxie', negations) and searched in the union of
that document's table chunk texts. A token is "lost" when absent from every table chunk of the doc.
Row check: for each source <tr> whose first cell is non-empty and that holds a dose-like token, there
must be one row card containing both a 4-word prefix of the first cell and every dose token of the row.
CPU only. Usage: python table_fidelity.py index/tas_v4 [index/tas_v3_errata]
"""
import collections, html, json, re, sqlite3, sys, unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
from rag_sfar.ingestion import loader as L
from rag_sfar.ingestion.text_cleaning import replace_math, decode_entities

def norm(s):
    s = unicodedata.normalize("NFKC", decode_entities(s))
    s = s.replace("’", "'").replace(" ", " ")
    s = re.sub(r"\s+", " ", s)
    return s.lower()

UNIT = r"(?:mg/kg/h|mg/kg/j|mg/kg|µg/kg|μg/kg|mcg/kg|ui/kg|mg|µg|μg|mcg|g|ui|ml/kg|ml|l|h|min|j|jours?|heures?|%|mmhg|kg|mmol/l|g/l|g/dl|cm|mm|sa|ans?|mois)"
TOK_RE = re.compile(rf"(?:[<>≤≥]=?\s*)?\d+(?:[.,]\d+)?(?:\s*(?:-|à|–)\s*\d+(?:[.,]\d+)?)?\s*{UNIT}\b|[<>≤≥]\s*\d+(?:[.,]\d+)?", re.I)
NEG_RE = re.compile(r"pas d'antibioprophylaxie|contre-indiqu\w*|\bne pas\b|\bnon recommand\w*|\bpas de\b", re.I)
DOSE_RE = re.compile(rf"\d+(?:[.,]\d+)?\s*(?:mg/kg|mg|µg|μg|g|ui)\b", re.I)

def cell_tokens(t):
    t = norm(replace_math(t))
    toks = {re.sub(r"\s+", "", m.group(0)) for m in TOK_RE.finditer(t)}
    toks |= {m.group(0).lower() for m in NEG_RE.finditer(t)}
    return toks

def main(index_dir, out):
    docs = L.load_sfar_corpus(Path("data/sfar_recommendations/output"), updates_dir=Path("data/corpus_updates"), use_corpus_updates=True)
    con = sqlite3.connect(f"{index_dir}/metadata.sqlite")
    tab_text = collections.defaultdict(list)
    cards = collections.defaultdict(list)
    for doc_id, ctype, p in con.execute("select doc_id, chunk_type, payload_json from chunks"):
        if ctype in ("table_markdown", "table_row_card", "callout_allergy", "callout_footnote", "prose"):
            t = json.loads(p)["text"]
            if ctype != "prose":
                tab_text[doc_id].append(norm(t))
            if ctype == "table_row_card":
                cards[doc_id].append(norm(t))
    stats = collections.Counter(); lost_by_doc = collections.Counter(); rows_bad_by_doc = collections.Counter()
    examples = []
    tables_by_doc = collections.Counter()
    for d in docs:
        did = d.metadata.doc_id
        blob = " ".join(tab_text.get(did, []))
        blob_ns = re.sub(r"\s+", "", blob)
        for tm in re.finditer(r"<table\b.*?</table>", d.text, flags=re.S | re.I):
            tables_by_doc[did] += 1
            soup = BeautifulSoup(tm.group(0), "html.parser")
            stats["tables"] += 1
            for tr in soup.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
                for c in cells:
                    for tok in cell_tokens(c):
                        stats["tokens"] += 1
                        if re.sub(r"\s+", "", tok) not in blob_ns:
                            stats["lost"] += 1; lost_by_doc[did] += 1
                            if len(examples) < 400:
                                examples.append((did, "TOKEN", tok, c[:200]))
                # row check
                if len(cells) >= 2 and cells[0].strip() and len(tr.find_all(["td", "th"], recursive=False)) >= 2:
                    first = norm(re.sub(r"^[▪■•○◦\-–—]+\s*", "", cells[0]))
                    words = re.findall(r"[\wéèêàçùôîâ'-]+", first)[:4]
                    if len(words) < 2:
                        continue
                    key = " ".join(words)
                    doses = {re.sub(r"\s+", "", m.group(0).lower()) for c in cells[1:] for m in DOSE_RE.finditer(norm(replace_math(c)))}
                    if not doses:
                        continue
                    stats["rows_checked"] += 1
                    cand = [k for k in cards.get(did, []) if key in k]
                    if not cand:
                        stats["rows_no_card_with_key"] += 1
                        continue
                    if not any(all(x in re.sub(r"\s+", "", k) for x in doses) for k in cand):
                        stats["rows_dose_not_with_key"] += 1; rows_bad_by_doc[did] += 1
                        if len(examples) < 800:
                            examples.append((did, "ROW", key, " || ".join(cells)[:300]))
    with open(out, "w") as f:
        f.write(json.dumps(stats) + "\n")
        f.write("lost tokens by doc: " + json.dumps(lost_by_doc.most_common(40), ensure_ascii=False) + "\n")
        f.write("rows with dose not in the card of their key, by doc: " + json.dumps(rows_bad_by_doc.most_common(40), ensure_ascii=False) + "\n")
        for e in examples:
            f.write("\t".join(e) + "\n")
    print(index_dir, dict(stats), "docs with lost tokens", len(lost_by_doc), "docs with bad rows", len(rows_bad_by_doc))

if __name__ == "__main__":
    for idx in sys.argv[1:]:
        main(idx, f"reports/agents/R1_annexes/table_fidelity_{Path(idx).name}.txt")
