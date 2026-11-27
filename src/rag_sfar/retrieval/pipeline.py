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
from rag_sfar.retrieval.medical_lexicon import fold_accents, tokenize_medical_french
from rag_sfar.retrieval.query_tools import (
    negated_token_weights,
    patient_negated_spans,
    remove_spans,
    split_mcq,
)
from rag_sfar.retrieval.reranker import BaseReranker
from rag_sfar.retrieval.router import _AGE_CONTEXT, analyze_query
from rag_sfar.retrieval.vector_store import LocalVectorStore
from rag_sfar.schemas import Chunk, QueryAnalysis, RetrievedChunk

# Sub-population of a paediatric query: neonate (< 28 days) vs older child. Applied only when the
# query is already routed to paediatrics, and an age needs an age context ("âgé de 5 jours",
# "nourrisson de 3 semaines", "J3 de vie"): a bare duration ("arrêter 3 jours avant",
# "antibiothérapie de 5 jours", "diabétique depuis 5 ans") is not an age.
_NEONATAL_TERM_RE = re.compile(r"\b(?:nouveau[- ]n[ée]e?s?|n[ée]onat\w*|pr[ée]matur[ée]e?s?)\b", re.I)
_AGE_DAYS_RE = re.compile(
    rf"{_AGE_CONTEXT}\s+(\d+)\s*(jours?|semaines?)\b|\b[jJ]\s?(\d+)\s+de\s+vie\b|\b(\d+)\s*jours?\s+de\s+vie\b",
    re.I,
)
_OLDER_CHILD_QUERY_RE = re.compile(
    rf"\badolescente?s?\b|{_AGE_CONTEXT}\s+(?:[1-9]|1[0-7])\s*ans?\b",
    re.I,
)
_NEONATAL_ONLY_SECTION_RE = re.compile(r"\bn[ée]onatal(?:e|ogique|ogie)\b", re.I)
# An isolated footnote call (`*`, `**`, `***`, `#`, `†`, `‡`), not Markdown bold/italic markers.
_FOOTNOTE_REF_RE = re.compile(r"(?<![\*\w.])\*{1,3}(?![\*\w])|(?<![\w#])#(?![\w#])|[†‡]")
# A footnote paragraph printed under a table starts with its call mark ("* …", "\*\* …",
# "# …", "† …"; Markdown escapes allowed), not with bold text ("**Céfazoline**").
_NOTE_START_RE = re.compile(r"^\s*(?:(?:\\?\*){1,4}(?![\*\w])|\\?#(?![#\w])|[†‡])")


_CALL_RE = re.compile(r"\*{1,4}(?![\*\w])|(?<![\w#])#(?![\w#])|[†‡]")
# Markdown emphasis (bold / italic spans) is formatting, not a footnote call.
_EMPHASIS_RE = re.compile(r"(\*{1,3})(?=[^\s*])(.+?)(?<=[^\s*])\1")
_NOTE_LINE_RE = re.compile(r"^\s*(\*{1,4}|#|†|‡)(?![\*\w#])", re.M)
_SCOPE_NOTE_RE = re.compile(r"\b(?:de|dans|du|pour)\s+ce(?:s)?\s+tableaux?\b", re.I)
# A "note" that is a bibliographic reference or an author address, not a table note.
_BIBLIO_OR_ADDRESS_RE = re.compile(
    r"auteur\s+correspondant|correspondance\s*:|e-?mail|@\w|\bdoi\b|\bet\s+al\b|"
    r"\b(?:19|20)\d{2}\s*;\s*\d+\s*(?:\(\d+\))?\s*:\s*\d+",
    re.I,
)


def _call_marks(text: str) -> set[str]:
    """Footnote call marks used in a text ("Gustilo-Anderson**", "IVL*", "#"). Escaped stars
    ("\\*") are literal marks; unescaped emphasis spans ("**Céfazoline**") are ignored."""
    t = text.replace("\\*", "\x00")
    t = _EMPHASIS_RE.sub(r"\2", t).replace("\x00", "*")
    return set(_CALL_RE.findall(t))


def _note_marks(text: str) -> set[str]:
    """Marks that start a note line ("* …", "** …", "# …")."""
    return set(_NOTE_LINE_RE.findall(text.replace("\\", "")))


def _act_tokens(row_text: str) -> set[str]:
    """Content words of the act label of a row card: the value of the first cell of its cell
    line (context lines such as "Sous-catégorie", "Section" or "Périmètre" are not the act)."""
    lines = [l for l in row_text.splitlines() if l.strip()]
    # The cell line ("Acte : … | Molécule : …"); context lines that some indexes prepend
    # ("Section : …", "Périmètre : …", "Sous-catégorie : …") are not the act.
    line = next((l for l in lines if " | " in l), lines[-1] if lines else "")
    cell = line.split(" | ")[0]
    value = cell.split(" : ", 1)[1] if " : " in cell else cell
    return {t for t in tokenize_medical_french(value) if len(t) >= 4 and not t.isdigit()}


def _labels_match(a: set[str], b: set[str]) -> bool:
    """Two act labels match when they share >= 2 content words covering at least half of the
    shorter label."""
    if not a or not b:
        return False
    shared = len(a & b)
    return shared >= 2 and shared >= 0.5 * min(len(a), len(b))


def _first_line(text: str) -> str:
    return text.strip().split("\n", 1)[0].strip()


def _dedup_by_text(items: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Drop a chunk whose normalised text already appears earlier in the context."""
    seen: set[str] = set()
    out = []
    for r in items:
        key = re.sub(r"\W+", " ", r.chunk.text.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _chunk_population(chunk: Chunk) -> str:
    """Population of a chunk: the structural labels written by ingestion when the index has
    them (`populations`: adulte / pediatrie / neonatal / obstetrique), else `population_hint`."""
    labels = set(getattr(chunk, "populations", None) or [])
    if labels:
        ped = bool(labels & {"pediatrie", "neonatal"})
        adult = bool(labels & {"adulte", "obstetrique"})
        if ped and not adult:
            return "pediatrie"
        if adult and not ped:
            return "adulte"
        return "mixte"
    return chunk.population_hint


def _query_subpopulation(query: str, population: str = "pediatrie") -> str | None:
    """Neonatal (< 28 days) vs older child, for a query already routed to paediatrics."""
    if population != "pediatrie":
        return None
    if _NEONATAL_TERM_RE.search(query):
        return "neonatal"
    for m in _AGE_DAYS_RE.finditer(query):
        if m.group(1):
            n, unit = int(m.group(1)), m.group(2).lower()
            days = n * 7 if unit.startswith("semaine") else n
        else:
            days = int(m.group(3) or m.group(4))
        if days < 28:
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
        # Negated background of the patient ("chez un adulte sans X ni Y"): lower weight in the
        # lexical query and/or removal from the semantic (dense + cross-encoder) query.
        # MCQ: the stem alone can carry the main query; options get their own retrieval (9b).
        mcq_stem, mcq_options = split_mcq(raw_full_query) if cfg.mcq_option_quota > 0 else (raw_full_query, [])
        orig = analysis.original_query
        suffix = analysis.expanded_query[len(orig):] if analysis.expanded_query.startswith(orig) else ""
        base_text = orig
        if mcq_options and cfg.mcq_stem_only and len(mcq_stem) >= 12:
            base_text = mcq_stem
        lexical_query = semantic_query = base_text + suffix
        lex_weights: dict[str, float] = {}
        if cfg.negated_term_weight < 1.0 or cfg.negation_strip_semantic:
            spans = patient_negated_spans(base_text)
            if spans:
                lex_weights = negated_token_weights(base_text, spans, cfg.negated_term_weight)
                if cfg.negation_strip_semantic:
                    semantic_query = remove_spans(base_text, spans) + suffix
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
                lexical_query,
                top_k=cfg.initial_candidates,
                allowed_mask=mask,
                term_weights=lex_weights or None,
            )
            timings["bm25_ms"] = round((time.perf_counter() - t_b) * 1000, 2)

        subword_hits: list[tuple[int, float]] = []
        if cfg.use_subword and self.store.subword is not None:
            t_s = time.perf_counter()
            subword_hits = self.store.subword.search(
                lexical_query,
                top_k=cfg.initial_candidates,
                allowed_mask=mask,
            )
            timings["subword_ms"] = round((time.perf_counter() - t_s) * 1000, 2)

        dense_hits: list[tuple[int, float]] = []
        if cfg.use_dense and self.embedder is not None and self.store.embeddings is not None:
            t_d = time.perf_counter()
            q_vec = self.embedder.embed_query(semantic_query)
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
                semantic_query,
                [r.chunk.indexed_text for r in rerank_pool],
            )
            max_fused = max((r.final_score for r in rerank_pool), default=1.0) or 1.0
            subpop = _query_subpopulation(analysis.original_query, analysis.population)
            for r, ce in zip(rerank_pool, ce_scores):
                r.rerank_score = round(ce, 5)
                norm_prior = r.final_score / max_fused
                blended = 0.68 * ce + 0.32 * norm_prior
                # Population consistency: only when the query states the population.
                if analysis.population == "pediatrie" and r.chunk.population_hint == "adulte":
                    blended *= 0.72
                elif analysis.population == "adulte" and r.chunk.population_hint == "pediatrie":
                    blended *= 0.72
                # Sub-population consistency: neonatal (<28j) vs older child/adolescent
                if subpop == "neonatal" and _is_neonatal_only_chunk(r.chunk):
                    blended *= 1.15
                elif subpop == "child" and _is_neonatal_only_chunk(r.chunk):
                    blended *= 0.68
                blended *= self._compute_clinical_scope_multiplier(r.chunk, analysis)
                r.final_score = round(blended, 6)
            rerank_pool.sort(key=lambda r: r.final_score, reverse=True)
            timings["rerank_ms"] = round((time.perf_counter() - t_r) * 1000, 2)

        # Coverage signal (exposed, never used to filter): best cross-encoder score of the main
        # query, plus the agreement between the lexical and dense channels.
        self.last_coverage = self._coverage_signal(rerank_pool, bm25_hits, dense_hits, cfg)
        timings.update(self.last_coverage)

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

        # 9b. Multi-query guarantees (B1): each MCQ option and each population compatible with
        # the query keep a few passages of their own (added after the ranked results).
        guaranteed: list[RetrievedChunk] = []
        if analysis.temporal_mode != "all_versions" and (mcq_options or cfg.population_quota > 0):
            t_m = time.perf_counter()
            guaranteed = self._guaranteed_extras(
                selected, analysis, cfg, mask, semantic_query, mcq_stem, mcq_options
            )
            timings["multi_query_ms"] = round((time.perf_counter() - t_m) * 1000, 2)
        if not cfg.context_hygiene:
            selected, guaranteed = selected + guaranteed, []

        if (
            cfg.context_window > 0
            or cfg.expand_table_parent
            or cfg.attach_table_notes
            or cfg.context_order != "rank"
            or cfg.context_hygiene
        ):
            selected = self._window_expand(selected, cfg, guaranteed)
        timings["total_retrieval_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        return selected, analysis, timings

    def _window_expand(
        self, selected: list[RetrievedChunk], cfg: RetrievalConfig, guaranteed: list[RetrievedChunk] | None = None
    ) -> list[RetrievedChunk]:
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
            is_guaranteed = (item.expansion_reason or "").startswith(("mcq_option", "population"))
            if (rank >= cfg.context_window_top and not is_guaranteed) or budget <= 0:
                continue
            extra: list = []
            notes: list = []
            c = item.chunk
            is_table = c.chunk_type in ("table_row_card", "table_markdown")
            if cfg.attach_table_notes and is_table:
                notes = (
                    self._table_notes(c, cfg.table_notes_max_chars)
                    if cfg.table_notes_mode == "linked"
                    else self._called_notes(c, cfg.table_notes_max_chars, cfg.table_notes_mode == "called_scope")
                )
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
            if cfg.context_window > 0 and (is_table or not cfg.context_window_tables_only):
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
            note_ids = {n.chunk_id for n in notes}
            extra = [ch for ch in extra if ch.chunk_id not in note_ids] + notes
            extra.sort(key=lambda ch: ch.chunk_index)
            for ch in extra:
                if ch.chunk_id in seen or len(ch.text) > budget:
                    continue
                seen.add(ch.chunk_id)
                budget -= len(ch.text)
                reason = "table_note" if ch.chunk_id in note_ids else "context_window"
                out.append(RetrievedChunk(chunk=ch, final_score=round(item.final_score * 0.9, 6),
                                          is_expanded_context=True, expansion_reason=reason))
        if cfg.context_hygiene:
            out = self._place_guaranteed(out, guaranteed or [], budget, getattr(self, "_guarantee_anchors", {}))
            out = _dedup_by_text(out)
        if cfg.context_order == "document":
            out = self._document_order(out)
        return out

    @staticmethod
    def _place_guaranteed(
        out: list[RetrievedChunk], guaranteed: list[RetrievedChunk], budget: int,
        anchors: dict[str, str],
    ) -> list[RetrievedChunk]:
        """Insert each guaranteed passage (no window of its own) right after the block of its
        anchor (the ranked passage it complements, else the first result), within the remaining
        character budget. Placed there, a later cut by rank removes lower-value chunks first."""
        ids = {r.chunk.chunk_id for r in out}
        for g in guaranteed:
            if g.chunk.chunk_id in ids or len(g.chunk.text) > budget:
                continue
            anchor = anchors.get(g.chunk.chunk_id)
            pos = next((i for i, r in enumerate(out) if r.chunk.chunk_id == anchor), 0)
            pos += 1
            while pos < len(out) and out[pos].is_expanded_context:
                pos += 1  # after the anchor's own window
            out.insert(pos, g)
            ids.add(g.chunk.chunk_id)
            budget -= len(g.chunk.text)
        return out

    @staticmethod
    def _coverage_signal(
        rerank_pool: list[RetrievedChunk],
        bm25_hits: list[tuple[int, float]],
        dense_hits: list[tuple[int, float]],
        cfg: RetrievalConfig,
    ) -> dict[str, float]:
        """Does the corpus cover the query? `coverage_score` = best cross-encoder probability
        over the reranked pool (-1 without reranker); `coverage_supported` = 1.0 when it reaches
        `cfg.coverage_threshold` (calibrated IN-SAMPLE on dev — the threshold was chosen and
        reported on the same queries — so indicative only, not validated; see
        reports/agents/B1_retrieval.md);
        `channel_agreement` = share of the BM25 top 10 also in the dense top 10."""
        ce = [r.rerank_score for r in rerank_pool if r.rerank_score is not None]
        top_b = {i for i, _ in bm25_hits[:10]}
        top_d = {i for i, _ in dense_hits[:10]}
        # -1.0 = not available (no reranker / channel disabled); keeps the dict JSON-safe.
        score = round(max(ce), 5) if ce else -1.0
        return {
            "coverage_score": score,
            "coverage_supported": (1.0 if score >= cfg.coverage_threshold else 0.0) if ce else -1.0,
            "channel_agreement": len(top_b & top_d) / 10.0 if (top_b and top_d) else -1.0,
            "dense_top_score": round(dense_hits[0][1], 5) if dense_hits else -1.0,
        }

    def _chunk_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Cached per-chunk arrays: population hint, document id, is-table flag."""
        if getattr(self, "_arrays", None) is None:
            chunks = self.store.chunks
            self._arrays = (
                np.array([_chunk_population(c) for c in chunks]),
                np.array([c.doc_id for c in chunks]),
                np.array([c.chunk_type in ("table_row_card", "table_markdown") for c in chunks]),
            )
        return self._arrays

    def _focused_search(
        self, query: str, mask: np.ndarray, cfg: RetrievalConfig, top_n: int, pool: int = 16
    ) -> list[RetrievedChunk]:
        """Small hybrid search (BM25 + dense, RRF, cross-encoder) inside `mask`, used for
        sub-queries. Returns the `top_n` best passages by the same blend as the main pass."""
        if not mask.any():
            return []
        fused: dict[int, float] = collections.defaultdict(float)
        if cfg.use_bm25:
            for rank, (idx, _) in enumerate(self.store.bm25.search(query, top_k=cfg.initial_candidates, allowed_mask=mask), 1):
                fused[idx] += cfg.bm25_weight / (cfg.rrf_k + rank)
        if cfg.use_dense and self.embedder is not None and self.store.embeddings is not None:
            q_vec = self.embedder.embed_query(query)
            for rank, (idx, _) in enumerate(self.store.dense_search(q_vec, top_k=cfg.initial_candidates, allowed_mask=mask), 1):
                fused[idx] += cfg.dense_weight / (cfg.rrf_k + rank)
        cands = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:pool]
        if not cands:
            return []
        out = [RetrievedChunk(chunk=self.store.chunks[i], final_score=s, rrf_score=round(s, 6)) for i, s in cands]
        if cfg.use_reranker and self.reranker is not None:
            ce = self.reranker.score_pairs(query, [r.chunk.indexed_text for r in out])
            top = max(r.final_score for r in out) or 1.0
            for r, c in zip(out, ce):
                r.rerank_score = round(c, 5)
                r.final_score = round(0.68 * c + 0.32 * r.final_score / top, 6)
            out.sort(key=lambda r: r.final_score, reverse=True)
        return out[:top_n]

    def _guaranteed_extras(
        self,
        selected: list[RetrievedChunk],
        analysis: QueryAnalysis,
        cfg: RetrievalConfig,
        mask: np.ndarray,
        semantic_query: str,
        mcq_stem: str,
        mcq_options: list[tuple[str, str]],
    ) -> list[RetrievedChunk]:
        """Passages guaranteed to each MCQ option (stem + option) and to each population that
        the query does not exclude (adult / paediatric metadata, restricted to the documents of
        the top results). Returned in addition to the ranked results, without duplicates."""
        seen = {r.chunk.chunk_id for r in selected}
        extras: list[RetrievedChunk] = []
        self._guarantee_anchors = {}

        def add(hits: list[RetrievedChunk], reason: str, n: int) -> None:
            for h in hits:
                if n <= 0:
                    break
                if h.chunk.chunk_id in seen:
                    n -= 1  # already in context: counts toward the quota
                    continue
                seen.add(h.chunk.chunk_id)
                h.expansion_reason = reason
                extras.append(h)
                n -= 1

        if mcq_options and cfg.mcq_option_quota > 0:
            for letter, text in mcq_options:
                sub = f"{mcq_stem} {text}".strip() if cfg.mcq_option_with_stem else text
                add(self._focused_search(sub, mask, cfg, cfg.mcq_option_quota), f"mcq_option:{letter}", cfg.mcq_option_quota)

        if cfg.population_quota > 0 and selected and cfg.population_guard:
            for hit, anchor_id, pop in self._guarded_population(selected, analysis, cfg, mask, semantic_query):
                if hit.chunk.chunk_id in seen:
                    continue
                seen.add(hit.chunk.chunk_id)
                hit.expansion_reason = f"population:{pop}"
                self._guarantee_anchors[hit.chunk.chunk_id] = anchor_id
                extras.append(hit)
        elif cfg.population_quota > 0 and selected:
            pops = {"pediatrie": ["pediatrie"], "adulte": ["adulte"]}.get(analysis.population, ["adulte", "pediatrie"])
            pop_arr, doc_arr, table_arr = self._chunk_arrays()
            top_docs = list(dict.fromkeys(r.chunk.doc_id for r in selected[:3]))
            in_docs = np.isin(doc_arr, top_docs)
            context = selected + extras
            for pop in pops:
                restrict = mask & in_docs & (pop_arr == pop)
                if cfg.population_tables_only:
                    restrict &= table_arr
                # The best `population_quota` passages of the restricted search must be in the
                # context (those already there count toward the quota).
                need = cfg.population_quota
                if not restrict.any():
                    continue
                query = semantic_query
                if cfg.population_counterpart:
                    # Parallel adult / paediatric tables: the act label of the best table row of
                    # the other population is added to the query to find its counterpart.
                    anchor = next(
                        (r.chunk for r in context
                         if r.chunk.chunk_type == "table_row_card"
                         and _chunk_population(r.chunk) not in (pop, "non_specifie", "mixte")),
                        None,
                    )
                    if anchor is not None:
                        query = f"{semantic_query} {anchor.text[:300]}"
                add(self._focused_search(query, restrict, cfg, need), f"population:{pop}", need)
        return extras

    def _population_doc_ok(self, doc_id: str, min_rows: int = 3) -> bool:
        """Guard of the population rule: the document has table rows of both populations."""
        cache = getattr(self, "_pop_doc_cache", None)
        if cache is None:
            cache = self._pop_doc_cache = {}
        if doc_id not in cache:
            pop_arr, doc_arr, _ = self._chunk_arrays()
            rows = np.array([c.chunk_type == "table_row_card" for c in self.store.chunks])
            in_doc = (doc_arr == doc_id) & rows
            cache[doc_id] = bool(
                int(np.sum(in_doc & (pop_arr == "adulte"))) >= min_rows
                and int(np.sum(in_doc & (pop_arr == "pediatrie"))) >= min_rows
            )
        return cache[doc_id]

    def _guarded_population(
        self,
        selected: list[RetrievedChunk],
        analysis: QueryAnalysis,
        cfg: RetrievalConfig,
        mask: np.ndarray,
        semantic_query: str,
    ) -> list[tuple[RetrievedChunk, str, str]]:
        """Guarded population rule. Fires only when the document of the first result has table
        rows of both populations. For each population the query does not exclude and that has
        no ranked row yet, the anchor is the best ranked row of the other population in that
        document; the question alone is searched inside the document's rows of the missing
        population, and a hit is kept only when its act label (first cell) matches the
        anchor's. Returns (passage, anchor chunk id, population)."""
        top_doc = selected[0].chunk.doc_id
        if not self._population_doc_ok(top_doc):
            return []
        pops = {"pediatrie": ["pediatrie"], "adulte": ["adulte"]}.get(analysis.population, ["adulte", "pediatrie"])
        pop_arr, doc_arr, _ = self._chunk_arrays()
        rows_arr = np.array([c.chunk_type == "table_row_card" for c in self.store.chunks]) if getattr(self, "_rows_arr", None) is None else self._rows_arr
        self._rows_arr = rows_arr
        ranked_rows = [r.chunk for r in selected if r.chunk.chunk_type == "table_row_card" and r.chunk.doc_id == top_doc]
        out: list[tuple[RetrievedChunk, str, str]] = []
        for pop in pops:
            other = "adulte" if pop == "pediatrie" else "pediatrie"
            anchors = [c for c in ranked_rows if _chunk_population(c) == other]
            if not anchors:
                continue
            anchor = anchors[0]
            label = _act_tokens(anchor.text)
            if len(label) < 2:
                continue
            if any(_chunk_population(c) == pop and _labels_match(label, _act_tokens(c.text)) for c in ranked_rows):
                continue  # the counterpart is already ranked
            restrict = mask & (doc_arr == top_doc) & (pop_arr == pop) & rows_arr
            for hit in self._focused_search(semantic_query, restrict, cfg, top_n=8):
                if _labels_match(label, _act_tokens(hit.chunk.text)):
                    out.append((hit, anchor.chunk_id, pop))
                    break
        return out

    def _called_notes(self, chunk: Chunk, max_chars: int, with_scope: bool) -> list[Chunk]:
        """Notes called by a retrieved table chunk: a note is attached only when one of its call
        marks (*, **, ***, #, †, ‡ at the start of a note line) appears in the chunk's text.
        Candidates are the notes linked at ingestion and the note paragraphs printed right after
        the CURRENT table (the walk stops at the next table). References, author addresses and
        allergy boxes are never attached. With `with_scope`, the table's scope note (a linked
        note that speaks of "ce tableau" / "ces tableaux") is attached too."""
        calls = _call_marks(chunk.text)
        out: dict[str, Chunk] = {}

        def eligible(c: Chunk | None) -> bool:
            return (
                c is not None
                and c.doc_id == chunk.doc_id
                and c.chunk_type not in ("callout_allergy", "references")
                and not c.is_reference_section
                and len(c.text) <= max_chars
                and not _BIBLIO_OR_ADDRESS_RE.search(c.text)
            )

        for cid in chunk.linked_callout_ids:
            c = self.store.get_chunk(cid)
            if not eligible(c):
                continue
            if calls & _note_marks(c.text) or (with_scope and _SCOPE_NOTE_RE.search(c.text[:200]) and not _note_marks(c.text)):
                out[c.chunk_id] = c
        if calls:
            # Walk to the end of the current table only: its own row cards (same table_id when
            # the index has one), never into the next table.
            tid = getattr(chunk, "table_id", "") or ""
            cur: Chunk | None = chunk
            if chunk.chunk_type == "table_markdown":
                nxt = self.store.get_chunk(chunk.next_chunk_id) if chunk.next_chunk_id else None
                cur = chunk
                while nxt is not None and nxt.chunk_type == "table_row_card" and nxt.doc_id == chunk.doc_id:
                    cur, nxt = nxt, (self.store.get_chunk(nxt.next_chunk_id) if nxt.next_chunk_id else None)
            header = self._table_header(chunk)
            nxt = self.store.get_chunk(cur.next_chunk_id) if cur and cur.next_chunk_id else None
            continuations = 0
            while nxt is not None and nxt.doc_id == chunk.doc_id:
                if nxt.chunk_type == "table_row_card" and (
                    not tid or (getattr(nxt, "table_id", "") or "") in ("", tid)
                ):
                    pass
                elif (
                    nxt.chunk_type == "table_markdown"
                    and header
                    and _first_line(nxt.text) == header
                    and continuations < 6
                ):
                    # Same header row: the table continues after a page break (same table).
                    continuations += 1
                    tid = getattr(nxt, "table_id", "") or ""
                else:
                    break
                nxt = self.store.get_chunk(nxt.next_chunk_id) if nxt.next_chunk_id else None
            taken = 0
            while nxt is not None and taken < 2 and nxt.doc_id == chunk.doc_id and _NOTE_START_RE.match(nxt.text):
                if eligible(nxt) and calls & _note_marks(nxt.text):
                    out[nxt.chunk_id] = nxt
                taken += 1
                nxt = self.store.get_chunk(nxt.next_chunk_id) if nxt.next_chunk_id else None
        return list(out.values())

    def _table_header(self, chunk: Chunk) -> str:
        """Header row of the table a table chunk belongs to ("" when not found)."""
        cur: Chunk | None = chunk
        for _ in range(200):
            if cur is None or cur.doc_id != chunk.doc_id:
                return ""
            if cur.chunk_type == "table_markdown":
                return _first_line(cur.text)
            if cur.chunk_type != "table_row_card":
                return ""
            cur = self.store.get_chunk(cur.prev_chunk_id) if cur.prev_chunk_id else None
        return ""

    @staticmethod
    def _document_order(items: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Group the context by document (documents in order of their best-ranked passage) and
        put each document's passages in reading order."""
        doc_rank: dict[str, int] = {}
        for i, r in enumerate(items):
            doc_rank.setdefault(r.chunk.doc_id, i)
        return sorted(items, key=lambda r: (doc_rank[r.chunk.doc_id], r.chunk.chunk_index))

    def _table_notes(self, chunk: Chunk, max_chars: int) -> list[Chunk]:
        """Notes that qualify a table chunk: footnote / scope-note callouts linked to it at
        ingestion, and the footnote paragraphs printed right after its table (text starting
        with a call mark), whatever their chunk type. Allergy callouts are not notes."""
        out: dict[str, Chunk] = {}
        for cid in chunk.linked_callout_ids:
            c = self.store.get_chunk(cid)
            if c is not None and c.chunk_type == "callout_footnote" and len(c.text) <= max_chars:
                out[c.chunk_id] = c
        cur: Chunk | None = chunk
        for _ in range(200):  # walk to the end of the table
            nxt = self.store.get_chunk(cur.next_chunk_id) if cur and cur.next_chunk_id else None
            if nxt is None or nxt.doc_id != chunk.doc_id:
                cur = None
                break
            cur = nxt
            if cur.chunk_type not in ("table_row_card", "table_markdown"):
                break
        taken = 0
        while cur is not None and cur.doc_id == chunk.doc_id and taken < 2:
            if cur.is_reference_section or not _NOTE_START_RE.match(cur.text):
                break
            if len(cur.text) <= max_chars:
                out[cur.chunk_id] = cur
            taken += 1
            cur = self.store.get_chunk(cur.next_chunk_id) if cur.next_chunk_id else None
        return list(out.values())

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

        subpop = _query_subpopulation(analysis.original_query, analysis.population)
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

    def _own_table_notes(self, chunk: Chunk, max_steps: int = 120) -> set[str]:
        """Footnote chunks placed right after the table that `chunk` belongs to (empty set when
        `chunk` is not a table chunk)."""
        if chunk.chunk_type not in ("table_row_card", "table_markdown"):
            return set()
        cur: Chunk | None = chunk
        for _ in range(max_steps):
            nxt = self.store.get_chunk(cur.next_chunk_id) if cur and cur.next_chunk_id else None
            if nxt is None or nxt.doc_id != chunk.doc_id:
                return set()
            cur = nxt
            if cur.chunk_type not in ("table_row_card", "table_markdown"):
                break
        notes: set[str] = set()
        while cur is not None and cur.doc_id == chunk.doc_id and cur.chunk_type == "callout_footnote":
            notes.add(cur.chunk_id)
            cur = self.store.get_chunk(cur.next_chunk_id) if cur.next_chunk_id else None
            if len(notes) >= 3:
                break
        return notes

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
                # Notes of the table this result belongs to (beyond pediatric/footnote-call
                # triggers, a note of another table in the same section is never pulled).
                table_notes = self._own_table_notes(item.chunk)
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
                            (wants_callout and len(c_obj.text) <= 550)
                            or (
                                cid in table_notes
                                and (
                                    item.chunk.population_hint == "pediatrie"
                                    or bool(_FOOTNOTE_REF_RE.search(item.chunk.text))
                                )
                            )
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
