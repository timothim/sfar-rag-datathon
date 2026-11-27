"""Named serving profiles: the single definition of what the deployed system runs.

The production profile is what was evaluated (reports/agents/B3_generation.md): retrieval
`C10_context_notes` (frozen, tag retrieval-freeze-20261127) on `index/tas_v6`, generation preset
`wide` (structured context, answer check as a warning, no molecule-repair call, no code-added
provenance), `clinical_concise` for open questions, multiple-choice questions routed by the engine
to `clinical_mcq`. The HTTP API, both MCP servers and the replay tool (eval_internal/gen_replay.py)
build their retrieval and generation from this object, so the evaluated prompt is the served one
(tests/test_generation_b3.py::test_api_prompt_identical_to_replay_prompt).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from rag_sfar.config import RetrievalConfig
from rag_sfar.generation.settings import GENERATION_PRESETS, GenerationConfig


@dataclass(frozen=True)
class ServingProfile:
    name: str
    retrieval_config_name: str
    index_dir: Path
    generation_preset: str
    open_mode: str
    attach_provenance: bool = False
    generation_overrides: dict = field(default_factory=dict)

    def retrieval_config(self) -> RetrievalConfig:
        # The definition lives with the retrieval ablation configurations (frozen by B1).
        from rag_sfar.evaluation.ablation import build_standard_ablation_configs

        for cfg in build_standard_ablation_configs():
            if cfg.name == self.retrieval_config_name:
                return cfg
        raise KeyError(f"retrieval configuration {self.retrieval_config_name!r} not found")

    def generation_config(self) -> GenerationConfig:
        g = GENERATION_PRESETS[self.generation_preset]
        if self.generation_overrides:
            g = g.replace(**self.generation_overrides)
        return g.replace(name=f"{self.name}:{self.generation_preset}")

    def resolve_index_dir(self, explicit: Path | str | None = None) -> Path:
        """Explicit argument > RAG_SFAR_INDEX_DIR environment variable > profile index."""
        if explicit:
            return Path(explicit)
        env = os.environ.get("RAG_SFAR_INDEX_DIR")
        return Path(env) if env else self.index_dir

    def replay_index_map(self) -> str:
        """--index-map value of the replay tool for this profile."""
        return f"{self.retrieval_config().chunking_strategy}={self.index_dir.name}"


PRODUCTION = ServingProfile(
    name="production",
    retrieval_config_name="C10_context_notes",
    index_dir=Path("index/tas_v6"),
    generation_preset="wide",
    open_mode="clinical_concise",
    attach_provenance=False,
    # Population-dependency note and coverage note: measured, not retained (B3 report §5-6).
    generation_overrides={"dependency_note": False, "coverage_gate": "off"},
)

PROFILES: dict[str, ServingProfile] = {"production": PRODUCTION}


def get_profile(name: str = "production") -> ServingProfile:
    if name not in PROFILES:
        raise KeyError(f"unknown profile {name!r}; known: {sorted(PROFILES)}")
    return PROFILES[name]


def build_engine(retriever, llm, profile: ServingProfile = PRODUCTION):
    """The engine as served: profile retrieval config, generation config and provenance policy."""
    from rag_sfar.generation.client import SfarRagEngine

    return SfarRagEngine(
        retriever=retriever,
        llm=llm,
        default_config=profile.retrieval_config(),
        attach_provenance=profile.attach_provenance,
        gen_config=profile.generation_config(),
    )
