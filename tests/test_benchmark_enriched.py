"""benchmark-enrichi adapter (suite abpe171): fragment normalization, evidence metrics, judge
structured fields, backward compatibility of the common format."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from rag_sfar.evaluation import datasets
from rag_sfar.evaluation.datasets import EvalItem, EvidencePassage, EvidenceSet, normalize_layout_fragment
from rag_sfar.evaluation.harness import evidence_metrics, passage_match
from rag_sfar.evaluation.judge import format_expectations, parse_judgement
from rag_sfar.evaluation.judge_io import structured_row_metrics

ROOT = Path(__file__).resolve().parents[1]

LAYOUT = (
    "Actes chirurgicaux ou interventionnels             Molécules   Dose Réinjections et      Force de la\n"
    "§ Prothèse de hanche ou de genou (dont reprise       Céfazoline  2g IVL  1g si durée > 4h,   ◉◎◎ (Avis d’experts)\n"
    "  précoce non septique)                              puis toutes les 4h\n"
    "§ Reconstruction ligamentaire avec utilisation de    Céfazoline  2g IVL  1g si durée > 4h,   ◉◎◎ (Avis d’experts)\n"
    "  matériel (vis d’interférence)\n"
)

ROW_CARD = ("Actes chirurgicaux ou interventionnels : Prothèse de hanche ou de genou (dont reprise précoce non septique) | "
            "Molécules : Céfazoline | Dose initiale : 2g IVL | Réinjections et durée : 1g si durée > 4h | "
            "Force de la recommandation : ●●● (Avis d'experts)")
OTHER_ROW = ("Actes chirurgicaux ou interventionnels : Arthroscopie sans matériel | Molécules : Céfazoline | "
             "Dose initiale : 2g IVL | Force de la recommandation : ●●● (Avis d'experts)")


def test_layout_fragment_is_split_into_rows_without_headers():
    rows = normalize_layout_fragment(LAYOUT)
    assert len(rows) == 2
    assert rows[0].startswith("Prothèse de hanche ou de genou (dont reprise précoce non septique)")
    assert "Force de la" not in rows[0] and "Molécules" not in rows[0]
    assert datasets.COLUMN_SEP.strip() in rows[0]


def test_generic_rows_are_dropped():
    assert normalize_layout_fragment("Céfazoline     2g IVL    1g si durée > 4h    ◉◎◎ (Avis d’experts)") == []
    assert normalize_layout_fragment("CHIRURGIE HEPATO-BILIAIRE, SPLENIQUE ET PANCREATIQUE") == []


def test_column_match_credits_the_right_row_only():
    row = normalize_layout_fragment(LAYOUT)[0]
    assert passage_match(row, ROW_CARD)
    assert not passage_match(row, OTHER_ROW)
    # quotes without the column separator keep the historical behaviour
    assert passage_match("Prothèse de hanche ou de genou (dont reprise précoce non septique)", ROW_CARD)


def _chunk(text):
    return SimpleNamespace(chunk=SimpleNamespace(text=text))


def test_evidence_recall_and_sufficiency():
    row = normalize_layout_fragment(LAYOUT)[0]
    item = EvalItem(
        id="X", suite="t", question="q", question_type="open", provenance="team_written",
        evidence=[EvidencePassage(evidence_id="e1", doc_id="d", fragments=[row]),
                  EvidencePassage(evidence_id="e2", doc_id="d", fragments=["Allergie aux bêtalactamines : clindamycine 900 mg en première intention"])],
        evidence_sets=[EvidenceSet(set_id="S1", required_evidence_ids=["e1", "e2"])],
    )
    m = evidence_metrics(item, [_chunk(OTHER_ROW), _chunk(ROW_CARD)])
    assert m["evidence_hit"] == 1.0 and m["evidence_recall"] == 0.5 and m["sufficiency"] == 0.0
    assert m["evidence_ranks"] == {"e1": 2, "e2": None} and m["sufficiency_rank"] is None
    m = evidence_metrics(item, [_chunk(ROW_CARD), _chunk(OTHER_ROW),
                                _chunk("En cas d'allergie aux bêtalactamines : clindamycine 900 mg en première intention")])
    assert m["sufficiency"] == 1.0 and m["sufficiency_rank"] == 3
    # no evidence set -> no evidence metric (clarification cases, older suites)
    assert evidence_metrics(EvalItem(id="Y", suite="t", question="q", question_type="open", provenance="team_written"), []) == {}


def test_older_suites_are_rewritten_byte_identically(tmp_path):
    src = ROOT / "eval/splits/abp171/dev.jsonl"
    out = tmp_path / "dev.jsonl"
    datasets.write_jsonl(datasets.read_jsonl(src), out)
    assert out.read_bytes() == src.read_bytes()


def test_abpe171_split_reuses_abp171_ids():
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        for part in ("dev", "test"):
            a = [json.loads(l)["id"] for l in (ROOT / f"eval/splits/abp171/{part}.jsonl").read_text().splitlines() if l.strip()]
            p = ROOT / f"eval/splits/abpe171/{part}.jsonl"
            if not p.exists():
                return
            b = [json.loads(l)["id"] for l in p.read_text().splitlines() if l.strip()]
            assert sorted(a) == sorted(b)
    finally:
        os.chdir(cwd)


def test_judge_structured_fields_are_optional():
    old = parse_judgement('{"correctness": "correct", "abstained": false, "serious_error": "none", "faithful": null, "justification": "ok"}')
    assert "claims_satisfied" not in old and "behavior" not in old
    new = parse_judgement('{"correctness": "partial", "abstained": false, "serious_error": "none", "faithful": null, '
                          '"justification": "x", "claims_satisfied": ["Q1-C1"], "forbidden_violated": [], "behavior": "answer"}')
    assert new["claims_satisfied"] == ["Q1-C1"] and new["behavior"] == "answer"
    assert "Q1-C1" in format_expectations([{"claim_id": "Q1-C1", "text": "t"}], [], "answer")


def test_structured_row_metrics():
    item = EvalItem(id="Q1", suite="t", question="q", question_type="open", provenance="team_written",
                    mandatory_claims=[{"claim_id": "C1", "text": "a"}, {"claim_id": "C2", "text": "b"}],
                    forbidden_claims=[{"claim_id": "F1", "text": "c"}], expected_behavior="clarification")
    m = structured_row_metrics(item, {"claims_satisfied": ["C1"], "forbidden_violated": ["F1"], "behavior": "answer"})
    assert m == {"judge_claims_rate": 0.5, "judge_no_omission": 0.0, "judge_forbidden_violation": 1.0, "judge_behavior_ok": 0.0}
    # verdicts of older judge runs (no structured keys) add nothing
    assert structured_row_metrics(item, {"correctness": "correct"}) == {}
