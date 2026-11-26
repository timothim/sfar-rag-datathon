"""02 - Qualité OCR Chandra.

(a) Compteurs de défauts sur TOUT le corpus (caractères de contrôle, LaTeX, <math>, images
    avec texte alternatif généré, mermaid, cases à cocher, titres collés, en-têtes/pieds
    répétés, numéros de page, césures, phrases coupées, listes doublées, variantes d'unités,
    entités HTML).
(b) Échantillon stratifié de 16 documents (années / domaines / formes) : mêmes indicateurs
    + extraits pour inspection manuelle.
(c) Comparaison au PDF : les PDF de data/sfar_recommendations/output/pdfs/ sont des pointeurs
    Git LFS (≈130 octets) ; le seul PDF réel disponible est
    data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/RFE-antibioprophylaxie-SFAR-v2.0.pdf
    (V2.0, 91 p.), comparé page à page à la sortie Chandra de la V3.0 (pages 1-90 quasi
    inchangées hors changelog V3.0).

Relancer : .venv/bin/python reports/agents/data_audit_scripts/02_ocr_quality.py
Sorties  : out/ocr_quality.json (+ stdout)
"""
from __future__ import annotations

import collections
import json
import re
import statistics
import unicodedata
from pathlib import Path

from common import OUT, ROOT, read

inv = json.loads((OUT / "inventory.json").read_text())["rows"]

CHECKS = {
    "ctrl_or_nul": re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]"),
    "replacement_char": re.compile("�"),
    "private_use": re.compile("[-]"),
    "latex_inline": re.compile(r"\$[^$\n]{1,80}\$"),
    "math_tag": re.compile(r"<math\b"),
    "sup_tag": re.compile(r"<sup>"),
    "sub_tag": re.compile(r"<sub>"),
    "image_alt": re.compile(r"!\[[^\]]{3,}\]\([^)]+\)"),
    "mermaid_block": re.compile(r"```mermaid"),
    "checkbox": re.compile(r"<input type=\"checkbox\""),
    "glued_heading": re.compile(r"[^\n\s#|`/(\[]#{1,4} \S"),
    "table_then_text_glued": re.compile(r"</table>[^\n<]"),
    "html_entity": re.compile(r"&(?:gt|lt|amp|nbsp|quot);"),
    "hyphen_break": re.compile(r"\b[a-zàâçéèêëîïôûùüÿœ]{2,}- [a-zàâçéèêëîïôûùüÿœ]{3,}\b"),
    "double_numbering": re.compile(r"(?m)^\s*(\d+)\. \1\. "),
    "double_bullet": re.compile(r"(?m)^\s*- [-•●▪–◦■] "),
    "page_number_line": re.compile(r"(?m)^\s*(?:Page\s*)?\d{1,3}\s*(?:/\s*\d{1,3}|sur \d{1,3})?\s*$"),
    "ligature": re.compile("[ﬀ-ﬆ]"),
    "nbsp_like": re.compile("[   ]"),
}
UNITS = {
    "µg (micro sign U+00B5)": "µg",
    "μg (grec U+03BC)": "μg",
    "mcg": re.compile(r"\bmcg\b"),
    "mg/kg": re.compile(r"mg\s?/\s?kg"),
    "mg.kg-1 / mg·kg−1": re.compile(r"mg\s?[.·]\s?kg\s?[-−‐]1|mg\s?kg\s?[-−]1|mg\s?\.\s?kg\^\{-1\}|mg\s?\\cdot\s?kg"),
    "UI/kg": re.compile(r"(?:UI|U)\s?/\s?kg"),
    "≥ (unicode)": "≥",
    "\\geq (LaTeX)": "\\geq",
    ">= (ascii)": ">=",
    "décimale virgule (ex 0,5 mg)": re.compile(r"\b\d+,\d+\s?(?:mg|g|µg|μg|ml|mL|UI)\b"),
    "décimale point (ex 0.5 mg)": re.compile(r"\b\d+\.\d+\s?(?:mg|g|µg|μg|ml|mL|UI)\b"),
}


def cnt(rx, s):
    return s.count(rx) if isinstance(rx, str) else len(rx.findall(s))


def repeated_lines(text: str):
    c = collections.Counter()
    for line in text.split("\n"):
        l = line.strip()
        if 8 <= len(l) <= 120 and not l.startswith(("<", "|", "-", "*", "#")) and not re.match(r"^\d+[.)]", l):
            c[l] += 1
    return [(l, n) for l, n in c.most_common() if n >= 4]


def cut_sentences(text: str) -> int:
    """Paragraphe qui se termine sans ponctuation, suivi d'un paragraphe commençant en minuscule."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    n = 0
    for a, b in zip(paras, paras[1:]):
        if a.startswith(("<", "#", "|", "!")) or b.startswith(("<", "#", "|", "!", "-", "*")):
            continue
        if re.search(r"[a-zàâçéèêëîïôûùü,]$", a) and re.match(r"^[a-zàâçéèêëîïôûùü]", b):
            n += 1
    return n


rows = []
glob_c = collections.Counter()
docs_with = collections.Counter()
unit_c = collections.Counter()
unit_docs = collections.Counter()
rep_examples = []
for r in inv:
    t = read(ROOT / r["md"])
    d = {"md": r["md"], "year": r["year_folder"], "chars": r["chars"]}
    for k, rx in CHECKS.items():
        v = cnt(rx, t)
        d[k] = v
        glob_c[k] += v
        docs_with[k] += bool(v)
    for k, rx in UNITS.items():
        v = cnt(rx, t)
        unit_c[k] += v
        unit_docs[k] += bool(v)
    rl = repeated_lines(t)
    d["repeated_lines_types"] = len(rl)
    d["repeated_lines_occ"] = sum(n for _, n in rl)
    glob_c["repeated_lines_occ"] += d["repeated_lines_occ"]
    docs_with["repeated_lines_occ"] += bool(rl)
    if rl and len(rep_examples) < 40:
        rep_examples.append((r["md"], rl[:3]))
    d["cut_sentences"] = cut_sentences(t)
    glob_c["cut_sentences"] += d["cut_sentences"]
    docs_with["cut_sentences"] += bool(d["cut_sentences"])
    alt = re.findall(r"!\[([^\]]{3,})\]", t)
    d["image_alt_chars"] = sum(len(a) for a in alt)
    glob_c["image_alt_chars"] += d["image_alt_chars"]
    en_alt = sum(1 for a in alt if re.search(r"\b(the|with|and|showing|of a|icon|logo)\b", a, re.I))
    glob_c["image_alt_english"] += en_alt
    d["non_nfc"] = t != unicodedata.normalize("NFC", t)
    glob_c["non_nfc_docs"] += d["non_nfc"]
    rows.append(d)

# ---------------------------------------------------------------- (b) échantillon
SAMPLE = [
    "2000/2_SFAR_Corticotherapie", "2001/cc_pancreatiteaigue", "2002/86-civdccons", "2004/2b_AFAR_texte-long_Hemorragies",
    "2006/2_AFAR_Blocs-perimedullaires", "2008/3_REANIMATION_Prise-en-charge", "2010/2_SFAR_Anesthesie-loco-regionale",
    "2012/AFAR_Examens-preinterventionnels", "2014/2_REANIMATION_epuration", "2016/RFE-ANREA-Reactualisation",
    "2018/2_RFE-CURARE-3", "2019/rfe-trauma-abdominale", "2020/RFE_TSM_2020", "2022/RPP-Trauma-cranien-leger",
    "2023/RFE-antibioprophylaxie-2023_V3.0", "2024/240516-Txt-definitif", "2025/2025_SFAR-SFA_RFE-Diagnostic",
    "2026/RFE-Infections-intra-abdominales", "2026/TEXTE-RFE-ALR-PEDIA", "unknown/2b_AFAR_Texte-Long_Intubation",
]
sample_rows = []
for key in SAMPLE:
    y, stem = key.split("/", 1)
    hit = next((x for x in rows if x["md"].split("/")[4] == y and x["md"].split("/")[5].startswith(stem)), None)
    if hit:
        sample_rows.append(hit)

# ---------------------------------------------------------------- (c) PDF vs Chandra
pdf_cmp = {}
try:
    from pypdf import PdfReader
    pdfp = ROOT / "data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/RFE-antibioprophylaxie-SFAR-v2.0.pdf"
    mdp = next(ROOT.glob("data/sfar_recommendations/output/chandra/2023/RFE-antibioprophylaxie-2023_V3.0*/*.md"))
    W = re.compile(r"[a-z0-9àâçéèêëîïôûùüÿœ]+")

    def words(s):
        s = unicodedata.normalize("NFC", s).lower().replace("’", "'")
        s = re.sub(r"<[^>]+>", " ", s)
        s = s.replace("\\geq", "≥").replace("\\leq", "≤")
        return W.findall(s)

    mdw = words(read(mdp))
    md5 = set(tuple(mdw[i:i + 5]) for i in range(len(mdw) - 4))
    md_tokens = collections.Counter(mdw)
    NUMU = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:mg|g|µg|μg|ui|ml|h|kg|min)(?:/kg|/h|/j)?\b", re.I)
    md_text_norm = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", read(mdp))).replace(" ", " ")
    md_numu = collections.Counter(x.lower().replace(" ", "").replace(".", ",") for x in NUMU.findall(md_text_norm))
    reader = PdfReader(str(pdfp))
    per_page = []
    for i, pg in enumerate(reader.pages, 1):
        pt = pg.extract_text() or ""
        pw = words(pt)
        if len(pw) < 30:
            per_page.append({"page": i, "words": len(pw)})
            continue
        p5 = [tuple(pw[j:j + 5]) for j in range(len(pw) - 4)]
        rec5 = sum(1 for g in p5 if g in md5) / len(p5)
        vocab_rec = sum(1 for w in pw if md_tokens[w]) / len(pw)
        nu = [x.lower().replace(" ", "").replace(".", ",") for x in NUMU.findall(re.sub(r"\s+", " ", pt))]
        nu_rec = (sum(1 for x in nu if md_numu[x]) / len(nu)) if nu else None
        per_page.append({"page": i, "words": len(pw), "5gram_recall": round(rec5, 3), "word_recall": round(vocab_rec, 3),
                         "dose_tokens": len(nu), "dose_recall": round(nu_rec, 3) if nu_rec is not None else None,
                         "missing_words": [w for w in dict.fromkeys(pw) if not md_tokens[w]][:12]})
    valid = [p for p in per_page if "5gram_recall" in p]
    pdf_cmp = {
        "pdf": str(pdfp.relative_to(ROOT)), "md": str(mdp.relative_to(ROOT)), "pdf_pages": len(reader.pages),
        "pages_compared": len(valid),
        "median_5gram_recall": statistics.median(p["5gram_recall"] for p in valid),
        "median_word_recall": statistics.median(p["word_recall"] for p in valid),
        "pages_5gram_lt_0.7": [(p["page"], p["5gram_recall"]) for p in valid if p["5gram_recall"] < 0.7],
        "dose_tokens_total": sum(p["dose_tokens"] for p in valid),
        "dose_recall_weighted": round(sum((p["dose_recall"] or 0) * p["dose_tokens"] for p in valid) / max(1, sum(p["dose_tokens"] for p in valid)), 3),
        "per_page": per_page,
    }
except Exception as ex:  # noqa: BLE001
    pdf_cmp = {"error": repr(ex)}

summary = {
    "corpus_totals": dict(glob_c), "docs_with_defect": dict(docs_with), "units_occurrences": dict(unit_c),
    "units_docs": dict(unit_docs),
    "top_repeated_lines_examples": rep_examples[:25],
    "worst_docs": {k: sorted(((x[k], x["md"]) for x in rows), reverse=True)[:5] for k in
                   ["ctrl_or_nul", "repeated_lines_occ", "cut_sentences", "hyphen_break", "glued_heading", "latex_inline", "image_alt"]},
    "sample": sample_rows,
    "pdf_comparison": {k: v for k, v in pdf_cmp.items() if k != "per_page"},
}
(OUT / "ocr_quality.json").write_text(json.dumps({"summary": summary, "rows": rows, "pdf_per_page": pdf_cmp.get("per_page")}, ensure_ascii=False, indent=1, default=str))
print(json.dumps({k: v for k, v in summary.items() if k not in ("sample", "top_repeated_lines_examples")}, ensure_ascii=False, indent=1, default=str))
print("\nÉchantillon :")
cols = ["chars", "ctrl_or_nul", "latex_inline", "math_tag", "image_alt", "glued_heading", "repeated_lines_occ", "page_number_line", "hyphen_break", "cut_sentences", "double_numbering", "double_bullet", "html_entity"]
print("doc".ljust(48), " ".join(c[:9].rjust(9) for c in cols))
for s in sample_rows:
    print(Path(s["md"]).parent.name[:46].ljust(48), " ".join(str(s[c]).rjust(9) for c in cols))
print("\nLignes répétées (exemples) :")
for md, rl in rep_examples[:20]:
    print(" ", Path(md).parent.name[:50], [(l[:60], n) for l, n in rl[:2]])
if pdf_cmp.get("per_page"):
    print("\nPDF V2.0 vs Chandra V3.0, pages à faible recouvrement :")
    for p in pdf_cmp["per_page"]:
        if p.get("5gram_recall") is not None and (p["5gram_recall"] < 0.7 or (p["dose_recall"] is not None and p["dose_recall"] < 0.85)):
            print("  p", p["page"], p["5gram_recall"], p["word_recall"], p["dose_tokens"], p["dose_recall"], p["missing_words"][:8])
