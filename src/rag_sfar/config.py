"""Configuration models for RAG-SFAR (environment settings + ablation configs)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_prefix="RAG_SFAR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    corpus_dir: Path = Path("data/sfar_recommendations/output")
    benchmark_path: Path = Path(
        "data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json"
    )
    index_dir: Path = Path("index/sota_default")

    # LLM settings (OpenAI-compatible: Ollama, vLLM, Mistral, OpenAI)
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5:14b-instruct"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 1024
    llm_timeout_seconds: float = 120.0

    # Embedding settings
    embedding_provider: Literal["sentence_transformer", "openai_compatible", "tfidf_svd"] = (
        "sentence_transformer"
    )
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_batch_size: int = 32

    # Reranker settings
    reranker_provider: Literal["cross_encoder", "none"] = "cross_encoder"
    reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

    # Vector backend
    vector_backend: Literal["local", "pgvector"] = "local"
    pgvector_dsn: str = "postgresql://postgres:postgres@localhost:5432/sfar_rag"

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # HTTP API only: append "(SFAR <année> [S1])" to benchmark-mode answers that lack a year
    # (display; flagged in sfar_verification.provenance_added_by_code). The engine default,
    # used by evaluations, is off.
    api_attach_provenance: bool = True


@dataclass
class RetrievalConfig:
    """Explicit configuration for reproducible RAG ablation experiments."""

    name: str = "sota_full"
    chunking_strategy: Literal["naive_fixed", "hierarchical_markdown", "table_aware_sota"] = (
        "table_aware_sota"
    )
    # Retrieval channels
    use_bm25: bool = True
    use_subword: bool = True
    use_dense: bool = True
    bm25_weight: float = 1.0
    subword_weight: float = 0.65
    dense_weight: float = 1.0
    rrf_k: int = 60

    # Frontier 2026 Fusion, CRAG & Context Optimization
    use_dbsf_fusion: bool = True  # Distribution-Based Score Fusion blended with RRF
    dbsf_blend: float = 0.35
    use_crag_multihop: bool = True  # Multi-facet query decomposition + corrective rescue
    use_u_shape_ordering: bool = True  # Lost-in-the-Middle primacy/recency reordering
    use_context_pruning: bool = True  # Provence-inspired prose pruning & noise-filtered precision context

    # Query processing
    use_medical_lexicon: bool = True
    use_query_router: bool = True

    # Safety & metadata controls
    exclude_references: bool = True
    prefer_french: bool = True
    latest_edition_only: bool = True
    exclude_abrogated: bool = True
    use_soft_metadata_boost: bool = True
    use_hard_subdomain_filter: bool = False  # Intentionally False by default (see audit!)

    # Reranking & deduplication
    use_reranker: bool = True
    initial_candidates: int = 45
    rerank_top_k: int = 24
    final_top_k: int = 8
    dedup_by_content: bool = True
    max_chunks_per_doc: int = 7

    # Context expansion
    expand_neighbors: bool = True
    expand_section_callouts: bool = True
    max_context_chars: int = 16000
    # Post-ranking context windows (applied after the final_top_k cut, own character budget):
    # +-context_window neighbouring chunks of the same document around each of the first
    # context_window_top results, and the parent table of retrieved table rows.
    context_window: int = 0
    context_window_top: int = 8
    expand_table_parent: bool = False
    context_char_budget: int = 30000
    # Notes of a retrieved table (B1, 2026-11-27): the footnote / scope-note callouts linked to a
    # retrieved table chunk at ingestion (`linked_callout_ids` of type callout_footnote) and the
    # block of footnotes printed right after the table (paragraphs starting with a call mark).
    attach_table_notes: bool = False
    table_notes_max_chars: int = 1200
    # Window neighbours only for table chunks (prose neighbours are usually off-topic).
    context_window_tables_only: bool = False
    # Order of the returned context: "rank" (anchor then its expansions) or "document"
    # (results grouped by document, in reading order inside each document).
    context_order: Literal["rank", "document"] = "rank"

    # Population balance (B1): when the query does not exclude a population, guarantee
    # `population_quota` passages of each population (adult / paediatric, from chunk metadata)
    # among the documents of the top results. 0 = off.
    population_quota: int = 0
    population_tables_only: bool = True  # quota counted and filled with table chunks only
    population_counterpart: bool = False  # add the act label of the other population's row
    # Multi-query retrieval for MCQs (B1): one retrieval per option (stem + option), each
    # option keeps `mcq_option_quota` passages in the final context. 0 = off.
    mcq_option_quota: int = 0
    mcq_stem_only: bool = False  # main query = stem without the option lines
    mcq_option_with_stem: bool = True  # option sub-query = stem + option (False: option alone)
    # Negated background terms (B1): weight of the tokens of a negated span ("sans allergie
    # aux X", "ni BPCO") in the lexical query (1.0 = unchanged, 0.0 = removed from BM25 only).
    negated_term_weight: float = 1.0
    # Same for the cross-encoder / dense query: drop negated spans attached to the patient.
    negation_strip_semantic: bool = False

    # Coverage signal (B1): the corpus is deemed to cover the query when the best
    # cross-encoder score reaches this threshold (exposed, never used to filter results).
    coverage_threshold: float = 0.2

    # Soft boost weights (applied additively/multiplicatively to RRF score)
    domain_boost: float = 0.18
    population_boost: float = 0.25
    population_mismatch_penalty: float = 0.35
    setting_boost: float = 0.20
    role_boost_map: dict[str, float] = field(
        default_factory=lambda: {
            "recommandation": 0.12,
            "texte_court": 0.12,
            "tableaux_synthese": 0.15,
            "algorithme": 0.10,
            "aide_cognitive": 0.08,
            "argumentaire": -0.04,
            "annexe": -0.05,
        }
    )
    table_card_boost: float = 0.10
