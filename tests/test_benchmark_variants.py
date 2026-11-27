"""Retrieval variants with a live model (normalisation, decomposition) in the replay tool and in
the HTTP API (interfaces/robustness.py::compose). Defaults must stay the frozen profile."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from rag_sfar.config import Settings
from rag_sfar.evaluation.datasets import EvalItem
from rag_sfar.interfaces import robustness as rob
from rag_sfar.interfaces.api import create_app
from test_generation_b3 import _gen_replay, _synthetic_retriever

Q = "Quelle prophylaxie pour le geste alpha ?"
ANSWER = "Prophylaxie par Produit X 2 g [S1]."


class FakeLLM:
    """Answers the three kinds of prompt in their strict formats and records the calls."""

    model = "fake"

    def __init__(self, normalize="NORMALISEE: Quelle prophylaxie pour le geste beta ?",
                 decompose="MULTIPLE\n1. Quelle prophylaxie pour le geste beta ?\n2. Quel délai pour le geste alpha ?"):
        self.normalize, self.decompose, self.calls = normalize, decompose, []

    def complete(self, system_prompt, user_prompt, temperature=None, max_tokens=None, **opts):
        if "normaliser l'écriture" in system_prompt:
            kind, text = "normalize", self.normalize
        elif "SIMPLE" in system_prompt and "MULTIPLE" in system_prompt:
            kind, text = "decompose", self.decompose
        else:
            kind, text = "generate", ANSWER
        self.calls.append((kind, system_prompt, user_prompt))
        return text, {}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("RAG_SFAR_DEMO_ROBUSTNESS", "RAG_SFAR_DECOMPOSE", "RAG_SFAR_QUERY_REWRITE", "RAG_SFAR_MULTI_QUERY",
              "RAG_SFAR_DEMO_LOCK_SETTINGS"):
        monkeypatch.delenv(k, raising=False)


def _client(llm=None):
    app = create_app(settings=Settings(reranker_provider="none"), enable_llm=False, retriever=_synthetic_retriever())
    app.state.engine.llm = llm
    return app, TestClient(app)


def test_compose_defaults_are_the_frozen_objects():
    from rag_sfar.generation.profile import PRODUCTION

    base, cfg = _synthetic_retriever(), PRODUCTION.retrieval_config()
    v = rob.RobustnessVariants(base, cfg)
    comp = rob.compose(v, "none", False, FakeLLM())
    assert comp.frozen and comp.retriever is base and comp.config is cfg
    assert comp.metadata()["normalization"] is None and comp.metadata()["decomposition"] is None
    with pytest.raises(ValueError):
        rob.compose(v, "hyde", False, None)
    # steps that need a model fall back without one, and say so
    comp = rob.compose(v, "both", True, None)
    assert comp.used == "lexical" and not comp.decompose_used and comp.unavailable


def test_decompose_default_env(monkeypatch):
    assert rob.decompose_default() is False
    monkeypatch.setenv("RAG_SFAR_DECOMPOSE", "1")
    assert rob.decompose_default() is True
    monkeypatch.setenv("RAG_SFAR_DECOMPOSE", "maybe")
    with pytest.raises(ValueError):
        rob.decompose_default()


def test_api_query_and_openai_endpoint_honour_the_choice():
    llm = FakeLLM()
    _, c = _client(llm)
    # default: frozen, no model call before generation
    r = c.post("/api/query", json={"query": Q}).json()
    assert r["extra"]["variant"]["used"] == "none" and r["extra"]["variant"]["decompose"] is False
    assert [k for k, *_ in llm.calls] == ["generate"]
    llm.calls.clear()
    r = c.post("/api/query", json={"query": Q, "robustness": "normalize", "decompose": True}).json()
    var = r["extra"]["variant"]
    assert var["used"] == "normalize" and var["normalization"]["used"] is True
    assert var["decompose"] is True and var["decomposition"]["fired"] is True
    assert len(var["decomposition"]["sub_questions"]) == 2
    kinds = [k for k, *_ in llm.calls]
    assert kinds[0] == "decompose" and kinds[-1] == "generate" and kinds.count("normalize") == 3
    # the generator sees the user's question, not the rewrite
    assert Q in llm.calls[-1][2]
    llm.calls.clear()
    r = c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": Q}], "robustness": "lexical"}).json()
    assert r["sfar_variant"]["used"] == "lexical" and r["sfar_variant"]["retrieval_config"].endswith("+subword+plain_acronyms")
    assert r["choices"][0]["message"]["content"] == ANSWER
    r = c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": Q}]}).json()
    assert r["sfar_variant"]["used"] == "none"
    assert c.post("/api/query", json={"query": Q, "robustness": "hyde"}).status_code == 422
    assert c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": Q}], "robustness": "x"}).status_code == 422


def test_server_defaults_from_environment(monkeypatch):
    monkeypatch.setenv("RAG_SFAR_DEMO_ROBUSTNESS", "normalize")
    monkeypatch.setenv("RAG_SFAR_DECOMPOSE", "1")
    llm = FakeLLM(decompose="SIMPLE")
    app, c = _client(llm)
    assert c.get("/api/generator").json()["decompose"]["default"] is True
    r = c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": Q}]}).json()
    v = r["sfar_variant"]
    assert v["used"] == "normalize" and v["decompose"] is True and v["decomposition"]["fired"] is False
    # an explicit request value overrides the server default
    r = c.post("/api/query", json={"query": Q, "robustness": "none", "decompose": False}).json()
    assert r["extra"]["variant"]["used"] == "none" and r["extra"]["variant"]["decompose"] is False


def _patch_capture(gr, monkeypatch, tmp_path):
    retriever = _synthetic_retriever()
    monkeypatch.setattr(gr, "REPLAY", tmp_path)
    monkeypatch.setattr(gr.harness, "load_retrievers", lambda *a, **k: {"table_aware_sota": retriever})
    items = [EvalItem(id=f"q{i}", suite="toy", question=q, question_type="open", provenance="team_written")
             for i, q in enumerate([Q, "Quelle prophylaxie pour le geste beta ?"])]
    monkeypatch.setattr(gr, "_items", lambda suite, ids, split="dev": items)
    return retriever, items


def test_replay_capture_default_unchanged_and_variant_recorded(tmp_path, monkeypatch):
    from rag_sfar.generation.profile import PRODUCTION

    gr = _gen_replay()
    retriever, items = _patch_capture(gr, monkeypatch, tmp_path)
    imap = PRODUCTION.replay_index_map()
    gr.capture("toy", "C10_context_notes", "", imap, None, "base", "cpu")
    rows = [json.loads(x) for x in (tmp_path / "base" / "toy.jsonl").read_text().splitlines()]
    cfg = PRODUCTION.retrieval_config()
    for it, row in zip(items, rows):
        ref = gr.cache_row(it.formatted_query(), *retriever.retrieve(it.formatted_query(), config=cfg))
        assert set(row) == {"id", "query", "retrieved", "analysis", "timings"}
        assert [x["chunk"]["chunk_id"] for x in row["retrieved"]] == [x["chunk"]["chunk_id"] for x in ref["retrieved"]]
    meta = json.loads((tmp_path / "base" / "meta.json").read_text())
    assert meta["robustness"] == "none" and meta["decompose"] is False and meta["base_config"] == "C10_context_notes"

    with pytest.raises(SystemExit):  # model steps need a backend
        gr.capture("toy", "C10_context_notes", "", imap, None, "v", "cpu", robustness="normalize")
    llm = FakeLLM()
    gr.capture("toy", "C10_context_notes", "", imap, None, "v", "cpu", robustness="both", decompose=True,
               llm=llm, llm_label="openai:fake")
    rows = [json.loads(x) for x in (tmp_path / "v" / "toy.jsonl").read_text().splitlines()]
    assert all(r["pre_retrieval"]["used"] == "both" and r["pre_retrieval"]["decompose"] for r in rows)
    assert rows[0]["pre_retrieval"]["normalization"]["used"] is True
    meta = json.loads((tmp_path / "v" / "meta.json").read_text())
    assert meta["pre_retrieval_llm"] == "openai:fake" and meta["config"].endswith("+subword+plain_acronyms")
    assert meta["suites"]["toy"]["pre_retrieval_counts"]["decompose_fired"] == 2
