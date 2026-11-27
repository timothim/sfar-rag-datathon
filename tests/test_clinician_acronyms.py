"""The clinicians' abbreviation dictionary merged into the lexicon (scripts/build_clinician_acronyms.py)."""

from __future__ import annotations

import re

from rag_sfar.generation.profile import PRODUCTION
from rag_sfar.retrieval.clinician_acronyms import CLINICIAN_ACRONYMS
from rag_sfar.retrieval.medical_lexicon import (
    FRENCH_STOPWORDS,
    HANDWRITTEN_ACRONYMS,
    MEDICAL_ACRONYMS,
    expand_medical_query,
)
from rag_sfar.retrieval.router import analyze_query

FUNCTION_WORDS = {"pas", "ne", "ni", "et", "ou", "de", "du", "des", "le", "la", "les", "ce", "sa", "ta", "en", "au"}


def test_dictionary_is_merged_and_handwritten_entries_win() -> None:
    assert len(CLINICIAN_ACRONYMS) > 300
    assert set(CLINICIAN_ACRONYMS).isdisjoint(HANDWRITTEN_ACRONYMS)
    assert len(MEDICAL_ACRONYMS) == len(CLINICIAN_ACRONYMS) + len(HANDWRITTEN_ACRONYMS)
    for abbr, expansion in HANDWRITTEN_ACRONYMS.items():
        assert MEDICAL_ACRONYMS[abbr] == expansion


def test_no_entry_can_fire_on_french_function_words() -> None:
    for abbr in CLINICIAN_ACRONYMS:
        assert abbr.lower() not in FUNCTION_WORDS, abbr
        assert abbr.lower() not in FRENCH_STOPWORDS, abbr
    # text typed in capitals: the negation and the articles are never read as abbreviations
    _, expanded = expand_medical_query("NE PAS DONNER DE CE TRAITEMENT ET SURVEILLER LES SIGNES")
    assert expanded == {}


def test_entries_are_single_tokens_with_one_plain_long_form() -> None:
    for abbr, long_form in CLINICIAN_ACRONYMS.items():
        assert re.fullmatch(r"[A-Za-zÀ-ÿ0-9]{2,12}", abbr), abbr
        assert long_form.strip() and long_form == " ".join(long_form.split()), abbr
        assert not re.search(r"\s+ou\s+", long_form), abbr


def test_frozen_profile_never_applies_the_lexicon() -> None:
    cfg = PRODUCTION.retrieval_config()
    assert cfg.use_medical_lexicon is False
    query = " ".join(list(CLINICIAN_ACRONYMS)[:20] + list(HANDWRITTEN_ACRONYMS)[:20])
    analysis = analyze_query(query, use_lexicon=cfg.use_medical_lexicon)
    assert analysis.expanded_query == query
    assert not analysis.acronyms_expanded
