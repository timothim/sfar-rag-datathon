"""K1 — Retrieval-only probe on the frozen configuration (C10_context_notes on index/tas_v6).

Queries are built from the corpus itself, never from an evaluation file: the PICO question
("Question 2.4 : Chez les patients ...?") that precedes a numbered recommendation in the current
editions of the non-antibioprophylaxis guidelines. For each query we record, in the final
context, where the chunk holding the target statement ranks, whether argument text of the same
question ranks above it, whether the statement chunk also holds its grade, and how many
bibliography-like chunks enter the context. Retrieval only (no generator).

Run: HF_HUB_OFFLINE=1 scripts/with_gpu_lock.sh K1 .venv/bin/python reports/agents/K1_annexes/retrieval_probe.py
"""

from __future__ import annotations

import collections
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
OUT = Path(__file__).resolve().parent
IDX = ROOT / "index" / "tas_v6"

sys.path.insert(0, str(OUT))
from corpus_structure_audit import GRADE_ANY, REC_STMT_RE, biblio_hits, is_abp  # noqa: E402

QUESTION_RE = re.compile(
    r"(?m)^\W*(?:\*\*)?Question\s*[\d.]*\s*(?:\*\*)?\s*[:\-–]?\s*(?:\*\*)?\s*\*?\s*(.{40,400}?\?)"
)


def build_queries(seed: int = 7, per_doc: int = 2) -> list[dict]:
    con = sqlite3.connect(IDX / "metadata.sqlite")
    docs = {d: json.loads(p) for d, p in con.execute("select doc_id, payload_json from documents")}
    by_doc = collections.defaultdict(list)
    for p, in con.execute("select payload_json from chunks where is_reference_section=0 order by idx"):
        c = json.loads(p)
        if c["chunk_type"] in ("prose", "recommendation_box", "callout_footnote"):
            by_doc[c["doc_id"]].append(c)
    rng = random.Random(seed)
    queries = []
    for doc_id, cs in sorted(by_doc.items()):
        meta = docs[doc_id]
        if not (meta.get("is_latest_edition") and meta.get("is_active")) or is_abp(meta.get("title", ""), doc_id):
            continue
        cs.sort(key=lambda c: c["chunk_index"])
        flow = "\n".join(c["text"] for c in cs)
        cands = []
        for m in QUESTION_RE.finditer(flow):
            after = flow[m.end(): m.end() + 3000]
            st = REC_STMT_RE.search(after)
            if not st:
                continue
            nxt_q = QUESTION_RE.search(after)
            if nxt_q and nxt_q.start() < st.start():
                continue
            stmt_line = after[st.start(): st.start() + 160]
            q = re.sub(r"\((?:P|I|C|O)\)", "", m.group(1))
            q = re.sub(r"[*_]", "", q).strip()
            cands.append({"doc_id": doc_id, "query": q, "stmt_id": st.group(1), "stmt_probe": re.sub(r"[*_\s]+", " ", stmt_line[len(st.group(0)):][:70]).strip()})
        rng.shuffle(cands)
        queries.extend(cands[:per_doc])
    return queries


def main() -> None:
    from rag_sfar.evaluation.ablation import build_standard_ablation_configs
    from rag_sfar.retrieval.embedder import build_embedder
    from rag_sfar.retrieval.pipeline import SfarRagRetriever
    from rag_sfar.retrieval.reranker import build_reranker
    from rag_sfar.retrieval.vector_store import LocalVectorStore

    queries = build_queries()
    print(f"{len(queries)} queries from {len({q['doc_id'] for q in queries})} documents", flush=True)
    store = LocalVectorStore.load(IDX)
    embedder = build_embedder(
        provider=store.manifest["embedding_provider"], model_name=store.manifest["embedding_model"], index_dir=IDX
    )
    reranker = build_reranker("cross_encoder", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
    retriever = SfarRagRetriever(store=store, embedder=embedder, reranker=reranker)
    cfg = {c.name: c for c in build_standard_ablation_configs()}["C10_context_notes"]
    rows = []
    for q in queries:
        results, _, _ = retriever.retrieve(q["query"], config=cfg)
        norm = lambda s: re.sub(r"[*_\s]+", " ", s)
        stmt_rank = None
        stmt_has_grade = None
        stmt_type = None
        arg_above = 0
        same_doc_seen = 0
        for rank, r in enumerate(results, 1):
            c = r.chunk
            t = norm(c.text)
            if c.doc_id == q["doc_id"] and q["stmt_probe"][:50] in t:
                if stmt_rank is None:
                    stmt_rank = rank
                    stmt_type = c.chunk_type
                    pos = t.find(q["stmt_probe"][:50])
                    nxt = REC_STMT_RE.search(c.text, 0)
                    seg = t[pos: pos + 1500]
                    stmt_has_grade = bool(GRADE_ANY.search(seg[: (seg.find(" R", 60) if seg.find(" R", 60) > 0 else len(seg))]))
            elif c.doc_id == q["doc_id"] and stmt_rank is None and c.chunk_type == "prose" and not REC_STMT_RE.search(c.text):
                arg_above += 1
        n_bib = sum(1 for r in results if biblio_hits(r.chunk.text) >= 3)
        n_bib_dense = sum(
            1 for r in results
            if biblio_hits(r.chunk.text) >= 3 and biblio_hits(r.chunk.text) / max(1, len([x for x in r.chunk.text.splitlines() if x.strip()])) >= 0.5
        )
        rows.append({
            **q, "n_context": len(results), "stmt_rank": stmt_rank, "stmt_chunk_type": stmt_type,
            "stmt_chunk_has_grade": stmt_has_grade, "same_doc_argument_above_stmt": arg_above,
            "context_chunks_ge3_biblio_lines": n_bib, "context_chunks_mostly_biblio": n_bib_dense,
            "top1_doc": results[0].chunk.doc_id if results else None,
            "top1_type": results[0].chunk.chunk_type if results else None,
            "context": [(r.chunk.chunk_id, r.chunk.chunk_type) for r in results],
        })
    (OUT / "retrieval_probe.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    n = len(rows)
    found = [r for r in rows if r["stmt_rank"]]
    s = {
        "queries": n,
        "docs": len({r["doc_id"] for r in rows}),
        "stmt_in_context": len(found),
        "stmt_rank1": sum(1 for r in found if r["stmt_rank"] == 1),
        "stmt_rank_le3": sum(1 for r in found if r["stmt_rank"] <= 3),
        "stmt_chunk_type": dict(collections.Counter(r["stmt_chunk_type"] for r in found)),
        "stmt_chunk_without_grade": sum(1 for r in found if r["stmt_chunk_has_grade"] is False),
        "queries_with_argument_above_stmt": sum(1 for r in found if r["same_doc_argument_above_stmt"] > 0),
        "top1_is_same_doc_argument_prose": sum(1 for r in rows if r["top1_doc"] == r["doc_id"] and r["top1_type"] == "prose" and r["stmt_rank"] != 1),
        "top1_other_doc": sum(1 for r in rows if r["top1_doc"] != r["doc_id"]),
        "queries_with_ge1_chunk_ge3_biblio_lines": sum(1 for r in rows if r["context_chunks_ge3_biblio_lines"] > 0),
        "queries_with_ge1_mostly_biblio_chunk": sum(1 for r in rows if r["context_chunks_mostly_biblio"] > 0),
        "mean_context": sum(r["n_context"] for r in rows) / max(1, n),
    }
    (OUT / "retrieval_probe_summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--dry":
        qs = build_queries()
        print(len(qs), len({q["doc_id"] for q in qs}))
        for q in qs[:5]:
            print(q)
    else:
        main()
