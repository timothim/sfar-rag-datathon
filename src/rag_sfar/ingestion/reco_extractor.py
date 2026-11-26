"""Generic extraction of graded recommendation units from the SFAR OCR Markdown corpus.

A *recommendation unit* is one graded statement of a guideline: its full text, its
strength (GRADE 1/2 +/-, expert opinion, no recommendation), the agreement of the
expert panel, its label (``R1.2``...), the field / PICO question it belongs to and
the edition metadata of the document. Units are meant to become indexed, citable
retrieval units later; this module only extracts them.

All rules derive from the general structure of SFAR guidelines, never from a given
guideline or benchmark question:

* labelled recommendations (``R<field>.<question>[.<n>]``, ``Recommandation n``,
  ``Encadré n``) in paragraphs, bold boxes or table cells;
* rating blocks following the statement (``GRADE 1+``, ``G2-``, ``(Grade 2-) Accord
  FORT``, ``Avis d'experts (Accord fort)``, bare ``1`` / ``2`` / ``AE`` cells of the
  2024-2026 HAS-style tables);
* unlabelled statements carrying an explicit trailing rating (``... (G1+)``,
  ``... (Avis d'experts) Accord fort``, ``... (accord fort)`` in agreement-rated
  documents);
* table rows whose first cell is a statement and a later cell a rating.

Strength is read from the rating when one exists. The wording ("Il faut", "Il faut
probablement", "Les experts suggèrent"...) only gives the direction (for / against)
and serves as a fallback, because in the HAS template used since 2024 "Il est
recommandé" may be rated GRADE 2.
"""

from __future__ import annotations

import bisect
import hashlib
import html
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from pydantic import BaseModel, Field

Strength = Literal[
    "grade_1_plus",
    "grade_1_minus",
    "grade_2_plus",
    "grade_2_minus",
    "expert_opinion",
    "no_recommendation",
    "unknown",
]
StrengthSource = Literal["rating", "wording", "none"]
ExtractionMode = Literal["labelled", "table_row", "inline_rating"]


class RecommendationUnit(BaseModel):
    """One graded recommendation extracted from a guideline document."""

    unit_id: str
    doc_id: str
    doc_title: str = ""
    year: int | None = None
    is_latest_edition: bool = True
    superseded_by: str | None = None
    doc_role: str | None = None
    reco_family_id: str | None = None
    reco_label: str | None = None
    field: str | None = None  # "Champ n ..." heading
    section: str | None = None  # PICO question / "Question n ..."
    heading: str | None = None  # last Markdown heading before the unit
    statement: str
    strength: Strength = "unknown"
    strength_raw: str | None = None
    strength_source: StrengthSource = "none"
    agreement: str | None = None  # normalised: fort, faible, relatif, modere, professionnel
    agreement_raw: str | None = None
    char_span: tuple[int, int]
    line: int
    extraction_mode: ExtractionMode
    duplicate_of: str | None = None  # unit_id of the same statement in a sibling document
    extra: dict = Field(default_factory=dict)


# --------------------------------------------------------------------------- OCR cleaning

_LATEX_SYMBOLS = {
    r"\geq": "≥", r"\geqslant": "≥", r"\ge": "≥", r"\leq": "≤", r"\leqslant": "≤", r"\le": "≤",
    r"\times": "×", r"\pm": "±", r"\mp": "∓", r"\cdot": "·", r"\approx": "≈", r"\sim": "~",
    r"\neq": "≠", r"\ne": "≠", r"\lt": "<", r"\gt": ">", r"\rightarrow": "→", r"\to": "→",
    r"\leftarrow": "←", r"\Rightarrow": "⇒", r"\ldots": "…", r"\dots": "…", r"\cdots": "…",
    r"\infty": "∞", r"\degree": "°", r"\circ": "°", r"\%": "%", r"\&": "&", r"\#": "#",
    r"\mu": "µ", r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\Delta": "Δ",
    r"\kappa": "κ", r"\lambda": "λ", r"\sigma": "σ", r"\theta": "θ", r"\tau": "τ", r"\omega": "ω",
    r"\le q": "≤",
}
_SUPERSCRIPTS = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
_LATEX_CMD_RX = re.compile(r"\\(?:[A-Za-z]+|[%&#])")
_LATEX_TEXT_RX = re.compile(r"\\(?:text|mathrm|mathbf|mathit|textbf|textit|operatorname|mbox|rm|bf)\s*\{([^{}]*)\}")
_LATEX_FRAC_RX = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_LATEX_SUP_RX = re.compile(r"\^\s*\{?\s*([0-9+\-]{1,3})\s*\}?")
_LATEX_SUB_RX = re.compile(r"_\s*\{([^{}]*)\}|_([A-Za-z0-9])")
_DOLLAR_RX = re.compile(r"\$\$?([^$]{1,300}?)\$\$?")
_MATH_TAG_RX = re.compile(r"<math[^>]*>(.*?)</math>", re.S | re.I)
_TAG_RX = re.compile(r"<[^>]+>")
_SPACE_RX = re.compile(r"[ \t\u00a0\u202f\u2009\u2007]+")


def _latex_to_text(expr: str) -> str:
    s = expr
    for _ in range(3):
        s2 = _LATEX_TEXT_RX.sub(r"\1", s)
        s2 = _LATEX_FRAC_RX.sub(r"\1/\2", s2)
        if s2 == s:
            break
        s = s2
    s = s.replace(r"\,", " ").replace(r"\;", " ").replace(r"\:", " ").replace(r"\!", "").replace(r"\ ", " ")
    s = re.sub(r"\\q?quad\b", " ", s)
    s = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)\b\s*", "", s)

    def _cmd(m: re.Match[str]) -> str:
        tok = m.group(0)
        return _LATEX_SYMBOLS.get(tok, tok[1:] if tok[1:].isalpha() else tok[1:])

    s = _LATEX_CMD_RX.sub(_cmd, s)
    s = _LATEX_SUP_RX.sub(lambda m: m.group(1).translate(_SUPERSCRIPTS), s)
    s = _LATEX_SUB_RX.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(2), s)
    s = s.replace("{", "").replace("}", "")
    return s.strip()


def clean_ocr_text(text: str) -> str:
    """Normalise the most frequent OCR artefacts of the Chandra Markdown output.

    HTML entities (also double-escaped), simple ``<math>`` and ``$...$`` LaTeX, HTML
    tags, Markdown emphasis, NUL bytes, typographic apostrophes and whitespace.
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFC", text.replace("\x00", ""))
    for _ in range(2):  # "&amp;gt;" -> "&gt;" -> ">"
        if "&" not in s:
            break
        s = html.unescape(s)
    s = _MATH_TAG_RX.sub(lambda m: _latex_to_text(m.group(1)), s)
    s = _DOLLAR_RX.sub(lambda m: _latex_to_text(m.group(1)), s)
    s = re.sub(r"<(?:sup|sub)>\s*([^<]{0,12}?)\s*</(?:sup|sub)>", r"\1", s, flags=re.I)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)  # Markdown images (OCR figure placeholders)
    s = _TAG_RX.sub(" ", s)
    s = re.sub(r"(?<=[\w.)»])\*\*(?=[A-ZÀ-Ý])", " ", s)  # "ACCORD FORT**Argumentaire**"
    s = s.replace("**", "").replace("__", "")
    s = re.sub(r"(?<![\w*])\*(?=\S)([^*\n]{1,3000}?)(?<=\S)\*(?![\w*])", r"\1", s)  # *italic*
    s = re.sub(r"^\*(?=\S)|(?<=\S)\*$", "", s.strip())
    s = s.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    s = re.sub(r"(?:(?<=[a-zà-ÿ]{2})|(?<=\)))\.(?=[A-ZÀ-Ý][a-zà-ÿ])", ". ", s)  # "fin.Début" glued by the OCR
    s = _SPACE_RX.sub(" ", s)
    s = re.sub(r"\s*\n\s*", " ", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\s+([,.;:](?:\s|$))", r"\1", s)
    s = re.sub(r"\s+([,.])$", r"\1", s)
    return s.strip()


# --------------------------------------------------------------------------- segmentation


@dataclass
class _Block:
    start: int
    end: int
    text: str  # cleaned text
    line: int
    table: int | None
    row: int | None
    cell: int | None
    heading: bool
    blank_before: bool


_BOUNDARY_RX = re.compile(
    r"\n|</t[dh]>|<tr\b[^>]*>|</tr>|<table\b[^>]*>|</table>|<br\s*/?>|</p>|</li>"
    # a bold recommendation label glued to the end of the previous paragraph
    r"|(?<=\S)(?=\*\*\s*R\s?\d+(?:\s?\.\s?\d+)+)"
    # a Markdown heading glued to the end of the previous paragraph ("...(accord fort).## 2.4 Titre")
    r"|(?<=[.)\]:*])(?=#{1,6} )",
    re.I,
)
_BULLET_PREFIX_RX = re.compile(r"^(?:[#>]+\s*|[-•●○▪◦·]\s+)+")


def _segment(markdown: str) -> list[_Block]:
    line_starts = [0] + [m.end() for m in re.finditer(r"\n", markdown)]
    blocks: list[_Block] = []
    table_id = 0
    in_table = False
    row = 0
    cell = 0
    newlines_since_block = 2
    pos = 0

    def _emit(a: int, b: int) -> None:
        nonlocal newlines_since_block
        raw = markdown[a:b]
        if not raw.strip():
            return
        lead = len(raw) - len(raw.lstrip())
        trail = len(raw) - len(raw.rstrip())
        a2, b2 = a + lead, b - trail
        raw_s = markdown[a2:b2]
        heading = raw_s.startswith("#")
        text = clean_ocr_text(raw_s)
        text = _BULLET_PREFIX_RX.sub("", text) if heading else text
        if not text:
            return
        blocks.append(
            _Block(
                start=a2,
                end=b2,
                text=text,
                line=bisect.bisect_right(line_starts, a2),
                table=table_id if in_table else None,
                row=row if in_table else None,
                cell=cell if in_table else None,
                heading=heading,
                blank_before=newlines_since_block >= 2,
            )
        )
        newlines_since_block = 0

    for m in _BOUNDARY_RX.finditer(markdown):
        _emit(pos, m.start())
        tok = m.group(0).lower()
        if tok == "\n":
            newlines_since_block += 1
        elif tok.startswith("<table"):
            table_id += 1
            in_table = True
            row = 0
            cell = 0
        elif tok == "</table>":
            in_table = False
            newlines_since_block = 2
        elif tok.startswith("<tr"):
            row += 1
            cell = 0
        elif tok in ("</td>", "</th>"):
            cell += 1
        pos = m.end()
    _emit(pos, len(markdown))
    return blocks


# --------------------------------------------------------------------------- patterns

_D = r"\-–—−‑‐"
_LABEL_CORE = (
    r"(?P<label>R\s?\d{1,2}(?:\s?\.\s?\d{1,2}){0,3}(?:[a-z](?![a-zA-Z]))?"
    r"|RP\s?\d{1,2}(?:\.\d{1,2}){0,3}"
    r"|Recommandation\s+(?:n\s?°\s?)?\d{1,2}(?:\.\d{1,2}){0,3}"
    r"|Encadr[ée]\s+\d{1,2}(?:\.\d{1,2}){0,3})"
)
# label at the start of a block, followed by a separator and the statement
_LABEL_START_RX = re.compile(
    rf"^(?:[-•●○▪]\s*)?{_LABEL_CORE}\.?(?:\s*\([^()]{{1,40}}\))?\s*(?:[{_D}:.)]\s*)?(?=[A-ZÀ-Ýa-zà-ÿ«\"(])"
)
# label alone (in a table cell or on its own line)
_LABEL_ALONE_RX = re.compile(rf"^(?:[-•●○▪]\s*)?{_LABEL_CORE}\.?(?:\s*\([^()]{{1,40}}\))?\s*[{_D}:.]?$")
_NUM_ANCHOR_RX = re.compile(rf"^(?P<label>\d{{1,2}}(?:\.\d{{1,2}}){{1,3}})\s*[{_D}]\s*(?=[A-ZÀ-Ý«])")
_NUM_LABEL_RX = re.compile(r"^(?P<label>\d{1,2}(?:\.\d{1,2}){1,3})\.?\s+(?=[A-ZÀ-Ý«])")
_RECO_PREFIX_RX = re.compile(r"^(?:Recommandations?|Reco\.?)\s*(?:n\s?°\s?\d+\s*)?[:.{_D}]\s*".replace("{_D}", _D), re.I)

_GRADE_RX = re.compile(
    rf"(?<![\w])(?:GRADE|Grade|grade)\s*(?P<lvl>1|2|II|I)(?![IVX\d])\s*(?P<sign>[+{_D}](?!\d))?"
    rf"|(?<![\w.])G\s?(?P<glvl>[12])\s*(?P<gsign>[+{_D}])(?![\w])"
    rf"|\(\s*G(?P<plvl>[12])\s*\)"
)
_AE_RX = re.compile(
    r"(?i:\bavis d'experts?\b|\baccord d'experts?\b|\bopinion d'experts?\b|\brecommandations? d'experts?\b)"
    r"|(?<![\w'])AE(?![\w'])",
)
_AE_TEXT_RX = re.compile(r"\bavis d'experts?\b|\baccord d'experts?\b|\bopinion d'experts?\b", re.I)
_ACCORD_RX = re.compile(
    r"\b(?:accord|consensus)\s+(?P<a>fort|faible|relatif|mod[ée]r[ée]|professionnel|fortement|large)\b", re.I
)
_NOREC_RX = re.compile(
    r"\bpas de recommandation\b|\babsence de recommandation\b|\baucune recommandation\b"
    r"|\bne (?:permet|permettent|peut|peuvent) pas (?:d'[ée]mettre|de formuler|d'[ée]tablir|de faire|de proposer)"
    r"(?: une| de| d'| la moindre)? ?recommandation"
    r"|\bpas en mesure (?:d'[ée]mettre|de formuler|de proposer) (?:une |de |d')?recommandation"
    r"|\bne (?:peut|peuvent) (?:pas )?se prononcer\b|\bn'ont pas pu (?:[ée]mettre|formuler) (?:de |une )?recommandation",
    re.I,
)
_RATING_FILLER_RX = re.compile(
    r"recommandations?\s+(?:forte|faible|optionnelle|conditionnelle)s?|qualit[ée] (?:des|de la) preuves?\s*\w*"
    r"|niveau (?:de preuve|d'[ée]vidence)\s*\w*|force de la recommandation|cotation|accord|consensus"
    r"|pour|contre|positive|n[ée]gative|[●○◯⬤•·]",
    re.I,
)
_VERBAL_GRADE_RX = re.compile(r"(?i)\brecommandation (forte|faible|conditionnelle|optionnelle)\b(?! (?:pour|contre)\b[^)]*:)")
_BARE_RATING_CELL_RX = re.compile(rf"^\(?\s*(?:GRADE|G)?\s*(?P<lvl>[12])\s*(?P<sign>[+{_D}])?\s*\)?$|^\(?AE\)?$", re.I)

_NEG_RX = re.compile(
    r"\bil ne faut (?:probablement |certainement |surtout )?pas\b|\bil n'est (?:probablement )?pas recommand"
    r"|\b(?:ne|n') ?(?:sont|est|soit|soient) (?:probablement )?pas recommand|\bnon recommand"
    r"|\brecommand\w* de ne (?:pas|jamais|plus)\b"
    r"|\b(?:sugg[èeé]r\w*|propos\w*|recommand\w*|conseill\w*|pr[ée]conis\w*) de ne (?:pas|jamais|plus)\b"
    r"|\bne (?:faut|doit|doivent|devrait|devraient) (?:probablement )?(?:pas|jamais|plus)\b"
    r"|\bil est (?:probablement )?(?:d[ée]conseill|contre-indiqu)\w*|\bne pas (?:utiliser|administrer|r[ée]aliser|recourir|pratiquer|prescrire)",
    re.I,
)
_WORDING = [
    ("no_recommendation", _NOREC_RX),
    (
        "weak",
        re.compile(
            r"\bil (?:ne )?faut probablement\b|\bil n'est probablement pas recommand|\bil est probablement recommand"
            r"|\b(?:sont|est|soit|soient) probablement (?:pas )?recommand|\bnous sugg[ée]rons\b|\bwe suggest\b",
            re.I,
        ),
    ),
    (
        "experts",
        re.compile(
            r"\bles experts? (?:sugg[èe]rent|proposent|recommandent|pr[ée]conisent|conseillent|consid[èe]rent|estiment|rappellent|soulignent)\b"
            r"|\bavis d'experts?\b|\bexperts suggest\b",
            re.I,
        ),
    ),
    (
        "strong",
        re.compile(
            r"\bil (?:ne )?faut\b|\bil n'est pas recommand|\bil est recommand|\bnous recommandons\b|\bwe recommend\b"
            r"|\b(?:sont|est|soit|soient) (?:pas )?recommand[ée]e?s?\b|\bil est (?:fortement )?(?:conseill|d[ée]conseill)",
            re.I,
        ),
    ),
]
# wording that announces a recommendation (used to accept unlabelled table rows)
_RECO_WORDING_RX = re.compile(
    r"\bil (?:ne )?faut\b|\bil (?:n')?est (?:probablement |fortement )?(?:pas )?recommand|\bles experts? (?:sugg|propos|recommand|pr[ée]conis|conseill)"
    r"|\b(?:sont|est) (?:probablement )?(?:pas )?recommand|\bnous (?:recommandons|sugg[ée]rons)|\bdoi(?:t|vent) [êe]tre\b",
    re.I,
)
# text that defines the rating scale itself (method sections)
_DEFINITION_RX = re.compile(
    r"(?:GRADE|G)\s*(?:1|2|I{1,2})\s*[+\-–]?\s*[=:]|faire ou (?:de )?ne pas faire|\b(?:de|ne pas) faire\s*[\"».;)]"
    r"|\bfaire\s*[»\"]|[«\"]\s*(?:il|nous|les experts)\b"
    r"|recommandation (?:forte|faible|optionnelle)\s*[:(]|\.\.\.|…\s*[»\"]|il faut faire\b|il faut probablement faire\b"
    r"|accord (?:fort|faible) (?:si|lorsque|quand)\b|\bcot[ée]e?s? entre\b"
    r"|\b\d+\s+(?:recommandations|avis d'experts)\b|\bparmi les (?:\d+ )?recommandations\b|\bniveau de preuve (?:[ée]lev[ée]|faible|mod[ée]r[ée])",
    re.I,
)
_SFAR_WORDING_DEF_RX = re.compile(r"(?i)il faut (?:probablement )?(?:ne pas )?faire|il ne faut (?:probablement )?pas faire")
_HAS_TEMPLATE_RX = re.compile(r"(?i)recommandation faible,? (?:qualit[ée] des preuves|niveau de preuve) [ée]lev[ée]")
_CHAMP_RX = re.compile(r"^(?:Champ|Domaine|Partie|Th[èe]me)\s+(?:n\s?°\s?)?(?:\d{1,2}|[IVX]{1,5})\b", re.I)
_QUESTION_RX = re.compile(
    r"^(?:Question|Q)\s*(?:n\s?°\s?)?(?:\d{1,2}(?:\.\d{1,2}){0,3})?\s*[{_D}:.)]|^Question\b|^Q\d".replace("{_D}", _D), re.I
)
_STOP_HEAD_RX = re.compile(
    r"^(?:Argumentaire|Rationnel|Justification|Arguments?|Commentaires?|R[ée]f[ée]rences?|Bibliographie|"
    r"Experts?\s*:|Coordonnateurs?|Questions?\b|Champ\b|PICO|Synth[èe]se des|Niveau de preuve|"
    r"Recommandation\s*$|RECOMMANDATION\s*$|R[ée]sum[ée]\b|Introduction\b|M[ée]thode)",
    re.I,
)
_REF_HEAD_RX = re.compile(r"^(?:[\dIVX]+[.)]?\s*)?(?:R[ée]f[ée]rences?(?: bibliographiques)?|Bibliographie|References)\s*:?$", re.I)
_REF_ENTRY_RX = re.compile(r"^(?:\[\d{1,3}\]\.?|\d{1,3}[.)]?\s+[A-Z][\w'\-]+(?:\s[A-Z]{1,3})?,\s)\s*")
_META_RX = re.compile(r"(?i)^(?:ces|les pr[ée]sentes|cette) (?:recommandations?|actualisation|mise à jour)\b")
_FIRST_PERSON_RX = re.compile(r"(?i)(?:^|[\s(«\"])(?:je|j'|moi|me|m'a semblé|à mon avis)(?=[\s,'])")
_NUMERIC_CELL_RX = re.compile(r"^[\d\s\[\]\-–/%().,;:<>=±]+$")
_LIST_ITEM_RX = re.compile(r"^(?:[-•●○▪◦·]\s|\d{1,2}[.)]\s|[a-z][.)]\s|[ivx]{1,4}[.)]\s)")
_FR_SW = (" les ", " des ", " une ", " dans ", " pour ", " avec ", " par ", " est ", " chez ", " sont ", " qui ", " sur ", " du ", " de ")
_EN_SW = (" the ", " and ", " with ", " for ", " are ", " should ", " which ", " this ", " from ", " we ", " of ", " in ")


def _is_english(text: str) -> bool:
    t = " " + text.lower() + " "
    fr = sum(t.count(w) for w in _FR_SW)
    en = sum(t.count(w) for w in _EN_SW)
    return en >= 3 and en > 1.5 * fr


def _norm_label(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw).strip()
    if re.match(r"^RP?\s?\d", s):
        return re.sub(r"\s", "", s).rstrip(".")
    m = re.match(r"^Recommandation\s+(?:n\s?°\s?)?(\d.*)$", s, re.I)
    if m:
        return "R" + m.group(1).replace(" ", "")
    return s


# --------------------------------------------------------------------------- rating helpers


@dataclass
class _Rating:
    level: str | None = None  # "1" | "2"
    sign: str | None = None  # "plus" | "minus"
    ae: bool = False
    norec: bool = False
    agreement: str | None = None
    agreement_raw: str | None = None
    legacy: bool = False  # rated on a pre-GRADE scale (grade A/B/C)
    raw: list[str] | None = None

    def found(self) -> bool:
        return bool(self.level or self.ae or self.norec)


def _parse_rating(texts: Iterable[str], allow_bare: bool = False) -> _Rating:
    r = _Rating(raw=[])
    for t in texts:
        m = _GRADE_RX.search(t)
        if m and r.level is None:
            lvl = m.group("lvl") or m.group("glvl") or m.group("plvl")
            lvl = {"I": "1", "II": "2"}.get(lvl, lvl)
            sign = m.group("sign") or m.group("gsign")
            r.level = lvl
            if sign:
                r.sign = "plus" if sign == "+" else "minus"
        elif allow_bare and r.level is None and not r.ae:
            b = _BARE_RATING_CELL_RX.match(t.strip())
            if b:
                if b.group("lvl"):
                    r.level = b.group("lvl")
                    if b.group("sign"):
                        r.sign = "plus" if b.group("sign") == "+" else "minus"
                else:
                    r.ae = True
        if r.level is None:
            v = _VERBAL_GRADE_RX.search(t)
            if v:
                r.level = "1" if v.group(1).lower() == "forte" else "2"
        if _AE_RX.search(t):
            r.ae = True
        if re.search(r"(?i)\bgrade\s+[A-D]\b(?!')", t) and not re.search(r"\bAE\b", t):
            r.legacy = True
        if re.search(r"\bpas de recommandation\b|\babsence de recommandation\b", t, re.I):
            r.norec = True
        a = _ACCORD_RX.search(t)
        if a and r.agreement is None:
            v = a.group("a").lower()
            r.agreement = {"fortement": "fort", "large": "fort", "modéré": "modere", "modere": "modere", "modérée": "modere"}.get(
                v, v.replace("é", "e")
            )
            r.agreement_raw = a.group(0)
        r.raw.append(t)
    return r


def _rating_remainder(text: str) -> str:
    s = _GRADE_RX.sub(" ", text)
    s = _AE_RX.sub(" ", s)
    s = re.sub(r"(?i)\bavis d'experts?\b", " ", s)
    s = _ACCORD_RX.sub(" ", s)
    s = re.sub(r"(?i)\b(?:pas|absence) de recommandation\b", " ", s)
    s = _RATING_FILLER_RX.sub(" ", s)
    return re.sub(r"[^A-Za-zÀ-ÿ0-9]+", "", s)


def _is_rating_block(text: str) -> bool:
    """A short block that only carries a rating (grade, expert opinion, agreement)."""
    if len(text) > 160:
        return False
    has = bool(
        _GRADE_RX.search(text)
        or _AE_RX.search(text)
        or _ACCORD_RX.search(text)
        or re.search(r"(?i)\b(?:pas|absence) de recommandation\b", text)
    )
    return has and len(_rating_remainder(text)) <= 12


# trailing rating at the end of a statement: "... (GRADE 1+, accord fort)." / "... G2+, Accord fort."
_TRAIL_TOKEN = (
    rf"(?:\(?\s*(?:GRADE|Grade|grade)\s*(?:1|2|II|I)(?![IVX\d])\s*[+{_D}]?\s*\)?"
    rf"|\(?\s*G\s?[12]\s*[+{_D}]\s*\)?|\(\s*G[12]\s*\)"
    r"|\(?\s*(?:[Aa]vis|AVIS) [dD]'[Ee](?:xperts?|XPERTS?)\s*\)?|\(\s*AE\s*\)|\(\s*(?:[Gg]rade|GRADE)\s+(?:AE|[A-D])\s*\)"
    r"|[(«\[]?\s*(?:[Aa]ccord|ACCORD|[Cc]onsensus) (?:[Ff]ort|FORT|[Ff]aible|FAIBLE|[Rr]elatif|RELATIF|[Mm]od[ée]r[ée]|[Pp]rofessionnel)\w*\s*[)»\]]?"
    r"|\(\s*recommandations? (?:forte|faible|conditionnelle)[^()]{0,80}\)|recommandation (?:forte|faible)\s*\)?)"
)
_TRAIL_RX = re.compile(rf"(?:\s*[,;]?\s*{_TRAIL_TOKEN})+\s*[.:;]?\s*$")
_LEAD_PAREN_RX = re.compile(r"(?i)^\((?=[^()]*\b(?:accord|grade|avis d'experts?)\b)[^()]{3,80}\)\s*[:.\-–]?\s*")
_PROSE_BEFORE_RATING = {
    "un", "une", "d'", "l'", "le", "la", "les", "des", "du", "de", "en", "par", "à", "a", "sur", "un", "cet", "ce",
    "son", "leur", "dont", "selon", "avec", "sans", "obtenu", "obtenue", "été", "est", "était",
}
_LEAD_RX = re.compile(rf"^\s*(?:{_TRAIL_TOKEN}\s*[,;:]?\s*)+")


_MID_RATING_RX = re.compile(
    rf"\s*(?P<r>(?:\(\s*(?:GRADE|Grade|grade)\s*(?:1|2|II|I)(?![IVX\d])\s*[+{_D}]?[^()]{{0,40}}\)|\(\s*G\s?[12]\s*[+{_D}]\s*\)"
    rf"|\(\s*(?:[Aa]vis|AVIS) [dD]'[Ee](?:xperts?|XPERTS?)\s*\)|\(\s*AE\s*\)"
    rf"|\(\s*(?:[Aa]ccord|ACCORD) (?:[Ff]ort|FORT|[Ff]aible|FAIBLE|[Rr]elatif|[Pp]rofessionnel)\w*\s*\))"
    rf"(?:\s*[,;]?\s*(?:\(?\s*(?:[Aa]ccord|ACCORD) \w+\s*\)?))?)\s*\.\s+(?=[A-ZÀ-Ý])"
)


def _split_trailing_rating(stmt: str) -> tuple[str, str | None]:
    m = _TRAIL_RX.search(stmt)
    if not m or m.start() == 0:
        return stmt, None
    rating = m.group(0).strip(" .,;:")
    before = re.search(r"([\w']+)\W*$", stmt[: m.start()])
    if before and before.group(1).lower() in _PROSE_BEFORE_RATING and not m.group(0).lstrip(" ,;").startswith("("):
        return stmt, None  # "... aboutissant à un avis d'experts." is prose, not a rating
    # require at least one real rating token
    if not (
        _GRADE_RX.search(rating) or _AE_RX.search(rating) or _ACCORD_RX.search(rating)
        or "recommandation" in rating or re.search(r"(?i)\bgrade\s+[A-D]\b", rating)
    ):
        return stmt, None
    core = stmt[: m.start()].rstrip(" ,;")
    if not core.endswith((".", ":", "!", ";")):
        core += "." if not stmt.rstrip().endswith(":") else ":"
    return core, rating


def _wording_class(stmt: str) -> str | None:
    low = stmt[:700]
    for name, rx in _WORDING:
        if rx.search(low):
            return name
    return None


def _normalize_strength(
    rating: _Rating, stmt: str, wording_maps_to_grade: bool
) -> tuple[Strength, StrengthSource]:
    if _NOREC_RX.search(stmt[:700]) or (rating.norec and not rating.level):
        return "no_recommendation", "rating" if rating.norec else "wording"
    neg = bool(_NEG_RX.search(stmt[:700]))
    if rating.legacy and not rating.level and not rating.ae:
        return "unknown", "rating"  # rated on another scale (grade A/B/C): no GRADE equivalent
    if rating.level:
        sign = rating.sign or ("minus" if neg else "plus")
        return f"grade_{rating.level}_{sign}", "rating"  # type: ignore[return-value]
    if rating.ae:
        return "expert_opinion", "rating"
    w = _wording_class(stmt)
    if w == "experts":
        return "expert_opinion", "wording"
    if w in ("strong", "weak") and wording_maps_to_grade:
        lvl = "1" if w == "strong" else "2"
        return f"grade_{lvl}_{'minus' if neg else 'plus'}", "wording"  # type: ignore[return-value]
    return "unknown", "none"


# --------------------------------------------------------------------------- extraction core


def _words(s: str) -> int:
    return len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", s))


def _norm_for_dedup(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-zà-ÿ0-9]+", " ", s)
    return s.strip()


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _is_duplicate(label_a: str | None, norm_a: str, label_b: str | None, norm_b: str) -> bool:
    """Same recommendation repeated (summary table and full text, short and long versions).

    Two different labels are never merged: guidelines often repeat one template sentence
    for several populations or procedures.
    """
    if label_a and label_b and label_a != label_b:
        return False
    sim = _jaccard(norm_a, norm_b)
    if label_a and label_a == label_b:
        return sim >= 0.5 or norm_a in norm_b or norm_b in norm_a
    return sim >= 0.9 or norm_a == norm_b


@dataclass
class _Raw:
    idx: int
    end_idx: int
    label: str | None
    statement: str
    rating: _Rating
    rating_text: str | None
    start: int
    end: int
    line: int
    mode: str
    field: str | None
    section: str | None
    heading: str | None


def _context_tracker(blocks: list[_Block]) -> tuple[list[tuple[str | None, str | None, str | None]], list[bool]]:
    """Return, for each block, (field, section, heading) in force and whether it lies in a reference list."""
    ctx: list[tuple[str | None, str | None, str | None]] = []
    in_refs: list[bool] = []
    field = section = heading = None
    refs = False
    for b in blocks:
        t = b.text
        refs = bool(_REF_ENTRY_RX.match(t))
        if b.heading:
            heading = t[:200]
        if len(t) < 400 and _CHAMP_RX.match(t):
            field = t[:200]
            section = None
            refs = False
        elif len(t) < 700 and _QUESTION_RX.match(t) and ("?" in t or b.heading or len(t) < 200):
            section = t[:400]
        ctx.append((field, section, heading))
        in_refs.append(refs)
    return ctx, in_refs


def _is_anchor(blocks: list[_Block], i: int) -> re.Match[str] | None:
    b = blocks[i]
    t = b.text
    m = _LABEL_START_RX.match(t) or _LABEL_ALONE_RX.match(t)
    if not m:
        return None
    # "R1.2" followed by a lowercase word in running prose is a cross-reference, not a label
    rest = t[m.end():]
    if rest and rest[0].islower() and not b.blank_before and b.table is None and not b.heading:
        return None
    # in a table, a label is the first filled cell of its row (reviewer-comment tables quote
    # labels in a later column)
    if b.table is not None and b.cell:
        for bj in blocks[max(0, i - 8): i]:
            if bj.table == b.table and bj.row == b.row and (bj.cell or 0) < b.cell:
                return None
    return m


def _valid_statement(stmt: str) -> bool:
    if _words(stmt) < 5:
        return False
    if stmt.rstrip(" *").endswith("?"):
        return False
    if _META_RX.match(stmt):
        return False  # "Ces recommandations devront être réactualisées..."
    if _FIRST_PERSON_RX.search(stmt):
        return False  # reviewer comments ("je pense que...") are not recommendations
    letters = sum(c.isalpha() for c in stmt)
    return letters >= 0.5 * len(stmt)


def _is_vote_row(blocks: list[_Block], i: int) -> bool:
    """Delphi result tables repeat the labels with numeric vote cells (median, %, n/N)."""
    b = blocks[i]
    if b.table is None:
        return False
    numeric = 0
    for bj in blocks[max(0, i - 12): i + 12]:
        if bj.table == b.table and bj.row == b.row and bj.cell != b.cell and _NUMERIC_CELL_RX.match(bj.text):
            numeric += 1
    return numeric >= 2


def _labelled_units(blocks: list[_Block], ctx, in_refs, consumed: set[int]) -> list[_Raw]:
    out: list[_Raw] = []
    anchors = {i: m for i, b in enumerate(blocks) if not in_refs[i] and (m := _is_anchor(blocks, i))}
    numeric: set[int] = set()
    if len({_norm_label(m.group("label")) for m in anchors.values()}) >= 3:
        # labels whose "R" was lost by the OCR ("5.1.3 - Chez ..."): kept only if a rating follows
        for i, b in enumerate(blocks):
            if i not in anchors and not in_refs[i] and not b.heading and (m := _NUM_ANCHOR_RX.match(b.text)):
                anchors[i] = m
                numeric.add(i)
    anchor_idx = sorted(anchors)
    for k, i in enumerate(anchor_idx):
        m = anchors[i]
        nxt = anchor_idx[k + 1] if k + 1 < len(anchor_idx) else len(blocks)
        b0 = blocks[i]
        if _is_vote_row(blocks, i):
            continue
        label = _norm_label(m.group("label"))
        if i in numeric:
            label = "R" + label
        first = b0.text[m.end():].lstrip(" -–:.").rstrip()
        parts: list[str] = []
        rating_texts: list[str] = []
        j = i
        if first:
            if _is_rating_block(first):
                rating_texts.append(first)
            else:
                parts.append(first)
        # statement in the following block(s) when the label stands alone or carried only the rating
        cur_cell = (b0.table, b0.row, b0.cell)
        if not parts:
            for jj in range(i + 1, min(nxt, i + 4)):
                bj = blocks[jj]
                if bj.heading or _STOP_HEAD_RX.match(bj.text):
                    break
                if _is_rating_block(bj.text) and not (bj.table is not None and bj.row == b0.row and len(bj.text) > 40):
                    rating_texts.append(bj.text)
                    continue
                parts.append(bj.text)
                j = jj
                cur_cell = (bj.table, bj.row, bj.cell)
                break
        if not parts:
            continue
        # continuation of the statement (same table cell, list after a colon, lowercase continuation)
        jj = j + 1
        while jj < nxt and jj < j + 25:
            bj = blocks[jj]
            prev = parts[-1]
            if bj.heading or _is_rating_block(bj.text) or _STOP_HEAD_RX.match(bj.text):
                break
            same_cell = bj.table is not None and (bj.table, bj.row, bj.cell) == cur_cell
            list_cont = bj.table is None and (
                (prev.rstrip().endswith((":", ";")) or (_LIST_ITEM_RX.match(prev) and len(parts) > 1))
                and (_LIST_ITEM_RX.match(bj.text) or not bj.blank_before or (prev.rstrip().endswith(":") and bj.text[:1] in "«\""))
            )
            # a sentence cut by a page break (often re-opened as a new table by the OCR)
            lower_cont = bj.text[:1].islower() and not prev.rstrip().endswith((".", ";", ":", "!", "?")) and len(bj.text) > 15
            if not (same_cell or list_cont or lower_cont):
                break
            if sum(len(p) for p in parts) + len(bj.text) > 3500:
                break
            parts.append(bj.text)
            j = jj
            jj += 1
        # rating: same row cells, or the next few short rating blocks
        for jj in range(j + 1, min(nxt, j + 6)):
            bj = blocks[jj]
            same_row = bj.table is not None and bj.table == b0.table and bj.row == blocks[j].row
            if same_row and _BARE_RATING_CELL_RX.match(bj.text.strip()):
                rating_texts.append(bj.text)
                continue
            if _is_rating_block(bj.text):
                rating_texts.append(bj.text)
                continue
            if same_row and len(bj.text) < 60:
                continue
            break
        stmt = " ".join(p.strip() for p in parts)
        inner = _LABEL_START_RX.match(stmt)
        if inner:  # "R1.3" (question number) followed by "R1.3.1 – statement": keep the inner label
            label = _norm_label(inner.group("label"))
            stmt = stmt[inner.end():].lstrip(" -–:.")
        mid = _MID_RATING_RX.search(stmt)
        if mid and mid.start() > 0 and _words(stmt[: mid.start()]) >= 5:
            stmt = stmt[: mid.start()].rstrip(" ,;") + ". " + mid.group("r")
        stmt, trailing = _split_trailing_rating(stmt)
        lead = _LEAD_PAREN_RX.match(stmt) or _LEAD_RX.match(stmt)
        if lead and _words(stmt[lead.end():]) >= 5 and (
            _GRADE_RX.search(lead.group(0)) or _AE_RX.search(lead.group(0)) or _ACCORD_RX.search(lead.group(0))
        ):
            rating_texts.insert(0, lead.group(0))
            stmt = stmt[lead.end():].strip()
            stmt = stmt[:1].upper() + stmt[1:]
        if trailing:
            rating_texts.insert(0, trailing)
        stmt = _RECO_PREFIX_RX.sub("", stmt).strip()
        if not _valid_statement(stmt):
            continue
        rating = _parse_rating(rating_texts, allow_bare=True)
        if i in numeric and not rating.found():
            continue
        consumed.update(range(i, j + 1))
        f, s, h = ctx[i]
        out.append(
            _Raw(i, j, label, stmt, rating, " | ".join(rating_texts) or None, b0.start, blocks[j].end, b0.line, "labelled", f, s, h)
        )
    return out


def _table_row_units(blocks: list[_Block], ctx, in_refs, consumed: set[int]) -> list[_Raw]:
    out: list[_Raw] = []
    for i, b in enumerate(blocks):
        if i in consumed or in_refs[i] or b.table is None or not (30 < len(b.text) < 2500):
            continue
        if not _RECO_WORDING_RX.search(b.text) or _DEFINITION_RX.search(b.text):
            continue
        # later cells of the same row (statement cell may span several blocks)
        parts = [b.text]
        j = i
        rating_texts: list[str] = []
        for jj in range(i + 1, min(len(blocks), i + 12)):
            bj = blocks[jj]
            if bj.table != b.table or bj.row != b.row:
                break
            if bj.cell == b.cell:
                parts.append(bj.text)
                j = jj
                continue
            if _BARE_RATING_CELL_RX.match(bj.text.strip()) or _is_rating_block(bj.text):
                rating_texts.append(bj.text)
        if not rating_texts:
            continue
        stmt = " ".join(parts)
        stmt, trailing = _split_trailing_rating(stmt)
        if trailing:
            rating_texts.insert(0, trailing)
        lm = _NUM_LABEL_RX.match(stmt)
        label = lm.group("label") if lm else None
        if lm:
            stmt = stmt[lm.end():]
        if not _valid_statement(stmt):
            continue
        rating = _parse_rating(rating_texts, allow_bare=True)
        if not rating.found():
            continue
        consumed.update(range(i, j + 1))
        f, s, h = ctx[i]
        out.append(_Raw(i, j, label, stmt, rating, " | ".join(rating_texts), b.start, blocks[j].end, b.line, "table_row", f, s, h))
    return out


_SENT_SPLIT_RX = re.compile(
    r"(?<=[.;!])\s+(?=[A-ZÀ-Ý«(])(?<!\bet al\. )(?<!\bvs\. )(?<!\bcf\. )(?<!\bFig\. )|(?<=\)\.)(?=[A-ZÀ-Ý])"
    r"|(?<=[»\]])\s*(?=\d{1,3}[).]\s)"
)


def _list_stem(blocks: list[_Block], i: int) -> str | None:
    """Introductory sentence ("... est indiqué :") of the list that block ``i`` belongs to,
    followed by the preceding unrated items that the rating of item ``i`` also covers."""
    k = i - 1
    while k >= 0 and i - k <= 30 and _LIST_ITEM_RX.match(blocks[k].text) and blocks[k].table == blocks[i].table:
        k -= 1
    if k < 0 or i - k > 30:
        return None
    t = blocks[k].text.rstrip()
    if not (t.endswith(":") and not blocks[k].heading and len(t) < 600):
        return None
    items: list[str] = []
    for kk in range(k + 1, i):
        it = blocks[kk].text
        if _TRAIL_RX.search(it):  # an item with its own rating closes the previous group
            items = []
        else:
            items.append(re.sub(r"^(?:[-•●○▪◦·]\s*)+", "", it))
    return " ".join([t] + items)


def _inline_units(
    blocks: list[_Block], ctx, in_refs, consumed: set[int], doc_uses_grade: bool, doc_uses_accord: bool
) -> list[_Raw]:
    """Unlabelled statements ending with an explicit rating."""
    out: list[_Raw] = []
    for i, b in enumerate(blocks):
        if i in consumed or in_refs[i] or b.heading or len(b.text) < 40:
            continue
        t = b.text
        if not (_GRADE_RX.search(t) or _AE_TEXT_RX.search(t) or re.search(r"\(\s*AE\s*\)", t) or _ACCORD_RX.search(t)):
            continue
        if _DEFINITION_RX.search(t):
            continue
        # one unit for the whole block if it is a labelled / bold box, otherwise one per rated sentence
        raw_block = b.text
        lm = _NUM_LABEL_RX.match(raw_block)
        whole = bool(lm) or bool(_RECO_PREFIX_RX.match(raw_block))
        sentences = [raw_block] if whole else _SENT_SPLIT_RX.split(raw_block)
        merged: list[str] = []
        for sent in sentences:  # a rating split off as its own "sentence" belongs to the previous one
            if merged and _is_rating_block(sent) and not _words(_rating_remainder(sent)):
                merged[-1] = merged[-1].rstrip() + " " + sent.strip()
            else:
                merged.append(sent)
        sentences = merged
        # absorb a list following a rated sentence ending with ':'
        list_tail: list[str] = []
        j = i
        if raw_block.rstrip().endswith(":"):
            for jj in range(i + 1, min(len(blocks), i + 20)):
                bj = blocks[jj]
                if bj.table != b.table or bj.heading or not _LIST_ITEM_RX.match(bj.text):
                    break
                list_tail.append(bj.text)
                j = jj
        pending: list[str] = []
        for si, sent in enumerate(sentences):
            stmt, rating_txt = _split_trailing_rating(sent.strip())
            lead_rating = None
            if not rating_txt:
                lead = _LEAD_RX.match(sent)
                if lead and (_GRADE_RX.search(lead.group(0)) or _AE_RX.search(lead.group(0))):
                    lead_rating = lead.group(0)
                    stmt = sent[lead.end():].strip()
            rt = rating_txt or lead_rating
            if not rt:
                pending.append(sent.strip())
                continue
            # unrated sentences just before a rated one belong to the same statement
            context = [p for p in pending if p] if rating_txt else []
            pending = []
            while context and sum(len(p) for p in context) + len(stmt) > 1500:
                context.pop(0)
            if context:
                stmt = " ".join(context + [stmt])
            has_grade_or_ae = bool(_GRADE_RX.search(rt) or _AE_RX.search(rt))
            if not has_grade_or_ae:
                # agreement-only rating: only in documents rated by agreement (formal consensus)
                if not doc_uses_accord:
                    continue
            if has_grade_or_ae and _GRADE_RX.search(rt) and not _AE_RX.search(rt) and not doc_uses_grade:
                continue
            if si == len(sentences) - 1 and list_tail and stmt.rstrip().endswith(":"):
                stmt = stmt + " " + " ".join(list_tail)
            elif si == len(sentences) - 1 and list_tail and rating_txt and sent.rstrip().endswith(":"):
                stmt = stmt.rstrip(".") + " : " + " ".join(list_tail)
            stmt = re.sub(r"^(?:[-•●○▪◦·]\s*)+", "", stmt)
            if stmt[:1].islower() and _LIST_ITEM_RX.match(b.text):
                stem = _list_stem(blocks, i)
                if stem:  # "Un examen est indiqué :" / "- dans tel cas (accord fort)"
                    stmt = stem + " " + stmt
            elif stmt[:1].islower() and si == 0 and i > 0 and blocks[i - 1].table == b.table:
                prev = blocks[i - 1].text.rstrip()
                if not prev.endswith((".", ";", ":", "!", "?", ")")) and not blocks[i - 1].heading:
                    # sentence cut in two paragraphs by the OCR: take its unrated beginning
                    head = [x for x in _SENT_SPLIT_RX.split(prev) if x.strip()]
                    tail: list[str] = []
                    for x in reversed(head):
                        if _TRAIL_RX.search(x) or _MID_RATING_RX.search(x + " X"):
                            break
                        tail.insert(0, x.strip())
                    if tail:
                        stmt = " ".join(tail) + " " + stmt
            label = None
            m1 = re.match(r"^(\d{1,3})\s*[).\-–]\s+(?=[A-ZÀ-Ý])", stmt)  # "12. Il est recommandé ..." / "3) ..."
            if m1:
                label = m1.group(1)
                stmt = stmt[m1.end():]
            m2 = _NUM_LABEL_RX.match(stmt)
            if m2:
                label = m2.group("label")
                stmt = stmt[m2.end():]
            stmt = _RECO_PREFIX_RX.sub("", stmt).strip()
            if not _valid_statement(stmt) or _DEFINITION_RX.search(stmt):
                continue
            rating = _parse_rating([rt])
            if not (rating.found() or rating.agreement):
                continue
            consumed.update(range(i, j + 1))
            f, s, h = ctx[i]
            out.append(_Raw(i, j, label, stmt, rating, rt, b.start, blocks[j].end, b.line, "inline_rating", f, s, h))
    return out


def _locate(markdown: str, start: int, end: int, stmt: str) -> tuple[int, int]:
    """Narrow a block-level span to the statement when its ends can be found in the raw text."""
    raw = markdown[start:end].replace("’", "'")
    head = stmt[:25]
    tail = stmt.rstrip(" .:;")[-25:]
    a = raw.find(head)
    z = raw.rfind(tail)
    s = start + a if a >= 0 else start
    e = start + z + len(tail) if z >= 0 and (a < 0 or z >= a) else end
    return (s, e) if e > s else (start, end)


def _doc_field(doc: dict, *keys: str, default=None):
    for k in keys:
        if k in doc and doc[k] is not None:
            return doc[k]
    return default


def extract_recommendations(markdown: str, doc: dict) -> list[RecommendationUnit]:
    """Extract the graded recommendation units of one OCR Markdown document.

    ``doc`` holds the document metadata (``doc_id``, ``title``, ``effective_year`` or
    ``year``, ``is_latest_edition``; optionally ``superseded_by``, ``doc_role``,
    ``reco_family_id``).
    """
    doc_id = str(_doc_field(doc, "doc_id", default="doc"))
    blocks = _segment(markdown)
    if not blocks:
        return []
    full = "\n".join(b.text for b in blocks)
    n_grade = sum(1 for _ in _GRADE_RX.finditer(full))
    doc_uses_grade = n_grade >= 3
    # Wording is a reliable proxy of the GRADE level only when the method section defines
    # it the classic SFAR way ("Il faut faire" = GRADE 1+, "Il faut probablement faire" =
    # GRADE 2+) and not with the HAS template where "Il est recommandé" may be GRADE 2.
    wording_maps_to_grade = doc_uses_grade and bool(_SFAR_WORDING_DEF_RX.search(full)) and not _HAS_TEMPLATE_RX.search(full)
    doc_uses_accord = sum(1 for _ in _ACCORD_RX.finditer(full)) >= 5
    ctx, in_refs = _context_tracker(blocks)
    consumed: set[int] = set()
    raws = _labelled_units(blocks, ctx, in_refs, consumed)
    # A guideline uses one presentation for its recommendations. When it labels them
    # (R1.1...), unlabelled rated sentences are argumentaire, captions or dose tables.
    if len({r.label for r in raws}) < 3:
        raws += _table_row_units(blocks, ctx, in_refs, consumed)
        raws += _inline_units(blocks, ctx, in_refs, consumed, doc_uses_grade, doc_uses_accord)
    raws.sort(key=lambda r: r.start)

    units: list[RecommendationUnit] = []
    kept_norm: list[tuple[str | None, str]] = []
    seen_ids: set[str] = set()
    n_english = 0
    for r in raws:
        stmt = re.sub(r"\s+", " ", r.statement).strip()
        stmt = re.sub(r"^(?:[-–•●○▪◦·)\]:]\s*)+", "", stmt)
        stmt = stmt[:1].upper() + stmt[1:]
        stmt = re.sub(r"(?<=\s)(?:[-–•●○▪◦·]\s+){2,}", "- ", stmt)  # "- - item" / "- • item"
        if _is_english(stmt):
            n_english += 1
            continue
        nrm = _norm_for_dedup(stmt)
        dup = False
        for lab, other in kept_norm:
            if _is_duplicate(r.label, nrm, lab, other):
                dup = True
                break
        if dup:
            continue
        kept_norm.append((r.label, nrm))
        strength, source = _normalize_strength(r.rating, stmt, wording_maps_to_grade)
        h = hashlib.sha1(nrm.encode("utf-8")).hexdigest()[:8]
        uid = f"{doc_id}:{r.label or 'u'}:{h}"
        if uid in seen_ids:
            continue
        seen_ids.add(uid)
        span = _locate(markdown, r.start, r.end, stmt) if r.mode == "inline_rating" else (r.start, r.end)
        year = _doc_field(doc, "effective_year", "year")
        units.append(
            RecommendationUnit(
                unit_id=uid,
                doc_id=doc_id,
                doc_title=str(_doc_field(doc, "title", default="")),
                year=int(year) if year is not None else None,
                is_latest_edition=bool(_doc_field(doc, "is_latest_edition", default=True)),
                superseded_by=_doc_field(doc, "superseded_by"),
                doc_role=_doc_field(doc, "doc_role"),
                reco_family_id=_doc_field(doc, "reco_family_id"),
                reco_label=r.label,
                field=r.field,
                section=r.section,
                heading=r.heading,
                statement=stmt,
                strength=strength,
                strength_raw=r.rating_text,
                strength_source=source,
                agreement=r.rating.agreement,
                agreement_raw=r.rating.agreement_raw,
                char_span=span,
                line=r.line,
                extraction_mode=r.mode,  # type: ignore[arg-type]
            )
        )
    return units


# --------------------------------------------------------------------------- corpus level

_DECLARED_RX = re.compile(
    r"(?:abouti(?:t|ssent|ssant)?\s+à|conduit\s+à|permis\s+d'(?:[ée]tablir|[ée]laborer|[ée]mettre)|permis\s+de\s+(?:formuler|r[ée]diger))\s+"
    r"(?:l'[ée]laboration de |l'[ée]criture de |la r[ée]daction de |la formulation de )?"
    r"(?P<n>\d{1,3}|[a-zéèêûô\-]+(?: et une?)?(?:-[a-zéèêûô]+)*)\s+recommandations",
    re.I,
)
_WORDNUM = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
    "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20,
    "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
}


def _wordnum(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    s = s.lower().replace(" et une", "-un").replace(" et un", "-un")
    tot = 0
    for p in s.split("-"):
        if p not in _WORDNUM:
            return None
        tot += _WORDNUM[p]
    return tot or None


def declared_recommendation_count(markdown: str) -> int | None:
    """Number of recommendations a document announces ("... a abouti à N recommandations")."""
    text = clean_ocr_text(markdown.replace("\n", " "))
    m = _DECLARED_RX.search(text)
    return _wordnum(m.group("n")) if m else None


DEFAULT_METADATA = Path("index/table_aware_sota/metadata.sqlite")
_ROLE_PRIORITY = {"recommandation": 0, "texte_court": 1, "argumentaire": 2, "tableaux_synthese": 3, "aide_cognitive": 4}


def load_documents(metadata_path: str | Path = DEFAULT_METADATA) -> list[dict]:
    """Read the document metadata (payload_json of the ``documents`` table)."""
    con = sqlite3.connect(str(metadata_path))
    try:
        rows = con.execute("SELECT payload_json FROM documents ORDER BY doc_id").fetchall()
    finally:
        con.close()
    return [json.loads(r[0]) for r in rows]


def mark_cross_document_duplicates(units: list[RecommendationUnit], docs: dict[str, dict]) -> None:
    """Flag a unit repeated in a sibling document of the same edition (same family and year).

    The kept copy is the one of the main recommendation text (role priority), then the
    first by doc_id. Duplicates are flagged, not removed.
    """
    groups: dict[tuple, list[RecommendationUnit]] = {}
    for u in units:
        d = docs.get(u.doc_id, {})
        fam = d.get("reco_family_id") or u.doc_id
        groups.setdefault((fam, u.year), []).append(u)
    for members in groups.values():
        by_doc: dict[str, list[RecommendationUnit]] = {}
        for u in members:
            by_doc.setdefault(u.doc_id, []).append(u)
        if len(by_doc) < 2:
            continue
        order = sorted(by_doc, key=lambda d: (_ROLE_PRIORITY.get(docs.get(d, {}).get("doc_role", ""), 9), d))
        kept: list[tuple[RecommendationUnit, str]] = []
        for d in order:
            for u in by_doc[d]:
                nrm = _norm_for_dedup(u.statement)
                for k, knrm in kept:
                    if k.doc_id == u.doc_id:
                        continue
                    if _is_duplicate(u.reco_label, nrm, k.reco_label, knrm):
                        u.duplicate_of = k.unit_id
                        break
                if u.duplicate_of is None:
                    kept.append((u, nrm))


def extract_corpus(
    metadata_path: str | Path = DEFAULT_METADATA,
    root: str | Path = ".",
    languages: tuple[str, ...] = ("fr", "bilingual"),
    exclude_roles: tuple[str, ...] = ("traduction_en",),
    documents: list[dict] | None = None,
) -> list[RecommendationUnit]:
    """Extract recommendation units from every French document, current or superseded."""
    docs = documents if documents is not None else load_documents(metadata_path)
    root = Path(root)
    units: list[RecommendationUnit] = []
    by_id: dict[str, dict] = {}
    for d in docs:
        if d.get("language") not in languages or d.get("doc_role") in exclude_roles:
            continue
        p = root / d["md_path"]
        if not p.exists():
            continue
        by_id[d["doc_id"]] = d
        units.extend(extract_recommendations(p.read_text(encoding="utf-8", errors="ignore"), d))
    mark_cross_document_duplicates(units, by_id)
    return units
