"""FastAPI Clinical Demonstrator UI + OpenAI-compatible `/v1/chat/completions` API.

Allows:
1. Physicians & jury to interactively query SFAR guidelines with full citation & score transparency.
2. Sibling datathon teams (`plateforme-evaluation`, `evaluation-cas-cliniques`) to benchmark
   our RAG seamlessly via standard OpenAI SDK (`base_url="http://localhost:8000/v1"`).
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from rag_sfar.config import Settings
from rag_sfar.interfaces import robustness as rob
from rag_sfar.interfaces.demo_page import DEMO_HTML
from rag_sfar.interfaces.generator_runtime import (
    GeneratorSettings,
    GeneratorState,
    list_models,
    safe_error,
    settings_locked,
)
from rag_sfar.generation.profile import PRODUCTION, ServingProfile, build_engine
from rag_sfar.retrieval.embedder import build_embedder
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.reranker import build_reranker
from rag_sfar.retrieval.vector_store import LocalVectorStore


class SearchRequest(BaseModel):
    query: str
    top_k: int = 8
    latest_only: bool | None = None
    use_reranker: bool = True
    use_hybrid: bool = True
    use_lexicon: bool = True
    expand_callouts: bool = True
    domains: list[str] | None = None


class QueryRequest(SearchRequest):
    # Production open-question mode (generation/profile.py); MCQs are routed by the engine.
    mode: str = "clinical_concise"
    retrieval_only: bool = False
    # Demo robustness variant (interfaces/robustness.py); None = server default ("none" = frozen).
    robustness: str | None = None


class GeneratorTestRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None


class GeneratorSettingsRequest(BaseModel):
    base_url: str
    model: str
    # None = keep the key currently in memory for this base URL; "" = no key.
    api_key: str | None = None
    max_tokens_override: int | None = Field(default=None, ge=16, le=32768)
    temperature_override: float | None = Field(default=None, ge=0.0, le=2.0)
    send_thinking_flag: bool = True


class ChatMessage(BaseModel):
    role: str
    content: str


class OpenAIChatRequest(BaseModel):
    model: str = "rag-sfar-sota"
    messages: list[ChatMessage]
    temperature: float | None = 0.0
    max_tokens: int | None = None




def create_app(
    index_dir: Path | None = None,
    settings: Settings | None = None,
    enable_llm: bool = True,
    mlx_model_path: str | None = None,
    profile: ServingProfile = PRODUCTION,
    retriever: SfarRagRetriever | None = None,
) -> FastAPI:
    """Create the FastAPI application serving `profile` (default: the evaluated production profile).

    Retrieval configuration, index, generation settings and provenance policy all come from the
    profile; the per-request retrieval switches of `SearchRequest` (top_k, use_reranker, ...) are
    accepted for backward compatibility but ignored, so that every answer is produced by the
    evaluated pipeline. `retriever` lets tests inject an in-memory retriever."""
    cfg_settings = settings or Settings()
    idx_path = profile.resolve_index_dir(index_dir)

    if retriever is None:
        store = LocalVectorStore.load(idx_path)
        manifest = store.manifest
        emb_provider = manifest.get("embedding_provider", cfg_settings.embedding_provider)
        emb_model = manifest.get("embedding_model", cfg_settings.embedding_model)
        # Apple Silicon: with a local MLX LLM on Metal, keep the PyTorch embedder and reranker on
        # CPU so that they never contend with MLX for GPU memory.
        torch_device = "cpu" if mlx_model_path else None

        embedder = None
        if store.embeddings is not None:
            embedder = build_embedder(
                provider=emb_provider,
                model_name=emb_model,
                base_url=cfg_settings.embedding_base_url,
                api_key=cfg_settings.embedding_api_key,
                index_dir=idx_path,
                device=torch_device,
            )

        reranker = None
        if cfg_settings.reranker_provider != "none":
            try:
                reranker = build_reranker(
                    provider=cfg_settings.reranker_provider,
                    model_name=cfg_settings.reranker_model,
                    device=torch_device,
                )
            except Exception:
                reranker = None

        retriever = SfarRagRetriever(store=store, embedder=embedder, reranker=reranker)
    store = retriever.store
    embedder = retriever.embedder
    reranker = retriever.reranker

    llm = None
    if mlx_model_path:
        from rag_sfar.generation.client import LocalMlxLLM

        llm = LocalMlxLLM(
            model_path=mlx_model_path,
            model_label=Path(mlx_model_path).name,
            temperature=cfg_settings.llm_temperature,
            max_tokens=cfg_settings.llm_max_tokens,
        )
    gen_settings: GeneratorSettings | None = None
    if not mlx_model_path and enable_llm:
        # Transport settings from the environment (RAG_SFAR_LLM_BASE_URL, _MODEL, _API_KEY);
        # the demo page may override them at run time unless RAG_SFAR_DEMO_LOCK_SETTINGS is set.
        # Temperature, token cap and thinking flag come from the profile's generation config.
        gen_settings = GeneratorSettings(
            base_url=cfg_settings.llm_base_url,
            model=cfg_settings.llm_model,
            api_key=cfg_settings.llm_api_key,
        )
        llm = gen_settings.build(cfg_settings.llm_timeout_seconds)
    engine = build_engine(retriever, llm, profile)
    gen_state = GeneratorState(gen_settings, cfg_settings.llm_timeout_seconds)
    rcfg = profile.retrieval_config()

    app = FastAPI(title="RAG-SFAR Clinical Engine", version="1.0.0")
    app.state.engine = engine
    app.state.profile = profile
    app.state.generator = gen_state
    gconf = engine.gen_config
    variants = rob.RobustnessVariants(retriever, rcfg)
    robustness_default = rob.default_choice()

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return DEMO_HTML

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "index_dir": str(idx_path),
            "num_documents": len(store.documents),
            "num_chunks": len(store.chunks),
            "embedding_model": embedder.model_name if embedder else "bm25_only",
            "reranker_model": reranker.model_name if reranker else "none",
            "llm_model": engine.llm.model if engine.llm else None,
            "settings_locked": settings_locked(),
            "profile": profile.name,
            "retrieval_config": rcfg.name,
            "generation_config": engine.gen_config.name if engine.gen_config else "legacy",
        }

    @app.get("/api/catalog")
    def catalog(latest_only: bool = False) -> dict[str, Any]:
        docs = [
            d.model_dump()
            for d in store.documents
            if (not latest_only or d.is_latest_edition)
        ]
        return {"count": len(docs), "documents": docs}

    @app.post("/api/search")
    def api_search(req: SearchRequest) -> dict[str, Any]:
        retrieved, analysis, timings = retriever.retrieve(
            query=req.query,
            config=rcfg,
            override_latest_only=req.latest_only,
            override_domains=req.domains,
        )
        return {
            "query_analysis": analysis.model_dump(),
            "latency_ms": timings,
            "retrieved_chunks": [r.model_dump() for r in retrieved],
        }

    def generator_info() -> dict[str, Any]:
        llm = engine.llm
        info: dict[str, Any] = {
            "available": llm is not None,
            "backend": None if llm is None else ("mlx" if hasattr(llm, "model_path") else "openai"),
            "model": getattr(llm, "model", None),
            "locked": settings_locked() or gen_state.settings is None and llm is not None,
            "settings": gen_state.settings.public() if gen_state.settings else None,
            "last_status": gen_state.last_status,
            # Call options fixed by the evaluated profile (what the generator receives by default).
            "profile_call_options": {
                "profile": profile.name,
                "open_mode": profile.open_mode,
                "max_tokens": gconf.max_tokens if gconf else None,
                "temperature": gconf.temperature if gconf else None,
                "enable_thinking": gconf.enable_thinking if gconf else None,
            },
        }
        if hasattr(llm, "base_url"):
            info["base_url"] = llm.base_url
        info["robustness"] = {"default": robustness_default, "choices": list(rob.CHOICES), "labels": rob.LABELS}
        return info

    @app.get("/api/generator")
    def api_generator() -> dict[str, Any]:
        return generator_info()

    @app.post("/api/generator/test")
    def api_generator_test(req: GeneratorTestRequest) -> dict[str, Any]:
        """List the endpoint's models (`<base_url>/models`). Locked deployments test only the
        configured endpoint. No key in the body = the key currently in memory."""
        cur = gen_state.settings
        if settings_locked() or not req.base_url:
            if cur is None:
                return {"ok": False, "models": [], "error": "Aucun point d'accès OpenAI configuré"}
            return list_models(cur.base_url, cur.api_key)
        key = req.api_key if req.api_key else (cur.api_key if cur and cur.base_url == req.base_url else "")
        return list_models(req.base_url, key)

    @app.post("/api/generator/settings")
    def api_generator_settings(req: GeneratorSettingsRequest) -> dict[str, Any]:
        if settings_locked():
            raise HTTPException(status_code=403, detail="Réglages verrouillés par le déploiement.")
        if not req.base_url.startswith(("http://", "https://")) or not req.model.strip():
            raise HTTPException(status_code=422, detail="URL (http/https) et modèle requis.")
        cur = gen_state.settings
        if req.api_key is None:  # keep the key in memory (same endpoint only)
            key = cur.api_key if cur and cur.base_url == req.base_url else ""
        else:
            key = req.api_key
        gen_state.apply(engine, GeneratorSettings(
            base_url=req.base_url.strip(), model=req.model.strip(), api_key=key,
            max_tokens_override=req.max_tokens_override or None,
            temperature_override=req.temperature_override,
            send_thinking_flag=req.send_thinking_flag,
        ))
        return generator_info()

    @app.post("/api/query/stream")
    def api_query_stream(req: QueryRequest) -> StreamingResponse:
        """Server-sent events: `retrieval`, `token`*, `done`. When the generator fails, a
        `generator_error` event (sanitized message) precedes `done`; the passages of the
        `retrieval` event remain the answer (passages-only fallback)."""

        choice = req.robustness or robustness_default
        if choice not in rob.CHOICES:
            raise HTTPException(status_code=422, detail=f"robustness must be one of {rob.CHOICES}")

        def event_gen():
            sent_retrieval = False
            sent_token = False
            try:
                used = choice
                unavailable = None
                if rob.needs_llm(choice) and engine.llm is None:
                    used = "lexical" if choice == "both" else "none"
                    unavailable = "Normalisation indisponible : aucun générateur configuré."
                if used == "none":
                    eng, cfg = engine, rcfg  # frozen profile, untouched
                else:
                    eng = copy.copy(engine)
                    eng.retriever = variants.retriever(used, engine.llm)
                    cfg = variants.retrieval_config(used)
                for ev in eng.stream_answer(
                    query=req.query,
                    mode=profile.open_mode,
                    config=cfg,
                    retrieval_only=req.retrieval_only,
                ):
                    if ev["type"] == "retrieval":
                        sent_retrieval = True
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                        var = {"type": "variant", "requested": choice, "used": used,
                               "label": rob.LABELS[used], "retrieval_config": cfg.name,
                               "unavailable": unavailable, "rewrite": rob.rewrite_trace(eng.retriever)}
                        yield f"data: {json.dumps(var, ensure_ascii=False)}\n\n"
                        continue
                    elif ev["type"] == "token":
                        sent_token = True
                    elif ev["type"] == "done" and not req.retrieval_only and engine.llm is not None:
                        gen_state.last_status = {"state": "ok", "at": time.time()}
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            except Exception as exc:  # noqa: BLE001
                msg = safe_error(exc)
                if sent_retrieval:
                    gen_state.last_status = {"state": "error", "error": msg, "at": time.time()}
                err = {"type": "generator_error" if sent_retrieval else "error", "message": msg,
                       "partial": sent_token}
                yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
                done = {"type": "done", "answer": "", "generator_failed": True, "latency_ms": {},
                        "verification": {}, "extra": {}}
                yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @app.post("/api/query")
    def api_query(req: QueryRequest) -> dict[str, Any]:
        try:
            resp = engine.answer(
                query=req.query,
                mode=req.mode,
                config=rcfg,
                override_latest_only=req.latest_only,
                override_domains=req.domains,
                retrieval_only=req.retrieval_only,
            )
            return resp.model_dump()
        except Exception as exc:
            # Graceful fallback to retrieval-only if local LLM server is offline
            resp = engine.answer(
                query=req.query,
                mode=req.mode,
                config=rcfg,
                override_latest_only=req.latest_only,
                override_domains=req.domains,
                retrieval_only=True,
            )
            resp.answer = (
                f"[Serveur LLM indisponible ({safe_error(exc)}) — mode retrieval actif]\n\n"
                + resp.answer
            )
            return resp.model_dump()

    # --- OpenAI-Compatible API for seamless Datathon Evaluation Platform integration ---
    @app.get("/v1/models")
    def openai_models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {"id": "rag-sfar-sota", "object": "model", "owned_by": "sfar-datathon"},
                {"id": "rag-sfar-benchmark-open", "object": "model", "owned_by": "sfar-datathon"},
                {"id": "rag-sfar-benchmark-mcq", "object": "model", "owned_by": "sfar-datathon"},
            ],
        }

    @app.post("/v1/chat/completions")
    def openai_chat(req: OpenAIChatRequest) -> dict[str, Any]:
        user_msgs = [m.content for m in req.messages if m.role == "user"]
        if not user_msgs:
            raise HTTPException(status_code=400, detail="No user message provided.")
        query = user_msgs[-1]
        mode = profile.open_mode
        if "benchmark-open" in req.model:
            mode = "benchmark_open"
        elif "benchmark-mcq" in req.model:
            mode = "benchmark_mcq"
        resp = engine.answer(query=query, mode=mode)
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": resp.answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": resp.token_usage.get("prompt_tokens", 0),
                "completion_tokens": resp.token_usage.get("completion_tokens", 0),
                "total_tokens": resp.token_usage.get("total_tokens", 0),
            },
            "sfar_citations": [c.model_dump() for c in resp.citations],
            "sfar_verification": resp.verification.model_dump(),
        }

    return app
