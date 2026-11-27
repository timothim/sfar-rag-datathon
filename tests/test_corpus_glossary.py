"""Corpus abbreviation glossary (Q1 robustness study): extraction, expansion, isolation from the
frozen retrieval pipeline. Texts are generic sentences, not evaluation questions."""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

from rag_sfar.retrieval.corpus_glossary import (
    GlossaryExpander,
    build_glossary,
    clean_long_form,
    extract_definitions,
    is_abbreviation,
    schwartz_hearst,
)


def test_inline_definitions():
    text = "Le recours à la ventilation non invasive (VNI) est discuté. La pression artérielle moyenne (PAM) cible est 65."
    pairs = {(a, lf) for a, lf, _ in extract_definitions(text)}
    assert ("VNI", "ventilation non invasive") in pairs
    assert ("PAM", "pression artérielle moyenne") in pairs


def test_abbreviation_then_long_form_and_rejections():
    pairs = {(a, lf) for a, lf, _ in extract_definitions("On utilise une HBPM (héparine de bas poids moléculaire) en relais.")}
    assert ("HBPM", "héparine de bas poids moléculaire") in pairs
    # letters not alignable -> rejected; roman numerals and single capitals are not abbreviations
    assert not extract_definitions("un traitement prolongé (XYZ) est proposé")
    assert not is_abbreviation("IV") and not is_abbreviation("Grade")
    assert clean_long_form(schwartz_hearst("IOT", "après échec d'intubation orotrachéale")) == "intubation orotrachéale"


def test_glossary_section_lines_and_tables():
    text = "AVK : antivitamine K\nAbréviation : SFAR | Signification : Société Française d'Anesthésie et de Réanimation"
    pairs = {(a, lf) for a, lf, _ in extract_definitions(text, glossary_context=True)}
    assert ("AVK", "antivitamine K") in pairs
    assert ("SFAR", "Société Française d'Anesthésie et de Réanimation") in pairs
    assert not extract_definitions(text, glossary_context=False) or all(p[2].startswith("inline") for p in extract_definitions(text))


def test_build_and_expand_both_directions():
    chunks = [
        SimpleNamespace(doc_id=f"d{i}", section_path="", text="La ventilation non invasive (VNI) est utile.")
        for i in range(2)
    ]
    g = build_glossary(chunks)
    e = g["entries"]["VNI"]
    assert e["long_forms"][0]["docs"] == 2
    exp = GlossaryExpander([{"abbr": "VNI", "long_form": "ventilation non invasive", "variants": ["ventilation non invasive"]}])
    q1, a1 = exp.expand("Indications de la VNI en postopératoire ?")
    assert q1.endswith("(ventilation non invasive)") and a1 == {"VNI": "ventilation non invasive"}
    q2, a2 = exp.expand("Indications de la ventilation non-invasive en postopératoire ?")
    assert q2.endswith("(VNI)")
    q3, a3 = exp.expand("Question sans sigle connu")
    assert a3 == {} and q3 == "Question sans sigle connu"


def test_capitalised_french_word_is_not_an_abbreviation():
    exp = GlossaryExpander([{"abbr": "PAS", "long_form": "pression artérielle systolique", "variants": ["pression artérielle systolique"]}])
    q, added = exp.expand("Il ne faut PAS arrêter le traitement")
    assert added == {}


def test_frozen_pipeline_does_not_import_the_glossary():
    code = (
        "import sys, rag_sfar.retrieval.pipeline, rag_sfar.evaluation.harness, rag_sfar.evaluation.ablation;"
        "assert 'rag_sfar.retrieval.corpus_glossary' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
