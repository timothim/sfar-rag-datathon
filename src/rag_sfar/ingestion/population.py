"""Population labels of a chunk, derived from the structure of SFAR documents.

Labels: "adulte", "pediatrie", "neonatal", "obstetrique" (a chunk can carry several).
Sources, by decreasing priority (the first one that yields a label wins):
1. "table": the table's own scope lines (scope note "Les posologies de ce tableau concernent
   l'enfant ...", sub-category banner, table title);
2. "section": the deepest heading of the section path that names a population
   ("CHAMP 3 ... pédiatriques et néonatales", "Chez l'adulte", "Femme enceinte");
3. "document": the document title (and file name) when it names a population.
Nothing is inferred from free prose: a passing mention of "enfant" in an argumentaire does not
make a chunk pediatric. Negated mentions ("hors néonatalogie", "sauf l'enfant", "à l'exclusion
des femmes enceintes", "non obstétrical") are ignored.
"""

from __future__ import annotations

import re
import unicodedata

POPULATIONS = ("adulte", "pediatrie", "neonatal", "obstetrique")

_TERMS: dict[str, str] = {
    "adulte": r"adultes?",
    "pediatrie": r"p[eé]diatri\w*|enfants?|nourrissons?|adolescent\w*|petite?s?\s+enfants?",
    "neonatal": r"n[eé]onat\w*|nouveau[- ]n[eé]e?s?|pr[eé]matur[eé]e?s?",
    "obstetrique": (
        r"obst[eé]tri\w*|femmes?\s+enceintes?|grossesses?|parturientes?|accouchements?|"
        r"c[eé]sariennes?|post[- ]?partum|p[eé]ripartum|pr[eé][- ]?[eé]clampsies?|[eé]clampsies?|"
        r"gestationnel\w*|enceintes?"
    ),
}
_TERM_RE = {k: re.compile(rf"(?<![\w-])(?:{v})(?![\w])", re.I) for k, v in _TERMS.items()}
_NEGATION_BEFORE_RE = re.compile(
    r"(?:\bhors|\bsauf|\br[eé]f[eé]rer\s+(?:au|aux|à)|\bcf\.?|\bvoir|\bcomme\s+chez|\bexcept\w*|\bexclu\w*|\bexclusion\s+(?:de|des|du)|\bnon|\bpas\s+(?:de|d['’]|chez)|\bsans)"
    r"(?:\s+(?:la|le|les|l['’]|de|des|du|d['’]|chez|une?|en|population|tableaux?|posologies?|doses?|"
    r"recommandations?|protocoles?))*\s*\(?\s*$",
    re.I,
)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def population_terms(text: str) -> set[str]:
    """Populations named (and not negated) in a short structural text (heading, banner, note)."""
    found: set[str] = set()
    t = _fold(text)
    for pop, rx in _TERM_RE.items():
        for m in rx.finditer(t):
            before = t[max(0, m.start() - 40) : m.start()]
            if _NEGATION_BEFORE_RE.search(before):
                continue
            # "-" glued forms like "non-obstétrical"
            if re.search(r"\bnon[- ]$", before, re.I):
                continue
            found.add(pop)
            break
    if "neonatal" in found:
        found.add("pediatrie")
    return found


_AGE_GROUPS = {"adulte", "pediatrie", "neonatal"}


def _refine(current: set[str], deeper: set[str]) -> set[str]:
    """A deeper label that names an age group replaces the inherited age group; "obstetrique"
    accumulates."""
    if not deeper:
        return current
    out = set(current)
    if deeper & _AGE_GROUPS:
        out -= _AGE_GROUPS
    return out | deeper


def populations_from_section(section_path: str) -> set[str]:
    """Populations named along a section path, refined from the root to the deepest heading."""
    pops: set[str] = set()
    for heading in (p.strip() for p in (section_path or "").split(" > ")):
        if heading:
            pops = _refine(pops, population_terms(heading))
    return pops


def infer_chunk_populations(
    section_path: str,
    table_scope_text: str = "",
    doc_title: str = "",
) -> tuple[list[str], str]:
    """(populations, source) for one chunk; see the module docstring for the rules."""
    sec = populations_from_section(section_path)
    # Only the first sentence of a scope note states the table's population ("... concernent
    # l'enfant de moins de 50 kg. Au-delà, se référer au tableau adulte.").
    first = re.split(r"(?<=[.!?])\s+", table_scope_text.strip(), maxsplit=1)[0] if table_scope_text else ""
    tab = population_terms(first) if first else set()
    if tab:
        return sorted(_refine(sec, tab)), "table"
    if sec:
        return sorted(sec), "section"
    pops = population_terms(doc_title)
    if pops:
        return sorted(pops), "document"
    return [], ""


def legacy_hint_from_populations(pops: list[str]) -> str:
    """Map structural populations onto the legacy `population_hint` values."""
    s = set(pops)
    ped = bool(s & {"pediatrie", "neonatal"})
    adult = "adulte" in s
    if ped and adult:
        return "mixte"
    if ped:
        return "pediatrie"
    if adult:
        return "adulte"
    return "non_specifie"
