"""OpenAI-compatible clinical generation client (Ollama, vLLM, Mistral, OpenAI, LiteLLM)
plus full end-to-end RagEngine orchestrating Retrieval -> Prompt -> LLM -> Verification."""

from __future__ import annotations

import re
import time
from typing import Any

from rag_sfar.config import RetrievalConfig, Settings
from rag_sfar.generation.prompts import (
    SYSTEM_BENCHMARK_MCQ,
    SYSTEM_BENCHMARK_OPEN,
    SYSTEM_CLINICAL_CONCISE,
    SYSTEM_CLINICAL_DETAILED,
    SYSTEM_TEMPORAL_DIFF,
    build_user_prompt,
)
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
    ) -> None:
        from openai import OpenAI

        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = OpenAI(base_url=base_url, api_key=api_key or "none", timeout=timeout)

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, dict[str, int]]:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=self.max_tokens if max_tokens is None else max_tokens,
        )
        content = (resp.choices[0].message.content or "").strip()
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
    ):
        """Yield incremental text deltas and a final `('__usage__', dict)` tuple."""
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=self.max_tokens if max_tokens is None else max_tokens,
            stream=True,
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
    ) -> None:
        from mlx_lm import load as mlx_load

        self.model = model_label or model_path
        self.model_path = model_path
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._mlx_model, self._tokenizer = mlx_load(model_path)

    def _format_prompt(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if hasattr(self._tokenizer, "apply_chat_template"):
            return self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        return f"{system_prompt}\n\n{user_prompt}\n"

    def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """Yield real-time token deltas on Apple Silicon GPU via `mlx_lm.stream_generate`."""
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        prompt_str = self._format_prompt(system_prompt, user_prompt)
        temp = self.temperature if temperature is None else temperature
        max_tok = self.max_tokens if max_tokens is None else max_tokens
        sampler = make_sampler(temp=temp)

        prompt_tokens = 0
        completion_tokens = 0
        for resp in stream_generate(
            self._mlx_model,
            self._tokenizer,
            prompt=prompt_str,
            max_tokens=max_tok,
            sampler=sampler,
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
    ) -> tuple[str, dict[str, int]]:
        chunks: list[str] = []
        usage: dict[str, int] = {}
        for ev_type, payload in self.stream_complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if ev_type == "token":
                chunks.append(payload)
            elif ev_type == "usage":
                usage = payload
        return "".join(chunks).strip(), usage


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
    """(max chunks, max characters) of the generation context per output mode.

    Hyper-parameters tuned on the development set (declared as such, see audit)."""
    max_chunks = 7 if mode == "benchmark_mcq" else (5 if mode == "benchmark_open" else 6)
    max_chars = 6500 if mode != "benchmark_open" else 5200
    return max_chunks, max_chars


def build_generation_context(
    retrieved: list[RetrievedChunk],
    analysis: QueryAnalysis,
    cfg: RetrievalConfig,
    query: str,
    mode: str = "clinical_detailed",
) -> tuple[list[RetrievedChunk], str]:
    """Select the chunks shown to the LLM and format the context block.

    Shared by the engine (sync and streaming) and the benchmark adapter so that every entry
    point evaluates the same context."""
    max_chunks, max_chars = generation_budget(mode)
    gen_chunks = (
        select_generation_context(
            retrieved,
            is_allergy_query=("allergy" in analysis.modifiers),
            max_chunks=max_chunks,
            max_total_chars=max_chars,
        )
        if cfg.use_context_pruning
        else retrieved
    )
    context_block = format_context_for_llm(
        gen_chunks,
        query=query,
        reorder_u_shape=cfg.use_u_shape_ordering,
        prune_prose=cfg.use_context_pruning,
    )
    if cfg.use_context_pruning:
        context_block = allergy_context_note(query) + context_block
    return gen_chunks, context_block


def attach_provenance(answer: str, gen_chunks: list[RetrievedChunk]) -> tuple[str, bool]:
    """Append "(SFAR <année> [S1])" when a short answer carries no year.

    Returns (answer, added). The added year is that of [S1], not necessarily of the source the
    model used: it is display-only and must not be counted as sourcing in evaluations."""
    if gen_chunks and not re.search(r"\b\d{4}\b", answer) and gen_chunks[0].chunk.effective_year:
        return f"{answer} (SFAR {gen_chunks[0].chunk.effective_year} [S1])", True
    return answer, False


class SfarRagEngine:
    """Complete RAG-SFAR orchestrator combining retrieval, grounded prompting, LLM, and verification."""

    def __init__(
        self,
        retriever: SfarRagRetriever,
        llm: OpenAICompatibleLLM | LocalMlxLLM | None = None,
        default_config: RetrievalConfig | None = None,
        attach_provenance: bool = False,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.default_config = default_config or RetrievalConfig()
        # Off by default (evaluation): when on, benchmark modes append "(SFAR <année> [S1])" to
        # answers without a year, and the response says so (`provenance_added_by_code`).
        self.attach_provenance = attach_provenance

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        retriever: SfarRagRetriever,
        default_config: RetrievalConfig | None = None,
        enable_llm: bool = True,
        attach_provenance: bool = False,
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
            retriever=retriever, llm=llm, default_config=default_config, attach_provenance=attach_provenance
        )

    def answer(
        self,
        query: str,
        mode: str = "clinical_detailed",
        config: RetrievalConfig | None = None,
        override_latest_only: bool | None = None,
        override_domains: list[str] | None = None,
        retrieval_only: bool = False,
    ) -> RagResponse:
        """Run full RAG pipeline for a clinical question."""
        cfg = config or self.default_config
        retrieved, analysis, timings = self.retriever.retrieve(
            query=query,
            config=cfg,
            override_latest_only=override_latest_only,
            override_domains=override_domains,
        )
        gen_chunks, context_block = build_generation_context(retrieved, analysis, cfg, query, mode)
        citations = build_citations(gen_chunks)

        # Auto-select temporal diff prompt if user explicitly asked for edition comparison
        effective_mode = mode
        if mode in ("clinical_detailed", "clinical_concise") and analysis.temporal_mode == "all_versions":
            effective_mode = "temporal_diff"

        if retrieval_only or self.llm is None:
            fallback_answer = (
                "Mode retrieval seul (aucun serveur LLM connecté). "
                "Consultez les extraits SFAR classés ci-dessous [S1]–[S"
                f"{len(citations)}] ou configurez RAG_SFAR_LLM_BASE_URL (Ollama/vLLM)."
            )
            return RagResponse(
                query=query,
                answer=fallback_answer,
                mode=effective_mode,
                query_analysis=analysis,
                citations=citations,
                retrieved_chunks=retrieved,
                latency_ms=timings,
                model_used="retrieval_only",
                config_name=cfg.name,
                extra={"context_chars": len(context_block), "provenance_added_by_code": False},
            )

        system_prompt = {
            "clinical_detailed": SYSTEM_CLINICAL_DETAILED,
            "clinical_concise": SYSTEM_CLINICAL_CONCISE,
            "temporal_diff": SYSTEM_TEMPORAL_DIFF,
            "benchmark_open": SYSTEM_BENCHMARK_OPEN,
            "benchmark_mcq": SYSTEM_BENCHMARK_MCQ,
        }.get(effective_mode, SYSTEM_CLINICAL_DETAILED)

        user_prompt = build_user_prompt(query=query, context_block=context_block, mode=effective_mode)
        t_gen = time.perf_counter()
        max_toks = (
            200
            if effective_mode == "benchmark_open"
            else (320 if effective_mode == "benchmark_mcq" else None)
        )
        raw_generation, token_usage = self.llm.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_toks,
        )
        raw_answer = _extract_benchmark_final_line(raw_generation) if effective_mode in ("benchmark_open", "benchmark_mcq") else raw_generation
        timings["generation_ms"] = round((time.perf_counter() - t_gen) * 1000, 2)
        timings["total_ms"] = round(timings.get("total_retrieval_ms", 0.0) + timings["generation_ms"], 2)

        verification = verify_generation(raw_answer, gen_chunks, mode=effective_mode)

        # Self-MedRAG (2026) Active Verifier-Guided Repair: if a drug molecule was hallucinated
        # outside all retrieved SFAR chunks, trigger ONE deterministic corrective pass.
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
                system_prompt=system_prompt,
                user_prompt=repair_prompt,
                max_tokens=max_toks,
            )
            repaired_answer = (
                _extract_benchmark_final_line(repaired_gen)
                if effective_mode in ("benchmark_open", "benchmark_mcq")
                else repaired_gen
            )
            timings["self_correction_ms"] = round((time.perf_counter() - t_rep) * 1000, 2)
            timings["total_ms"] = round(
                timings.get("total_ms", 0.0) + timings["self_correction_ms"], 2
            )
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                token_usage[k] = token_usage.get(k, 0) + rep_usage.get(k, 0)
            rep_verif = verify_generation(repaired_answer, gen_chunks, mode=effective_mode)
            if rep_verif.grounding_score >= verification.grounding_score:
                raw_answer = repaired_answer
                verification = rep_verif
                self_corrected = True

        # Optional display-only provenance for benchmark modes (off by default; flagged when used)
        provenance_added = False
        if self.attach_provenance and effective_mode in ("benchmark_open", "benchmark_mcq"):
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
                "context_chars": len(context_block),
                "self_corrected": self_corrected,
                "reasoning_trace": raw_generation if raw_generation != raw_answer else "",
                "provenance_added_by_code": provenance_added,
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
    ):
        """Stream retrieval results immediately (< 250 ms), then stream LLM tokens live, then verify."""
        cfg = config or self.default_config
        retrieved, analysis, timings = self.retriever.retrieve(
            query=query,
            config=cfg,
            override_latest_only=override_latest_only,
            override_domains=override_domains,
        )
        gen_chunks, context_block = build_generation_context(retrieved, analysis, cfg, query, mode)
        citations = build_citations(gen_chunks)
        effective_mode = mode
        if mode in ("clinical_detailed", "clinical_concise") and analysis.temporal_mode == "all_versions":
            effective_mode = "temporal_diff"

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

        system_prompt = {
            "clinical_detailed": SYSTEM_CLINICAL_DETAILED,
            "clinical_concise": SYSTEM_CLINICAL_CONCISE,
            "temporal_diff": SYSTEM_TEMPORAL_DIFF,
            "benchmark_open": SYSTEM_BENCHMARK_OPEN,
            "benchmark_mcq": SYSTEM_BENCHMARK_MCQ,
        }.get(effective_mode, SYSTEM_CLINICAL_DETAILED)
        user_prompt = build_user_prompt(query=query, context_block=context_block, mode=effective_mode)
        max_toks = (
            200
            if effective_mode == "benchmark_open"
            else (320 if effective_mode == "benchmark_mcq" else None)
        )

        t_gen = time.perf_counter()
        chunks_out: list[str] = []
        token_usage: dict[str, int] = {}
        for ev_type, payload in self.llm.stream_complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_toks,
        ):
            if ev_type == "token":
                chunks_out.append(payload)
                yield {"type": "token", "text": payload}
            elif ev_type == "usage":
                token_usage = payload

        raw_generation = "".join(chunks_out).strip()
        raw_answer = (
            _extract_benchmark_final_line(raw_generation)
            if effective_mode in ("benchmark_open", "benchmark_mcq")
            else raw_generation
        )
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
                system_prompt=system_prompt,
                user_prompt=repair_prompt,
                max_tokens=max_toks,
            )
            repaired_answer = (
                _extract_benchmark_final_line(repaired_gen)
                if effective_mode in ("benchmark_open", "benchmark_mcq")
                else repaired_gen
            )
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
