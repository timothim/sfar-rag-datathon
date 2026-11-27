"""Zero-latency deterministic clinical query analyzer & metadata router."""

from __future__ import annotations

import re

from rag_sfar.ingestion.loader import infer_domains_from_text
from rag_sfar.retrieval.medical_lexicon import expand_medical_query, fold_accents
from rag_sfar.schemas import PopulationScope, QueryAnalysis, SettingScope

TEMPORAL_DIFF_PATTERNS = [
    r"\b(?:qu['’]est[- ]ce\s+qui\s+a\s+chang[ée]|a\s+chang[ée]\s+(?:dans|entre|depuis))\b",
    r"\b[ée]volution\s+(?:des\s+recommandations|entre|depuis)\b",
    r"\bdiff[ée]rences?\s+entre\b",
    r"\bcompar\w*\s+(?:les\s+)?(?:recommandations|[ée]ditions|versions)\b",
    r"\bancienne(?:s)?\s+(?:recommandation|[ée]dition|version)\b",
    r"\bpr[ée]c[ée]dente(?:s)?\s+(?:recommandation|[ée]dition|version)\b",
    r"\bhistorique\s+des\s+versions\b",
    r"\bentre\s+20\d{2}\s+et\s+20\d{2}\b",
    r"\bmise\s+[àa]\s+jour\s+20\d{2}\b",
    r"\bversion\s+20\d{2}\b",
    r"\bv[123]\.\d+\b",
]

# Population is set only when the query states it. A bare duration ("6 mois", "3 ans") is not
# an age: it needs an age context ("âgé de 6 mois", "enfant de 3 ans", "nourrisson de 2 mois").
# French gender and number are handled systematically: every population noun or adjective that
# has a feminine form accepts it (âgé/âgée, adolescent/adolescente, nouveau-né/nouveau-née,
# patient/patiente), and every one accepts the plural.
_AGE_CONTEXT = (
    r"(?:[âa]g[ée]e?s?\s+de|enfants?\s+de|nourrissons?\s+de|gar[çc]ons?\s+de|filles?\s+de|"
    r"fillettes?\s+de|adolescente?s?\s+de|patiente?s?\s+de)"
)
PEDIATRIC_QUERY_RE = re.compile(
    r"\b(enfants?|p[ée]diatr\w*|nourrissons?|nouveau[- ]n[ée]e?s?|n[ée]onat\w*|b[ée]b[ée]s?|"
    r"adolescente?s?|fillettes?|gar[çc]onnets?|"
    rf"{_AGE_CONTEXT}\s+\d+\s*(?:jours?|semaines?|mois)|"
    rf"{_AGE_CONTEXT}\s+(?:[1-9]|1[0-7])\s*ans?)\b",
    re.I,
)
ADULT_QUERY_RE = re.compile(
    r"\b(adultes?|sujets?\s+[âa]g[ée]e?s?|personnes?\s+[âa]g[ée]e?s?|"
    rf"{_AGE_CONTEXT}\s+(?:1[89]|[2-9]\d|1[0-1]\d)\s*ans?)\b",
    re.I,
)

URGENCE_QUERY_RE = re.compile(
    r"\b(urgences?|urgente?s?|non\s+programm[ée]e?s?|h[ée]morragie\s+grave|r[ée]vers\w*|antidote|"
    r"traumatisme\s+grave|choc\s+h[ée]morragique|polytraumatis\w*|d[ée]chocage)\b",
    re.I,
)
PROGRAMME_QUERY_RE = re.compile(
    r"\b(programm[ée]e?s?|chirurgie\s+programm\w*|[ée]lective?s?|proc[ée]dure\s+invasive\s+programm\w*|"
    r"ambulatoire|proth[èe]se\s+totale|arthrod[èe]se|geste\s+programm\w*)\b",
    re.I,
)
REA_QUERY_RE = re.compile(r"\b(r[ée]animation|soins\s+critiques|sdra|ventilation\s+m[ée]canique|choc\s+septique)\b", re.I)

MODIFIER_PATTERNS: dict[str, re.Pattern[str]] = {
    # Mentions of allergy / hypersensitivity only: a drug class ("pénicilline") or the word
    # "alternative" is not an allergy.
    "allergy": re.compile(r"\b(allerg\w*|hypersensibilit\w*)\b", re.I),
    "obesity": re.compile(r"\b(ob[èe]s\w*|imc|surpoids|poids\s*>\s*100|100\s*kg)\b", re.I),
    "renal": re.compile(r"\b(r[ée]nal\w*|clairance|dfg|clcr|cockcroft|dialys\w*|insuffisance\s+r[ée]nale)\b", re.I),
    "dosage": re.compile(r"\b(posologie\w*|dose\w*|dosage\w*|r[ée]injection\w*|dur[ée]e\w*|d[ée]lai\w*|arr[êe]t\w*|j-\d+|reprise\w*|relais)\b", re.I),
    "grade": re.compile(r"\b(grade\w*|niveau\s+de\s+preuve|accord\s+d|avis\s+d.?experts?)\b", re.I),
    "references": re.compile(r"\b(r[ée]f[ée]rences?\s+bibliographiques?|bibliographie|[ée]tudes?\s+cit[ée]es?|auteurs?)\b", re.I),
}


# Negation scope (NegEx-style pre-negation, Harkema et al. 2009, with a tight scope).
# A negation cue applies to the term that IMMEDIATELY follows it, not to the rest of the
# sentence: "sans allergie", "non allergique", "pas d'allergie", "ni obésité", "aucun
# antécédent d'allergie" are negated; "non diabétique allergique à X" or "sans antécédent
# particulier, allergique à X" are NOT (the cue negates "diabétique" / "antécédent particulier").
# Between the cue and the term only closed-class words are allowed: elided or plain articles
# and prepositions, and the generic evidential nouns "antécédent(s) de", "notion de",
# "signe(s) de", "histoire de". Any other word (adjective, noun, verb) ends the scope.
_NEG_CUE = r"(?:sans|pas|aucune?|ni|non|jamais|absence|indemne|exempte?s?)"
_NEG_BRIDGE_WORD = (
    r"(?:d['’]|l['’]|(?:de|du|des|la|le|les|un|une|ant[ée]c[ée]dents?|notions?|signes?|histoire)\b)"
)
_NEG_SCOPE_RE = re.compile(
    rf"\b{_NEG_CUE}(?:[\s\-]+|(?=d['’]))(?:{_NEG_BRIDGE_WORD}[\s\-]*)*$",
    re.I,
)


def is_negated_at(text: str, start: int) -> bool:
    """True when the term starting at `start` in `text` is directly governed by a negation cue."""
    return bool(_NEG_SCOPE_RE.search(text[max(0, start - 80) : start]))


def has_affirmed_match(pattern: re.Pattern[str], text: str) -> bool:
    """Return True iff `pattern` matches at least one non-negated occurrence in `text`."""
    return any(not is_negated_at(text, m.start()) for m in pattern.finditer(text))


_NEGATABLE_MODIFIERS = frozenset({"allergy", "obesity", "renal"})


def _affirmed_text(query: str, acronyms: dict[str, str]) -> str:
    """The query followed by the expansions of its non-negated acronyms ("sans IRC" does not
    contribute "insuffisance rénale chronique"). The separator ends any negation scope."""
    kept = []
    for acr, expansion in acronyms.items():
        positions = [m.start() for m in re.finditer(rf"(?<!\w){re.escape(acr)}(?!\w)", query)]
        if any(not is_negated_at(query, pos) for pos in positions):
            kept.append(expansion)
    return query if not kept else f"{query} ; {' ; '.join(dict.fromkeys(kept))}"


def analyze_query(query: str, use_lexicon: bool = True) -> QueryAnalysis:
    """Analyze clinical intent, temporal scope, population, setting, and modifiers."""
    if use_lexicon:
        expanded, acronyms = expand_medical_query(query)
    else:
        expanded, acronyms = query, {}

    q_low = query.lower()
    exp_low = expanded.lower()
    q_fold = fold_accents(exp_low)

    # 1. Temporal intent
    years = sorted({int(y) for y in re.findall(r"\b(20[0-2]\d)\b", query)})
    is_diff = any(re.search(p, q_low) for p in TEMPORAL_DIFF_PATTERNS)
    if is_diff or len(years) >= 2:
        temporal_mode = "all_versions"
    elif len(years) == 1:
        temporal_mode = "specific_year"
    else:
        temporal_mode = "latest_only"

    # 2. Population intent
    population: PopulationScope = "non_specifie"
    has_ped = bool(PEDIATRIC_QUERY_RE.search(q_low))
    has_adult = bool(ADULT_QUERY_RE.search(q_low))
    if has_ped and not has_adult:
        population = "pediatrie"
    elif has_adult and not has_ped:
        population = "adulte"
    elif has_ped and has_adult:
        population = "mixte"

    # 3. Setting intent
    setting: SettingScope = "non_specifie"
    has_urg = bool(URGENCE_QUERY_RE.search(q_low))
    has_prog = bool(PROGRAMME_QUERY_RE.search(q_low))
    has_rea = bool(REA_QUERY_RE.search(q_low))
    if has_urg and not has_prog:
        setting = "urgence"
    elif has_prog and not has_urg:
        setting = "programme"
    elif has_rea and not has_prog and not has_urg:
        setting = "reanimation"

    # 4. Clinical modifiers (NegEx-guarded for patient-state conditions like allergy/obesity/renal)
    modifiers: list[str] = []
    affirmed_text = _affirmed_text(query, acronyms)
    for name, pat in MODIFIER_PATTERNS.items():
        if name in _NEGATABLE_MODIFIERS:
            if has_affirmed_match(pat, affirmed_text):
                modifiers.append(name)
        elif pat.search(exp_low):
            modifiers.append(name)
    if is_diff and "diff" not in modifiers:
        modifiers.append("diff")

    # 5. Soft domain hints (used for soft boosting — NEVER blind hard subdomain filtering!)
    # Word-anchored matching on the expanded query (no substring hits such as "rac" in "fracture").
    inferred_domains = infer_domains_from_text(q_fold)

    return QueryAnalysis(
        original_query=query,
        expanded_query=expanded,
        acronyms_expanded=acronyms,
        temporal_mode=temporal_mode,
        requested_years=years,
        inferred_domains=inferred_domains,
        population=population,
        setting=setting,
        modifiers=modifiers,
        wants_references=("references" in modifiers),
    )


# A patient allergy stated in the question ("allergique à X", "allergie aux X", "antécédent
# d'allergie à X", "hypersensibilité à X"), unless negated ("pas d'allergie", "non allergique",
# "sans allergie", "aucune allergie").
_AFFIRMED_ALLERGY_RE = re.compile(
    r"\b(?:allergiques?|allergies?|hypersensibilit[ée]s?)(?:\s+(?:connue|av[ée]r[ée]e|document[ée]e|"
    r"imm[ée]diate|retard[ée]e|grave|s[ée]v[èe]re)s?)*\s+(?:[àa]|aux|au|envers)\s+[^,;.?!\n]{2,60}?"
    r"(?=\s+(?:et|ou|pour|avec|chez|devant|lors|avant|apr[èe]s|qui|quel\w*)\b|\s*[,;.?!:\n]|\s*$)",
    re.I,
)


def detect_affirmed_allergy(query: str) -> str | None:
    """Return the allergy statement made in the question (e.g. "allergique à la X"), or None.

    Generic: no allergen class is assumed; the returned span is quoted back as written."""
    for m in _AFFIRMED_ALLERGY_RE.finditer(query):
        if is_negated_at(query, m.start()):
            continue
        return m.group(0).strip()
    return None
