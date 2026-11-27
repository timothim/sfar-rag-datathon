"""K2 — Snapshot of the chunker output (hash per document) with the current code, for the
byte-identity test with all K2 switches off. Writes no text, only hashes."""
import hashlib, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from rag_sfar.ingestion.loader import load_sfar_corpus
from rag_sfar.ingestion.chunker import ChunkOptions, chunk_corpus

def doc_hashes(chunks):
    out = {}
    for c in chunks:
        h = out.setdefault(c.doc_id, hashlib.sha256())
        h.update(c.model_dump_json().encode())
    return {k: v.hexdigest() for k, v in out.items()}

if __name__ == "__main__":
    t = time.time()
    docs = load_sfar_corpus(ROOT / "data/sfar_recommendations/output", updates_dir=ROOT / "data/corpus_updates")
    print("load", time.time() - t, len(docs))
    t = time.time()
    ch = chunk_corpus(docs, options=ChunkOptions())
    print("chunk", time.time() - t, len(ch))
    Path(sys.argv[1]).write_text(json.dumps(doc_hashes(ch), indent=0, sort_keys=True))
