"""End-to-end Frontier 2026 Retrieval & Context-Construction Pipeline for SFAR Guidelines.

Implements:
1. Clinical Query Analysis + French Anesthesia Acronym/Synonym Expansion
2. Hard Safety Filtering (active, latest edition unless diff/year requested, exclude refs, FR)
3. Tri-Channel Retrieval:
   - Sparse Word BM25+ (exact drug/dosage/rec-ID matching)
   - Sparse Subword Char 3–5 N-Gram TF-IDF (French medical morphology & OCR typo resilience)
   - Dense Multilingual Neural Cosine (`E5` / `BGE-M3`)
4. Hybrid RRF + DBSF (*Distribution-Based Score Fusion*, Bruch et al. & Qdrant 2025/2026)
   + Soft Metadata / Population / Setting / Role Priors
5. Neural Cross-Encoder Reranking + Population Consistency + Diversity Deduplication
6. Corrective RAG (CRAG) / Self-MedRAG Multi-Hop Facet Rescue Pass (coverage of systemic
   modifiers: resistant-bacteria carriage, obesity, renal impairment, explicit recommendation ID)
7. Small-to-Big Context Builder (Section Callouts + Neighbor Footnotes)
   + Provence-style Verbose Prose Pruning + Lost-in-the-Middle U-Shape Ordering

Output contract: `retrieve()` returns at most `final_top_k` chunks, sorted by decreasing
`final_score` (edition-comparison queries keep their latest/older interleaving instead).
Population priors only apply when the query states the population (adult or paediatric).
"""

from __future__ import annotations

import collections
import re
import time

import numpy as np

from rag_sfar.config import RetrievalConfig
from rag_sfar.retrieval.context_optimizer import prune_verbose_prose, reorder_lost_in_the_middle
from rag_sfar.retrieval.crag import (
    detect_clinical_facets,
    extract_composite_procedure_subqueries,
    extract_mcq_option_subqueries,
    find_missing_facets,
    strip_mcq_distractor_options,
)
from rag_sfar.retrieval.embedder import BaseEmbedder
from rag_sfar.retrieval.medical_lexicon import fold_accents
from rag_sfar.retrieval.reranker import BaseReranker
from rag_sfar.retrieval.router import analyze_query, strip_negated_background_for_retrieval
from rag_sfar.retrieval.vector_store import LocalVectorStore
from rag_sfar.schemas import Chunk, QueryAnalysis, RetrievedChunk

_NEONATAL_QUERY_RE = re.compile(
    r"\b(?:nouveau[- ]n[ée]e?s?|n[ée]onat\w*|pr[ée]matur[ée]e?s?|\d+\s*jours?\s*(?:de\s+vie)?\b)\b",
    re.I,
)
_OLDER_CHILD_QUERY_RE = re.compile(
    r"\b(?:adolescente?s?|(?:enfant|gar[çc]on|fille|fillette|adolescente?|patiente?)\s+de\s+(?:[1-9]|1[0-7])\s*ans?|\b(?:[1-9]|1[0-7])\s*ans?)\b",
    re.I,
)
_NEONATAL_ONLY_SECTION_RE = re.compile(r"\bn[ée]onatal(?:e|ogique|ogie)\b", re.I)
_FOOTNOTE_REF_RE = re.compile(r"(?:\*{1,3}(?!\w)|(?<!\w)#(?!\w)|†|‡)")


def _query_subpopulation(query: str) -> str | None:
    """Distinguish explicit neonatal (< 28d) vs older-child/adolescent queries."""
    if _NEONATAL_QUERY_RE.search(query):
        return "neonatal"
    if _OLDER_CHILD_QUERY_RE.search(query):
        return "child"
    return None


def _is_neonatal_only_chunk(chunk: Chunk) -> bool:
    """True when a chunk belongs specifically to a neonatal-only section (not general pediatrics)."""
    sec = (chunk.section_path or "").lower()
    if "néonatalog" in sec or "neonatalog" in sec:
        return True
    return bool(_NEONATAL_ONLY_SECTION_RE.search(sec) and "pédiatr" not in sec and "pediatr" not in sec)


def _dbsf_normalize(hits: list[tuple[int, float]]) -> dict[int, float]:
    """Distribution-Based Score Fusion normalization: maps raw scores via (mu +/- 3*sigma) -> [0, 1].

    Preserves score magnitude (so runaway exact clinical matches outrank close ties) while
    remaining immune to extreme scale differences between BM25, Char-Ngram, and Cosine.
    """
    if not hits:
        return {}
    vals = np.array([s for _, s in hits], dtype=np.float64)
    mu = float(np.mean(vals))
    sigma = float(np.std(vals))
    if sigma < 1e-8:
        return {idx: 1.0 for idx, _ in hits}
    lo = mu - 3.0 * sigma
    hi = mu + 3.0 * sigma
    span = max(1e-8, hi - lo)
    return {idx: float(max(0.0, min(1.0, (s - lo) / span))) for idx, s in hits}


class SfarRagRetriever:
    """Frontier 2026 multi-stage clinical retriever with tri-channel DBSF+RRF, CRAG multi-hop
    rescue, neural cross-encoder reranking, and section-anchored allergy/footnote expansion."""

    def __init__(
        self,
        store: LocalVectorStore,
        embedder: BaseEmbedder | None = None,
        reranker: BaseReranker | None = None,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.reranker = reranker

    def retrieve(
        self,
        query: str,
        config: RetrievalConfig | None = None,
        override_latest_only: bool | None = None,
        override_domains: list[str] | None = None,
        override_doc_ids: list[str] | None = None,
    ) -> tuple[list[RetrievedChunk], QueryAnalysis, dict[str, float]]:
        """Execute full retrieval pipeline and return ranked chunks, query analysis, and timings."""
        cfg = config or RetrievalConfig()
        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        # 1. Analyze & expand query (strip distractor drug-choice MCQ lines before retrieval!)
        t_q = time.perf_counter()
        raw_full_query = query
        retrieval_query = strip_mcq_distractor_options(query) if cfg.use_crag_multihop else query
        retrieval_query = strip_negated_background_for_retrieval(retrieval_query)
        if cfg.use_query_router:
            analysis = analyze_query(retrieval_query, use_lexicon=cfg.use_medical_lexicon)
        else:
            from rag_sfar.retrieval.medical_lexicon import expand_medical_query

            exp, acr = (
                expand_medical_query(retrieval_query) if cfg.use_medical_lexicon else (retrieval_query, {})
            )
            analysis = QueryAnalysis(
                original_query=retrieval_query,
                expanded_query=exp,
                acronyms_expanded=acr,
            )
        timings["query_analysis_ms"] = round((time.perf_counter() - t_q) * 1000, 2)

        # 2. Build hard safety filter mask
        if override_latest_only is not None:
            latest_only = override_latest_only
        elif not cfg.latest_edition_only:
            latest_only = False
        elif analysis.temporal_mode in ("all_versions", "specific_year"):
            latest_only = False
        else:
            latest_only = True

        allowed_years = (
            analysis.requested_years
            if (cfg.use_query_router and analysis.temporal_mode == "specific_year")
            else None
        )
        exclude_refs = cfg.exclude_references and not analysis.wants_references
        hard_domains = (
            override_domains
            if override_domains
            else (analysis.inferred_domains if cfg.use_hard_subdomain_filter else None)
        )

        mask = self.store.build_filter_mask(
            exclude_references=exclude_refs,
            prefer_french=cfg.prefer_french,
            latest_edition_only=latest_only,
            exclude_abrogated=cfg.exclude_abrogated,
            allowed_years=allowed_years,
            required_domains=hard_domains,
            doc_ids=override_doc_ids,
        )

        # 3. Tri-channel retrieval (BM25+ Word + Subword Char N-gram + Dense Neural)
        bm25_hits: list[tuple[int, float]] = []
        if cfg.use_bm25:
            t_b = time.perf_counter()
            bm25_hits = self.store.bm25.search(
                analysis.expanded_query,
                top_k=cfg.initial_candidates,
                allowed_mask=mask,
            )
            timings["bm25_ms"] = round((time.perf_counter() - t_b) * 1000, 2)

        subword_hits: list[tuple[int, float]] = []
        if cfg.use_subword and self.store.subword is not None:
            t_s = time.perf_counter()
            subword_hits = self.store.subword.search(
                analysis.expanded_query,
                top_k=cfg.initial_candidates,
                allowed_mask=mask,
            )
            timings["subword_ms"] = round((time.perf_counter() - t_s) * 1000, 2)

        dense_hits: list[tuple[int, float]] = []
        if cfg.use_dense and self.embedder is not None and self.store.embeddings is not None:
            t_d = time.perf_counter()
            q_vec = self.embedder.embed_query(analysis.expanded_query)
            dense_hits = self.store.dense_search(
                q_vec,
                top_k=cfg.initial_candidates,
                allowed_mask=mask,
            )
            timings["dense_ms"] = round((time.perf_counter() - t_d) * 1000, 2)

        # 4. Hybrid Fusion: Weighted RRF + optional DBSF (preserves runaway exact matches!)
        t_f = time.perf_counter()
        bm25_rank_map = {idx: (rank + 1, score) for rank, (idx, score) in enumerate(bm25_hits)}
        sub_rank_map = {idx: (rank + 1, score) for rank, (idx, score) in enumerate(subword_hits)}
        dense_rank_map = {idx: (rank + 1, score) for rank, (idx, score) in enumerate(dense_hits)}

        bm25_dbsf = _dbsf_normalize(bm25_hits) if cfg.use_dbsf_fusion else {}
        sub_dbsf = _dbsf_normalize(subword_hits) if cfg.use_dbsf_fusion else {}
        dense_dbsf = _dbsf_normalize(dense_hits) if cfg.use_dbsf_fusion else {}

        # Optional multi-facet RAG-Fusion boost for systemic clinical modifiers (BLSE, obese, rec_id)
        # PLUS Option-Aware MCQ parallel retrieval AND Composite Multi-Act surgical decomposition!
        facets = detect_clinical_facets(analysis) if cfg.use_crag_multihop else []
        mcq_opt_subqs = extract_mcq_option_subqueries(raw_full_query) if cfg.use_crag_multihop else []
        composite_subqs = (
            extract_composite_procedure_subqueries(raw_full_query) if cfg.use_crag_multihop else []
        )
        facet_rank_bonus: dict[int, float] = collections.defaultdict(float)
        guaranteed_subq_indices: list[int] = []
        if cfg.use_crag_multihop and facets:
            for facet in facets:
                # Only run pre-fusion sub-query for high-precision multi-hop facets
                if facet.name == "allergy":
                    continue
                f_hits = self.store.bm25.search(facet.subquery, top_k=15, allowed_mask=mask)
                for rank, (c_idx, _) in enumerate(f_hits, start=1):
                    facet_rank_bonus[c_idx] += 0.55 / (cfg.rrf_k + rank)

        if cfg.use_crag_multihop and (mcq_opt_subqs or composite_subqs):
            extra_queries = [sq for _, sq in mcq_opt_subqs] + composite_subqs
            for sq in extra_queries:
                sq_bm25 = self.store.bm25.search(sq, top_k=8, allowed_mask=mask)
                sq_sub = (
                    self.store.subword.search(sq, top_k=8, allowed_mask=mask)
                    if (cfg.use_subword and self.store.subword is not None)
                    else []
                )
                sq_scores: dict[int, float] = collections.defaultdict(float)
                for rk, (c_idx, _) in enumerate(sq_bm25, start=1):
                    sq_scores[c_idx] += 0.65 / (cfg.rrf_k + rk)
                    facet_rank_bonus[c_idx] += 0.60 / (cfg.rrf_k + rk)
                for rk, (c_idx, _) in enumerate(sq_sub, start=1):
                    sq_scores[c_idx] += 0.45 / (cfg.rrf_k + rk)
                    facet_rank_bonus[c_idx] += 0.40 / (cfg.rrf_k + rk)
                if sq_scores:
                    top_sq = sorted(sq_scores.items(), key=lambda kv: kv[1], reverse=True)
                    # Guarantee Top-2 matches for EACH MCQ option / composite surgical act reach Stage-2!
                    for c_idx, _ in top_sq[:2]:
                        if c_idx not in guaranteed_subq_indices:
                            guaranteed_subq_indices.append(c_idx)

        candidate_indices = (
            set(bm25_rank_map.keys())
            | set(sub_rank_map.keys())
            | set(dense_rank_map.keys())
            | set(facet_rank_bonus.keys())
        )

        # Normalize maximum theoretical RRF so DBSF blend sits cleanly on the same [0, 1] scale
        active_w = (
            (cfg.bm25_weight if bm25_hits else 0.0)
            + (cfg.subword_weight if subword_hits else 0.0)
            + (cfg.dense_weight if dense_hits else 0.0)
        ) or 1.0
        max_rrf_unit = active_w / (cfg.rrf_k + 1.0)

        fused: list[RetrievedChunk] = []
        for idx in candidate_indices:
            chunk = self.store.chunks[idx]
            rrf = facet_rank_bonus.get(idx, 0.0)
            b_rank, b_score = bm25_rank_map.get(idx, (None, 0.0))
            s_rank, _ = sub_rank_map.get(idx, (None, 0.0))
            d_rank, d_score = dense_rank_map.get(idx, (None, 0.0))
            if b_rank is not None:
                rrf += cfg.bm25_weight / (cfg.rrf_k + b_rank)
            if s_rank is not None:
                rrf += cfg.subword_weight / (cfg.rrf_k + s_rank)
            if d_rank is not None:
                rrf += cfg.dense_weight / (cfg.rrf_k + d_rank)

            base_score = rrf
            if cfg.use_dbsf_fusion:
                dbsf = (
                    cfg.bm25_weight * bm25_dbsf.get(idx, 0.0)
                    + cfg.subword_weight * sub_dbsf.get(idx, 0.0)
                    + cfg.dense_weight * dense_dbsf.get(idx, 0.0)
                ) / active_w
                rrf_norm = rrf / max_rrf_unit
                base_score = (1.0 - cfg.dbsf_blend) * rrf_norm + cfg.dbsf_blend * dbsf

            meta_mult = 1.0
            if cfg.use_soft_metadata_boost:
                meta_mult += self._compute_soft_metadata_boost(chunk, analysis, cfg)

            fused_score = base_score * max(0.25, meta_mult)
            fused.append(
                RetrievedChunk(
                    chunk=chunk,
                    final_score=round(fused_score, 6),
                    bm25_score=b_score,
                    bm25_rank=b_rank,
                    dense_score=d_score,
                    dense_rank=d_rank,
                    rrf_score=round(rrf, 6),
                    metadata_boost=round(meta_mult - 1.0, 4),
                )
            )

        fused.sort(key=lambda r: r.final_score, reverse=True)
        timings["fusion_ms"] = round((time.perf_counter() - t_f) * 1000, 2)

        # 5. Neural Cross-Encoder Reranking
        if analysis.temporal_mode == "all_versions":
            # Balance rerank pool across BOTH latest (e.g. 2026) and historical editions (e.g. 2018)
            half = max(4, cfg.rerank_top_k // 2)
            latest_cands = [r for r in fused if r.chunk.is_latest_edition][:half]
            older_cands = [r for r in fused if not r.chunk.is_latest_edition][:half]
            rerank_pool = []
            seen_pool_ids: set[str] = set()
            for pair_i in range(max(len(latest_cands), len(older_cands))):
                if pair_i < len(latest_cands):
                    rerank_pool.append(latest_cands[pair_i])
                    seen_pool_ids.add(latest_cands[pair_i].chunk.chunk_id)
                if pair_i < len(older_cands):
                    rerank_pool.append(older_cands[pair_i])
                    seen_pool_ids.add(older_cands[pair_i].chunk.chunk_id)
            for r in fused:
                if len(rerank_pool) >= cfg.rerank_top_k:
                    break
                if r.chunk.chunk_id not in seen_pool_ids:
                    rerank_pool.append(r)
                    seen_pool_ids.add(r.chunk.chunk_id)
        else:
            rerank_pool = list(fused[: cfg.rerank_top_k])
            # Multi-channel Top-2 + Option-Aware / Composite Multi-Act guarantee: never let a
            # #1/#2 hit from BM25, Subword Char N-Gram, Dense, or a decomposed MCQ option /
            # composite surgical act get starved out of Stage-2 Cross-Encoder reranking!
            if rerank_pool:
                fused_by_id = {r.chunk.chunk_id: r for r in fused}
                pool_ids = {r.chunk.chunk_id for r in rerank_pool}
                guaranteed: list[RetrievedChunk] = []
                for c_idx in guaranteed_subq_indices:
                    cid = self.store.chunks[c_idx].chunk_id
                    if cid not in pool_ids and cid in fused_by_id:
                        guaranteed.append(fused_by_id[cid])
                        pool_ids.add(cid)
                for channel_hits in (bm25_hits[:2], subword_hits[:2], dense_hits[:2]):
                    for c_idx, _ in channel_hits:
                        cid = self.store.chunks[c_idx].chunk_id
                        if cid not in pool_ids and cid in fused_by_id:
                            guaranteed.append(fused_by_id[cid])
                            pool_ids.add(cid)
                if guaranteed:
                    keep_n = max(1, cfg.rerank_top_k - len(guaranteed))
                    rerank_pool = rerank_pool[:keep_n] + guaranteed
        if cfg.use_reranker and self.reranker is not None and rerank_pool:
            t_r = time.perf_counter()
            ce_scores = self.reranker.score_pairs(
                analysis.expanded_query,
                [r.chunk.indexed_text for r in rerank_pool],
            )
            max_fused = max((r.final_score for r in rerank_pool), default=1.0) or 1.0
            subpop = _query_subpopulation(analysis.original_query)
            for r, ce in zip(rerank_pool, ce_scores):
                r.rerank_score = round(ce, 5)
                norm_prior = r.final_score / max_fused
                blended = 0.68 * ce + 0.32 * norm_prior
                # Population consistency: only when the query states the population.
                if analysis.population == "pediatrie" and r.chunk.population_hint == "adulte":
                    blended *= 0.68
                elif analysis.population == "adulte" and r.chunk.population_hint == "pediatrie":
                    blended *= 0.68
                # Sub-population consistency: neonatal (<28j) vs older child/adolescent
                if subpop == "neonatal" and _is_neonatal_only_chunk(r.chunk):
                    blended *= 1.15
                elif subpop == "child" and _is_neonatal_only_chunk(r.chunk):
                    blended *= 0.68
                # Do not let specialty allergy callout boxes crowd out procedure rows when
                # the query has NO affirmed allergy (e.g. "sans allergie aux bêtalactamines").
                if "allergy" not in analysis.modifiers and r.chunk.chunk_type == "callout_allergy":
                    blended *= 0.65
                blended *= self._compute_clinical_scope_multiplier(r.chunk, analysis)
                r.final_score = round(blended, 6)
            rerank_pool.sort(key=lambda r: r.final_score, reverse=True)
            timings["rerank_ms"] = round((time.perf_counter() - t_r) * 1000, 2)

        # 6. Deduplication & Diversity selection
        if analysis.temporal_mode == "all_versions":
            # Interleave latest & historical editions so temporal_diff ALWAYS receives both!
            latest_sel = self._select_diverse(
                [r for r in rerank_pool if r.chunk.is_latest_edition],
                cfg,
                max_per_doc=3,
                max_items=max(2, cfg.final_top_k // 2),
            )
            older_sel = self._select_diverse(
                [r for r in rerank_pool if not r.chunk.is_latest_edition],
                cfg,
                max_per_doc=3,
                max_items=max(2, cfg.final_top_k // 2),
            )
            selected = []
            for pair_i in range(max(len(latest_sel), len(older_sel))):
                if pair_i < len(latest_sel):
                    selected.append(latest_sel[pair_i])
                if pair_i < len(older_sel):
                    selected.append(older_sel[pair_i])
            selected = selected[: cfg.final_top_k]
        else:
            selected = self._select_diverse(
                rerank_pool,
                cfg,
                max_per_doc=cfg.max_chunks_per_doc,
                max_allergy_callouts=2,
            )

        # 6b. For Option-Aware MCQ / Composite Multi-Act queries, ensure high-signal structured
        # chunks for EACH decomposed sub-query are preserved inside `selected` so the LLM can
        # verify every single surgical act or MCQ choice side-by-side without noisy prose!
        if cfg.use_crag_multihop and guaranteed_subq_indices and analysis.temporal_mode != "all_versions":
            sel_ids = {r.chunk.chunk_id for r in selected}
            pool_by_id = {r.chunk.chunk_id: r for r in rerank_pool}
            fused_by_id = {r.chunk.chunk_id: r for r in fused}
            base_top = selected[0].final_score if selected else 0.75
            primary_doc_id = selected[0].chunk.doc_id if selected else None
            injected = 0
            for c_idx in guaranteed_subq_indices:
                cid = self.store.chunks[c_idx].chunk_id
                if cid in sel_ids:
                    continue
                cand = pool_by_id.get(cid) or fused_by_id.get(cid)
                if cand is None:
                    continue
                if cand.chunk.chunk_type not in ("table_row_card", "table_markdown", "recommendation_box"):
                    continue
                if primary_doc_id and cand.chunk.doc_id != primary_doc_id and (cand.rerank_score or 0.0) < 0.65:
                    continue
                # Respect anatomical exclusion and population consistency before injecting
                if self._compute_clinical_scope_multiplier(cand.chunk, analysis) < 0.7:
                    continue
                if analysis.population == "adulte" and cand.chunk.population_hint == "pediatrie":
                    continue
                selected.append(
                    RetrievedChunk(
                        chunk=cand.chunk,
                        final_score=round(max(cand.final_score, base_top * 0.82), 6),
                        bm25_score=cand.bm25_score,
                        dense_score=cand.dense_score,
                        rerank_score=cand.rerank_score,
                        is_expanded_context=True,
                        expansion_reason="crag_rescue:multi_act_or_mcq_option",
                    )
                )
                sel_ids.add(cid)
                injected += 1
                if injected >= 4:
                    break

        # 7. Corrective RAG (CRAG) Facet Coverage Gate & Rescue Pass
        if cfg.use_crag_multihop and facets:
            t_crag = time.perf_counter()
            selected = self._crag_rescue_missing_facets(selected, facets, mask, analysis, cfg)
            timings["crag_ms"] = round((time.perf_counter() - t_crag) * 1000, 2)

        # 8. Small-to-Big Context Expansion (Section-Anchored Allergy/Footnote Callouts + Neighbors)
        t_e = time.perf_counter()
        if cfg.expand_section_callouts or cfg.expand_neighbors:
            selected = self._expand_context(selected, analysis, cfg)
        timings["context_expand_ms"] = round((time.perf_counter() - t_e) * 1000, 2)

        # 9. Output contract: at most `final_top_k` chunks, sorted by decreasing score. Added
        # chunks (CRAG rescues, callouts, neighbours) compete with the selection on their score
        # instead of being appended beyond the budget. Edition-comparison queries keep their
        # latest/older interleaving so both editions stay represented.
        if analysis.temporal_mode != "all_versions":
            selected = sorted(selected, key=lambda r: r.final_score, reverse=True)
        selected = selected[: max(0, cfg.final_top_k)]
        if cfg.context_window > 0 or cfg.expand_table_parent:
            selected = self._window_expand(selected, cfg)
        timings["total_retrieval_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        return selected, analysis, timings

    def _window_expand(self, selected: list[RetrievedChunk], cfg: RetrievalConfig) -> list[RetrievedChunk]:
        """Small-to-big context windows after ranking (generic, structure-based).

        For each of the first `context_window_top` results: the parent table when the result is
        a table row card, then +-`context_window` neighbouring chunks of the same document
        (bibliography excluded). Expansions are placed right after their anchor, in reading
        order, and stop at `context_char_budget` characters overall. Ranked results are never
        dropped."""
        seen = {r.chunk.chunk_id for r in selected}
        budget = cfg.context_char_budget - sum(len(r.chunk.text) for r in selected)
        out: list[RetrievedChunk] = []
        for rank, item in enumerate(selected):
            out.append(item)
            if rank >= cfg.context_window_top or budget <= 0:
                continue
            extra: list = []
            c = item.chunk
            if cfg.expand_table_parent and c.chunk_type == "table_row_card":
                cur = c
                for _ in range(60):
                    if not cur.prev_chunk_id:
                        break
                    cur = self.store.get_chunk(cur.prev_chunk_id)
                    if cur is None or cur.doc_id != c.doc_id:
                        break
                    if cur.chunk_type == "table_markdown":
                        extra.append(cur)
                        break
                    if cur.chunk_type != "table_row_card":
                        break
            if cfg.context_window > 0:
                for direction in ("prev_chunk_id", "next_chunk_id"):
                    cur = c
                    for _ in range(cfg.context_window):
                        nid = getattr(cur, direction)
                        if not nid:
                            break
                        cur = self.store.get_chunk(nid)
                        if cur is None or cur.doc_id != c.doc_id or cur.is_reference_section:
                            break
                        extra.append(cur)
            extra.sort(key=lambda ch: ch.chunk_index)
            for ch in extra:
                if ch.chunk_id in seen or len(ch.text) > budget:
                    continue
                seen.add(ch.chunk_id)
                budget -= len(ch.text)
                out.append(RetrievedChunk(chunk=ch, final_score=round(item.final_score * 0.9, 6),
                                          is_expanded_context=True, expansion_reason="context_window"))
        return out

    def _crag_rescue_missing_facets(
        self,
        selected: list[RetrievedChunk],
        facets: list,
        mask: np.ndarray,
        analysis: QueryAnalysis,
        cfg: RetrievalConfig,
    ) -> list[RetrievedChunk]:
        """CRAG post-retrieval audit: if a mandatory clinical facet (BLSE, obese, rec_id,
        pediatric mg/kg, renal) is absent from Top-K, launch a focused rescue retrieval."""
        missing = find_missing_facets(selected, facets, min_chunks_per_facet=1)
        if not missing:
            return selected

        out = list(selected)
        seen_ids = {r.chunk.chunk_id for r in out}
        base_score = out[0].final_score if out else 0.5
        total_chars = sum(len(r.chunk.indexed_text) for r in out)

        for facet in missing:
            rescue_hits = self.store.bm25.search(facet.subquery, top_k=20, allowed_mask=mask)
            added = 0
            for c_idx, b_sc in rescue_hits:
                chunk = self.store.chunks[c_idx]
                if chunk.chunk_id in seen_ids:
                    continue
                if not facet.evidence_regex.search(chunk.indexed_text):
                    continue
                # Respect population consistency during rescue
                if analysis.population == "pediatrie" and chunk.population_hint == "adulte":
                    continue
                if analysis.population == "adulte" and chunk.population_hint == "pediatrie":
                    continue
                if total_chars + len(chunk.indexed_text) > cfg.max_context_chars:
                    break
                out.append(
                    RetrievedChunk(
                        chunk=chunk,
                        final_score=round(base_score * 0.90, 6),
                        bm25_score=b_sc,
                        is_expanded_context=True,
                        expansion_reason=f"crag_rescue:{facet.name}",
                    )
                )
                seen_ids.add(chunk.chunk_id)
                total_chars += len(chunk.indexed_text)
                added += 1
                if added >= 2:
                    break
        return out

    def _compute_soft_metadata_boost(
        self, chunk: Chunk, analysis: QueryAnalysis, cfg: RetrievalConfig
    ) -> float:
        """Compute interpretable soft multiplicative metadata adjustments."""
        boost = 0.0

        if analysis.inferred_domains:
            chunk_doms = {d.lower() for d in chunk.domains}
            if any(d.lower() in chunk_doms for d in analysis.inferred_domains):
                boost += cfg.domain_boost

        if analysis.population == "pediatrie":
            if chunk.population_hint == "pediatrie":
                boost += cfg.population_boost
            elif chunk.population_hint == "adulte":
                boost -= cfg.population_mismatch_penalty
        elif analysis.population == "adulte":
            if chunk.population_hint == "adulte":
                boost += cfg.population_boost * 0.5
            elif chunk.population_hint == "pediatrie":
                boost -= cfg.population_mismatch_penalty
        # Population not stated (or mixed): no population prior.

        if analysis.setting == "urgence":
            if chunk.setting_scope == "urgence":
                boost += cfg.setting_boost
            elif chunk.setting_scope == "programme":
                boost -= cfg.setting_boost * 0.8
        elif analysis.setting == "programme":
            if chunk.setting_scope == "programme":
                boost += cfg.setting_boost
            elif chunk.setting_scope == "urgence":
                boost -= cfg.setting_boost * 0.8

        boost += cfg.role_boost_map.get(chunk.doc_role, 0.0)

        if chunk.chunk_type == "table_row_card":
            boost += cfg.table_card_boost
        elif chunk.chunk_type == "recommendation_box":
            boost += 0.14

        if analysis.requested_years and chunk.effective_year in analysis.requested_years:
            boost += 0.25

        if "allergy" in analysis.modifiers and chunk.has_allergy_info:
            boost += 0.14
        elif "allergy" not in analysis.modifiers and chunk.chunk_type == "callout_allergy":
            boost -= 0.25

        subpop = _query_subpopulation(analysis.original_query)
        if subpop == "neonatal" and _is_neonatal_only_chunk(chunk):
            boost += 0.22
        elif subpop == "child" and _is_neonatal_only_chunk(chunk):
            boost -= 0.22

        if "diff" in analysis.modifiers:
            txt_lo = chunk.text.lower()
            sec_lo = chunk.section_path.lower()
            if "historique des versions" in sec_lo:
                boost += 0.55
            elif chunk.chunk_type in ("prose", "recommendation_box") and any(
                kw in txt_lo for kw in ("mise à jour", "actualisation", "modifi", "nouveau", "changement")
            ):
                boost += 0.35
            elif chunk.chunk_type == "table_row_card":
                boost -= 0.15

        # Explicit `(hors X)` scope exclusion in a section heading that the query contradicts
        boost -= 0.65 * _count_contradicted_exclusions(chunk.section_path, analysis.original_query)

        return boost

    def _compute_clinical_scope_multiplier(self, chunk: Chunk, analysis: QueryAnalysis) -> float:
        """Post-rerank clinical scope guard: demote chunks whose section heading explicitly
        excludes, with a parenthesised `(hors X)`, a situation X that the query is about."""
        n = _count_contradicted_exclusions(chunk.section_path, analysis.original_query)
        return 0.45**n

    def _select_diverse(
        self,
        candidates: list[RetrievedChunk],
        cfg: RetrievalConfig,
        max_per_doc: int | None = None,
        max_items: int | None = None,
        max_allergy_callouts: int | None = None,
    ) -> list[RetrievedChunk]:
        selected: list[RetrievedChunk] = []
        seen_sigs: set[str] = set()
        doc_counts: collections.Counter[str] = collections.Counter()
        allergy_count = 0
        cap = max_per_doc if max_per_doc is not None else cfg.max_chunks_per_doc
        limit = max_items if max_items is not None else cfg.final_top_k

        for cand in candidates:
            if len(selected) >= limit:
                break
            if doc_counts[cand.chunk.doc_id] >= cap:
                continue
            if (
                max_allergy_callouts is not None
                and cand.chunk.chunk_type == "callout_allergy"
                and allergy_count >= max_allergy_callouts
            ):
                continue
            if cfg.dedup_by_content:
                sig = re.sub(r"\W+", "", cand.chunk.text.lower())[:180]
                if sig in seen_sigs:
                    continue
                seen_sigs.add(sig)
            selected.append(cand)
            doc_counts[cand.chunk.doc_id] += 1
            if cand.chunk.chunk_type == "callout_allergy":
                allergy_count += 1

        return selected

    def _expand_context(
        self,
        selected: list[RetrievedChunk],
        analysis: QueryAnalysis,
        cfg: RetrievalConfig,
    ) -> list[RetrievedChunk]:
        out = list(selected)
        seen_ids = {r.chunk.chunk_id for r in out}
        total_chars = sum(len(r.chunk.indexed_text) for r in out)
        wants_callout = bool(
            set(analysis.modifiers) & {"allergy", "obesity", "renal", "dosage"}
        )

        if cfg.expand_section_callouts:
            pulled_allergy_sections: set[str] = set()
            pulled_footnotes = 0
            # Check for true specialty allergy boxes ("En cas d'allergie aux bêtalactamines")
            # anchored to the EXACT same parent specialty section as Top-1/Top-2 procedure chunks!
            for item in selected[:3]:
                for cid in item.chunk.linked_callout_ids:
                    if cid in seen_ids:
                        continue
                    c_obj = self.store.get_chunk(cid)
                    if c_obj is None:
                        continue
                    should_pull = False
                    reason = "section_callout"
                    if (
                        c_obj.chunk_type == "callout_allergy"
                        and ("allergy" in analysis.modifiers)
                        and item.chunk.parent_section_id not in pulled_allergy_sections
                        and re.search(r"en\s+cas\s+d['’]allergie", c_obj.text, re.I)
                    ):
                        should_pull = True
                        pulled_allergy_sections.add(item.chunk.parent_section_id)
                        reason = "specialty_allergy_box"
                    elif (
                        c_obj.chunk_type == "callout_footnote"
                        and pulled_footnotes < 2
                        and len(c_obj.text) <= 950
                        and (
                            wants_callout
                            or item.chunk.population_hint == "pediatrie"
                            or bool(_FOOTNOTE_REF_RE.search(item.chunk.text))
                        )
                    ):
                        should_pull = True
                        pulled_footnotes += 1
                        reason = "section_footnote"

                    if should_pull and total_chars + len(c_obj.indexed_text) <= cfg.max_context_chars:
                        out.append(
                            RetrievedChunk(
                                chunk=c_obj,
                                final_score=round(
                                    item.final_score * (0.99 if reason == "specialty_allergy_box" else 0.94),
                                    6,
                                ),
                                is_expanded_context=True,
                                expansion_reason=reason,
                            )
                        )
                        seen_ids.add(cid)
                        total_chars += len(c_obj.indexed_text)

        if cfg.expand_neighbors:
            pulled_neighbors = 0
            for item in selected[:2]:
                if pulled_neighbors >= 1:
                    break
                nxt_id = item.chunk.next_chunk_id
                if not nxt_id or nxt_id in seen_ids:
                    continue
                nxt = self.store.get_chunk(nxt_id)
                if nxt is None or nxt.is_reference_section:
                    continue
                if (
                    nxt.section_id == item.chunk.section_id
                    and nxt.chunk_type not in ("table_row_card", "table_markdown")
                    and len(nxt.text) <= 650
                    and total_chars + len(nxt.indexed_text) <= cfg.max_context_chars
                ):
                    out.append(
                        RetrievedChunk(
                            chunk=nxt,
                            final_score=round(item.final_score * 0.85, 6),
                            is_expanded_context=True,
                            expansion_reason="next_neighbor",
                        )
                    )
                    seen_ids.add(nxt_id)
                    total_chars += len(nxt.indexed_text)
                    pulled_neighbors += 1

        return out


_SECTION_EXCLUSION_RE = re.compile(r"\(\s*hors\s+([^()]{3,80}?)\s*\)")
_EXCLUSION_STOPWORDS = frozenset(
    {"de", "du", "des", "la", "le", "les", "l", "d", "et", "ou", "en", "a", "au", "aux", "un", "une"}
)


def _excluded_scopes(section_path: str) -> list[list[str]]:
    """Content words of each parenthesised `(hors X)` exclusion in a section path.

    Only parenthesised exclusions are read: that is how RFE headings restrict the scope of a
    section (e.g. a table restricted to some sites). Unparenthesised `hors` belongs to titles
    that define the scope of the whole document and must not penalise that document."""
    out: list[list[str]] = []
    for phrase in _SECTION_EXCLUSION_RE.findall(fold_accents(section_path.lower())):
        words = [w for w in re.findall(r"[a-z0-9]+", phrase) if w not in _EXCLUSION_STOPWORDS and len(w) >= 3]
        if words:
            out.append(words)
    return out


def _count_contradicted_exclusions(section_path: str, query: str) -> int:
    """Number of `(hors X)` exclusions of a section whose X is the subject of the query.

    X is the subject when all its content words appear in the query and the query does not
    itself exclude X ("hors X", "hors du/de la X", "en dehors du X")."""
    scopes = _excluded_scopes(section_path)
    if not scopes:
        return 0
    q_fold = fold_accents(query.lower())
    q_words = set(re.findall(r"[a-z0-9]+", q_fold))
    n = 0
    for words in scopes:
        if not all(w in q_words for w in words):
            continue
        head = re.escape(words[0])
        if re.search(rf"\b(?:de)?hors\s+(?:(?:du|des|de\s+la|de\s+l['’ ]?|de|d['’ ]|les?|la)\s*)?{head}\b", q_fold):
            continue
        n += 1
    return n


def format_context_for_llm(
    retrieved: list[RetrievedChunk],
    query: str = "",
    reorder_u_shape: bool = True,
    prune_prose: bool = False,
) -> str:
    """Format retrieved chunks into a citation-ready clinical context block with optional
    Lost-in-the-Middle U-Shape ordering and Provence-style prose pruning."""
    # Keep original [S1..Sk] numbering aligned with citations; apply U-Shape reordering on
    # longer contexts (>= 6 chunks) where Lost-in-the-Middle attention decay occurs.
    numbered = list(enumerate(retrieved, start=1))
    if reorder_u_shape and len(numbered) >= 6:
        left = [pair for i, pair in enumerate(numbered) if i % 2 == 0]
        right = [pair for i, pair in enumerate(numbered) if i % 2 == 1]
        right.reverse()
        numbered = left + right

    blocks: list[str] = []
    for orig_idx, item in numbered:
        c = item.chunk
        yr = str(c.effective_year) if c.effective_year else "Date N/A"
        ver = f" ({c.version_label})" if c.version_label else ""
        edition_tag = (
            "EN VIGUEUR"
            if c.is_latest_edition
            else f"ÉDITION ANTÉRIEURE — REMPLACÉE ({c.superseded_by})"
        )
        grades = f" | Grades : {', '.join(c.grade_levels)}" if c.grade_levels else ""
        exp_tag = f" | Contexte associé : {item.expansion_reason}" if item.is_expanded_context else ""
        body = (
            prune_verbose_prose(c.text, query=query, chunk_type=c.chunk_type)
            if (prune_prose and query)
            else c.text
        )
        header = (
            f"### [S{orig_idx}] {c.doc_title} — {c.doc_type} SFAR {yr}{ver} [{edition_tag}]\n"
            f"Section : {c.section_path or 'Général'} | Type : {c.chunk_type}{grades}{exp_tag}"
        )
        blocks.append(f"{header}\n{body}")
    return "\n\n---\n\n".join(blocks)
