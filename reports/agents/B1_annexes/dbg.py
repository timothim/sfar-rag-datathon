"""Debug a question: gold chunks, their ranks in each channel, and the final context."""
import sys, dataclasses
from pathlib import Path
from rag_sfar.evaluation.harness import load_retrievers, select_configs, tokens, _shingles, _column_shingles, COLUMN_SEP
from rag_sfar.evaluation.datasets import load_suite
from rag_sfar.config import Settings
sys.path.insert(0, str(Path(__file__).parent))
from b1eval import parse_variant

def grams(t):
    tt = tokens(t); return _shingles(tt) | _shingles(tt, 2)
def covers(frag, sh):
    q = _column_shingles(frag) if COLUMN_SEP in frag else _shingles(tokens(frag))
    return bool(q) and len(q & sh) / len(q) >= 0.5

suite, qids, variant = sys.argv[1], sys.argv[2].split(","), (sys.argv[3] if len(sys.argv) > 3 else "C9:")
r = load_retrievers(Path("index"), ["table_aware_sota"], "cross_encoder", Settings().reranker_model, index_map={"table_aware_sota": __import__("os").environ.get("B1IDX","tas_v3_errata")})["table_aware_sota"]
base = select_configs(__import__("os").environ.get("B1BASE","C9"))[0]
_, cfg = parse_variant(variant, base)
items = {i.id: i for i in load_suite(suite, "dev")}
st = r.store
for qid in qids:
    it = items[qid]; q = it.formatted_query()
    print("=" * 30, qid, it.tags); print(q)
    gold = {}
    frags = [(e.evidence_id, f) for e in it.evidence for f in e.fragments] or [("gp", g.quote) for g in it.gold_passages]
    gdocs = set(it.gold_doc_ids) or {g.doc_id for g in it.gold_passages}
    for idx, c in enumerate(st.chunks):
        if c.doc_id not in gdocs: continue
        sh = grams(c.text)
        for eid, f in frags:
            if covers(f, sh): gold.setdefault(eid, []).append(idx)
    an = __import__("rag_sfar.retrieval.router", fromlist=["x"]).analyze_query(q, use_lexicon=False)
    mask = st.build_filter_mask(exclude_references=True, prefer_french=True, latest_edition_only=True, exclude_abrogated=True)
    bm = [i for i, _ in st.bm25.search(q, top_k=500, allowed_mask=mask)]
    dn = [i for i, _ in st.dense_search(r.embedder.embed_query(q), top_k=500, allowed_mask=mask)]
    ret, an2, _ = r.retrieve(q, config=cfg)
    retids = [x.chunk.chunk_id for x in ret]
    for eid, idxs in gold.items():
        for i in idxs[:4]:
            c = st.chunks[i]
            ce = r.reranker.score_pairs(q, [c.indexed_text])[0]
            pos = retids.index(c.chunk_id) + 1 if c.chunk_id in retids else None
            print(f"  GOLD {eid[-14:]} idx={i} {c.chunk_type} pop={c.population_hint} bm25={bm.index(i)+1 if i in bm else '-'} dense={dn.index(i)+1 if i in dn else '-'} ce={ce:.3f} ctx={pos} | {c.section_path[-70:]} | {c.text[:110]!r}")
    missing = [e.evidence_id for e in it.evidence if e.evidence_id not in gold]
    if missing: print("  UNMAPPED", missing)
    print(f"  pop={an2.population} mods={an2.modifiers}")
    for k, x in enumerate(ret, 1):
        c = x.chunk
        print(f"   {k:2d} {x.rerank_score if x.rerank_score is not None else -1:.3f} {c.chunk_type[:12]:12s} {c.population_hint[:5]} {x.expansion_reason or '':14s} {c.section_path[-50:]!r} {c.text[:90]!r}")
