"""R1: list every page-split carry (carried_first_cell) with the carried key and the first data row
of the new fragment, for manual review (CPU only)."""
import re, random
from pathlib import Path
from rag_sfar.ingestion import loader as L, chunker as C, table_parser as T
from rag_sfar.ingestion.text_cleaning import NulRepairer
docs = L.load_sfar_corpus(Path("data/sfar_recommendations/output"), updates_dir=Path("data/corpus_updates"), use_corpus_updates=True)
cur = {}
out = []
orig = T.parse_html_table
def parse(tok, **kw):
    p = orig(tok, **kw)
    if p.carried_first_cell and p.row_groups:
        r = p.row_groups[0].rows[0]
        out.append((cur["d"], p.headers[:3], p.carried_first_cell[:80], " || ".join(x[:50] for x in r[1:4])))
    return p
C.parse_html_table = parse
rep = NulRepairer([d.text for d in docs])
for d in docs:
    cur["d"] = d.metadata.doc_id[:50]
    C._chunk_table_aware_sota(d, options=C.ChunkOptions(), nul_repairer=rep)
random.Random(3).shuffle(out)
for o in out[:40]: print(o)
print(len(out))
