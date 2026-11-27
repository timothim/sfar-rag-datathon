"""K1 — In-memory check (frozen code, nothing written to index/ or data/): how many tables receive
the column headers of an earlier, NON-contiguous table of the same major section (table_parser
`elif previous_headers` branch, which does not require contiguity). Wraps parse_html_table in this
process only to observe its inputs/outputs; the chunker output is not saved.

Run: .venv/bin/python -I reports/agents/K1_annexes/header_inheritance_check.py
"""
import collections, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
import rag_sfar.ingestion.chunker as ch
from rag_sfar.ingestion.loader import load_sfar_corpus, resolve_corpus_updates_dir

orig = ch.parse_html_table
log = []
cur = {"doc": None}
def wrapped(tok, previous_headers=None, previous_is_contiguous=False, carry_first_cell=None):
    t = orig(tok, previous_headers=previous_headers, previous_is_contiguous=previous_is_contiguous, carry_first_cell=carry_first_cell)
    log.append((cur["doc"], bool(previous_is_contiguous), bool(t.inherited_headers), len(t.headers), t.num_rows, list(t.headers)[:3]))
    return t
ch.parse_html_table = wrapped
corpus = ROOT / "data" / "sfar_recommendations" / "output"
docs = load_sfar_corpus(corpus, updates_dir=resolve_corpus_updates_dir(None) if False else ROOT / "data" / "corpus_updates")
cls_of = {m["doc_id"]: m["cls"] for m in json.loads((Path(__file__).parent / "doc_metrics.json").read_text())}
opts = ch.ChunkOptions()
for d in docs:
    cur["doc"] = d.metadata.doc_id
    ch._chunk_table_aware_sota(d, options=opts)
c = collections.Counter(); per_cls = collections.Counter(); docs_hit = set(); ex = []
seen = set()
for doc, contig, inh, nh, nr, hd in log:
    key = (doc, contig, inh, nh, nr, tuple(hd))
    c["parse_calls"] += 1
    if inh:
        c["inherited"] += 1
        if not contig:
            c["inherited_non_contiguous"] += 1
            per_cls[cls_of.get(doc, "?")] += 1
            docs_hit.add(doc)
            if len(ex) < 15:
                ex.append((doc[:60], nr, hd))
out = {**c, "docs_with_non_contiguous_inheritance": len(docs_hit), "by_class": dict(per_cls), "examples": ex,
       "note": "parse calls include the occasional re-parse of a table (carry undo), so counts are upper bounds"}
(Path(__file__).parent / "header_inheritance_check.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
