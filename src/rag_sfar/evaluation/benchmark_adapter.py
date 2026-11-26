"""Plug-and-play adapter for `tomboulier/antibioprophylaxie-LLM-benchmark` (`ApproachPort`)
plus exact deterministic scoring compatible with `OpenScorer` & `QCMScorer`."""

from __future__ import annotations

import re
from typing import Any

from rag_sfar.config import RetrievalConfig
from rag_sfar.generation.prompts import build_user_prompt
from rag_sfar.retrieval.pipeline import SfarRagRetriever, format_context_for_llm


def normalize_answer(text: str) -> str:
    """Exact mirror of `antibioprophylaxie-LLM-benchmark` `scorer.normalize`."""
    t = text.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = t.rstrip(".").strip()
    return t


def score_antibioprophylaxie_answer(
    question_type: str,
    expected_answer: str,
    actual_answer: str,
) -> bool:
    """Deterministic scorer 100% aligned with `OpenScorer` and `QCMScorer`."""
    if question_type == "mcq":
        exp_letter = expected_answer.strip().upper()
        m = re.search(r"\b([A-D])\b", actual_answer.upper())
        return (m.group(1) if m else None) == exp_letter

    norm_exp = normalize_answer(expected_answer)
    norm_act = normalize_answer(actual_answer)
    if norm_exp in ("pas d'antibioprophylaxie", "hors périmètre"):
        return norm_exp in norm_act
    molecules = [normalize_answer(m) for m in expected_answer.split("+")]
    return all(m in norm_act for m in molecules)


def score_sourcing_present(actual_answer: str) -> bool:
    """Exact mirror of `antibioprophylaxie-LLM-benchmark` `SourcingScorer`."""
    return bool(re.search(r"\b\d{4}\b", normalize_answer(actual_answer)))


def _format_question_with_choices(question: Any) -> str:
    """Extract question text and append formatted MCQ choices (A. ..., B. ...) when present."""
    q_text = getattr(question, "question_text", None) or getattr(question, "question", str(question))
    choices_obj = getattr(question, "choices", None)
    if choices_obj is None:
        return q_text
    choices_dict = getattr(choices_obj, "choices", choices_obj)
    if isinstance(choices_dict, dict) and choices_dict:
        choices_lines = "\n".join(f"{k}. {v}" for k, v in choices_dict.items())
        return f"{q_text}\n{choices_lines}"
    return q_text


class SfarRagApproach:
    """Drop-in `ApproachPort` adapter for `tomboulier/antibioprophylaxie-LLM-benchmark`.

    Usage tomorrow on LibreDataHub with the evaluation-platform team:
        approach = SfarRagApproach(retriever=retriever, config=RetrievalConfig())
        approach.prepare()
        prompt = approach.build_prompt(question)
    """

    def __init__(
        self,
        retriever: SfarRagRetriever,
        config: RetrievalConfig | None = None,
        approach_name: str = "rag-sfar-sota",
    ) -> None:
        self._retriever = retriever
        self._config = config or RetrievalConfig()
        self._approach_name = approach_name
        self._prepared = False

    @property
    def approach_id(self) -> Any:
        try:
            from llm_benchmark.domain.value_objects import ApproachId

            return ApproachId(self._approach_name)
        except ImportError:
            return self._approach_name

    def prepare(self) -> None:
        self._prepared = True

    def build_prompt(self, question: Any) -> str:
        if not self._prepared:
            self.prepare()
        full_q = _format_question_with_choices(question)
        q_type = str(getattr(question, "question_type", "open")).lower()
        mode = "benchmark_mcq" if "mcq" in q_type else "benchmark_open"
        retrieved, _, _ = self._retriever.retrieve(full_q, config=self._config)
        ctx = format_context_for_llm(retrieved, query=full_q, prune_prose=self._config.use_u_shape_ordering)
        return build_user_prompt(query=full_q, context_block=ctx, mode=mode)
