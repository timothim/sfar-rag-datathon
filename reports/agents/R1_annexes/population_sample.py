"""R1: reproducible sample of chunks for manual review of population labels (seed 7):
60 labelled chunks (20 per source: table / section / document) and 30 unlabelled ones,
at most 2 chunks per document, bibliography excluded."""
import json, random, sqlite3, collections
con = sqlite3.connect("index/tas_v4/metadata.sqlite")
rows = []
for did, ct, p in con.execute("select doc_id, chunk_type, payload_json from chunks where chunk_type!='references'"):
    ch = json.loads(p)
    rows.append(ch)
rng = random.Random(7)
rng.shuffle(rows)
def pick(pred, n):
    out, per = [], collections.Counter()
    for ch in rows:
        if pred(ch) and per[ch["doc_id"]] < 2:
            out.append(ch); per[ch["doc_id"]] += 1
            if len(out) == n: break
    return out
S = []
for src in ("table", "section", "document"):
    S += [("L", c) for c in pick(lambda c, s=src: c.get("population_source") == s, 20)]
S += [("U", c) for c in pick(lambda c: not c.get("populations"), 30)]
for i, (k, c) in enumerate(S, 1):
    print(f"#{i} [{k}] pops={c['populations']} src={c['population_source']} type={c['chunk_type']} doc={c['doc_id'][:60]}\n  title={c['doc_title'][:120]}\n  section={c['section_path'][-200:]}\n  text={c['text'][:420]!r}\n")
