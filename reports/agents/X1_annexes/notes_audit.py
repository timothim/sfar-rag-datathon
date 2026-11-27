"""Audit of footnote / scope coverage for table row cards in index/tas_v6 under the frozen
`called_scope` note attachment: which call marks of a row stay without their note."""
import sqlite3, json, collections, re, sys, random
from rag_sfar.schemas import Chunk
from rag_sfar.retrieval.pipeline import SfarRagRetriever, _call_marks, _note_marks
class Shim:
    def __init__(self, chunks): self.by = {c.chunk_id: c for c in chunks}
    def get_chunk(self, cid): return self.by.get(cid)
con = sqlite3.connect("index/tas_v6/metadata.sqlite")
chunks = [Chunk.model_validate_json(r[0]) for r in con.execute("select payload_json from chunks order by idx")]
store = Shim(chunks)
R = SfarRagRetriever.__new__(SfarRagRetriever); R.store = store
stats = collections.Counter(); per_doc = collections.Counter(); miss = []
for c in chunks:
    if c.chunk_type != "table_row_card" or not c.is_latest_edition or not c.is_active: continue
    # calls in the cell line only (the card may embed its notes as "Note ..." lines)
    lines = c.text.splitlines()
    cell = "\n".join(l for l in lines if not l.startswith(("Note", "Périmètre", "Section", "Tableau", "Sous-catégorie")))
    calls = _call_marks(cell)
    if not calls: continue
    stats["rows_with_calls"] += 1
    embedded = set()
    for l in lines:
        if l.startswith("Note"):
            m = re.match(r"Note\s*\(([^)]*)\)", l)
            embedded |= set(re.findall(r"\*{1,4}|#|†|‡", m.group(1))) if m else _note_marks(l.split(":", 1)[-1].strip()) or {"?"}
    notes = R._called_notes(c, 1200, True)
    attached = set().union(*[_note_marks(n.text) for n in notes]) if notes else set()
    missing = {m for m in calls if m not in embedded and m not in attached}
    if "?" in embedded: missing = set()  # an unlabeled embedded note: cannot tell, count as covered
    stats["embedded_any"] += bool(embedded)
    if missing:
        stats["rows_missing"] += 1; per_doc[c.doc_id] += 1; miss.append((c, missing))
print(dict(stats)); print(per_doc.most_common(20))
random.seed(0)
for c, m in random.sample(miss, min(12, len(miss))):
    print("====", c.chunk_id, m); print(c.text[:600])

# --- classify the missing marks
import unicodedata
def norm_note_marks(text):
    out = set()
    for line in text.replace("\\", "").splitlines():
        s = line.strip()
        s2 = re.sub(r"^[_*](?=[*#†‡])", "", s) if s[:1] in "_*" else s   # italic wrapper "*\*note*"
        for cand in (s, s2):
            m = re.match(r"^(\*{1,4}|#|†|‡)(?![\*#])", cand)
            if m: out.add(m.group(1))
    return out
by_doc = collections.defaultdict(list)
for c in chunks: by_doc[c.doc_id].append(c)
cls = collections.Counter(); dist = collections.Counter(); examples = collections.defaultdict(list)
for c, missing in miss:
    L = by_doc[c.doc_id]; i = next(k for k, x in enumerate(L) if x.chunk_id == c.chunk_id)
    for m in missing:
        found = None; crossed = False
        for k in range(i + 1, min(len(L), i + 40)):
            x = L[k]
            if x.is_reference_section or x.chunk_type == "references": continue
            if x.chunk_type == "table_markdown" and x.table_id != c.table_id: crossed = True
            if x.chunk_type in ("table_row_card",) : continue
            if m in norm_note_marks(x.text):
                found = (k - i, x); break
        if not found: cls["no_note_after"] += 1; examples["no_note_after"].append((c, m)); continue
        d, x = found
        key = ("crossed_table" if crossed else "same_table") + ("_startmark" if m in _note_marks(x.text) else "_italic_or_inner")
        cls[key] += 1; dist[min(d, 20)] += 1; examples[key].append((c, m, x))
print(cls); print(sorted(dist.items()))
for k, v in examples.items():
    print("#####", k)
    for e in v[:4]:
        print("  ROW:", e[0].chunk_id[-30:], e[1], e[0].text.splitlines()[-1][:150])
        if len(e) > 2: print("  NOTE:", e[2].chunk_type, e[2].text[:150].replace("\n", " // "))
