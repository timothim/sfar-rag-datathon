"""Rubric v4 and the blind, replicated judging pipeline (synthetic cases only: no benchmark text)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rag_sfar.evaluation import judge_io
from rag_sfar.evaluation.datasets import EvalItem
from rag_sfar.evaluation.harness import aggregate_binary, clopper_pearson
from rag_sfar.evaluation.judge import JUDGE_RUBRIC, RUBRIC_VERSION, normalize_verdict, parse_judgement
from rag_sfar.evaluation.judge_io import (acceptable_behaviors, agreement, apply_v4_consistency, bound_sources,
                                          cited_labels, combine_passes, parse_prompt_sources, row_metrics)

ROOT = Path(__file__).resolve().parents[1]


def _item(**kw) -> EvalItem:
    base = dict(id="T1", suite="synthetic", question="Question synthétique ?", question_type="open",
                provenance="team_written", reference_answer="Conduite X.")
    base.update(kw)
    return EvalItem(**base)


def _v(correctness="correct", serious="none", **kw) -> dict:
    return {"correctness": correctness, "abstained": False, "serious_error": serious, "faithful": None,
            "justification": "j", **kw}


# ---------------------------------------------------------------- statistics


def test_clopper_pearson_known_values():
    lo, hi = clopper_pearson(0, 69)
    assert lo == 0.0 and abs(hi - 0.0521) < 1e-3          # rule of three is ~0.043; exact is 0.052
    lo, hi = clopper_pearson(3, 30)
    assert abs(lo - 0.0211) < 1e-3 and abs(hi - 0.2653) < 1e-3
    lo, hi = clopper_pearson(30, 30)
    assert hi == 1.0 and abs(lo - 0.8843) < 1e-3
    assert clopper_pearson(0, 0) != clopper_pearson(0, 0)  # nan
    with pytest.raises(ValueError):
        clopper_pearson(5, 3)


def test_aggregate_binary_zero_events_not_degenerate():
    a = aggregate_binary([0.0] * 57)
    assert a["mean"] == 0.0 and a["ci_high"] > 0.06 and a["ci_method"] == "clopper_pearson" and a["k"] == 0


# ---------------------------------------------------------------- rubric


def test_rubric_text_matches_instructions_file():
    md = (ROOT / "eval_internal/judge/JUDGE_INSTRUCTIONS.md").read_text(encoding="utf-8")
    body = md[md.index("Tu es un évaluateur"): md.index("## Format d'entrée")].rstrip()
    assert body == JUDGE_RUBRIC
    assert RUBRIC_VERSION == "v4"
    # the v3 contradiction ("ces clés n'influencent pas correctness") is gone
    assert "n'influencent pas" not in md


def test_other_and_unjustified_assumption_are_serious():
    assert "other" in judge_io.SERIOUS and "unjustified_assumption" in judge_io.SERIOUS
    assert row_metrics(None, _v(serious="other"))["judge_serious_error"] == 1.0
    assert row_metrics(None, _v(serious="none"))["judge_serious_error"] == 0.0


def test_unparseable_output_is_technical_failure_not_other():
    v = parse_judgement("not json")
    assert v["technical_failure"] and v["serious_error"] is None and v["correctness"] is None
    v = normalize_verdict({"correctness": "great", "abstained": False, "serious_error": "none"})
    assert v["technical_failure"]
    m = row_metrics(_item(), v)
    assert m["judge_correct"] == 0.0 and m["judge_technical_failure"] == 1.0 and "judge_serious_error" not in m


def test_behavior_strict_lenient_case_by_case():
    ans = _item(expected_behavior="answer")
    clar = _item(expected_behavior="clarification", required_missing_information=["âge", "terrain"])
    assert acceptable_behaviors(ans) == ["answer"]
    assert acceptable_behaviors(ans, lenient=True) == ["answer", "conditional"]
    assert acceptable_behaviors(clar) == ["clarification", "conditional"]
    m = row_metrics(ans, _v(behavior="conditional"))
    assert m["judge_behavior_ok"] == 0.0 and m["judge_behavior_ok_lenient"] == 1.0 and m["judge_behavior_ok_case_by_case"] == 0.0
    m = row_metrics(ans, _v(behavior="conditional", alternative_justified=True))
    assert m["judge_behavior_ok"] == 0.0 and m["judge_behavior_ok_case_by_case"] == 1.0
    explicit = _item(expected_behavior="answer", meta={"acceptable_behaviors": ["answer_with_evidence", "conditional_answer"]})
    assert acceptable_behaviors(explicit) == ["answer", "conditional"]


def test_clarification_must_ask_required_information():
    clar = _item(expected_behavior="clarification", required_missing_information=["âge", "terrain"])
    v = apply_v4_consistency(clar, _v(behavior="clarification", missing_info_requested=["M1"]))
    assert v["correctness"] == "partial" and v["v4_overrides"]
    v = apply_v4_consistency(clar, _v(behavior="clarification", missing_info_requested=[]))
    assert v["correctness"] == "incorrect"
    v = apply_v4_consistency(clar, _v(behavior="clarification", missing_info_requested=["M1", "M2"]))
    assert v["correctness"] == "correct" and "v4_overrides" not in v
    assert row_metrics(clar, v)["judge_missing_info_complete"] == 1.0
    v = apply_v4_consistency(clar, _v(behavior="answer"))
    assert v["correctness"] == "partial"


def test_correct_requires_all_mandatory_claims_and_abstention_is_incorrect():
    it = _item(expected_behavior="answer", mandatory_claims=[{"claim_id": "C1", "text": "a"}, {"claim_id": "C2", "text": "b"}])
    assert apply_v4_consistency(it, _v(claims_satisfied=["C1"], behavior="answer"))["correctness"] == "partial"
    assert apply_v4_consistency(it, _v(claims_satisfied=["C1", "C2"], behavior="answer"))["correctness"] == "correct"
    v = apply_v4_consistency(_item(), _v(abstained=True))
    assert v["correctness"] == "incorrect"
    assert row_metrics(_item(), v)["judge_false_abstention"] == 1.0
    # consistency rules never raise a verdict
    assert apply_v4_consistency(it, _v("incorrect", claims_satisfied=["C1", "C2"]))["correctness"] == "incorrect"


def test_abstention_metrics():
    off = _item(should_abstain=True, reference_answer="")
    assert row_metrics(off, _v(abstained=True))["judge_missing_abstention"] == 0.0
    assert row_metrics(off, _v())["judge_missing_abstention"] == 1.0
    assert "judge_false_abstention" not in row_metrics(off, _v())


# ---------------------------------------------------------------- combination and agreement


def test_combination_is_conservative_and_reports_spread():
    a = {"judge_correct": 1.0, "judge_serious_error": 0.0, "judge_behavior_ok": 1.0, "judge_claims_rate": 1.0}
    b = {"judge_correct": 0.0, "judge_serious_error": 1.0, "judge_behavior_ok": 1.0, "judge_claims_rate": 0.5}
    c = combine_passes([a, b])
    assert c["judge_correct"] == 0.0 and c["judge_correct_any"] == 1.0
    assert c["judge_serious_error"] == 1.0 and c["judge_serious_error_all"] == 0.0
    assert c["judge_behavior_ok"] == 1.0 and c["judge_claims_rate"] == 0.5 and c["judge_claims_rate_max"] == 1.0
    # a pass with an undetermined safety status does not hide the other's serious error
    f = row_metrics(None, {"technical_failure": True})
    assert combine_passes([f, b])["judge_serious_error"] == 1.0


def test_agreement_kappa():
    va = {"x1": _v("correct"), "x2": _v("partial"), "x3": _v("incorrect", "wrong_drug"), "x4": _v("correct")}
    vb = {"x1": _v("correct"), "x2": _v("incorrect"), "x3": _v("incorrect", "wrong_drug"), "x4": _v("correct"),
          "x5": _v("correct")}
    r = agreement(va, vb)
    assert r["n"] == 4 and r["correctness"]["raw"] == 0.75 and r["correctness"]["disagreements"] == ["x2"]
    assert r["serious_error"]["raw"] == 1.0 and r["serious_error"]["kappa"] == 1.0


# ---------------------------------------------------------------- cited sources


PROMPT = ("EXTRAITS :\n\n[S1] Titre A\nTexte un.\n\n[S2] Titre B\n" + "long " * 2000 + "\n\n[S3] Titre C\nTexte trois.\n"
          "\n---\nQUESTION CLINIQUE :\nQuestion synthétique ?")


def test_cited_sources_parsing_and_bounds():
    blocks = parse_prompt_sources(PROMPT)
    assert sorted(blocks) == [1, 2, 3] and blocks[1].startswith("[S1] Titre A") and "QUESTION" not in blocks[3]
    assert cited_labels("A [S1]. B [S3, 2016]. C [S1, S2]. D [12].") == [1, 2, 3]
    out = bound_sources(blocks, [1, 2, 3], max_each=500, max_total=900)
    assert [s["label"] for s in out] == ["S1", "S2", "S3"]
    assert out[1]["lines"][-1].endswith("[tronqué]") and sum(len(x) for s in out for x in s["lines"]) <= 900 + 50
    assert all(len(x) <= judge_io.LINE_CHARS for s in bound_sources(blocks, [2]) for x in s["lines"])


# ---------------------------------------------------------------- blind export and merge (end to end)


@pytest.fixture()
def blind_env(tmp_path, monkeypatch):
    items = {"dev": [_item(id="A1", expected_behavior="answer", mandatory_claims=[{"claim_id": "A1-C1", "text": "a"}]),
                     _item(id="A2", expected_behavior="clarification", required_missing_information=["âge"],
                           meta={"narrative": "Corrigé détaillé synthétique."}),
                     _item(id="A3", should_abstain=True, reference_answer="")]}
    monkeypatch.setattr(judge_io, "load_suite", lambda suite, split: items[split])
    reports = []
    for name, cfg in (("r1", "cfgA|modelA"), ("r2", "cfgB|modelB")):
        rep = {"suite": "synthetic", "split": "dev", "replay": {}, "timestamp": "t", "n_items": 3, "k": 0, "comparisons": [],
               "runs": [{"config": cfg, "summary": {}, "rows": [
                   {"id": i.id, "suite": "synthetic", "answer": f"Réponse {k} [S1]", "judge": {"old": 1}, "judge_correct": 1.0}
                   for k, i in enumerate(items["dev"])]}]}
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(rep), encoding="utf-8")
        reports.append(p)
    dirs = dict(runs_dir=tmp_path / "runs", keys_dir=tmp_path / "keys")
    return reports, dirs, tmp_path


def _judge_all(run_dir: Path, pass_id: str, verdict_for):
    for f in sorted(run_dir.glob("judge_input_*.json")):
        cases = json.loads(f.read_text(encoding="utf-8"))
        out = run_dir / f"pass_{pass_id}" / f.name.replace("input", "out")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([{"case_id": c["case_id"], **verdict_for(c)} for c in cases]), encoding="utf-8")


def test_blind_export_hides_system_and_merge_is_strict(blind_env):
    reports, dirs, tmp = blind_env
    man = judge_io.export_blind(reports, "blind_t", batch_size=4, frontier_root=tmp / "none", check_ignored=False, **dirs)
    run_dir = dirs["runs_dir"] / "blind_t"
    batches = sorted(run_dir.glob("judge_input_*.json"))
    assert len(batches) == 2 and man["n_cases"] == 6
    text = "".join(f.read_text(encoding="utf-8") for f in batches)
    for leak in ("cfgA", "modelB", "synthetic", "dev", "r1"):
        assert leak not in text
    cases = [c for f in batches for c in json.loads(f.read_text(encoding="utf-8"))]
    assert all(re.fullmatch(r"x[0-9a-f]{10}", c["case_id"]) for c in cases)
    assert not list(run_dir.glob("mapping*")) and (dirs["keys_dir"] / "blind_t" / "mapping.json").exists()
    assert all("cited_sources" not in c for c in cases)  # no prompt folder: no excerpts
    assert {c["required_missing_information"][0]["id"] for c in cases if "required_missing_information" in c} == {"M1"}

    def good(c):
        v = _v(claims_satisfied=["A1-C1"], behavior="answer") if "mandatory_claims" in c else _v()
        if "required_missing_information" in c:
            v = _v(behavior="clarification", missing_info_requested=["M1"])
        if "s'abstenir" in c["reference"]:
            v = _v(abstained=True)
        return v

    _judge_all(run_dir, "a", good)
    # pass b: one serious error on one case, and one verdict missing
    first = cases[0]["case_id"]
    _judge_all(run_dir, "b", lambda c: _v("incorrect", "wrong_dose") if c["case_id"] == first else good(c))
    bout = run_dir / "pass_b" / "judge_out_1.json"
    data = json.loads(bout.read_text(encoding="utf-8"))
    bout.write_text(json.dumps(data[:-1]), encoding="utf-8")
    missing_id = data[-1]["case_id"]

    with pytest.raises(SystemExit):
        judge_io.merge_blind("blind_t", ["a", "b"], out_root=tmp / "out", **dirs)
    res = judge_io.merge_blind("blind_t", ["a", "b"], allow_missing=True, out_root=tmp / "out", **dirs)
    assert res["missing_or_invalid"] == 1 and res["problems"][0]["case_id"] == missing_id
    merged = [json.loads((tmp / "out" / "blind_t" / p.name).read_text(encoding="utf-8")) for p in reports]
    rows = [r for m in merged for r in m["runs"][0]["rows"]]
    assert all(r["judge_v4"]["rubric"] == "v4" and "judge_previous" in r for r in rows)
    bad = [r for r in rows if r["judge_v4"]["opaque_id"] in (first, missing_id)]
    assert all(r["judge_correct"] == 0.0 and r["judge_correct_any"] == 1.0 for r in bad)
    assert sum(r.get("judge_serious_error", 0) for r in rows) == 1
    assert sum(r["judge_correct"] for r in rows) == 4
    s = merged[0]["runs"][0]["summary"]
    assert s["judge_serious_error"]["ci_method"] == "clopper_pearson"
    assert "a-b" in s["judge_agreement"] and merged[0]["judge"]["rubric"] == "v4"
    # original reports untouched
    assert json.loads(reports[0].read_text(encoding="utf-8"))["runs"][0]["rows"][0]["judge"] == {"old": 1}


def test_export_refuses_existing_run(blind_env):
    reports, dirs, tmp = blind_env
    judge_io.export_blind(reports, "blind_t", frontier_root=tmp / "none", check_ignored=False, **dirs)
    with pytest.raises(SystemExit):
        judge_io.export_blind(reports, "blind_t", frontier_root=tmp / "none", check_ignored=False, **dirs)


def test_cited_sources_recovered_from_prompt_folder(blind_env):
    reports, dirs, tmp = blind_env
    meta = {"cache": "synthetic_cache", "suites": ["synthetic"]}
    folder = tmp / "frontier" / "f1"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (folder / "gen_input_0.json").write_text(json.dumps(
        [{"case_id": i, "suite": "synthetic", "system": "s", "user": PROMPT} for i in ("A1", "A2", "A3")]), encoding="utf-8")
    rep = json.loads(reports[0].read_text(encoding="utf-8"))
    rep["replay"] = meta
    reports[0].write_text(json.dumps(rep), encoding="utf-8")
    man = judge_io.export_blind(reports[:1], "blind_s", frontier_root=tmp / "frontier", check_ignored=False, **dirs)
    assert man["sources_status"] == {"ok": 3}
    cases = [c for f in (dirs["runs_dir"] / "blind_s").glob("judge_input_*.json") for c in json.loads(f.read_text(encoding="utf-8"))]
    assert all(c["cited_sources"][0]["label"] == "S1" and "Texte un." in c["cited_sources"][0]["lines"] for c in cases)
    shown = judge_io.show("blind_s", 0, runs_dir=dirs["runs_dir"])
    assert "Texte un." in shown and "case_id x" in shown


def test_cited_sources_from_blind_generation_keys(blind_env):
    reports, dirs, tmp = blind_env
    meta = {"cache": "c", "suites": ["synthetic"], "split": "dev"}
    keys = tmp / "frontier_keys"
    keys.mkdir()
    (keys / "exp.json").write_text(json.dumps({"meta": meta, "cases": [
        {"id": i, "suite": "synthetic", "user": PROMPT, "case_id": f"c{n}"} for n, i in enumerate(("A1", "A2", "A3"))]}), encoding="utf-8")
    rep = json.loads(reports[1].read_text(encoding="utf-8"))
    rep["replay"] = meta
    reports[1].write_text(json.dumps(rep), encoding="utf-8")
    man = judge_io.export_blind(reports[1:], "blind_k", frontier_root=tmp / "frontier_none", check_ignored=False, **dirs)
    assert man["sources_status"] == {"ok": 3}  # keys root defaults to <frontier_root>/../frontier_keys
    idx = judge_io.PromptIndex(tmp / "frontier_none", keys_root=keys)
    assert idx.prompts(meta)[("synthetic", "A2")] == PROMPT
