"""Demo-only robustness variants built beside the frozen serving profile.

Choices (per question, default from RAG_SFAR_DEMO_ROBUSTNESS, else "none"):
- "none": the frozen, evaluated profile, untouched (same retriever, same configuration object).
- "lexical": the profile's retrieval configuration with `use_subword` and `use_medical_lexicon`
  switched on together (no model call), as built by eval_internal/robustness/run_retrieval.py.
- "normalize": `query_rewrite.wrap_retriever(..., variant="normalize", use="add")`: the served
  model normalises the question, the frozen context is kept and the rewrite's passages are added.
- "both": the two together.

Only the conservative normalisation in `add` mode is offered: free reformulation and the
hypothetical-passage variant changed the meaning of questions (reports/agents/Q2_reformulation.md).
Both options were measured on development questions only; they are not part of the evaluation.

Memory: none of the variants loads a model or an index. The character n-gram index is loaded with
the store in every case, the lexical variant only changes two flags of a configuration copy, and
the normalisation wrapper is a small per-request object around the shared retriever (per request so
that its trace, which the page displays, cannot mix two concurrent questions).
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any

from rag_sfar.retrieval.query_rewrite import QueryRewriteRetriever, wrap_retriever

CHOICES = ("none", "lexical", "normalize", "both")
ENV_DEFAULT = "RAG_SFAR_DEMO_ROBUSTNESS"
LEXICAL_FLAGS = {"use_subword": True, "use_medical_lexicon": True}
LABELS = {
    "none": "aucune (configuration gelée évaluée)",
    "lexical": "lexicale (n-grammes de caractères + lexique médical)",
    "normalize": "normalisation de la question par le modèle (mode add)",
    "both": "lexicale + normalisation par le modèle",
}


def default_choice() -> str:
    v = os.environ.get(ENV_DEFAULT, "none").strip().lower() or "none"
    if v not in CHOICES:
        raise ValueError(f"{ENV_DEFAULT}={v!r}; known: {CHOICES}")
    return v


def needs_llm(choice: str) -> bool:
    return choice in ("normalize", "both")


class RobustnessVariants:
    def __init__(self, base_retriever: Any, base_config: Any) -> None:
        self.base_retriever = base_retriever
        self.base_config = base_config
        self._lexical_config = None  # built lazily, cached

    def retrieval_config(self, choice: str):
        if choice in ("lexical", "both"):
            if self._lexical_config is None:
                self._lexical_config = dataclasses.replace(
                    self.base_config, name=f"{self.base_config.name}+subword+lexicon", **LEXICAL_FLAGS
                )
            return self._lexical_config
        return self.base_config

    def retriever(self, choice: str, llm: Any):
        if needs_llm(choice):
            return wrap_retriever(self.base_retriever, llm=llm, variant="normalize", use="add")
        return self.base_retriever


def rewrite_trace(retriever: Any) -> dict[str, Any] | None:
    """What the page shows about the normalisation (None when no wrapper was used)."""
    if not isinstance(retriever, QueryRewriteRetriever) or retriever.last_trace is None:
        return None
    tr = retriever.last_trace
    return {
        "used": tr.used,
        "normalized_question": tr.rewrite if tr.used else None,
        "unchanged": (not tr.used) and not tr.format_error and not tr.guard_rejected,
        "error": tr.format_error or None,
        "n_added": tr.n_added,
        "llm_ms": tr.llm_ms,
    }
