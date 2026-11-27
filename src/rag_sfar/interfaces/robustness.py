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

Decomposition (multi_query "decompose", default from RAG_SFAR_DECOMPOSE, off when unset) can be
added to any choice; `compose` builds the per-question retriever for (choice, decomposition), the
same object in the HTTP API and in the replay tool (eval_internal/gen_replay.py capture).

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


# ---------------------------------------------------------------- composition with decomposition

ENV_DECOMPOSE = "RAG_SFAR_DECOMPOSE"


def decompose_default() -> bool:
    """Server default for question decomposition (RAG_SFAR_DECOMPOSE=1; off when unset)."""
    v = os.environ.get(ENV_DECOMPOSE, "0").strip().lower() or "0"
    if v not in ("0", "1", "false", "true", "off", "on", "no", "yes"):
        raise ValueError(f"{ENV_DECOMPOSE}={v!r}; use 0 or 1")
    return v in ("1", "true", "on", "yes")


class TraceLog:
    """Transparent proxy that keeps the `last_trace` of the wrapped retriever after every call
    (the normalisation wrapper is called once for the question and once per sub-question when
    decomposition fires; the first trace is the question's)."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.traces: list[Any] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def retrieve(self, *args: Any, **kw: Any):
        out = self.inner.retrieve(*args, **kw)
        tr = getattr(self.inner, "last_trace", None)
        if tr is not None:
            self.traces.append(tr)
        return out


@dataclasses.dataclass
class Composed:
    """One question's retriever for a (robustness choice, decomposition) pair, with what each
    language-model step did. Order: decomposition (outermost, reads the raw question) ->
    normalisation (add mode) -> plain acronym expansion -> frozen retriever."""

    retriever: Any
    config: Any
    requested: str
    used: str
    decompose_requested: bool
    decompose_used: bool
    unavailable: str | None = None
    rewrite_log: TraceLog | None = None
    lexical: PlainExpansionRetriever | None = None
    decomposer: Any = None

    @property
    def frozen(self) -> bool:
        return self.used == "none" and not self.decompose_used

    def normalization(self) -> dict[str, Any] | None:
        """Same fields as `rewrite_trace` (question's own call) plus the number of calls."""
        if self.rewrite_log is None or not self.rewrite_log.traces:
            return None
        tr = self.rewrite_log.traces[0]
        return {
            "used": tr.used,
            "normalized_question": tr.rewrite if tr.used else None,
            "unchanged": (not tr.used) and not tr.format_error and not tr.guard_rejected,
            "error": tr.format_error or None,
            "n_added": tr.n_added,
            "llm_ms": tr.llm_ms,
            "n_calls": len(self.rewrite_log.traces),
        }

    def decomposition(self) -> dict[str, Any] | None:
        if self.decomposer is None or self.decomposer.last_trace is None:
            return None
        tr = self.decomposer.last_trace
        return {"fired": tr.fired, "sub_questions": list(tr.extra_queries), "error": tr.format_error or None,
                "raw_answer": tr.raw_answer, "llm_ms": tr.llm_ms}

    def metadata(self) -> dict[str, Any]:
        """What the API responses and the replay reports record about the variant."""
        return {
            "requested": self.requested, "used": self.used, "label": LABELS[self.used],
            "retrieval_config": self.config.name, "unavailable": self.unavailable,
            "decompose_requested": self.decompose_requested, "decompose": self.decompose_used,
            "normalization": self.normalization(), "decomposition": self.decomposition(),
            "expansions": dict(self.lexical.added) if self.lexical is not None else None,
        }


def compose(variants: RobustnessVariants, choice: str, decompose: bool, llm: Any) -> Composed:
    """Retriever and retrieval configuration for one question. `choice="none"` without
    decomposition returns the frozen retriever and configuration objects themselves. The steps
    that need the language model fall back when `llm` is None (normalize -> none, both ->
    lexical, decomposition off), and `unavailable` says so."""
    if choice not in CHOICES:
        raise ValueError(f"robustness must be one of {CHOICES}, got {choice!r}")
    used, unavailable, dec = choice, None, bool(decompose)
    if llm is None and (needs_llm(choice) or dec):
        if needs_llm(choice):
            used = "lexical" if choice == "both" else "none"
        dec = False
        unavailable = "Étapes avec modèle indisponibles : aucun générateur configuré."
    cfg = variants.retrieval_config(used)
    if used == "none" and not dec:
        return Composed(variants.base_retriever, cfg, choice, used, bool(decompose), dec, unavailable)
    base = variants.base_retriever
    lexical = None
    if used in ("lexical", "both"):
        lexical = base = PlainExpansionRetriever(base, variants.expander())
    log = None
    if needs_llm(used):
        log = base = TraceLog(wrap_retriever(base, llm=llm, variant="normalize", use="add"))
    decomposer = None
    if dec:
        from rag_sfar.retrieval import multi_query

        decomposer = base = multi_query.wrap_retriever(base, llm=llm, mode="decompose")
    return Composed(base, cfg, choice, used, bool(decompose), dec, unavailable, log, lexical, decomposer)
