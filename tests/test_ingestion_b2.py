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
