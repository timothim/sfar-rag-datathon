"""K2 — Compare the chunks of two indexes (or of an index and the chunker in memory with the K2
switches from the environment), per document: identical / changed / added / removed, matched on
(text, chunk_type, section_path) multiset, then by order. Prints counts; with --doc, lists the
changed chunks of that document (ids, type, first 40 words at most)."""
import argparse, collections, json, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

def load_index(d):
    con = sqlite3.connect(ROOT / d / "metadata.sqlite")
    out = collections.defaultdict(list)
    for (p,) in con.execute("select payload_json from chunks order by idx"):
        c = json.loads(p); out[c["doc_id"]].append(c)
    return out

def load_memory():
    from rag_sfar.ingestion.loader import load_sfar_corpus
    from rag_sfar.ingestion.chunker import ChunkOptions, chunk_corpus
    docs = load_sfar_corpus(ROOT / "data/sfar_recommendations/output", updates_dir=ROOT / "data/corpus_updates")
    out = collections.defaultdict(list)
    for c in chunk_corpus(docs, options=ChunkOptions()):
        out[c.doc_id].append(json.loads(c.model_dump_json()))
    return out

def key(c): return (c["text"], c["chunk_type"])

def words(t, n=40): return " ".join(t.split()[:n])

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--a", default="index/tas_v6"); ap.add_argument("--b", default="memory")
    ap.add_argument("--doc", action="append", default=[]); ap.add_argument("--json")
    a = ap.parse_args()
    A = load_index(a.a); B = load_memory() if a.b == "memory" else load_index(a.b)
    tot = collections.Counter(); per = {}
    for doc in sorted(set(A) | set(B)):
        ca = collections.Counter(key(c) for c in A.get(doc, [])); cb = collections.Counter(key(c) for c in B.get(doc, []))
        same = sum((ca & cb).values()); only_a = ca - cb; only_b = cb - ca
        # text identical, type changed
        ta = collections.Counter(t for t, _ in only_a.elements()); tb = collections.Counter(t for t, _ in only_b.elements())
        retyped = sum((ta & tb).values())
        r = {"identical": same, "retyped": retyped, "removed": sum(only_a.values()) - retyped, "added": sum(only_b.values()) - retyped,
             "section_path_changed": sum(1 for x, y in zip(A.get(doc, []), B.get(doc, [])) if key(x) == key(y) and x["section_path"] != y["section_path"]),
             "is_ref_changed": sum(1 for x, y in zip(A.get(doc, []), B.get(doc, [])) if key(x) == key(y) and x["is_reference_section"] != y["is_reference_section"])}
        per[doc] = r; tot.update(r)
        if doc in a.doc or any(s in doc for s in a.doc):
            print("==", doc, r)
            for t, ty in only_a.elements(): print("  - ", ty, "|", words(t))
            for t, ty in only_b.elements():
                cid = next(c["chunk_id"] for c in B[doc] if key(c) == (t, ty)); print("  + ", cid, ty, "|", words(t))
    print("TOTAL", dict(tot), "docs touched", sum(1 for r in per.values() if r["retyped"] or r["removed"] or r["added"] or r["section_path_changed"]))
    if a.json: Path(a.json).write_text(json.dumps({"total": dict(tot), "per_doc": per}, indent=0))
