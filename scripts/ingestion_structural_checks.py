"""Structural checks of the table_aware_sota chunking over the whole corpus (no embeddings).

Counts what the chunker produces and what it loses, from the source Markdown alone:
- chunk counts by type, size distribution, chunks above 4 000 characters;
- tables: with explicit / inherited / no headers, tables of >= 2 columns that yield no row card,
  row cards and Markdown chunks still carrying generic "Col N" / "Colonne N" headers;
- full-width rows (a single cell spanning the table) whose text is in no chunk;
- source text units (paragraph lines and table cells of >= 4 words) whose text is in no chunk
  of the same document ("uncovered text"), excluding bibliography sections;
- OCR residues left in chunk text: HTML entities, LaTeX, <math>, NUL bytes, English image
  descriptions, Mermaid blocks, headings glued to text;
- population labels per chunk (when the chunker sets them).

Usage:
  HF_HUB_OFFLINE=1 .venv/bin/python scripts/ingestion_structural_checks.py [--json out.json]
      [--from-index index/<dir>]   # read chunks from an existing index instead of re-chunking

With --from-index the "uncovered text" check uses the corpus as loaded today (same overlay).
"""

from __future__ import annotations

import argparse
import collections
import html
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_sfar.config import Settings  # noqa: E402
from rag_sfar.ingestion.chunker import chunk_corpus  # noqa: E402
from rag_sfar.ingestion.loader import load_sfar_corpus  # noqa: E402
from rag_sfar.schemas import Chunk  # noqa: E402

NG = 4
REF_HEADING_RE = re.compile(r"^#{1,6}\s+.*\b(r[eé]f[eé]rences?|bibliographie)\b", re.I)


def fold(text: str) -> str:
    """Accent-folded alphanumeric tokens, after removing markup that the chunker may legitimately
    rewrite (HTML entities and tags, LaTeX commands and delimiters, image syntax)."""
    text = html.unescape(text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"</?[a-zA-Z][^<>]{0,300}>", " ", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = re.sub(r"\b(?:Figure|Image|Schéma) ?:", " ", text)
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", t))


def source_units(md: str) -> list[tuple[str, str]]:
    """(kind, text) units of the source Markdown, bibliography sections excluded."""
    units: list[tuple[str, str]] = []
    in_ref = False
    ref_level = 0
    parts = re.split(r"(<table\b.*?</table>)", md, flags=re.S | re.I)
    for part in parts:
        if part.lower().startswith("<table"):
            if in_ref:
                continue
            soup = BeautifulSoup(part, "html.parser")
            for cell in soup.find_all(["td", "th"]):
                if cell.find(["td", "th"]):
                    continue
                units.append(("cell", cell.get_text(" ", strip=True)))
            continue
        for line in part.splitlines():
            s = line.strip()
            m = re.match(r"^(#{1,6})\s+", s)
            if m:
                lvl = len(m.group(1))
                if REF_HEADING_RE.match(s):
                    in_ref, ref_level = True, lvl
                elif in_ref and lvl <= ref_level:
                    in_ref = False
                continue
            if in_ref or not s:
                continue
            if s.startswith("!["):
                continue
            s = re.sub(r"</?[a-zA-Z][^<>]{0,300}>", " ", s)
            units.append(("line", s))
    return [(k, t) for k, t in units if len(fold(t).split()) >= 4]


def load_index_chunks(index_dir: Path) -> list[Chunk]:
    con = sqlite3.connect(index_dir / "metadata.sqlite")
    rows = con.execute("SELECT payload_json FROM chunks ORDER BY idx").fetchall()
    return [Chunk.model_validate_json(r[0]) for r in rows]


def full_width_rows(md: str) -> list[str]:
    out = []
    for tbl in re.findall(r"<table\b.*?</table>", md, flags=re.S | re.I):
        soup = BeautifulSoup(tbl, "html.parser")
        trs = soup.find_all("tr")
        ncols = 0
        for tr in trs:
            ncols = max(ncols, sum(int(str(c.get("colspan", 1) or 1)) if str(c.get("colspan", 1) or 1).isdigit() else 1
                                   for c in tr.find_all(["td", "th"], recursive=False)))
        if ncols < 2:
            continue
        for tr in trs:
            cells = tr.find_all(["td", "th"], recursive=False)
            if len(cells) == 1:
                cs = str(cells[0].get("colspan", 1) or 1)
                if cs.isdigit() and int(cs) >= ncols - 0 and ncols >= 2:
                    txt = cells[0].get_text(" ", strip=True)
                    if len(fold(txt).split()) >= 4:
                        out.append(txt)
    return out


RESIDUES = {
    "html_entity": re.compile(r"&(?:gt|lt|amp|nbsp|quot|#\d+);"),
    "latex_dollar": re.compile(r"\$[^$\n]{1,80}\$"),
    "latex_cmd": re.compile(r"\\(?:geq|leq|times|text|mathrm|frac|pm|ge|le|approx|mu|alpha|beta)\b"),
    "math_tag": re.compile(r"</?math\b"),
    "nul": re.compile("\x00"),
    "english_figure": re.compile(r"\[Figure : [^\]]*\b(?:the|with|and|of|showing|logo|diagram|chart)\b[^\]]*\]", re.I),
    "image_md": re.compile(r"!\[[^\]]*\]\([^)]*\)"),
    "mermaid": re.compile(r"```\s*mermaid|\bgraph\s+(?:TD|LR|TB)\b|flowchart\s+(?:TD|LR|TB)"),
    "glued_heading": re.compile(r"[^\n#\s]#{1,4}\s+[A-ZÀ-Ý]"),
    "html_tag": re.compile(r"</?(?:td|tr|table|div|span|ul|li|br|p|sup|sub|b|i|u)\b[^>]*>", re.I),
}


# ---------------------------------------------------------------- fidelity checks (after R1 review)

_COMPARE_RE = re.compile(r"[<>≤≥]\s*=?\s*\d+(?:[.,]\d+)?")
_NUM_UNIT_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:mg/kg/j|mg/kg/h|mg/kg|µg/kg|mg|µg|g|ui|ml/kg|ml|mmol/l|mmol|kg|%|h|min|j|sa)?(?![a-z])",
    re.I,
)
_DRUG_RE = re.compile(
    r"\b[a-zà-ÿ]{3,}(?:ine|ines|ole|oles|ide|ides|one|ones|xime|cilline|mycine|azole|parine|sartan|pril|tamol|zépam|zolam)\b",
    re.I,
)


def clinical_tokens(text: str) -> set[str]:
    """Numbers (with their unit), comparisons and drug-like words of a cell or row, folded and
    without spaces, so that "≥ 2 g" and "≥2g" are the same token."""
    from rag_sfar.ingestion.text_cleaning import clean_chunk_text

    t = clean_chunk_text(text)
    toks = set()
    for rx in (_COMPARE_RE, _NUM_UNIT_RE, _DRUG_RE):
        for m in rx.finditer(t):
            tok = re.sub(r"\s+", "", m.group(0).lower())
            if tok:
                toks.add(unicodedata.normalize("NFC", tok))
    return toks


def _compact(text: str) -> str:
    from rag_sfar.ingestion.text_cleaning import clean_chunk_text

    return unicodedata.normalize("NFC", re.sub(r"\s+", "", clean_chunk_text(text).lower()))


def table_fidelity(docs, by_doc) -> dict:
    """Every clinical token of every source table row must be found, all together, in one
    "unit" of the chunks of that document: one line of a table chunk, or one row card."""
    rows = rows_fail = toks = toks_missing = 0
    examples = []
    for d in docs:
        if d.metadata.language == "en":
            continue
        units = []
        blob = []
        for c in by_doc.get(d.metadata.doc_id, []):
            if c.chunk_type in ("table_markdown", "callout_allergy"):
                units.extend(_compact(line) for line in c.text.splitlines() if line.strip())
                blob.append(_compact(c.text))
            elif c.chunk_type == "table_row_card":
                units.append(_compact(c.text))
                blob.append(_compact(c.text))
        blob_s = "|".join(blob)
        for tbl in re.findall(r"<table\b.*?</table>", d.text, flags=re.S | re.I):
            for tr in BeautifulSoup(tbl, "html.parser").find_all("tr"):
                rt = set()
                for cell in tr.find_all(["td", "th"], recursive=False):
                    rt |= clinical_tokens(cell.get_text(" "))
                if not rt:
                    continue
                rows += 1
                toks += len(rt)
                miss = {t for t in rt if t not in blob_s}
                toks_missing += len(miss)
                if not any(all(t in u for t in rt) for u in units):
                    rows_fail += 1
                    if len(examples) < 15:
                        examples.append((d.metadata.doc_id[:40], sorted(rt)[:8], sorted(miss)[:5]))
    return {"rows_with_tokens": rows, "rows_not_in_one_unit": rows_fail, "tokens": toks,
            "tokens_missing": toks_missing, "examples": examples}


def flowchart_fidelity(docs, by_doc) -> dict:
    from rag_sfar.ingestion.text_cleaning import _MERMAID_BLOCK_RE, _fold_tokens, mermaid_required_tokens

    blocks = bad = 0
    ex = []
    for d in docs:
        out_tokens = set()
        for c in by_doc.get(d.metadata.doc_id, []):
            out_tokens |= _fold_tokens(c.text)
        for m in _MERMAID_BLOCK_RE.finditer(d.text):
            blocks += 1
            miss = mermaid_required_tokens(m.group(1)) - out_tokens
            if miss:
                bad += 1
                if len(ex) < 10:
                    ex.append((d.metadata.doc_id[:40], sorted(miss)[:8]))
    return {"blocks": blocks, "blocks_losing_tokens": bad, "examples": ex}


# Corrupted micro units ("\mug", "mug", "mumol"); raw "\mu" is unconverted LaTeX, counted apart.
_MICRO_BAD_RE = re.compile(r"\\mug|\bmug\b|\bmumol\b|\bmuL\b")
_MICRO_RAW_RE = re.compile(r"\\mu\b")


def single_line_tables(chunks) -> int:
    n = 0
    for c in chunks:
        if c.chunk_type != "table_markdown":
            continue
        lines = [ln for ln in c.text.splitlines() if "|" in ln]
        # a header row glued to its separator and data rows (header-only tables are legitimate)
        if len(lines) == 1 and "---" in lines[0]:
            n += 1
    return n


def exclusion_contradictions(chunks) -> int:
    """Chunks labelled with a population that their document title or section path explicitly
    excludes ("(nouveau-né exclu)", "hors pédiatrie")."""
    from rag_sfar.ingestion.population import _TERM_RE

    n = 0
    for c in chunks:
        if not getattr(c, "populations", None):
            continue
        ctx = f"{c.doc_title} > {c.section_path}"
        for pop, rx in _TERM_RE.items():
            if pop not in c.populations:
                continue
            for m in rx.finditer(ctx):
                after = ctx[m.end() : m.end() + 25]
                before = ctx[max(0, m.start() - 12) : m.start()]
                par = ctx[: m.start()].rfind("(")
                in_excl = par != -1 and ")" not in ctx[par : m.start()] and re.match(
                    r"\s*(?:except\w*|excluding|sauf|hors)\b", ctx[par + 1 : m.start()], re.I
                )
                if in_excl or re.match(r"^[\s)\]]*(?:exclue?s?|exclus)\b", after, re.I) or re.search(r"\b(?:hors|sauf)\s+(?:l['’]|la|le|les)?\s*$", before, re.I):
                    n += 1
                    break
            else:
                continue
            break
    return n


def parse_options(spec: str):
    import dataclasses

    from rag_sfar.ingestion.chunker import ChunkOptions

    opts = ChunkOptions()
    for kv in (spec or "").split(","):
        if not kv.strip():
            continue
        k, _, v = kv.partition("=")
        cur = getattr(opts, k.strip())
        setattr(opts, k.strip(), v.lower() in ("1", "true") if isinstance(cur, bool) else int(v) if isinstance(cur, int) else v)
    return opts


def run(index_dir: Path | None, options: str = "") -> dict:
    s = Settings()
    docs = load_sfar_corpus(s.corpus_dir)
    if index_dir is None:
        chunks = chunk_corpus(docs, strategy="table_aware_sota", options=parse_options(options))
    else:
        chunks = load_index_chunks(index_dir)
    by_doc: dict[str, list[Chunk]] = collections.defaultdict(list)
    for c in chunks:
        by_doc[c.doc_id].append(c)

    out: dict = {"num_documents": len(docs), "num_chunks": len(chunks)}
    out["chunk_types"] = dict(collections.Counter(c.chunk_type for c in chunks))
    lens = sorted(len(c.text) for c in chunks)
    out["text_len"] = {
        "median": lens[len(lens) // 2],
        "p99": lens[int(len(lens) * 0.99)],
        "max": lens[-1],
        "gt_4000": sum(1 for x in lens if x > 4000),
        "gt_2500": sum(1 for x in lens if x > 2500),
    }
    out["indexed_len_max"] = max(len(c.indexed_text) for c in chunks)
    big = sorted(chunks, key=lambda c: -len(c.text))[:5]
    out["largest"] = [(c.doc_id[:50], c.chunk_type, len(c.text)) for c in big]

    generic_hdr = re.compile(r"\b(?:Col|Colonne) \d+\b")
    out["cards_with_generic_headers"] = sum(
        1 for c in chunks if c.chunk_type == "table_row_card" and generic_hdr.search(c.text)
    )
    out["table_md_with_generic_headers"] = sum(
        1 for c in chunks if c.chunk_type == "table_markdown" and generic_hdr.search(c.text)
    )

    # Uncovered source text and full-width rows
    unc_units = 0
    unc_chars = 0
    tot_units = 0
    tot_chars = 0
    fw_total = 0
    fw_lost = 0
    fw_examples = []
    unc_by_kind = collections.Counter()
    unc_examples = []
    from rag_sfar.ingestion.text_cleaning import NulRepairer, collapse_list_markers

    repair = NulRepairer([d.text for d in docs])
    W = 24

    def windows(t: str, step: int = 1) -> list[str]:
        t = t.replace(" ", "")
        if len(t) <= W:
            return [t] if t else []
        return [t[i : i + W] for i in range(0, len(t) - W + 1, step)]

    for d in docs:
        if d.metadata.language == "en":
            continue
        grams: set = set()
        folded = [fold(repair(c.text)).replace(" ", "") for c in by_doc.get(d.metadata.doc_id, [])]
        doc_str = "|".join(folded)
        for f in folded:
            grams.update(windows(f))

        def missing_share(t: str) -> float:
            t = t.replace(" ", "")
            if len(t) <= W:
                return 0.0 if t in doc_str else 1.0
            ug = windows(t, step=4)
            return sum(1 for g in ug if g not in grams) / len(ug)

        src = collapse_list_markers(repair(d.text))
        for kind, t in source_units(src):
            if "-->" in t or re.match(r"^\s*(?:graph|flowchart|subgraph)\b", t):
                continue  # Mermaid source syntax: rewritten as text by the chunker
            if not fold(t):
                continue
            miss = missing_share(fold(t))
            n = len(fold(t))
            tot_units += 1
            tot_chars += n
            if miss > 0.5:
                unc_units += 1
                unc_by_kind[kind] += 1
                if len(unc_examples) < 80 and n > 20:
                    unc_examples.append((d.metadata.doc_id[:40], kind, t[:160]))
            unc_chars += miss * n
        for t in full_width_rows(src):
            fw_total += 1
            if fold(t) and missing_share(fold(t)) > 0.5:
                fw_lost += 1
                if len(fw_examples) < 10:
                    fw_examples.append((d.metadata.doc_id[:40], t[:120]))
    out["uncovered"] = {
        "units": unc_units,
        "units_total": tot_units,
        "chars": int(unc_chars),
        "chars_total": tot_chars,
        "share_chars_pct": round(100 * unc_chars / max(1, tot_chars), 2),
        "by_kind": dict(unc_by_kind),
        "examples": unc_examples,
    }
    out["full_width_rows"] = {"total": fw_total, "lost": fw_lost, "examples": fw_examples}

    res = {}
    for name, rx in RESIDUES.items():
        res[name] = sum(len(rx.findall(c.text)) for c in chunks if not c.is_reference_section)
    out["residues_in_text"] = res
    res_idx = {}
    for name in ("html_entity", "latex_cmd", "math_tag", "nul", "english_figure", "mermaid"):
        res_idx[name] = sum(len(RESIDUES[name].findall(c.indexed_text)) for c in chunks if not c.is_reference_section)
    out["residues_in_indexed_text"] = res_idx

    pops = collections.Counter()
    for c in chunks:
        pops[getattr(c, "population_hint", "?")] += 1
    out["population_hint"] = dict(pops)
    out["fidelity"] = {
        "tables": table_fidelity(docs, by_doc),
        "flowcharts": flowchart_fidelity(docs, by_doc),
        "single_line_table_chunks": single_line_tables(chunks),
        "table_markdown_chunks": sum(1 for c in chunks if c.chunk_type == "table_markdown"),
        "micro_unit_corruptions": sum(len(_MICRO_BAD_RE.findall(c.text)) for c in chunks),
        "raw_latex_mu": sum(len(_MICRO_RAW_RE.findall(c.text)) for c in chunks),
        "population_exclusion_contradictions": exclusion_contradictions(chunks),
    }
    if chunks and hasattr(chunks[0], "populations"):
        pp = collections.Counter()
        for c in chunks:
            for p in getattr(c, "populations", []) or ["(vide)"]:
                pp[p] += 1
        out["populations"] = dict(pp)

    # Headerless tables that produce no row card (recomputed from parse stats when available)


    from rag_sfar.ingestion import chunker as _ch

    stats = getattr(_ch, "TABLE_STATS", None)
    if stats is not None and index_dir is None:
        out["table_parse_stats"] = dict(stats)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    ap.add_argument("--from-index", type=Path)
    ap.add_argument("--options", default="", help="ChunkOptions as key=value,...")
    a = ap.parse_args()
    out = run(a.from_index, a.options)
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if a.json:
        a.json.write_text(txt, encoding="utf-8")
    print(txt[:6000])


if __name__ == "__main__":
    main()
