"""Generation-stage settings: what the LLM is shown (context budget, format, order) and how it
is called (thinking, sampling, output length).

Kept separate from `RetrievalConfig` (owned by the retrieval stage): the retrieval decides which
evidence is available, the generation settings decide how much of it a given model class can
read and in which form. `GenerationConfig()` with no argument reproduces the historical behaviour
(6 chunks / 6 500 characters selected by `select_generation_context`, legacy formatting), so
existing callers are unchanged.

Presets (`GENERATION_PRESETS`) name one configuration per model class; each choice in them is
documented in reports/agents/B3_generation.md with its dev measurement.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Literal

ContextSelection = Literal["legacy", "budget"]
ContextFormat = Literal["legacy", "structured"]
ContextOrder = Literal["rank", "u_shape", "document"]
TableRendering = Literal["as_is", "drop_covered_cards", "rows_as_cards"]
SourceHeader = Literal["legacy", "rich"]
CoverageGate = Literal["off", "note", "refuse"]


@dataclass(frozen=True)
class GenerationConfig:
    name: str = "legacy"

    # ------------------------------------------------------------------ context
    # "legacy": `select_generation_context` (noise filter + per-mode budget of 5-7 chunks /
    # 5 200-6 500 chars) when the retrieval config has `use_context_pruning`, else every chunk.
    # "budget": every retrieved chunk in rank order until `max_context_chunks` /
    # `max_context_chars` is reached, independent of the retrieval flags.
    selection: ContextSelection = "legacy"
    max_context_chunks: int = 6
    max_context_chars: int = 6500
    # "legacy": `retrieval.pipeline.format_context_for_llm` (unchanged historical format).
    # "structured": generation/context.py (numbering in display order, options below).
    context_format: ContextFormat = "legacy"
    # Merge chunks of one document that follow each other in the text into one passage.
    merge_adjacent: bool = False
    context_order: ContextOrder = "u_shape"
    table_rendering: TableRendering = "as_is"
    source_header: SourceHeader = "legacy"
    # Provence-style prose pruning of long chunks (legacy: follows `use_context_pruning`).
    prune_prose: bool | None = None
    # Note quoting the question's allergy statement (legacy: follows `use_context_pruning`).
    allergy_note: bool | None = None

    # ------------------------------------------------------------------ coverage gate
    # Retrieval coverage signal (`coverage_supported` from the retriever timings):
    # "off" ignore it; "note" tell the LLM the retrieval found no close passage; "refuse" return
    # the fixed abstention sentence without calling the LLM.
    coverage_gate: CoverageGate = "off"

    # ------------------------------------------------------------------ prompt / call
    # Population-dependency note (generation/context.py): when the question names no population
    # and the context holds both adult and paediatric tables, tell the model to answer per
    # population instead of choosing one.
    dependency_note: bool = False
    # State the question before the excerpts as well as after them.
    question_first: bool = False
    # Prompt mode used when the caller does not force one (None = caller decides).
    prompt_mode: str | None = None
    # None = chat-template default. False disables Qwen3.5+ "thinking" (mlx: template kwarg;
    # OpenAI-compatible / vLLM: chat_template_kwargs).
    enable_thinking: bool | None = None
    temperature: float = 0.0
    top_p: float = 0.0  # 0 = disabled
    top_k: int = 0  # 0 = disabled
    presence_penalty: float = 0.0
    max_tokens: int | None = None  # None = backend default / per-mode default
    # Deterministic answer check (generation/answer_check.py): "off", "flag" (warning only),
    # "regenerate" (one corrective pass when the check fails).
    answer_check: Literal["off", "flag", "regenerate"] = "off"

    def replace(self, **changes: Any) -> "GenerationConfig":
        return dataclasses.replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


LEGACY = GenerationConfig()

# One configuration per model class. "small" keeps the historical narrow context for 3-9B
# models; "wide" is for ~30B-class models (and the 9B stand-in) that can read the full
# retrieval output. Values are set from the dev measurements in B3_generation.md.
GENERATION_PRESETS: dict[str, GenerationConfig] = {
    "legacy": LEGACY,
    "small": GenerationConfig(
        name="small",
        selection="legacy",
        max_context_chunks=6,
        max_context_chars=6500,
        enable_thinking=False,
    ),
    "wide": GenerationConfig(
        name="wide",
        selection="budget",
        max_context_chunks=40,
        max_context_chars=30000,
        context_format="structured",
        merge_adjacent=True,
        context_order="rank",
        table_rendering="as_is",
        source_header="rich",
        prune_prose=False,
        allergy_note=False,
        enable_thinking=False,
    ),
}


def parse_generation_overrides(base: GenerationConfig, spec: str) -> GenerationConfig:
    """Apply "field=value+field=value" overrides (same syntax as the retrieval --ablate)."""
    if not spec:
        return base
    changes: dict[str, Any] = {}
    fields = {f.name: f for f in dataclasses.fields(GenerationConfig)}
    for part in [p.strip() for p in spec.split("+") if p.strip()]:
        key, _, raw = part.partition("=")
        if key not in fields:
            raise ValueError(f"Unknown GenerationConfig field {key!r}")
        cur = getattr(base, key)
        if raw.lower() in ("none", "null"):
            changes[key] = None
        elif isinstance(cur, bool) or key in ("prune_prose", "allergy_note", "enable_thinking"):
            changes[key] = raw.lower() in ("1", "true", "yes")
        elif isinstance(cur, int) and not isinstance(cur, bool) or key in ("max_tokens", "top_k"):
            changes[key] = int(raw)
        elif isinstance(cur, float):
            changes[key] = float(raw)
        else:
            changes[key] = raw
    return dataclasses.replace(base, **changes)


def resolve_generation_config(preset: str = "legacy", overrides: str = "") -> GenerationConfig:
    if preset not in GENERATION_PRESETS:
        raise ValueError(f"Unknown generation preset {preset!r}; known: {sorted(GENERATION_PRESETS)}")
    cfg = parse_generation_overrides(GENERATION_PRESETS[preset], overrides)
    if overrides:
        cfg = cfg.replace(name=f"{cfg.name}+{overrides}")
    return cfg
