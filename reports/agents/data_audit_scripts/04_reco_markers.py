"""04 - Structure type d'une RFE SFAR : fréquence des marqueurs (GRADE, force, accord,
avis d'experts, identifiants Rx.y, PICO, champs/questions, argumentaire, références),
classification du format par document et par année, prototype d'extraction générique
des recommandations, validation contre le nombre déclaré (« ont abouti à N recommandations »).

Relancer : .venv/bin/python reports/agents/data_audit_scripts/04_reco_markers.py
Sorties  : out/reco_markers.json, out/reco_units.jsonl
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

from common import OUT, ROOT, read, write_json

inv = json.loads((OUT / "inventory.json").read_text())["rows"]


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace(" ", " ").replace("−", "-")
    return s


def blocks_of(raw: str):
    """Découpe en blocs (lignes ; cellules de tableau séparées), en gardant le n° de ligne source."""
    out = []
    for ln, line in enumerate(raw.split("\n"), 1):
        line = norm(line)
        if "<" in line:
            parts = re.split(r"</t[dh]>|</tr>|<br\s*/?>|</p>|</li>", line)
        else:
            parts = [line]
        for p in parts:
            t = re.sub(r"<[^>]+>", " ", p)
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                out.append((ln, t))
    return out


# ------------------------------------------------------------------ marqueurs
P = {
    # force (ordre important : négatif faible > négatif fort > positif faible > positif fort)
    "faible_neg": r"\bil ne faut probablement pas\b|\bil n'est probablement pas recommand|\bne (?:sont|est|soit|soient) probablement pas recommand|\bnous sugg[ée]rons de ne pas\b|\bil est probablement recommand[ée] de ne pas\b",
    "forte_neg": r"\bil ne faut pas\b|\bil n'est pas recommand|\bne (?:sont|est|soit|soient) pas recommand|\bnous recommandons de ne pas\b|\bil est recommand[ée] de ne pas\b",
    "faible_pos": r"\bil faut probablement\b|\bil est probablement recommand|\b(?:sont|est) probablement recommand|\bnous sugg[ée]rons\b",
    "forte_pos": r"\bil faut\b|\bil est recommand[ée]\b|\bnous recommandons\b|\b(?:sont|est) recommand[ée]e?s?\b",
    "experts": r"\bles experts (?:sugg[èe]rent|proposent|recommandent|consid[èe]rent|estiment|pr[ée]conisent)\b|\bavis d'experts?\b|\baccord d'experts\b",
}
STRENGTH_ORDER = ["faible_neg", "forte_neg", "faible_pos", "forte_pos", "experts"]
RX = {k: re.compile(v, re.I) for k, v in P.items()}
GRADE_LBL = re.compile(r"\bGRADE\s?[12]\s?[+\-]?(?![\d.])|\bG[12]\s?[+\-](?![\w])|\bG[12]\b(?=[,)\s])", re.I)
GRADE_LBL_STRICT = re.compile(r"\bGRADE\s?[12]\s?[+\-]?(?![\d.])|(?<![\w.])G[12]\s?[+\-]", re.I)
ACCORD = re.compile(r"\baccord (?:fort|faible|relatif|mod[ée]r[ée]|fortement)|\bconsensus (?:fort|faible)\b|\baccord professionnel\b", re.I)
OLD_ABC = re.compile(r"\(grade [abcd]\)|\bgrade [abcd]\b|\bniveau de preuve [1-4]\b|\bpr[ée]somption scientifique\b|\bfaible niveau de preuve\b", re.I)
RID_START = re.compile(r"^(?:\*\*|#+\s*|[-•●]\s*)*\s*(R\s?\d+(?:\s?\.\s?\d+){0,3})\.?\s*(?:\*\*)?\s*(?:[–\-:.)]\s*)?(?:\*\*)?\s*(?=[A-ZÀ-Ý«])")
RID_ALONE = re.compile(r"^(?:\*\*)?\s*(R\s?\d+(?:\.\d+){0,3})\s*(?:\*\*)?$")
GRADE_CELL = re.compile(r"^\(?\s*(?:GRADE|G)?\s*[12]\s*[+\-]?\s*\)?(?:\s*[,(]?\s*accord \w+\)?)?$|^AE$|^\(?avis d'experts?\)?(?:\s*\(?accord \w+\)?)?$", re.I)
RID_ANY = re.compile(r"(?<![\w.])R\s?\d+(?:\.\d+){0,3}(?=\s*[–\-:.)]\s)")
JURY = re.compile(r"\ble jury (?:recommande|propose|estime|considère)", re.I)
PICO = re.compile(r"\bPICO\b")
CHAMP = re.compile(r"^(?:#+\s*)?(?:\*\*)?\s*(champ|domaine)\s+(\d+|[IVX]+)\b", re.I)
QUESTION = re.compile(r"^(?:#+\s*)?(?:\*\*)?\s*(question|Q)\s*(\d+(?:\.\d+)*)\b", re.I)
ARGU = re.compile(r"^(?:#+\s*)?(?:\*\*)?\s*argumentaire|^(?:#+\s*)?(?:\*\*)?\s*rationnel\b|^(?:#+\s*)?(?:\*\*)?\s*justification", re.I)
REFHEAD = re.compile(r"^#{1,6}\s*(?:\*\*)?\s*(?:[\dIVX]+[.)]?\s*)?(r[ée]f[ée]rences?(?: bibliographiques)?|bibliographie|references)\b", re.I)
DECLARED = re.compile(r"abouti(?:t|ssent)? à (?:l'élaboration de |l'écriture de |la rédaction de )?(\d+|[a-zéèêûô\-]+(?: et un| et une)?) (?:recommandations|propositions)", re.I)
WORDNUM = {"un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
           "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "trente": 30,
           "quarante": 40, "cinquante": 50, "soixante": 60}
REMPLACE = re.compile(r"(?:remplacent|remplace|annulent?|abrogent?|se substituent? (?:à|aux)|actualisation|r[ée]actualisation|mise à jour|mettent à jour|update of|replace[sd]?)\b[^.\n]{0,160}?\b(19\d\d|20[0-2]\d)\b", re.I)


def wordnum(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    s = s.lower().replace(" et un", "-un").replace(" et une", "-un")
    tot = 0
    for p in s.split("-"):
        if p not in WORDNUM:
            return None
        tot += WORDNUM[p]
    return tot or None


def strength_of(t: str) -> str | None:
    for k in STRENGTH_ORDER:
        if RX[k].search(t):
            return k
    return None


MAIN_FORMS = {"texte_principal", "texte_court", "texte_long_argumentaire"}
docs = []
units_out = open(OUT / "reco_units.jsonl", "w")
examples = collections.defaultdict(list)

for r in inv:
    path = ROOT / r["md"]
    raw = read(path)
    blocks = blocks_of(raw)
    full = "\n".join(t for _, t in blocks)
    # corps hors références (après le dernier titre "Références")
    c = collections.Counter()
    for k in STRENGTH_ORDER:
        c[k] = len(RX[k].findall(full))
    c["grade_label"] = len(GRADE_LBL_STRICT.findall(full))
    c["accord"] = len(ACCORD.findall(full))
    c["old_abc"] = len(OLD_ABC.findall(full))
    c["jury"] = len(JURY.findall(full))
    c["pico"] = len(PICO.findall(full))
    c["argumentaire_head"] = sum(1 for _, t in blocks if ARGU.search(t))
    c["champ_head"] = sum(1 for _, t in blocks if CHAMP.search(t))
    c["question_head"] = sum(1 for _, t in blocks if QUESTION.search(t))
    c["ref_heading"] = sum(1 for line in raw.split("\n") if REFHEAD.search(line.strip()))
    c["remplace_mention"] = len(REMPLACE.findall(full[:20000]))

    # ------------------------------------------------ extraction prototype
    units = []
    champ = question = None
    rid_idx = [i for i, (_, t) in enumerate(blocks) if RID_START.match(t) or RID_ALONE.match(t)]
    rid_set = set(rid_idx)
    nxt = {a: b for a, b in zip(rid_idx, rid_idx[1:] + [len(blocks)])}
    used = set()
    for i, (ln, t) in enumerate(blocks):
        m = CHAMP.search(t)
        if m:
            champ = f"{m.group(1).capitalize()} {m.group(2)}"
        m = QUESTION.search(t)
        if m and len(t) < 400:
            question = t[:200]
        rid = None
        if i in rid_set:
            m = RID_START.match(t) or RID_ALONE.match(t)
            rid = re.sub(r"\s", "", m.group(1)).upper()
            stmt = t[m.end():].strip(" *")
            j = i
            if len(stmt) < 25 and i + 1 < len(blocks):
                stmt = (stmt + " " + blocks[i + 1][1]).strip()
                j = i + 1
            win_blocks = [stmt] + [b[1] for b in blocks[j + 1: min(nxt[i], j + 5)]]
            mode = "id"
        else:
            # mode B : ligne de tableau sans identifiant = énoncé + cellule de cotation isolée
            if i in used or not (25 < len(t) < 900) or strength_of(t) is None:
                continue
            follow = [b[1] for b in blocks[i + 1: i + 3]]
            if not any(GRADE_CELL.match(f) for f in follow):
                continue
            stmt, j, mode = t, i, "row"
            win_blocks = [t] + follow
        used.update(range(i, j + 1))
        window = " ".join(win_blocks)
        g = GRADE_LBL_STRICT.search(window)
        gcell = next((w for w in win_blocks[1:] if GRADE_CELL.match(w)), None)
        a = ACCORD.search(window)
        st = strength_of(stmt[:600])
        grade = g.group(0) if g else (gcell if gcell else None)
        u = {"md": r["md"], "line": blocks[i][0], "mode": mode, "rid": rid,
             "champ": champ or (f"Champ {rid[1:].split('.')[0]}" if rid and "." in rid else None),
             "question": question, "strength_phrase": st, "grade": grade, "accord": a.group(0) if a else None,
             "avis_experts": bool(re.search(r"avis d'experts?|\bAE\b", window, re.I)), "text": stmt[:400]}
        units.append(u)
        units_out.write(json.dumps(u, ensure_ascii=False) + "\n")
    rids = {u["rid"] for u in units if u["rid"]}
    n_units_total = len({u["rid"] for u in units if u["rid"]}) + sum(1 for u in units if not u["rid"])
    dm = DECLARED.search(full)
    declared = wordnum(dm.group(1)) if dm else None

    # ------------------------------------------------ classe de format
    n_rid = len(rids)
    if c["grade_label"] >= 3 and (n_rid >= 3 or c["accord"] >= 3):
        fmt = "GRADE_SFAR (Rx.y + GRADE + accord)"
    elif c["grade_label"] >= 3:
        fmt = "GRADE sans identifiants"
    elif n_rid >= 3 and (c["experts"] >= 3 or c["accord"] >= 3):
        fmt = "Avis d'experts / RPP (Rx.y sans GRADE)"
    elif c["accord"] >= 10:
        fmt = "Cotation d'accord seule (accord fort/faible, RAND/UCLA)"
    elif c["old_abc"] >= 3:
        fmt = "Gradation ancienne (A/B/C, niveaux de preuve)"
    elif c["jury"] >= 2:
        fmt = "Conférence de consensus (jury)"
    elif n_rid >= 3:
        fmt = "Identifiants Rx.y seuls"
    else:
        fmt = "Narratif / non structuré"
    for k in ["grade_label", "accord", "experts", "faible_neg", "forte_neg", "faible_pos", "old_abc", "jury"]:
        if c[k] and len(examples[k]) < 6:
            rx = {"grade_label": GRADE_LBL_STRICT, "accord": ACCORD, "old_abc": OLD_ABC, "jury": JURY}.get(k) or RX[k]
            for ln, line in enumerate(raw.split("\n"), 1):
                mm = rx.search(norm(re.sub(r"<[^>]+>", " ", line)))
                if mm:
                    examples[k].append(f"{r['md']}:{ln}  «{norm(re.sub(r'<[^>]+>', ' ', line)).strip()[:160]}»")
                    break
    docs.append({"md": r["md"], "year": r["year_folder"], "form": r["form"], "lang": r["lang"], "type": r["type"],
                 "format": fmt, "markers": dict(c), "n_units": len(units), "n_rids": n_rid, "n_units_dedup": n_units_total, "n_row_units": sum(1 for u in units if u["mode"] == "row"), "declared": declared,
                 "units_with_grade": sum(1 for u in units if u["grade"]),
                 "units_with_accord": sum(1 for u in units if u["accord"]),
                 "units_with_strength": sum(1 for u in units if u["strength_phrase"]),
                 "units_avis_experts": sum(1 for u in units if u["avis_experts"] or u["strength_phrase"] == "experts")})
units_out.close()

# ------------------------------------------------------------------ agrégats
main = [d for d in docs if d["form"] in MAIN_FORMS and d["lang"] != "en"]
fmt_all = collections.Counter(d["format"] for d in docs)
fmt_main = collections.Counter(d["format"] for d in main)


def period(y: str) -> str:
    if y == "unknown":
        return "inconnue"
    y = int(y)
    return "2000-2004" if y < 2005 else "2005-2009" if y < 2010 else "2010-2014" if y < 2015 else "2015-2019" if y < 2020 else "2020-2022" if y < 2023 else "2023-2026"


by_period = collections.defaultdict(collections.Counter)
for d in main:
    by_period[period(d["year"])][d["format"]] += 1
docs_with = {k: sum(1 for d in docs if d["markers"].get(k)) for k in docs[0]["markers"]}
tot_markers = {k: sum(d["markers"].get(k, 0) for d in docs) for k in docs[0]["markers"]}
main_with = {k: sum(1 for d in main if d["markers"].get(k)) for k in docs[0]["markers"]}
# validation : n R-ids extraits vs nb déclaré
val = [(d["md"], d["declared"], d["n_units_dedup"]) for d in docs if d["declared"]]
exact = sum(1 for _, a, b in val if a == b)
within10 = sum(1 for _, a, b in val if a and abs(a - b) <= max(1, 0.1 * a))
units_all = sum(d["n_units"] for d in docs)
allu = [json.loads(l) for l in open(OUT / "reco_units.jsonl")]


def gnorm(g):
    if not g:
        return "aucune"
    if re.search(r"AE|avis", g, re.I):
        return "AE"
    m = re.search(r"([12])\s*([+\-]?)", g)
    return (m.group(1) + m.group(2)) if m else "autre"


xtab = collections.Counter((u["strength_phrase"] or "aucune", gnorm(u["grade"] if u["grade"] else ("AE" if u["avis_experts"] else None))) for u in allu)

summary = {
    "n_docs": len(docs), "n_main_fr": len(main),
    "format_all": fmt_all, "format_main_fr": fmt_main,
    "format_main_by_period": {k: dict(v) for k, v in sorted(by_period.items())},
    "docs_with_marker": docs_with, "main_docs_with_marker": main_with, "total_marker_occurrences": tot_markers,
    "units_total": units_all,
    "units_with_grade": sum(d["units_with_grade"] for d in docs),
    "units_with_accord": sum(d["units_with_accord"] for d in docs),
    "units_with_strength": sum(d["units_with_strength"] for d in docs),
    "units_avis_experts": sum(d["units_avis_experts"] for d in docs),
    "docs_with_units": sum(1 for d in docs if d["n_units"]),
    "units_by_mode": collections.Counter(u["mode"] for u in allu),
    "units_dedup_total": sum(d["n_units_dedup"] for d in docs),
    "phrase_x_grade": {f"{a} | {b}": n for (a, b), n in sorted(xtab.items(), key=lambda x: -x[1])},
    "declared_count_docs": len(val), "declared_exact_match": exact, "declared_within_10pct": within10,
    "declared_detail": val,
    "examples": examples,
}
write_json("reco_markers.json", {"summary": summary, "docs": docs})
print(json.dumps({k: v for k, v in summary.items() if k not in ("declared_detail", "examples")}, ensure_ascii=False, indent=1, default=str))
print("\nDéclaré vs extrait :")
for m, a, b in sorted(val, key=lambda x: x[0]):
    print(f"  déclaré={a:>4} extrait={b:>4}  {Path(m).parent.name[:80]}")
print("\nExemples :")
for k, v in examples.items():
    print(k)
    for e in v[:3]:
        print("   ", e.replace(str(ROOT) + "/", ""))
