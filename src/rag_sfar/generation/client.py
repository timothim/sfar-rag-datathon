"""OpenAI-compatible clinical generation client (Ollama, vLLM, Mistral, OpenAI, LiteLLM)
plus full end-to-end RagEngine orchestrating Retrieval -> Prompt -> LLM -> Verification."""

from __future__ import annotations

import dataclasses
import re
import time
from typing import Any

from rag_sfar.config import RetrievalConfig, Settings
from rag_sfar.generation.answer_check import check_answer
from rag_sfar.generation.context import assemble_context, select_within_budget
from rag_sfar.generation.prompts import (
    ABSTENTION_SENTENCE,
    SYSTEM_CLINICAL_DETAILED,
    SYSTEM_PROMPTS,
    build_user_prompt,
)
from rag_sfar.generation.settings import LEGACY, GenerationConfig
from rag_sfar.generation.verifier import verify_generation
from rag_sfar.retrieval.context_optimizer import select_generation_context
from rag_sfar.retrieval.pipeline import SfarRagRetriever, format_context_for_llm
from rag_sfar.retrieval.router import detect_affirmed_allergy
from rag_sfar.schemas import Citation, QueryAnalysis, RagResponse, RetrievedChunk


class OpenAICompatibleLLM:
    """Universal chat client compatible with LibreDataHub Ollama/vLLM and cloud OpenAI/Mistral."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        timeout: float = 120.0,
        enable_thinking: bool | None = None,
        top_p: float = 0.0,
        top_k: int = 0,
        presence_penalty: float = 0.0,
    ) -> None:
        from openai import OpenAI

        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.options = {"enable_thinking": enable_thinking, "top_p": top_p, "top_k": top_k,
                        "presence_penalty": presence_penalty}
        self._client = OpenAI(base_url=base_url, api_key=api_key or "none", timeout=timeout)

    def _request_kwargs(self, temperature, max_tokens, opts: dict[str, Any]) -> dict[str, Any]:
        """Chat-completion arguments. `enable_thinking` and `top_k` go through `extra_body`
        (vLLM / SGLang: `chat_template_kwargs`, `top_k`); servers that do not know them ignore
        `extra_body` fields or reject them, so they are sent only when set."""
        o = {**self.options, **{k: v for k, v in opts.items() if v is not None}}
        kw: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }
        if o.get("top_p"):
            kw["top_p"] = o["top_p"]
        if o.get("presence_penalty"):
            kw["presence_penalty"] = o["presence_penalty"]
        extra: dict[str, Any] = {}
        if o.get("enable_thinking") is not None:
            extra["chat_template_kwargs"] = {"enable_thinking": bool(o["enable_thinking"])}
        if o.get("top_k"):
            extra["top_k"] = int(o["top_k"])
        if extra:
            kw["extra_body"] = extra
        return kw

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **opts: Any,
    ) -> tuple[str, dict[str, int]]:
        resp = self._client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **self._request_kwargs(temperature, max_tokens, opts),
        )
        content = strip_reasoning((resp.choices[0].message.content or "").strip())
        usage = {}
        if resp.usage is not None:
            usage = {
                "prompt_tokens": int(resp.usage.prompt_tokens or 0),
                "completion_tokens": int(resp.usage.completion_tokens or 0),
                "total_tokens": int(resp.usage.total_tokens or 0),
            }
        return content, usage

    def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **opts: Any,
    ):
        """Yield incremental text deltas and a final `('__usage__', dict)` tuple."""
        stream = self._client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
            **self._request_kwargs(temperature, max_tokens, opts),
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield ("token", delta)
        yield ("usage", {})


class LocalMlxLLM:
    """Zero-server Apple Silicon GPU local LLM backend powered by `mlx-lm` (deterministic greedy)."""

    def __init__(
        self,
        model_path: str,
        model_label: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 450,
        enable_thinking: bool | None = None,
        top_p: float = 0.0,
        top_k: int = 0,
        presence_penalty: float = 0.0,
    ) -> None:
        from mlx_lm import load as mlx_load

        self.model = model_label or model_path
        self.model_path = model_path
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.options = {"enable_thinking": enable_thinking, "top_p": top_p, "top_k": top_k,
                        "presence_penalty": presence_penalty}
        self._mlx_model, self._tokenizer = mlx_load(model_path)

    def _format_prompt(self, system_prompt: str, user_prompt: str, enable_thinking: bool | None = None) -> str:
        """Chat template. `enable_thinking=False` is passed to the template (Qwen3 / 3.5+ render
        an empty <think></think> block); templates without that variable ignore it. None keeps
        the template default (mlx-lm then turns thinking ON for Qwen3.5+)."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if hasattr(self._tokenizer, "apply_chat_template"):
            kwargs: dict[str, Any] = {}
            if enable_thinking is not None:
                kwargs["enable_thinking"] = bool(enable_thinking)
            return self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, **kwargs
            )
        return f"{system_prompt}\n\n{user_prompt}\n"

    def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **opts: Any,
    ):
        """Yield real-time token deltas on Apple Silicon GPU via `mlx_lm.stream_generate`."""
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_logits_processors, make_sampler

        o = {**self.options, **{k: v for k, v in opts.items() if v is not None}}
        prompt_str = self._format_prompt(system_prompt, user_prompt, o.get("enable_thinking"))
        temp = self.temperature if temperature is None else temperature
        max_tok = self.max_tokens if max_tokens is None else max_tokens
        sampler = make_sampler(temp=temp, top_p=float(o.get("top_p") or 0.0), top_k=int(o.get("top_k") or 0))
        extra: dict[str, Any] = {}
        if o.get("presence_penalty"):
            extra["logits_processors"] = make_logits_processors(
                presence_penalty=float(o["presence_penalty"]), presence_context_size=256
            )

        prompt_tokens = 0
        completion_tokens = 0
        for resp in stream_generate(
            self._mlx_model,
            self._tokenizer,
            prompt=prompt_str,
            max_tokens=max_tok,
            sampler=sampler,
            **extra,
        ):
            if resp.text:
                yield ("token", resp.text)
            prompt_tokens = int(resp.prompt_tokens)
            completion_tokens = int(resp.generation_tokens)

        yield (
            "usage",
            {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **opts: Any,
    ) -> tuple[str, dict[str, int]]:
        chunks: list[str] = []
        usage: dict[str, int] = {}
        for ev_type, payload in self.stream_complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            **opts,
        ):
            if ev_type == "token":
                chunks.append(payload)
            elif ev_type == "usage":
                usage = payload
        return strip_reasoning("".join(chunks).strip()), usage


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.S)


def strip_reasoning(text: str) -> str:
    """Remove a <think>...</think> block (reasoning models) from a completion; an unterminated
    block (output cut while thinking) leaves an empty answer."""
    text = _THINK_RE.sub("", text)
    if "<think>" in text:
        text = text.split("<think>", 1)[0]
    return text.strip()


def build_citations(retrieved: list[RetrievedChunk]) -> list[Citation]:
    citations: list[Citation] = []
    for i, item in enumerate(retrieved, start=1):
        c = item.chunk
        citations.append(
            Citation(
                citation_id=f"S{i}",
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                doc_title=c.doc_title,
                effective_year=c.effective_year,
                version_label=c.version_label,
                doc_type=c.doc_type,
                section_path=c.section_path,
                grade_levels=c.grade_levels,
                is_latest_edition=c.is_latest_edition,
                superseded_by=c.superseded_by,
                landing_url=c.landing_url,
                excerpt=c.text[:480] + ("..." if len(c.text) > 480 else ""),
                chunk_type=c.chunk_type,
                score=round(item.final_score, 5),
            )
        )
    return citations


def allergy_context_note(query: str) -> str:
    """Context note added when — and only when — the question states a patient allergy.

    Generic wording: it quotes the question's own allergy statement and assumes no allergen
    class (the previous version asserted a beta-lactam allergy on any 'alternative' or
    'pénicilline' mention)."""
    statement = detect_affirmed_allergy(query)
    if not statement:
        return ""
    return (
        f"NOTE : la question mentionne une allergie (« {statement} »). Recherche dans les extraits "
        "la conduite prévue pour ce terrain et applique-la ; si les extraits ne la précisent pas, "
        "signale-le.\n\n"
    )



def generation_budget(mode: str) -> tuple[int, int]:
    """(max chunks, max characters) of the legacy generation context per output mode.

    Hyper-parameters tuned on the development set (declared as such, see audit). Used only by
    `GenerationConfig(selection="legacy")`, the historical small-model budget."""
    max_chunks = 7 if mode == "benchmark_mcq" else (5 if mode == "benchmark_open" else 6)
    max_chars = 6500 if mode != "benchmark_open" else 5200
    return max_chunks, max_chars


def build_generation_context(
    retrieved: list[RetrievedChunk],
    analysis: QueryAnalysis,
    cfg: RetrievalConfig,
    query: str,
    mode: str = "clinical_detailed",
    gen_config: GenerationConfig | None = None,
) -> tuple[list[RetrievedChunk], str]:
    """Select the passages shown to the LLM and format the context block.

    Shared by the engine (sync and streaming), the benchmark adapter and the replay tool so that
    every entry point evaluates the same context. Without `gen_config` the historical behaviour
    is kept exactly (budget and pruning follow `cfg.use_context_pruning`)."""
    g = gen_config or LEGACY
    pruning = cfg.use_context_pruning
    if g.selection == "legacy":
        if pruning:
            max_chunks, max_chars = generation_budget(mode)
            gen_chunks = select_generation_context(
                retrieved,
                is_allergy_query=("allergy" in analysis.modifiers),
                max_chunks=max_chunks,
                max_total_chars=max_chars,
            )
        else:
            gen_chunks = list(retrieved)
    else:
        gen_chunks = select_within_budget(retrieved, g.max_context_chunks, g.max_context_chars)
    prune_prose = pruning if g.prune_prose is None else g.prune_prose
    allergy_note = pruning if g.allergy_note is None else g.allergy_note
    if g.context_format == "legacy":
        u_shape = cfg.use_u_shape_ordering if g is LEGACY else g.context_order == "u_shape"
        context_block = format_context_for_llm(
            gen_chunks, query=query, reorder_u_shape=u_shape, prune_prose=prune_prose
        )
    else:
        gen_chunks, context_block = assemble_context(
            gen_chunks,
            g.replace(max_context_chunks=10**6, max_context_chars=10**9, prune_prose=prune_prose),
            query=query,
        )
    if allergy_note:
        context_block = allergy_context_note(query) + context_block
    return gen_chunks, context_block


def attach_provenance(answer: str, gen_chunks: list[RetrievedChunk]) -> tuple[str, bool]:
    """Append "(SFAR <année> [S1])" when a short answer carries no year.

    Returns (answer, added). The added year is that of [S1], not necessarily of the source the
    model used: it is display-only and must not be counted as sourcing in evaluations."""
    if gen_chunks and not re.search(r"\b\d{4}\b", answer) and gen_chunks[0].chunk.effective_year:
        return f"{answer} (SFAR {gen_chunks[0].chunk.effective_year} [S1])", True
    return answer, False


BENCHMARK_MODES = ("benchmark_open", "benchmark_mcq")

COVERAGE_NOTE = (
    "NOTE : la recherche documentaire n'a trouvé aucun passage proche de la question. Vérifie "
    "avec soin que les extraits traitent bien la situation demandée avant de répondre.\n\n"
)


def system_prompt_for(mode: str) -> str:
    return SYSTEM_PROMPTS.get(mode, SYSTEM_CLINICAL_DETAILED)


def default_max_tokens(mode: str) -> int | None:
    return 200 if mode == "benchmark_open" else (320 if mode == "benchmark_mcq" else None)


def llm_call_options(gen_config: GenerationConfig | None) -> dict[str, Any]:
    """Keyword arguments for `llm.complete` derived from the generation settings. Empty for the
    legacy configuration so that third-party LLM stubs with the historical signature still work."""
    if gen_config is None:
        return {}
    opts: dict[str, Any] = {"temperature": gen_config.temperature}
    if gen_config.enable_thinking is not None:
        opts["enable_thinking"] = gen_config.enable_thinking
    if gen_config.top_p:
        opts["top_p"] = gen_config.top_p
    if gen_config.top_k:
        opts["top_k"] = gen_config.top_k
    if gen_config.presence_penalty:
        opts["presence_penalty"] = gen_config.presence_penalty
    return opts


def coverage_supported(timings: dict[str, Any]) -> bool | None:
    """Retrieval coverage flag (B1): True / False, or None when the retriever does not expose it."""
    v = timings.get("coverage_supported")
    if v is None or v < 0:
        return None
    return bool(v >= 0.5)


class SfarRagEngine:
    """Complete RAG-SFAR orchestrator combining retrieval, grounded prompting, LLM, and verification."""

    def __init__(
        self,
        retriever: SfarRagRetriever | None,
        llm: OpenAICompatibleLLM | LocalMlxLLM | None = None,
        default_config: RetrievalConfig | None = None,
        attach_provenance: bool = False,
        gen_config: GenerationConfig | None = None,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.default_config = default_config or RetrievalConfig()
        # Off by default (evaluation): when on, benchmark modes append "(SFAR <année> [S1])" to
        # answers without a year, and the response says so (`provenance_added_by_code`).
        self.attach_provenance = attach_provenance
        # None = historical generation behaviour (see GenerationConfig).
        self.gen_config = gen_config

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        retriever: SfarRagRetriever,
        default_config: RetrievalConfig | None = None,
        enable_llm: bool = True,
        attach_provenance: bool = False,
        gen_config: GenerationConfig | None = None,
    ) -> "SfarRagEngine":
        llm = None
        if enable_llm:
            llm = OpenAICompatibleLLM(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                timeout=settings.llm_timeout_seconds,
            )
        return cls(
            retriever=retriever, llm=llm, default_config=default_config,
            attach_provenance=attach_provenance, gen_config=gen_config,
        )

    def answer(
        self,
        query: str,
        mode: str = "clinical_detailed",
        config: RetrievalConfig | None = None,
        override_latest_only: bool | None = None,
        override_domains: list[str] | None = None,
        retrieval_only: bool = False,
        gen_config: GenerationConfig | None = None,
    ) -> RagResponse:
        """Run full RAG pipeline for a clinical question."""
        cfg = config or self.default_config
        retrieved, analysis, timings = self.retriever.retrieve(
            query=query,
            config=cfg,
            override_latest_only=override_latest_only,
            override_domains=override_domains,
        )
        return self.generate(
            query, retrieved, analysis, timings, mode=mode, config=cfg,
            retrieval_only=retrieval_only, gen_config=gen_config,
        )

    def _prepare(self, query, retrieved, analysis, timings, mode, cfg, g):
        gen_chunks, context_block = build_generation_context(retrieved, analysis, cfg, query, mode, g)
        effective_mode = mode
        if mode in ("clinical_detailed", "clinical_concise", "clinical_production") and analysis.temporal_mode == "all_versions":
            effective_mode = "temporal_diff"
        covered = coverage_supported(timings)
        gate = g.coverage_gate if g else "off"
        if gate == "note" and covered is False:
            context_block = COVERAGE_NOTE + context_block
        return gen_chunks, context_block, effective_mode, covered, gate

    def generate(
        self,
        query: str,
        retrieved: list[RetrievedChunk],
        analysis: QueryAnalysis,
        timings: dict[str, Any] | None = None,
        mode: str = "clinical_detailed",
        config: RetrievalConfig | None = None,
        retrieval_only: bool = False,
        gen_config: GenerationConfig | None = None,
    ) -> RagResponse:
        """Generation stage on an already retrieved context (used by `answer` and by the replay
        tool, which caches retrieval outputs)."""
        cfg = config or self.default_config
        g = gen_config or self.gen_config
        timings = dict(timings or {})
        gen_chunks, context_block, effective_mode, covered, gate = self._prepare(
            query, retrieved, analysis, timings, mode, cfg, g
        )
        citations = build_citations(gen_chunks)
        base_extra = {
            "context_chars": len(context_block),
            "n_passages": len(gen_chunks),
            "coverage_supported": covered,
            "provenance_added_by_code": False,
        }

        if retrieval_only or self.llm is None:
            fallback_answer = (
                "Mode retrieval seul (aucun serveur LLM connecté). "
                "Consultez les extraits SFAR classés ci-dessous [S1]–[S"
                f"{len(citations)}] ou configurez RAG_SFAR_LLM_BASE_URL (Ollama/vLLM)."
            )
            return RagResponse(
                query=query, answer=fallback_answer, mode=effective_mode, query_analysis=analysis,
                citations=citations, retrieved_chunks=retrieved, latency_ms=timings,
                model_used="retrieval_only", config_name=cfg.name, extra=base_extra,
            )

        if gate == "refuse" and covered is False and effective_mode not in BENCHMARK_MODES:
            verification = verify_generation(ABSTENTION_SENTENCE, gen_chunks, mode=effective_mode)
            return RagResponse(
                query=query, answer=ABSTENTION_SENTENCE, mode=effective_mode, query_analysis=analysis,
                citations=citations, retrieved_chunks=gen_chunks, verification=verification,
                latency_ms=timings, token_usage={}, model_used=self.llm.model, config_name=cfg.name,
                extra={**base_extra, "coverage_refused": True},
            )

        system_prompt = system_prompt_for(effective_mode)
        user_prompt = build_user_prompt(query=query, context_block=context_block, mode=effective_mode,
                                        question_first=bool(g and g.question_first))
        max_toks = (g.max_tokens if g and g.max_tokens else None) or default_max_tokens(effective_mode)
        opts = llm_call_options(g)
        t_gen = time.perf_counter()
        raw_generation, token_usage = self.llm.complete(
            system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=max_toks, **opts
        )
        raw_answer = _final_answer(raw_generation, effective_mode)
        timings["generation_ms"] = round((time.perf_counter() - t_gen) * 1000, 2)
        timings["total_ms"] = round(timings.get("total_retrieval_ms", 0.0) + timings["generation_ms"], 2)

        verification = verify_generation(raw_answer, gen_chunks, mode=effective_mode)

        # Verifier-guided repair: if a tracked drug molecule is absent from all shown passages,
        # one corrective pass.
        self_corrected = False
        if verification.ungrounded_molecules:
            repair_prompt = (
                f"{user_prompt}\n\n"
                f"TA RÉPONSE PRÉCÉDENTE : {raw_answer}\n"
                f"ALERTE SÉCURITÉ CLINIQUE : Les molécules suivantes ne figurent PAS dans les "
                f"extraits SFAR [S1]–[S{len(gen_chunks)}] : {', '.join(verification.ungrounded_molecules)}. "
                f"Corrige ta réponse en t'appuyant UNIQUEMENT sur les molécules explicitement "
                f"présentes dans les extraits fournis (ou réponds 'Hors périmètre' si les extraits ne permettent pas de répondre)."
            )
            t_rep = time.perf_counter()
            repaired_gen, rep_usage = self.llm.complete(
                system_prompt=system_prompt, user_prompt=repair_prompt, max_tokens=max_toks, **opts
            )
            repaired_answer = _final_answer(repaired_gen, effective_mode)
            timings["self_correction_ms"] = round((time.perf_counter() - t_rep) * 1000, 2)
            timings["total_ms"] = round(timings.get("total_ms", 0.0) + timings["self_correction_ms"], 2)
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                token_usage[k] = token_usage.get(k, 0) + rep_usage.get(k, 0)
            rep_verif = verify_generation(repaired_answer, gen_chunks, mode=effective_mode)
            if rep_verif.grounding_score >= verification.grounding_score:
                raw_answer = repaired_answer
                verification = rep_verif
                self_corrected = True

        # Deterministic answer check (doses, drugs, citations against the shown passages).
        check = None
        check_regenerated = False
        if g is not None and g.answer_check != "off" and effective_mode not in BENCHMARK_MODES:
            check = check_answer(raw_answer, gen_chunks, is_abstention=verification.is_abstention, query=query)
            if check.flagged and g.answer_check == "regenerate":
                fix_prompt = (
                    f"{user_prompt}\n\nTA RÉPONSE PRÉCÉDENTE :\n{raw_answer}\n\n"
                    "CONTRÔLE AUTOMATIQUE : " + " ; ".join(check.reasons()) + ". Réécris la réponse en "
                    "reprenant exactement les doses, unités et molécules écrites dans les extraits, avec une "
                    "source [Sx] valide après chaque phrase."
                )
                t_fix = time.perf_counter()
                fixed_gen, fix_usage = self.llm.complete(
                    system_prompt=system_prompt, user_prompt=fix_prompt, max_tokens=max_toks, **opts
                )
                timings["answer_check_ms"] = round((time.perf_counter() - t_fix) * 1000, 2)
                timings["total_ms"] = round(timings.get("total_ms", 0.0) + timings["answer_check_ms"], 2)
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    token_usage[k] = token_usage.get(k, 0) + fix_usage.get(k, 0)
                fixed = _final_answer(fixed_gen, effective_mode)
                fixed_verif = verify_generation(fixed, gen_chunks, mode=effective_mode)
                fixed_check = check_answer(fixed, gen_chunks, is_abstention=fixed_verif.is_abstention, query=query)
                if not fixed_check.flagged:
                    raw_answer, verification, check, check_regenerated = fixed, fixed_verif, fixed_check, True
            if check.flagged:
                verification.warnings.append("Contrôle automatique : " + " ; ".join(check.reasons()))

        # Optional display-only provenance for benchmark modes (off by default; flagged when used)
        provenance_added = False
        if self.attach_provenance and effective_mode in BENCHMARK_MODES:
            raw_answer, provenance_added = attach_provenance(raw_answer, gen_chunks)
        verification.provenance_added_by_code = provenance_added

        return RagResponse(
            query=query,
            answer=raw_answer,
            mode=effective_mode,
            query_analysis=analysis,
            citations=citations,
            retrieved_chunks=gen_chunks,
            verification=verification,
            latency_ms=timings,
            token_usage=token_usage,
            model_used=self.llm.model,
            config_name=cfg.name,
            extra={
                **base_extra,
                "self_corrected": self_corrected,
                "reasoning_trace": raw_generation if raw_generation != raw_answer else "",
                "provenance_added_by_code": provenance_added,
                "prompt_chars": len(system_prompt) + len(user_prompt),
                "answer_check": dataclasses.asdict(check) if check is not None else None,
                "answer_check_regenerated": check_regenerated,
            },
        )

    def stream_answer(
        self,
        query: str,
        mode: str = "clinical_detailed",
        config: RetrievalConfig | None = None,
        override_latest_only: bool | None = None,
        override_domains: list[str] | None = None,
        retrieval_only: bool = False,
        gen_config: GenerationConfig | None = None,
    ):
        """Stream retrieval results immediately (< 250 ms), then stream LLM tokens live, then verify."""
        cfg = config or self.default_config
        g = gen_config or self.gen_config
        retrieved, analysis, timings = self.retriever.retrieve(
            query=query,
            config=cfg,
            override_latest_only=override_latest_only,
            override_domains=override_domains,
        )
        gen_chunks, context_block, effective_mode, covered, gate = self._prepare(
            query, retrieved, analysis, timings, mode, cfg, g
        )
        citations = build_citations(gen_chunks)

        yield {
            "type": "retrieval",
            "query_analysis": analysis.model_dump(),
            "latency_ms": timings,
            "retrieved_chunks": [r.model_dump() for r in gen_chunks],
            "citations": [c.model_dump() for c in citations],
            "model_used": self.llm.model if (self.llm and not retrieval_only) else "retrieval_only",
        }

        if retrieval_only or self.llm is None:
            fallback = (
                f"Mode retrieval seul — {len(citations)} extraits SFAR classés [S1]–[S{len(citations)}] ci-contre."
            )
            yield {"type": "token", "text": fallback}
            yield {"type": "done", "answer": fallback, "latency_ms": timings, "verification": {}, "extra": {}}
            return

        if gate == "refuse" and covered is False and effective_mode not in BENCHMARK_MODES:
            yield {"type": "token", "text": ABSTENTION_SENTENCE}
            yield {
                "type": "done", "answer": ABSTENTION_SENTENCE, "full_generation": "", "latency_ms": timings,
                "token_usage": {}, "verification": verify_generation(ABSTENTION_SENTENCE, gen_chunks, mode=effective_mode).model_dump(),
                "model_used": self.llm.model, "extra": {"coverage_refused": True, "provenance_added_by_code": False},
            }
            return

        system_prompt = system_prompt_for(effective_mode)
        user_prompt = build_user_prompt(query=query, context_block=context_block, mode=effective_mode,
                                        question_first=bool(g and g.question_first))
        max_toks = (g.max_tokens if g and g.max_tokens else None) or default_max_tokens(effective_mode)
        opts = llm_call_options(g)

        t_gen = time.perf_counter()
        chunks_out: list[str] = []
        token_usage: dict[str, int] = {}
        for ev_type, payload in self.llm.stream_complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_toks,
            **opts,
        ):
            if ev_type == "token":
                chunks_out.append(payload)
                yield {"type": "token", "text": payload}
            elif ev_type == "usage":
                token_usage = payload

        raw_generation = strip_reasoning("".join(chunks_out).strip())
        raw_answer = _final_answer(raw_generation, effective_mode)
        timings["generation_ms"] = round((time.perf_counter() - t_gen) * 1000, 2)
        timings["total_ms"] = round(timings.get("total_retrieval_ms", 0.0) + timings["generation_ms"], 2)

        verification = verify_generation(raw_answer, gen_chunks, mode=effective_mode)
        self_corrected = False
        if verification.ungrounded_molecules:
            repair_prompt = (
                f"{user_prompt}\n\n"
                f"TA RÉPONSE PRÉCÉDENTE : {raw_answer}\n"
                f"ALERTE SÉCURITÉ CLINIQUE : Molécules hors-source : {', '.join(verification.ungrounded_molecules)}. "
                f"Corrige en utilisant UNIQUEMENT les extraits SFAR fournis."
            )
            t_rep = time.perf_counter()
            repaired_gen, rep_usage = self.llm.complete(
                system_prompt=system_prompt, user_prompt=repair_prompt, max_tokens=max_toks, **opts
            )
            repaired_answer = _final_answer(repaired_gen, effective_mode)
            timings["self_correction_ms"] = round((time.perf_counter() - t_rep) * 1000, 2)
            timings["total_ms"] = round(timings["total_ms"] + timings["self_correction_ms"], 2)
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                token_usage[k] = token_usage.get(k, 0) + rep_usage.get(k, 0)
            rep_verif = verify_generation(repaired_answer, gen_chunks, mode=effective_mode)
            if rep_verif.grounding_score >= verification.grounding_score:
                raw_answer = repaired_answer
                verification = rep_verif
                self_corrected = True

        yield {
            "type": "done",
            "answer": raw_answer,
            "full_generation": raw_generation,
            "latency_ms": timings,
            "token_usage": token_usage,
            "verification": verification.model_dump(),
            "model_used": self.llm.model,
            "extra": {
                "self_corrected": self_corrected,
                "reasoning_trace": raw_generation if raw_generation != raw_answer else "",
                # The streaming path never appends a source.
                "provenance_added_by_code": False,
            },
        }


def _final_answer(raw_generation: str, mode: str) -> str:
    return _extract_benchmark_final_line(raw_generation) if mode in BENCHMARK_MODES else raw_generation


def _extract_benchmark_final_line(raw_text: str) -> str:
    """Extract the final clean answer from a Verify-Then-Answer structured benchmark response."""
    matches = list(
        re.finditer(r"(?:Ligne\s*2\s*[—–-]\s*)?\*{0,2}R[ÉE]PONSE\*{0,2}\s*:\s*(.+)", raw_text, re.I)
    )
    if matches:
        ans = matches[-1].group(1).strip().splitlines()[0].strip()
        return ans.strip("* ").strip()
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    return lines[-1].strip("* ").strip() if lines else raw_text.strip()
