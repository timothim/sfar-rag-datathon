"""SOTA HTML Table Reconstruction & Clinical Row-Card Engine for Chandra OCR Markdown.

Forensic audit of the SFAR corpus revealed:
- 2,060 HTML <table> elements across 185 documents (0 Markdown pipe tables)
- 49.1% of all tables (1,011/2,060) — and 64.5% (89/138) in Antibioprophylaxie V3.0 —
  are headerless cross-page continuations!
- Critical clinical alternatives (e.g., beta-lactam allergy alternatives) live inside
  `rowspan` groups that standard splitters detach from the surgical procedure name.

This module reconstructs 2D logical grids with resolved rowspan/colspan, propagates headers
across cross-page continuations, tracks intra-table bold sub-header banners (e.g., AVK vs
AOD), and emits BOTH clean Markdown tables and self-contained Row-Group Clinical Cards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from rag_sfar.ingestion.text_cleaning import latex_to_text


@dataclass
class TableRowGroup:
    """One or more rows coupled by a leading rowspan (e.g., primary + alternative regimen)."""

    rows: list[list[str]]
    sub_banner: str = ""
    raw_text: str = ""
    # Full-width note rows ("En cas de ... considérer ...") that follow this group's rows.
    notes: list[str] = field(default_factory=list)


@dataclass
class ParsedTable:
    """Structured representation of a reconstructed HTML table."""

    headers: list[str]
    has_explicit_headers: bool
    inherited_headers: bool
    row_groups: list[TableRowGroup] = field(default_factory=list)
    num_cols: int = 0
    num_rows: int = 0
    # Full-width note rows placed before any data row: they apply to the whole table.
    table_notes: list[str] = field(default_factory=list)
    # Column 0 value carried over from the previous fragment of a page-split table.
    carried_first_cell: str = ""

    @property
    def has_headers(self) -> bool:
        return any(h.strip() for h in self.headers) and (self.has_explicit_headers or self.inherited_headers)

    def to_markdown_chunks(
        self,
        header_context: str = "",
        max_chars: int = 1800,
    ) -> list[str]:
        """Serialize table into Markdown chunks, never splitting a rowspan group (unless the group
        alone exceeds 1.5 x `max_chars`) and always repeating the column header row.

        A table without a recognised header row is rendered as plain rows ("a | b | c"), without
        an invented "Col 1 | Col 2" header. Full-width note rows are kept after their group."""
        if not self.row_groups and not self.table_notes:
            if self.has_headers and any(h.strip() and not re.fullmatch(r"Col \d+", h) for h in self.headers):
                # Header-only table (empty form or grid): keep its column titles.
                return [(f"{header_context}\n" if header_context else "") + "| " + " | ".join(_escape_md_cell(h) for h in self.headers) + " |"]
            return []

        ncols = max(1, self.num_cols)
        if self.has_headers:
            cols = self.headers
            header_line = "| " + " | ".join(_escape_md_cell(c) for c in cols) + " |"
            sep_line = "| " + " | ".join("---" for _ in cols) + " |"
            table_head = f"{header_line}\n{sep_line}"
        else:
            cols = [""] * ncols
            table_head = ""

        def _row_line(cells: list[str]) -> str:
            if table_head:
                return "| " + " | ".join(_escape_md_cell(c) for c in cells) + " |"
            vals = [_escape_md_cell(c) for c in cells if c.strip()]
            return " | ".join(vals)

        def _banner_line(text: str) -> str:
            return _row_line([f"**{text}**"] + [""] * (len(cols) - 1))

        chunks: list[str] = []
        current_lines: list[str] = []
        current_len = len(table_head) + len(header_context) + 10
        last_banner = ""

        def _flush() -> None:
            nonlocal current_lines, current_len
            if current_lines:
                prefix = f"{header_context}\n" if header_context else ""
                head = f"{table_head}\n" if table_head else ""
                chunks.append(f"{prefix}{head}" + "\n".join(current_lines))
            current_lines = []
            current_len = len(table_head) + len(header_context) + 10

        for note in self.table_notes:
            current_lines.append(_row_line([f"Note : {note}"] + [""] * (len(cols) - 1)))
            current_len += len(current_lines[-1]) + 1

        for grp in self.row_groups:
            grp_lines: list[str] = []
            if grp.sub_banner and grp.sub_banner != last_banner:
                grp_lines.append(_banner_line(grp.sub_banner))
                last_banner = grp.sub_banner
            for row in grp.rows:
                grp_lines.append(_row_line(_pad_row(row, len(cols))))
            for note in grp.notes:
                grp_lines.append(_row_line([f"Note : {note}"] + [""] * (len(cols) - 1)))

            grp_len = sum(len(line) + 1 for line in grp_lines)
            if current_lines and current_len + grp_len > max_chars:
                _flush()
                if grp.sub_banner and (not grp_lines or grp_lines[0] != _banner_line(grp.sub_banner)):
                    current_lines.append(_banner_line(grp.sub_banner))
                    current_len += len(current_lines[-1]) + 1
            if grp_len > 1.5 * max_chars:
                # Oversized group: split it row by row, repeating its banner.
                for line in grp_lines:
                    if current_lines and current_len + len(line) + 1 > max_chars:
                        _flush()
                        if grp.sub_banner:
                            current_lines.append(_banner_line(grp.sub_banner))
                            current_len += len(current_lines[-1]) + 1
                    current_lines.append(line)
                    current_len += len(line) + 1
                continue
            current_lines.extend(grp_lines)
            current_len += grp_len

        _flush()
        return chunks

    def to_row_cards(
        self,
        min_cols: int = 2,
        title: str = "",
        section: str = "",
        context_lines: list[str] | None = None,
        require_headers: bool = True,
    ) -> list[str]:
        """Self-contained row-group cards: one card per row group, which repeats the table
        title, the section, the sub-category banner and the column headers, so that the card can
        be read (and retrieved) on its own.

        Without recognised headers (`require_headers=False`), cells are joined with " — ".

        Example (rowspan group of a dosing table):
          Section : Chirurgie rhinologique
          Actes chirurgicaux ou interventionnels : Chirurgie rhinologique avec greffon
          • Schéma 1 : Molécules = Céfazoline | Dose initiale = 2g IVL | ...
          • Schéma 2 : Molécules = Alternative : Amoxicilline/Clavulanate | ...
        """
        if self.num_cols < min_cols or not self.row_groups:
            return []
        has_hdr = self.has_headers
        if require_headers and not has_hdr:
            return []

        cols = self.headers if has_hdr else [""] * self.num_cols
        cards: list[str] = []
        prefix: list[str] = []
        if title:
            prefix.append(f"Tableau : {title}")
        if section:
            prefix.append(f"Section : {section}")
        prefix.extend(context_lines or [])
        for note in self.table_notes:
            prefix.append(f"Note du tableau : {note}")

        def _pair(i: int, v: str, sep: str) -> str:
            return f"{cols[i]}{sep}{v}" if cols[i] else v

        joiner = " | " if has_hdr else " — "
        for grp in self.row_groups:
            if not grp.rows:
                continue
            lines: list[str] = []
            if grp.sub_banner:
                lines.append(f"Sous-catégorie : {grp.sub_banner}")

            if len(grp.rows) == 1:
                row = _pad_row(grp.rows[0], len(cols))
                pairs = [_pair(i, row[i], " : ") for i in range(len(cols)) if row[i].strip()]
                if not pairs:
                    continue
                lines.append(joiner.join(pairs))
            else:
                # Multi-row rowspan group: factor out the shared key column(s)
                first = _pad_row(grp.rows[0], len(cols))
                shared_cols = [
                    i
                    for i in range(len(cols))
                    if first[i].strip()
                    and all(_pad_row(r, len(cols))[i] == first[i] for r in grp.rows[1:])
                ]
                if shared_cols:
                    lines.append(joiner.join(_pair(i, first[i], " : ") for i in shared_cols))
                for r_idx, raw_r in enumerate(grp.rows, start=1):
                    r = _pad_row(raw_r, len(cols))
                    rem = [_pair(i, r[i], " = ") for i in range(len(cols)) if i not in shared_cols and r[i].strip()]
                    if rem:
                        lines.append(f"• Schéma {r_idx} : " + joiner.join(rem))
            for note in grp.notes:
                lines.append(f"Note : {note}")

            body = "\n".join(lines).strip()
            # Skip ultra-short trivial rows (e.g. blank spacers)
            if len(body) >= 25:
                cards.append("\n".join(prefix + [body]).strip())

        return cards


_BR = "\u2028"  # line break inside a cell, resolved by _resolve_breaks
_BULLET_PREFIX_RE = re.compile(r"^[▪•\-–—■○◦]+\s*")


def _li_text(li: Tag) -> str:
    """Text of one list item; a nested list becomes "parent : child ; child"."""
    own: list[str] = []
    nested: list[str] = []
    for child in li.children:
        if isinstance(child, Tag) and child.name in ("ul", "ol"):
            nested.extend(t for t in (_li_text(x) for x in child.find_all("li", recursive=False)) if t)
        elif isinstance(child, Tag):
            if child.name == "br":
                own.append(_BR)
            elif child.name == "math":
                own.append(latex_to_text(child.get_text()))
            else:
                own.append(_node_text(child))
        else:
            own.append(str(child))
    head = _BULLET_PREFIX_RE.sub("", _resolve_breaks("".join(own)))
    if nested:
        sep = " " if head.rstrip().endswith(":") else " : "
        return f"{head}{sep}{' ; '.join(nested)}" if head else " ; ".join(nested)
    return head


def _node_text(node: Tag) -> str:
    """Readable text of a cell sub-tree: every text node kept once, lists as "a ; b",
    line breaks as " / "."""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, Tag):
            if child.name in ("ul", "ol"):
                items = [t for t in (_li_text(li) for li in child.find_all("li", recursive=False)) if t]
                if items:
                    parts.append(" " + " ; ".join(items) + " ")
            elif child.name == "li":
                t = _li_text(child)
                if t:
                    parts.append(" " + t + " ;")
            elif child.name == "br":
                parts.append(_BR)
            elif child.name == "math":
                # LaTeX rendered before extraction, so that "<math>\\mu</math>g" gives "µg"
                parts.append(latex_to_text(child.get_text()))
            elif child.name in ("p", "div"):
                t = _node_text(child)
                if t.strip():
                    parts.append(" / " + t + " / ")
            else:
                parts.append(_node_text(child))
        else:
            parts.append(str(child))
    return "".join(parts)


# A line that starts with a unit continues the value above it ("≤ 5<br>µg/kg/min").
_UNIT_START_RE = re.compile(r"^(?:µ|\\mu|mg|g/|g\b|kg|ml|mL|mmol|µmol|UI|U/|%|mmHg|h\b|min\b)")


def _resolve_breaks(text: str) -> str:
    """A line break inside a cell continues the sentence when the next line starts in lower
    case or the previous one ends with a comma / an opening word ("1g si durée > 4h,<br>puis
    toutes les 4h<br>jusqu'à fin de chirurgie"); otherwise it separates two items (" / ")."""
    parts = [p.strip() for p in text.split(_BR)]
    out = ""
    for p in parts:
        if not p:
            if out and not out.endswith(" / "):
                out += " / "
            continue
        if not out or out.endswith(" / "):
            out += p
        elif _UNIT_START_RE.match(p) or re.match(r"^[a-zà-ÿ(]", p) or re.search(r"[,(\-–]$|\b(?:de|du|des|la|le|les|à|au|et|ou|en|par|pour|si|puis|jusqu'à)$", out):
            out += " " + p
        else:
            out += " / " + p
    return _normalize_ws(out)


def _clean_cell_text(cell: Tag) -> str:
    """Convert an HTML <td>/<th> cell into clean readable inline text.

    All text is kept, including text outside list items ("Si allergie : <ul>…</ul>"); nested
    list items are written once ("Acte : sous-cas 1 ; sous-cas 2")."""
    text = _resolve_breaks(_node_text(cell))
    text = re.sub(r"(?:\s*/\s*){2,}", " / ", text)
    text = re.sub(r"\s*;\s*(?:;\s*)+", " ; ", text)
    text = re.sub(r"\s+([;,.])", r"\1", text)
    text = re.sub(r":\s*/\s*", ": ", text)
    text = re.sub(r"(?:^|(?<=\s))[▪■•○◦]\s*", "", text)
    return text.strip(" /;")


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _escape_md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _pad_row(row: list[str], target_len: int) -> list[str]:
    if len(row) >= target_len:
        return row[:target_len]
    return row + [""] * (target_len - len(row))


def _is_banner_row(row_cells: list[str], raw_tr: Tag, total_cols: int) -> str | None:
    """Text of a single-cell full-width row (bold or spanning the table), else None."""
    non_empty = [c for c in row_cells if c.strip()]
    if len(non_empty) != 1 or total_cols < 2:
        return None
    text = non_empty[0].strip()
    if len(text) < 3:
        return None
    # Check if bold or spanning multiple columns
    tds = raw_tr.find_all(["td", "th"], recursive=False)
    has_bold = bool(raw_tr.find(["b", "strong"]))
    has_colspan = any(_int_attr(td, "colspan") >= max(2, total_cols - 1) for td in tds)
    if has_colspan or (has_bold and len(tds) == 1):
        return text
    if has_bold and len(text) <= 160:
        return text
    return None


_NOTE_START_RE = re.compile(
    r"^(?:[\*†‡#§¶(\[]|en\s+cas\b|si\b|nb\b|n\.b\.|note\b|attention\b|remarque\b|à\s+noter\b|a\s+noter\b|"
    r"cf\.?\b|voir\b|il\s+(?:est|faut|convient)\b|pas\s+d.\s*indication\b|une?\s+\w+\s+(?:est|peut)\b)",
    re.I,
)
_NOTE_VERB_RE = re.compile(
    r"\b(?:est|sont|doit|doivent|peut|peuvent|faut|convient|considérer|considérée?s?|recommand\w*|"
    r"propos\w*|sugg[eè]r\w*|administrer|réaliser|poursuivi\w*|adapt\w+|discut\w+|privilégi\w+)\b",
    re.I,
)


def full_width_row_kind(text: str, raw_tr: Tag) -> str:
    """"label" for a sub-category title row ("Chirurgie des gonades", "Patients sous AVK"),
    "note" for a full-width sentence that qualifies the rows around it ("En cas de ...,
    considérer ...", "* posologie ...")."""
    t = text.strip()
    if t.endswith("?"):
        return "label"  # a question heads the rows that answer it
    # Short title-like rows are labels even when they end with "." or a call mark
    # ("Candida sp.", "Chirurgie du tube digestif *", "Faible risque [0–8]"): at most 8 words,
    # no conjugated verb, not opening with a note marker. The call mark stays in the label, so
    # its footnote is linked to the rows that FOLLOW (the label heads them).
    core = re.sub(r"[\s*†‡#§]+$", "", t)
    if (
        core
        and len(core.split()) <= 8
        and not _NOTE_VERB_RE.search(core)
        and not re.match(r"^[\*†‡#§(\[]", t)
        and not re.match(r"(?i)^(?:en\s+cas|si\b|nb\b|note\b|attention\b|remarque\b)", t)
    ):
        return "label"
    italic_only = bool(raw_tr.find(["i", "em"])) and not raw_tr.find(["b", "strong"])
    if italic_only or len(t) > 140 or _NOTE_START_RE.match(t):
        return "note"
    if re.search(r"[.;*†‡]\s*$", t):
        return "note"
    if _NOTE_VERB_RE.search(t) and len(t.split()) > 6:
        return "note"
    return "label"


def _int_attr(cell: Tag, name: str) -> int:
    try:
        return max(1, int(str(cell.get(name, "1")).strip()))
    except ValueError:
        return 1


def _looks_like_header_row(row: list[str]) -> bool:
    """Heuristic fallback when OCR used <td> instead of <th> for the table header row.

    Guards strictly against clinical data rows (which contain bullet chars, dosages, or GRADE).
    """
    non_empty = [c.strip().lower() for c in row if c.strip()]
    if len(non_empty) < 2:
        return False
    joined = " ".join(non_empty)
    # Never classify a clinical data row as a column header!
    if any(sym in joined for sym in ("▪", "■", "●●", "grade 1", "grade 2", "avis d'expert", "avis d’expert")):
        return False
    if re.search(r"\b\d+\s*(?:g|mg|ml|ui)\b|\bivl\b|\bamoxicilline\b|\bc[ée]fazoline\b", joined):
        return False
    header_clues = [
        "actes chirurgicaux",
        "molécule",
        "molecule",
        "posologie",
        "dose initiale",
        "réinjection",
        "reinjection",
        "force de la recommandation",
        "grade",
        "accord",
        "nomenclature",
        "allergie",
        "durée",
        "duree",
        "situation",
        "recommandation",
        "traitement",
        "procédure",
        "risque",
        "interventions",
    ]
    hits = sum(1 for c in non_empty if any(k in c for k in header_clues))
    avg_len = sum(len(c) for c in non_empty) / len(non_empty)
    return hits >= 2 and avg_len < 55


def parse_html_table(
    table_html: str,
    previous_headers: list[str] | None = None,
    previous_is_contiguous: bool = True,
    carry_first_cell: str | None = None,
) -> ParsedTable:
    """Parse an HTML <table> with full rowspan/colspan expansion and continuation support.

    `previous_is_contiguous` tells whether the previous table ends right before this one (no
    text in between); a banner-only first header row inherits `previous_headers` only then.
    `carry_first_cell` is the first-column value of the last row of the previous fragment of a
    page-split table (same width, contiguous): leading rows of this fragment whose first cell is
    empty (the rowspan cut by the page break) take it back."""
    soup = BeautifulSoup(table_html, "html.parser")
    table = soup.find("table")
    if table is None:
        return ParsedTable(headers=[], has_explicit_headers=False, inherited_headers=False)

    raw_trs = table.find_all("tr")
    if not raw_trs:
        return ParsedTable(headers=[], has_explicit_headers=False, inherited_headers=False)

    # First pass: expand rowspan & colspan into a clean 2D grid while tracking rowspan anchors
    grid: list[list[str]] = []
    is_th_row: list[bool] = []
    tr_tags: list[Tag] = []
    # Track which rows belong to the same rowspan group initiated by col 0 (or col 0/1)
    row_group_anchor: list[int] = []
    active_spans: dict[int, tuple[int, str, int]] = {}  # col_idx -> (remaining_rows, text, origin_row)
    # Track col-0 rowspan==K cells containing K leaf <li> items (Chandra OCR parallel sub-rows!)
    parallel_list_spans: list[tuple[int, int, list[str]]] = []

    for r_idx, tr in enumerate(raw_trs):
        cells = tr.find_all(["td", "th"], recursive=False)
        if not cells:
            continue
        row_vals: list[str] = []
        th_count = 0
        td_count = 0
        c_idx = 0
        inherited_anchor = r_idx

        def _consume_active_spans() -> None:
            nonlocal c_idx, inherited_anchor
            while c_idx in active_spans:
                rem, txt, origin = active_spans[c_idx]
                row_vals.append(txt)
                if c_idx <= 1:
                    inherited_anchor = min(inherited_anchor, origin)
                if rem <= 1:
                    del active_spans[c_idx]
                else:
                    active_spans[c_idx] = (rem - 1, txt, origin)
                c_idx += 1

        for cell in cells:
            _consume_active_spans()
            if cell.name == "th":
                th_count += 1
            else:
                td_count += 1
            txt = _clean_cell_text(cell)
            try:
                rowspan = max(1, int(str(cell.get("rowspan", "1")).strip()))
            except ValueError:
                rowspan = 1
            try:
                colspan = max(1, int(str(cell.get("colspan", "1")).strip()))
            except ValueError:
                colspan = 1
            # Guard against corrupt OCR spans (e.g. rowspan=999)
            rowspan = min(rowspan, 40)
            colspan = min(colspan, 16)

            # Detect Chandra OCR 1-to-1 parallel <li> list packed inside a col-0 rowspan=K cell
            if c_idx == 0 and rowspan >= 2:
                leaf_lis = [li for li in cell.find_all("li") if not li.find("li")]
                if len(leaf_lis) == rowspan:
                    parent_li = leaf_lis[0].find_parent("li")
                    prefix = ""
                    if parent_li is not None:
                        prefix = " ".join(
                            s.strip() for s in parent_li.find_all(string=True, recursive=False) if s.strip()
                        )
                    items = [
                        (f"{prefix} {li.get_text(' ', strip=True)}".strip() if prefix else li.get_text(" ", strip=True))
                        for li in leaf_lis
                    ]
                    items = [re.sub(r"^[▪■•○\-–—]+\s*", "", it).strip() for it in items]
                    if all(items):
                        parallel_list_spans.append((len(grid), rowspan, items))

            for offset in range(colspan):
                row_vals.append(txt if offset == 0 else "")
                if rowspan > 1:
                    active_spans[c_idx] = (rowspan - 1, txt if offset == 0 else "", r_idx)
                c_idx += 1

        _consume_active_spans()
        grid.append(row_vals)
        is_th_row.append(th_count > 0 and th_count >= td_count)
        tr_tags.append(tr)
        row_group_anchor.append(inherited_anchor)

    if not grid:
        return ParsedTable(headers=[], has_explicit_headers=False, inherited_headers=False)

    max_cols = max(len(r) for r in grid)
    grid = [_pad_row(r, max_cols) for r in grid]

    # De-merge Chandra OCR 1-to-1 parallel <li> spans ONLY when right-hand rows contradict
    # (e.g. 'PAS D'ANTIBIOPROPHYLAXIE' on one row vs an antibiotic on another, NOT 'Alternative :'),
    # proving the K list items align 1-to-1 with the K rows (e.g. Septo-rhinoplastie sans vs avec greffe).
    for start_row, span_k, items in parallel_list_spans:
        if start_row + span_k > len(grid):
            continue
        right_texts = [" ".join(grid[start_row + o][1:]).lower() for o in range(span_k)]
        has_no_abp = any("pas d'antibioprophylaxie" in t or "pas d’antibioprophylaxie" in t for t in right_texts)
        has_pos_abp = any(
            ("pas d'antibioprophylaxie" not in t and "pas d’antibioprophylaxie" not in t and len(t.strip()) > 3)
            for t in right_texts
        )
        has_alt = any("alternative" in t for t in right_texts)
        if has_no_abp and has_pos_abp and not has_alt:
            for o in range(span_k):
                grid[start_row + o][0] = items[o]
                row_group_anchor[start_row + o] = start_row + o

    # Identify header rows
    headers: list[str] = []
    data_start = 0
    has_explicit_headers = False
    inherited_headers = False

    # A continuation table whose first <thead>/<th> row is a single full-width sub-category banner
    # (e.g. `<th colspan="5">Chirurgie des gonades</th>`) inherits the previous table's column
    # headers, but only when it is a true continuation: the previous table is contiguous (no text
    # in between; the caller also requires the same section), has the same number of columns, and
    # the banner is not followed by this table's own header row (`<th>` row).
    first_non_empty = sum(1 for c in grid[0] if c.strip())
    is_banner_th_row0 = (
        is_th_row[0]
        and max_cols >= 3
        and first_non_empty == 1
        and bool(previous_headers)
        and previous_is_contiguous
        and len(previous_headers or []) == max_cols
        and not (len(is_th_row) > 1 and is_th_row[1])
    )

    if is_th_row[0] and not is_banner_th_row0:
        has_explicit_headers = True
        header_rows: list[list[str]] = []
        while data_start < len(grid) and is_th_row[data_start]:
            header_rows.append(grid[data_start])
            data_start += 1
        # Combine multi-row headers cleanly
        headers = []
        for col_i in range(max_cols):
            parts = []
            for hr in header_rows:
                val = hr[col_i].strip()
                if val and val not in parts:
                    parts.append(val)
            headers.append(" / ".join(parts))
    elif _looks_like_header_row(grid[0]):
        has_explicit_headers = True
        headers = [c.strip() for c in grid[0]]
        data_start = 1
    elif previous_headers:
        # Cross-page continuation table! Inherit headers when column count matches
        # (or differs by 1 due to an extra/dropped Nomenclature column in SFAR tables!)
        if len(previous_headers) == max_cols:
            headers = list(previous_headers)
            inherited_headers = True
        elif len(previous_headers) == max_cols + 1 and "nomenclature" in previous_headers[0].lower():
            headers = list(previous_headers[1:])
            inherited_headers = True
        elif len(previous_headers) + 1 == max_cols and len(grid[0][0]) <= 16:
            headers = ["Catégorie"] + list(previous_headers)
            inherited_headers = True

    # Page-split rowspan: leading data rows with an empty first cell continue the previous
    # fragment's last row key.
    carried = ""
    if carry_first_cell and max_cols >= 2:
        for idx in range(data_start, len(grid)):
            row = grid[idx]
            if not any(c.strip() for c in row):
                continue
            if row[0].strip() or not any(c.strip() for c in row[1:]):
                break
            row[0] = carry_first_cell
            row_group_anchor[idx] = -1  # same group as the other carried rows
            carried = carry_first_cell

    # Group data rows by rowspan anchor & detect sub-header banners / full-width notes
    row_groups: list[TableRowGroup] = []
    table_notes: list[str] = []
    current_banner = ""
    pending_group: TableRowGroup | None = None
    pending_anchor: int | None = None
    pending_label = False  # a label row seen, not yet followed by a data row

    for idx in range(data_start, len(grid)):
        row = grid[idx]
        if not any(c.strip() for c in row):
            continue
        banner = _is_banner_row(row, tr_tags[idx], max_cols)
        if banner is not None:
            if full_width_row_kind(banner, tr_tags[idx]) == "note":
                if pending_group is not None:
                    pending_group.notes.append(banner)
                elif row_groups:
                    row_groups[-1].notes.append(banner)
                else:
                    table_notes.append(banner)
                continue
            if pending_group is not None:
                row_groups.append(pending_group)
                pending_group = None
                pending_anchor = None
            if pending_label and current_banner:
                # Two labels in a row: the first one heads nothing, keep it as its own row.
                row_groups.append(TableRowGroup(rows=[[current_banner] + [""] * (max_cols - 1)]))
            current_banner = banner
            pending_label = True
            continue

        anchor = row_group_anchor[idx]
        if pending_group is not None and anchor == pending_anchor:
            pending_group.rows.append(row)
        else:
            if pending_group is not None:
                row_groups.append(pending_group)
            pending_group = TableRowGroup(rows=[row], sub_banner=current_banner)
            pending_anchor = anchor
        pending_label = False

    if pending_group is not None:
        row_groups.append(pending_group)
    if pending_label and current_banner:
        # A trailing label row (nothing below it in this fragment) is kept as a row.
        row_groups.append(TableRowGroup(rows=[[current_banner] + [""] * (max_cols - 1)]))

    return ParsedTable(
        headers=headers,
        has_explicit_headers=has_explicit_headers,
        inherited_headers=inherited_headers,
        row_groups=row_groups,
        num_cols=max_cols,
        num_rows=sum(len(g.rows) for g in row_groups),
        table_notes=table_notes,
        carried_first_cell=carried,
    )
