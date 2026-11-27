"""Structural links followed after retrieval (`rag_sfar.retrieval.links`, sidecar built by
`scripts/build_chunk_links.py`). Synthetic chunks only: no evaluation text here (principle 3)."""

from __future__ import annotations

import gzip
import json
import os
import sys
from pathlib import Path

import pytest

from rag_sfar.config import RetrievalConfig
from rag_sfar.retrieval.links import ChunkLinks, LinkedRetriever, LinkPolicy, apply_links
from rag_sfar.schemas import Chunk, QueryAnalysis, RetrievedChunk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_chunk_links as bcl  # noqa: E402

HDR = "Actes"


def card(cid: str, idx: int, table: str, pops: list[str], label: str, dose: str, doc: str = "D",
         source: str = "section") -> Chunk:
    return Chunk(
        chunk_id=f"{doc}__{cid}", doc_id=doc, chunk_index=idx, chunk_type="table_row_card",
        text=f"Section : S\n{HDR} : {label} | Molécule : M | Dose : {dose}", indexed_text="x",
        doc_title="T", doc_type="RFE", effective_year=2026, populations=pops, population_source=source,
        table_id=f"{doc}__{table}",
    )


class Store:
    def __init__(self, chunks):
        self.by = {c.chunk_id: c for c in chunks}

    def get_chunk(self, cid):
        return self.by.get(cid)


ADULT = card("a1", 1, "t1", ["adulte"], "Résection alphaxyl; Plastie betazor", "2 g")
ADULT_OTHER = card("a2", 2, "t1", ["adulte"], "Ablation gammaplex", "1 g")
CHILD = card("p1", 10, "t2", ["pediatrie"], "Résection alphaxyl; Plastie betazor; Exérèse deltaron", "30 mg/kg")
CHILD_OTHER = card("p2", 11, "t2", ["pediatrie"], "Ablation gammaplex étendue", "50 mg/kg")
NEO = card("n1", 20, "t3", ["neonatal", "pediatrie"], "Résection alphaxyl; Plastie betazor", "20 mg/kg")
ALL = [ADULT, ADULT_OTHER, CHILD, CHILD_OTHER, NEO]


def test_builder_links_only_rows_whose_acts_are_all_covered():
    links, stats = bcl.build_counterparts(ALL, max_per_pop=2)
    adult = {l["target"]: l for l in links[ADULT.chunk_id]}
    assert set(adult) == {CHILD.chunk_id, NEO.chunk_id}
    assert adult[CHILD.chunk_id]["match"] == "subset" and adult[NEO.chunk_id]["match"] == "exact"
    # The child row names one more act than the adult row: no link back to the adult row.
    assert ADULT.chunk_id not in {l["target"] for l in links.get(CHILD.chunk_id, [])}
    # Different acts ("gammaplex" vs "gammaplex étendue") are never linked.
    assert ADULT_OTHER.chunk_id not in links and CHILD_OTHER.chunk_id not in links


def test_builder_refuses_document_level_population_and_other_header():
    a = card("a1", 1, "t1", ["adulte"], "Résection alphaxyl", "2 g", source="document")
    b = card("p1", 10, "t2", ["pediatrie"], "Résection alphaxyl", "30 mg/kg", source="document")
    assert bcl.build_counterparts([a, b], 2)[0] == {}
    c = card("p1", 10, "t2", ["pediatrie"], "Résection alphaxyl", "30 mg/kg")
    c = c.model_copy(update={"text": c.text.replace(HDR, "Autre colonne")})
    a2 = card("a1", 1, "t1", ["adulte"], "Résection alphaxyl", "2 g")
    assert bcl.build_counterparts([a2, c], 2)[0] == {}


def test_builder_drops_ambiguous_links():
    a = card("a1", 1, "t1", ["adulte"], "Résection alphaxyl", "2 g")
    many = [card(f"p{i}", 10 + i, f"t{2 + i}", ["pediatrie"], f"Résection alphaxyl; Variante{i} zzz", "x") for i in range(3)]
    links, stats = bcl.build_counterparts([a, *many], max_per_pop=2)
    assert a.chunk_id not in links and stats["ambiguous_dropped"] >= 1


def test_note_reader_accepts_italic_escaped_marks_only():
    assert bcl.note_marks_relaxed("*\\*en cas de X, voir Y*") == {"*"}
    assert bcl.note_marks_relaxed("\\*\\* Note double") == {"**"}
    assert bcl.note_marks_relaxed("*Texte en italique*") == set()


def _links() -> ChunkLinks:
    cp, _ = bcl.build_counterparts(ALL, 2)
    terms = bcl.anchor_terms(ALL, set(cp), max_df=1.0)
    return ChunkLinks(cp, {}, {}, terms)


def _ctx(*chunks: Chunk, expanded: tuple[Chunk, ...] = ()) -> list[RetrievedChunk]:
    out = [RetrievedChunk(chunk=c, final_score=1.0 - i / 10) for i, c in enumerate(chunks)]
    out[1:1] = [RetrievedChunk(chunk=e, final_score=0.5, is_expanded_context=True, expansion_reason="context_window") for e in expanded]
    return out


def _an(pop: str = "non_specifie") -> QueryAnalysis:
    return QueryAnalysis(original_query="q", expanded_query="q", population=pop)


def test_disabled_policy_returns_the_same_list():
    ctx = _ctx(ADULT, ADULT_OTHER)
    out, stats = apply_links(ctx, _an(), RetrievalConfig(), Store(ALL), _links(), LinkPolicy())
    assert out is ctx and not stats["counterparts_added"]


def test_counterpart_added_after_anchor_block_marked_with_population():
    ctx = _ctx(ADULT, CHILD_OTHER, expanded=(ADULT_OTHER,))
    q = "résection alphaxyl et plastie betazor"
    out, stats = apply_links(ctx, _an(), RetrievalConfig(), Store(ALL), _links(), LinkPolicy(counterparts=True), query=q)
    ids = [r.chunk.chunk_id for r in out]
    # the frozen list is kept in order (the step only adds)
    assert [i for i in ids if i in {r.chunk.chunk_id for r in ctx}] == [r.chunk.chunk_id for r in ctx]
    # added right after the anchor block (anchor + its window), before the next ranked result
    assert ids.index(ADULT_OTHER.chunk_id) < ids.index(CHILD.chunk_id) < ids.index(CHILD_OTHER.chunk_id)
    added = {r.chunk.chunk_id: r for r in out if (r.expansion_reason or "").startswith("counterpart")}
    assert added[CHILD.chunk_id].expansion_reason == "counterpart:pediatrie"
    assert added[NEO.chunk_id].expansion_reason == "counterpart:neonatal"


def test_counterpart_respects_named_population_and_anchor_relevance():
    store, links = Store(ALL), _links()
    q = "résection alphaxyl et plastie betazor"
    # adult question: nothing from an adult anchor
    out, st = apply_links(_ctx(ADULT, ADULT_OTHER), _an("adulte"), RetrievalConfig(), store, links,
                          LinkPolicy(counterparts=True), query=q)
    assert not st["counterparts_added"]
    # child question with an age: the paediatric row, not the neonatal one
    out, st = apply_links(_ctx(ADULT, ADULT_OTHER), _an("pediatrie"), RetrievalConfig(), store, links,
                          LinkPolicy(counterparts=True), query=q + " chez un enfant de 8 ans")
    assert [a["population"] for a in st["counterparts_added"]] == ["pediatrie"]
    # the question does not name the anchor's act: no link followed
    out, st = apply_links(_ctx(ADULT, ADULT_OTHER), _an(), RetrievalConfig(), store, links,
                          LinkPolicy(counterparts=True), query="ablation gammaplex")
    assert not st["counterparts_added"] and st["anchors_skipped_not_named"] == 1


def test_counterpart_not_added_when_visible_or_over_budget():
    store, links, q = Store(ALL), _links(), "résection alphaxyl et plastie betazor"
    out, st = apply_links(_ctx(ADULT, CHILD), _an("pediatrie"), RetrievalConfig(), store, links,
                          LinkPolicy(counterparts=True), query=q + " enfant de 8 ans")
    assert not st["counterparts_added"]
    tight = len(ADULT.text) + len(ADULT_OTHER.text) + 5
    out, st = apply_links(_ctx(ADULT, ADULT_OTHER), _an(), RetrievalConfig(), store, links,
                          LinkPolicy(counterparts=True, char_budget=tight), query=q)
    assert not st["counterparts_added"]


def test_linked_retriever_disabled_is_identity():
    class Base:
        store = Store(ALL)

        def retrieve(self, query, config=None, **kw):
            return _ctx(ADULT, ADULT_OTHER), _an(), {"t": 1.0}

    base = Base()
    r1 = base.retrieve("résection alphaxyl")
    r2 = LinkedRetriever(base, links=_links()).retrieve("résection alphaxyl")
    assert [x.chunk.chunk_id for x in r1[0]] == [x.chunk.chunk_id for x in r2[0]] and r2[2] == r1[2]


# ---------------------------------------------------------------- frozen configuration, real data

FROZEN_ROWS = ROOT / "reports/agents/B1_annexes/res/tas_v6_F0__abpe171.json.gz"
SIDECAR = ROOT / "index/tas_v6_links"


@pytest.mark.skipif(
    not (FROZEN_ROWS.exists() and (SIDECAR / "links.json").exists() and (ROOT / "index/tas_v6/metadata.sqlite").exists()),
    reason="frozen outputs, tas_v6 index or link sidecar not present",
)
def test_frozen_outputs_unchanged_when_disabled_and_only_extended_when_enabled():
    """On the frozen C10_context_notes outputs (tas_v6, dev), the disabled step returns the same
    chunks, and the enabled step keeps every frozen chunk in its order."""
    import sqlite3

    rows = json.load(gzip.open(FROZEN_ROWS))["rows"][:40]
    need = {cid for r in rows for cid in r["chunks"]}
    con = sqlite3.connect(f"file:{ROOT / 'index/tas_v6/metadata.sqlite'}?mode=ro", uri=True)
    chunks = [Chunk.model_validate_json(p) for (p,) in con.execute("SELECT payload_json FROM chunks")]
    store = Store(chunks)
    assert need <= set(store.by)
    links = ChunkLinks.load(SIDECAR, ROOT / "index/tas_v6")
    for r in rows:
        ctx = [RetrievedChunk(chunk=store.get_chunk(c), final_score=1.0, is_expanded_context=x is not None,
                              expansion_reason=x) for c, x in zip(r["chunks"], r["reasons"])]
        an = QueryAnalysis(original_query="", expanded_query="", population=r["pop"])
        out, _ = apply_links(ctx, an, RetrievalConfig(), store, links, LinkPolicy())
        assert [x.chunk.chunk_id for x in out] == r["chunks"]
        out, _ = apply_links(ctx, an, RetrievalConfig(), store, links,
                             LinkPolicy(counterparts=True, notes=True, anchor_must_match_query=False))
        kept = [x.chunk.chunk_id for x in out if x.chunk.chunk_id in set(r["chunks"])]
        assert kept == r["chunks"]


@pytest.mark.skipif(os.environ.get("RAG_SFAR_SLOW_TESTS") != "1", reason="loads the embedder and reranker")
def test_frozen_retriever_identical_through_disabled_wrapper():
    """Live check (set RAG_SFAR_SLOW_TESTS=1, run under scripts/with_gpu_lock.sh): the frozen
    retriever wrapped with the link step disabled returns exactly the frozen chunks."""
    from rag_sfar.config import Settings
    from rag_sfar.evaluation.datasets import load_suite
    from rag_sfar.evaluation.harness import load_retrievers, select_configs

    cfg = select_configs("C10_context_notes")[0]
    base = load_retrievers(ROOT / "index", ["table_aware_sota"], "cross_encoder", Settings().reranker_model,
                           index_map={"table_aware_sota": "tas_v6"})["table_aware_sota"]
    wrapped = LinkedRetriever(base, SIDECAR)
    frozen = {r["id"]: r["chunks"] for r in json.load(gzip.open(FROZEN_ROWS))["rows"]}
    for it in load_suite("abpe171", "dev")[:12]:
        q = it.formatted_query()
        got = [x.chunk.chunk_id for x in wrapped.retrieve(q, config=cfg)[0]]
        assert got == frozen[it.id]
