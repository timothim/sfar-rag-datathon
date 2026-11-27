"""K1 — Structural audit of the frozen index `index/tas_v6` for the non-antibioprophylaxis corpus.

Read-only: reads `index/tas_v6/metadata.sqlite` and the source Markdown paths recorded in it.
Writes JSON/TSV outputs next to this script. No model, no GPU.

Usage: .venv/bin/python -I reports/agents/K1_annexes/corpus_structure_audit.py
"""

from __future__ import annotations

import collections
import json
import re
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DB = ROOT / "index" / "tas_v6" / "metadata.sqlite"

# ---------------------------------------------------------------- patterns (generic, corpus-level)
# Grade formats captured by the chunker (copy of chunker.GRADE_RE, frozen code not imported).
GRADE_CAPTURED = re.compile(
    r"\b(?:GRADE\s*[12]\s*[+\-]?|Avis\s+d['’]experts?|Accord\s+(?:FORT|FAIBLE|fort|faible)|"
    r"Recommandation\s+(?:forte|faible))\b",
    re.I,
)
# Grade formats that exist in SFAR/HAS texts across periods (broader).
GRADE_ANY = re.compile(
    r"(?:\bGRADE\s*[12]\s*[+\-]?|\bG\s?[12]\s?[+\-−]|\(\s*[12]\s?[+\-−]\s*\)|\bAvis\s+d['’]experts?\b|"
    r"\bAccord\s+(?:fort|faible|relatif|professionnel|d['’]experts?)\b|\bRecommandation\s+(?:forte|faible)\b|"
    r"\bgrade\s+[ABCDE]\b|\(\s*[ABC]\s*\)|\bniveau\s+de\s+preuve\s+[1-4IV]+\b|\bAE\b|\bRPC?\s+[A-C]\b|"
    r"\b[Aa]ccord\s+(?:FORT|FAIBLE)\b|\bGRADE\s+(?:fort|faible)\b|\bconsensus\s+(?:fort|faible)\b)",
    re.I,
)
GRADE_NOT_CAPTURED_FORMS = {
    "G1+/G2- (lettre G)": re.compile(r"\bG\s?[12]\s?[+\-−](?![\w])"),
    "(1+)/(2-) seul": re.compile(r"\(\s*[12]\s?[+\-−]\s*\)"),
    "grade A/B/C/E": re.compile(r"\bgrade\s+[ABCDE]\b", re.I),
    "accord professionnel/relatif": re.compile(r"\baccord\s+(?:professionnel|relatif)\b", re.I),
    "AE (sigle avis d'experts)": re.compile(r"(?<![\w-])AE(?![\w-])"),
}
REC_ID_RE = re.compile(r"\bR\d+(?:\.\d+){1,2}\b")
# A statement start: an R-id at the start of a line (optionally bold), followed by a separator.
REC_STMT_RE = re.compile(
    r"(?m)^[ \t>*_\-#•]*(?:\*\*)?\s*(R\s?\d+(?:\.\d+){0,2}|Recommandation\s+\d+(?:\.\d+){0,2})\s*(?:\*\*)?\s*[–—\-:.)]?\s*(?:\*\*)?\s*(?=[A-ZÀ-Ýa-zé«(])"
)
# Unnumbered recommendation formulae (FR + EN).
RECO_VERB_RE = re.compile(
    r"\b(?:il\s+est\s+(?:probablement\s+)?recommand[ée]|il\s+n['’]est\s+(?:probablement\s+)?pas\s+recommand[ée]|"
    r"les\s+experts\s+(?:sugg[èe]rent|recommandent|proposent)|il\s+(?:ne\s+)?faut\s+(?:probablement\s+)?(?:pas\s+)?|"
    r"we\s+(?:recommend|suggest)|the\s+experts\s+suggest|il\s+est\s+(?:possible|sugg[ée]r[ée]))\b",
    re.I,
)
ARG_MARK_RE = re.compile(r"(?im)^\W*(?:Argumentaire|Rationnel|Justification|Rationale)\b")
BIBLIO_LINE_RE = re.compile(
    r"(?m)(?:^\s*(?:-\s*)?(?:\[\d+\]|\d{1,3}[.)]\s+[A-Z][\w'’-]+\s+[A-Z]{1,3}\b)|\bet\s+al\b\.?|\bdoi[:\s]|"
    r"\b(?:19|20)\d{2}\s*;\s*\d+\s*(?:\(\d+\))?\s*:\s*\d)"
)
CLINICAL_RE = re.compile(
    r"(?:\bR\d+\.\d+(?:\.\d+)?\s*[–\-:]|il\s+est\s+(?:probablement\s+)?recommand[ée]|"
    r"les\s+experts\s+sugg[èe]rent|\bGRADE\s*[12]|\bmg/kg\b|\bposologie\b)",
    re.I,
)
IMAGE_MARK_RE = re.compile(r"\[Image, description automatique")
MERMAID_MARK_RE = re.compile(r"\[Organigramme")
FIG_CAPTION_RE = re.compile(r"(?im)^\W*(?:Figure|Fig\.|Algorithme|Arbre d[ée]cisionnel|Annexe)\s*\d*\s*[:.\-–]")
TABLE_CAPTION_RE = re.compile(r"(?im)^\W*Tableau\s*[IVX\d]+")
EN_STOP = re.compile(r"\b(?:the|and|of|with|for|patients|should|were|was|is|are|in)\b")
FR_STOP = re.compile(r"\b(?:le|la|les|des|et|du|une|chez|est|sont|dans|pour)\b")


def lang_of(text: str) -> str:
    en = len(EN_STOP.findall(text.lower()))
    fr = len(FR_STOP.findall(text.lower()))
    if en + fr < 8:
        return "?"
    return "en" if en > 2 * fr else ("fr" if fr > 2 * en else "mix")


def is_abp(title: str, doc_id: str) -> bool:
    s = (title + " " + doc_id).lower()
    return "antibioprophylax" in s


def biblio_hits(text: str) -> int:
    return len(BIBLIO_LINE_RE.findall(text))


def load():
    con = sqlite3.connect(DB)
    docs = {}
    for doc_id, payload in con.execute("select doc_id, payload_json from documents"):
        docs[doc_id] = json.loads(payload)
    chunks = collections.defaultdict(list)
    for idx, cid, doc_id, ctype, is_ref, payload in con.execute(
        "select idx, chunk_id, doc_id, chunk_type, is_reference_section, payload_json from chunks order by idx"
    ):
        p = json.loads(payload)
        p["_idx"] = idx
        p["_is_ref"] = bool(is_ref)
        chunks[doc_id].append(p)
    for v in chunks.values():
        v.sort(key=lambda c: c["chunk_index"])
    return docs, chunks


def classify(meta: dict, m: dict) -> str:
    role = meta.get("doc_role", "")
    if is_abp(meta.get("title", ""), meta["doc_id"]):
        return "0_ABP"
    if meta.get("language") == "en" or role == "traduction_en":
        return "E_anglais"
    if role in ("algorithme", "aide_cognitive", "tableaux_synthese", "annexe") or m["src_chars"] < 15000:
        return "F_fiche_algo_annexe"
    if m["table_share"] >= 0.35:
        return "T_tableaux_dominants"
    if m["n_rec_stmt"] >= 3:
        return "G1_gradee_numerotee"
    if m["n_grade_any"] >= 5:
        return "G2_gradee_sans_numero"
    if (meta.get("effective_year") or 0) <= 2010:
        return "O_ancienne_non_gradee"
    return "X_recente_non_gradee"


def doc_metrics(meta: dict, cs: list[dict]) -> dict:
    flow = [c for c in cs if c["chunk_type"] in ("prose", "recommendation_box", "callout_footnote", "callout_allergy")]
    flow_text = "\n".join(c["text"] for c in flow if not c["_is_ref"])
    tm_chars = sum(len(c["text"]) for c in cs if c["chunk_type"] == "table_markdown")
    prose_chars = sum(len(c["text"]) for c in flow if not c["_is_ref"])
    ref_chars = sum(len(c["text"]) for c in cs if c["_is_ref"])
    lens = [len(c["text"]) for c in cs if not c["_is_ref"]]
    secs = [c["section_path"] for c in cs if not c["_is_ref"]]
    sec_counter = collections.Counter(secs)
    m = {
        "n_chunks": len(cs),
        "by_type": dict(collections.Counter(c["chunk_type"] for c in cs)),
        "src_chars": meta.get("char_count") or 0,
        "table_share": tm_chars / max(1, tm_chars + prose_chars),
        "ref_share_chars": ref_chars / max(1, ref_chars + tm_chars + prose_chars),
        "n_rec_stmt": len(REC_STMT_RE.findall(flow_text)),
        "n_rec_ids_any": len(set(REC_ID_RE.findall(flow_text))),
        "n_grade_any": len(GRADE_ANY.findall(flow_text)),
        "n_grade_captured": len(GRADE_CAPTURED.findall(flow_text)),
        "n_reco_verbs": len(RECO_VERB_RE.findall(flow_text)),
        "n_images": sum(len(IMAGE_MARK_RE.findall(c["text"])) for c in cs),
        "n_mermaid": sum(len(MERMAID_MARK_RE.findall(c["text"])) for c in cs),
        "n_fig_captions": len(FIG_CAPTION_RE.findall(flow_text)),
        "n_table_captions_prose": len(TABLE_CAPTION_RE.findall(flow_text)),
        "n_sections": len(sec_counter),
        "top_section_share": (sec_counter.most_common(1)[0][1] / len(secs)) if secs else 0,
        "empty_section_share": (sec_counter.get("", 0) / len(secs)) if secs else 0,
        "len_median": statistics.median(lens) if lens else 0,
        "short_lt150": sum(1 for x in lens if x < 150),
        "long_gt2000": sum(1 for x in lens if x > 2000),
        "n_nonref": len(lens),
        "lang_chunks": dict(collections.Counter(lang_of(c["text"]) for c in flow if not c["_is_ref"])),
    }
    for name, rx in GRADE_NOT_CAPTURED_FORMS.items():
        m["form:" + name] = len(rx.findall(flow_text))
    return m


GRADE_NEAR_RE = GRADE_ANY


def reco_integrity(meta: dict, cs: list[dict], examples: dict) -> collections.Counter:
    """For each numbered recommendation statement in the reading flow: is its grade in the same
    chunk before the next statement? Is the chunk typed recommendation_box? Are several statements
    merged? Does the chunk's grade_levels match? Is the chunk mostly argument text?"""
    cnt = collections.Counter()
    flow = [c for c in cs if c["chunk_type"] in ("prose", "recommendation_box", "callout_footnote") and not c["_is_ref"]]
    for i, c in enumerate(flow):
        t = c["text"]
        stmts = list(REC_STMT_RE.finditer(t))
        if not stmts:
            if c["chunk_type"] == "prose" and c.get("grade_levels"):
                cnt["prose_with_grade_levels"] += 1
                if not RECO_VERB_RE.search(t):
                    cnt["prose_with_grade_levels_no_reco_formula"] += 1
                    examples["grade_on_non_statement"].append((c["chunk_id"], c["section_path"][:80], c["grade_levels"]))
            continue
        cnt["chunks_with_stmt"] += 1
        ids = list(dict.fromkeys(s.group(1) for s in stmts))
        for sid in ids:
            cnt["stmt_ids"] += 1
            if not REC_ID_RE.fullmatch(sid):
                cnt["stmt_id_format_not_captured_by_chunker"] += 1
                if len(examples["id_not_captured"]) < 200:
                    examples["id_not_captured"].append((c["chunk_id"], sid, c["chunk_type"]))
        if len(ids) >= 2:
            cnt["chunks_with_ge2_stmts"] += 1
            cnt["stmts_in_merged_chunks"] += len(ids)
        if c["chunk_type"] != "recommendation_box":
            cnt["stmt_chunk_not_rec_box"] += 1
            examples["stmt_not_box"].append((c["chunk_id"], ids[:3], c["chunk_type"]))
        # chunk starts with references (glued bibliography)
        head = t[: stmts[0].start()]
        if biblio_hits(head) >= 1:
            cnt["stmt_chunk_with_biblio_before"] += 1
            examples["biblio_glued"].append((c["chunk_id"], ids[:2]))
        # grade per statement
        grades_found = []
        for k, s in enumerate(stmts):
            end = stmts[k + 1].start() if k + 1 < len(stmts) else len(t)
            seg = t[s.start():end]
            cnt["stmts"] += 1
            g = GRADE_NEAR_RE.search(seg)
            if g:
                cnt["stmt_grade_same_chunk"] += 1
                grades_found.append(g.group(0))
                if not GRADE_CAPTURED.search(seg):
                    cnt["stmt_grade_format_not_captured"] += 1
                    examples["grade_not_captured"].append((c["chunk_id"], s.group(1), g.group(0)))
            elif k + 1 == len(stmts):
                nxt = flow[i + 1]["text"][:400] if i + 1 < len(flow) else ""
                if GRADE_NEAR_RE.search(nxt) and not REC_STMT_RE.search(nxt[: GRADE_NEAR_RE.search(nxt).start()]):
                    cnt["stmt_grade_in_next_chunk"] += 1
                    examples["grade_split"].append((c["chunk_id"], s.group(1)))
                elif re.search(r"absence\s+de\s+recommandation|pas\s+de\s+recommandation", seg, re.I):
                    cnt["stmt_absence_de_reco"] += 1
                else:
                    cnt["stmt_no_grade_found"] += 1
                    examples["no_grade"].append((c["chunk_id"], s.group(1)))
            else:
                if re.search(r"absence\s+de\s+recommandation|pas\s+de\s+recommandation", seg, re.I):
                    cnt["stmt_absence_de_reco"] += 1
                else:
                    cnt["stmt_no_grade_found"] += 1
                    examples["no_grade"].append((c["chunk_id"], s.group(1)))
        # argument share inside a recommendation_box
        if c["chunk_type"] == "recommendation_box":
            cnt["rec_box"] += 1
            am = ARG_MARK_RE.search(t, stmts[0].start())
            if am:
                tail = len(t) - am.end()
                if tail > 300:
                    cnt["rec_box_with_argument_tail_gt300"] += 1
                    examples["box_with_argument"].append((c["chunk_id"], ids[:2], tail))
            if len(ids) >= 2:
                gl = c.get("grade_levels") or []
                distinct = {re.sub(r"\s+", " ", g.lower()) for g in gl}
                if len(distinct) >= 2:
                    cnt["rec_box_ge2_stmts_mixed_grades"] += 1
                    examples["mixed_grades"].append((c["chunk_id"], ids[:4], gl[:4]))
    for c in cs:
        if c["chunk_type"] == "callout_footnote" and not c["_is_ref"] and (RECO_VERB_RE.search(c["text"]) or GRADE_ANY.search(c["text"])):
            cnt["footnote_typed_with_reco_or_grade"] += 1
            examples["footnote_reco"].append((c["chunk_id"], c["section_path"][:60]))
        parts = [x.strip() for x in c["section_path"].split(" > ") if x.strip()]
        keys = [re.sub(r"[\d.IVX]+", "#", re.split(r"[:.\-–]", x)[0].upper())[:20] for x in parts]
        if any(keys[k] == keys[k + 1] and re.search(r"\d|[IVX]", parts[k]) for k in range(len(keys) - 1)):
            cnt["section_path_sibling_stacked"] += 1
            if len(examples["sibling_stacked"]) < 40:
                examples["sibling_stacked"].append((c["chunk_id"], c["section_path"][:120]))
        if len(parts) >= 5:
            cnt["section_path_depth_ge5"] += 1
    # statements written as Markdown headings (would be in section_path, not text)
    for c in cs:
        sp = c["section_path"]
        if re.search(r"(?:^|> )\s*R\d+(?:\.\d+){1,2}\s*[–\-:.]", sp):
            cnt["chunks_under_stmt_heading"] += 1
    return cnt


def reference_audit(cs: list[dict], examples: dict) -> collections.Counter:
    cnt = collections.Counter()
    for c in cs:
        t = c["text"]
        if c["_is_ref"]:
            cnt["ref_flagged"] += 1
            continue
        if c["chunk_type"] in ("table_row_card", "table_markdown"):
            continue
        h = biblio_hits(t)
        lines = [ln for ln in t.splitlines() if ln.strip()]
        dense = h >= 3 and h / max(1, len(lines)) >= 0.5
        if dense and not CLINICAL_RE.search(t):
            cnt["unflagged_biblio_like"] += 1
            examples["unflagged_biblio"].append((c["chunk_id"], c["section_path"][:60], h))
        elif h >= 3 and CLINICAL_RE.search(t):
            cnt["clinical_chunk_with_ge3_biblio_lines"] += 1
    return cnt


def table_audit(cs: list[dict], examples: dict) -> collections.Counter:
    cnt = collections.Counter()
    by_table = collections.defaultdict(list)
    for c in cs:
        if c["chunk_type"] in ("table_markdown", "callout_allergy") and c.get("table_id"):
            by_table[c["table_id"]].append(c)
        if c["chunk_type"] == "table_row_card":
            cnt["row_cards"] += 1
            body = c["text"]
            if re.search(r" — ", body) and " : " not in body.split("\n")[-1]:
                cnt["row_cards_headerless"] += 1
            if len(body) > 1800:
                cnt["row_cards_gt1800"] += 1
    for tid, parts in by_table.items():
        cnt["tables"] += 1
        has_sep = ["| ---" in p["text"] or "|---" in p["text"] for p in parts]
        if not any(has_sep):
            cnt["tables_no_header_row"] += 1
        if len(parts) > 1:
            cnt["tables_split_in_parts"] += 1
            if not all(has_sep):
                cnt["tables_split_some_part_without_header"] += 1
        rows = sum(p["text"].count("\n|") for p in parts)
        if rows <= 1:
            cnt["tables_le1_row"] += 1
        n_cards = sum(1 for c in cs if c["chunk_type"] == "table_row_card" and c.get("table_id") == tid)
        if n_cards == 0:
            cnt["tables_without_cards"] += 1
    # tables that are images: image descriptions mentioning table
    for c in cs:
        for m in re.finditer(r"\[Image, description automatique en anglais : ([^\]]{0,300})", c["text"]):
            if re.search(r"\btable\b|\btabular\b|\bgrid\b|\brows?\b|\bcolumns?\b", m.group(1), re.I):
                cnt["image_described_as_table"] += 1
                examples["table_as_image"].append((c["chunk_id"], m.group(1)[:90]))
    return cnt


def main() -> None:
    docs, chunks = load()
    rows = []
    cls_docs = collections.defaultdict(list)
    examples_by_cls = collections.defaultdict(lambda: collections.defaultdict(list))
    agg = collections.defaultdict(collections.Counter)
    for doc_id, meta in docs.items():
        cs = chunks.get(doc_id, [])
        m = doc_metrics(meta, cs)
        cls = classify(meta, m)
        m.update(
            doc_id=doc_id, cls=cls, title=meta.get("title", ""), year=meta.get("effective_year"),
            doc_type=meta.get("doc_type"), role=meta.get("doc_role"), language=meta.get("language"),
            latest=bool(meta.get("is_latest_edition")), active=bool(meta.get("is_active")),
        )
        ex = examples_by_cls[cls]
        ri = reco_integrity(meta, cs, ex)
        ra = reference_audit(cs, ex)
        ta = table_audit(cs, ex)
        m["reco"] = dict(ri)
        m["refs"] = dict(ra)
        m["tables"] = dict(ta)
        rows.append(m)
        cls_docs[cls].append(m)
        key = cls + ("" if m["latest"] and m["active"] else "|ancienne")
        for d in (ri, ra, ta):
            agg[cls].update(d)
        agg[cls]["docs"] += 1
        agg[cls]["docs_current"] += int(m["latest"] and m["active"])
        agg[cls]["chunks"] += m["n_chunks"]
        agg[cls]["nonref_chunks"] += m["n_nonref"]
        agg[cls]["short_lt150"] += m["short_lt150"]
        agg[cls]["long_gt2000"] += m["long_gt2000"]
        agg[cls]["images"] += m["n_images"]
        agg[cls]["mermaid"] += m["n_mermaid"]
        agg[cls]["fig_captions"] += m["n_fig_captions"]
        agg[cls]["docs_one_section_ge80pct"] += int(m["top_section_share"] >= 0.8 and m["n_nonref"] >= 10)
        agg[cls]["docs_with_images"] += int(m["n_images"] > 0)
        agg[cls]["docs_with_fig_caption_no_image_no_mermaid"] += int(m["n_fig_captions"] > 0 and m["n_images"] == 0 and m["n_mermaid"] == 0)
        for k, v in m.items():
            if k.startswith("form:"):
                agg[cls][k] += v
        for k, v in m["by_type"].items():
            agg[cls]["type:" + k] += v
        for k, v in m["lang_chunks"].items():
            agg[cls]["lang:" + k] += v
    (OUT / "doc_metrics.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    summary = {cls: dict(sorted(c.items())) for cls, c in sorted(agg.items())}
    (OUT / "class_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    ex_out = {cls: {k: v[:25] for k, v in d.items()} for cls, d in examples_by_cls.items()}
    (OUT / "examples.json").write_text(json.dumps(ex_out, ensure_ascii=False, indent=1))
    with open(OUT / "typology.tsv", "w") as f:
        f.write("cls\tdoc_id\tyear\trole\tlang\tcurrent\ttable_share\tn_rec_stmt\tn_grade_any\tn_grade_captured\tn_reco_verbs\tn_images\tn_mermaid\tn_sections\ttop_section_share\tn_chunks\n")
        for m in sorted(rows, key=lambda r: (r["cls"], r["year"] or 0)):
            f.write(
                f"{m['cls']}\t{m['doc_id']}\t{m['year']}\t{m['role']}\t{m['language']}\t{int(m['latest'] and m['active'])}\t"
                f"{m['table_share']:.2f}\t{m['n_rec_stmt']}\t{m['n_grade_any']}\t{m['n_grade_captured']}\t{m['n_reco_verbs']}\t"
                f"{m['n_images']}\t{m['n_mermaid']}\t{m['n_sections']}\t{m['top_section_share']:.2f}\t{m['n_chunks']}\n"
            )
    for cls, c in summary.items():
        print(cls, json.dumps(c, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
