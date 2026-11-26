"""05 - Tableaux : fréquence, types, problèmes (continuations entre pages, en-têtes, cellules
vides, rowspan/colspan, taille, encadrés de recommandation OCRisés en tableaux).

Relancer : .venv/bin/python reports/agents/data_audit_scripts/05_tables.py
Sorties  : out/tables.json (+ stdout)
"""
from __future__ import annotations

import collections
import json
import re
import statistics
from pathlib import Path

from common import OUT, ROOT, read

inv = json.loads((OUT / "inventory.json").read_text())["rows"]
TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)
STRENGTH = re.compile(r"il (?:ne )?faut|il (?:n'|n’)?est (?:probablement )?(?:pas )?recommand|les experts (?:sugg|propos|recommand)|nous (?:recommandons|sugg)", re.I)
RID = re.compile(r"(?<![\w.])R\s?\d+(?:\.\d+){0,3}\b")
GRADEW = re.compile(r"\bGRADE\s?[12]|\bG[12][+\-]|accord (?:fort|faible|relatif)|avis d.experts|●●", re.I)
DOSE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:mg|g|µg|μg|UI|U|mmol|ml|mL)(?:\s?/\s?(?:kg|h|j|24\s?h|m2))?\b")
DRUG = re.compile(r"\b(?:c[ée]fazoline|c[ée]furoxime|c[ée]foxitine|vancomycine|clindamycine|gentamicine|amoxicilline|m[ée]tronidazole|h[ée]parine|enoxaparine|apixaban|rivaroxaban|dabigatran|aspirine|clopidogrel|propofol|k[ée]tamine|morphine|sufentanil|rocuronium|sugammadex|noradr[ée]naline|ad[ée]naline|dexam[ée]thasone|ondans[ée]tron|parac[ée]tamol|tranexamique|fibrinog[èe]ne|insuline|lidoca[ïi]ne|ropivaca[ïi]ne|bupivaca[ïi]ne)\b", re.I)
EVID = re.compile(r"\b(?:RR|OR|HR|IC\s?95|IC95|p\s?[<=]|n\s?=|essai|étude|randomis|méta-analyse|cohorte)\b", re.I)
SCORE = re.compile(r"\b(?:score|classification|stade|échelle|critères|points?)\b", re.I)


def classify(tbl: str, txt: str, ncols: int) -> str:
    if (RID.search(txt) or STRENGTH.search(txt)) and (GRADEW.search(txt) or ncols <= 3):
        return "encadre_recommandation"
    if "checkbox" in tbl or re.search(r"\boui\b.*\bnon\b", txt, re.I) and ncols >= 2 and len(txt) < 1500:
        return "checklist_formulaire"
    if len(DOSE.findall(txt)) >= 2 and (DRUG.search(txt) or re.search(r"posolog|dose|bolus|perfusion|IVL|IVD|réinjection", txt, re.I)):
        return "posologie_therapeutique"
    if re.search(r"niveau de preuve|qualité des preuves|force de la recommandation|cotation|GRADE", txt, re.I) and not RID.search(txt):
        return "methodologie_gradation"
    if len(EVID.findall(txt)) >= 3:
        return "synthese_etudes"
    if SCORE.search(txt):
        return "score_classification_criteres"
    return "autre_descriptif"


tables = []
per_doc = []
for r in inv:
    t = read(ROOT / r["md"])
    ms = list(TABLE.finditer(t))
    prev_end = None
    prev_cols = None
    n_md_pipe = len(re.findall(r"(?m)^\|.*\|\s*$\n^\|\s*:?-{3,}", t))
    for m in ms:
        tbl = m.group(0)
        rows = re.findall(r"<tr\b.*?</tr>", tbl, re.S | re.I)
        cells_per_row = [len(re.findall(r"<t[dh]\b", row, re.I)) for row in rows]
        ncols = max(cells_per_row) if cells_per_row else 0
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tbl, re.S | re.I)
        empty = sum(1 for c in cells if not re.sub(r"<[^>]+>|\s|&nbsp;", "", c))
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", tbl))
        gap = t[prev_end:m.start()] if prev_end is not None else None
        has_head = bool(re.search(r"<thead|<th\b", tbl, re.I))
        contiguous = gap is not None and len(gap.strip()) == 0
        cont = contiguous and not has_head and prev_cols == ncols
        kind = classify(tbl, txt, ncols)
        line = t[:m.start()].count("\n") + 1
        tables.append({"md": r["md"], "line": line, "year": r["year_folder"], "rows": len(rows), "cols": ncols, "cells": len(cells),
                       "empty_cells": empty, "chars": len(tbl), "text_chars": len(txt), "has_header": has_head,
                       "rowspan": tbl.count("rowspan"), "colspan": tbl.count("colspan"), "contiguous_prev": contiguous,
                       "continuation_guess": cont, "kind": kind, "math": tbl.count("<math") + len(re.findall(r"\$[^$]{1,60}\$", tbl)),
                       "glued_after": bool(re.match(r"[^\n<\s]", t[m.end():m.end() + 1])), "preview": txt[:140]})
        prev_end, prev_cols = m.end(), ncols
    per_doc.append({"md": r["md"], "n_tables": len(ms), "md_pipe_tables": n_md_pipe,
                    "table_chars_share": round(sum(len(m.group(0)) for m in ms) / max(1, len(t)), 3)})

n = len(tables)
kinds = collections.Counter(x["kind"] for x in tables)
summary = {
    "tables": n,
    "docs_with_tables": sum(1 for d in per_doc if d["n_tables"]),
    "markdown_pipe_tables": sum(d["md_pipe_tables"] for d in per_doc),
    "with_header_th": sum(x["has_header"] for x in tables),
    "without_header": sum(not x["has_header"] for x in tables),
    "contiguous_with_previous": sum(x["contiguous_prev"] for x in tables),
    "continuation_guess_noheader_samecols": sum(x["continuation_guess"] for x in tables),
    "with_rowspan": sum(1 for x in tables if x["rowspan"]),
    "with_colspan": sum(1 for x in tables if x["colspan"]),
    "with_math_or_latex": sum(1 for x in tables if x["math"]),
    "empty_cells_share": round(sum(x["empty_cells"] for x in tables) / max(1, sum(x["cells"] for x in tables)), 3),
    "tables_gt_50pct_empty": sum(1 for x in tables if x["cells"] and x["empty_cells"] / x["cells"] > 0.5),
    "single_cell_tables": sum(1 for x in tables if x["cells"] == 1),
    "one_col_tables": sum(1 for x in tables if x["cols"] == 1),
    "text_chars_median": statistics.median(x["text_chars"] for x in tables),
    "text_chars_p90": sorted(x["text_chars"] for x in tables)[int(0.9 * n)],
    "tables_gt_2000_textchars(~500tok)": sum(1 for x in tables if x["text_chars"] > 2000),
    "tables_gt_6000_textchars(~1500tok)": sum(1 for x in tables if x["text_chars"] > 6000),
    "glued_text_after_table": sum(x["glued_after"] for x in tables),
    "kinds": kinds,
    "kinds_docs": {k: len({x["md"] for x in tables if x["kind"] == k}) for k in kinds},
    "table_char_share_corpus": round(sum(d["table_chars_share"] * r["chars"] for d, r in zip(per_doc, inv)) / sum(r["chars"] for r in inv), 3),
    "top_docs": sorted(((d["n_tables"], d["md"]) for d in per_doc), reverse=True)[:8],
    "examples": {k: [f"{x['md']}:{x['line']} «{x['preview'][:110]}»" for x in tables if x["kind"] == k][:3] for k in kinds},
    "continuation_examples": [f"{x['md']}:{x['line']} cols={x['cols']}" for x in tables if x["continuation_guess"]][:5],
}
(OUT / "tables.json").write_text(json.dumps({"summary": summary, "tables": tables}, ensure_ascii=False, indent=1, default=str))
print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
