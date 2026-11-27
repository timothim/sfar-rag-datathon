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

import hashlib
import re
from typing import Literal

from rag_sfar.ingestion.loader import LoadedDocument
from rag_sfar.ingestion.table_parser import ParsedTable, parse_html_table
from rag_sfar.schemas import Chunk, ChunkType, DocumentMetadata, PopulationScope

ChunkingStrategy = Literal["naive_fixed", "hierarchical_markdown", "table_aware_sota"]

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


def _build_context_header(meta: DocumentMetadata, section_path: str, chunk_type: ChunkType) -> str:
    yr = str(meta.effective_year) if meta.effective_year else "Date non précisée"
    ver = f" {meta.version_label}" if meta.version_label else ""
    doms = ", ".join(meta.domains[:3])
    status = "" if meta.is_latest_edition else f" [ÉDITION ANTÉRIEURE — REMPLACÉE EN {meta.superseded_by_year}]"
    sec = f" | Section : {section_path}" if section_path else ""
    kind = " | Tableau structuré" if chunk_type in ("table_markdown", "table_row_card") else ""
    return f"[{meta.doc_type} SFAR {yr}{ver}{status} | {meta.title} | Domaines : {doms}{sec}{kind}]"


def _make_chunk(
    meta: DocumentMetadata,
    chunk_index: int,
    text: str,
    section_path: str,
    section_id: str,
    chunk_type: ChunkType,
    is_ref: bool = False,
    prepend_context: bool = True,
) -> Chunk:
    clean_text = text.strip()
    header = _build_context_header(meta, section_path, chunk_type) if prepend_context else ""
    indexed_text = f"{header}\n{clean_text}" if header else clean_text

    cid_hash = hashlib.md5(f"{meta.doc_id}:{chunk_index}:{clean_text[:80]}".encode("utf-8")).hexdigest()[:8]
    chunk_id = f"{meta.doc_id}__c{chunk_index:04d}_{cid_hash}"

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


def _split_prose_paragraphs(text: str, max_chars: int = 1200, overlap_chars: int = 180) -> list[str]:
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


def _chunk_table_aware_sota(
    doc: LoadedDocument,
    max_prose_chars: int = 1200,
    max_table_chars: int = 1800,
    emit_row_cards: bool = True,
) -> list[Chunk]:
    """SOTA Clinical Chunker for SFAR guidelines.

    Key innovations:
    1. Isolates prose vs HTML <table> blocks inside each true section.
    2. Reconstructs EVERY HTML <table> (rowspan/colspan + headerless cross-page continuation
       header propagation + sub-header banners).
    3. Emits BOTH Markdown table chunks AND atomic Row-Group Cards for multi-column clinical
       tables (so lookup questions & rowspan allergy alternatives hit near-100% recall).
    4. Tracks specialty/parent section scope (e.g. `PARTIE 7 : CHIRURGIE ORTHOPÉDIQUE`) and
       automatically links any Allergy/Alternative callout box in that section to EVERY table
       chunk in that specialty (solving the Specialty Allergy-Box Split-Chunk Problem!).
    """
    meta = doc.metadata
    text = doc.text

    # Step 1: Parse document into structural sections while preserving HTML tables intact.
    # First tokenize into HTML tables vs non-table text so headings inside tables never break state.
    tokens = re.split(r"(<table\b.*?</table>)", text, flags=re.S | re.I)

    # Walk tokens, tracking heading stack and specialty/major section anchor
    heading_stack: list[tuple[int, str]] = []
    current_major_section = "root"
    section_counter = 0

    def _current_sec_path() -> str:
        return " > ".join(h for _, h in heading_stack)

    def _is_ref_sec() -> bool:
        return any(REF_HEADING_RE.search(h) for _, h in heading_stack[-2:])

    def _update_major_section(lvl: int, htext: str) -> None:
        nonlocal current_major_section, section_counter
        # Major clinical specialty divisions (CHAMP = 1, PARTIE = 2, or explicit ANTIBIOPROPHYLAXIE EN ...).
        # NEVER reset major section on lvl>=3 subheadings like "### Chirurgie carcinologique" inside a PARTIE,
        # otherwise child surgical tables lose their link to the parent specialty allergy box!
        if lvl <= 2 or re.match(r"^(?:PARTIE|CHAMP|ANTIBIOPROPHYLAXIE\s+EN)\b", htext, re.I):
            section_counter += 1
            current_major_section = f"{meta.doc_id}__maj{section_counter:03d}"

    chunks: list[Chunk] = []
    idx = 0
    last_table_headers: list[str] | None = None
    last_table_major_section: str = ""
    # Map major_section_id -> list of callout chunk indices (allergy boxes, key footnotes)
    major_section_callouts: dict[str, list[str]] = {}
    major_section_chunks: dict[str, list[Chunk]] = {}

    def _register_chunk(c: Chunk, major_sec: str, is_callout: bool = False) -> None:
        chunks.append(c)
        major_section_chunks.setdefault(major_sec, []).append(c)
        if is_callout:
            major_section_callouts.setdefault(major_sec, []).append(c.chunk_id)

    # True while nothing but whitespace separates the current token from the previous table.
    prev_table_contiguous = False
    for tok in tokens:
        if not tok or not tok.strip():
            continue
        if not tok.lstrip().lower().startswith("<table"):
            prev_table_contiguous = False

        if tok.lstrip().lower().startswith("<table"):
            # A real clinical HTML table never lives inside a bibliography; pop stale Références!
            while heading_stack and REF_HEADING_RE.search(heading_stack[-1][1]):
                heading_stack.pop()
            sec_path = _current_sec_path()
            is_ref = _is_ref_sec()
            if is_ref:
                continue

            # Only inherit previous table headers within the same major section
            prev_hdrs = (
                last_table_headers
                if last_table_major_section == current_major_section
                else None
            )
            parsed: ParsedTable = parse_html_table(
                tok, previous_headers=prev_hdrs, previous_is_contiguous=prev_table_contiguous
            )
            prev_table_contiguous = True
            if parsed.has_explicit_headers and parsed.headers:
                last_table_headers = parsed.headers
                last_table_major_section = current_major_section

            # Detect if this table IS specifically a compact specialty allergy box
            # (NEVER classify a full surgical procedure table as an allergy callout!)
            hdr_blob = " ".join(parsed.headers).lower()
            is_procedure_table = any(
                k in hdr_blob for k in ("actes chirurgicaux", "interventionnels", "nomenclature", "procédure")
            )
            raw_table_plain = " ".join(
                " ".join(row) for g in parsed.row_groups for row in g.rows
            )
            prev_is_allergy_intro = (
                len(chunks) > 0
                and chunks[-1].parent_section_id == current_major_section
                and bool(ALLERGY_BOX_RE.search(chunks[-1].text))
                and len(chunks[-1].text) < 400
            )
            is_allergy_table = (not is_procedure_table) and (
                (prev_is_allergy_intro and parsed.num_rows <= 8)
                or (
                    parsed.num_rows <= 6
                    and bool(ALLERGY_BOX_RE.search(raw_table_plain[:500]))
                )
            )

            # Emit clean Markdown table chunk(s)
            md_chunks = parsed.to_markdown_chunks(max_chars=max_table_chars)
            for md_t in md_chunks:
                ctype: ChunkType = "callout_allergy" if is_allergy_table else "table_markdown"
                c = _make_chunk(
                    meta=meta,
                    chunk_index=idx,
                    text=md_t,
                    section_path=sec_path,
                    section_id=current_major_section,
                    chunk_type=ctype,
                    is_ref=False,
                    prepend_context=True,
                )
                _register_chunk(c, current_major_section, is_callout=is_allergy_table)
                idx += 1

            # Emit self-contained Row-Group Clinical Cards for dense clinical lookup tables!
            if (
                emit_row_cards
                and not is_allergy_table
                and parsed.num_cols >= 3
                and len(parsed.row_groups) >= 1
                and (parsed.has_explicit_headers or parsed.inherited_headers)
            ):
                cards = parsed.to_row_cards(min_cols=3)
                for card in cards:
                    c = _make_chunk(
                        meta=meta,
                        chunk_index=idx,
                        text=card,
                        section_path=sec_path,
                        section_id=current_major_section,
                        chunk_type="table_row_card",
                        is_ref=False,
                        prepend_context=True,
                    )
                    _register_chunk(c, current_major_section, is_callout=False)
                    idx += 1
            continue

        # Prose token: walk line by line to update headings and emit prose chunks
        lines = tok.splitlines()
        buf_lines: list[str] = []

        def _flush_prose() -> None:
            nonlocal idx
            body = "\n".join(buf_lines).strip()
            if not body:
                return
            sec_path = _current_sec_path()
            is_ref = _is_ref_sec()
            if is_ref:
                # Split paragraphs and verify each piece is genuinely bibliographic (never swallow R1.2.1 / R1.6!)
                for piece in _split_prose_paragraphs(body, max_chars=2000):
                    truly_ref = _is_truly_reference_text(piece)
                    if truly_ref:
                        c = _make_chunk(
                            meta=meta,
                            chunk_index=idx,
                            text=piece,
                            section_path=sec_path,
                            section_id=current_major_section,
                            chunk_type="references",
                            is_ref=True,
                            prepend_context=True,
                        )
                        chunks.append(c)
                        idx += 1
                    else:
                        is_rec_box = bool(REC_ID_RE.search(piece) and GRADE_RE.search(piece))
                        c = _make_chunk(
                            meta=meta,
                            chunk_index=idx,
                            text=piece,
                            section_path=re.sub(r"\s*>\s*R[ée]f[ée]rences.*$", "", sec_path, flags=re.I),
                            section_id=current_major_section,
                            chunk_type="recommendation_box" if is_rec_box else "prose",
                            is_ref=False,
                            prepend_context=True,
                        )
                        _register_chunk(c, current_major_section, is_callout=False)
                        idx += 1
                return

            # Keep version-history changelogs intact (up to 3500 chars) so minor-version diffs
            # (e.g. V3.0 -> V3.1) stay in the same retrievable chunk as the preceding version.
            eff_max_chars = 3500 if "historique des versions" in sec_path.lower() else max_prose_chars
            for piece in _split_prose_paragraphs(body, max_chars=eff_max_chars):
                # If a specialty allergy box ("En cas d'allergie aux bêtalactamines...") starts
                # mid-paragraph after unrelated prose (e.g. IMC>=50 or intro text), split it out
                # as its own atomic, high-signal `callout_allergy` chunk!
                allergy_m = ALLERGY_BOX_RE.search(piece)
                sub_pieces: list[str]
                if allergy_m and allergy_m.start() > 60:
                    before = piece[: allergy_m.start()].strip()
                    after = piece[allergy_m.start() :].strip()
                    sub_pieces = [p for p in (before, after) if p]
                else:
                    sub_pieces = [piece]

                for sub in sub_pieces:
                    is_allergy_box = bool(ALLERGY_BOX_RE.search(sub))
                    is_rec_box = bool(REC_ID_RE.search(sub) and GRADE_RE.search(sub))
                    # A recommendation box is never a footnote, whatever its first character
                    # (Markdown bold "**R1.1 ..." starts with "*").
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
                    c = _make_chunk(
                        meta=meta,
                        chunk_index=idx,
                        text=sub,
                        section_path=sec_path,
                        section_id=current_major_section,
                        chunk_type=ctype,
                        is_ref=False,
                        prepend_context=True,
                    )
                    _register_chunk(
                        c,
                        current_major_section,
                        is_callout=(is_allergy_box or is_footnote),
                    )
                    idx += 1

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
                    has_cp = any(
                        re.match(r"^(?:CHAMP|PARTIE)\s+\d+", h.upper())
                        for _, h in heading_stack
                    )
                    sem_lvl = _semantic_heading_level(lvl, htext, has_champ_or_partie=has_cp)
                    while heading_stack and heading_stack[-1][0] >= sem_lvl:
                        heading_stack.pop()
                    heading_stack.append((sem_lvl, htext))
                    _update_major_section(sem_lvl, htext)
                    # Reset table header inheritance when entering a brand-new major section
                    if current_major_section != last_table_major_section:
                        last_table_headers = None
                    continue
            buf_lines.append(line)
        _flush_prose()

    # Step 2: Link section-anchored allergy/footnote callouts to every chunk in that major section!
    chunk_by_id = {c.chunk_id: c for c in chunks}
    for major_sec, callout_ids in major_section_callouts.items():
        if not callout_ids:
            continue
        # Always prioritize true specialty allergy boxes before footnotes!
        allergy_cids = [cid for cid in callout_ids if chunk_by_id[cid].chunk_type == "callout_allergy"]
        other_cids = [cid for cid in callout_ids if chunk_by_id[cid].chunk_type != "callout_allergy"]
        linked = allergy_cids[:2] + other_cids[:2]
        for c in major_section_chunks.get(major_sec, []):
            if c.chunk_id not in linked:
                c.linked_callout_ids = list(linked)

    _link_neighbors(chunks)
    return chunks


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
    **kwargs,
) -> list[Chunk]:
    """Chunk all documents in a loaded SFAR corpus."""
    all_chunks: list[Chunk] = []
    for d in docs:
        all_chunks.extend(chunk_document(d, strategy=strategy, **kwargs))
    return all_chunks
