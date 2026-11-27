"""Demo-only robustness variants built beside the frozen serving profile.

Choices (per question, default from RAG_SFAR_DEMO_ROBUSTNESS, else "none"):
- "none": the frozen, evaluated profile, untouched (same retriever, same configuration object).
- "lexical": the profile's retrieval configuration with `use_subword` switched on, plus plain
  acronym expansion of the query (no model call): Q1's `lexicon_plain` variant
  (eval_internal/robustness/run_retrieval.py, reports/agents/Q1_robustesse.md). The full
  hand-written lexicon (`use_medical_lexicon`) stays off in every demo variant: 13 of its entries
  add terms beyond the acronym's long form (7 add molecule names), which would steer the search.
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
LEXICAL_FLAGS = {"use_subword": True, "use_medical_lexicon": False}

# Rule (Q1 report, section 4): an entry of `MEDICAL_ACRONYMS` is plain when its expansion is only
# the full form of the acronym. These 13 entries add more (molecule names: C1G, C2G, C3G, AOD, AVK,
# AAP, HBPM; topic words: ATB, IIA, BLSE, DFG, ClCr, IMC) and are not expanded at all. Same list as
# eval_internal/robustness/run_retrieval.py::LEXICON_BOOST_ENTRIES, the variant Q1 measured.
# Brand-name and drug-class synonyms of the lexicon are left out.
LEXICON_BOOST_ENTRIES = frozenset(
    {"ATB", "IIA", "C1G", "C2G", "C3G", "BLSE", "AOD", "AVK", "AAP", "HBPM", "DFG", "ClCr", "IMC"}
)


def plain_entries() -> list[dict[str, Any]]:
    from rag_sfar.retrieval.medical_lexicon import MEDICAL_ACRONYMS

    return [{"abbr": a, "long_form": lf, "variants": [lf]}
            for a, lf in MEDICAL_ACRONYMS.items() if a not in LEXICON_BOOST_ENTRIES]


class PlainExpansionRetriever:
    """Expands plain acronyms of the search query (abbreviation -> long form appended in
    parentheses, as Q1 measured) before the base retriever; the question shown to the generator
    is unchanged. `added` collects the expansions of every search made for one question."""

    def __init__(self, base: Any, expander: Any) -> None:
        self.base = base
        self.expander = expander
        self.added: dict[str, str] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)

    def retrieve(self, query: str, *args: Any, **kw: Any):
        expanded, added = self.expander.expand(query)
        self.added.update(added)
        return self.base.retrieve(expanded, *args, **kw)
LABELS = {
    "none": "aucune (configuration gelée évaluée)",
    "lexical": "lexicale (n-grammes de caractères + développement des sigles)",
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
        self._expander = None

    def retrieval_config(self, choice: str):
        if choice in ("lexical", "both"):
            if self._lexical_config is None:
                self._lexical_config = dataclasses.replace(
                    self.base_config, name=f"{self.base_config.name}+subword+plain_acronyms", **LEXICAL_FLAGS
                )
            return self._lexical_config
        return self.base_config

    def expander(self):
        if self._expander is None:
            from rag_sfar.retrieval.corpus_glossary import GlossaryExpander

            self._expander = GlossaryExpander(plain_entries(), long_to_abbr=False)
        return self._expander

    def retriever(self, choice: str, llm: Any):
        base = self.base_retriever
        if choice in ("lexical", "both"):
            base = PlainExpansionRetriever(base, self.expander())
        if needs_llm(choice):
            return wrap_retriever(base, llm=llm, variant="normalize", use="add")
        return base


def expansions(retriever: Any) -> dict[str, str] | None:
    """Acronym expansions added to the search query (None when the lexical variant is off)."""
    r = retriever.base if isinstance(retriever, QueryRewriteRetriever) else retriever
    return dict(r.added) if isinstance(r, PlainExpansionRetriever) else None


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
