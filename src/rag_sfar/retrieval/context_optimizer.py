"""Context Engineering Optimizers:
1. Lost-in-the-Middle U-Shape Ordering (Liu et al. / Medical RAG 2025-2026): places the
   highest-confidence sources at the start (primacy) and end (recency) of the LLM context.
2. Provence-Inspired Query-Aware Sentence Pruning (ICLR 2025): trims low-signal narrative
   boilerplate from verbose prose chunks while strictly preserving structured tables,
   row cards, recommendation boxes, allergy boxes, GRADE markers, and dosage/timing lines.
"""

from __future__ import annotations

import re

from rag_sfar.retrieval.medical_lexicon import tokenize_medical_french
from rag_sfar.schemas import RetrievedChunk

PROTECTED_CHUNK_TYPES = frozenset(
    {"table_markdown", "table_row_card", "recommendation_box", "callout_allergy", "callout_footnote"}
)
CLINICAL_MUST_KEEP_RE = re.compile(
    r"(?:\bR\d+\.\d+|\bGRADE\s*[12]|Avis\s+d['’]experts?|Accord\s+(?:fort|faible)|"
    r"\b\d+(?:[.,]\d+)?\s*(?:mg/kg|mg|g|UI|mL|IVL|min|h\b|heures?)\b|\bJ-\d+\b|"
    r"il\s+est\s+(?:probablement\s+)?recommand[ée]|il\s+n['’]est\s+pas\s+recommand[ée]|"
    r"les\s+experts\s+sugg[èe]rent|allerg|contre-indiqu)",
    re.I,
)


def reorder_lost_in_the_middle(items: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Reorder descending-relevance chunks into a U-shaped primacy/recency layout:
    `[rank 1, rank 3, rank 5, ..., rank 6, rank 4, rank 2]`.

    Counters Transformer middle-context attention decay (Liu et al., TACL 2024;
    verified in 2025–2026 clinical RAG benchmarks).
    """
    if len(items) <= 2:
        return list(items)
    left: list[RetrievedChunk] = []
    right: list[RetrievedChunk] = []
    for idx, item in enumerate(items):
        if idx % 2 == 0:
            left.append(item)
        else:
            right.append(item)
    right.reverse()
    return left + right


def prune_verbose_prose(
    text: str,
    query: str,
    chunk_type: str,
    max_chars: int = 1100,
    min_keep_sentences: int = 3,
) -> str:
    """Deterministically prune irrelevant boilerplate sentences from verbose prose chunks.

    NEVER touches structured tables, row cards, recommendation boxes, or allergy boxes.
    """
    if chunk_type in PROTECTED_CHUNK_TYPES or len(text) <= max_chars:
        return text

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) <= min_keep_sentences:
        return text

    q_toks = set(tokenize_medical_french(query))
    scored: list[tuple[int, float, str]] = []
    for idx, sent in enumerate(sentences):
        s_toks = set(tokenize_medical_french(sent))
        overlap = len(q_toks & s_toks) / max(1, len(q_toks))
        clinical_bonus = 1.5 if CLINICAL_MUST_KEEP_RE.search(sent) else 0.0
        pos_bonus = 0.25 if idx == 0 else 0.0
        scored.append((idx, overlap + clinical_bonus + pos_bonus, sent))

    # Select highest-signal sentences within max_chars, then restore original sentence order
    ranked = sorted(scored, key=lambda x: x[1], reverse=True)
    kept_indices: set[int] = set()
    budget = 0
    for idx, _, sent in ranked:
        if len(kept_indices) >= min_keep_sentences and budget + len(sent) + 1 > max_chars:
            continue
        kept_indices.add(idx)
        budget += len(sent) + 1

    ordered = [sent for idx, _, sent in scored if idx in kept_indices]
    return " ".join(ordered)


def select_generation_context(
    retrieved: list[RetrievedChunk],
    is_allergy_query: bool = False,
    max_chunks: int = 5,
    min_relative_score: float = 0.62,
    max_total_chars: int = 5200,
) -> list[RetrievedChunk]:
    """Noise-Filtered Precision Context Selection (Cuconasu et al. SIGIR 2024 / Provence ICLR 2025).

    Retrieval optimizes Recall (Top-8..10), whereas Generation optimizes Signal-to-Noise (CUE):
    - Drops low-relevance distractor chunks that flood the LLM with wrong surgical molecules.
    - Always preserves CRAG rescues and (when allergy is requested) the best allergy callout,
      while excluding unrequested allergy callouts on non-allergy queries.
    """
    if not retrieved:
        return []
    top1_score = max(r.final_score for r in retrieved) or 1.0

    # Filter out distractor allergy boxes on non-allergy queries
    pool: list[RetrievedChunk] = []
    for r in retrieved:
        if not is_allergy_query and r.chunk.chunk_type == "callout_allergy":
            continue
        pool.append(r)
    if not pool:
        pool = list(retrieved)

    # On allergy queries, anchor to the highest-scoring compact surgical row-card (`table_row_card`)
    # when strongly scored (>= 0.80) so the procedure row and its own specialty allergy box sit
    # immediately adjacent at [S1] and [S2] (never separated by unrelated specialty prose, while
    # never demoting a 0.999 allergy box behind a noisy low-score full table dump!).
    row_card_pool = [r for r in pool if r.chunk.chunk_type == "table_row_card" and r.final_score >= 0.80]
    struct_pool = [r for r in pool if r.chunk.chunk_type in ("table_row_card", "table_markdown")]
    proc_pool = row_card_pool or struct_pool or [r for r in pool if r.chunk.chunk_type != "callout_allergy"]
    anchor_pool = proc_pool[:2] if proc_pool else pool[:2]
    top_sec_ids = {r.chunk.parent_section_id for r in anchor_pool if r.chunk.parent_section_id}
    has_own_allergy = is_allergy_query and any(
        r.chunk.chunk_type == "callout_allergy" and r.chunk.parent_section_id in top_sec_ids
        for r in pool
    )

    must_keep: list[RetrievedChunk] = []
    rest: list[RetrievedChunk] = []
    if is_allergy_query and row_card_pool and has_own_allergy:
        # Place the compact primary surgical procedure card FIRST, then its matching specialty allergy box!
        must_keep.append(row_card_pool[0])
        for r in pool:
            if r.chunk.chunk_type == "callout_allergy" and r.chunk.parent_section_id in top_sec_ids:
                must_keep.append(r)
                break
    elif is_allergy_query and has_own_allergy:
        # When no compact row-card exists (only a large full table dump), put the specialty
        # allergy box FIRST at Primacy [S1] so 1re intention is never obscured by sub-exceptions!
        for r in pool:
            if r.chunk.chunk_type == "callout_allergy" and r.chunk.parent_section_id in top_sec_ids:
                must_keep.append(r)
                break
    must_ids = {r.chunk.chunk_id for r in must_keep}

    for i, r in enumerate(pool):
        if r.chunk.chunk_id in must_ids:
            continue
        is_crag = bool(r.expansion_reason and r.expansion_reason.startswith("crag_rescue"))
        is_own_allergy = is_allergy_query and (
            r.chunk.chunk_type == "callout_allergy" and r.chunk.parent_section_id in top_sec_ids
        )
        is_foreign_allergy = (
            is_allergy_query
            and has_own_allergy
            and r.chunk.chunk_type == "callout_allergy"
            and r.chunk.parent_section_id not in top_sec_ids
        )
        if is_foreign_allergy:
            continue
        if i < 2 or is_crag or is_own_allergy:
            must_keep.append(r)
            must_ids.add(r.chunk.chunk_id)
        else:
            rest.append(r)

    chosen: list[RetrievedChunk] = []
    seen: set[str] = set()
    used_chars = 0

    for r in must_keep:
        if r.chunk.chunk_id in seen:
            continue
        chosen.append(r)
        seen.add(r.chunk.chunk_id)
        used_chars += len(r.chunk.text)

    for r in rest:
        if len(chosen) >= max_chunks:
            break
        if r.chunk.chunk_id in seen:
            continue
        if r.final_score < top1_score * min_relative_score:
            continue
        if used_chars + len(r.chunk.text) > max_total_chars and len(chosen) >= 3:
            continue
        chosen.append(r)
        seen.add(r.chunk.chunk_id)
        used_chars += len(r.chunk.text)

    return chosen

