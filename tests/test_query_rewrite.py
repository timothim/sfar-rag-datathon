"""Query rewriting wrapper (agent Q2): off = frozen output, fallbacks, strict parser, add-merge
guarantee, MCQ options hidden from the model.

All queries are synthetic, written for these tests (not taken from an evaluation set)."""

from __future__ import annotations

import dataclasses
import re

import pytest

from rag_sfar.evaluation.ablation import build_standard_ablation_configs
from rag_sfar.retrieval.bm25 import BM25Index
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.query_rewrite import (
    SYSTEMS,
    FormatError,
    QueryRewriteConfig,
    QueryRewriteRetriever,
    guard_violations,
    merge_add,
    parse_rewrite,
    rewrite_prompt,
    same_text,
    split_options,
    wrap_retriever,
)
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
    "Quelle proposition est exacte ?\nA. seuil biologique\nB. technique d'anesthésie",
]


def _ids(items):
    return [r.chunk.chunk_id for r in items]


def test_off_returns_exactly_the_frozen_chunks(monkeypatch):
    base = _retriever()
    cfg = _frozen_cfg()
    monkeypatch.delenv("RAG_SFAR_QUERY_REWRITE", raising=False)
    monkeypatch.delenv("RAG_SFAR_QUERY_REWRITE_USE", raising=False)
    assert wrap_retriever(base) is base  # default: not wrapped at all
    wrapped = QueryRewriteRetriever(base, QueryRewriteConfig(variant="off"))
    for q in QUERIES:
        a, _, _ = base.retrieve(q, config=cfg)
        b, _, _ = wrapped.retrieve(q, config=cfg)
        assert _ids(a) == _ids(b)
        assert [r.final_score for r in a] == [r.final_score for r in b]


def test_env_switch(monkeypatch):
    base = _retriever()
    monkeypatch.setenv("RAG_SFAR_QUERY_REWRITE", "normalize")
    monkeypatch.setenv("RAG_SFAR_QUERY_REWRITE_USE", "replace")
    with pytest.raises(ValueError):
        wrap_retriever(base)  # an enabled variant without a model is an error, not a silent no-op

    class FakeLLM:
        def complete(self, system, user, temperature=None, max_tokens=None):
            return "INCHANGEE", {}

    w = wrap_retriever(base, llm=FakeLLM())
    assert isinstance(w, QueryRewriteRetriever)
    assert w.config.variant == "normalize" and w.config.use == "replace"
    monkeypatch.setenv("RAG_SFAR_QUERY_REWRITE", "bogus")
    with pytest.raises(ValueError):
        wrap_retriever(base, llm=FakeLLM())


@pytest.mark.parametrize("use", ["replace", "add"])
def test_unchanged_malformed_or_identical_rewrites_give_the_frozen_output(use):
    base = _retriever()
    cfg = _frozen_cfg()
    cases = [("normalize", "INCHANGEE"), ("normalize", "bla bla"), ("normalize", "NORMALISEE:"),
             ("normalize", "NORMALISEE: a\nb"), ("reformulate", "INCHANGEE"), ("hyde", "")]
    for variant, ans in cases:
        r = QueryRewriteRetriever(base, QueryRewriteConfig(variant=variant, use=use), responder=lambda s, u, a=ans: a)
        for q in QUERIES:
            a, _, _ = base.retrieve(q, config=cfg)
            b, _, _ = r.retrieve(q, config=cfg)
            assert _ids(a) == _ids(b), (variant, ans)
            assert not r.last_trace.used
    # a "rewrite" equal to the question up to case, accents and punctuation is not used
    for q in QUERIES:
        stem, _ = split_options(q)
        r = QueryRewriteRetriever(base, QueryRewriteConfig(variant="normalize", use=use),
                                  responder=lambda s, u, t=stem: "NORMALISEE: " + t.upper().rstrip(" ?") + " !")
        assert _ids(base.retrieve(q, config=cfg)[0]) == _ids(r.retrieve(q, config=cfg)[0])
        assert not r.last_trace.used


def test_responder_failure_falls_back():
    def boom(s, u):
        raise RuntimeError("model down")

    base = _retriever()
    r = QueryRewriteRetriever(base, QueryRewriteConfig(variant="normalize", use="replace"), responder=boom)
    a, _, _ = base.retrieve(QUERIES[0], config=_frozen_cfg())
    b, _, _ = r.retrieve(QUERIES[0], config=_frozen_cfg())
    assert _ids(a) == _ids(b)
    assert "responder error" in r.last_trace.format_error


def test_model_sees_the_stem_only_and_options_are_appended_verbatim():
    base = _retriever()
    seen: list[str] = []
    calls: list[str] = []

    class Spy:
        def retrieve(self, query, **kw):
            calls.append(query)
            return base.retrieve(query, **kw)

    def responder(s, u):
        seen.append(u)
        return "NORMALISEE: Quelle proposition est exacte concernant le seuil ?"

    r = QueryRewriteRetriever(Spy(), QueryRewriteConfig(variant="normalize", use="replace"), responder=responder)
    r.retrieve(QUERIES[3], config=_frozen_cfg())
    assert "A." not in seen[0] and "B." not in seen[0]
    assert calls == ["Quelle proposition est exacte concernant le seuil ?\nA. seuil biologique\nB. technique d'anesthésie"]


def test_add_keeps_every_frozen_chunk_in_place_and_respects_budget():
    base = _retriever()
    cfg = _frozen_cfg()
    r = QueryRewriteRetriever(base, QueryRewriteConfig(variant="normalize", use="add", max_chars=4000, max_chunks=30),
                              responder=lambda s, u: "NORMALISEE: surveillance postopératoire et seuil biologique")
    for q in QUERIES[:3]:
        a, _, _ = base.retrieve(q, config=cfg)
        b, _, _ = r.retrieve(q, config=cfg)
        assert _ids(b)[: len(a)] == _ids(a)  # frozen context first, unchanged
        assert len(set(_ids(b))) == len(b)
        assert len(b) <= max(30, len(a))
        assert sum(len(x.chunk.text) for x in b) <= max(4000, sum(len(x.chunk.text) for x in a))
        assert r.last_trace.used and r.last_trace.n_added == len(b) - len(a)
        assert all((x.expansion_reason or "").startswith("query_rewrite:") for x in b[len(a):])


def _rc(cid: str, n: int, expanded: bool = False) -> RetrievedChunk:
    c = Chunk(chunk_id=cid, doc_id="d", chunk_index=0, text=cid.ljust(n, "x"), indexed_text=cid)
    return RetrievedChunk(chunk=c, final_score=1.0, is_expanded_context=expanded)


def test_merge_add_superset_order_budget():
    orig = [_rc("a", 100), _rc("a_w", 100, True), _rc("b", 100)]
    new = [_rc("c", 100), _rc("c_w", 100, True), _rc("a", 100), _rc("d", 300), _rc("e", 50)]
    out = [r.chunk.chunk_id for r in merge_add(orig, new, max_chars=600, max_chunks=10)]
    assert out == ["a", "a_w", "b", "c", "c_w", "e"]  # d does not fit, e does; a not duplicated
    # chunk cap
    assert [r.chunk.chunk_id for r in merge_add(orig, new, 10_000, 4)] == ["a", "a_w", "b", "c"]
    # the frozen context is never cut, even above the budget
    assert [r.chunk.chunk_id for r in merge_add(orig, new, 50, 2)] == ["a", "a_w", "b"]


def test_parser_is_strict():
    assert parse_rewrite("normalize", " INCHANGEE ") is None
    assert parse_rewrite("normalize", "INCHANGÉE") is None
    assert parse_rewrite("normalize", "NORMALISÉE: Quelle conduite à tenir ?") == "Quelle conduite à tenir ?"
    assert parse_rewrite("reformulate", "REFORMULEE: Quelle conduite à tenir ?") == "Quelle conduite à tenir ?"
    assert parse_rewrite("hyde", "PASSAGE: Chez l'adulte, il est recommandé de surveiller.").startswith("Chez")
    for variant, bad in (("normalize", ""), ("normalize", "Voici la question : x y z"),
                         ("normalize", "NORMALISEE: deux\nlignes ici"), ("reformulate", "INCHANGEE"),
                         ("reformulate", "NORMALISEE: question réécrite"), ("hyde", "REFORMULEE: une question ici"),
                         ("hyde", "PASSAGE: court")):
        with pytest.raises(FormatError):
            parse_rewrite(variant, bad)


def test_guard_and_same_text():
    assert guard_violations("Enfant de 3 ans sans antécédent", "Enfant de 3 ans sans antécédent") == []
    v = guard_violations("Enfant de 3 ans sans antécédent", "Patient avec antécédent")
    assert any("number lost" in x for x in v) and any("negation lost" in x for x in v)
    assert any("population lost" in x for x in v)
    assert any("number added" in x for x in guard_violations("Quelle dose ?", "Quelle dose de 2 g ?"))
    assert same_text("Quelle conduite ?", "quelle  conduite")
    assert not same_text("Quelle conduite ?", "Quelle conduite à tenir ?")


def test_prompts_are_domain_neutral_and_contain_the_question():
    q = "Question synthétique sur un sujet quelconque ?"
    for variant, system in SYSTEMS.items():
        s, u = rewrite_prompt(variant, q)
        assert s == system and q in u
        # no example question, no digits, no drug-like INN stems, no recommendation numbers
        assert not re.search(r"\d", s)
        assert not re.search(r"\bR\d+\.\d", s)
        assert not re.search(r"\w+(?:cilline|mycine|xaban|gatran|parine|curonium|caïne|azolam|zoline)\b", s, re.I)
