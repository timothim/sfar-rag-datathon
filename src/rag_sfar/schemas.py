"""Core typed data models for RAG-SFAR."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DocRole = Literal[
    "recommandation",
    "texte_court",
    "argumentaire",
    "algorithme",
    "aide_cognitive",
    "tableaux_synthese",
    "annexe",
    "traduction_en",
    "abrogee",
]

ChunkType = Literal[
    "prose",
    "table_markdown",
    "table_row_card",
    "recommendation_box",
    "callout_allergy",
    "callout_footnote",
    "references",
    # One graded recommendation (statement + strength), extracted by reco_extractor; added
    # next to the chunks that already contain it (see ingestion/chunker.py).
    "recommendation_unit",
]

# Structural population labels of a chunk (ingestion/population.py).
PopulationLabel = Literal["adulte", "pediatrie", "neonatal", "obstetrique"]

PopulationScope = Literal["adulte", "pediatrie", "mixte", "non_specifie"]
SettingScope = Literal["programme", "urgence", "reanimation", "mixte", "non_specifie"]


class DocumentMetadata(BaseModel):
    """Enriched metadata for one SFAR recommendation document."""

    doc_id: str
    title: str
    filename: str
    md_path: str
    sha256: str = ""
    landing_url: str = ""
    download_url: str = ""

    # Raw metadata from discovery.json
    doc_type: str = "RFE"  # RFE, RPP, Preconisation, HAS
    raw_year: int | None = None
    raw_discipline: str | None = None
    raw_subdomain: str | None = None
    source_tabs: list[str] = Field(default_factory=list)

    # Enriched / normalized metadata
    effective_year: int | None = None
    version_label: str | None = None
    disciplines: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    subdomain_was_imputed: bool = False
    year_was_imputed: bool = False
    language: Literal["fr", "en", "bilingual"] = "fr"
    doc_role: DocRole = "recommandation"
    reco_family_id: str = ""

    # Longitudinal / Temporal supersession metadata
    topic_lineage: str | None = None
    is_active: bool = True
    is_latest_edition: bool = True
    superseded_by: str | None = None
    superseded_by_year: int | None = None
    # Why this edition is considered superseded (rule and evidence), for review.
    supersession_evidence: str = ""

    # Clinical scope metadata
    population_scope: PopulationScope = "non_specifie"
    setting_scope: SettingScope = "non_specifie"

    # Corpus stats
    num_pages: int | None = None
    char_count: int = 0
    table_count: int = 0
    reference_char_ratio: float = 0.0


class Chunk(BaseModel):
    """A single indexed passage or structured table unit."""

    chunk_id: str
    doc_id: str
    chunk_index: int
    chunk_type: ChunkType = "prose"
    section_path: str = ""
    section_id: str = ""
    text: str  # Raw clean text for display & LLM
    indexed_text: str  # Contextualized text (with header breadcrumb) for BM25/Dense

    # Clinical annotations extracted from content
    grade_levels: list[str] = Field(default_factory=list)
    recommendation_ids: list[str] = Field(default_factory=list)
    population_hint: PopulationScope = "non_specifie"
    is_reference_section: bool = False
    has_allergy_info: bool = False
    has_dosage_info: bool = False

    # Graph / hierarchy links for small-to-big context expansion
    parent_section_id: str = ""
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None
    linked_callout_ids: list[str] = Field(default_factory=list)

    # Denormalized document metadata for ultra-fast filtering & display
    doc_title: str = ""
    doc_type: str = "RFE"
    effective_year: int | None = None
    version_label: str | None = None
    domains: list[str] = Field(default_factory=list)
    language: str = "fr"
    doc_role: str = "recommandation"
    reco_family_id: str = ""
    topic_lineage: str | None = None
    is_active: bool = True
    is_latest_edition: bool = True
    superseded_by: str | None = None
    setting_scope: str = "non_specifie"
    landing_url: str = ""
    filename: str = ""

    # Structural population labels (adulte / pediatrie / neonatal / obstetrique), and where they
    # come from: "table" (scope note, banner, title of the table), "section" (heading path),
    # "document" (title) or "" (unknown). Empty list = population not stated by the structure.
    populations: list[str] = Field(default_factory=list)
    population_source: str = ""
    # Identifier shared by all chunks of one table (Markdown chunks and row cards), "" otherwise.
    table_id: str = ""
    # recommendation_unit chunks: chunk that contains the statement in the document flow,
    # strength (normalized, e.g. grade_1_plus / expert_opinion / unknown), raw rating, agreement
    # and label (R1.2...). Empty for other chunk types.
    source_chunk_id: str | None = None
    reco_strength: str = ""
    reco_strength_raw: str = ""
    reco_agreement: str = ""
    reco_label: str = ""


class QueryAnalysis(BaseModel):
    """Structured analysis of a user clinical query."""

    original_query: str
    expanded_query: str
    acronyms_expanded: dict[str, str] = Field(default_factory=dict)
    temporal_mode: Literal["latest_only", "all_versions", "specific_year"] = "latest_only"
    requested_years: list[int] = Field(default_factory=list)
    inferred_domains: list[str] = Field(default_factory=list)
    population: PopulationScope = "non_specifie"
    setting: SettingScope = "non_specifie"
    modifiers: list[str] = Field(default_factory=list)  # allergy, obesity, renal, dosage, diff, grade
    wants_references: bool = False


class RetrievedChunk(BaseModel):
    """A retrieved chunk with full score provenance for transparency & ablation."""

    chunk: Chunk
    final_score: float
    bm25_score: float = 0.0
    bm25_rank: int | None = None
    dense_score: float = 0.0
    dense_rank: int | None = None
    rrf_score: float = 0.0
    metadata_boost: float = 0.0
    rerank_score: float | None = None
    is_expanded_context: bool = False
    expansion_reason: str | None = None


class Citation(BaseModel):
    """Structured clinical source citation returned to the user."""

    citation_id: str  # e.g. "S1"
    chunk_id: str
    doc_id: str
    doc_title: str
    effective_year: int | None
    version_label: str | None
    doc_type: str
    section_path: str
    grade_levels: list[str] = Field(default_factory=list)
    is_latest_edition: bool = True
    superseded_by: str | None = None
    landing_url: str = ""
    excerpt: str = ""
    chunk_type: str = "prose"
    score: float = 0.0


class VerificationReport(BaseModel):
    """Post-generation grounding & safety check."""

    citations_found: list[str] = Field(default_factory=list)
    invalid_citations: list[str] = Field(default_factory=list)
    mentioned_molecules: list[str] = Field(default_factory=list)
    ungrounded_molecules: list[str] = Field(default_factory=list)
    obsolete_sources_used: list[str] = Field(default_factory=list)
    is_abstention: bool = False
    grounding_score: float = 1.0
    warnings: list[str] = Field(default_factory=list)
    # True when "(SFAR <année> [S1])" was appended by code, not written by the model.
    provenance_added_by_code: bool = False


class RagResponse(BaseModel):
    """Complete RAG pipeline output with full traceability."""

    query: str
    answer: str
    mode: str = "clinical_detailed"
    query_analysis: QueryAnalysis
    citations: list[Citation] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    verification: VerificationReport = Field(default_factory=VerificationReport)
    latency_ms: dict[str, float] = Field(default_factory=dict)
    token_usage: dict[str, int] = Field(default_factory=dict)
    model_used: str = ""
    config_name: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)
