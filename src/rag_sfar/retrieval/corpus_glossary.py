"""Abbreviation glossary extracted from the corpus itself, and an optional query expansion.

Generic alternative to the hand-written `medical_lexicon`: SFAR guidelines define their
abbreviations in the text, either inline ("antibioprophylaxie (ABP)", "ABP (antibioprophylaxie)")
or in "Abréviations" / "Glossaire" sections and tables ("ABP : antibioprophylaxie",
"Abréviation : ABP | Signification : …", "AB, antibiotique ; HC, hémocultures"). Every candidate
pair is validated by a letter alignment in the spirit of Schwartz & Hearst (2003): the letters of
the abbreviation must appear in order in the long form, the first one at the start of its first
word. Nothing in this module is specific to a guideline or to an evaluation question.

This module is NOT used by the retrieval pipeline: nothing imports it, so the frozen
configuration (`C10_context_notes`) is unaffected. `expand_query_with_glossary` is meant to be
applied to the question before calling `SfarRagRetriever.retrieve` (experiment only, see
`eval_internal/robustness/`).
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ABBR_RE = r"[A-Z][A-Za-z0-9\-]{1,9}"
_ROMAN = re.compile(r"^(?=[IVXLC]+$)M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})$")
_GLOSSARY_SECTION = re.compile(r"abr[ée]viation|glossaire|acronyme|sigle", re.I)
_ELISION = re.compile(r"^(?:l|d|qu|j|s|n)['’]", re.I)
_LEADING_ARTICLE = re.compile(r"^(?:le|la|les|un|une|des|du|de|d|l|au|aux)\s+", re.I)
_STOP_END = {"de", "du", "des", "la", "le", "les", "et", "ou", "à", "a", "en", "d", "l", "par", "pour", "sur", "au", "aux"}


def _fold_char(c: str) -> str:
    d = unicodedata.normalize("NFKD", c)
    return (d[0] if d else c).lower()


def fold(text: str) -> str:
    """Accent- and case-folding that keeps string length (index-aligned)."""
    return "".join(_fold_char(c) for c in text)


def norm(text: str) -> str:
    """Matching form: folded, hyphens and apostrophes as spaces, single spaces."""
    t = re.sub(r"[-‐–'’]", " ", fold(text))
    return re.sub(r"\s+", " ", t).strip()


def group_key(text: str) -> str:
    """Grouping key of long forms: `norm` without spaces, final s/x of each word dropped
    ("intubation oro-trachéale" = "intubation orotrachéale"; "infections du site opératoire" =
    "infection du site opératoire")."""
    return "".join(w[:-1] if len(w) > 3 and w[-1] in "sx" else w for w in norm(text).split())


# French words that are also written in capitals for emphasis ("ne nécessite PAS de …"): such a
# token is never read as an abbreviation in a query.
FRENCH_WORDS_IN_CAPS = frozenset(
    "pas ne ni non ou et si sans avec plus moins tous toutes aucun aucune jamais seul seule "
    "le la les un une des du de au aux en est sont car mais donc or que qui".split()
)


def is_french_word(tok: str) -> bool:
    return fold(tok) in FRENCH_WORDS_IN_CAPS


def is_abbreviation(tok: str) -> bool:
    if not re.fullmatch(ABBR_RE, tok):
        return False
    if sum(1 for c in tok if c.isupper()) < 2:
        return False
    if _ROMAN.match(tok) or tok.isdigit():
        return False
    letters = [c for c in tok if c.isalpha()]
    return len(letters) >= 2


def _letters(abbr: str) -> str:
    return "".join(c for c in fold(abbr) if c.isalnum())


def schwartz_hearst(short: str, text: str) -> str | None:
    """Shortest suffix of `text` (a word-aligned window before the parenthesis) that is a valid
    long form of `short`: its letters in order, right to left, the first one at a word start."""
    s_str, l_str = _letters(short), fold(text)
    s, l = len(s_str) - 1, len(l_str) - 1
    while s >= 0:
        c = s_str[s]
        while l >= 0 and (l_str[l] != c or (s == 0 and l > 0 and l_str[l - 1].isalnum())):
            l -= 1
        if l < 0:
            return None
        l -= 1
        s -= 1
    start = max(text.rfind(" ", 0, l + 1), text.rfind("\n", 0, l + 1)) + 1
    return text[start:].strip()


def forward_match(short: str, long_form: str) -> bool:
    """Glossary entries ("ABBR : long form"): the first letter starts the long form, the others
    follow in order."""
    s_str, l_str = _letters(short), fold(long_form)
    alnum = [i for i, c in enumerate(l_str) if c.isalnum()]
    if not s_str or not alnum or l_str[alnum[0]] != s_str[0]:
        return False
    pos = alnum[0] + 1
    for c in s_str[1:]:
        pos = l_str.find(c, pos)
        if pos < 0:
            return False
        pos += 1
    return True


def clean_long_form(text: str) -> str:
    t = re.sub(r"[*_`\[\]]", "", text)
    t = re.sub(r"\s+", " ", t).strip(" .,;:-–—\"'«»")
    t = _ELISION.sub("", t)
    t = _LEADING_ARTICLE.sub("", t)
    return t.strip()


def _valid_pair(abbr: str, long_form: str) -> bool:
    if not is_abbreviation(abbr) or not long_form:
        return False
    words = long_form.split()
    if not (1 <= len(words) <= 12) or len(long_form) > 120:
        return False
    if len(_letters(long_form)) < len(_letters(abbr)) + 2:
        return False
    if fold(words[-1]) in _STOP_END:
        return False
    if any(ch in long_form for ch in "()|:;=") or re.search(r"\d{3,}", long_form):
        return False
    if fold(abbr) in {fold(w) for w in words}:  # "ABP (ABP)" or the abbreviation itself
        return False
    return forward_match(abbr, long_form)


_PAREN_AFTER = re.compile(r"\(\s*(" + ABBR_RE + r")\s*[),;]")
_PAREN_LONG = re.compile(r"(?<![\w-])(" + ABBR_RE + r")\s*\(([^()\n]{3,120})\)")
_LINE_DEF = re.compile(r"^\s*[-*•]?\s*\**(" + ABBR_RE + r")\**\s*(?::|=|—|–|\s-\s)\s*(.{3,160})$")
_LIST_DEF = re.compile(r"(?:^|[;:.]\s*)\**(" + ABBR_RE + r")\**\s*,\s*([^;,]{3,100})(?=;|\.\s|$)")
_DASH_SPLIT = re.compile(r"\s[—–]\s")


def extract_definitions(text: str, glossary_context: bool = False) -> list[tuple[str, str, str]]:
    """(abbreviation, long form, pattern) pairs defined in `text`."""
    out: list[tuple[str, str, str]] = []
    # 1. "long form (ABBR)" — the classic inline definition.
    for m in _PAREN_AFTER.finditer(text):
        abbr = m.group(1)
        if not is_abbreviation(abbr):
            continue
        before = text[: m.start()]
        before = re.split(r"[\n;:()\[\]|]|\.\s", before)[-1] if before else ""
        words = before.split()
        n = min(len(_letters(abbr)) + 5, 2 * len(_letters(abbr)))
        window = " ".join(words[-n:])
        lf = schwartz_hearst(abbr, window) if window else None
        if lf:
            lf = clean_long_form(lf)
            if _valid_pair(abbr, lf):
                out.append((abbr, lf, "inline_long_then_abbr"))
    # 2. "ABBR (long form)".
    for m in _PAREN_LONG.finditer(text):
        abbr, lf = m.group(1), clean_long_form(m.group(2))
        if _valid_pair(abbr, lf):
            out.append((abbr, lf, "inline_abbr_then_long"))
    if not glossary_context:
        return out
    # 3. Glossary sections and tables.
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("section :"):
            continue
        cells = [c.strip() for c in line.split(" | ")]
        if len(cells) == 2:  # table row card "Abréviation : X | Signification : Y"
            vals = [c.split(" : ", 1)[1] if " : " in c else c for c in cells]
            abbr, lf = vals[0].strip("* "), clean_long_form(vals[1])
            if _valid_pair(abbr, lf):
                out.append((abbr, lf, "glossary_table"))
                continue
        parts = _DASH_SPLIT.split(line)
        if len(parts) >= 4 and len(parts) % 2 == 0:  # "FA — fibrillation … — TSV — tachycardie …"
            for a, b in zip(parts[0::2], parts[1::2]):
                a, lf = a.strip("* ,"), clean_long_form(b)
                if _valid_pair(a, lf):
                    out.append((a, lf, "glossary_list"))
            continue
        m = _LINE_DEF.match(line)
        if m:
            lf = clean_long_form(re.split(r"\s;\s|;\s*$", m.group(2))[0])
            if _valid_pair(m.group(1), lf):
                out.append((m.group(1), lf, "glossary_line"))
                continue
        for m in _LIST_DEF.finditer(line):  # "AB, antibiotique ; HC, hémocultures"
            lf = clean_long_form(m.group(2))
            if _valid_pair(m.group(1), lf):
                out.append((m.group(1), lf, "glossary_list"))
    return out


def build_glossary(chunks: Iterable[Any]) -> dict[str, Any]:
    """Aggregate definitions over chunks (objects with `.text`, `.doc_id`, `.section_path`).

    For each abbreviation, long forms are grouped by their folded text; the primary long form is
    the one defined in the most documents (ties: most occurrences)."""
    occ: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    docs: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    surface: dict[tuple[str, str], Counter] = defaultdict(Counter)
    patterns: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for ch in chunks:
        gctx = bool(_GLOSSARY_SECTION.search(getattr(ch, "section_path", "") or "")) or bool(
            _GLOSSARY_SECTION.search((ch.text or "")[:200])
        )
        for abbr, lf, pat in extract_definitions(ch.text or "", glossary_context=gctx):
            key = group_key(lf)
            occ[abbr][key]["n"] += 1
            docs[abbr][key].add(ch.doc_id)
            surface[(abbr, key)][lf] += 1
            patterns[(abbr, key)][pat] += 1
    entries = {}
    for abbr, forms in occ.items():
        lst = []
        for key, cnt in forms.items():
            lst.append({
                "long_form": surface[(abbr, key)].most_common(1)[0][0],
                "variants": sorted(surface[(abbr, key)]),
                "folded": key,
                "docs": len(docs[abbr][key]),
                "count": cnt["n"],
                "patterns": dict(patterns[(abbr, key)]),
            })
        lst.sort(key=lambda e: (-e["docs"], -e["count"], e["folded"]))
        entries[abbr] = {
            "abbr": abbr,
            "docs": len(set().union(*docs[abbr].values())),
            "long_forms": lst,
        }
    return {"n_abbreviations": len(entries), "entries": dict(sorted(entries.items()))}


def save_glossary(glossary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(glossary, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8")


def load_glossary(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def usable_entries(glossary: dict[str, Any], min_docs: int = 2) -> list[dict[str, Any]]:
    """Entries used for expansion / perturbation: the primary long form of each abbreviation,
    when it is defined in at least `min_docs` documents (rarer or ambiguous ones dropped)."""
    out = []
    for abbr, e in glossary["entries"].items():
        lf = e["long_forms"][0]
        if lf["docs"] >= min_docs:
            out.append({"abbr": abbr, "long_form": lf["long_form"], "variants": lf.get("variants", [lf["long_form"]]), "docs": lf["docs"]})
    return out


def usable_pairs(glossary: dict[str, Any], min_docs: int = 2) -> list[tuple[str, str]]:
    return [(e["abbr"], e["long_form"]) for e in usable_entries(glossary, min_docs)]


class GlossaryExpander:
    """Query-side expansion: an abbreviation of the query gets its long form appended, a long form
    of the query gets its abbreviation appended (same output format as `expand_medical_query`).
    Abbreviations are matched case-sensitively on whole tokens, long forms on `norm` text."""

    def __init__(self, entries: list[dict[str, Any]], long_to_abbr: bool = True) -> None:
        """`long_to_abbr=False`: only abbreviations of the query are expanded."""
        self.abbr_to_long: dict[str, str] = {}
        self.long_to_abbr: dict[str, str] = {}
        for e in entries:
            self.abbr_to_long.setdefault(e["abbr"], e["long_form"])
            for v in (e["variants"] if long_to_abbr else []):
                if len(norm(v)) >= 4:
                    self.long_to_abbr.setdefault(norm(v), e["abbr"])
        keys = sorted(self.long_to_abbr, key=len, reverse=True)
        self._long_re = re.compile(r"(?<!\w)(" + "|".join(re.escape(k) for k in keys) + r")(?!\w)") if keys else None

    def expand(self, query: str) -> tuple[str, dict[str, str]]:
        added: dict[str, str] = {}
        nq = norm(query)
        for tok in re.findall(r"(?<![\w-])[A-Za-z][A-Za-z0-9\-]{1,9}(?![\w-])", query):
            lf = self.abbr_to_long.get(tok)
            if lf and norm(lf) not in nq and not is_french_word(tok):
                added[tok] = lf
        if self._long_re is not None:
            for m in self._long_re.finditer(nq):
                abbr = self.long_to_abbr[m.group(1)]
                if not re.search(rf"(?<!\w){re.escape(abbr)}(?!\w)", query):
                    added[m.group(1)] = abbr
        if not added:
            return query, {}
        return f"{query} ({' '.join(dict.fromkeys(added.values()))})", added
