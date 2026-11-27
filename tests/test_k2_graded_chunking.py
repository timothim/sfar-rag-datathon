"""K2 switches of the table_aware_sota chunker: off by default, byte-identical output when off,
and the generic rules on synthetic text (no corpus text in this file)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rag_sfar.ingestion import chunker as ch
from rag_sfar.ingestion.loader import LoadedDocument
from rag_sfar.schemas import DocumentMetadata

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "k2_chunker_baseline_hashes.json"
SWITCHES = ("RAG_SFAR_CHUNK_GRADE_HEADINGS", "RAG_SFAR_CHUNK_GRADES", "RAG_SFAR_CHUNK_REC_IDS", "RAG_SFAR_CHUNK_BIBLIO")


@pytest.fixture(autouse=True)
def _switches_off(monkeypatch):
    for k in SWITCHES:
        monkeypatch.delenv(k, raising=False)


def test_switches_off_by_default():
    o = ch.ChunkOptions()
    assert not (o.grade_heading_as_text or o.extended_grades or o.extended_rec_ids or o.unheaded_biblio)


def test_switches_read_from_environment(monkeypatch):
    monkeypatch.setenv("RAG_SFAR_CHUNK_GRADE_HEADINGS", "1")
    assert ch.ChunkOptions().grade_heading_as_text


@pytest.mark.skipif(not (ROOT / "data/sfar_recommendations/output").exists(), reason="corpus not available")
def test_switches_off_output_byte_identical_to_frozen_chunker():
    """All 265 documents (>= 10 required): chunk JSON hashed per document equals the snapshot
    taken with the chunker before the K2 change (the code that built index/tas_v6)."""
    from rag_sfar.ingestion.loader import load_sfar_corpus

    docs = load_sfar_corpus(ROOT / "data/sfar_recommendations/output", updates_dir=ROOT / "data/corpus_updates")
    hashes: dict[str, "hashlib._Hash"] = {}
    for c in ch.chunk_corpus(docs, options=ch.ChunkOptions()):
        hashes.setdefault(c.doc_id, hashlib.sha256()).update(c.model_dump_json().encode())
    got = {k: v.hexdigest() for k, v in hashes.items()}
    want = json.loads(FIXTURE.read_text())
    assert len(want) >= 10
    assert got == want


def _doc(text: str) -> LoadedDocument:
    meta = DocumentMetadata(doc_id="synthetic_doc", title="Synthetic guideline", filename="x.md", md_path="x.md")
    return LoadedDocument(metadata=meta, text=text)


GRADED = (
    "# CHAMP 1 : Test\n\n### Question 1\n\n**R1.1 – Il est recommandé de faire A chez le patient X.**\n\n"
    "### GRADE 1 (recommandation forte)\n\nArgumentaire : texte d'argumentaire.\n\n"
    "**R1.2 – Il est probablement recommandé de faire B.**\n\n### Avis d'experts (Accord FORT)\n\nArgumentaire : autre texte.\n"
)


def test_grade_heading_stays_with_its_statement():
    off = ch._chunk_table_aware_sota(_doc(GRADED), options=ch.ChunkOptions())
    assert any("GRADE 1" in c.section_path for c in off)
    on = ch._chunk_table_aware_sota(_doc(GRADED), options=ch.ChunkOptions(grade_heading_as_text=True))
    assert not any("GRADE" in c.section_path or "Avis" in c.section_path for c in on)
    joined = "\n".join(c.text for c in on)
    assert joined.index("R1.1") < joined.index("GRADE 1") < joined.index("R1.2") < joined.index("Avis d'experts")


def test_grade_line_detection_is_form_based():
    assert ch._is_grade_line("GRADE 2+ (Accord FORT)")
    assert ch._is_grade_line("Avis d'experts (Accord fort)")
    assert ch._is_grade_line("G1+")
    assert not ch._is_grade_line("GRADE 1 : il est recommandé de faire A")
    assert not ch._is_grade_line("Méthode GRADE")


def test_extended_grades_and_statement_typing():
    text = "# Titre\n\n*Il est recommandé de faire A chez le patient X (grade B).*\n"
    off = ch._chunk_table_aware_sota(_doc(text), options=ch.ChunkOptions())
    on = ch._chunk_table_aware_sota(_doc(text), options=ch.ChunkOptions(extended_grades=True))
    assert off[0].chunk_type == "callout_footnote" and not off[0].grade_levels
    assert on[0].chunk_type == "recommendation_box" and on[0].grade_levels == ["grade B"]
    method = "# Méthode\n\nUne recommandation forte : GRADE 1 « il est recommandé de faire » ; GRADE 2 « il est probablement recommandé ».\n"
    assert ch._chunk_table_aware_sota(_doc(method), options=ch.ChunkOptions(extended_grades=True))[0].chunk_type == "prose"


def test_extended_rec_ids():
    text = "# Titre\n\nR 3 – Il faut faire A chez le patient de chirurgie programmée (GRADE 2+).\n"
    on = ch._chunk_table_aware_sota(_doc(text), options=ch.ChunkOptions(extended_rec_ids=True))
    assert on[0].chunk_type == "recommendation_box" and on[0].recommendation_ids == ["R 3"]


def test_unheaded_bibliography_flagged():
    refs = "\n".join(f"[{i}] Martin JP, Durand A, et al. A study title {i}. J Test 2015;{i}(2):{10 + i}-20." for i in range(1, 6))
    text = "# Question 1\n\nTexte clinique sur la question, sans aucune citation.\n\n# Question 2\n\n" + refs + "\n"
    on = ch._chunk_table_aware_sota(_doc(text), options=ch.ChunkOptions(unheaded_biblio=True))
    assert any(c.is_reference_section and c.chunk_type == "references" for c in on)
    assert any(not c.is_reference_section for c in on)
    arg = "Dans l'étude de Martin et al. [3], puis Durand et al. [4] et Petit et al. [5], le risque était réduit."
    assert not ch._looks_like_bibliography(arg)
