"""D1 - Audit of unit / magnitude corruption in doses across the SFAR corpus.

Read-only: scans the Chandra Markdown (and the corpus_updates overlay) and writes
candidate lists to reports/agents/D1_annexes/. Detectors are generic (corpus structure
and pharmacological plausibility); none uses an evaluation question.

Usage: .venv/bin/python reports/agents/D1_annexes/detect_doses.py
"""
from __future__ import annotations

import collections
import csv
import html
import json
import math
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHANDRA = ROOT / "data/sfar_recommendations/output/chandra"
OVERLAY = ROOT / "data/corpus_updates"
OUT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Drug lexicon: plausible ranges come from the auditor's pharmacological knowledge
# (standard anaesthesia / ICU / paediatric posology), NOT from the corpus.
# Units: µg for "abs", µg/kg for "kg", µg/kg/min for "kg_min", µg/kg/h for "kg_h",
# µg/min for "min", µg/h for "h". A range is deliberately wide (covers adult, child,
# neonate, all routes incl. intrathecal / intratracheal); only >=10-fold excursions are flagged.
# "micro" = drug usually dosed in micrograms (used by the micro-sign-absence detector).
# ---------------------------------------------------------------------------
MG = 1000.0
DRUGS: dict[str, dict] = {
    "adrénaline": dict(pat=r"(?<!nor)(?<!nor-)adr[ée]naline|(?<!nor)[ée]pin[ée]phrine", micro=True,
                       kg=(0.5, 100), kg_min=(0.005, 3), abs=(1, 5 * MG), min=(0.5, 50), h=(30, 5 * MG)),
    "noradrénaline": dict(pat=r"noradr[ée]naline|nor[ée]pin[ée]phrine", micro=True,
                          kg=(0.02, 10), kg_min=(0.005, 5), abs=(1, 100), min=(0.5, 100), h=(30, 10 * MG), infusion=True),
    "fentanyl": dict(pat=r"(?<!su)(?<!re)(?<!al)fentanyl", micro=True,
                     kg=(0.1, 50), kg_h=(0.2, 10), abs=(5, 2 * MG), h=(5, 300)),
    "sufentanil": dict(pat=r"sufentanil", micro=True, kg=(0.02, 5), kg_h=(0.05, 2), abs=(0.5, 150), h=(1, 100)),
    "rémifentanil": dict(pat=r"r[ée]mifentanil", micro=True, kg=(0.1, 5), kg_min=(0.01, 2), abs=(5, 500)),
    "alfentanil": dict(pat=r"alfentanil", micro=True, kg=(2, 100), abs=(100, 5 * MG)),
    "clonidine": dict(pat=r"clonidine", micro=True, kg=(0.3, 5), kg_h=(0.1, 2), abs=(10, 600)),
    "dexmédétomidine": dict(pat=r"dexm[ée]d[ée]tomidine", micro=True, kg=(0.1, 4), kg_h=(0.1, 2), abs=(5, 200)),
    "atropine": dict(pat=r"atropine", micro=True, kg=(5, 50), abs=(50, 3 * MG)),
    "isoprénaline": dict(pat=r"isopr[ée]naline|isoprot[ée]r[ée]nol", micro=True, kg_min=(0.005, 0.5), min=(0.5, 20), abs=(1, 2 * MG), infusion=True),
    "dobutamine": dict(pat=r"dobutamine", micro=True, kg_min=(1, 40), infusion=True),
    "dopamine": dict(pat=r"(?<!do)(?<!bu)dopamine", micro=True, kg_min=(1, 30), infusion=True),
    "phényléphrine": dict(pat=r"ph[ée]nyl[ée]phrine|n[ée]osyn[ée]phrine", micro=True, kg=(0.5, 10), kg_min=(0.05, 5), abs=(10, 1 * MG), min=(5, 200)),
    "glycopyrronium": dict(pat=r"glycopyrr", micro=True, kg=(2, 20), abs=(50, 1 * MG)),
    "naloxone": dict(pat=r"naloxone", micro=True, kg=(0.5, 100), kg_h=(0.2, 20), abs=(10, 4 * MG)),
    "desmopressine": dict(pat=r"desmopressine|ddavp", micro=True, kg=(0.1, 1), abs=(0.5, 40)),
    "flumazénil": dict(pat=r"flumaz[ée]nil", micro=True, kg=(2, 30), abs=(50, 2 * MG)),
    "carbétocine": dict(pat=r"carb[ée]tocine", micro=True, abs=(20, 200)),
    "sulprostone": dict(pat=r"sulprostone", micro=True, abs=(50, 1500), h=(20, 600)),
    "misoprostol": dict(pat=r"misoprostol", micro=True, abs=(25, 1 * MG)),
    "milrinone": dict(pat=r"milrinone", micro=True, kg=(10, 100), kg_min=(0.1, 1)),
    "lévosimendan": dict(pat=r"l[ée]vosimendan", micro=True, kg=(3, 30), kg_min=(0.02, 0.4)),
    "salbutamol": dict(pat=r"salbutamol", micro=True, kg=(1, 300), kg_min=(0.05, 5), abs=(50, 10 * MG)),
    "néostigmine": dict(pat=r"n[ée]ostigmine", micro=True, kg=(10, 80), abs=(250, 5 * MG)),
    "dropéridol": dict(pat=r"drop[ée]ridol|dehydrobenzperidol", micro=True, kg=(5, 75), abs=(100, 5 * MG)),
    "buprénorphine": dict(pat=r"bupr[ée]norphine", micro=True, kg=(1, 20), abs=(50, 32 * MG)),
    "trinitrine": dict(pat=r"trinitrine|nitroglyc[ée]rine", micro=True, kg_min=(0.1, 10), abs=(50, 5 * MG)),
    # mg-family controls (same machinery, to catch mg->g, decimal losses and the reverse error)
    "morphine": dict(pat=r"(?<!hydro)(?<!dihydro)morphine", kg=(5, 500), kg_h=(5, 100), abs=(25, 60 * MG), h=(100, 10 * MG)),
    "kétamine": dict(pat=r"k[ée]tamine", kg=(50, 10 * MG), kg_h=(30, 3 * MG), kg_min=(0.5, 50), abs=(2.5 * MG, 1000 * MG)),
    "propofol": dict(pat=r"propofol", kg=(200, 5 * MG), kg_h=(500, 15 * MG), kg_min=(10, 300), abs=(5 * MG, 600 * MG)),
    "midazolam": dict(pat=r"midazolam", kg=(10, 600), kg_h=(10, 300), abs=(250, 50 * MG), h=(250, 20 * MG)),
    "rocuronium": dict(pat=r"rocuronium", kg=(100, 1.5 * MG), abs=(5 * MG, 200 * MG)),
    "suxaméthonium": dict(pat=r"succinylcholine|suxam[ée]thonium|c[ée]locurine", kg=(500, 4 * MG), abs=(10 * MG, 200 * MG)),
    "sugammadex": dict(pat=r"sugammadex", kg=(1 * MG, 16 * MG)),
    "étomidate": dict(pat=r"[ée]tomidate", kg=(100, 600)),
    "thiopental": dict(pat=r"thiopental|penthotal", kg=(1 * MG, 10 * MG)),
    "lidocaïne": dict(pat=r"lidoca[iï]ne|xyloca[iï]ne", kg=(200, 7 * MG), kg_h=(300, 3 * MG), kg_min=(5, 50), abs=(10 * MG, 500 * MG)),
    "bupivacaïne": dict(pat=r"(?<!l[ée]vo)(?<!levo)bupivaca[iï]ne", kg=(100, 3 * MG), abs=(1 * MG, 200 * MG)),
    "lévobupivacaïne": dict(pat=r"l[ée]vobupivaca[iï]ne", kg=(100, 3 * MG), abs=(1 * MG, 200 * MG)),
    "ropivacaïne": dict(pat=r"ropivaca[iï]ne", kg=(100, 4 * MG), abs=(1 * MG, 300 * MG)),
    "paracétamol": dict(pat=r"parac[ée]tamol|ac[ée]taminoph[eè]ne", kg=(5 * MG, 25 * MG), abs=(100 * MG, 4000 * MG)),
    "ibuprofène": dict(pat=r"ibuprof[eè]ne", kg=(3 * MG, 15 * MG), abs=(100 * MG, 2400 * MG)),
    "kétoprofène": dict(pat=r"k[ée]toprof[eè]ne", kg=(0.5 * MG, 2 * MG), abs=(25 * MG, 300 * MG)),
    "tramadol": dict(pat=r"tramadol", kg=(0.5 * MG, 3 * MG), abs=(25 * MG, 600 * MG)),
    "néfopam": dict(pat=r"n[ée]fopam", abs=(5 * MG, 120 * MG)),
    "dexaméthasone": dict(pat=r"dexam[ée]thasone", kg=(50, 1 * MG), abs=(0.5 * MG, 40 * MG)),
    "ondansétron": dict(pat=r"ondans[ée]tron", kg=(50, 200), abs=(1 * MG, 16 * MG)),
    "acide tranexamique": dict(pat=r"acide tranexamique|tranexamic|exacyl", kg=(5 * MG, 100 * MG), kg_h=(0.5 * MG, 20 * MG), abs=(0.5 * MG * 1000 / 1000 * 100, 4000 * MG)),
    "amiodarone": dict(pat=r"amiodarone|cordarone", kg=(2 * MG, 10 * MG), abs=(50 * MG, 1500 * MG)),
    "éphédrine": dict(pat=r"(?<!ps[ée]udo)(?<!nor)(?<!ad)(?<!syn)(?<!ph[ée]nyl)[ée]ph[ée]drine", kg=(50, 1 * MG), abs=(1 * MG, 60 * MG)),
    "esmolol": dict(pat=r"esmolol", kg=(100, 1 * MG), kg_min=(10, 300)),
    "kétorolac": dict(pat=r"k[ée]torolac", kg=(200, 1 * MG), abs=(5 * MG, 60 * MG)),
    "hydrocortisone": dict(pat=r"hydrocortisone|hemisuccinate", kg=(0.5 * MG, 10 * MG), abs=(10 * MG, 400 * MG)),
    "gentamicine": dict(pat=r"gentamicine", kg=(2 * MG, 10 * MG), abs=(40 * MG, 800 * MG)),
    "vancomycine": dict(pat=r"vancomycine", kg=(10 * MG, 40 * MG), abs=(250 * MG, 3000 * MG)),
    "céfazoline": dict(pat=r"c[ée]fazoline", kg=(20 * MG, 60 * MG), abs=(500 * MG, 4000 * MG)),
    "magnésium": dict(pat=r"sulfate de magn[ée]sium|magn[ée]sium", kg=(10 * MG, 100 * MG), abs=(500 * MG, 6000 * MG)),
    "nicardipine": dict(pat=r"nicardipine", kg=(5, 50), kg_min=(0.5, 5), abs=(0.25 * MG, 5 * MG), h=(0.5 * MG, 15 * MG)),
    "urapidil": dict(pat=r"urapidil", abs=(5 * MG, 50 * MG), h=(5 * MG, 60 * MG)),
}
# fix a typo-proof value for tranexamic acid absolute dose
DRUGS["acide tranexamique"]["abs"] = (250 * MG, 4000 * MG)
DRUG_RES = {k: re.compile(v["pat"], re.I) for k, v in DRUGS.items()}

MASS = {"g": 1e6, "mg": 1e3, "µg": 1.0, "ng": 1e-3}


def latex_to_text(s: str) -> str:
    """Flatten the inline LaTeX Chandra emits ($\\mu\\text{g}$, $\\geq$, kg^{-1}) to plain text."""
    def repl(m: re.Match) -> str:
        x = m.group(1)
        x = re.sub(r"\\(?:text|mathrm|mathit|textit|operatorname)\s*\{([^{}]*)\}", r"\1", x)
        for a, b in [(r"\mu", "µ"), (r"\geq", "≥"), (r"\leq", "≤"), (r"\ge", "≥"), (r"\le", "≤"),
                     (r"\times", "×"), (r"\pm", "±"), (r"\cdot", "·"), (r"\%", "%"), (r"\,", " "), (r"\ ", " "),
                     (r"\approx", "≈"), (r"\sim", "~"), (r"\circ", "°"), (r"\gt", ">"), (r"\lt", "<")]:
            x = x.replace(a, b)
        x = re.sub(r"\^\{([^{}]*)\}", r"^\1", x)
        x = x.replace("{", "").replace("}", "")
        return x
    s = re.sub(r"<math[^>]*>(.{1,200}?)</math>", repl, s)
    return re.sub(r"\$([^$\n]{1,120})\$", repl, s)


def html_to_lines(s: str) -> str:
    s = html.unescape(s)
    s = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", " | ", s)
    s = re.sub(r"</tr>", "\n", s)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s


def load_docs() -> list[tuple[str, list[str]]]:
    docs = []
    for p in sorted(CHANDRA.glob("*/*/*.md")):
        docs.append((str(p.relative_to(ROOT)), p.read_text(encoding="utf-8").split("\n")))
    for p in sorted(OVERLAY.glob("*.md")):
        if p.name != "ERRATA.md":
            docs.append((str(p.relative_to(ROOT)), p.read_text(encoding="utf-8").split("\n")))
    return docs


NUM = r"(?P<num>\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
RANGE = NUM + r"(?:\s*(?:-|–|—|à|a|/)\s*(?P<num2>\d+(?:[.,]\d+)?))?"
UNIT = r"(?P<unit>µg|mcg|mg|ng|g)(?![a-zA-Zµ])"
PERKG = r"(?P<perkg>\s*/\s*kg\b|\s*[.·]?\s*kg\s*\^?\s*[-−]\s*1|\s+par\s+kg\b)?"
PERT = r"(?P<pert>\s*/\s*(?:min|mn|h|heure|j|jour|24\s*h)\b|\s*[.·]?\s*(?:min|h|mn)\s*\^?\s*[-−]\s*1|\s+par\s+(?:min|minute|heure|h|jour)\b)?"
# a mass followed by a volume is a concentration (µg/ml, mg/L, µg ml^-1), not a dose
CONC = re.compile(r"\s*(?:/|par)\s*(?:\d+(?:[.,]\d+)?\s*)?(?:ml|l|dl|m2|m²|mmol)\b|\s*[.·]?\s*(?:ml|l|dl)\s*\^?\s*[-−]\s*1", re.I)
DOSE_RE = re.compile(r"(?<![\w.,])" + RANGE + r"\s*" + UNIT + PERKG + PERT)


def to_float(x: str) -> float:
    return float(re.sub(r"[ \u00a0\u202f]", "", x).replace(",", "."))


def dose_type(perkg: bool, pert: str | None) -> str | None:
    t = None
    if pert:
        p = pert.lower()
        t = "min" if ("min" in p or "mn" in p) else ("h" if ("h" in p or "heure" in p) else "day")
    if t == "day":
        return None
    if perkg:
        return "kg" if t is None else f"kg_{t}"
    return "abs" if t is None else t


def find_doses(lines: list[str]):
    """Yield (line_no, text_line, match, drug, dist)."""
    for i, raw in enumerate(lines):
        if not re.search(r"\d", raw):
            continue
        line = html_to_lines(latex_to_text(raw))
        for sub in line.split("\n"):
            for m in DOSE_RE.finditer(sub):
                if CONC.match(sub, m.end()):
                    continue
                # a drug named right after the dose ("2 µg/kg de rémifentanil") wins; otherwise
                # the nearest preceding drug mention in a 160-char window of this row/line
                best = None
                after = sub[m.end(): m.end() + 60]
                am = re.match(r"\s*[),]?\s*(?:de |d'|d’|of |\()\s*", after)
                if am:
                    for d, rx in DRUG_RES.items():
                        if rx.match(after, am.end()):
                            best = d
                if best is None:
                    win = sub[max(0, m.start() - 160): m.start()]
                    bpos = -1
                    for d, rx in DRUG_RES.items():
                        for dm in rx.finditer(win):
                            if dm.start() > bpos:
                                best, bpos = d, dm.start()
                yield i + 1, sub, m, best


def short(s: str, m: re.Match, w: int = 60) -> str:
    # short context only: the guideline texts belong to the SFAR (public repository)
    a, b = max(0, m.start() - w), min(len(s), m.end() + 25)
    return s[a:b].strip()


def main() -> None:
    docs = load_docs()
    rows = []          # all attributed doses
    cand = []          # candidates (detector, doc, line, ...)
    doc_stats = {}
    for path, lines in docs:
        text = "\n".join(lines)
        flat = latex_to_text(text)
        has_micro = bool(re.search(r"[µμ]g|\bmcg\b|\bgammas?\b|microgramme", flat, re.I))
        micro_drugs_dosed = collections.Counter()
        for ln, sub, m, drug in find_doses(lines):
            unit = m.group("unit").replace("mcg", "µg")
            v = to_float(m.group("num"))
            v2 = to_float(m.group("num2")) if m.group("num2") else None
            dt = dose_type(bool(m.group("perkg")), m.group("pert"))
            if drug is None or dt is None:
                continue
            spec = DRUGS[drug]
            if spec.get("micro"):
                micro_drugs_dosed[drug] += 1
            ug = v * MASS[unit]
            rows.append(dict(doc=path, line=ln, drug=drug, dtype=dt, value=v, unit=unit, ug=ug,
                             ctx=short(sub, m)))
            # D1: knowledge-based plausibility
            rng = spec.get(dt)
            if rng:
                lo, hi = rng
                vals = [ug] + ([v2 * MASS[unit]] if v2 is not None else [])
                folds = []
                for u in vals:
                    if u < lo / 10:
                        folds.append(lo / u if u > 0 else math.inf)
                    elif u > hi * 10:
                        folds.append(u / hi)
                if folds:
                    f = max(folds)
                    cand.append(dict(detector="D1_plausibilite", doc=path, line=ln, drug=drug, dtype=dt,
                                     found=m.group(0).strip(), fold=round(f, 1),
                                     note=f"hors plage {lo:g}-{hi:g} µg ({dt})", ctx=short(sub, m)))
            # D10 infusion drug without time unit
            if spec.get("infusion") and dt in ("kg", "abs") and unit == "µg" and "kg" in dt:
                cand.append(dict(detector="D10_debit_sans_temps", doc=path, line=ln, drug=drug, dtype=dt,
                                 found=m.group(0).strip(), fold="", note="médicament perfusé, dose /kg sans /min ou /h",
                                 ctx=short(sub, m)))
        # D4: micro sign absent while µg-family drugs are dosed
        if micro_drugs_dosed and not has_micro:
            cand.append(dict(detector="D4_micro_absent_doc", doc=path, line="", drug=";".join(sorted(micro_drugs_dosed)),
                             dtype="", found=str(sum(micro_drugs_dosed.values())), fold="",
                             note="aucun µ/mcg/microgramme dans le document alors que des médicaments dosés en µg y sont posologiés",
                             ctx=""))
        doc_stats[path] = dict(has_micro=has_micro, micro_drug_doses=sum(micro_drugs_dosed.values()))

        # D5: generic conversion-damage patterns on the flattened text, line by line
        for i, raw in enumerate(lines):
            if not re.search(r"\d", raw):
                continue
            line = html_to_lines(latex_to_text(raw))
            for sub in line.split("\n"):
                # per-minute dosing in mg/kg is exceptional in anaesthesia: often a lost µ
                for m in re.finditer(r"(?<![\w.,])\d+(?:[.,]\d+)?\s*mg\s*(?:/\s*kg\s*/\s*min|[.·]?\s*kg\s*\^?-1\s*[.·]?\s*min\s*\^?-1)", sub):
                    cand.append(dict(detector="D12_mg_kg_min", doc=path, line=i + 1, drug="", dtype="",
                                     found=m.group(0), fold="", note="mg/kg/min (unité inhabituelle, µ perdu ?)", ctx=short(sub, m)))
                # leading-zero integers before a unit: "05 mg", "005 mg/kg" (lost decimal separator)
                for m in re.finditer(r"(?<![\w.,])(?<!\d )(?<!\d\u00a0)(?<!\d\u202f)0\d+\s*(?:µg|mg|g|ml|mL|UI|mmol)\b(?:/kg)?", sub):
                    cand.append(dict(detector="D5_zero_initial", doc=path, line=i + 1, drug="", dtype="",
                                     found=m.group(0), fold="", note="entier à zéro initial (virgule perdue ?)", ctx=short(sub, m)))
                # "0 5 mg": decimal separator turned into a space
                for m in re.finditer(r"(?<![\w.,\d] )(?<![\w.,])0 \d{1,2}\s*(?:µg|mg|g|ml|mL|UI|mmol)\b", sub):
                    cand.append(dict(detector="D6_virgule_espace", doc=path, line=i + 1, drug="", dtype="",
                                     found=m.group(0), fold="", note="'0 x unité' (virgule devenue espace ?)", ctx=short(sub, m)))
                # range whose dash was lost: "5 10 mg" (exclude thousands groups "1 000")
                for m in re.finditer(r"(?<![\w.,|])(\d{1,3}(?:[.,]\d+)?) (\d{1,3}(?:[.,]\d+)?)\s*(µg|mg|g|ml|mL|UI|mmol)(?:/kg)?\b", sub):
                    a, b = m.group(1), m.group(2)
                    if re.fullmatch(r"\d{3}", b) and not re.search(r"[.,]", a):
                        continue  # thousands separator
                    if to_float(a) < to_float(b):
                        cand.append(dict(detector="D7_tiret_perdu", doc=path, line=i + 1, drug="", dtype="",
                                         found=m.group(0), fold="", note="deux nombres croissants accolés avant une unité (tiret perdu ?)",
                                         ctx=short(sub, m)))
                # unit split from its number by a table-cell boundary
                for m in re.finditer(r"(?<![\w.,])\d+(?:[.,]\d+)?\s*\|\s*(?:µg|mg|g|ml|mL|UI)(?:/kg)?\b", sub):
                    cand.append(dict(detector="D8_unite_cellule_suivante", doc=path, line=i + 1, drug="", dtype="",
                                     found=m.group(0), fold="", note="nombre et unité dans deux cellules", ctx=short(sub, m)))
                # Symbol-font residues for ≥ ≤ µ and broken comparators
                for m in re.finditer(r"[³£](?=\s*\d)|\ufffd|(?<=\d)\s*[´](?=\s*\d)|[<>]\s*=\s*\d", sub):
                    cand.append(dict(detector="D9_signe_symbole", doc=path, line=i + 1, drug="", dtype="",
                                     found=m.group(0), fold="", note="résidu de police Symbol / comparateur cassé", ctx=short(sub, m)))
                # variant micro spellings (informational)
                for m in re.finditer(r"\bmcg\b|\bgammas?\b|\bug/|\bng/kg", sub):
                    cand.append(dict(detector="D11_variante_micro", doc=path, line=i + 1, drug="", dtype="",
                                     found=m.group(0), fold="", note="graphie non standard du microgramme (informatif)",
                                     ctx=short(sub, m)))

        # D13: HTML tables whose dose unit is only in the column header ("Posologie (µg/kg)")
        for tm in re.finditer(r"<table.*?</table>", text, re.S):
            tab = latex_to_text(html.unescape(tm.group(0)))
            tline = text[: tm.start()].count("\n") + 1
            trs = re.findall(r"<tr[^>]*>(.*?)</tr>", tab, re.S)
            cells = [[re.sub(r"<[^>]+>", " ", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)] for tr in trs]
            if not cells:
                continue
            hdr_units = {}
            for j, h in enumerate(cells[0]):
                um = re.search(r"(?<![A-Za-zÀ-ÿ])(µg|mcg|mg|ng)(?![A-Za-z])\s*(/\s*kg|[.·]?\s*kg\s*\^?-1)?\s*(/\s*(?:min|h)\b|[.·]?\s*(?:min|h)\s*\^?-1)?", h)
                if um and re.search(r"posolog|dose|bolus|débit|perfusion|\(", h, re.I):
                    dt = dose_type(bool(um.group(2)), um.group(3))
                    if dt:
                        hdr_units[j] = (um.group(1).replace("mcg", "µg"), dt, h)
            for r in cells[1:]:
                if not r:
                    continue
                hits = [(m.start(), d) for d, rx in DRUG_RES.items() for m in [rx.search(r[0])] if m]
                drug = min(hits)[1] if hits else None
                if not drug:
                    continue
                for j, (unit, dt, h) in hdr_units.items():
                    if j >= len(r) or re.search(r"[a-zA-Zµ]", re.sub(r"\b(?:à|a|to|max)\b", "", r[j])):
                        continue  # cell carries its own unit/text: handled by D1
                    rng = DRUGS[drug].get(dt)
                    for nm in re.finditer(r"\d+(?:[.,]\d+)?", r[j]):
                        ug = to_float(nm.group(0)) * MASS[unit]
                        rows.append(dict(doc=path, line=tline, drug=drug, dtype=dt, value=to_float(nm.group(0)),
                                         unit=unit, ug=ug, ctx="[tableau]"))
                        if rng and ug > 0 and (ug < rng[0] / 10 or ug > rng[1] * 10):
                            f = max(rng[0] / ug, ug / rng[1])
                            cand.append(dict(detector="D13_unite_en_entete", doc=path, line=tline, drug=drug, dtype=dt,
                                             found=f"{nm.group(0)} [{unit}, en-tête]", fold=round(f, 1),
                                             note=f"hors plage {rng[0]:g}-{rng[1]:g} µg ({dt})",
                                             ctx=f"{r[0][:50]} | en-tête « {h[:50]} » | {r[j][:30]}"))

    # D2: corpus-empirical outliers per (drug, dose type)
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r["drug"], r["dtype"])].append(r)
    for (drug, dt), rs in groups.items():
        if len(rs) < 5:
            continue
        med = statistics.median(r["ug"] for r in rs if r["ug"] > 0)
        for r in rs:
            if r["ug"] <= 0:
                continue
            f = r["ug"] / med
            if f >= 100 or f <= 0.01:
                cand.append(dict(detector="D2_outlier_corpus", doc=r["doc"], line=r["line"], drug=drug, dtype=dt,
                                 found=f"{r['value']:g} {r['unit']}", fold=round(max(f, 1 / f), 1),
                                 note=f"médiane corpus {med:g} µg ({dt}, n={len(rs)})", ctx=r["ctx"]))
    # D3: same doc, same drug, same number with two mass units 1000x apart
    bydoc = collections.defaultdict(lambda: collections.defaultdict(set))
    for r in rows:
        bydoc[(r["doc"], r["drug"], r["dtype"])][r["value"]].add(r["unit"])
    for (doc, drug, dt), vals in bydoc.items():
        for v, units in vals.items():
            if {"mg", "µg"} <= units or {"g", "mg"} <= units:
                ex = [r for r in rows if r["doc"] == doc and r["drug"] == drug and r["dtype"] == dt and r["value"] == v]
                for r in ex:
                    cand.append(dict(detector="D3_meme_nombre_x1000", doc=doc, line=r["line"], drug=drug, dtype=dt,
                                     found=f"{v:g} {r['unit']}", fold=1000, note=f"même nombre avec {sorted(units)} dans le document",
                                     ctx=r["ctx"]))

    with open(OUT / "doses_extracted.tsv", "w", newline="", encoding="utf-8") as f:
        fields = [k for k in rows[0].keys() if k != "ctx"]  # no text context: line numbers suffice
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    cols = ["detector", "doc", "line", "drug", "dtype", "found", "fold", "note", "ctx"]
    with open(OUT / "candidates.tsv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader(); w.writerows(cand)
    per_det = collections.Counter(c["detector"] for c in cand)
    per_det_docs = {d: len({c["doc"] for c in cand if c["detector"] == d}) for d in per_det}
    per_doc = collections.Counter((c["detector"], c["doc"]) for c in cand)
    summary = dict(n_docs=len(docs), n_doses_attributed=len(rows),
                   docs_with_micro=sum(v["has_micro"] for v in doc_stats.values()),
                   per_detector={d: dict(candidates=n, docs=per_det_docs[d]) for d, n in sorted(per_det.items())},
                   per_detector_doc=[dict(detector=d, doc=doc, n=n) for (d, doc), n in sorted(per_doc.items())])
    (OUT / "candidates_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary["per_detector"], ensure_ascii=False, indent=1))
    print("docs", len(docs), "doses", len(rows), "docs_with_micro", summary["docs_with_micro"])


if __name__ == "__main__":
    main()
