"""K3: header carry-over between non-contiguous tables (RAG_SFAR_TABLE_ADJACENT_HEADERS).

Synthetic snippets only; the byte-identity test reads corpus documents from data/ at run time
(skipped when data/ is absent) and compares against digests made with the parser before K3."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import rag_sfar.ingestion.table_parser as tp
from rag_sfar.ingestion.table_parser import gap_allows_continuation, headers_look_like_column_names, parse_html_table

ROOT = Path(__file__).resolve().parents[1]
HDRS = ["Acte", "Produit", "Dose"]
ROW = "<table><tr><td>Acte A</td><td>Produit B</td><td>1 unité</td></tr></table>"


def test_switch_is_off_by_default():
    assert tp.ADJACENT_HEADERS is False


def test_switch_off_keeps_far_inheritance(monkeypatch):
    monkeypatch.setattr(tp, "ADJACENT_HEADERS", False)
    t = parse_html_table(ROW, previous_headers=HDRS, previous_is_contiguous=False)
    assert t.inherited_headers and t.headers == HDRS


def test_switch_on_rules(monkeypatch):
    monkeypatch.setattr(tp, "ADJACENT_HEADERS", True)
    assert parse_html_table(ROW, previous_headers=HDRS, previous_is_contiguous=True).inherited_headers
    assert not parse_html_table(ROW, previous_headers=HDRS, previous_is_contiguous=False).inherited_headers
    ok = parse_html_table(ROW, previous_headers=HDRS, previous_is_contiguous=False, continuation_gap="\n### Sous-titre\nRunning title\n")
    assert ok.inherited_headers
    para = "Texte. " * 60
    assert not parse_html_table(ROW, previous_headers=HDRS, previous_is_contiguous=False, continuation_gap=para).inherited_headers
    cap = "\nTableau 3\nAutre chose\n"
    assert not parse_html_table(ROW, previous_headers=HDRS, previous_is_contiguous=False, continuation_gap=cap).inherited_headers


def test_header_shape():
    assert headers_look_like_column_names(["Acte", "Dose"])
    assert not headers_look_like_column_names(["Titre de section", "", ""])
    assert not headers_look_like_column_names(["Intervention X", "9", "[6-9]"])
    assert gap_allows_continuation("")
    assert not gap_allows_continuation(None)


def test_switch_off_byte_identical_on_corpus_sample(monkeypatch):
    corpus = ROOT / "data" / "sfar_recommendations" / "output"
    if not corpus.exists():
        pytest.skip("corpus not available")
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from k3_table_digest import table_digests

    from rag_sfar.ingestion.loader import load_sfar_corpus

    monkeypatch.setattr(tp, "ADJACENT_HEADERS", False)
    expected = json.loads((ROOT / "tests" / "fixtures" / "k3_table_parser_baseline_digests.json").read_text())
    assert len(expected) >= 10
    docs = {d.metadata.doc_id: d for d in load_sfar_corpus(corpus, updates_dir=ROOT / "data" / "corpus_updates")}
    for doc_id, digest in expected.items():
        assert table_digests(docs[doc_id].text, parse_html_table) == digest, doc_id
