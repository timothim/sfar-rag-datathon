"""K2 — Chunks whose (text, chunk_type) changed between two indexes, outside the current
antibioprophylaxis guideline; count, and print a seeded random sample of N with the closest
chunk of the same document in the old index (for manual labelling better / same / worse).
Usage: sample_changed.py tas_v6 tas_v7b 30"""
import collections, difflib, json, random, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
ABP = "2026_RFE-antibioprophylaxie-2023_V3_1_pour-mise-sur-site-juillet-2026_642ad1"

def load(ix):
    con = sqlite3.connect(ROOT / "index" / ix / "metadata.sqlite")
    d = collections.defaultdict(list)
    for (p,) in con.execute("select payload_json from chunks order by idx"):
        c = json.loads(p); d[c["doc_id"]].append(c)
    return d

a, b, n = load(sys.argv[1]), load(sys.argv[2]), int(sys.argv[3])
changed = []
for doc, cs in b.items():
    if doc == ABP:
        continue
    old = collections.Counter((c["text"], c["chunk_type"]) for c in a.get(doc, []))
    for c in cs:
        k = (c["text"], c["chunk_type"])
        if old[k] > 0:
            old[k] -= 1
        else:
            changed.append(c)
text_changed = sum(1 for c in changed if c["text"] not in {x["text"] for x in a.get(c["doc_id"], [])})
print("changed chunks outside ABP:", len(changed), "of which text changed:", text_changed, "type only:", len(changed) - text_changed,
      "docs:", len({c["doc_id"] for c in changed}))
print("types:", collections.Counter((c["chunk_type"]) for c in changed))
random.seed(27)
for i, c in enumerate(random.sample(changed, n), 1):
    cands = a.get(c["doc_id"], [])
    best = max(cands, key=lambda x: difflib.SequenceMatcher(None, x["text"][:600], c["text"][:600]).quick_ratio()) if cands else None
    print(f"\n### {i} {c['chunk_id']}")
    if best:
        print(f"OLD {best['chunk_type']} grades={best['grade_levels'][:3]} path=…{best['section_path'][-70:]}\n    {' '.join(best['text'].split())[:500]}")
    print(f"NEW {c['chunk_type']} grades={c['grade_levels'][:3]} path=…{c['section_path'][-70:]}\n    {' '.join(c['text'].split())[:500]}")
