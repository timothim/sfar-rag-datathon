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
