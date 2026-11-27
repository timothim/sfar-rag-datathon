"""Multi-query retrieval wrapper (agent X2): off = frozen output, strict parsers, budgeted merge.

All queries are synthetic, written for these tests (not taken from an evaluation set)."""

from __future__ import annotations

import dataclasses

import pytest

from rag_sfar.evaluation.ablation import build_standard_ablation_configs
from rag_sfar.retrieval.bm25 import BM25Index
from rag_sfar.retrieval.multi_query import (
    CORRECT_SYSTEM,
    DECOMPOSE_SYSTEM,
    FormatError,
    MultiQueryConfig,
    MultiQueryRetriever,
    correct_prompt,
    decompose_prompt,
    merge_results,
    parse_correction,
    parse_decomposition,
    split_clauses,
    wrap_retriever,
)
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.vector_store import LocalVectorStore
from rag_sfar.schemas import Chunk, DocumentMetadata, RetrievedChunk


def _chunks() -> list[Chunk]:
    topics = ["gestion du traitement chronique", "technique d'anesthésie", "surveillance postopératoire",
              "seuil biologique", "délai d'arrêt avant le geste"]
    out = []
    for d in range(3):
        prev = None
        for i in range(10):
            cid = f"d{d}_c{i}"
            text = f"Document {d}, passage {i} : {topics[(i + d) % 5]} chez l'adulte, recommandation {i}."
            out.append(Chunk(chunk_id=cid, doc_id=f"d{d}", chunk_index=i, text=text, indexed_text=text,
                             doc_title=f"Recommandation {d}", effective_year=2024, is_latest_edition=True,
                             prev_chunk_id=prev, section_path=f"Chapitre {i // 3}"))
            prev = cid
    for a, b in zip(out, out[1:]):
        if a.doc_id == b.doc_id:
            a.next_chunk_id = b.chunk_id
    return out


def _retriever() -> SfarRagRetriever:
    chunks = _chunks()
    docs = [DocumentMetadata(doc_id=f"d{d}", title=f"Recommandation {d}", filename=f"d{d}.pdf", md_path=f"d{d}.md",
                             effective_year=2024) for d in range(3)]
    store = LocalVectorStore(chunks=chunks, documents=docs, embeddings=None,
                             bm25=BM25Index().build([c.indexed_text for c in chunks]))
    return SfarRagRetriever(store=store)


def _frozen_cfg():
    cfg = next(c for c in build_standard_ablation_configs() if c.name == "C10_context_notes")
    # no models in the unit test: same configuration without the dense channel and reranker
    return dataclasses.replace(cfg, use_dense=False, use_reranker=False)


QUERIES = [
    "Quel délai d'arrêt du traitement chronique avant le geste chez l'adulte ?",
    "Quelle technique d'anesthésie et quelle surveillance postopératoire ?",
    "seuil biologique",
]


def test_off_returns_exactly_the_frozen_chunks(monkeypatch):
    base = _retriever()
    cfg = _frozen_cfg()
    monkeypatch.delenv("RAG_SFAR_MULTI_QUERY", raising=False)
    assert wrap_retriever(base) is base  # default: not wrapped at all
    wrapped = MultiQueryRetriever(base, MultiQueryConfig(mode="off"))
    for q in QUERIES:
        a, _, _ = base.retrieve(q, config=cfg)
        b, _, _ = wrapped.retrieve(q, config=cfg)
        assert [r.chunk.chunk_id for r in a] == [r.chunk.chunk_id for r in b]
        assert [r.final_score for r in a] == [r.final_score for r in b]


def test_llm_modes_fall_back_to_frozen_output_when_single_or_malformed():
    base = _retriever()
    cfg = _frozen_cfg()
    for mode, answers in (("decompose", ["SIMPLE", "bla", "MULTIPLE\n1. une seule sous-question ici"]),
                          ("llm_correct", ["COMPLET", "INCOMPLET", "Je pense que c'est complet"])):
        for ans in answers:
            mq = MultiQueryRetriever(base, MultiQueryConfig(mode=mode), responder=lambda s, u, a=ans: a)
            for q in QUERIES:
                a, _, _ = base.retrieve(q, config=cfg)
                b, _, _ = mq.retrieve(q, config=cfg)
                assert [r.chunk.chunk_id for r in a] == [r.chunk.chunk_id for r in b], (mode, ans)
                assert not mq.last_trace.fired


def test_responder_failure_falls_back():
    def boom(s, u):
        raise RuntimeError("model down")

    base = _retriever()
    mq = MultiQueryRetriever(base, MultiQueryConfig(mode="decompose"), responder=boom)
    a, _, _ = base.retrieve(QUERIES[0], config=_frozen_cfg())
    b, _, _ = mq.retrieve(QUERIES[0], config=_frozen_cfg())
    assert [r.chunk.chunk_id for r in a] == [r.chunk.chunk_id for r in b]
    assert "responder error" in mq.last_trace.format_error


def test_decomposition_adds_subquery_passages_within_budget():
    base = _retriever()
    cfg = _frozen_cfg()
    ans = "MULTIPLE\n1. Quel seuil biologique chez l'adulte ?\n2. Quelle surveillance postopératoire chez l'adulte ?"
    mq = MultiQueryRetriever(base, MultiQueryConfig(mode="decompose", max_chars=2000, max_chunks=12),
                             responder=lambda s, u: ans)
    out, _, timings = mq.retrieve(QUERIES[0], config=cfg)
    assert mq.last_trace.fired and len(mq.last_trace.extra_queries) == 2
    assert len(out) <= 12 and sum(len(r.chunk.text) for r in out) <= 2000
    assert len({r.chunk.chunk_id for r in out}) == len(out)
    assert any((r.expansion_reason or "").startswith("multi_query:sub1") for r in out)
    assert any((r.expansion_reason or "").startswith("multi_query:sub2") for r in out)
    assert timings["multi_query_n"] == 2.0


def test_parsers_are_strict():
    assert parse_decomposition(" SIMPLE \n") == []
    assert parse_decomposition("MULTIPLE\n1. Première sous-question ?\n2. Deuxième sous-question ?") == [
        "Première sous-question ?", "Deuxième sous-question ?"]
    for bad in ("", "Simple, une seule recherche", "MULTIPLE\n1. seule sous-question",
                "MULTIPLE\n2. sous-question numéro deux\n1. sous-question numéro un",
                "MULTIPLE\n1. a1 sous-question\n2. a2 sous-question\n3. a3 sous-question\n4. a4 sous-question",
                "SIMPLE\nparce que"):
        with pytest.raises(FormatError):
            parse_decomposition(bad)
    assert parse_correction("COMPLET") == []
    assert parse_correction("INCOMPLET\nREQUÊTE: délai d'arrêt du traitement") == ["délai d'arrêt du traitement"]
    for bad in ("INCOMPLET", "INCOMPLET\nrecherche: x y z w v", "COMPLET\nok",
                "INCOMPLET\nREQUETE: une requête a\nREQUETE: une requête b\nREQUETE: une requête c"):
        with pytest.raises(FormatError):
            parse_correction(bad)


def test_prompts_are_domain_neutral_and_contain_the_question():
    q = "Question synthétique sur un sujet quelconque ?"
    s, u = decompose_prompt(q)
    assert s == DECOMPOSE_SYSTEM and q in u
    s, u = correct_prompt(q, [])
    assert s == CORRECT_SYSTEM and q in u
    import re

    # no drug-like INN stems, no recommendation numbers in the fixed prompts
    for text in (DECOMPOSE_SYSTEM, CORRECT_SYSTEM):
        assert not re.search(r"\bR\d+\.\d", text)
        assert not re.search(r"\w+(?:cilline|mycine|xaban|gatran|parine|curonium|caïne|azolam)\b", text, re.I)


def test_split_clauses_uses_grammar_only():
    q = "Chez une patiente sous traitement chronique qui doit avoir un geste programmé, quand arrêter le traitement ?"
    cl = split_clauses(q)
    assert len(cl) >= 2
    assert split_clauses("Quel seuil biologique ?") == ["Quel seuil biologique"]
    # MCQ options are not clauses
    assert all("A." not in c for c in split_clauses("Quelle proposition est exacte ?\nA. un\nB. deux"))


def _rc(cid: str, n: int, expanded: bool = False) -> RetrievedChunk:
    c = Chunk(chunk_id=cid, doc_id="d", chunk_index=0, text=cid.ljust(n, "x"), indexed_text=cid)
    return RetrievedChunk(chunk=c, final_score=1.0, is_expanded_context=expanded)


def test_merge_guarantees_a_share_to_each_source_and_respects_budget():
    main = [_rc(f"m{i}", 100) for i in range(30)]
    sub = [_rc(f"s{i}", 100) for i in range(5)]
    out = merge_results([main, sub], share=2, max_chars=1000, max_chunks=40, labels=["main", "sub1"])
    ids = [r.chunk.chunk_id for r in out]
    assert ids[:4] == ["m0", "s0", "m1", "s1"]
    assert sum(len(r.chunk.text) for r in out) <= 1000 and len(out) == 10
    # window items stay with their anchor; duplicates are skipped
    main = [_rc("a", 50), _rc("a_win", 50, True), _rc("b", 50)]
    sub = [_rc("a", 50), _rc("c", 50)]
    ids = [r.chunk.chunk_id for r in merge_results([main, sub], 2, 10_000, 40, ["main", "sub1"])]
    assert ids == ["a", "a_win", "b", "c"]
