"""K3 - Characterise every table whose headers are inherited from a NON-contiguous table.

In memory only (nothing written to index/ or data/). Wraps chunker.parse_html_table in this
process to see each call, re-splits the document text exactly as the chunker does, and records
what sits between the headerless table and (a) the immediately preceding table, (b) the table
whose headers it inherits (last table with explicit headers of the same major section).

Run: .venv/bin/python -I reports/agents/K3_annexes/characterise_inheritance.py [--switch]
Output: K3_annexes/inheritance_cases[_switch].json (ids, counts and gap kinds; short excerpts
for hand labelling are written to inheritance_cases_excerpts.local.json, not committed).
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
import rag_sfar.ingestion.chunker as ch  # noqa: E402
from rag_sfar.ingestion.loader import load_sfar_corpus  # noqa: E402

OUT = Path(__file__).parent
SWITCH = "--switch" in sys.argv
if SWITCH:
    import rag_sfar.ingestion.table_parser as tp
    tp.ADJACENT_HEADERS = True
    sys.path.insert(0, str(Path(__file__).parent))
    import gap_wrapper  # noqa: E402
    gap_wrapper.install()

orig = ch.parse_html_table
cur: dict = {"doc": None, "tokens": [], "pos": 0, "tables": []}
log: list[dict] = []


def _gap_kind(gap: str) -> str:
    g = gap.strip()
    if not g:
        return "nothing"
    lines = [ln.strip() for ln in g.splitlines() if ln.strip()]
    if any(ln.startswith("#") for ln in lines):
        return "heading"
    if len(g) <= 300:
        return "short_text"  # note, caption, footnote, page residue
    return "paragraph"


def _col_kinds(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    n = max(len(r) for r in rows)
    kinds = []
    for i in range(n):
        vals = [r[i] for r in rows if i < len(r) and r[i].strip()]
        if not vals:
            kinds.append("empty")
            continue
        num = sum(bool(re.search(r"\d", v)) and len(v) <= 40 for v in vals) / len(vals)
        long_ = sum(len(v) > 80 for v in vals) / len(vals)
        kinds.append("num" if num >= 0.6 else ("long" if long_ >= 0.5 else "text"))
    return kinds


def wrapped(tok, previous_headers=None, previous_is_contiguous=False, carry_first_cell=None):
    t = orig(tok, previous_headers=previous_headers, previous_is_contiguous=previous_is_contiguous,
             carry_first_cell=carry_first_cell)
    toks = cur["tokens"]
    try:
        ti = toks.index(tok, cur["pos"])
    except ValueError:
        try:
            ti = toks.index(tok)
        except ValueError:
            ti = -1
    if ti >= 0:
        cur["pos"] = ti
    rows = [r for g in t.row_groups for r in g.rows]
    rec = {"doc": cur["doc"], "tok": ti, "contig": bool(previous_is_contiguous), "inherited": bool(t.inherited_headers),
           "explicit": bool(t.has_explicit_headers), "ncols": t.num_cols, "nhdr": len(t.headers),
           "headers": list(t.headers), "rows": rows[:3], "kinds": _col_kinds(rows),
           "had_prev_headers": bool(previous_headers), "prev_ncols": len(previous_headers or [])}
    # Replace an earlier record of the same token (carry undo re-parse)
    tabs = cur["tables"]
    if tabs and tabs[-1]["tok"] == ti and ti >= 0:
        tabs[-1] = rec
        log[-1] = rec
    else:
        tabs.append(rec)
        log.append(rec)
    return t


ch.parse_html_table = wrapped
docs = load_sfar_corpus(ROOT / "data" / "sfar_recommendations" / "output", updates_dir=ROOT / "data" / "corpus_updates")
opts = ch.ChunkOptions()
cases = []
rep = ch.NulRepairer()
for d in docs:
    text = d.text
    if opts.clean_ocr and "\x00" in text:
        text = rep(text)
    cur.update(doc=d.metadata.doc_id, tokens=re.split(r"(<table\b.*?</table>)", text, flags=re.S | re.I), pos=0, tables=[])
    ch._chunk_table_aware_sota(d, options=opts)
    tabs = cur["tables"]
    toks = cur["tokens"]
    for k, r in enumerate(tabs):
        if not r["had_prev_headers"] or r["explicit"]:
            continue
        # source = last earlier table with explicit headers (chunker keeps them per major section)
        src = next((tabs[j] for j in range(k - 1, -1, -1) if tabs[j]["explicit"]), None)
        prev = tabs[k - 1] if k else None
        gap_prev = "".join(toks[prev["tok"] + 1: r["tok"]]) if prev and prev["tok"] >= 0 and r["tok"] >= 0 else ""
        gap_src = "".join(toks[src["tok"] + 1: r["tok"]]) if src and src["tok"] >= 0 and r["tok"] >= 0 else ""
        between_tables = sum(1 for x in tabs[tabs.index(src) + 1: k]) if src else -1
        kp, ks = r["kinds"], (src["kinds"] if src else [])
        agree = (sum(a == b or "empty" in (a, b) for a, b in zip(kp, ks)) / max(1, len(kp))) if ks else None
        cases.append({
            "doc": r["doc"], "table_index": k, "contig": r["contig"], "inherited": r["inherited"],
            "ncols": r["ncols"], "src_ncols": src["ncols"] if src else None, "src_index": tabs.index(src) if src else None,
            "tables_between_src": between_tables, "gap_prev_kind": _gap_kind(gap_prev) if not r["contig"] else "nothing",
            "gap_prev_chars": len(gap_prev.strip()), "gap_src_chars": len(re.sub(r"<table\b.*?</table>", "", gap_src, flags=re.S).strip()),
            "kind_agreement": round(agree, 2) if agree is not None else None,
            "_headers": r["headers"], "_src_headers": src["headers"] if src else [], "_rows": r["rows"],
            "_src_rows": src["rows"][:2] if src else [], "_gap_prev": gap_prev.strip()[:600],
        })

abp = lambda doc: "antibioprophylaxie" in doc.lower()  # noqa: E731
nc = [c for c in cases if c["inherited"] and not c["contig"]]
summary = {
    "switch": SWITCH,
    "parse_calls": len(log),
    "inherited_total": sum(1 for x in log if x["inherited"]),
    "inherited_contiguous": sum(1 for x in log if x["inherited"] and x["contig"]),
    "inherited_non_contiguous": len(nc),
    "non_contiguous_abp": sum(abp(c["doc"]) for c in nc),
    "non_contiguous_other": sum(not abp(c["doc"]) for c in nc),
    "docs": len({c["doc"] for c in nc}),
    "gap_prev_kind": {g: dict(collections.Counter(c["gap_prev_kind"] for c in nc if abp(c["doc"]) == g2))
                      for g, g2 in (("abp", True), ("other", False))},
    "src_is_immediately_previous": {g: sum(c["tables_between_src"] == 0 for c in nc if abp(c["doc"]) == g2)
                                     for g, g2 in (("abp", True), ("other", False))},
    "ncols_equal_src": {g: sum(c["ncols"] == c["src_ncols"] for c in nc if abp(c["doc"]) == g2)
                        for g, g2 in (("abp", True), ("other", False))},
}
suffix = "_switch" if SWITCH else ""
(OUT / f"inheritance_summary{suffix}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
(OUT / f"inheritance_cases{suffix}.json").write_text(json.dumps(
    [{k: v for k, v in c.items() if not k.startswith("_")} for c in nc], ensure_ascii=False, indent=0))
(OUT / f"inheritance_cases_excerpts{suffix}.local.json").write_text(json.dumps(nc, ensure_ascii=False, indent=1))
print(json.dumps(summary, ensure_ascii=False, indent=1))
