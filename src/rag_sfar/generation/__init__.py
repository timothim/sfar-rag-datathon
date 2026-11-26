"""Grounded clinical generation, prompts, and hallucination verification."""

from rag_sfar.generation.client import OpenAICompatibleLLM, SfarRagEngine, build_citations
from rag_sfar.generation.prompts import (
    SYSTEM_BENCHMARK_MCQ,
    SYSTEM_BENCHMARK_OPEN,
    SYSTEM_CLINICAL_DETAILED,
    SYSTEM_TEMPORAL_DIFF,
    build_user_prompt,
)
from rag_sfar.generation.verifier import verify_generation

__all__ = [
    "OpenAICompatibleLLM",
    "SfarRagEngine",
    "SYSTEM_BENCHMARK_MCQ",
    "SYSTEM_BENCHMARK_OPEN",
    "SYSTEM_CLINICAL_DETAILED",
    "SYSTEM_TEMPORAL_DIFF",
    "build_citations",
    "build_user_prompt",
    "verify_generation",
]
