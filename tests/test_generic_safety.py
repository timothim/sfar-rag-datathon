"""Non-regression tests for the clinical-safety defects fixed in the "generic C8" pass.

Every query below is synthetic (written for these tests, not taken from an evaluation set).
Each test names the defect it guards against (audit references: reports/01_audit.md).
"""

from __future__ import annotations

from rag_sfar.config import RetrievalConfig
from rag_sfar.ingestion.loader import infer_domains_from_text, normalize_and_impute_domains
from rag_sfar.retrieval.bm25 import BM25Index
from rag_sfar.retrieval.medical_lexicon import expand_medical_query
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.router import analyze_query, detect_affirmed_allergy
from rag_sfar.retrieval.vector_store import LocalVectorStore
from rag_sfar.schemas import Chunk, DocumentMetadata, RetrievedChunk


def _store(chunks: list[Chunk]) -> LocalVectorStore:
    docs = {
        c.doc_id: DocumentMetadata(
            doc_id=c.doc_id, title=c.doc_title or c.doc_id, filename=f"{c.doc_id}.pdf",
            md_path=f"{c.doc_id}.md", effective_year=c.effective_year or 2024,
        )
        for c in chunks
    }
    return LocalVectorStore(
        chunks=chunks, documents=list(docs.values()), embeddings=None,
        bm25=BM25Index().build([c.indexed_text for c in chunks]),
    )


def _chunk(cid: str, text: str, doc_id: str = "d1", **kw) -> Chunk:
    kw.setdefault("doc_title", "Document de test")
    kw.setdefault("effective_year", 2024)
    kw.setdefault("is_latest_edition", True)
    return Chunk(chunk_id=cid, doc_id=doc_id, chunk_index=0, text=text, indexed_text=text, **kw)


# --- C4: acronym lexicon ------------------------------------------------------------------------

def test_lexicon_does_not_expand_french_words():
    for q in (
        "Faut-il ne pas arrêter l'aspirine avant une chirurgie ?",
        "PAS D'ARRÊT DU TRAITEMENT AVANT LE GESTE ?",
        "Le patient ira en salle de réveil puis en rac",
        "Conduite en iso-volémie ?",
    ):
        expanded, acr = expand_medical_query(q)
        assert acr == {}, (q, acr)
        assert "pneumonie" not in expanded.lower()


def test_lexicon_still_expands_written_acronyms():
    _, acr = expand_medical_query("Arrêt des AOD avant PTH, ClCr 40 mL/min, portage E-BLSE")
    assert {"AOD", "PTH", "ClCr", "BLSE"} <= set(acr)
    # Case-sensitive: lower-case forms are words, not acronyms
    assert expand_medical_query("aod pth")[1] == {}


def test_router_does_not_add_infectious_domain_on_negation():
    qa = analyze_query("Faut-il ne pas arrêter l'aspirine avant une chirurgie ?")
    assert "Infectiologie" not in qa.inferred_domains


# --- Router: population ---------------------------------------------------------------------------

def test_bare_duration_is_not_a_paediatric_age():
    for q in (
        "Chez un patient sous antiagrégant, quel délai d'arrêt 6 mois après un stent ?",
        "Reprise du traitement 3 ans après la chirurgie ?",
        "Patient opéré il y a 2 ans d'une valve mécanique",
    ):
        assert analyze_query(q).population == "non_specifie", q


def test_stated_ages_set_the_population():
    assert analyze_query("Enfant de 6 mois : durée du jeûne préopératoire ?").population == "pediatrie"
    assert analyze_query("Patient âgé de 4 ans, analgésie après adénoïdectomie").population == "pediatrie"
    assert analyze_query("Patiente âgée de 45 ans, analgésie après hystérectomie").population == "adulte"
    assert analyze_query("Analgésie chez le sujet âgé après fracture").population == "adulte"
    # Pregnancy no longer implies a population on its own
    assert analyze_query("Analgésie pendant la grossesse ?").population == "non_specifie"


# --- C5: allergy modifier and allergy note -------------------------------------------------------

def test_alternative_or_drug_class_does_not_trigger_allergy():
    for q in (
        "Quelle alternative à l'intubation orotrachéale en cas d'échec ?",
        "Quelle est la place des pénicillines dans la pneumonie communautaire ?",
        "Bêtalactamines et insuffisance rénale : adaptation des doses ?",
        "Intolérance au glucose en réanimation : objectifs glycémiques ?",
    ):
        qa = analyze_query(q)
        assert "allergy" not in qa.modifiers, q
        assert detect_affirmed_allergy(q) is None, q


def test_affirmed_allergy_is_detected_and_negations_ignored():
    assert detect_affirmed_allergy("Patiente allergique aux curares : quelle induction ?") == "allergique aux curares"
    assert detect_affirmed_allergy("Antécédent d'allergie à la chlorhexidine et pose de cathéter") == "allergie à la chlorhexidine"
    for q in (
        "Pas d'allergie connue aux curares : quelle induction ?",
        "Patient non allergique à la chlorhexidine",
        "Prise en charge d'une réaction allergique peranesthésique",
    ):
        assert detect_affirmed_allergy(q) is None, q
    assert "allergy" in analyze_query("Patiente allergique aux curares").modifiers


def test_allergy_note_only_when_stated_and_class_neutral():
    from rag_sfar.generation.client import allergy_context_note, build_generation_context

    assert allergy_context_note("Quelle alternative au propofol pour la sédation ?") == ""
    assert allergy_context_note("Place des pénicillines en réanimation ?") == ""
    note = allergy_context_note("Patiente allergique aux curares : quelle induction ?")
    assert "allergique aux curares" in note
    assert "bêtalactamine" not in note.lower() and "pénicilline" not in note.lower()

    store = _store([_chunk("c1", "Induction anesthésique : choix des agents et des curares.")])
    retriever = SfarRagRetriever(store=store)
    cfg = RetrievalConfig(use_dense=False, use_reranker=False)
    for q, expected in (
        ("Quelle alternative aux curares pour l'induction ?", False),
        ("Patiente allergique aux curares : quelle induction ?", True),
    ):
        retrieved, analysis, _ = retriever.retrieve(q, config=cfg)
        _, ctx = build_generation_context(retrieved, analysis, cfg, q)
        assert ctx.startswith("NOTE : la question mentionne une allergie") is expected, q
        assert "ALLERGIQUE aux bêtalactamines" not in ctx


# --- I2: domain imputation by words -----------------------------------------------------------------

def test_domain_keywords_match_words_not_substrings():
    assert "Ambulatoire et Réhabilitation" not in infer_domains_from_text("Fracture du col et intubation orotrachéale")
    assert "Organisation et Professionnel" not in infer_domains_from_text("Faiblesse musculaire acquise")
    assert "Ambulatoire et Réhabilitation" in infer_domains_from_text("Programme RAC en chirurgie colique")
    assert "Infectiologie" in infer_domains_from_text("Antibiothérapie probabiliste")  # stems still match
    domains, _ = normalize_and_impute_domains(None, "Prise en charge d'une fracture", "")
    assert "Ambulatoire et Réhabilitation" not in domains


# --- I3: population prior and "(hors X)" ------------------------------------------------------------

def test_paediatric_prior_only_when_population_stated():
    retriever = SfarRagRetriever(store=_store([_chunk("c1", "x")]))
    ped = _chunk("c2", "Analgésie après amygdalectomie", population_hint="pediatrie")
    cfg = RetrievalConfig()
    unstated = analyze_query("Quelle analgésie après amygdalectomie ?")
    adult = analyze_query("Quelle analgésie après amygdalectomie chez l'adulte ?")
    base = retriever._compute_soft_metadata_boost(_chunk("c3", "x"), unstated, cfg)
    assert retriever._compute_soft_metadata_boost(ped, unstated, cfg) == base
    assert retriever._compute_soft_metadata_boost(ped, adult, cfg) < base


def test_section_exclusion_rule():
    retriever = SfarRagRetriever(store=_store([_chunk("c1", "x")]))
    title_scope = _chunk("c1", "x", section_path="Intubation en urgence d'un adulte hors bloc opératoire")
    excl = _chunk("c2", "x", section_path="Partie 3 > Plaies (hors main)")
    mult = retriever._compute_clinical_scope_multiplier
    # A document whose title says "hors bloc" is not penalised for a query about that setting
    assert mult(title_scope, analyze_query("Intubation en urgence hors du bloc opératoire ?")) == 1.0
    # A parenthesised section exclusion contradicted by the query is penalised...
    assert mult(excl, analyze_query("Prise en charge d'une plaie de la main")) < 1.0
    # ...unless the query itself excludes it
    assert mult(excl, analyze_query("Prise en charge d'une plaie hors de la main")) == 1.0
    assert mult(excl, analyze_query("Prise en charge d'une plaie du pied")) == 1.0


# --- I4: output contract of retrieve() ---------------------------------------------------------------

def test_final_top_k_is_respected_and_output_sorted():
    chunks = [
        _chunk(f"c{i}", f"Chirurgie colique {i} : prévention et posologie chez le patient obèse, IMC {30 + i}.",
               doc_id=f"d{i % 3}", chunk_type="table_row_card")
        for i in range(12)
    ]
    retriever = SfarRagRetriever(store=_store(chunks))
    for k in (1, 3, 5):
        res, _, _ = retriever.retrieve(
            "Prévention pour une colectomie associée à une cure d'éventration chez un patient obèse BLSE R1.1 ?",
            config=RetrievalConfig(use_dense=False, use_reranker=False, final_top_k=k),
        )
        assert len(res) <= k
        scores = [r.final_score for r in res]
        assert scores == sorted(scores, reverse=True)


def test_crag_subqueries_have_no_hard_coded_ids_or_molecules():
    from rag_sfar.retrieval.crag import detect_clinical_facets

    q = "Prévention pour une colectomie chez un patient obèse porteur de BLSE ?"
    facets = detect_clinical_facets(analyze_query(q))
    assert {f.name for f in facets} >= {"obesity", "blse"}
    for f in facets:
        assert f.subquery.startswith(q)
        assert "R1." not in f.subquery
        for mol in ("céfazoline", "ertapénème", "clindamycine", "amoxicilline", "apixaban"):
            assert mol not in f.subquery.lower()


# --- C6: code-added sourcing ---------------------------------------------------------------------------

class _NoYearLLM:
    model = "mock-llm"

    def complete(self, system_prompt, user_prompt, temperature=None, max_tokens=None):
        return "Ligne 2 — RÉPONSE : Dose unique préopératoire", {"total_tokens": 1}


def test_provenance_is_not_added_by_default_and_flagged_when_added():
    from rag_sfar.generation.client import SfarRagEngine

    store = _store([_chunk("c1", "Prophylaxie : dose unique préopératoire.", effective_year=2025)])
    cfg = RetrievalConfig(use_dense=False, use_reranker=False)
    retriever = SfarRagRetriever(store=store)

    default = SfarRagEngine(retriever=retriever, llm=_NoYearLLM(), default_config=cfg)
    resp = default.answer("Quelle prophylaxie ?", mode="benchmark_open")
    assert resp.answer == "Dose unique préopératoire"
    assert resp.extra["provenance_added_by_code"] is False
    assert resp.verification.provenance_added_by_code is False

    display = SfarRagEngine(retriever=retriever, llm=_NoYearLLM(), default_config=cfg, attach_provenance=True)
    resp = display.answer("Quelle prophylaxie ?", mode="benchmark_open")
    assert resp.answer.endswith("(SFAR 2025 [S1])")
    assert resp.extra["provenance_added_by_code"] is True
    assert resp.verification.provenance_added_by_code is True


# --- Benchmark adapter -----------------------------------------------------------------------------------

def test_adapter_uses_engine_context():
    from types import SimpleNamespace

    from rag_sfar.evaluation.benchmark_adapter import SfarRagApproach
    from rag_sfar.generation.client import build_generation_context

    store = _store([_chunk("c1", "Induction anesthésique : choix des agents et des curares.")])
    retriever = SfarRagRetriever(store=store)
    cfg = RetrievalConfig(use_dense=False, use_reranker=False, use_u_shape_ordering=False)
    approach = SfarRagApproach(retriever=retriever, config=cfg)
    q = SimpleNamespace(question_text="Patiente allergique aux curares : quelle induction ?", question_type="open")
    prompt = approach.build_prompt(q)
    retrieved, analysis, _ = retriever.retrieve(q.question_text, config=cfg)
    _, ctx = build_generation_context(retrieved, analysis, cfg, q.question_text, "benchmark_open")
    assert ctx in prompt
    assert "allergique aux curares" in prompt
