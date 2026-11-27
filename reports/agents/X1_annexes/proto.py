import sqlite3, json, collections, re, unicodedata, sys
c = sqlite3.connect('index/tas_v6/metadata.sqlite')
rows = [json.loads(r[0]) for r in c.execute("select payload_json from chunks where chunk_type='table_row_card' order by idx")]
CTX = ("Tableau :", "Section :", "Sous-catégorie :", "Périmètre :", "Note")
def cell_line(t):
    for l in t.splitlines():
        if " | " in l and not l.startswith(CTX): return l
    return ""
def fold(s):
    s = unicodedata.normalize("NFKD", s); s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("\\", "")
    s = re.sub(r"[*#†‡]", " ", s); s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())
def label(t):
    cell = cell_line(t).split(" | ")[0]
    h, sep, v = cell.partition(" : ")
    if not sep: return None, None
    return fold(h.split(" / ")[0]), v
def pclass(p):
    s = set(p.get("populations") or [])
    if p.get("population_source") not in ("section", "table", "document"): return None
    if s == {"adulte"}: return "adulte"
    if s == {"pediatrie"}: return "pediatrie"
    if s == {"neonatal", "pediatrie"} or s == {"neonatal"}: return "neonatal"
    if s in ({"obstetrique"}, {"adulte", "obstetrique"}): return "obstetrique"
    return None
by_doc = collections.defaultdict(list)
for p in rows:
    if not (p.get("is_latest_edition") and p.get("is_active")): continue
    pc = pclass(p)
    h, v = label(p["text"])
    if not pc or not v: continue
    items = [fold(x) for x in re.split(r";", v)]
    items = [x for x in items if len(x) >= 6 and any(len(w) >= 4 and not w.isdigit() for w in x.split())]
    if not items: continue
    by_doc[p["doc_id"]].append((p, pc, h, fold(v), set(items)))
mode = sys.argv[1] if len(sys.argv) > 1 else "item"
links = []
for doc, L in by_doc.items():
    for a in L:
        for b in L:
            if a is b or a[1] == b[1] or a[0]["table_id"] == b[0]["table_id"]: continue
            if mode == "exact": ok = a[3] == b[3]
            else: ok = bool(a[4] & b[4])
            if ok: links.append((doc, a, b))
print(len(links), collections.Counter(d for d, *_ in links))
cnt = collections.Counter((a[0]["chunk_id"], b[1]) for d, a, b in links)
print("fanout dist", collections.Counter(cnt.values()))
import random; random.seed(1)
for d, a, b in random.sample(links, min(40, len(links))):
    print(a[1], '->', b[1], '|', a[3][:80], '||', b[3][:80])
