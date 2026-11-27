"""B1 retrieval changes: MCQ parsing, patient-negation spans, table notes, population quotas,
coverage signal. All texts are synthetic (written for these tests, not taken from an
evaluation set)."""

from __future__ import annotations

import dataclasses

from rag_sfar.config import RetrievalConfig
from rag_sfar.retrieval.bm25 import BM25Index
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.query_tools import (
    negated_token_weights,
    patient_negated_spans,
    remove_spans,
    split_mcq,
)
from rag_sfar.retrieval.vector_store import LocalVectorStore
from rag_sfar.schemas import Chunk, DocumentMetadata

# --- MCQ parsing --------------------------------------------------------------------------------


def test_split_mcq_stem_and_options():
    stem, opts = split_mcq("Quel geste convient ?\nA. Geste un\nB. Geste deux\nC) Geste trois")
    assert stem == "Quel geste convient ?"
    assert opts == [("A", "Geste un"), ("B", "Geste deux"), ("C", "Geste trois")]


def test_split_mcq_requires_consecutive_letters():
    assert split_mcq("Question ?\nB. un\nD. deux")[1] == []
    assert split_mcq("Question sans options ?")[1] == []
    assert split_mcq("Question ?\nA. une seule option")[1] == []


# --- Negated background of the patient --------------------------------------------------------


def _neg(q: str) -> list[str]:
    return [q[a:b].strip() for a, b in patient_negated_spans(q)]


def test_patient_negation_spans_follow_the_patient_description():
    assert _neg("Chez une patiente de 52 ans sans diabète ni tabagisme, quel bilan avant la pose ?") == [
        "sans diabète", "ni tabagisme",
    ]
    assert _neg("Enfant de 8 ans pesant 25 kg, sans antécédent particulier : quelle conduite ?") == [
        "sans antécédent particulier",
    ]


def test_act_defining_negation_is_left_alone():
    # The negation defines the act, not the patient.
    assert _neg("Quelle prise en charge pour une cure d'éventration sans renfort prothétique ?") == []
    assert _neg("Chez un adulte, réparation tendineuse sans matériel : quelle conduite ?") == []


def test_negation_span_stops_before_an_affirmed_condition():
    q = "Homme de 60 ans non fumeur allergique à la molécule X : quelle alternative ?"
    spans = patient_negated_spans(q)
    kept = remove_spans(q, spans)
    assert "allergique à la molécule X" in kept
    assert "fumeur" not in kept


def test_mcq_options_are_never_touched_by_negation():
    q = "Dans quel cas ?\nA. Patient sans facteur de risque particulier\nB. Patient avec facteur de risque"
    assert patient_negated_spans(q) == []


def test_negated_token_weights_only_for_tokens_absent_elsewhere():
    q = "Patiente de 40 ans sans hypertension, hypertension portale à explorer ?"
    w = negated_token_weights(q, patient_negated_spans(q), 0.2)
    assert "hypertension" not in w  # also affirmed outside the negated span
    q2 = "Patiente de 40 ans sans hypertension, quelle imagerie du foie ?"
    assert negated_token_weights(q2, patient_negated_spans(q2), 0.2) == {"hypertension": 0.2}


def test_bm25_term_weights_lower_a_term():
    texts = ["encadré hypertension conduite", "imagerie du foie conduite"]
    bm = BM25Index().build(texts)
    plain = dict(bm.search("hypertension imagerie foie", top_k=2))
    weighted = dict(bm.search("hypertension imagerie foie", top_k=2, term_weights={"hypertension": 0.0}))
    assert 0 in plain and 0 not in weighted
    assert abs(plain[1] - weighted[1]) < 1e-6


# --- Synthetic store ---------------------------------------------------------------------------


def _store(chunks: list[Chunk]) -> LocalVectorStore:
    docs = {
        c.doc_id: DocumentMetadata(
            doc_id=c.doc_id, title=c.doc_id, filename=f"{c.doc_id}.pdf", md_path=f"{c.doc_id}.md",
            effective_year=2024,
        )
        for c in chunks
    }
    return LocalVectorStore(
        chunks=chunks, documents=list(docs.values()), embeddings=None,
        bm25=BM25Index().build([c.indexed_text for c in chunks]),
    )


def _chain(specs: list[tuple[str, str, str, dict]], doc_id: str = "d1") -> list[Chunk]:
    """Chunks of one document linked in reading order: (id, type, text, extra fields)."""
    out = []
    for i, (cid, ctype, text, kw) in enumerate(specs):
        out.append(
            Chunk(
                chunk_id=cid, doc_id=doc_id, chunk_index=i, chunk_type=ctype, text=text,
                indexed_text=text, prev_chunk_id=specs[i - 1][0] if i else None,
                next_chunk_id=specs[i + 1][0] if i + 1 < len(specs) else None, **kw,
            )
        )
    return out


_BASE = RetrievalConfig(
    use_subword=False, use_dense=False, use_reranker=False, use_crag_multihop=False,
    use_medical_lexicon=False, use_soft_metadata_boost=False, expand_neighbors=False,
    expand_section_callouts=False, final_top_k=1,
)


def test_table_notes_attach_linked_scope_note_and_trailing_footnotes():
    chunks = _chain([
        ("scope", "callout_footnote", "Les doses de ce tableau valent pour la population cible.", {}),
        ("tab", "table_markdown", "| Geste | Molécule |\n| zygomaplastie | moléculine |", {"linked_callout_ids": ["scope"]}),
        ("row", "table_row_card", "Geste : zygomaplastie* | Molécule : moléculine", {"linked_callout_ids": ["scope"]}),
        ("fn", "prose", "\\* Prolonger si contamination majeure.", {}),
        ("after", "prose", "Texte suivant sans rapport.", {}),
    ])
    r = SfarRagRetriever(_store(chunks))
    cfg = dataclasses.replace(_BASE, attach_table_notes=True)
    res, _, _ = r.retrieve("zygomaplastie", config=cfg)
    ids = [x.chunk.chunk_id for x in res]
    assert ids[0] == "row"
    assert {"scope", "fn"} <= set(ids)
    assert "after" not in ids
    assert all(x.expansion_reason == "table_note" for x in res[1:])
    # Off by default: same query, nothing attached.
    res0, _, _ = r.retrieve("zygomaplastie", config=_BASE)
    assert [x.chunk.chunk_id for x in res0] == ["row"]


def test_bold_text_is_not_a_footnote():
    chunks = _chain([
        ("row", "table_row_card", "Geste : zygomaplastie | Molécule : moléculine", {}),
        ("bold", "prose", "**Moléculine** : rappel de pharmacologie générale.", {}),
    ])
    r = SfarRagRetriever(_store(chunks))
    res, _, _ = r.retrieve("zygomaplastie", config=dataclasses.replace(_BASE, attach_table_notes=True))
    assert [x.chunk.chunk_id for x in res] == ["row"]


def test_population_quota_adds_the_other_population_for_unstated_population():
    chunks = _chain([
        ("ad", "table_row_card", "Acte : arthroplastie du coude | Molécule : moléculine 2 g", {"population_hint": "adulte"}),
        ("x1", "prose", "Texte général sur le coude et son arthroplastie.", {}),
        ("ped", "table_row_card", "Acte : arthroplastie du coude | Molécule : moléculine 30 mg/kg", {"population_hint": "pediatrie"}),
    ])
    r = SfarRagRetriever(_store(chunks))
    cfg = dataclasses.replace(_BASE, population_quota=1)
    res, an, _ = r.retrieve("arthroplastie du coude : quelle molécule ?", config=cfg)
    assert an.population == "non_specifie"
    ids = [x.chunk.chunk_id for x in res]
    assert {"ad", "ped"} <= set(ids)
    # A query that states the adult population gets no paediatric quota.
    res_ad, an_ad, _ = r.retrieve("Adulte, arthroplastie du coude : quelle molécule ?", config=cfg)
    assert an_ad.population == "adulte"
    assert "ped" not in [x.chunk.chunk_id for x in res_ad][:1]
    assert not any((x.expansion_reason or "").startswith("population:pediatrie") for x in res_ad)


def test_mcq_option_quota_retrieves_each_option():
    chunks = _chain([
        ("o1", "table_row_card", "Acte : rhinoplastie | conduite alpha", {}),
        ("o2", "table_row_card", "Acte : otoplastie | conduite beta", {}),
        ("o3", "table_row_card", "Acte : blépharoplastie | conduite gamma", {}),
    ])
    r = SfarRagRetriever(_store(chunks))
    q = "Quelle conduite ?\nA. rhinoplastie\nB. otoplastie\nC. blépharoplastie"
    res, _, _ = r.retrieve(q, config=dataclasses.replace(_BASE, mcq_option_quota=1))
    assert {"o1", "o2", "o3"} <= {x.chunk.chunk_id for x in res}


def test_coverage_signal_is_exposed_without_filtering():
    chunks = _chain([("a", "prose", "texte sur la zygomaplastie", {})])
    r = SfarRagRetriever(_store(chunks))
    res, _, timings = r.retrieve("zygomaplastie", config=_BASE)
    assert res  # never filtered
    assert timings["coverage_score"] == -1.0  # no reranker: not available
    assert timings["coverage_supported"] == -1.0
    assert r.last_coverage["coverage_score"] == -1.0
