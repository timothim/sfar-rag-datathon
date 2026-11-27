"""Multi-strategy chunker for SFAR clinical recommendations.

Supports three cleanly separated strategies for rigorous scientific ablation:
1. `naive_fixed`: Sliding character window on raw Markdown/HTML (standard baseline).
2. `hierarchical_markdown`: Section-aware Markdown splitter with bibliography tagging.
3. `table_aware_sota`: Full SOTA clinical chunker combining:
   - Smart heading breadcrumb hierarchy (filtering OCR false headings)
   - Bibliography (`Références`) isolation (removes ~24% retrieval noise)
   - Native HTML <table> parsing with rowspan/colspan resolution, cross-page continuation
     header inheritance, Markdown table chunks + self-contained Clinical Row-Group Cards
   - GRADE & Recommendation ID extraction (`R1.1`, `GRADE 1+`, `Avis d'experts`)
   - Contextual Header Prepending (Anthropic Contextual Retrieval pattern)
   - Section-Anchored Callout Linking (automatically links each specialty's
     "En cas d'allergie aux bêtalactamines" box & footnotes to every chunk in that section!)
"""

from __future__ import annotations

import collections
import hashlib
import re
import unicodedata
from typing import Literal

from dataclasses import dataclass

from rag_sfar.ingestion.loader import LoadedDocument
from rag_sfar.ingestion.population import infer_chunk_populations, legacy_hint_from_populations
from rag_sfar.ingestion.table_parser import ParsedTable, parse_html_table
from rag_sfar.ingestion.text_cleaning import NulRepairer, clean_chunk_text
from rag_sfar.schemas import Chunk, ChunkType, DocumentMetadata, PopulationScope

ChunkingStrategy = Literal["naive_fixed", "hierarchical_markdown", "table_aware_sota"]

# Corpus-level table counters filled by the table_aware_sota chunker (diagnostics only:
# read by scripts/ingestion_structural_checks.py, never by retrieval).
TABLE_STATS: collections.Counter = collections.Counter()

# Patterns for clinical annotations
GRADE_RE = re.compile(
    r"\b(?:GRADE\s*[12]\s*[+\-]?|Avis\s+d['’]experts?|Accord\s+(?:FORT|FAIBLE|fort|faible)|"
    r"Recommandation\s+(?:forte|faible))\b",
    re.I,
)
REC_ID_RE = re.compile(r"\bR\d+(?:\.\d+){1,2}\b")
# A table/footnote note: starts with a note call (`*`, `**`, `***` followed by a space or text,
# `#`, `†`, `‡`, optionally Markdown-escaped) or "Note :" / "NB :". Markdown bold ("**R1.1",
# "**Céfazoline**") is not a note call: a run of two or more stars glued to a word is excluded.
FOOTNOTE_START_RE = re.compile(r"^\s*(?:\\?\*(?:\\?\*){0,2}\s|\\?\*(?![\*\s])|\\?[#†‡]|Note\s*:|NB\s*:)", re.I)
# A short paragraph that comments on the adjacent table ("Les posologies de ce tableau ...").
TABLE_NOTE_RE = re.compile(r"^.{0,160}\b(?:de|dans|du)\s+ce\s+tableau\b", re.I | re.S)
REF_HEADING_RE = re.compile(r"\b(r[eé]f[eé]rences?|bibliographie)\b", re.I)
ALLERGY_BOX_RE = re.compile(
    r"(?:en\s+cas\s+d['’]allergie\s+aux\s+b[êe]talactamines,\s*si\s+antibioprophylaxie\s+indiqu[ée]e|"
    r"^#?\s*si\s+allergie\s+aux\s+(?:p[ée]nicillines|b[êe]talactamines)|"
    r"en\s+cas\s+de\s+chirurgie\s+proth[ée]tique.*allergie\s+aux\s+b[êe]talactamines|"
    r"en\s+cas\s+d['’]allergie\s+(?:vraie\s+|av[ée]r[ée]e\s+)?aux\s+b[êe]talactamines\s*:)",
    re.I | re.M,
)
DOSAGE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mg/kg|mg|g|UI|µg|mcg|mL|IVL|IV|PO|J-\d+|h\b|heures?)\b",
    re.I,
)
PEDIATRIC_RE = re.compile(
    r"\b(p[ée]diatri\w*|enfant\w*|nourrisson\w*|n[ée]onatal\w*|nouveau[- ]n[ée])\b",
    re.I,
)
ADULT_RE = re.compile(r"\b(adulte\w*)\b", re.I)

# Patterns that unambiguously mark the START of real clinical content (auto-exiting a
# preceding `#### Références` block when Chandra omitted a new markdown heading!)
EXIT_REF_LINE_RE = re.compile(
    r"^\s*(?:\*\*)?(?:Question\s*(?:\d+\s*)?[:\-–]|R\d+\.\d+(?:\.\d+)?\s*[–\-:]|"
    r"Recommandation\s+\d|Argumentaire\s*[:\-–]?|CHAMP\s+\d|PARTIE\s+\d|"
    r"Tableau\s+\d|Facteurs?\s+de\s+risque|Traitement\s+probabiliste)",
    re.I,
)
CLINICAL_CONTENT_RE = re.compile(
    r"(?:\bR\d+\.\d+(?:\.\d+)?\s*[–\-:]|il\s+est\s+(?:probablement\s+)?recommand[ée]|"
    r"il\s+n['’]est\s+pas\s+recommand[ée]|les\s+experts\s+sugg[èe]rent|"
    r"\bGRADE\s*[12]\s*[+\-]?|\bAvis\s+d['’]experts?|\bposologie\b|\bmg/kg\b)",
    re.I,
)
BIBLIO_LINE_RE = re.compile(
    r"(?:^\s*(?:\[\d+\]|\d+\.\s+[A-Z][a-z]+\s+[A-Z]{1,3}\b)|et\s+al\.|\bdoi[:\s]|"
    r"\b(?:19|20)\d{2}\s*;\s*\d+\s*(?:\(\d+\))?\s*:)",
    re.I | re.M,
)


def _is_truly_reference_text(text: str) -> bool:
    """Confirm a passage under a `Références` heading is genuinely bibliographic noise
    and NOT a clinical recommendation whose heading was omitted by OCR."""
    if CLINICAL_CONTENT_RE.search(text):
        # Double-check it isn't just a paper title containing a word; count bibliographic markers
        bib_hits = len(BIBLIO_LINE_RE.findall(text))
        if bib_hits < 3:
            return False
    return True


def _extract_grades(text: str) -> list[str]:
    found = []
    for m in GRADE_RE.finditer(text):
        val = re.sub(r"\s+", " ", m.group(0)).strip()
        if val not in found:
            found.append(val)
    return found[:8]


def _extract_rec_ids(text: str) -> list[str]:
    found = []
    for m in REC_ID_RE.finditer(text):
        val = m.group(0)
        if val not in found:
            found.append(val)
    return found[:10]


def _infer_chunk_population(
    section_path: str, text: str, doc_pop: PopulationScope
) -> PopulationScope:
    sec_low = section_path.lower()
    if PEDIATRIC_RE.search(sec_low):
        return "pediatrie"
    if ADULT_RE.search(sec_low) and not PEDIATRIC_RE.search(sec_low):
        return "adulte"
    if doc_pop in ("adulte", "pediatrie"):
        return doc_pop
    has_ped = bool(PEDIATRIC_RE.search(text[:800]))
    has_adult = bool(ADULT_RE.search(text[:800]))
    if has_ped and not has_adult:
        return "pediatrie"
    if has_adult and not has_ped:
        return "adulte"
    return doc_pop


@dataclass
class ChunkOptions:
    """Options of the table_aware_sota chunker (defaults = recommended configuration).

    - clean_ocr: deterministic OCR clean-up of chunk text (text_cleaning.clean_chunk_text);
    - hard_max_chars: hard cap of a prose piece (0 = no cap): a sentence or list longer than the
      prose budget is cut on line, then word boundaries;
    - header_domains: "all" (legacy: every imputed domain), "declared" (only the source
      sub-domain) or "none" in the indexed context header;
    - header_status: always state the edition status in the header ("en vigueur" /
      "remplacée par l'édition AAAA" / "abrogée"), not only for superseded editions;
    - population_hint: "legacy" (section path, then document scope, then the first 800
      characters of text) or "structural" (from ingestion/population.py);
    - reco_units: add one `recommendation_unit` chunk per primary graded recommendation;
    - table_cards_min_cols: minimum width of a table that gets row cards (legacy: 3)."""

    clean_ocr: bool = True
    hard_max_chars: int = 2400
    # Measured on dev (B2): removing the domains and stating "[en vigueur]" did not help
    # (multirfe passage hit with windows -3.9 pts [-9.2 ; 0]), so the legacy header is kept.
    header_domains: str = "all"
    header_status: bool = False
    population_hint: str = "legacy"
    # Recommendation units were neutral on dev (B2): off by default, available for tests.
    reco_units: bool = False
    table_cards_min_cols: int = 2


LEGACY_HEADER = ChunkOptions()


def _build_context_header(
    meta: DocumentMetadata, section_path: str, chunk_type: ChunkType, opts: ChunkOptions | None = None
) -> str:
    opts = opts or LEGACY_HEADER
    yr = str(meta.effective_year) if meta.effective_year else "Date non précisée"
    ver = f" {meta.version_label}" if meta.version_label else ""
    if not meta.is_active:
        status = " [ABROGÉE]"
    elif not meta.is_latest_edition:
        status = f" [ÉDITION ANTÉRIEURE — REMPLACÉE EN {meta.superseded_by_year}]"
    else:
        status = " [en vigueur]" if opts.header_status else ""
    if opts.header_domains == "all":
        doms = f" | Domaines : {', '.join(meta.domains[:3])}"
    elif opts.header_domains == "declared" and meta.raw_subdomain:
        doms = f" | Domaines : {meta.raw_subdomain}"
    else:
        doms = ""
    sec = f" | Section : {section_path}" if section_path else ""
    kind = " | Tableau structuré" if chunk_type in ("table_markdown", "table_row_card") else ""
    if chunk_type == "recommendation_unit":
        kind = " | Recommandation cotée"
    return f"[{meta.doc_type} SFAR {yr}{ver}{status} | {meta.title}{doms}{sec}{kind}]"


def _make_chunk(
    meta: DocumentMetadata,
    chunk_index: int,
    text: str,
    section_path: str,
    section_id: str,
    chunk_type: ChunkType,
    is_ref: bool = False,
    prepend_context: bool = True,
    opts: ChunkOptions | None = None,
    table_scope: str = "",
    nul_repairer: NulRepairer | None = None,
) -> Chunk:
    """Build one chunk. Without `opts` (naive / hierarchical strategies) the legacy behaviour
    is kept: no OCR clean-up, legacy header and legacy population hint."""
    clean_text = text.strip()
    if opts is not None and opts.clean_ocr:
        clean_text = clean_chunk_text(clean_text, nul_repairer)
    header = _build_context_header(meta, section_path, chunk_type, opts) if prepend_context else ""
    indexed_text = f"{header}\n{clean_text}" if header else clean_text

    cid_hash = hashlib.md5(f"{meta.doc_id}:{chunk_index}:{clean_text[:80]}".encode("utf-8")).hexdigest()[:8]
    chunk_id = f"{meta.doc_id}__c{chunk_index:04d}_{cid_hash}"

    pops, pop_src = infer_chunk_populations(section_path, table_scope, meta.title)
    if opts is not None and opts.population_hint == "structural":
        pop_hint = legacy_hint_from_populations(pops)
    else:
        pop_hint = _infer_chunk_population(section_path, clean_text, meta.population_scope)
    return Chunk(
        chunk_id=chunk_id,
        doc_id=meta.doc_id,
        chunk_index=chunk_index,
        chunk_type=chunk_type,
        section_path=section_path,
        section_id=section_id,
        text=clean_text,
        indexed_text=indexed_text,
        grade_levels=_extract_grades(clean_text),
        recommendation_ids=_extract_rec_ids(clean_text),
        population_hint=pop_hint,
        populations=pops,
        population_source=pop_src,
        is_reference_section=is_ref,
        has_allergy_info=bool(re.search(r"allerg", clean_text, re.I)),
        has_dosage_info=bool(DOSAGE_RE.search(clean_text)),
        parent_section_id=section_id,
        doc_title=meta.title,
        doc_type=meta.doc_type,
        effective_year=meta.effective_year,
        version_label=meta.version_label,
        domains=list(meta.domains),
        language=meta.language,
        doc_role=meta.doc_role,
        reco_family_id=meta.reco_family_id,
        topic_lineage=meta.topic_lineage,
        is_active=meta.is_active,
        is_latest_edition=meta.is_latest_edition,
        superseded_by=meta.superseded_by,
        setting_scope=meta.setting_scope,
        landing_url=meta.landing_url,
        filename=meta.filename,
    )


def _refresh_indexed_text(c: Chunk, meta: DocumentMetadata, opts: ChunkOptions | None) -> None:
    header = _build_context_header(meta, c.section_path, c.chunk_type, opts)
    c.indexed_text = f"{header}\n{c.text}"
    c.has_dosage_info = bool(DOSAGE_RE.search(c.text))
    c.grade_levels = _extract_grades(c.text)


def _link_neighbors(chunks: list[Chunk]) -> None:
    for i, c in enumerate(chunks):
        if i > 0 and chunks[i - 1].doc_id == c.doc_id and not chunks[i - 1].is_reference_section:
            c.prev_chunk_id = chunks[i - 1].chunk_id
        if i + 1 < len(chunks) and chunks[i + 1].doc_id == c.doc_id and not chunks[i + 1].is_reference_section:
            c.next_chunk_id = chunks[i + 1].chunk_id


def _chunk_naive_fixed(
    doc: LoadedDocument, chunk_size: int = 1200, overlap: int = 200
) -> list[Chunk]:
    """Baseline 0: classic fixed-size sliding window over raw text (no HTML table parsing,
    no heading tracking, no bibliography filtering)."""
    text = doc.text
    meta = doc.metadata
    chunks: list[Chunk] = []
    start = 0
    idx = 0
    step = max(200, chunk_size - overlap)
    while start < len(text):
        piece = text[start : start + chunk_size].strip()
        if len(piece) >= 40:
            chunks.append(
                _make_chunk(
                    meta=meta,
                    chunk_index=idx,
                    text=piece,
                    section_path="",
                    section_id=f"{meta.doc_id}__root",
                    chunk_type="prose",
                    is_ref=False,
                    prepend_context=False,
                )
            )
            idx += 1
        start += step
    _link_neighbors(chunks)
    return chunks


def _is_valid_heading(level: int, title_text: str) -> bool:
    """Filter out Chandra OCR false headings (e.g., stray bold sentences, footnote `#`, HTML tags)."""
    clean = re.sub(r"[\*_`]", "", title_text).strip()
    if not clean or len(clean) > 220 or "</td>" in clean.lower():
        return False
    if re.fullmatch(r"[\d\W]+", clean):
        return False
    if level == 1 and clean.lower().startswith(
        ("si allergie", "en cas d", "la demi-vie", "pas d'indication", "pas d’indication")
    ):
        return False
    return True


def _semantic_heading_level(
    raw_level: int, htext: str, has_champ_or_partie: bool = False
) -> int:
    """Normalize inconsistent OCR heading levels (e.g., CHAMP=1, PARTIE=2) so
    sub-specialties emitted as `# H1` never evict `CHAMP 2` or swallow `PARTIE 7`."""
    up = htext.strip().upper()
    if re.match(r"^CHAMP\s+\d+", up):
        return 1
    if re.match(r"^HISTORIQUE\s+DES\s+VERSIONS", up):
        return 1
    if re.match(r"^INTRODUCTION\b", up) and raw_level <= 2:
        return 1
    if re.match(r"^PARTIE\s+\d+", up):
        return 2
    if has_champ_or_partie:
        return max(3, raw_level)
    return raw_level


def _clean_heading_text(raw_heading: str) -> tuple[int, str]:
    m = re.match(r"^(#{1,6})\s+(.*)$", raw_heading.strip())
    if not m:
        return 0, raw_heading.strip()
    level = len(m.group(1))
    title = re.sub(r"[\*_`]+", "", m.group(2)).strip()
    title = re.sub(r"\s+", " ", title)
    return level, title


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Cut a piece longer than `max_chars` on line boundaries, then on word boundaries."""
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    buf = ""
    for line in text.split("\n"):
        while len(line) > max_chars:
            cut = line.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            head, line = line[:cut].rstrip(), line[cut:].lstrip()
            if buf:
                out.append(buf)
                buf = ""
            out.append(head)
        if buf and len(buf) + len(line) + 1 > max_chars:
            out.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf.strip():
        out.append(buf)
    return [x for x in out if x.strip()]


def _split_prose_paragraphs(
    text: str, max_chars: int = 1200, overlap_chars: int = 180, hard_max_chars: int = 0
) -> list[str]:
    """Split prose cleanly along paragraph / sentence boundaries with gentle overlap.

    With `hard_max_chars` > 0, any piece still longer (a sentence without punctuation, a long
    list, a flowchart) is cut on line, then word boundaries."""
    pieces = _split_prose_paragraphs_soft(text, max_chars, overlap_chars)
    if hard_max_chars <= 0:
        return pieces
    out: list[str] = []
    for p in pieces:
        out.extend(_hard_split(p, hard_max_chars))
    return [x for x in out if len(x.strip()) >= 35]


def _split_prose_paragraphs_soft(text: str, max_chars: int = 1200, overlap_chars: int = 180) -> list[str]:
    """Split prose cleanly along paragraph / sentence boundaries with gentle overlap."""
    # Remove markdown image links to logos/decorative figures while keeping alt text if informative
    text = re.sub(r"!\[(?:SFAR logo|SPILF logo|logo[^\]]*)\]\([^\)]+\)", "", text, flags=re.I)
    text = re.sub(r"!\[([^\]]{0,300})\]\([^\)]+\)", r"[Figure : \1]", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    buf: list[str] = []
    buf_len = 0

    for p in paras:
        if len(p) > max_chars:
            # Flush current buffer first
            if buf:
                out.append("\n\n".join(buf))
                buf = []
                buf_len = 0
            # Split long paragraph by sentence
            sents = re.split(r"(?<=[.!?;])\s+", p)
            s_buf: list[str] = []
            s_len = 0
            for s in sents:
                if s_buf and s_len + len(s) + 1 > max_chars:
                    out.append(" ".join(s_buf))
                    # Keep last sentence as overlap
                    tail = s_buf[-1] if len(s_buf[-1]) <= overlap_chars else ""
                    s_buf = [tail, s] if tail else [s]
                    s_len = sum(len(x) + 1 for x in s_buf)
                else:
                    s_buf.append(s)
                    s_len += len(s) + 1
            if s_buf:
                out.append(" ".join(s_buf))
            continue

        if buf and buf_len + len(p) + 2 > max_chars:
            out.append("\n\n".join(buf))
            # Soft overlap: carry last short paragraph if small enough
            carry = buf[-1] if len(buf[-1]) <= overlap_chars else ""
            buf = [carry, p] if carry else [p]
            buf_len = sum(len(x) + 2 for x in buf)
        else:
            buf.append(p)
            buf_len += len(p) + 2

    if buf:
        out.append("\n\n".join(buf))
    return [x for x in out if len(x.strip()) >= 35]


def _chunk_hierarchical_markdown(doc: LoadedDocument, max_chars: int = 1200) -> list[Chunk]:
    """Baseline 2: Heading-aware Markdown splitting + bibliography tagging, but without HTML
    table reconstruction or row-card generation."""
    meta = doc.metadata
    lines = doc.text.splitlines()
    heading_stack: list[tuple[int, str]] = []
    current_lines: list[str] = []
    sections: list[tuple[str, str, bool]] = []  # (section_path, body, is_ref)

    def _flush() -> None:
        body = "\n".join(current_lines).strip()
        if not body:
            return
        sec_path = " > ".join(h for _, h in heading_stack)
        is_ref = any(REF_HEADING_RE.search(h) for _, h in heading_stack[-2:])
        sections.append((sec_path, body, is_ref))

    for line in lines:
        if re.match(r"^#{1,6}\s+", line.strip()):
            lvl, htext = _clean_heading_text(line)
            if _is_valid_heading(lvl, htext):
                _flush()
                current_lines = []
                while heading_stack and heading_stack[-1][0] >= lvl:
                    heading_stack.pop()
                heading_stack.append((lvl, htext))
                continue
        current_lines.append(line)
    _flush()

    chunks: list[Chunk] = []
    idx = 0
    for s_idx, (sec_path, body, is_ref) in enumerate(sections):
        sec_id = f"{meta.doc_id}__sec{s_idx:03d}"
        # Strip raw HTML attributes to be fair, without structured table parsing
        clean_body = re.sub(r'\s+(?:data-bbox|style|border)="[^"]*"', "", body)
        for piece in _split_prose_paragraphs(clean_body, max_chars=max_chars):
            chunks.append(
                _make_chunk(
                    meta=meta,
                    chunk_index=idx,
                    text=piece,
                    section_path=sec_path,
                    section_id=sec_id,
                    chunk_type="references" if is_ref else "prose",
                    is_ref=is_ref,
                    prepend_context=True,
                )
            )
            idx += 1

    _link_neighbors(chunks)
    return chunks


_TABLE_TITLE_RE = re.compile(r"^\s*(?:\*\*)?\s*(?:Tableau|Table|Tab\.)\s*[\dIVXLC]+[a-z]?\b", re.I)
_BOLD_LINE_RE = re.compile(r"^\s*\*\*([^*]{3,200})\*\*\s*:?\s*$")
# Footnote call marks at the start of a note paragraph: "*", "**", "\\*\\*", "**\\*\\***", "†", "#".
# An unescaped run of "*" counts only when followed by a space ("* posologie ..."): "**Question"
# is Markdown bold, not a call mark. Escaped runs ("\\*\\*") may be wrapped in bold ("**\\*\\***").
_NOTE_MARK_RE = re.compile(
    r"^\s*(?:\*\*(?=\\\*))?(?:(?P<esc>(?:\\\*){1,5})(?:\*\*)?|(?P<mark>\*{1,5}(?=\s)|†{1,3}|‡{1,3}|§|#(?=\s)|¶))\s*"
)


def _table_title(prose_tail: str) -> str:
    """Caption of a table: the last non-empty line of the text right before it, when that line
    is a "Tableau N" caption or a short bold line."""
    line = prose_tail.strip().splitlines()[-1].strip() if prose_tail.strip() else ""
    if not line or line.startswith("#") or len(line) > 220:
        return ""
    if _TABLE_TITLE_RE.match(line):
        return re.sub(r"[\*_]+", "", line).strip()
    m = _BOLD_LINE_RE.match(line)
    if m:
        return m.group(1).strip()
    return ""


def _scope_note_text(piece: str, max_chars: int = 400) -> str:
    """Scope note of the following table(s): the paragraph that says "... de ce tableau ...",
    plus the short paragraphs right after it (e.g. a maximal dose), up to `max_chars`."""
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", piece) if p.strip()]
    if not paras or len(paras[0]) > max_chars:
        return ""
    out = [paras[0]]
    for p in paras[1:3]:
        if p.startswith(("**", "#", "|")) or len(p) > 300 or len(" ".join(out)) + len(p) > max_chars:
            break
        out.append(p)
    return " ".join(out)


def _note_mark(paragraph: str) -> str | None:
    """Normalized call mark of a footnote paragraph ("*", "**", "†"...), else None."""
    m = _NOTE_MARK_RE.match(paragraph)
    if not m:
        return None
    mark = "*" * m.group("esc").count("*") if m.group("esc") else m.group("mark")
    rest = paragraph[m.end():].strip()
    if not rest or rest[:1] in "*":
        return None
    return mark


def _has_call(text: str, mark: str) -> bool:
    text = re.sub(r"\*\*[^*\n|]{2,200}?\*\*", " ", text)  # Markdown bold spans are not calls
    if set(mark) == {"*"}:
        return bool(re.search(rf"(?<![\*\w]){re.escape(mark)}(?![\*\w])|(?<=\w){re.escape(mark)}(?![\*\w])", text))
    return mark in text


def _chunk_table_aware_sota(
    doc: LoadedDocument,
    max_prose_chars: int = 1200,
    max_table_chars: int = 1800,
    emit_row_cards: bool = True,
    options: ChunkOptions | None = None,
    nul_repairer: NulRepairer | None = None,
    reco_units: list | None = None,
) -> list[Chunk]:
    """SOTA Clinical Chunker for SFAR guidelines.

    1. Isolates prose vs HTML <table> blocks inside each true section.
    2. Reconstructs every HTML <table> (rowspan/colspan, page-split continuations, sub-category
       banners, full-width note rows) and emits Markdown table chunks plus self-contained row
       cards (title, section, scope note, sub-category, column headers, linked footnotes).
    3. Tracks the major section (CHAMP / PARTIE) to link callouts (allergy boxes, notes) to the
       chunks of that section.
    4. Optionally cleans OCR residues, caps prose pieces and adds graded recommendation units.
    """
    opts = options or ChunkOptions()
    meta = doc.metadata
    text = doc.text
    if opts.clean_ocr and "\x00" in text:
        text = (nul_repairer or NulRepairer())(text)

    tokens = re.split(r"(<table\b.*?</table>)", text, flags=re.S | re.I)

    heading_stack: list[tuple[int, str]] = []
    current_major_section = "root"
    section_counter = 0

    def _current_sec_path() -> str:
        return " > ".join(h for _, h in heading_stack)

    def _is_ref_sec() -> bool:
        return any(REF_HEADING_RE.search(h) for _, h in heading_stack[-2:])

    def _update_major_section(lvl: int, htext: str) -> None:
        nonlocal current_major_section, section_counter
        if lvl <= 2 or re.match(r"^(?:PARTIE|CHAMP|ANTIBIOPROPHYLAXIE\s+EN)\b", htext, re.I):
            section_counter += 1
            current_major_section = f"{meta.doc_id}__maj{section_counter:03d}"

    chunks: list[Chunk] = []
    idx = 0
    last_table_headers: list[str] | None = None
    last_table_major_section: str = ""
    major_section_callouts: dict[str, list[str]] = {}
    major_section_chunks: dict[str, list[Chunk]] = {}
    # Table context carried between tokens
    prose_tail = ""  # text of the prose right before the current table (caption detection)
    last_table: ParsedTable | None = None
    last_table_section = ""
    # Scope note ("Les posologies de ce tableau concernent ...") and the heading path under
    # which it appeared: it applies to the following tables while that path stays open.
    scope_note: tuple[tuple[str, ...], str] | None = None
    note_targets: list[Chunk] = []  # table chunks waiting for their footnotes
    notes_seen_since_table = False
    modified: set[str] = set()
    table_counter = 0

    def _register_chunk(c: Chunk, major_sec: str, is_callout: bool = False) -> None:
        chunks.append(c)
        major_section_chunks.setdefault(major_sec, []).append(c)
        if is_callout:
            major_section_callouts.setdefault(major_sec, []).append(c.chunk_id)

    def _mk(text_: str, sec_path: str, ctype: ChunkType, is_ref: bool = False, table_scope: str = "") -> Chunk:
        nonlocal idx
        c = _make_chunk(
            meta=meta, chunk_index=idx, text=text_, section_path=sec_path,
            section_id=current_major_section, chunk_type=ctype, is_ref=is_ref,
            prepend_context=True, opts=opts, table_scope=table_scope, nul_repairer=nul_repairer,
        )
        idx += 1
        return c

    prev_table_contiguous = False
    for tok in tokens:
        if not tok or not tok.strip():
            continue
        is_table = tok.lstrip().lower().startswith("<table")
        if not is_table:
            prev_table_contiguous = False

        if is_table:
            while heading_stack and REF_HEADING_RE.search(heading_stack[-1][1]):
                heading_stack.pop()
            sec_path = _current_sec_path()
            if _is_ref_sec():
                # A table is never bibliography: keep it, without the "Références" level.
                sec_path = re.sub(r"\s*>\s*(?:R[ée]f[ée]rences?|Bibliographie)\b.*$", "", sec_path, flags=re.I)
                TABLE_STATS["tables_under_reference_heading"] += 1

            prev_hdrs = last_table_headers if last_table_major_section == current_major_section else None
            carry = None
            if (
                prev_table_contiguous
                and last_table is not None
                and last_table.row_groups
                and last_table_section == sec_path
            ):
                last_row = last_table.row_groups[-1].rows[-1]
                carry = last_row[0] if last_row and last_row[0].strip() else None
            parsed: ParsedTable = parse_html_table(
                tok,
                previous_headers=prev_hdrs,
                previous_is_contiguous=prev_table_contiguous,
                carry_first_cell=carry,
            )
            if parsed.num_cols and carry and len(last_table.headers or []) not in (0, parsed.num_cols) and last_table.num_cols != parsed.num_cols:
                # Different width: not the same table, undo the carry.
                parsed = parse_html_table(tok, previous_headers=prev_hdrs, previous_is_contiguous=prev_table_contiguous)
            is_continuation = prev_table_contiguous
            prev_table_contiguous = True
            if parsed.has_explicit_headers and parsed.headers:
                last_table_headers = parsed.headers
                last_table_major_section = current_major_section
            last_table = parsed
            last_table_section = sec_path
            if notes_seen_since_table:
                note_targets = []
                notes_seen_since_table = False
            if not is_continuation:
                table_counter += 1
            table_id = f"{meta.doc_id}__t{table_counter:03d}"

            hdr_blob = " ".join(parsed.headers).lower()
            is_procedure_table = any(
                k in hdr_blob for k in ("actes chirurgicaux", "interventionnels", "nomenclature", "procédure")
            )
            raw_table_plain = " ".join(" ".join(row) for g in parsed.row_groups for row in g.rows)
            prev_is_allergy_intro = (
                len(chunks) > 0
                and chunks[-1].parent_section_id == current_major_section
                and bool(ALLERGY_BOX_RE.search(chunks[-1].text))
                and len(chunks[-1].text) < 400
            )
            is_allergy_table = (not is_procedure_table) and (
                (prev_is_allergy_intro and parsed.num_rows <= 8)
                or (parsed.num_rows <= 6 and bool(ALLERGY_BOX_RE.search(raw_table_plain[:500])))
            )

            title = _table_title(prose_tail) if not is_continuation else ""
            cur_path = tuple(h for _, h in heading_stack)
            scope = scope_note[1] if scope_note and cur_path[: len(scope_note[0])] == scope_note[0] else ""
            banners = " ".join(dict.fromkeys(g.sub_banner for g in parsed.row_groups if g.sub_banner))
            md_chunks = parsed.to_markdown_chunks(max_chars=max_table_chars)
            md_prefix = "".join(
                f"{lab} : {val}\n" for lab, val in (("Tableau", title), ("Périmètre", scope)) if val
            )
            if md_prefix:
                md_chunks = [f"{md_prefix}{m}" for m in md_chunks]
            for md_t in md_chunks:
                ctype: ChunkType = "callout_allergy" if is_allergy_table else "table_markdown"
                c = _mk(md_t, sec_path, ctype, table_scope=" ".join(x for x in (scope, title) if x))
                c.table_id = table_id
                _register_chunk(c, current_major_section, is_callout=is_allergy_table)
                note_targets.append(c)

            n_before_cards = len(chunks)
            if emit_row_cards and not is_allergy_table and parsed.row_groups:
                section_tail = " > ".join(h for _, h in heading_stack[-2:])
                ctx_lines = [f"Périmètre : {scope}"] if scope else []
                cards = parsed.to_row_cards(
                    min_cols=opts.table_cards_min_cols,
                    title=title,
                    section=section_tail,
                    context_lines=ctx_lines,
                    require_headers=False,
                )
                for card, grp in zip(cards, [g for g in parsed.row_groups if g.rows]):
                    c = _mk(card, sec_path, "table_row_card", table_scope=" ".join(x for x in (scope, title, grp.sub_banner) if x))
                    c.table_id = table_id
                    _register_chunk(c, current_major_section, is_callout=False)
                    note_targets.append(c)
            n_cards = len(chunks) - n_before_cards
            TABLE_STATS["tables"] += 1
            TABLE_STATS["tables_ge2cols"] += parsed.num_cols >= 2
            TABLE_STATS["explicit_headers"] += parsed.has_explicit_headers
            TABLE_STATS["inherited_headers"] += parsed.inherited_headers
            TABLE_STATS["row_cards"] += n_cards
            TABLE_STATS["carried_first_cell"] += bool(parsed.carried_first_cell)
            TABLE_STATS["full_width_notes"] += len(parsed.table_notes) + sum(len(g.notes) for g in parsed.row_groups)
            TABLE_STATS["titled"] += bool(title)
            TABLE_STATS["with_scope_note"] += bool(scope)
            if parsed.num_cols >= 2 and n_cards == 0 and not is_allergy_table:
                TABLE_STATS["ge2cols_without_cards"] += 1
                if not parsed.has_headers:
                    TABLE_STATS["ge2cols_headerless_without_cards"] += 1
            prose_tail = ""
            continue

        # Prose token: walk line by line to update headings and emit prose chunks
        prose_tail = tok
        lines = tok.splitlines()
        buf_lines: list[str] = []

        def _flush_prose() -> None:
            nonlocal notes_seen_since_table, scope_note
            body = "\n".join(buf_lines).strip()
            if not body:
                return
            if opts.clean_ocr:
                body = clean_chunk_text(body, nul_repairer)
            sec_path = _current_sec_path()
            is_ref = _is_ref_sec()
            if is_ref:
                for piece in _split_prose_paragraphs(body, max_chars=2000, hard_max_chars=opts.hard_max_chars):
                    if _is_truly_reference_text(piece):
                        chunks.append(_mk(piece, sec_path, "references", is_ref=True))
                    else:
                        is_rec_box = bool(REC_ID_RE.search(piece) and GRADE_RE.search(piece))
                        c = _mk(
                            piece,
                            re.sub(r"\s*>\s*R[ée]f[ée]rences.*$", "", sec_path, flags=re.I),
                            "recommendation_box" if is_rec_box else "prose",
                        )
                        _register_chunk(c, current_major_section, is_callout=False)
                return

            eff_max_chars = 3500 if "historique des versions" in sec_path.lower() else max_prose_chars
            hard = max(opts.hard_max_chars, eff_max_chars + 500) if opts.hard_max_chars else 0
            for piece in _split_prose_paragraphs(body, max_chars=eff_max_chars, hard_max_chars=hard):
                allergy_m = ALLERGY_BOX_RE.search(piece)
                if allergy_m and allergy_m.start() > 60:
                    sub_pieces = [p for p in (piece[: allergy_m.start()].strip(), piece[allergy_m.start():].strip()) if p]
                else:
                    sub_pieces = [piece]
                for sub in sub_pieces:
                    is_allergy_box = bool(ALLERGY_BOX_RE.search(sub))
                    is_rec_box = bool(REC_ID_RE.search(sub) and GRADE_RE.search(sub))
                    is_footnote = (
                        not is_rec_box
                        and not is_allergy_box
                        and len(sub) < 900
                        and bool(FOOTNOTE_START_RE.match(sub) or TABLE_NOTE_RE.match(sub))
                    )
                    if is_allergy_box:
                        ctype: ChunkType = "callout_allergy"
                    elif is_rec_box:
                        ctype = "recommendation_box"
                    elif is_footnote:
                        ctype = "callout_footnote"
                    else:
                        ctype = "prose"
                    # Scope note of the following tables ("Les posologies de ce tableau ...")
                    scope_txt = ""
                    if not is_allergy_box and TABLE_NOTE_RE.match(sub) and not FOOTNOTE_START_RE.match(sub):
                        scope_txt = _scope_note_text(sub)
                        if scope_txt:
                            scope_note = (tuple(h for _, h in heading_stack), scope_txt)
                    c = _mk(sub, sec_path, ctype, table_scope=scope_txt)
                    _register_chunk(c, current_major_section, is_callout=(is_allergy_box or is_footnote))
                    # Footnotes of the preceding table(s): append to the chunks that call them.
                    for para in re.split(r"\n\s*\n|\n(?=\s*(?:\\?\*|†|‡|#\s))", sub):
                        mark = _note_mark(para)
                        if not mark or not note_targets:
                            continue
                        note_txt = re.sub(r"\s+", " ", _NOTE_MARK_RE.sub("", para, count=1)).strip()
                        note_txt = re.sub(r"\*\*$", "", note_txt).strip()
                        if len(note_txt) < 8:
                            continue
                        if len(note_txt) > 500:
                            note_txt = note_txt[:500].rsplit(" ", 1)[0] + " […]"
                        for t in note_targets:
                            if _has_call(t.text.split("\nNote (")[0], mark) and f"Note ({mark})" not in t.text:
                                t.text = f"{t.text}\nNote ({mark}) : {note_txt}"
                                modified.add(t.chunk_id)
                        notes_seen_since_table = True
                        TABLE_STATS["footnotes_linked"] += 1

        for line in lines:
            if _is_ref_sec() and EXIT_REF_LINE_RE.match(line):
                _flush_prose()
                buf_lines = []
                while heading_stack and REF_HEADING_RE.search(heading_stack[-1][1]):
                    heading_stack.pop()
            if re.match(r"^#{1,6}\s+", line.strip()):
                lvl, htext = _clean_heading_text(line)
                if _is_valid_heading(lvl, htext):
                    _flush_prose()
                    buf_lines = []
                    has_cp = any(re.match(r"^(?:CHAMP|PARTIE)\s+\d+", h.upper()) for _, h in heading_stack)
                    sem_lvl = _semantic_heading_level(lvl, htext, has_champ_or_partie=has_cp)
                    while heading_stack and heading_stack[-1][0] >= sem_lvl:
                        heading_stack.pop()
                    heading_stack.append((sem_lvl, htext))
                    prev_major = current_major_section
                    _update_major_section(sem_lvl, htext)
                    if current_major_section != last_table_major_section:
                        last_table_headers = None
                    if current_major_section != prev_major:
                        note_targets = []
                    continue
            buf_lines.append(line)
        _flush_prose()

    for c in chunks:
        if c.chunk_id in modified:
            _refresh_indexed_text(c, meta, opts)

    # Link section-anchored allergy/footnote callouts to every chunk in that major section
    chunk_by_id = {c.chunk_id: c for c in chunks}
    for major_sec, callout_ids in major_section_callouts.items():
        if not callout_ids:
            continue
        allergy_cids = [cid for cid in callout_ids if chunk_by_id[cid].chunk_type == "callout_allergy"]
        other_cids = [cid for cid in callout_ids if chunk_by_id[cid].chunk_type != "callout_allergy"]
        linked = allergy_cids[:2] + other_cids[:2]
        for c in major_section_chunks.get(major_sec, []):
            if c.chunk_id not in linked:
                c.linked_callout_ids = list(linked)

    _link_neighbors(chunks)
    if opts.reco_units and reco_units:
        chunks.extend(_recommendation_unit_chunks(doc, chunks, reco_units, opts, start_index=idx))
    return chunks


def _norm_words(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", t))


def _recommendation_unit_chunks(
    doc: LoadedDocument, chunks: list[Chunk], units: list, opts: ChunkOptions, start_index: int
) -> list[Chunk]:
    """One `recommendation_unit` chunk per primary graded recommendation of the document.

    Text = section context (champ, question, heading) + label + statement + rating. The unit is
    placed outside the reading-order chain: its `prev_chunk_id` is the chunk that contains the
    statement in the flow (so a ±1 context window brings back the surrounding text) and its
    `next_chunk_id` is that chunk's successor."""
    meta = doc.metadata
    flow = [c for c in chunks if not c.is_reference_section]
    flow_norm = [(c, _norm_words(c.text)) for c in flow]
    out: list[Chunk] = []
    idx = start_index
    for u in units:
        stmt = (u.statement or "").strip()
        if len(stmt) < 25:
            continue
        key = _norm_words(stmt)[:120]
        src = next((c for c, n in flow_norm if key and key in n), None)
        if src is None:
            key2 = _norm_words(stmt)[:60]
            src = next((c for c, n in flow_norm if key2 and key2 in n), None)
        ctx = [x for x in (u.field, u.section, u.heading) if x]
        lines = []
        if ctx:
            lines.append("Contexte : " + " > ".join(dict.fromkeys(ctx)))
        label = f"{u.reco_label} – " if u.reco_label else ""
        lines.append(f"Recommandation : {label}{stmt}")
        rating = []
        if u.strength_raw:
            rating.append(u.strength_raw.strip())
        elif u.strength and u.strength != "unknown":
            rating.append(u.strength)
        if u.agreement_raw and (not u.strength_raw or u.agreement_raw.lower() not in u.strength_raw.lower()):
            rating.append(u.agreement_raw.strip())
        if rating:
            lines.append("Cotation : " + " ; ".join(rating))
        sec_path = src.section_path if src is not None else " > ".join(x for x in (u.field, u.heading) if x)
        c = _make_chunk(
            meta=meta, chunk_index=idx, text="\n".join(lines), section_path=sec_path,
            section_id=src.section_id if src is not None else f"{meta.doc_id}__reco",
            chunk_type="recommendation_unit", prepend_context=True, opts=opts,
        )
        idx += 1
        c.source_chunk_id = src.chunk_id if src is not None else None
        c.prev_chunk_id = src.chunk_id if src is not None else None
        c.next_chunk_id = src.next_chunk_id if src is not None else None
        if src is not None:
            c.populations, c.population_source = list(src.populations), src.population_source
            c.population_hint = src.population_hint
        c.reco_strength = u.strength or ""
        c.reco_strength_raw = u.strength_raw or ""
        c.reco_agreement = u.agreement or ""
        c.reco_label = u.reco_label or ""
        out.append(c)
    return out


def chunk_document(
    doc: LoadedDocument,
    strategy: ChunkingStrategy = "table_aware_sota",
    **kwargs,
) -> list[Chunk]:
    """Chunk a single LoadedDocument using the requested strategy."""
    if strategy == "naive_fixed":
        return _chunk_naive_fixed(doc, **kwargs)
    if strategy == "hierarchical_markdown":
        return _chunk_hierarchical_markdown(doc, **kwargs)
    if strategy == "table_aware_sota":
        return _chunk_table_aware_sota(doc, **kwargs)
    raise ValueError(f"Unknown chunking strategy: {strategy}")


def chunk_corpus(
    docs: list[LoadedDocument],
    strategy: ChunkingStrategy = "table_aware_sota",
    options: ChunkOptions | None = None,
    **kwargs,
) -> list[Chunk]:
    """Chunk all documents in a loaded SFAR corpus.

    For `table_aware_sota`, `options` (ChunkOptions) selects the clean-up, header and unit
    behaviour; graded recommendation units are extracted here for the whole corpus so that
    duplicates across the parts of one edition (short / long text) are indexed once."""
    all_chunks: list[Chunk] = []
    if strategy != "table_aware_sota":
        for d in docs:
            all_chunks.extend(chunk_document(d, strategy=strategy, **kwargs))
        return all_chunks
    opts = options or ChunkOptions()
    repairer = NulRepairer([d.text for d in docs]) if opts.clean_ocr else None
    units_by_doc: dict[str, list] = {}
    if opts.reco_units:
        units_by_doc = _extract_units_by_doc(docs)
    for d in docs:
        all_chunks.extend(
            _chunk_table_aware_sota(
                d, options=opts, nul_repairer=repairer, reco_units=units_by_doc.get(d.metadata.doc_id), **kwargs
            )
        )
    return all_chunks


def _extract_units_by_doc(docs: list[LoadedDocument]) -> dict[str, list]:
    """Primary graded recommendation units (reco_extractor) of the French documents."""
    from rag_sfar.ingestion import reco_extractor as rx

    units: list = []
    by_id: dict[str, dict] = {}
    for d in docs:
        m = d.metadata
        if m.language not in ("fr", "bilingual") or m.doc_role == "traduction_en":
            continue
        dd = m.model_dump()
        by_id[m.doc_id] = dd
        units.extend(rx.extract_recommendations(d.text, dd))
    rx.mark_cross_document_duplicates(units, by_id)
    out: dict[str, list] = collections.defaultdict(list)
    for u in units:
        if u.duplicate_of is None:
            out[u.doc_id].append(u)
    return out
