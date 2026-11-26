"""Unit and integration tests for RAG-SFAR."""

from __future__ import annotations

from pathlib import Path

import pytest

from rag_sfar.config import RetrievalConfig
from rag_sfar.evaluation.benchmark_adapter import score_antibioprophylaxie_answer
from rag_sfar.generation.verifier import verify_generation
from rag_sfar.ingestion.chunker import chunk_document
from rag_sfar.ingestion.loader import (
    LoadedDocument,
    clean_chandra_markdown,
    detect_language,
    infer_effective_year_and_version,
    load_sfar_corpus,
    normalize_and_impute_domains,
)
from rag_sfar.ingestion.table_parser import parse_html_table
from rag_sfar.interfaces.mcp_server import SfarMcpServer
from rag_sfar.retrieval.bm25 import BM25Index
from rag_sfar.retrieval.medical_lexicon import expand_medical_query, tokenize_medical_french
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.router import analyze_query
from rag_sfar.retrieval.vector_store import LocalVectorStore
from rag_sfar.schemas import Chunk, DocumentMetadata, RetrievedChunk


def test_clean_chandra_inline_headings():
    raw = "V3.0 du 04/05/2026### INTRODUCTION\npendant 48h maximum.## PARTIE 2 : ORL"
    cleaned = clean_chandra_markdown(raw)
    assert "\n\n### INTRODUCTION" in cleaned
    assert "\n\n## PARTIE 2 : ORL" in cleaned


def test_html_table_rowspan_and_continuation_headers():
    t1 = """
    <table>
      <thead>
        <tr><th>Actes chirurgicaux</th><th>Molécules</th><th>Dose initiale</th><th>Force</th></tr>
      </thead>
      <tbody>
        <tr>
          <td rowspan="2"><ul><li>▪ Chirurgie rhinologique avec greffon</li></ul></td>
          <td>Céfazoline</td><td>2g IVL</td><td>GRADE 2</td>
        </tr>
        <tr>
          <td><i>Alternative :</i> Amoxicilline/Clavulanate</td><td>2g IVL</td><td>Avis d'experts</td>
        </tr>
      </tbody>
    </table>
    """
    p1 = parse_html_table(t1)
    assert p1.has_explicit_headers is True
    assert p1.headers == ["Actes chirurgicaux", "Molécules", "Dose initiale", "Force"]
    assert len(p1.row_groups) == 1
    assert len(p1.row_groups[0].rows) == 2
    cards = p1.to_row_cards(min_cols=3)
    assert len(cards) == 1
    assert "Chirurgie rhinologique avec greffon" in cards[0]
    assert "Céfazoline" in cards[0]
    assert "Amoxicilline/Clavulanate" in cards[0]

    # Headerless continuation table on next page
    t2 = """
    <table>
      <tr><td>Prothèse totale de genou</td><td>Céfazoline</td><td>2g IVL</td><td>GRADE 1</td></tr>
    </table>
    """
    p2 = parse_html_table(t2, previous_headers=p1.headers)
    assert p2.has_explicit_headers is False
    assert p2.inherited_headers is True
    assert p2.headers == p1.headers
    md = p2.to_markdown_chunks()[0]
    assert "| Actes chirurgicaux | Molécules | Dose initiale | Force |" in md
    assert "Prothèse totale de genou" in md


def test_table_sub_banner_inheritance():
    t_anticoag = """
    <table>
      <thead><tr><th>N°</th><th>Recommandation</th><th>Grade</th><th>Accord</th></tr></thead>
      <tbody>
        <tr><td></td><td><b>Patients traités par un AVK</b></td><td></td><td></td></tr>
        <tr><td>3.1</td><td>Arrêt warfarine J-6, contrôle INR veille</td><td>2+</td><td>Fort</td></tr>
        <tr><td></td><td><b>Patients traités par un AOD</b></td><td></td><td></td></tr>
        <tr><td>3.3</td><td>Arrêt apixaban/rivaroxaban à J-3</td><td>2+</td><td>Fort</td></tr>
      </tbody>
    </table>
    """
    parsed = parse_html_table(t_anticoag)
    cards = parsed.to_row_cards(min_cols=3)
    assert any("Patients traités par un AVK" in c and "J-6" in c for c in cards)
    assert any("Patients traités par un AOD" in c and "J-3" in c for c in cards)


def test_language_detection_handles_english_abstract():
    # English abstract at top, French full body
    en_abs = "Background: the patients in this study were recommended for surgery and anesthesia. " * 25
    fr_body = "Les recommandations formalisées d'experts de la SFAR dans la prise en charge des patients chez l'adulte pour une chirurgie avec antibioprophylaxie. " * 60
    assert detect_language(en_abs + fr_body, "RFE_francais.pdf") == "fr"
    assert detect_language(en_abs * 5, "RFE-Guidelines-for-management.pdf") == "en"


def test_effective_year_and_domain_imputation():
    yr, ver, _ = infer_effective_year_and_version(
        2023,
        "RFE-antibioprophylaxie-2023_V3.0_pour-mise-sur-site-juin-2026_sans-code-CCAM.pdf",
        "Antibioprophylaxie en chirurgie",
        "V3.0 du 04/05/2026 ### INTRODUCTION",
    )
    assert yr == 2026
    assert ver == "V3.0 (04/05/2026)"

    domains, imputed = normalize_and_impute_domains(
        None,
        "Gestion des anticoagulants pour une procédure invasive programmée",
        "AVK AOD apixaban warfarine hémostase",
    )
    assert imputed is True
    assert "Hématologie – Coagulation – Transfusion" in domains


def test_medical_lexicon_and_query_router():
    exp, acr = expand_medical_query("Antibioprophylaxie pour PTH chez patient allergique")
    assert "PTH" in acr
    assert "prothèse totale de hanche" in exp.lower()

    qa_latest = analyze_query("Délai d'arrêt des AOD avant une neurochirurgie programmée ?")
    assert qa_latest.temporal_mode == "latest_only"
    assert qa_latest.setting == "programme"
    assert "AOD" in qa_latest.acronyms_expanded

    qa_diff = analyze_query("Qu'est-ce qui a changé entre 2018 et 2026 pour l'antibioprophylaxie ?")
    assert qa_diff.temporal_mode == "all_versions"
    assert qa_diff.requested_years == [2018, 2026]

    qa_urg = analyze_query("Réversion anticoagulant en urgence pour hémorragie intracrânienne")
    assert qa_urg.setting == "urgence"

    toks = tokenize_medical_french("Amoxicilline/Clavulanate 2g IVL à J-3")
    assert "amoxicilline" in toks and "clavulanate" in toks and "j-3" in toks


def test_section_allergy_box_linking_and_expansion():
    md = """
## PARTIE 7 : CHIRURGIE ORTHOPEDIQUE

<table>
  <thead><tr><th>Actes</th><th>Molécules</th><th>Dose</th><th>Force</th></tr></thead>
  <tbody>
    <tr><td>Prothèse totale de genou (PTG)</td><td>Céfazoline</td><td>2g IVL</td><td>GRADE 1</td></tr>
    <tr><td>Arthroscopie diagnostique sans matériel</td><td>Pas d'antibioprophylaxie</td><td>-</td><td>GRADE 1</td></tr>
  </tbody>
</table>

En cas d'allergie aux bêtalactamines, si antibioprophylaxie indiquée dans ce tableau : Clindamycine 900 mg IVL. En cas de prothèse de hanche par voie antérieure : préférer Vancomycine.

#### Références
1. Smith et al. Cefazolin vs Clindamycin in total knee arthroplasty. 2019.
"""
    meta = DocumentMetadata(
        doc_id="doc_abp_2026",
        title="Antibioprophylaxie en chirurgie",
        filename="RFE_abp.pdf",
        md_path="dummy.md",
        effective_year=2026,
        domains=["Infectiologie"],
        topic_lineage="antibioprophylaxie",
        is_latest_edition=True,
    )
    chunks = chunk_document(LoadedDocument(metadata=meta, text=md), strategy="table_aware_sota")
    # References must be tagged
    ref_chunks = [c for c in chunks if c.is_reference_section]
    assert len(ref_chunks) >= 1
    # Row card for PTG must link to the specialty allergy box!
    ptg_cards = [c for c in chunks if c.chunk_type == "table_row_card" and "genou" in c.text.lower()]
    assert len(ptg_cards) == 1
    assert len(ptg_cards[0].linked_callout_ids) >= 1

    # Retrieve with BM25+ and verify specialty allergy box is auto-attached!
    bm25 = BM25Index().build([c.indexed_text for c in chunks])
    store = LocalVectorStore(chunks=chunks, documents=[meta], embeddings=None, bm25=bm25)
    retriever = SfarRagRetriever(store=store)
    cfg = RetrievalConfig(use_dense=False, use_reranker=False, expand_section_callouts=True)
    results, _, _ = retriever.retrieve("PTG allergie aux bêtalactamines", config=cfg)
    combined_text = " ".join(r.chunk.text for r in results).lower()
    assert "clindamycine" in combined_text
    assert all(not r.chunk.is_reference_section for r in results)


def test_citation_and_molecule_verifier():
    c1 = Chunk(
        chunk_id="c1",
        doc_id="d1",
        chunk_index=0,
        text="Prothèse totale de genou : Céfazoline 2g IVL (GRADE 1).",
        indexed_text="Prothèse totale de genou : Céfazoline 2g IVL (GRADE 1).",
        doc_title="ABP 2026",
        effective_year=2026,
        is_latest_edition=True,
    )
    retrieved = [RetrievedChunk(chunk=c1, final_score=0.95)]

    rep_ok = verify_generation("Administrer Céfazoline 2g IVL [S1].", retrieved)
    assert rep_ok.grounding_score == 1.0
    assert rep_ok.ungrounded_molecules == []

    rep_bad = verify_generation("Administrer Méropénème 1g IV [S1] [S9].", retrieved)
    assert "S9" in rep_bad.invalid_citations
    assert "meropeneme" in rep_bad.ungrounded_molecules
    assert rep_bad.grounding_score < 0.5


def test_antibioprophylaxie_scorer_parity():
    assert score_antibioprophylaxie_answer("open", "Clindamycine + Gentamicine", "Clindamycine + Gentamicine.")
    assert score_antibioprophylaxie_answer("open", "Pas d'antibioprophylaxie", "Pas d'antibioprophylaxie")
    assert not score_antibioprophylaxie_answer("open", "Clindamycine + Gentamicine", "Clindamycine")
    assert score_antibioprophylaxie_answer("mcq", "C", "Réponse : C")
    assert not score_antibioprophylaxie_answer("mcq", "C", "A")


def test_mcp_server_protocol():
    c1 = Chunk(
        chunk_id="c1",
        doc_id="d1",
        chunk_index=0,
        text="Arrêt des AOD (apixaban, rivaroxaban) à J-3 avant procédure programmée.",
        indexed_text="Arrêt des AOD (apixaban, rivaroxaban) à J-3 avant procédure programmée.",
        doc_title="Gestion des anticoagulants",
        effective_year=2026,
        domains=["Hématologie – Coagulation – Transfusion"],
        is_latest_edition=True,
    )
    meta = DocumentMetadata(
        doc_id="d1",
        title="Gestion des anticoagulants",
        filename="anticoag.pdf",
        md_path="a.md",
        effective_year=2026,
        domains=["Hématologie – Coagulation – Transfusion"],
    )
    store = LocalVectorStore(
        chunks=[c1], documents=[meta], embeddings=None, bm25=BM25Index().build([c1.indexed_text])
    )
    mcp = SfarMcpServer(SfarRagRetriever(store=store))
    init_resp = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_resp["result"]["serverInfo"]["name"] == "rag-sfar-mcp"
    tools_resp = mcp.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(tools_resp["result"]["tools"]) == 4
    call_resp = mcp.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "search_sfar_recommendations", "arguments": {"query": "arrêt AOD"}},
        }
    )
    assert "J-3" in call_resp["result"]["content"][0]["text"]


@pytest.mark.skipif(
    not Path("data/sfar_recommendations/output/discovery.json").exists(),
    reason="Real SFAR corpus not present",
)
def test_real_corpus_supersession_and_integrity():
    docs = load_sfar_corpus(Path("data/sfar_recommendations/output"))
    assert len(docs) >= 260
    # Verify flagship 2026 editions are marked latest while older editions are superseded
    abp = [d.metadata for d in docs if d.metadata.topic_lineage == "antibioprophylaxie"]
    assert any(m.effective_year == 2026 and m.is_latest_edition for m in abp)
    assert any(m.effective_year == 2018 and not m.is_latest_edition for m in abp)

    # Verify urgence 2024 vs programmé 2026 anticoagulants are BOTH active & latest!
    ac_prog = [d.metadata for d in docs if d.metadata.topic_lineage == "anticoagulants_procedure_programmee"]
    ac_urg = [d.metadata for d in docs if d.metadata.topic_lineage == "anticoagulants_urgence"]
    assert any(m.effective_year == 2026 and m.is_latest_edition for m in ac_prog)
    assert any(m.effective_year == 2024 and m.is_latest_edition for m in ac_urg)


def test_frontier_2026_subword_crag_context_opt_and_rag_x():
    from rag_sfar.evaluation.rag_x import compute_rag_x_diagnostics
    from rag_sfar.retrieval.context_optimizer import prune_verbose_prose, reorder_lost_in_the_middle
    from rag_sfar.retrieval.crag import detect_clinical_facets, find_missing_facets
    from rag_sfar.retrieval.subword import CharNgramIndex

    # 1. Subword Char 3-5 N-Gram catches French morphology & OCR typos
    sw = CharNgramIndex().build(
        [
            "Chirurgie colorectale programmée : céfoxitine 2g IVL.",
            "Antibioprophylaxie morsure animale : amoxicilline/clavulanate 2g IVL.",
            "Prise en charge d'une hémorragie intracrânienne sous AOD.",
        ]
    )
    hits = sw.search("colectomie colique", top_k=2)
    assert hits and hits[0][0] == 0
    hits_typo = sw.search("morsures animales", top_k=2)
    assert hits_typo and hits_typo[0][0] == 1

    # 2. Auto-exit References heading: clinical R1.7.2 after #### Références must NOT be swallowed
    md_ref_trap = """
## CHAMP 1
#### Références
[1] Smith J et al. Study on prophylaxis. Ann Surg 2020;10:1-5.

**R1.7.2 – En cas de positivité du dépistage de la colonisation rectale à E-BLSE, l'ertapénème 2g IVL est recommandé (Avis d'experts).**
"""
    meta = DocumentMetadata(
        doc_id="doc_ref_trap", title="ABP", filename="abp.pdf", md_path="x.md", effective_year=2026
    )
    chks = chunk_document(LoadedDocument(metadata=meta, text=md_ref_trap), strategy="table_aware_sota")
    non_ref = [c for c in chks if not c.is_reference_section]
    assert any("ertapénème" in c.text.lower() for c in non_ref)

    # 3. CRAG Facet Decomposition & Missing Facet Detection
    qa = analyze_query("Antibioprophylaxie pour colectomie droite chez un patient porteur rectal de BLSE ?")
    facets = detect_clinical_facets(qa)
    assert any(f.name == "blse" for f in facets)
    dummy_c = Chunk(chunk_id="c0", doc_id="d0", chunk_index=0, text="Colectomie standard : céfoxitine.", indexed_text="Colectomie standard : céfoxitine.")
    missing = find_missing_facets([RetrievedChunk(chunk=dummy_c, final_score=0.9)], facets)
    assert any(f.name == "blse" for f in missing)

    # 4. Lost-in-the-Middle U-Shape Reordering & Provence-style Pruning
    items = [
        RetrievedChunk(
            chunk=Chunk(chunk_id=f"c{i}", doc_id="d", chunk_index=i, text=f"T{i}", indexed_text=f"T{i}"),
            final_score=1.0 - i * 0.1,
        )
        for i in range(6)
    ]
    reordered = reorder_lost_in_the_middle(items)
    assert reordered[0].chunk.chunk_id == "c0"  # #1 at primacy start
    assert reordered[-1].chunk.chunk_id == "c1"  # #2 at recency end

    long_prose = (
        "L'histoire de la médecine remonte à l'antiquité et comporte de nombreux débats généraux. " * 15
        + "Pour la prothèse totale de hanche, il est recommandé d'administrer Céfazoline 2g IVL (GRADE 1)."
    )
    pruned = prune_verbose_prose(long_prose, query="prothèse hanche céfazoline", chunk_type="prose", max_chars=400)
    assert "Céfazoline 2g IVL" in pruned and len(pruned) < len(long_prose)

    # 5. RAG-X 4-Quadrant Component Diagnostics
    diag = compute_rag_x_diagnostics(
        [
            {"evidence_present": True, "is_correct": True},
            {"evidence_present": True, "is_correct": True},
            {"evidence_present": False, "is_correct": True},  # Lucky guess
            {"evidence_present": True, "is_correct": False},  # Generator error
        ]
    )
    assert diag.raw_accuracy == 0.75
    assert diag.grounded_accuracy == 0.5
    assert diag.accuracy_fallacy_gap == 0.25
    assert round(diag.context_utilization_efficiency, 4) == round(2 / 3, 4)


def test_mcq_choices_formatting_and_sourcing_scorer():
    from rag_sfar.evaluation.benchmark_adapter import score_sourcing_present
    from rag_sfar.evaluation.benchmarks import EvalQuestion

    q = EvalQuestion(
        id="Q163",
        question_type="mcq",
        question="Quelle conduite est INCORRECTE ?",
        choices={"A": "Amoxicilline/Clavulanate", "B": "Céfazoline", "C": "Aucun ajout"},
        expected_answer="C",
    )
    fmt = q.formatted_query()
    assert "A. Amoxicilline/Clavulanate" in fmt and "C. Aucun ajout" in fmt
    assert score_antibioprophylaxie_answer("mcq", "C", "C (SFAR 2026 [S1])")
    assert score_antibioprophylaxie_answer("open", "Céfazoline", "Céfazoline (SFAR 2026 [S1])")
    assert score_antibioprophylaxie_answer(
        "open", "Pas d'antibioprophylaxie", "Pas d'antibioprophylaxie (SFAR 2026 [S1])"
    )
    assert score_sourcing_present("Céfazoline (SFAR 2026 [S1])")
    assert not score_sourcing_present("Céfazoline")


def test_self_medrag_active_verifier_repair():
    from rag_sfar.generation.client import SfarRagEngine

    c1 = Chunk(
        chunk_id="c1",
        doc_id="d1",
        chunk_index=0,
        text="Prothèse de hanche : Céfazoline 2g IVL (GRADE 1).",
        indexed_text="Prothèse de hanche : Céfazoline 2g IVL (GRADE 1).",
        doc_title="Antibioprophylaxie",
        effective_year=2026,
        is_latest_edition=True,
    )
    meta = DocumentMetadata(
        doc_id="d1", title="Antibioprophylaxie", filename="abp.pdf", md_path="a.md", effective_year=2026
    )
    store = LocalVectorStore(
        chunks=[c1], documents=[meta], embeddings=None, bm25=BM25Index().build([c1.indexed_text])
    )

    class HallucinatingThenFixedLLM:
        model = "mock-llm"

        def __init__(self):
            self.calls = 0

        def complete(self, system_prompt, user_prompt, temperature=None, max_tokens=None):
            self.calls += 1
            if self.calls == 1:
                return "Méropénème (SFAR 2026 [S1])", {"prompt_tokens": 50, "completion_tokens": 8, "total_tokens": 58}
            return "Céfazoline (SFAR 2026 [S1])", {"prompt_tokens": 80, "completion_tokens": 8, "total_tokens": 88}

    mock_llm = HallucinatingThenFixedLLM()
    engine = SfarRagEngine(
        retriever=SfarRagRetriever(store=store),
        llm=mock_llm,
        default_config=RetrievalConfig(use_dense=False, use_reranker=False),
    )
    resp = engine.answer("Prothèse de hanche ?", mode="benchmark_open")
    assert mock_llm.calls == 2
    assert resp.extra["self_corrected"] is True
    assert "Céfazoline" in resp.answer
    assert resp.verification.grounding_score == 1.0


def test_noise_filtered_precision_context_selection():
    from rag_sfar.retrieval.context_optimizer import select_generation_context

    def _rc(cid: str, ctype: str, score: float, txt: str = "x") -> RetrievedChunk:
        return RetrievedChunk(
            chunk=Chunk(chunk_id=cid, doc_id="d", chunk_index=0, chunk_type=ctype, text=txt, indexed_text=txt),
            final_score=score,
        )

    pool = [
        _rc("c1", "table_row_card", 0.99, "Morsure : Amoxicilline/Clavulanate"),
        _rc("c2", "table_row_card", 0.92, "Plaie contaminée : Amoxicilline/Clavulanate"),
        _rc("c3", "callout_allergy", 0.90, "En cas d'allergie : Clindamycine"),
        _rc("c4", "table_row_card", 0.85, "Prothèse : Céfazoline"),
        _rc("c5", "prose", 0.40, "Bruit faible score"),
    ]
    # Non-allergy query MUST exclude allergy box and low-score noise
    non_all = select_generation_context(pool, is_allergy_query=False, max_chunks=4, min_relative_score=0.62)
    ids_non = [r.chunk.chunk_id for r in non_all]
    assert "c3" not in ids_non
    assert "c5" not in ids_non
    assert ids_non[:2] == ["c1", "c2"]

    # Allergy query MUST preserve allergy box in top slots
    all_sel = select_generation_context(pool, is_allergy_query=True, max_chunks=4, min_relative_score=0.62)
    ids_all = [r.chunk.chunk_id for r in all_sel]
    assert "c3" in ids_all[:3]
    assert "c5" not in ids_all

    # Extract-Then-Answer 2-line parser
    from rag_sfar.generation.client import _extract_benchmark_final_line

    raw = (
        "Ligne 1 — Analyse : [S1] Acte exact = Morsure | Allergie = non | Molécule = Amoxicilline/Clavulanate\n"
        "Ligne 2 — Réponse : Amoxicilline/Clavulanate (SFAR 2026 [S1])"
    )
    assert _extract_benchmark_final_line(raw) == "Amoxicilline/Clavulanate (SFAR 2026 [S1])"


def test_specialty_allergy_box_survives_child_chirurgie_subheading():
    md = """
## PARTIE 2 : CHIRURGIE ORL
Texte introductif général sur la chirurgie ORL et les facteurs de risque infectieux postopératoires.
Pour les patients d'IMC >= 50 kg/m2, la posologie est discutée collégialement.

En cas d'allergie aux bêtalactamines, si antibioprophylaxie indiquée dans ce tableau :
**Clindamycine 900 mg IVL** (Avis d'experts).

### Chirurgie carcinologique cervico-faciale
<table>
<thead><tr><th>Actes chirurgicaux ou interventionnels</th><th>Molécules</th><th>Dose initiale</th></tr></thead>
<tbody><tr><td>Chirurgie carcinologique avec lambeau libre</td><td>Amoxicilline/Clavulanate</td><td>2g IVL</td></tr></tbody>
</table>
"""
    meta = DocumentMetadata(
        doc_id="abp_orl", title="ABP", filename="abp.pdf", md_path="abp.md", effective_year=2026
    )
    chks = chunk_document(LoadedDocument(metadata=meta, text=md), strategy="table_aware_sota")
    by_id = {c.chunk_id: c for c in chks}
    lambeau = [c for c in chks if "lambeau libre" in c.text.lower() and c.chunk_type == "table_row_card"]
    assert lambeau, "Expected lambeau libre row card"
    linked_allergies = [
        by_id[lid] for lid in lambeau[0].linked_callout_ids if by_id[lid].chunk_type == "callout_allergy"
    ]
    assert linked_allergies, "Child '### Chirurgie ...' table MUST inherit parent PARTIE allergy box!"
    assert linked_allergies[0].text.lower().startswith("en cas d'allergie")
    assert "clindamycine" in linked_allergies[0].text.lower()


def test_balanced_temporal_diff_and_macrolide_guard():
    # 1. Verify macrolides like azithromycine are caught by molecule verifier
    src_chunk = RetrievedChunk(
        chunk=Chunk(
            chunk_id="iia1",
            doc_id="iia",
            chunk_index=0,
            text="R1.2.1 : Céfotaxime ou Ceftriaxone + Métronidazole (GRADE 1+).",
            indexed_text="R1.2.1 : Céfotaxime ou Ceftriaxone + Métronidazole (GRADE 1+).",
        ),
        final_score=0.95,
    )
    ver = verify_generation("Alternative : Azithromycine + Métronidazole [S1].", [src_chunk])
    assert "azithromycine" in ver.ungrounded_molecules
    assert ver.grounding_score < 1.0

    # 2. Verify temporal_diff balances BOTH latest (2026) and historical (2018) editions
    chunks = [
        Chunk(
            chunk_id=f"c2018_{i}",
            doc_id="abp_2018",
            chunk_index=i,
            chunk_type="table_row_card",
            text=f"Antibioprophylaxie 2018 acte {i} : Céfazoline",
            indexed_text=f"[RFE SFAR 2018] Antibioprophylaxie 2018 acte {i} : Céfazoline",
            doc_title="Antibioprophylaxie",
            effective_year=2018,
            is_latest_edition=False,
        )
        for i in range(5)
    ] + [
        Chunk(
            chunk_id=f"c2026_{i}",
            doc_id="abp_2026",
            chunk_index=i,
            chunk_type="prose",
            text=f"Antibioprophylaxie V3.0 2026 mise à jour pédiatrie changement {i}",
            indexed_text=f"[RFE SFAR 2026 V3.0] Antibioprophylaxie V3.0 2026 mise à jour pédiatrie changement {i}",
            doc_title="Antibioprophylaxie",
            effective_year=2026,
            is_latest_edition=True,
        )
        for i in range(3)
    ]
    metas = [
        DocumentMetadata(doc_id="abp_2018", title="ABP", filename="a18.pdf", md_path="a18.md", effective_year=2018, is_latest_edition=False),
        DocumentMetadata(doc_id="abp_2026", title="ABP", filename="a26.pdf", md_path="a26.md", effective_year=2026, is_latest_edition=True),
    ]
    store = LocalVectorStore(
        chunks=chunks,
        documents=metas,
        embeddings=None,
        bm25=BM25Index().build([c.indexed_text for c in chunks]),
    )
    ret = SfarRagRetriever(store=store)
    res, an, _ = ret.retrieve(
        "Qu'est-ce qui a changé en antibioprophylaxie entre 2018 et 2026 ?",
        RetrievalConfig(use_dense=False, use_reranker=False, final_top_k=6),
    )
    assert an.temporal_mode == "all_versions"
    years = {r.chunk.effective_year for r in res[:4]}
    assert years == {2018, 2026}, f"Expected both 2018 and 2026 in top-4 diff context, got {years}"


def test_mcq_option_composite_and_scope_guard():
    from rag_sfar.retrieval.crag import (
        extract_composite_procedure_subqueries,
        extract_mcq_option_subqueries,
    )

    # 1. Comparative MCQ with distinct clinical acts triggers option-aware retrieval
    mcq_acts = (
        "Parmi ces interventions ORL, laquelle ne nécessite PAS d'antibioprophylaxie ?\n"
        "A. Pose d'implant cochléaire\nB. Amygdalectomie\nC. Laryngectomie totale\nD. Trachéotomie chirurgicale"
    )
    opts = extract_mcq_option_subqueries(mcq_acts)
    assert len(opts) == 4
    assert any("Amygdalectomie" in sq for _, sq in opts)

    # 2. Pure drug-only MCQ does NOT trigger noisy option subqueries
    mcq_drugs = (
        "Alternative allergie pour une prothèse de genou ?\n"
        "A. Céfazoline 2g IVL\nB. Amoxicilline/Clavulanate 2g IVL\nC. Pas d'antibioprophylaxie recommandée\nD. Clindamycine 900mg IVL"
    )
    assert extract_mcq_option_subqueries(mcq_drugs) == []

    # 3. Composite multi-act surgical query decomposes into atomic sub-queries
    comp = (
        "Quelle antibioprophylaxie pour une splénectomie d'hémostase associée à "
        "la pose d'un fixateur externe sur fracture fermée du fémur chez un polytraumatisé ?"
    )
    subqs = extract_composite_procedure_subqueries(comp)
    assert len(subqs) == 2
    assert any("splénectomie" in s.lower() for s in subqs)
    assert any("fixateur externe" in s.lower() for s in subqs)

    # 4. Drug-only MCQ strips distractor drug options before retrieval (prevents distractor leakage!)
    from rag_sfar.retrieval.crag import strip_mcq_distractor_options

    stripped = strip_mcq_distractor_options(mcq_drugs)
    assert "Amoxicilline" not in stripped and "prothèse de genou" in stripped
    # Comparative act MCQ preserves full options for option-aware retrieval
    assert "Amygdalectomie" in strip_mcq_distractor_options(mcq_acts)

    # 5. 1-to-1 parallel <li> rowspan de-merging on contradictory PAS D'ABP vs Céfazoline tables
    html_tbl = """
    <table>
      <thead><tr><th>Actes</th><th>Molécules</th><th>Dose</th></tr></thead>
      <tbody>
        <tr>
          <td rowspan="2"><ul><li>▪ Septo-rhinoplastie sans greffe</li><li>▪ Septo-rhinoplastie avec greffe</li></ul></td>
          <td colspan="2">PAS D'ANTIBIOPROPHYLAXIE</td>
        </tr>
        <tr><td>Céfazoline</td><td>2g IVL</td></tr>
      </tbody>
    </table>
    """
    pt = parse_html_table(html_tbl)
    cards = pt.to_row_cards()
    assert len(cards) == 2
    assert "sans greffe" in cards[0] and "PAS D'ANTIBIOPROPHYLAXIE" in cards[0] and "Céfazoline" not in cards[0]
    assert "avec greffe" in cards[1] and "Céfazoline" in cards[1] and "PAS D'ANTIBIOPROPHYLAXIE" not in cards[1]









