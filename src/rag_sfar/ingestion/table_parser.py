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


@dataclass
class TableRowGroup:
    """One or more rows coupled by a leading rowspan (e.g., primary + alternative regimen)."""

    rows: list[list[str]]
    sub_banner: str = ""
    raw_text: str = ""


@dataclass
class ParsedTable:
    """Structured representation of a reconstructed HTML table."""

    headers: list[str]
    has_explicit_headers: bool
    inherited_headers: bool
    row_groups: list[TableRowGroup] = field(default_factory=list)
    num_cols: int = 0
    num_rows: int = 0

    def to_markdown_chunks(
        self,
        header_context: str = "",
        max_chars: int = 1800,
    ) -> list[str]:
        """Serialize table into Markdown chunks, NEVER splitting a rowspan group and
        ALWAYS repeating the column header row on every chunk."""
        if not self.row_groups:
            return []

        cols = self.headers if self.headers else [f"Col {i+1}" for i in range(max(1, self.num_cols))]
        header_line = "| " + " | ".join(_escape_md_cell(c) for c in cols) + " |"
        sep_line = "| " + " | ".join("---" for _ in cols) + " |"
        table_head = f"{header_line}\n{sep_line}"

        chunks: list[str] = []
        current_lines: list[str] = []
        current_len = len(table_head) + len(header_context) + 10
        last_banner = ""

        for grp in self.row_groups:
            grp_lines: list[str] = []
            if grp.sub_banner and grp.sub_banner != last_banner:
                banner_cells = [f"**{grp.sub_banner}**"] + [""] * (len(cols) - 1)
                grp_lines.append("| " + " | ".join(_escape_md_cell(c) for c in banner_cells) + " |")
                last_banner = grp.sub_banner
            for row in grp.rows:
                padded = _pad_row(row, len(cols))
                grp_lines.append("| " + " | ".join(_escape_md_cell(c) for c in padded) + " |")

            grp_len = sum(len(l) + 1 for l in grp_lines)
            if current_lines and current_len + grp_len > max_chars:
                prefix = f"{header_context}\n" if header_context else ""
                chunks.append(f"{prefix}{table_head}\n" + "\n".join(current_lines))
                current_lines = []
                current_len = len(table_head) + len(header_context) + 10
                if grp.sub_banner:
                    banner_cells = [f"**{grp.sub_banner}**"] + [""] * (len(cols) - 1)
                    banner_md = "| " + " | ".join(_escape_md_cell(c) for c in banner_cells) + " |"
                    if not grp_lines or grp_lines[0] != banner_md:
                        current_lines.append(banner_md)
                        current_len += len(banner_md) + 1

            current_lines.extend(grp_lines)
            current_len += grp_len

        if current_lines:
            prefix = f"{header_context}\n" if header_context else ""
            chunks.append(f"{prefix}{table_head}\n" + "\n".join(current_lines))
        return chunks

    def to_row_cards(self, min_cols: int = 2) -> list[str]:
        """Generate self-contained clinical Row-Group Cards for structured lookup tables.

        Example output for an Antibioprophylaxie rowspan group:
          Actes chirurgicaux ou interventionnels : Chirurgie rhinologique avec greffon ; Chirurgie sinusienne tumorale
          - Option 1 : Molécules = Céfazoline | Dose initiale = 2g IVL | Réinjections et durée = 1g si durée > 4h... | Force = GRADE 2
          - Option 2 : Molécules = Alternative : Amoxicilline/Clavulanate | Dose initiale = 2g IVL | ...
        """
        if self.num_cols < min_cols or not self.row_groups:
            return []

        cols = self.headers if self.headers else [f"Colonne {i+1}" for i in range(self.num_cols)]
        cards: list[str] = []

        for grp in self.row_groups:
            if not grp.rows:
                continue
            lines: list[str] = []
            if grp.sub_banner:
                lines.append(f"Sous-catégorie : {grp.sub_banner}")

            if len(grp.rows) == 1:
                row = _pad_row(grp.rows[0], len(cols))
                pairs = [
                    f"{cols[i]} : {row[i]}"
                    for i in range(len(cols))
                    if row[i].strip()
                ]
                if not pairs:
                    continue
                lines.append(" | ".join(pairs))
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
                    shared_parts = [f"{cols[i]} : {first[i]}" for i in shared_cols]
                    lines.append(" | ".join(shared_parts))
                for r_idx, raw_r in enumerate(grp.rows, start=1):
                    r = _pad_row(raw_r, len(cols))
                    rem = [
                        f"{cols[i]} = {r[i]}"
                        for i in range(len(cols))
                        if i not in shared_cols and r[i].strip()
                    ]
                    if rem:
                        lines.append(f"• Schéma {r_idx} : " + " | ".join(rem))

            card_text = "\n".join(lines).strip()
            # Skip ultra-short trivial rows (e.g. blank spacers)
            if len(card_text) >= 25:
                cards.append(card_text)

        return cards


def _clean_cell_text(cell: Tag) -> str:
    """Convert an HTML <td>/<th> cell into clean readable inline text."""
    # Preserve list items clearly with semicolons/bullets
    lis = cell.find_all("li")
    if lis:
        parts = []
        for li in lis:
            t = _normalize_ws(li.get_text(" ", strip=True))
            t = re.sub(r"^[▪•\-–—\*]+\s*", "", t)
            if t:
                parts.append(t)
        # Check if there is non-li text too
        if parts:
            return " ; ".join(parts)

    # Replace <br> with spaces or separators
    for br in cell.find_all("br"):
        br.replace_with(" / ")
    text = cell.get_text(" ", strip=True)
    text = _normalize_ws(text)
    text = re.sub(r"(?:\s*/\s*){2,}", " / ", text)
    text = text.strip(" /")
    return text


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _escape_md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _pad_row(row: list[str], target_len: int) -> list[str]:
    if len(row) >= target_len:
        return row[:target_len]
    return row + [""] * (target_len - len(row))


def _is_banner_row(row_cells: list[str], raw_tr: Tag, total_cols: int) -> str | None:
    """Detect an intra-table sub-header banner (e.g. `<b>Patients traités par un AVK</b>`)."""
    non_empty = [c for c in row_cells if c.strip()]
    if len(non_empty) != 1 or total_cols < 2:
        return None
    text = non_empty[0].strip()
    if len(text) > 160 or len(text) < 3:
        return None
    # Check if bold or spanning multiple columns
    tds = raw_tr.find_all(["td", "th"], recursive=False)
    has_bold = bool(raw_tr.find(["b", "strong"]))
    has_colspan = any(int(td.get("colspan", 1) or 1) >= max(2, total_cols - 1) for td in tds)
    if has_bold or has_colspan:
        return text
    return None


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
) -> ParsedTable:
    """Parse an HTML <table> with full rowspan/colspan expansion and continuation support.

    `previous_is_contiguous` tells whether the previous table ends right before this one (no
    text in between); a banner-only first header row inherits `previous_headers` only then."""
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
            headers.append(" / ".join(parts) if parts else f"Col {col_i + 1}")
    elif _looks_like_header_row(grid[0]):
        has_explicit_headers = True
        headers = [c.strip() or f"Col {i + 1}" for i, c in enumerate(grid[0])]
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

    # Group data rows by rowspan anchor & detect sub-header banners
    row_groups: list[TableRowGroup] = []
    current_banner = ""
    pending_group: TableRowGroup | None = None
    pending_anchor: int | None = None

    for idx in range(data_start, len(grid)):
        row = grid[idx]
        if not any(c.strip() for c in row):
            continue
        banner = _is_banner_row(row, tr_tags[idx], max_cols)
        if banner is not None:
            if pending_group is not None:
                row_groups.append(pending_group)
                pending_group = None
                pending_anchor = None
            current_banner = banner
            continue

        anchor = row_group_anchor[idx]
        if pending_group is not None and anchor == pending_anchor:
            pending_group.rows.append(row)
        else:
            if pending_group is not None:
                row_groups.append(pending_group)
            pending_group = TableRowGroup(rows=[row], sub_banner=current_banner)
            pending_anchor = anchor

    if pending_group is not None:
        row_groups.append(pending_group)

    return ParsedTable(
        headers=headers,
        has_explicit_headers=has_explicit_headers,
        inherited_headers=inherited_headers,
        row_groups=row_groups,
        num_cols=max_cols,
        num_rows=sum(len(g.rows) for g in row_groups),
    )
