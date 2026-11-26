import pytest

from rag_sfar.evaluation import cost_ledger as cl


def test_compute_cost_with_cache_and_batch():
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        "cache_creation_input_tokens": 200_000,
        "cache_read_input_tokens": 500_000,
    }
    # Opus 5.5: 4 + 2 + 0.2*5 + 0.5*0.2 = 4 + 2 + 1.0 + 0.1
    assert cl.compute_cost("claude-opus-5-5", usage) == pytest.approx(7.1)
    assert cl.compute_cost("claude-opus-5-5", usage, batch=True) == pytest.approx(3.55)


def test_unknown_model_raises():
    with pytest.raises(KeyError):
        cl.compute_cost("gpt-unknown", {"input_tokens": 1})


def test_record_usage_and_cumulative(tmp_path):
    path = tmp_path / "ledger.csv"
    cl.record_usage("exp1", "claude-haiku-5-5", {"input_tokens": 2_000_000, "output_tokens": 0}, path=path)
    cl.record_estimate("exp2", "claude-haiku-5-5", 9.0, path=path)
    cl.record_usage("exp2", "claude-haiku-5-5", {"input_tokens": 0, "output_tokens": 2_000_000}, path=path)
    assert cl.total_spent(path) == pytest.approx(0.2 + 1.0)
    assert cl.spent_by_experiment(path) == {"exp1": pytest.approx(0.2), "exp2": pytest.approx(1.0)}


def test_guard_experiment(tmp_path):
    path = tmp_path / "ledger.csv"
    with pytest.raises(cl.BudgetExceeded):
        cl.guard_experiment("big", "claude-opus-5-5", 20.0, path=path)
    cl.guard_experiment("big", "claude-opus-5-5", 20.0, approved_by_user=True, path=path)
    cl.guard_experiment("mid", "claude-opus-5-5", 6.0, path=path)
    rows = cl._read_rows(path)
    assert [r["experiment"] for r in rows] == ["big", "mid"]
    assert all(r["kind"] == "estimate" for r in rows)
