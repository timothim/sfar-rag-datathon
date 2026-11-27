"""Generation context construction: which retrieved chunks the LLM reads, in which order and form.

Every transformation here is structural (document order, table layout, edition metadata) and
applies to any guideline of the corpus; none depends on a clinical topic.

Pipeline (each step switchable in `GenerationConfig`):
1. selection   — legacy noise filter, or every chunk in rank order within a char/chunk budget;
2. tables      — drop a table row card whose row is already shown by its parent table, or render
                 Markdown tables as one "header : value" line per row;
3. merging     — chunks of one document that follow each other in the text become one passage;
4. order       — rank (best first), U-shape, or document order (documents by best rank);
5. rendering   — source header (legacy one-liner or rich: title, year, edition status, section,
                 nature, population, strength) and [Sx] numbering in display order.

`assemble_context` returns the passages as `RetrievedChunk`s (merged passages carry a synthetic
chunk whose text is the merged text), so citations and the verifier work unchanged: [Sx] is the
x-th returned passage.
"""

from __future__ import annotations

import re

from rag_sfar.generation.settings import GenerationConfig
from rag_sfar.retrieval.context_optimizer import prune_verbose_prose
from rag_sfar.schemas import RetrievedChunk

_TABLE_TYPES = ("table_markdown",)
_CARD_TYPES = ("table_row_card",)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


# ---------------------------------------------------------------- 1. selection


def select_within_budget(retrieved: list[RetrievedChunk], max_chunks: int, max_chars: int) -> list[RetrievedChunk]:
    """Rank order, skip a chunk that would overflow the character budget (a later, shorter one
    may still fit), stop at `max_chunks`."""
    out: list[RetrievedChunk] = []
    used = 0
    for rc in retrieved:
        if len(out) >= max_chunks:
            break
        n = len(rc.chunk.text)
        if out and used + n > max_chars:
            continue
        out.append(rc)
        used += n
    return out


# ---------------------------------------------------------------- 2. tables


def _card_values(text: str) -> list[str]:
    """Cell values of a row card ("Sous-catégorie : X\\nCol : v | Col : v")."""
    vals = []
    for line in text.splitlines():
        for cell in line.split(" | "):
            if " : " in cell:
                v = cell.split(" : ", 1)[1].strip()
                if v:
                    vals.append(_norm(v))
    return vals


def _row_covered(card_text: str, table_text: str) -> bool:
    lines = [ln for ln in card_text.splitlines() if not ln.lower().startswith("sous-cat")]
    vals = _card_values("\n".join(lines))
    t = _norm(table_text.replace("|", " "))
    t = re.sub(r"\s+", " ", t)
    return bool(vals) and all(re.sub(r"\s+", " ", v) in t for v in vals)


def drop_covered_cards(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Remove a row card when a Markdown table chunk of the same document in the context already
    contains every cell value of that row (the card is then a duplicate)."""
    tables = [rc for rc in chunks if rc.chunk.chunk_type in _TABLE_TYPES]
    if not tables:
        return chunks
    out = []
    for rc in chunks:
        if rc.chunk.chunk_type in _CARD_TYPES and any(
            t.chunk.doc_id == rc.chunk.doc_id and _row_covered(rc.chunk.text, t.chunk.text) for t in tables
        ):
            continue
        out.append(rc)
    return out


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def markdown_table_as_rows(text: str) -> str:
    """Render each Markdown table of `text` as one "Header : value | ..." line per row.

    A row whose only non-empty cell is the first one (a sub-category banner, often bold) becomes
    "Sous-catégorie : X" and is repeated in front of the following rows, so each line can be read
    alone. Empty cells are omitted (never shifted). Non-table lines are kept as they are."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        is_header = (
            ln.strip().startswith("|")
            and i + 1 < len(lines)
            and re.fullmatch(r"\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*", lines[i + 1] or "")
        )
        if not is_header:
            out.append(ln)
            i += 1
            continue
        headers = _split_row(ln)
        i += 2
        sub = ""
        while i < len(lines) and lines[i].strip().startswith("|"):
            cells = _split_row(lines[i])
            i += 1
            filled = [(h, c) for h, c in zip(headers, cells) if c and c.strip("* ")]
            if not filled:
                continue
            if len(filled) == 1 and filled[0][0] == headers[0] and len(headers) > 1:
                sub = filled[0][1].strip("* ").strip()
                continue
            parts = [f"{h.strip('* ') or 'Colonne'} : {c}" for h, c in filled]
            prefix = f"[{sub}] " if sub else ""
            out.append("- " + prefix + " | ".join(parts))
    return "\n".join(out)


# ---------------------------------------------------------------- 3. merging


def _adjacent(a, b) -> bool:
    return a.doc_id == b.doc_id and (a.next_chunk_id == b.chunk_id or b.chunk_index == a.chunk_index + 1)


class Passage:
    """One displayed source: one chunk, or a run of consecutive chunks of one document."""

    def __init__(self, items: list[RetrievedChunk], best_rank: int) -> None:
        self.items = items
        self.best_rank = best_rank

    @property
    def first(self):
        return self.items[0].chunk


def merge_adjacent_chunks(chunks: list[RetrievedChunk]) -> list[Passage]:
    """Group chunks of the same document that follow each other in the text (reading order).
    Duplicated chunk ids are kept once. Passage rank = best rank of its chunks."""
    rank = {}
    uniq: list[RetrievedChunk] = []
    for i, rc in enumerate(chunks):
        if rc.chunk.chunk_id in rank:
            continue
        rank[rc.chunk.chunk_id] = i
        uniq.append(rc)
    by_doc: dict[str, list[RetrievedChunk]] = {}
    for rc in uniq:
        by_doc.setdefault(rc.chunk.doc_id, []).append(rc)
    passages: list[Passage] = []
    for items in by_doc.values():
        items.sort(key=lambda r: r.chunk.chunk_index)
        run = [items[0]]
        for rc in items[1:]:
            if _adjacent(run[-1].chunk, rc.chunk):
                run.append(rc)
            else:
                passages.append(Passage(run, min(rank[r.chunk.chunk_id] for r in run)))
                run = [rc]
        passages.append(Passage(run, min(rank[r.chunk.chunk_id] for r in run)))
    return passages


# ---------------------------------------------------------------- 4. order


def order_passages(passages: list[Passage], order: str) -> list[Passage]:
    by_rank = sorted(passages, key=lambda p: p.best_rank)
    if order == "rank":
        return by_rank
    if order == "u_shape":
        if len(by_rank) < 6:
            return by_rank
        left = by_rank[0::2]
        right = by_rank[1::2]
        return left + right[::-1]
    if order == "document":
        doc_rank: dict[str, int] = {}
        for p in by_rank:
            doc_rank.setdefault(p.first.doc_id, p.best_rank)
        return sorted(passages, key=lambda p: (doc_rank[p.first.doc_id], p.first.chunk_index))
    raise ValueError(f"unknown context order {order!r}")


# ---------------------------------------------------------------- 5. rendering

_NATURE = {
    "table_markdown": "tableau",
    "table_row_card": "ligne de tableau",
    "recommendation_box": "recommandation",
    "recommendation_unit": "recommandation",
    "callout_footnote": "note",
    "callout_allergy": "encadré allergie",
    "prose": "texte",
}


def _strengths(grades: list[str]) -> str:
    seen: dict[str, str] = {}
    for g in grades:
        k = _norm(g).replace("’", "'")
        seen.setdefault(k, g)
    return ", ".join(seen.values())


def _edition_label(c) -> str:
    if not getattr(c, "is_active", True):
        return "ABROGÉE — ne plus appliquer"
    if c.is_latest_edition:
        return "en vigueur"
    return f"ÉDITION ANTÉRIEURE, remplacée{(' par ' + c.superseded_by) if c.superseded_by else ''}"


def rich_header(label: str, items: list[RetrievedChunk]) -> str:
    c = items[0].chunk
    yr = str(c.effective_year) if c.effective_year else "année non précisée"
    ver = f", {c.version_label}" if c.version_label else ""
    lines = [f"[{label}] {c.doc_title} — {c.doc_type} SFAR {yr}{ver} — {_edition_label(c)}"]
    sections = list(dict.fromkeys(r.chunk.section_path for r in items if r.chunk.section_path))
    if sections:
        lines.append("Section : " + sections[0] + ("" if len(sections) == 1 else f" (et {len(sections) - 1} autre(s))"))
    natures = list(dict.fromkeys(_NATURE.get(r.chunk.chunk_type, "texte") for r in items))
    meta = ["Nature : " + ", ".join(natures)]
    pops = list(dict.fromkeys(p for r in items for p in (r.chunk.populations or [])))
    if pops:
        meta.append("Population : " + ", ".join(pops))
    grades = _strengths([g for r in items for g in r.chunk.grade_levels])
    if grades:
        meta.append("Force/accord mentionnés : " + grades)
    lines.append(" | ".join(meta))
    return "\n".join(lines)


def legacy_header(label: str, items: list[RetrievedChunk]) -> str:
    c = items[0].chunk
    yr = str(c.effective_year) if c.effective_year else "Date N/A"
    ver = f" ({c.version_label})" if c.version_label else ""
    tag = "EN VIGUEUR" if c.is_latest_edition else f"ÉDITION ANTÉRIEURE — REMPLACÉE ({c.superseded_by})"
    grades = sorted({g for r in items for g in r.chunk.grade_levels})
    g = f" | Grades : {', '.join(grades)}" if grades else ""
    return (
        f"### [{label}] {c.doc_title} — {c.doc_type} SFAR {yr}{ver} [{tag}]\n"
        f"Section : {c.section_path or 'Général'} | Type : {c.chunk_type}{g}"
    )


def _passage_text(p: Passage, gen_cfg: GenerationConfig, query: str) -> str:
    parts = []
    prev_section = p.items[0].chunk.section_path
    for rc in p.items:
        c = rc.chunk
        body = c.text
        if gen_cfg.prune_prose and query:
            body = prune_verbose_prose(body, query=query, chunk_type=c.chunk_type)
        if gen_cfg.table_rendering == "rows_as_cards" and c.chunk_type in _TABLE_TYPES:
            body = markdown_table_as_rows(body)
        if c.section_path and c.section_path != prev_section:
            parts.append(f"(Section : {c.section_path})")
            prev_section = c.section_path
        parts.append(body.strip())
    return "\n".join(parts)


def _as_retrieved(p: Passage, text: str) -> RetrievedChunk:
    if len(p.items) == 1 and text == p.items[0].chunk.text:
        return p.items[0]
    best = max(p.items, key=lambda r: r.final_score)
    first = p.items[0]
    chunk = first.chunk.model_copy(
        update={
            "text": text,
            "indexed_text": "\n".join(r.chunk.indexed_text for r in p.items),
            "chunk_id": "+".join(r.chunk.chunk_id for r in p.items),
            "grade_levels": list(dict.fromkeys(g for r in p.items for g in r.chunk.grade_levels)),
        }
    )
    return best.model_copy(update={"chunk": chunk, "is_expanded_context": all(r.is_expanded_context for r in p.items)})


def assemble_context(
    retrieved: list[RetrievedChunk], gen_cfg: GenerationConfig, query: str = ""
) -> tuple[list[RetrievedChunk], str]:
    """Structured context: returns (passages in [S1..Sn] order, context block)."""
    chunks = select_within_budget(retrieved, gen_cfg.max_context_chunks, gen_cfg.max_context_chars)
    if gen_cfg.table_rendering == "drop_covered_cards":
        chunks = drop_covered_cards(chunks)
    if gen_cfg.merge_adjacent:
        passages = merge_adjacent_chunks(chunks)
    else:
        seen = set()
        passages = []
        for i, rc in enumerate(chunks):
            if rc.chunk.chunk_id not in seen:
                seen.add(rc.chunk.chunk_id)
                passages.append(Passage([rc], i))
    passages = order_passages(passages, gen_cfg.context_order)
    header = rich_header if gen_cfg.source_header == "rich" else legacy_header
    blocks = []
    out: list[RetrievedChunk] = []
    for n, p in enumerate(passages, start=1):
        text = _passage_text(p, gen_cfg, query)
        blocks.append(f"{header(f'S{n}', p.items)}\n{text}")
        out.append(_as_retrieved(p, text))
    return out, "\n\n---\n\n".join(blocks)
