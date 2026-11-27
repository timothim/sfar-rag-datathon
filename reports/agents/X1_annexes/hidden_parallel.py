"""Look for parallel tables outside population labels: same doc, different tables, identical
normalised first-cell label (>= 2 content words). Shows whether a population (or other) contrast
separates them, to check that the counterpart structure is not hidden by missing labels."""
import sqlite3, json, collections, re, sys
sys.path.insert(0, "reports/agents/X1_annexes")
from proto_utils import fold, label
c = sqlite3.connect('index/tas_v6/metadata.sqlite')
rows = [json.loads(r[0]) for r in c.execute("select payload_json from chunks where chunk_type='table_row_card' order by idx")]
by = collections.defaultdict(list)
for p in rows:
    if not (p.get("is_latest_edition") and p.get("is_active")): continue
    h, v = label(p["text"])
    if not v: continue
    fv = fold(v)
    if len([w for w in fv.split() if len(w) >= 4]) < 2: continue
    by[(p["doc_id"], fv)].append(p)
docs = collections.Counter()
ex = []
for (d, fv), L in by.items():
    tids = {p["table_id"] for p in L}
    if len(tids) < 2: continue
    # only keep pairs whose row text differs (otherwise duplicate cards)
    texts = {re.sub(r"\W+", " ", p["text"].split("\n")[-1]) for p in L}
    if len(texts) < 2: continue
    docs[d] += 1
    ex.append((d, fv, [(p["table_id"][-4:], ",".join(p.get("populations") or []), p["section_path"][-70:]) for p in L][:3]))
print(len(docs)); 
for d, n in docs.most_common(): print(n, d)
import random; random.seed(0)
for e in random.sample(ex, min(30, len(ex))): print(e)
