"""Demo chatbot (interfaces/demo_page.py + generator endpoints of interfaces/api.py).

A stand-in OpenAI-compatible server (fixed answer with citations, streaming, key check) replaces
the real generator. The key used here is an obvious dummy."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from rag_sfar.config import Settings
from rag_sfar.interfaces.api import create_app
from test_generation_b3 import _Recorder, _synthetic_retriever

DUMMY_KEY = "dummy-test-key-not-a-secret"
ANSWER = "Prophylaxie par Produit X 2 g [S1]. Le geste beta n'en nécessite pas [S2]."


class StandIn:
    """Minimal OpenAI-compatible server: /v1/models, /v1/chat/completions (stream or not)."""

    def __init__(self, models=("standin-model-a", "standin-model-b"), key: str | None = None):
        self.models, self.key, self.requests = list(models), key, []
        self.rewrite_reply = "NORMALISEE: Quelle prophylaxie pour le geste beta ?"
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence
                pass

            def _auth_ok(self):
                if outer.key is None:
                    return True
                if self.headers.get("Authorization") == f"Bearer {outer.key}":
                    return True
                self._json(401, {"error": {"message": f"Incorrect API key provided: {self.headers.get('Authorization')}"}})
                return False

            def _json(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if not self._auth_ok():
                    return
                if self.path.rstrip("/") == "/v1/models":
                    self._json(200, {"object": "list", "data": [{"id": m, "object": "model"} for m in outer.models]})
                else:
                    self._json(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if not self._auth_ok():
                    return
                outer.requests.append(body)
                system = body["messages"][0]["content"]
                if "normaliser" in system and not body.get("stream"):  # question-normalisation call
                    self._json(200, {"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                                     "choices": [{"index": 0, "message": {"role": "assistant", "content": outer.rewrite_reply},
                                                  "finish_reason": "stop"}]})
                    return
                if body.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for piece in (ANSWER[:20], ANSWER[20:]):
                        ch = {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": body["model"],
                              "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
                        self.wfile.write(f"data: {json.dumps(ch)}\n\n".encode())
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
                self._json(200, {"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                                 "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWER},
                                              "finish_reason": "stop"}],
                                 "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _free_port_url() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}/v1"


def _app(base_url: str | None = None, model: str = "standin-model-a", key: str = ""):
    settings = Settings(reranker_provider="none", llm_base_url=base_url or _free_port_url(),
                        llm_model=model, llm_api_key=key, llm_timeout_seconds=5)
    app = create_app(settings=settings, enable_llm=True, retriever=_synthetic_retriever())
    return app, TestClient(app)


def _events(client, query, retrieval_only=False):
    r = client.post("/api/query/stream", json={"query": query, "retrieval_only": retrieval_only})
    assert r.status_code == 200
    return [json.loads(b[5:]) for b in r.text.split("\n\n") if b.startswith("data:")]


Q = "Quelle prophylaxie pour le geste alpha ?"


@pytest.fixture(autouse=True)
def _unlocked(monkeypatch):
    monkeypatch.delenv("RAG_SFAR_DEMO_LOCK_SETTINGS", raising=False)
    monkeypatch.delenv("RAG_SFAR_DEMO_ROBUSTNESS", raising=False)
    monkeypatch.delenv("RAG_SFAR_QUERY_REWRITE", raising=False)


def test_page_served_offline_with_disclaimer():
    _, c = _app()
    html = c.get("/").text
    assert "Prototype de recherche" in html and "jugement clinique" in html
    assert "Passages seuls" in html and "/api/query/stream" in html
    assert "<script src" not in html and "<link" not in html and "@import" not in html


def test_passages_only_mode_without_any_generator():
    app = create_app(settings=Settings(reranker_provider="none"), enable_llm=False, retriever=_synthetic_retriever())
    c = TestClient(app)
    for retrieval_only in (True, False):
        ev = _events(c, Q, retrieval_only=retrieval_only)
        assert [e["type"] for e in ev] == ["retrieval", "variant", "token", "done"]
        assert ev[1]["used"] == "none" and ev[1]["rewrite"] is None
        assert ev[0]["model_used"] == "retrieval_only" and ev[0]["retrieved_chunks"]
    assert c.get("/api/generator").json()["available"] is False


def test_unreachable_generator_falls_back_to_passages():
    _, c = _app(key=DUMMY_KEY)
    ev = _events(c, Q)
    types = [e["type"] for e in ev]
    assert types[0] == "retrieval" and ev[0]["retrieved_chunks"]
    assert "generator_error" in types and types[-1] == "done" and ev[-1]["generator_failed"]
    assert DUMMY_KEY not in json.dumps(ev)
    g = c.get("/api/generator").json()
    assert g["last_status"]["state"] == "error" and DUMMY_KEY not in json.dumps(g)


def test_streamed_answer_citations_map_to_passages():
    srv = StandIn()
    try:
        _, c = _app(srv.url)
        ev = _events(c, Q)
        assert [e["type"] for e in ev][0] == "retrieval" and ev[-1]["type"] == "done"
        done, ret = ev[-1], ev[0]
        assert done["answer"] == ANSWER and done["model_used"] == "standin-model-a"
        assert "".join(e["text"] for e in ev if e["type"] == "token") == ANSWER
        # [Sn] in the answer = n-th passage of the retrieval event = n-th citation
        assert set(done["verification"]["citations_found"]) == {"S1", "S2"}
        n = len(ret["retrieved_chunks"])
        expected_invalid = {f"S{k}" for k in (1, 2) if k > n}
        assert set(done["verification"]["invalid_citations"]) == expected_invalid
        for i, cit in enumerate(ret["citations"]):
            assert cit["citation_id"] == f"S{i + 1}"
            assert cit["chunk_id"] == ret["retrieved_chunks"][i]["chunk"]["chunk_id"]
        assert c.get("/api/generator").json()["last_status"]["state"] == "ok"
    finally:
        srv.stop()


def test_settings_change_endpoint_and_model_not_prompt():
    a, b = StandIn(models=["model-a"]), StandIn(models=["model-b"])
    try:
        app, c = _app(a.url, model="model-a")
        _events(c, Q)
        r = c.post("/api/generator/settings", json={"base_url": b.url, "model": "model-b"})
        assert r.status_code == 200 and r.json()["model"] == "model-b" and r.json()["base_url"] == b.url
        _events(c, Q)
        assert len(a.requests) == 1 and len(b.requests) == 1
        ra, rb = a.requests[0], b.requests[0]
        assert (ra["model"], rb["model"]) == ("model-a", "model-b")
        assert ra["messages"] == rb["messages"]
        # same call options as evaluated: profile token cap, temperature 0, thinking off
        for req in (ra, rb):
            assert req["max_tokens"] == 1024 and req["temperature"] == 0.0
            assert req["chat_template_kwargs"] == {"enable_thinking": False}
        # and the prompt is the one the engine sends to any LLM (the evaluated prompt, cf.
        # test_api_prompt_identical_to_replay_prompt)
        rec = _Recorder()
        app.state.engine.llm = rec
        assert c.post("/api/query", json={"query": Q}).status_code == 200
        sys_p, user_p = rec.calls[0][:2]
        assert ra["messages"] == [{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}]
    finally:
        a.stop()
        b.stop()


def test_overrides_and_thinking_flag_are_transport_only():
    srv = StandIn()
    try:
        _, c = _app(srv.url)
        _events(c, Q)
        r = c.post("/api/generator/settings", json={"base_url": srv.url, "model": "standin-model-b",
                                                     "max_tokens_override": 2048, "temperature_override": 0.3,
                                                     "send_thinking_flag": False})
        assert r.status_code == 200
        _events(c, Q)
        first, second = srv.requests
        assert second["max_tokens"] == 2048 and second["temperature"] == 0.3
        assert "chat_template_kwargs" not in second and second["model"] == "standin-model-b"
        assert first["messages"] == second["messages"]
    finally:
        srv.stop()


def test_connection_test_wrong_url_wrong_key_and_key_never_echoed():
    srv = StandIn(key=DUMMY_KEY)
    try:
        _, c = _app(_free_port_url())
        ok = c.post("/api/generator/test", json={"base_url": srv.url, "api_key": DUMMY_KEY}).json()
        assert ok == {"ok": True, "models": ["standin-model-a", "standin-model-b"]}
        bad_key = c.post("/api/generator/test", json={"base_url": srv.url, "api_key": "wrong-dummy"}).json()
        assert bad_key["ok"] is False and "401" in bad_key["error"] and "wrong-dummy" not in json.dumps(bad_key)
        bad_url = c.post("/api/generator/test", json={"base_url": _free_port_url()}).json()
        assert bad_url["ok"] is False and bad_url["error"]
        # apply with the key, then the key is kept in memory but never returned
        r = c.post("/api/generator/settings", json={"base_url": srv.url, "model": "standin-model-a", "api_key": DUMMY_KEY})
        assert DUMMY_KEY not in r.text and r.json()["settings"]["api_key_set"] is True
        assert DUMMY_KEY not in c.get("/api/generator").text and DUMMY_KEY not in c.get("/api/health").text
        assert c.post("/api/generator/test", json={"base_url": srv.url}).json()["ok"] is True  # key kept
        ev = _events(c, Q)
        assert ev[-1]["answer"] == ANSWER
        # wrong key at query time -> passages-only fallback, key not leaked
        c.post("/api/generator/settings", json={"base_url": srv.url, "model": "standin-model-a", "api_key": "wrong-dummy"})
        ev = _events(c, Q)
        assert any(e["type"] == "generator_error" for e in ev) and "wrong-dummy" not in json.dumps(ev)
    finally:
        srv.stop()


def test_endpoint_going_down_mid_session_falls_back():
    srv = StandIn()
    _, c = _app(srv.url)
    assert _events(c, Q)[-1]["answer"] == ANSWER
    srv.stop()
    ev = _events(c, Q)
    assert ev[0]["type"] == "retrieval" and ev[0]["retrieved_chunks"]
    assert any(e["type"] == "generator_error" for e in ev) and ev[-1]["generator_failed"]


def test_locked_settings(monkeypatch):
    monkeypatch.setenv("RAG_SFAR_DEMO_LOCK_SETTINGS", "1")
    srv = StandIn()
    try:
        _, c = _app(srv.url)
        assert c.get("/api/generator").json()["locked"] is True
        r = c.post("/api/generator/settings", json={"base_url": _free_port_url(), "model": "x"})
        assert r.status_code == 403
        # the connection test ignores a typed URL and checks the configured endpoint only
        t = c.post("/api/generator/test", json={"base_url": _free_port_url()}).json()
        assert t["ok"] is True
        assert c.get("/api/generator").json()["base_url"] == srv.url
    finally:
        srv.stop()


# ------------------------------------------------------------------ robustness selector


def _chunk_ids(ev):
    return [r["chunk"]["chunk_id"] for r in ev[0]["retrieved_chunks"]]


def test_robustness_none_is_the_frozen_profile():
    from rag_sfar.generation.profile import PRODUCTION, build_engine

    app, c = _app()
    retriever = app.state.engine.retriever
    ev = _events_rob(c, Q, "none", retrieval_only=True)
    ref = next(build_engine(retriever, None, PRODUCTION).stream_answer(
        Q, mode=PRODUCTION.open_mode, config=PRODUCTION.retrieval_config(), retrieval_only=True))
    assert _chunk_ids(ev) == [r["chunk"]["chunk_id"] for r in ref["retrieved_chunks"]]
    var = ev[1]
    assert var["used"] == "none" and var["retrieval_config"] == "C10_context_notes" and var["rewrite"] is None
    # default (no field) = none unless RAG_SFAR_DEMO_ROBUSTNESS says otherwise
    assert _events(c, Q, retrieval_only=True)[1]["used"] == "none"


def _events_rob(client, query, robustness, retrieval_only=False):
    r = client.post("/api/query/stream", json={"query": query, "retrieval_only": retrieval_only,
                                               "robustness": robustness})
    assert r.status_code == 200
    return [json.loads(b[5:]) for b in r.text.split("\n\n") if b.startswith("data:")]


def test_robustness_lexical_subword_and_plain_acronyms_only(monkeypatch):
    app, c = _app()
    retriever = app.state.engine.retriever
    seen = []
    orig = retriever.retrieve
    monkeypatch.setattr(retriever, "retrieve", lambda query, config=None, **kw: (seen.append((query, config)), orig(query, config=config, **kw))[1])
    q = "Quelle ABP pour le geste alpha chez un patient sous AOD ?"
    ev = _events_rob(c, q, "lexical", retrieval_only=True)
    base = app.state.profile.retrieval_config()
    query, cfg = seen[-1]
    assert cfg.use_subword and not cfg.use_medical_lexicon and cfg.name == "C10_context_notes+subword+plain_acronyms"
    import dataclasses
    diff = {f.name for f in dataclasses.fields(base) if getattr(base, f.name) != getattr(cfg, f.name)}
    assert diff <= {"use_subword", "name"} and not base.use_medical_lexicon
    # plain acronym expanded to its long form; molecule-adding entry (AOD) not expanded at all
    assert ev[1]["used"] == "lexical" and ev[1]["rewrite"] is None
    assert ev[1]["expansions"] == {"ABP": "antibioprophylaxie"}
    assert query == q + " (antibioprophylaxie)"
    assert "apixaban" not in query and "rivaroxaban" not in query


def test_plain_acronym_table_excludes_entries_adding_terms():
    from rag_sfar.interfaces import robustness as rob
    from rag_sfar.retrieval.medical_lexicon import MEDICAL_ACRONYMS

    entries = {e["abbr"]: e["long_form"] for e in rob.plain_entries()}
    for abbr in ("C1G", "C2G", "C3G", "AOD", "AVK", "AAP", "HBPM"):
        assert abbr in MEDICAL_ACRONYMS and abbr not in entries
    exp = rob.RobustnessVariants(None, None).expander()
    for abbr in ("C1G", "C3G", "AVK", "HBPM"):
        assert exp.expand(f"Quelle dose de {abbr} ?")[1] == {}
    assert len(entries) == len(MEDICAL_ACRONYMS) - 13


def test_robustness_none_never_expands():
    _, c = _app()
    ev = _events_rob(c, "Quelle ABP pour le geste alpha ?", "none", retrieval_only=True)
    assert ev[1]["expansions"] is None


def test_robustness_normalize_goes_through_the_add_wrapper_and_is_shown():
    srv = StandIn()
    try:
        _, c = _app(srv.url)
        ev = _events_rob(c, Q, "normalize")
        var = ev[1]
        assert var["used"] == "normalize" and var["rewrite"]["used"] is True
        assert var["rewrite"]["normalized_question"] == "Quelle prophylaxie pour le geste beta ?"
        rw_req = srv.requests[0]
        assert "normaliser" in rw_req["messages"][0]["content"] and rw_req["max_tokens"] == 200
        assert rw_req["chat_template_kwargs"] == {"enable_thinking": False}
        assert ev[-1]["answer"] == ANSWER
        # unchanged question -> reported as unchanged, frozen retrieval
        srv.rewrite_reply = "INCHANGEE"
        ev = _events_rob(c, Q, "both", retrieval_only=True)
        assert ev[1]["used"] == "both" and ev[1]["rewrite"]["used"] is False and ev[1]["rewrite"]["unchanged"]
        assert ev[1]["retrieval_config"].endswith("+subword+plain_acronyms")
    finally:
        srv.stop()


def test_robustness_normalize_unavailable_without_generator():
    app = create_app(settings=Settings(reranker_provider="none"), enable_llm=False, retriever=_synthetic_retriever())
    c = TestClient(app)
    var = _events_rob(c, Q, "normalize", retrieval_only=True)[1]
    assert var["used"] == "none" and var["unavailable"]
    var = _events_rob(c, Q, "both", retrieval_only=True)[1]
    assert var["used"] == "lexical" and var["unavailable"]
    # unreachable generator: the wrapper falls back to the original question and says so
    _, c2 = _app()
    var = _events_rob(c2, Q, "normalize", retrieval_only=True)[1]
    assert var["rewrite"]["used"] is False and var["rewrite"]["error"]
    assert c.post("/api/query/stream", json={"query": Q, "robustness": "hyde"}).status_code == 422
