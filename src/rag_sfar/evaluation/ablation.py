"""Progressive RAG Ablation Suite (C0 Naive Baseline -> C7 Full SOTA).

Compares chunking, bibliography filtering, table/row-card structuring, medical acronym
expansion, dense embeddings, hybrid RRF, temporal/metadata routing, neural cross-encoder
reranking, and section-anchored allergy/footnote expansion on identical benchmarks.
"""

from __future__ import annotations

from typing import Any

from rag_sfar.config import RetrievalConfig
from rag_sfar.evaluation.benchmarks import EvalQuestion
from rag_sfar.evaluation.retrieval_metrics import evaluate_retrieval_dataset
from rag_sfar.retrieval.pipeline import SfarRagRetriever


def build_standard_ablation_configs() -> list[RetrievalConfig]:
    """Return the canonical 9-step progressive ablation ladder (C0 Naive -> C8 Frontier 2026)."""
    return [
        RetrievalConfig(
            name="C0_naive_fixed_bm25",
            chunking_strategy="naive_fixed",
            use_bm25=True,
            use_subword=False,
            use_dense=False,
            use_dbsf_fusion=False,
            use_crag_multihop=False,
            use_medical_lexicon=False,
            use_query_router=False,
            exclude_references=False,
            prefer_french=False,
            latest_edition_only=False,
            exclude_abrogated=False,
            use_soft_metadata_boost=False,
            use_reranker=False,
            expand_neighbors=False,
            expand_section_callouts=False,
            use_u_shape_ordering=False,
            use_context_pruning=False,
            final_top_k=8,
        ),
        RetrievalConfig(
            name="C1_naive_fixed_dense",
            chunking_strategy="naive_fixed",
            use_bm25=False,
            use_subword=False,
            use_dense=True,
            use_dbsf_fusion=False,
            use_crag_multihop=False,
            use_medical_lexicon=False,
            use_query_router=False,
            exclude_references=False,
            prefer_french=False,
            latest_edition_only=False,
            exclude_abrogated=False,
            use_soft_metadata_boost=False,
            use_reranker=False,
            expand_neighbors=False,
            expand_section_callouts=False,
            use_u_shape_ordering=False,
            use_context_pruning=False,
            final_top_k=8,
        ),
        RetrievalConfig(
            name="C2_hierarchical_bm25_no_refs",
            chunking_strategy="hierarchical_markdown",
            use_bm25=True,
            use_subword=False,
            use_dense=False,
            use_dbsf_fusion=False,
            use_crag_multihop=False,
            use_medical_lexicon=False,
            use_query_router=False,
            exclude_references=True,
            prefer_french=True,
            latest_edition_only=False,
            exclude_abrogated=True,
            use_soft_metadata_boost=False,
            use_reranker=False,
            expand_neighbors=False,
            expand_section_callouts=False,
            use_u_shape_ordering=False,
            use_context_pruning=False,
            final_top_k=8,
        ),
        RetrievalConfig(
            name="C3_table_sota_bm25_lexicon",
            chunking_strategy="table_aware_sota",
            use_bm25=True,
            use_subword=False,
            use_dense=False,
            use_dbsf_fusion=False,
            use_crag_multihop=False,
            use_medical_lexicon=True,
            use_query_router=False,
            exclude_references=True,
            prefer_french=True,
            latest_edition_only=False,
            exclude_abrogated=True,
            use_soft_metadata_boost=False,
            use_reranker=False,
            expand_neighbors=False,
            expand_section_callouts=False,
            use_u_shape_ordering=False,
            use_context_pruning=False,
            final_top_k=8,
        ),
        RetrievalConfig(
            name="C4_table_sota_dense",
            chunking_strategy="table_aware_sota",
            use_bm25=False,
            use_subword=False,
            use_dense=True,
            use_dbsf_fusion=False,
            use_crag_multihop=False,
            use_medical_lexicon=True,
            use_query_router=False,
            exclude_references=True,
            prefer_french=True,
            latest_edition_only=False,
            exclude_abrogated=True,
            use_soft_metadata_boost=False,
            use_reranker=False,
            expand_neighbors=False,
            expand_section_callouts=False,
            use_u_shape_ordering=False,
            use_context_pruning=False,
            final_top_k=8,
        ),
        RetrievalConfig(
            name="C5_table_sota_hybrid_rrf",
            chunking_strategy="table_aware_sota",
            use_bm25=True,
            use_subword=False,
            use_dense=True,
            use_dbsf_fusion=False,
            use_crag_multihop=False,
            use_medical_lexicon=True,
            use_query_router=False,
            exclude_references=True,
            prefer_french=True,
            latest_edition_only=False,
            exclude_abrogated=True,
            use_soft_metadata_boost=False,
            use_reranker=False,
            expand_neighbors=False,
            expand_section_callouts=False,
            use_u_shape_ordering=False,
            use_context_pruning=False,
            final_top_k=8,
        ),
        RetrievalConfig(
            name="C6_hybrid_temporal_metadata",
            chunking_strategy="table_aware_sota",
            use_bm25=True,
            use_subword=False,
            use_dense=True,
            use_dbsf_fusion=False,
            use_crag_multihop=False,
            use_medical_lexicon=True,
            use_query_router=True,
            exclude_references=True,
            prefer_french=True,
            latest_edition_only=True,
            exclude_abrogated=True,
            use_soft_metadata_boost=True,
            use_reranker=False,
            expand_neighbors=False,
            expand_section_callouts=False,
            use_u_shape_ordering=False,
            use_context_pruning=False,
            final_top_k=8,
        ),
        RetrievalConfig(
            name="C7_sota_rerank_callouts",
            chunking_strategy="table_aware_sota",
            use_bm25=True,
            use_subword=False,
            use_dense=True,
            use_dbsf_fusion=False,
            use_crag_multihop=False,
            use_medical_lexicon=True,
            use_query_router=True,
            exclude_references=True,
            prefer_french=True,
            latest_edition_only=True,
            exclude_abrogated=True,
            use_soft_metadata_boost=True,
            use_reranker=True,
            expand_neighbors=True,
            expand_section_callouts=True,
            use_u_shape_ordering=False,
            use_context_pruning=False,
            final_top_k=8,
        ),
        RetrievalConfig(
            name="C8_frontier_2026_tri_dbsf_crag",
            chunking_strategy="table_aware_sota",
            use_bm25=True,
            use_subword=True,
            use_dense=True,
            use_dbsf_fusion=True,
            use_crag_multihop=True,
            use_medical_lexicon=True,
            use_query_router=True,
            exclude_references=True,
            prefer_french=True,
            latest_edition_only=True,
            exclude_abrogated=True,
            use_soft_metadata_boost=True,
            use_reranker=True,
            expand_neighbors=True,
            expand_section_callouts=True,
            use_u_shape_ordering=True,
            use_context_pruning=True,
            final_top_k=8,
        ),
        # C9: simplification of C8 after one-at-a-time ablation on the internal dev set
        # (2026-11-26): only dense retrieval and the cross-encoder showed a measurable gain.
        # CRAG, char n-grams, DBSF, metadata boost, lexicon, neighbour/callout expansion removed.
        # The query router is kept for edition-comparison detection (functional, too rare to measure).
        RetrievalConfig(
            name="C9_simple_hybrid_rerank",
            chunking_strategy="table_aware_sota",
            use_bm25=True,
            use_subword=False,
            use_dense=True,
            use_dbsf_fusion=False,
            use_crag_multihop=False,
            use_medical_lexicon=False,
            use_query_router=True,
            exclude_references=True,
            prefer_french=True,
            latest_edition_only=True,
            exclude_abrogated=True,
            use_soft_metadata_boost=False,
            use_reranker=True,
            expand_neighbors=False,
            expand_section_callouts=False,
            use_u_shape_ordering=True,
            use_context_pruning=True,
            final_top_k=8,
        ),
        # C10 (B1, 2026-11-27): C9 + context built for a ~30B generator, each element kept after a
        # one-at-a-time ablation on the three dev sets (reports/agents/B1_retrieval.md):
        # 16 ranked results with +-1 neighbour and the parent table of table rows (windows),
        # notes of retrieved tables (scope notes, footnotes), no per-document cap below the
        # final budget (a single guideline usually holds all the evidence), one adult and one
        # paediatric table passage when the query does not exclude that population
        # (counterpart search through the act label of the other population's row), and for
        # MCQs two passages per option (stem + option sub-query).
        # Tested and not kept: negation handling (no gain on top of this configuration),
        # larger candidate pools, bge-reranker-v2-m3, edition filter off, other budgets (see the report).
        RetrievalConfig(
            name="C10_context_population",
            chunking_strategy="table_aware_sota",
            use_bm25=True,
            use_subword=False,
            use_dense=True,
            use_dbsf_fusion=False,
            use_crag_multihop=False,
            use_medical_lexicon=False,
            use_query_router=True,
            exclude_references=True,
            prefer_french=True,
            latest_edition_only=True,
            exclude_abrogated=True,
            use_soft_metadata_boost=False,
            use_reranker=True,
            expand_neighbors=False,
            expand_section_callouts=False,
            use_u_shape_ordering=True,
            use_context_pruning=True,
            final_top_k=16,
            max_chunks_per_doc=16,
            context_window=1,
            expand_table_parent=True,
            attach_table_notes=True,
            population_quota=1,
            population_counterpart=True,
            mcq_option_quota=2,
        ),
    ]


def run_ablation_suite(
    retrievers_by_strategy: dict[str, SfarRagRetriever],
    datasets: dict[str, list[EvalQuestion]],
    configs: list[RetrievalConfig] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Execute ablation configs across all provided datasets."""
    cfg_list = configs or build_standard_ablation_configs()
    results: dict[str, list[dict[str, Any]]] = {ds_name: [] for ds_name in datasets}

    for cfg in cfg_list:
        retriever = retrievers_by_strategy.get(cfg.chunking_strategy)
        if retriever is None:
            continue
        # Skip dense-only config cleanly if store has no dense embeddings
        if cfg.use_dense and not cfg.use_bm25 and retriever.store.embeddings is None:
            continue
        for ds_name, qs in datasets.items():
            print(f"[ablation] Running {cfg.name} on {ds_name} ({len(qs)} questions)...", flush=True)
            metrics = evaluate_retrieval_dataset(retriever=retriever, questions=qs, config=cfg)
            results[ds_name].append(metrics)

    return results


def format_ablation_markdown(results: dict[str, list[dict[str, Any]]]) -> str:
    """Render ablation results as a crisp Markdown report for restitution slides."""
    lines: list[str] = ["# RAG-SFAR — Résultats d'Ablation Comparative\n"]
    for ds_name, rows in results.items():
        lines.append(f"## Benchmark : `{ds_name}`\n")
        lines.append(
            "| Config | Strategy | Edition Hit@8 | Obsolète Intrusion | Evidence Recall | Allergie Recall | MRR | Latence (ms) | ~Tokens |"
        )
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in rows:
            ev = f"{r['evidence_recall']*100:.1f}%" if r["evidence_recall"] is not None else "—"
            al = (
                f"{r['allergy_evidence_recall']*100:.1f}%"
                if r["allergy_evidence_recall"] is not None
                else "—"
            )
            lines.append(
                f"| `{r['config_name']}` | {r['chunking_strategy']} "
                f"| **{r['current_edition_hit_rate']*100:.1f}%** "
                f"| {r['obsolete_intrusion_rate']*100:.1f}% "
                f"| **{ev}** | **{al}** "
                f"| {r['mrr_current_edition']:.3f} "
                f"| {r['avg_latency_ms']:.1f} "
                f"| {int(r['est_context_tokens'])} |"
            )
        lines.append("")
    return "\n".join(lines)
