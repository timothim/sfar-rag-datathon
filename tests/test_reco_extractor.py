"""Tests of the generic recommendation-unit extractor (synthetic snippets only)."""

from __future__ import annotations

from rag_sfar.ingestion.reco_extractor import (
    RecommendationUnit,
    clean_ocr_text,
    declared_recommendation_count,
    extract_corpus,
    extract_recommendations,
)

DOC = {"doc_id": "test_doc", "title": "RFE de test", "effective_year": 2021, "is_latest_edition": True}

# Method section of a classic SFAR GRADE guideline: wording maps to GRADE levels.
SFAR_METHOD = """
## Méthode

La méthode GRADE a été utilisée. Une recommandation forte s'exprime par « il faut faire » (GRADE 1+)
ou « il ne faut pas faire » (GRADE 1-) et une recommandation faible par « il faut probablement faire »
(GRADE 2+) ou « il ne faut probablement pas faire » (GRADE 2-).
"""


def _one(units: list[RecommendationUnit], label: str) -> RecommendationUnit:
    found = [u for u in units if u.reco_label == label]
    assert len(found) == 1, [u.reco_label for u in units]
    return found[0]


def test_paragraph_format_grade_and_agreement():
    md = SFAR_METHOD + """
## Champ 1. Prévention

**Question 1.1 : Faut-il administrer la molécule A en prévention ?**

**R1.1 – Il faut probablement administrer la molécule A avant l'incision pour réduire le risque de complication.**

**GRADE 2+ (Accord fort)**

**Argumentaire :** Plusieurs essais suggèrent un bénéfice modeste (GRADE 1+ dans une autre population).
"""
    units = extract_recommendations(md, DOC)
    u = _one(units, "R1.1")
    assert u.strength == "grade_2_plus"
    assert u.strength_source == "rating"
    assert u.agreement == "fort"
    assert u.field and u.field.startswith("Champ 1")
    assert u.section and u.section.startswith("Question 1.1")
    assert u.statement.startswith("Il faut probablement administrer la molécule A")
    assert "Argumentaire" not in u.statement
    s, e = u.char_span
    assert "R1.1" in md[s:e] and "avant l'incision" in md[s:e]
    assert len(units) == 1


def test_table_box_format_negative_weak():
    md = SFAR_METHOD + (
        '<table border="1"><tr><td><b>R2.1 – Il n\'est probablement pas recommandé de tester la manœuvre B '
        "avant l'induction.</b></td></tr><tr><td style=\"text-align: right;\"><b>(Grade 2-) Accord FORT</b></td></tr>"
        "<tr><td><b>R2.2 – Il est recommandé d'utiliser le dispositif C pour faciliter le geste.</b></td></tr>"
        "<tr><td><b>(Grade 1+) Accord FORT</b></td></tr></table>\n"
    )
    units = extract_recommendations(md, DOC)
    assert _one(units, "R2.1").strength == "grade_2_minus"
    assert _one(units, "R2.2").strength == "grade_1_plus"
    assert _one(units, "R2.2").agreement == "fort"


def test_has_template_strength_read_from_rating_cell_not_wording():
    """In the HAS-style table, "Il est recommandé" can be GRADE 2: the cell wins."""
    md = """
Formulations utilisées : « Il est recommandé de ... » (recommandation faible, qualité des preuves élevée).

<table border="1">
<thead><tr><th colspan="2">RECOMMANDATION</th><th>Niveau de preuve</th></tr></thead>
<tbody>
<tr><td colspan="3"><b>Champ 1. Gestion du matériel</b></td></tr>
<tr>
<td>R1.1.1</td>
<td>En l'absence de critère de difficulté, il est recommandé d'utiliser le dispositif D en première intention pour augmenter le succès.</td>
<td>2</td>
</tr>
<tr>
<td>R1.1.2</td>
<td>Il est recommandé de ne pas utiliser le dispositif E en routine pour limiter les complications.</td>
<td>2</td>
</tr>
<tr>
<td>R1.1.3</td>
<td>Il est recommandé de vérifier le dispositif D avant chaque utilisation pour éviter un échec.</td>
<td>1</td>
</tr>
<tr>
<td>R1.1.4</td>
<td>Les experts suggèrent de former les équipes à l'utilisation du dispositif D.</td>
<td>AE</td>
</tr>
</tbody>
</table>
"""
    units = extract_recommendations(md, DOC)
    assert _one(units, "R1.1.1").strength == "grade_2_plus"
    assert _one(units, "R1.1.2").strength == "grade_2_minus"
    assert _one(units, "R1.1.3").strength == "grade_1_plus"
    assert _one(units, "R1.1.4").strength == "expert_opinion"
    assert _one(units, "R1.1.1").field == "Champ 1. Gestion du matériel"
    assert len(units) == 4


def test_has_template_without_rating_does_not_guess_grade_from_wording():
    md = """
Formulations utilisées : « Il est recommandé de ... » (recommandation faible, qualité des preuves élevée).
Les recommandations sont cotées GRADE 1 ou GRADE 2 ou GRADE 2 selon le cas.

**R3.1 – Il est recommandé de surveiller le paramètre F pendant toute la procédure chez l'adulte.**
"""
    u = _one(extract_recommendations(md, DOC), "R3.1")
    assert u.strength == "unknown"
    assert u.strength_source == "none"


def test_wording_fallback_in_classic_sfar_document():
    md = SFAR_METHOD + """
**R4.1 – Il ne faut probablement pas administrer la molécule G en routine chez le patient âgé.**

Paragraphe suivant sans rapport avec la cotation.
"""
    u = _one(extract_recommendations(md, DOC), "R4.1")
    assert u.strength == "grade_2_minus"
    assert u.strength_source == "wording"


def test_expert_opinion_rpp_format():
    md = """
**R3.2 - Les experts suggèrent de réaliser une évaluation H avant toute sortie du patient de l'unité.**

Avis d'experts (Accord Fort)
"""
    u = _one(extract_recommendations(md, DOC), "R3.2")
    assert u.strength == "expert_opinion"
    assert u.strength_source == "rating"
    assert u.agreement == "fort"


def test_no_recommendation():
    md = """
**R2.6.1. Les données de la littérature ne permettent pas d'émettre de recommandation concernant la technique J chez l'enfant.**

**ABSENCE DE RECOMMANDATION**
"""
    u = _one(extract_recommendations(md, DOC), "R2.6.1")
    assert u.strength == "no_recommendation"


def test_label_glued_to_previous_reference_line():
    md = SFAR_METHOD + """
[6] Auteur A, Auteur B. Titre d'un article. Revue 2001;29:383-7**R2.3 – Il est probablement recommandé d'administrer la molécule K à délai d'action court pour l'induction rapide.**

**GRADE 2+ (accord fort)**
"""
    u = _one(extract_recommendations(md, DOC), "R2.3")
    assert u.strength == "grade_2_plus"
    assert u.statement.startswith("Il est probablement recommandé")


def test_statement_keeps_list_after_colon_and_reads_rating_after_list():
    md = """
**R5.1. Les experts suggèrent, en cas d'échec de la première stratégie, de :**

- - **soit augmenter la fréquence d'administration de la molécule L ;**
- - **soit augmenter la dose unitaire de 25 %.**

**AVIS D'EXPERTS (accord fort)**
"""
    u = _one(extract_recommendations(md, DOC), "R5.1")
    assert "augmenter la fréquence" in u.statement and "dose unitaire" in u.statement
    assert "- - " not in u.statement
    assert u.strength == "expert_opinion"


def test_inline_grade_format_without_labels():
    md = """
G1+ = il faut faire.
G2+ = il faut probablement faire.

Recommandation : il faut probablement associer la molécule M à la molécule N chez les patients à haut risque (G2+).

Il ne faut pas administrer la molécule P en cas d'allongement de l'intervalle QT (G1-). Les données sur la molécule Q restent limitées.

La molécule R est recommandée en traitement de secours (G1+).
"""
    units = extract_recommendations(md, DOC)
    strengths = sorted(u.strength for u in units)
    assert strengths == ["grade_1_minus", "grade_1_plus", "grade_2_plus"]
    assert all(u.extraction_mode == "inline_rating" for u in units)
    assert not any("il faut faire" in u.statement.lower() for u in units)  # method definitions excluded


def test_agreement_only_document():
    md = "\n\n".join(
        [
            "La cotation a utilisé une méthode dérivée de la RAND/UCLA.",
            "La surveillance continue du paramètre S est indispensable chez ces patients (accord fort).",
            "Un bilan T est réalisé dès l'admission (accord fort). Un second bilan est réalisé à la sixième heure (accord faible).",
            "La mise en place de protocoles locaux est recommandée (accord fort).",
            "Ces recommandations devront être réactualisées dans un délai de trois ans (accord fort).",
            "Le transfert en unité spécialisée est indiqué en cas d'aggravation clinique (accord fort).",
        ]
    )
    units = extract_recommendations(md, DOC)
    assert len(units) == 5  # the meta statement about the update is excluded
    assert all(u.strength == "unknown" for u in units)
    assert {u.agreement for u in units} == {"fort", "faible"}


def test_rejects_questions_comments_and_vote_tables():
    md = SFAR_METHOD + """
**R1.10 Question : faut-il utiliser la technique U chez l'adulte en ventilation spontanée ?**

<table border="1"><tr><td>R2</td><td>9</td><td>[1-9]</td><td>45/47 (96%)</td></tr>
<tr><td>R3</td><td>je pense qu'il faut distinguer deux situations cliniques différentes ici</td></tr></table>

**R1.11 – Il faut utiliser la technique U chez l'adulte en ventilation spontanée.**

**GRADE 1+ (Accord fort)**
"""
    units = extract_recommendations(md, DOC)
    assert [u.reco_label for u in units] == ["R1.11"]


def test_duplicate_summary_and_template_sentences():
    md = SFAR_METHOD + """
<table border="1"><tr><td>R1.1</td><td>Chez l'enfant opéré d'une chirurgie V, il est recommandé de réaliser une analgésie locorégionale.</td><td>GRADE 1+</td></tr>
<tr><td>R1.2</td><td>Chez l'enfant opéré d'une chirurgie W, il est recommandé de réaliser une analgésie locorégionale.</td><td>GRADE 1+</td></tr></table>

**R1.1 – Chez l'enfant opéré d'une chirurgie V, il est recommandé de réaliser une analgésie locorégionale.**

**GRADE 1+ (Accord fort)**
"""
    units = extract_recommendations(md, DOC)
    assert sorted(u.reco_label for u in units) == ["R1.1", "R1.2"]


def test_numeric_label_without_r_in_labelled_document():
    md = SFAR_METHOD + """
**R5.1 - Il est recommandé de mesurer le paramètre X avant le geste chez tout patient traité.**

**GRADE 1+ (Accord fort)**

**R5.2 - Il est probablement recommandé de mesurer le paramètre Y avant le geste chez le patient traité.**

**GRADE 2+ (Accord fort)**

**5.3 - Chez un patient traité, les experts suggèrent de ne pas répéter la mesure X après le geste.**

### AVIS D'EXPERTS (Accord fort)

**R5.4 - Il faut probablement répéter la mesure Y après le geste chez le patient instable.**

**GRADE 2+ (Accord fort)**

## 6.1 - Organisation des soins

Texte narratif sans cotation.
"""
    units = extract_recommendations(md, DOC)
    assert sorted(u.reco_label for u in units) == ["R5.1", "R5.2", "R5.3", "R5.4"]
    assert _one(units, "R5.3").strength == "expert_opinion"


def test_unit_id_is_stable_and_unique():
    md = SFAR_METHOD + """
**R1.1 – Il faut administrer la molécule Z avant l'incision chirurgicale chez l'adulte.**

**GRADE 1+ (Accord fort)**
"""
    a = extract_recommendations(md, DOC)
    b = extract_recommendations(md, DOC)
    assert [u.unit_id for u in a] == [u.unit_id for u in b]
    assert a[0].unit_id.startswith("test_doc:R1.1:")
    assert a[0].year == 2021 and a[0].is_latest_edition is True and a[0].doc_title == "RFE de test"


def test_clean_ocr_text():
    raw = "IMC $\\geq 40 \\text{ kg/m}^2$ et dose &gt; 2 g, SpO<math>_2</math> &amp;amp; PAM  <math>\\leq 65</math> mmHg **gras**"
    assert clean_ocr_text(raw) == "IMC ≥ 40 kg/m² et dose > 2 g, SpO2 & PAM ≤ 65 mmHg gras"
    assert clean_ocr_text("R\x00\x00éserve d’experts") == "Réserve d'experts"
    assert clean_ocr_text("AR-5HT<sub>3</sub>") == "AR-5HT3"


def test_statement_is_cleaned():
    md = """
**R2.2.1. Chez les patients en situation d'obésité ( $IMC \\geq 40 \\text{ kg/m}^2$ ), les experts suggèrent une dose &lt; 2 mg/kg.**

**AVIS D'EXPERT (accord fort)**
"""
    u = _one(extract_recommendations(md, DOC), "R2.2.1")
    assert "IMC ≥ 40 kg/m²" in u.statement
    assert "< 2 mg/kg" in u.statement
    assert "$" not in u.statement and "&lt;" not in u.statement and "**" not in u.statement


def test_declared_count():
    assert declared_recommendation_count("Le travail des experts a abouti à 27 recommandations.") == 27
    assert declared_recommendation_count("La synthèse a abouti à vingt-quatre recommandations.") == 24
    assert declared_recommendation_count("Le texte aboutissant à un avis d'experts.") is None


def test_extract_corpus_flags_cross_document_duplicates(tmp_path):
    body = SFAR_METHOD + """
**R1.1 – Il faut administrer la molécule Z avant l'incision chirurgicale chez l'adulte.**

**GRADE 1+ (Accord fort)**
"""
    (tmp_path / "a.md").write_text(body, encoding="utf-8")
    (tmp_path / "b.md").write_text(body, encoding="utf-8")
    (tmp_path / "c.md").write_text(body, encoding="utf-8")
    base = {"effective_year": 2020, "is_latest_edition": False, "reco_family_id": "fam1", "title": "T"}
    docs = [
        {**base, "doc_id": "long", "md_path": "b.md", "language": "fr", "doc_role": "argumentaire"},
        {**base, "doc_id": "main", "md_path": "a.md", "language": "fr", "doc_role": "recommandation"},
        {**base, "doc_id": "en", "md_path": "c.md", "language": "en", "doc_role": "traduction_en"},
    ]
    units = extract_corpus(documents=docs, root=tmp_path)
    by_doc = {u.doc_id: u for u in units}
    assert set(by_doc) == {"long", "main"}
    assert by_doc["main"].duplicate_of is None
    assert by_doc["long"].duplicate_of == by_doc["main"].unit_id
    assert by_doc["main"].is_latest_edition is False


def test_legacy_grade_is_not_converted_to_grade():
    md = SFAR_METHOD + """
**R11.** Il est recommandé de réaliser un examen X avant toute intervention de type Y (Grade C).

**R12.** Il est recommandé de ne pas réaliser l'examen X avant une intervention de type Z (Grade AE).

**R13.** Il est fortement recommandé de réaliser l'examen X avant une intervention de type W (Grade A).
"""
    units = extract_recommendations(md, DOC)
    assert _one(units, "R11").strength == "unknown"
    assert _one(units, "R11").strength_raw == "(Grade C)"
    assert _one(units, "R12").strength == "expert_opinion"
    assert "(Grade" not in _one(units, "R13").statement


def test_rated_list_item_gets_its_stem_and_unrated_siblings():
    md = "\n".join(
        [
            "Le premier point est consensuel (accord fort).",
            "Un deuxième point est admis (accord fort).",
            "Un troisième point est admis (accord faible).",
            "Un quatrième point est admis (accord fort).",
            "",
            "Avec la molécule A, le geste B est possible à condition de respecter deux principes :",
            "",
            "- • un délai de 12 heures entre la dernière dose et le geste ;",
            "- • un délai de 24 heures entre le geste et la dose suivante (accord professionnel).",
        ]
    )
    units = extract_recommendations(md, DOC)
    u = next(u for u in units if "dose suivante" in u.statement)
    assert u.statement.startswith("Avec la molécule A")
    assert "12 heures" in u.statement
    assert u.agreement == "professionnel"


def test_statement_continued_after_page_break_table():
    md = """
**R2.6.3 – Chez un patient traité par la molécule A et présentant une hémorragie grave, les experts suggèrent d'arrêter le traitement**<table border="1">
<tr><td><p>anticoagulant et de discuter l'administration d'un antidote.</p></td></tr>
<tr><td><b>AVIS D'EXPERTS (Accord fort)</b></td></tr></table>
"""
    u = _one(extract_recommendations(md, DOC), "R2.6.3")
    assert u.statement.endswith("traitement anticoagulant et de discuter l'administration d'un antidote.")
    assert u.strength == "expert_opinion" and u.strength_source == "rating"


def test_labels_quoted_in_reviewer_comment_tables_are_ignored():
    md = SFAR_METHOD + """
<table border="1"><tr><td>Relecteur</td><td><b>R2</b> : Il faudrait discuter un délai plus court pour la molécule A chez ces patients.</td><td>Non retenu</td></tr></table>

**R2 – Il faut administrer la molécule A pendant 48 heures après le geste chez ces patients.**

**GRADE 1+ (Accord fort)**
"""
    units = extract_recommendations(md, DOC)
    assert len(units) == 1 and units[0].statement.startswith("Il faut administrer")
