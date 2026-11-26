"""Corrective RAG (CRAG) & Self-MedRAG Clinical Multi-Hop Facet Decomposition.

Inspired by CRAG (Yan et al., 2024) and Self-MedRAG (2026):
1. Clinical Facet Decomposition: detects multi-hop queries combining a procedure/pathology
   with a systemic modifier (resistant-bacteria carriage, obesity, renal impairment, paediatric
   population, explicit recommendation identifier) and builds a secondary sub-query made of the
   original question plus generic modifier terms. No molecule, procedure or recommendation
   number is hard-coded (CLAUDE.md, principle 1).
2. Corrective Confidence & Facet Coverage Gate: audits top-k passages and launches a
   targeted corrective rescue retrieval whenever a required clinical facet is under-covered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag_sfar.retrieval.medical_lexicon import fold_accents, tokenize_medical_french
from rag_sfar.schemas import QueryAnalysis, RetrievedChunk


@dataclass
class ClinicalFacet:
    """A mandatory clinical dimension detected in a user query that MUST be evidenced."""

    name: str
    subquery: str
    evidence_regex: re.Pattern[str]


# Rules mapping a systemic clinical modifier -> generic modifier terms + evidence regex.
# The sub-query is `<original question> <modifier terms>`: the topic comes from the question
# itself, never from a hard-coded list of molecules or recommendation numbers.
FACET_RULES: list[tuple[str, re.Pattern[str], str, re.Pattern[str]]] = [
    (
        "blse",
        re.compile(r"\b(?:e-?blse|blse|b[êe]ta-?lactamase\s+[àa]\s+spectre)\b", re.I),
        "BLSE bêta-lactamase à spectre élargi colonisation portage",
        re.compile(r"\b(?:e-?blse|blse|b[êe]ta-?lactamases?\s+[àa]\s+spectre)\b", re.I),
    ),
    (
        "obesity",
        re.compile(r"\b(?:ob[èe]s\w*|imc|poids\s*>\s*100|100\s*kg)\b", re.I),
        "patient obèse obésité IMC poids adaptation posologie",
        re.compile(r"\b(?:ob[èe]s\w*|imc)\b", re.I),
    ),
    (
        "renal",
        re.compile(r"\b(?:insuffisance\s+r[ée]nale|clairance|dfg|clcr|cockcroft|fonction\s+r[ée]nale)\b", re.I),
        "insuffisance rénale fonction rénale DFG clairance créatinine adaptation",
        re.compile(r"\b(?:dfg|clairance|r[ée]nal\w*|clcr|cockcroft)\b", re.I),
    ),
    (
        "pediatric",
        re.compile(r"\b(?:p[ée]diatr\w*|enfant\w*|nourrisson\w*|n[ée]onatal\w*)\b", re.I),
        "pédiatrie enfant posologie mg/kg",
        re.compile(r"\b(?:mg/kg|p[ée]diatri\w*|enfant)\b", re.I),
    ),
    # Note: allergy boxes are NOT searched as procedure-blind sub-queries (that would flood the
    # pool with allergy boxes of unrelated sections); they are linked through the section of the
    # matched chunk (`linked_callout_ids`).
]


def detect_clinical_facets(analysis: QueryAnalysis) -> list[ClinicalFacet]:
    """Identify distinct clinical facets requiring explicit evidentiary coverage."""
    q_orig = analysis.original_query
    facets: list[ClinicalFacet] = []

    # 1. Explicit recommendation IDs (e.g., R1.1, R1.2.1, R1.6, R2.1.2)
    rec_ids = re.findall(r"\bR\d+\.\d+(?:\.\d+)?\b", q_orig, re.I)
    for rid in rec_ids[:2]:
        facets.append(
            ClinicalFacet(
                name=f"rec_id:{rid.upper()}",
                subquery=f"{rid.upper()} {q_orig}",
                evidence_regex=re.compile(rf"\b{re.escape(rid)}\b", re.I),
            )
        )

    # 2. Systemic clinical modifiers
    for name, trigger_re, base_subq, ev_re in FACET_RULES:
        if trigger_re.search(q_orig):
            # The question itself carries the topic; the modifier terms carry the facet.
            subq = f"{q_orig} {base_subq}".strip()
            facets.append(ClinicalFacet(name=name, subquery=subq, evidence_regex=ev_re))

    return facets


# Generic French question wording that carries no topic (interrogatives, MCQ scaffolding).
_QUESTION_WORDS: frozenset[str] = frozenset(
    {
        "parmi", "laquelle", "lequel", "lesquelles", "lesquels", "quelle", "quelles", "quel", "quels",
        "suivante", "suivantes", "suivant", "suivants", "proposition", "propositions", "affirmation",
        "affirmations", "reponse", "reponses", "exacte", "exactes", "inexacte", "inexactes",
        "correcte", "correctes", "incorrecte", "incorrectes", "vrai", "vraie", "faux", "fausse",
        "conduite", "tenir", "necessite", "necessitent", "recommande", "recommandee", "recommandees",
        "indique", "indiquee", "indiquees", "concernant", "propose", "proposee", "cas", "chez",
        "sauf", "selon", "actuelles", "actuelle",
    }
)


def _extract_anchor_terms(query: str, max_terms: int = 6) -> str:
    """Topic anchor of a question stem: its first content words (stopwords and generic question
    wording removed). Derived from the question only — no hard-coded topic list."""
    terms: list[str] = []
    for tok in tokenize_medical_french(query):
        if len(tok) < 3 or tok.isdigit() or tok in _QUESTION_WORDS or tok in terms:
            continue
        terms.append(tok)
        if len(terms) >= max_terms:
            break
    return " ".join(terms)


def find_missing_facets(
    retrieved: list[RetrievedChunk],
    facets: list[ClinicalFacet],
    min_chunks_per_facet: int = 1,
) -> list[ClinicalFacet]:
    """Audit retrieved passages and return clinical facets that lack direct evidence."""
    missing: list[ClinicalFacet] = []
    for facet in facets:
        covered = sum(1 for r in retrieved if facet.evidence_regex.search(r.chunk.indexed_text))
        if covered < min_chunks_per_facet:
            missing.append(facet)
    return missing


# Words recognised as drug names from the WHO INN "stem" conventions (international
# nonproprietary names share standardised affixes per pharmacological class), in French spelling.
# This is a referential-based rule (not a list of molecules from one guideline); unknown names
# simply fall back to being treated as clinical statements.
_INN_STEM_RE = re.compile(
    r"^(?:c[ée]f\w+|c[ée]ph\w+|\w*(?:cillines?|mycines?|micines?|oxacines?|p[ée]n[èe]mes?|bactam|"
    r"nidazoles?|conazoles?|azoles?|planines?|primes?|xaban|gatran|parines?|curonium|curium|"
    r"ca[ïi]nes?|azepam|azolam|olol|prils?|sartans?|statines?|prazoles?|s[ée]trons?|fentanil|"
    r"grel(?:or)?|fibans?|tidines?|clavulan\w*|sulfam\w*))$",
    re.I,
)
_DOSE_OR_ROUTE_RE = re.compile(
    r"^(?:\d+(?:[.,]\d+)?(?:g|mg|µg|ug|mcg|ui|ml|h|min|j)?(?:/(?:kg|h|j|m2))*|j-?\d+|"
    r"ivl?|ivd|ivse|po|im|sc|per|os|seule?s?|en|dose|unique|puis|ou|et|avec|recommand[ée]e?s?|"
    r"g|mg|µg|ui|kg|h|min|mg/kg|/|\+)$",
    re.I,
)
# Options stating the absence of an intervention ("Pas de …", "Aucun …") are answer labels,
# not clinical acts to retrieve separately.
_NEGATIVE_OPTION_RE = re.compile(r"^\s*(?:pas\s+d|aucune?\b|ne\s+pas\b|abstention\b)", re.I)


def _is_drug_or_dosage_option(text: str) -> bool:
    """True when an MCQ option is only drug names (INN stems), doses, routes and connectors,
    or a negative label; such options do not describe distinct clinical situations."""
    if _NEGATIVE_OPTION_RE.match(text):
        return True
    words = [w for w in re.split(r"[\s,;:()]+|(?<=[a-zé])/(?=[a-zé])|\+", fold_accents(text.lower())) if w]
    if not words:
        return False
    return all(_INN_STEM_RE.match(w) or _DOSE_OR_ROUTE_RE.match(w) for w in words)


_MCQ_OPTION_LINE_RE = re.compile(r"^\s*([A-E])[.)]\s+(.+?)\s*$", re.M)
# Composite questions: two situations explicitly joined by an association phrase.
_COMPOSITE_SPLIT_RE = re.compile(
    r"\b(?:associ[ée]e?s?\s+[àa]|combin[ée]e?s?\s+[àa]|concomitante?s?\s+(?:d['’]une?|[àa]))\b",
    re.I,
)


def extract_mcq_option_subqueries(query: str) -> list[tuple[str, str]]:
    """For comparative MCQs whose choices are distinct clinical situations or statements,
    build one targeted sub-query per option (stem topic + option) so the evidence for EVERY
    option is retrieved.

    Skips drug-list / dosage-only MCQs, where the stem already identifies the situation.
    """
    matches = list(_MCQ_OPTION_LINE_RE.finditer(query))
    if len(matches) < 2:
        return []

    first_opt_pos = matches[0].start()
    stem = query[:first_opt_pos].strip() if first_opt_pos > 0 else query.splitlines()[0]
    stem_anchor = _extract_anchor_terms(stem)

    substantive: list[tuple[str, str]] = []
    for m in matches:
        letter, clean = m.group(1), m.group(2).strip()
        if len(clean) < 4:
            continue
        if _is_drug_or_dosage_option(clean):
            continue
        substantive.append((letter, f"{stem_anchor} {clean}".strip()))

    # Only trigger option-aware multi-retrieval when >= 2 options are substantive statements
    return substantive if len(substantive) >= 2 else []


def strip_mcq_distractor_options(query: str) -> str:
    """Prevent MCQ distractor contamination during retrieval.

    When an MCQ lists candidate drug/dosage answers (`extract_mcq_option_subqueries == []`),
    feeding the distractor drug names into BM25/dense/cross-encoder pulls retrieval toward
    sections that prescribe those distractors. The option lines are stripped for retrieval only;
    the LLM still sees all choices.
    """
    matches = _MCQ_OPTION_LINE_RE.findall(query)
    if len(matches) < 2:
        return query
    # Keep full query if choices are comparative clinical acts/statements
    if extract_mcq_option_subqueries(query):
        return query
    m_first = _MCQ_OPTION_LINE_RE.search(query)
    if not m_first:
        return query
    stem = query[: m_first.start()].strip()
    return stem if len(stem) >= 12 else query


def extract_composite_procedure_subqueries(query: str) -> list[str]:
    """Detect questions that explicitly associate two clinical situations ("X associée à Y")
    and split them into one sub-query per situation, so both get retrieval coverage."""
    # Only operate on the question stem (before MCQ choices if any)
    m_opt = _MCQ_OPTION_LINE_RE.search(query)
    stem = query[: m_opt.start()].strip() if m_opt else query.strip()
    parts = [p.strip(" ,;?.:") for p in _COMPOSITE_SPLIT_RE.split(stem) if p and len(p.strip()) >= 12]
    if len(parts) < 2:
        return []
    out: list[str] = []
    for part in parts[:3]:
        if len(re.findall(r"[a-zA-ZÀ-ÿ]{4,}", part)) < 2:
            continue
        out.append(part)
    return out if len(out) >= 2 else []
