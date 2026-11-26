"""Quantitative retrieval evaluation metrics for rigorous RAG ablation studies."""

from __future__ import annotations

import collections
from typing import Any

from rag_sfar.config import RetrievalConfig
from rag_sfar.evaluation.benchmarks import EvalQuestion
from rag_sfar.retrieval.medical_lexicon import fold_accents
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.schemas import RetrievedChunk


def _doc_matches_question(rc: RetrievedChunk, q: EvalQuestion) -> bool:
    c = rc.chunk
    if q.expected_topic_lineage and c.topic_lineage == q.expected_topic_lineage:
        return True
    if q.expected_title_keywords:
        title_fold = fold_accents(c.doc_title.lower())
        if all(fold_accents(kw.lower()) in title_fold for kw in q.expected_title_keywords):
            return True
    return False


def _edition_is_current_for_question(rc: RetrievedChunk, q: EvalQuestion) -> bool:
    if not _doc_matches_question(rc, q):
        return False
    c = rc.chunk
    if q.expects_multiple_editions:
        return True
    if q.expected_min_year is not None and c.effective_year is not None:
        return c.effective_year >= q.expected_min_year
    return c.is_latest_edition


def _evidence_present(retrieved: list[RetrievedChunk], terms: list[str]) -> bool | None:
    if not terms:
        return None
    blob = fold_accents(" ".join(r.chunk.indexed_text.lower() for r in retrieved))
    return all(fold_accents(t.lower()) in blob for t in terms)


def evaluate_retrieval_dataset(
    retriever: SfarRagRetriever,
    questions: list[EvalQuestion],
    config: RetrievalConfig,
    k_eval: int | None = None,
) -> dict[str, Any]:
    """Evaluate a retrieval configuration across an entire question dataset.

    Measures:
    - `doc_hit_rate`: Target guideline family found in top-k
    - `current_edition_hit_rate`: Correct UP-TO-DATE edition found in top-k (not obsolete!)
    - `obsolete_intrusion_rate`: % of non-diff queries where an obsolete edition enters top-k
    - `bibliography_pollution_rate`: % of retrieved chunks that are Références/Bibliography
    - `evidence_recall`: % of questions whose required clinical answer terms appear in top-k
    - `allergy_evidence_recall`: Evidence recall specifically on allergy-alternative questions
    - `mrr_current_edition`: Mean Reciprocal Rank of first correct current-edition chunk
    - `multi_edition_coverage`: % of temporal-diff queries retrieving >=2 distinct years
    - `avg_latency_ms` & `avg_context_chars` (~4 chars/token)
    """
    n = len(questions)
    if n == 0:
        return {}

    doc_hits = 0
    curr_hits = 0
    obsolete_intrusions = 0
    non_diff_count = 0
    total_chunks_returned = 0
    ref_chunks_returned = 0

    ev_hits = 0
    ev_total = 0
    allergy_ev_hits = 0
    allergy_ev_total = 0
    rr_sum = 0.0
    multi_ed_hits = 0
    multi_ed_total = 0
    latencies: list[float] = []
    ctx_chars_list: list[int] = []
    per_category: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"n": 0, "curr_hit": 0, "ev_hit": 0, "ev_n": 0}
    )
    failures: list[dict[str, Any]] = []

    for q in questions:
        retrieved, analysis, timings = retriever.retrieve(q.question, config=config)
        eval_slice = retrieved[:k_eval] if k_eval else retrieved
        latencies.append(timings.get("total_retrieval_ms", 0.0))
        ctx_chars_list.append(sum(len(r.chunk.text) for r in eval_slice))

        total_chunks_returned += len(eval_slice)
        ref_chunks_returned += sum(1 for r in eval_slice if r.chunk.is_reference_section)

        has_doc = any(_doc_matches_question(r, q) for r in eval_slice)
        has_curr = any(_edition_is_current_for_question(r, q) for r in eval_slice)
        if has_doc:
            doc_hits += 1
        if has_curr:
            curr_hits += 1

        if not q.expects_multiple_editions:
            non_diff_count += 1
            if any(not r.chunk.is_latest_edition for r in eval_slice):
                obsolete_intrusions += 1
        else:
            multi_ed_total += 1
            distinct_yrs = {
                r.chunk.effective_year
                for r in eval_slice
                if _doc_matches_question(r, q) and r.chunk.effective_year is not None
            }
            if len(distinct_yrs) >= 2:
                multi_ed_hits += 1

        # MRR for first current-edition matching chunk
        rr = 0.0
        for rank, r in enumerate(eval_slice, start=1):
            if _edition_is_current_for_question(r, q):
                rr = 1.0 / rank
                break
        rr_sum += rr

        # Evidence presence check
        ev = _evidence_present(eval_slice, q.required_evidence_terms)
        cat_stat = per_category[q.category]
        cat_stat["n"] += 1
        if has_curr:
            cat_stat["curr_hit"] += 1

        if ev is not None:
            ev_total += 1
            cat_stat["ev_n"] += 1
            if ev:
                ev_hits += 1
                cat_stat["ev_hit"] += 1
            if q.is_allergy_question:
                allergy_ev_total += 1
                if ev:
                    allergy_ev_hits += 1

        if not has_curr or ev is False:
            failures.append(
                {
                    "id": q.id,
                    "title": q.title,
                    "category": q.category,
                    "has_curr_edition": has_curr,
                    "evidence_found": ev,
                    "required_terms": q.required_evidence_terms,
                    "top3_docs": [
                        f"{r.chunk.doc_title} ({r.chunk.effective_year}, {r.chunk.chunk_type})"
                        for r in eval_slice[:3]
                    ],
                }
            )

    avg_ctx_chars = sum(ctx_chars_list) / max(1, n)
    return {
        "config_name": config.name,
        "chunking_strategy": config.chunking_strategy,
        "num_questions": n,
        "doc_hit_rate": round(doc_hits / n, 4),
        "current_edition_hit_rate": round(curr_hits / n, 4),
        "obsolete_intrusion_rate": round(obsolete_intrusions / max(1, non_diff_count), 4),
        "bibliography_pollution_rate": round(
            ref_chunks_returned / max(1, total_chunks_returned), 4
        ),
        "evidence_recall": round(ev_hits / max(1, ev_total), 4) if ev_total else None,
        "evidence_eval_count": ev_total,
        "allergy_evidence_recall": (
            round(allergy_ev_hits / max(1, allergy_ev_total), 4) if allergy_ev_total else None
        ),
        "allergy_eval_count": allergy_ev_total,
        "mrr_current_edition": round(rr_sum / n, 4),
        "multi_edition_coverage": (
            round(multi_ed_hits / multi_ed_total, 4) if multi_ed_total else None
        ),
        "avg_latency_ms": round(sum(latencies) / max(1, n), 2),
        "avg_context_chars": round(avg_ctx_chars, 1),
        "est_context_tokens": round(avg_ctx_chars / 4.0, 0),
        "per_category": {
            cat: {
                "n": s["n"],
                "curr_hit_rate": round(s["curr_hit"] / max(1, s["n"]), 4),
                "ev_recall": round(s["ev_hit"] / s["ev_n"], 4) if s["ev_n"] else None,
            }
            for cat, s in sorted(per_category.items())
        },
        "sample_failures": failures[:15],
    }
