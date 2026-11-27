"""Ingestion tests (B2): tables, OCR clean-up, populations, notes, units, editions.

Synthetic snippets only (no benchmark or corpus text)."""

from __future__ import annotations

from rag_sfar.ingestion.chunker import ChunkOptions, _chunk_table_aware_sota, _hard_split, chunk_corpus
from rag_sfar.ingestion.loader import (
    LoadedDocument,
    _apply_abrogated_twins,
    _apply_explicit_update_mentions,
)
from rag_sfar.ingestion.population import infer_chunk_populations, population_terms
from rag_sfar.ingestion.table_parser import parse_html_table
from rag_sfar.ingestion.text_cleaning import NulRepairer, clean_chunk_text, latex_to_text, mermaid_to_text
from rag_sfar.schemas import DocumentMetadata


def _meta(doc_id: str = "d1", title: str = "Recommandations de test", **kw) -> DocumentMetadata:
    base = dict(doc_id=doc_id, title=title, filename=f"{doc_id}.pdf", md_path="x.md", effective_year=2024)
    base.update(kw)
    return DocumentMetadata(**base)


# ---------------------------------------------------------------- tables


def test_cell_text_keeps_text_outside_lists_and_nested_items_once():
    html = (
        "<table><tr><th>Situation</th><th>Conduite</th></tr>"
        "<tr><td><b>Si allergie :</b><ul><li>Molécule X</li><li>Molécule Y<ul><li>dose A</li></ul></li></ul></td>"
        "<td>Option 1</td></tr></table>"
    )
    t = parse_html_table(html)
    cell = t.row_groups[0].rows[0][0]
    assert "Si allergie" in cell and "Molécule X" in cell
    assert cell.count("dose A") == 1


def test_cell_line_breaks_join_continuations():
    html = "<table><tr><th>A</th><th>B</th></tr><tr><td>x</td><td>1 g si durée &gt; 4h,<br/>puis toutes les 4h<br/>jusqu'à la fin</td></tr></table>"
    t = parse_html_table(html)
    assert t.row_groups[0].rows[0][1] == "1 g si durée > 4h, puis toutes les 4h jusqu'à la fin"


def test_full_width_note_row_is_kept_and_attached():
    html = (
        "<table><tr><th>Acte</th><th>Molécule</th><th>Dose</th></tr>"
        "<tr><td>Acte alpha</td><td>Molécule Z</td><td>1 g</td></tr>"
        '<tr><td colspan="3">En cas de contamination majeure, considérer un traitement prolongé*</td></tr>'
        "</table>"
    )
    t = parse_html_table(html)
    assert t.row_groups[-1].notes == ["En cas de contamination majeure, considérer un traitement prolongé*"]
    cards = t.to_row_cards()
    assert any("Note : En cas de contamination majeure" in c for c in cards)
    assert any("contamination majeure" in m for m in t.to_markdown_chunks())


def test_label_row_heads_following_rows_and_trailing_label_is_kept():
    html = (
        "<table><tr><th>Acte</th><th>Molécule</th></tr>"
        '<tr><td colspan="2"><b>Chirurgie du groupe B</b></td></tr>'
        "<tr><td>Acte beta</td><td>Molécule W</td></tr>"
        '<tr><td colspan="2"><b>Chirurgie du groupe C</b></td></tr>'
        "</table>"
    )
    t = parse_html_table(html)
    assert t.row_groups[0].sub_banner == "Chirurgie du groupe B"
    assert any("Chirurgie du groupe C" in " ".join(r) for g in t.row_groups for r in g.rows)


def test_headerless_table_gets_cards_without_fake_column_names():
    html = "<table><tr><td><ul><li>▪ Acte gamma</li><li>▪ Acte delta</li></ul></td><td>PAS DE TRAITEMENT</td><td>Avis d'experts</td></tr></table>"
    t = parse_html_table(html)
    md = t.to_markdown_chunks()[0]
    assert "Col 1" not in md and "Acte gamma" in md
    cards = t.to_row_cards(section="Chirurgie gamma", require_headers=False)
    assert cards and "Section : Chirurgie gamma" in cards[0] and "Colonne" not in cards[0]


def test_page_split_rowspan_takes_back_its_key():
    html = "<table><tr><td></td><td>Molécule V</td><td>2 g</td></tr></table>"
    t = parse_html_table(html, carry_first_cell="Acte epsilon")
    assert t.row_groups[0].rows[0][0] == "Acte epsilon"
    assert t.carried_first_cell == "Acte epsilon"


def test_chunker_cards_carry_section_scope_note_and_footnotes():
    md = (
        "# CHAMP 3. Recommandations chez l'enfant\n\n## PARTIE 1 : Chirurgie zeta\n\n"
        "Les doses de ce tableau concernent l'enfant de moins de 40 kg. Au-delà, voir le tableau adulte.\n\n"
        "### Sous-groupe eta\n\n"
        "<table><tr><th>Acte</th><th>Molécule</th><th>Dose</th></tr>"
        "<tr><td>Acte theta</td><td>Molécule Q *</td><td>10 mg/kg</td></tr></table>\n\n"
        "\\* dose maximale de 2 g par injection.\n"
    )
    chunks = _chunk_table_aware_sota(LoadedDocument(metadata=_meta(), text=md), options=ChunkOptions())
    card = next(c for c in chunks if c.chunk_type == "table_row_card")
    assert "Section :" in card.text and "Sous-groupe eta" in card.text
    assert "Périmètre : Les doses de ce tableau" in card.text
    assert "Note (*) : dose maximale de 2 g" in card.text
    assert card.populations == ["pediatrie"] and card.population_source == "table"
    assert card.table_id and card.indexed_text.endswith(card.text)


def test_hard_split_caps_unpunctuated_text():
    text = " ".join(["mot"] * 3000)
    parts = _hard_split(text, 2400)
    assert max(len(p) for p in parts) <= 2400 and sum(len(p.split()) for p in parts) == 3000


# ---------------------------------------------------------------- OCR clean-up


def test_latex_entities_and_tags_are_cleaned():
    out = clean_chunk_text("IMC $\\geq 30$ kg/m$^2$, durée &gt; 4h, SpO<sub>2</sub> &amp;gt; 90 %, $IC_{95}$")
    assert "≥ 30" in out and "m²" in out and "> 4h" in out and "SpO2" in out and "IC95" in out
    assert latex_to_text(r"\text{mmHg} \times 10^{3}") == "mmHg × 10³"


def test_nul_pairs_are_repaired_from_vocabulary():
    rep = NulRepairer(["La réserve fonctionnelle est évaluée."])
    assert rep("R\x00\x00serve fonctionnelle") == "Réserve fonctionnelle"


def test_images_and_mermaid_become_readable():
    out = clean_chunk_text("![Blue square logo](a.png) Texte ![Flowchart showing the decision tree for the airway](b.png)")
    assert "logo" not in out and "description automatique en anglais" in out
    flow = mermaid_to_text('graph TD; A["Choc ?"] -- OUI --> B[Traitement X]; A -- NON --> C[Surveillance]')
    assert "Choc ? → (OUI) Traitement X" in flow and "Choc ? → (NON) Surveillance" in flow


# ---------------------------------------------------------------- populations


def test_population_terms_and_negation():
    assert population_terms("Chez l'enfant de moins de 6 ans") == {"pediatrie"}
    assert population_terms("chez l'enfant (hors néonatalogie)") == {"pediatrie"}
    assert population_terms("Femme enceinte") == {"obstetrique"}
    assert population_terms("se référer au tableau adulte") == set()
    pops, src = infer_chunk_populations("CHAMP 2 adultes > PARTIE 1 > Chez l'enfant")
    assert pops == ["pediatrie"] and src == "section"
    pops, src = infer_chunk_populations("Introduction", doc_title="Prise en charge du nouveau-né")
    assert set(pops) == {"neonatal", "pediatrie"} and src == "document"


# ---------------------------------------------------------------- recommendation units


def test_recommendation_units_are_added_outside_the_reading_chain():
    md = (
        "## Méthode\n\nUne recommandation forte s'exprime par « il faut faire » (GRADE 1+) et une "
        "recommandation faible par « il faut probablement faire » (GRADE 2+).\n\n"
        "## Champ 1. Prévention\n\n**R1.1 – Il faut probablement administrer la molécule A avant "
        "l'incision pour réduire le risque de complication.**\n\n**GRADE 2+ (Accord fort)**\n\n"
        "Argumentaire : texte de justification assez long pour former un paragraphe.\n"
    )
    doc = LoadedDocument(metadata=_meta(language="fr"), text=md)
    chunks = chunk_corpus([doc], options=ChunkOptions(reco_units=True))
    units = [c for c in chunks if c.chunk_type == "recommendation_unit"]
    assert len(units) == 1
    u = units[0]
    assert "R1.1" in u.text and "GRADE 2+" in u.text and u.reco_strength == "grade_2_plus"
    assert u.source_chunk_id and u.prev_chunk_id == u.source_chunk_id
    assert all(c.next_chunk_id != u.chunk_id for c in chunks)


# ---------------------------------------------------------------- editions


def test_explicit_update_mention_supersedes_older_edition_of_same_subject():
    old = LoadedDocument(_meta("old", "Urgences alpha extrahospitalières", effective_year=2010, reco_family_id="f1"), "x")
    other = LoadedDocument(_meta("oth", "Choix du soluté beta", effective_year=2010, reco_family_id="f3"), "x")
    new = LoadedDocument(
        _meta("new", "Urgences alpha en médecine d'urgence", effective_year=2022, reco_family_id="f2"),
        "Intro.\n\nEn 2010, la société a publié des recommandations sur les urgences alpha "
        "extrahospitalières. Une mise à jour de ces recommandations semblait nécessaire ; le soluté "
        "beta a aussi été traité en 2010 (choix du soluté beta).\n",
    )
    _apply_explicit_update_mentions([old, other, new])
    assert old.metadata.is_latest_edition is False and old.metadata.superseded_by == "new"
    assert "mention explicite" in old.metadata.supersession_evidence
    assert other.metadata.is_latest_edition is True  # cited, but a different subject


def test_near_copy_of_abrogated_document_is_abrogated():
    body = " ".join(f"phrase numéro {i} du texte de préconisation" for i in range(300))
    ab = LoadedDocument(_meta("ab", "Préconisations", is_active=False, effective_year=2022), body)
    twin = LoadedDocument(_meta("tw", "Préconisations", effective_year=2022), body + " fin")
    other = LoadedDocument(_meta("ot", "Autre"), "texte sans rapport " * 200)
    _apply_abrogated_twins([ab, twin, other])
    assert twin.metadata.is_active is False and "quasi-copie" in twin.metadata.supersession_evidence
    assert other.metadata.is_active is True


# ---------------------------------------------------------------- fixes after review R1


def test_markdown_table_rows_and_empty_cells_survive_cleanup():
    md = "| Acte | Molécule | Dose |\n| --- | --- | --- |\n| A | Aucune |  |\n| B | Molécule Z | 2 g |"
    out = clean_chunk_text(md)
    lines = out.splitlines()
    assert len(lines) == 4
    assert [ln.count("|") for ln in lines] == [4, 4, 4, 4]
    # orphan cell fragments outside a table are still joined
    assert clean_chunk_text("<td>a</td><td>b</td>") == "| a | b |"


def test_micro_units_never_become_mug():
    from rag_sfar.ingestion.table_parser import parse_html_table

    assert "µg/kg/min" in clean_chunk_text(r"<math>\leq 0,1 \mu\text{g/kg/min}</math>")
    assert clean_chunk_text(r"$\mu g$ et \mu mol") == "µg et µmol"
    t = parse_html_table("<table><tr><th>A</th></tr><tr><td>3 à 5 <math>\\mu</math>g/kg</td></tr></table>")
    assert t.row_groups[0].rows[0][0] == "3 à 5 µg/kg"
    assert "mug" not in clean_chunk_text(r"25 $\mu\text{g} L^{-1}$")


def test_value_and_unit_split_by_line_break_stay_together():
    from rag_sfar.ingestion.table_parser import parse_html_table

    t = parse_html_table("<table><tr><th>A</th><th>B</th></tr><tr><td>x</td><td>Molécule ≤ 5<br>µg/kg/min</td></tr></table>")
    assert t.row_groups[0].rows[0][1] == "Molécule ≤ 5 µg/kg/min"


def test_mermaid_edge_labels_with_comparisons_bidirectional_and_nested_brackets():
    block = (
        "graph TD\n    A[Score] -- SCORE > 26\nOu AUTRE > 22 --> B[Traitement X]\n"
        "    A -- SCORE < 8 --> C[Réduction Y]\n    C <--> D[Encadré 0,01 mg/kg]\n"
        "    D --> E[Si [Molécule] > 50 ng/mL]\n"
    )
    out = mermaid_to_text(block)
    for tok in ("26", "22", "Traitement X", "Réduction Y", "0,01 mg/kg", "[Molécule] > 50 ng/mL"):
        assert tok in out


def test_mermaid_fidelity_guard_keeps_raw_block_when_content_is_lost():
    from rag_sfar.ingestion import text_cleaning as tc

    block = "graph TD\n    A[Début] --> B[Dose 5 mg]\n"
    original = tc.mermaid_to_text
    try:
        tc.mermaid_to_text = lambda b: "[Organigramme (converti depuis le schéma OCR)]\n- Début"
        out = tc.mermaid_block_to_text(block)
    finally:
        tc.mermaid_to_text = original
    assert "syntaxe d'origine conservée" in out and "Dose 5 mg" in out


def test_population_negation_after_term_and_in_exclusion_parenthesis():
    assert population_terms("Ventilation au cours de l'insuffisance aiguë (nouveau-né exclu)") == set()
    assert population_terms("Prise en charge (except cross transmission and neonate)") == set()
    assert population_terms("Enfants exclus de l'étude") == set()


def test_population_not_taken_from_sentences_or_enumerations():
    pops, _ = infer_chunk_populations("PARTIE 6 : CHIRURGIE ALPHA, BETA, OBSTETRIQUE ET GAMMA > Sous-groupe")
    assert pops == []
    pops, _ = infer_chunk_populations("Enfants – Les experts suggèrent d'utiliser la technique delta chez l'enfant")
    assert pops == []


def test_short_label_rows_ending_with_period_or_call_mark_are_labels():
    html = (
        "<table><tr><th>Germe</th><th>Traitement</th></tr>"
        '<tr><td colspan="2"><i>Groupe alpha sp.</i></td></tr><tr><td>alpha 1</td><td>X</td></tr>'
        '<tr><td colspan="2">Chirurgie du groupe beta *</td></tr><tr><td>beta 1</td><td>Y</td></tr>'
        "</table>"
    )
    t = parse_html_table(html)
    assert [g.sub_banner for g in t.row_groups] == ["Groupe alpha sp.", "Chirurgie du groupe beta *"]
    assert all(not g.notes for g in t.row_groups)


def test_nul_pair_is_not_guessed_without_vocabulary_evidence():
    rep = NulRepairer(["La réserve est évaluée."])
    assert rep("(\x00\x00 3 fois)") == "(� 3 fois)"
    assert rep("Xy\x00\x00z") == "Xy�z"


def test_explicit_update_rule_ignores_bibliography_entries():
    old = LoadedDocument(_meta("old", "Prévention alpha beta gamma", effective_year=2011, reco_family_id="f1"), "x")
    new = LoadedDocument(
        _meta("new", "Prévention alpha beta gamma chez l'adulte", effective_year=2024, reco_family_id="f2"),
        "Intro.\n\n[1] Auteur A. Prévention alpha beta gamma. Actualisation 2011. Revue 2011;1:1.\n",
    )
    _apply_explicit_update_mentions([old, new])
    assert old.metadata.is_latest_edition is True


# ---------------------------------------------------------------- corpus patches (official errata)


def _write_patch_corpus(tmp_path, text: str, original: str, corrected: str, sha: str | None = None):
    import hashlib
    import json

    corpus = tmp_path / "sfar" / "output"
    md_dir = corpus / "chandra" / "2006" / "doc_alpha"
    md_dir.mkdir(parents=True)
    md = md_dir / "doc_alpha.md"
    md.write_text(text, encoding="utf-8")
    (corpus / "discovery.json").write_text(
        json.dumps({"documents": [{"filename": "doc_alpha.pdf", "year": 2006, "title": "Document alpha", "sha256": "abc123"}]}),
        encoding="utf-8",
    )
    upd = tmp_path / "updates"
    upd.mkdir()
    (upd / "updates_manifest.json").write_text(json.dumps({"documents": []}), encoding="utf-8")
    patch = {
        "id": "T-1",
        "document": "x/chandra/2006/doc_alpha/doc_alpha.md",
        "document_sha256": sha or hashlib.sha256(md.read_bytes()).hexdigest(),
        "original": original,
        "corrected": corrected,
        "evidence": "erratum page 2",
        "pdf_pages": [1, 2],
    }
    (upd / "patches.json").write_text(json.dumps({"patches": [patch]}), encoding="utf-8")
    return corpus, upd


def test_corpus_patch_is_applied_visibly_and_recorded(tmp_path):
    from rag_sfar.ingestion.loader import PATCH_NOTE, load_sfar_corpus

    text = "# Titre\n\nLa dose de la molécule A est de 10 mg/kg en intraveineux.\n"
    corpus, upd = _write_patch_corpus(tmp_path, text, "est de 10 mg/kg en", "est de 10 µg/kg en")
    docs = load_sfar_corpus(corpus, updates_dir=upd)
    d = docs[0]
    assert d.metadata.applied_patches == ["T-1"]
    assert "10 µg/kg [" + PATCH_NOTE + " : « 10 mg/kg »] en intraveineux" in d.text
    chunks = chunk_corpus(docs, options=ChunkOptions())
    assert any(c.corpus_patch_ids == ["T-1"] for c in chunks)


def test_corpus_patch_fails_loudly_on_sha_mismatch_or_non_unique_original(tmp_path):
    import pytest

    from rag_sfar.ingestion.loader import CorpusPatchError, load_sfar_corpus

    corpus, upd = _write_patch_corpus(tmp_path, "A 10 mg. B.\n", "10 mg", "10 µg", sha="0" * 64)
    with pytest.raises(CorpusPatchError):
        load_sfar_corpus(corpus, updates_dir=upd)


def test_corpus_patch_fails_when_original_is_not_unique(tmp_path):
    import pytest

    from rag_sfar.ingestion.loader import CorpusPatchError, load_sfar_corpus

    corpus, upd = _write_patch_corpus(tmp_path, "A 10 mg. B 10 mg.\n", "10 mg", "10 µg")
    with pytest.raises(CorpusPatchError):
        load_sfar_corpus(corpus, updates_dir=upd)


def test_strength_glyphs_dropped_before_a_grade_label_only():
    out = clean_chunk_text("Molécule A | ●●● (GRADE 2) | [◉◎◎ (Avis d'experts)] | ○○ case vide | ○ Patients")
    assert "●" not in out and "◉" not in out
    assert "(GRADE 2)" in out and "(Avis d'experts)" in out and "○○ case vide" in out and "○ Patients" in out
