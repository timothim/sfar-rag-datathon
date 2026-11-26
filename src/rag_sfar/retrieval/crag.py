"""Corrective RAG (CRAG) & Self-MedRAG Clinical Multi-Hop Facet Decomposition.

Inspired by CRAG (Yan et al., 2024) and Self-MedRAG (2026):
1. Clinical Facet Decomposition: detects multi-hop queries combining a procedure/pathology
   with a systemic modifier (`E-BLSE`, `obèse/IMC`, `allergie`, `insuffisance rénale`,
   `pédiatrie`, explicit recommendation ID `R1.2.1`/`R1.6`) and constructs focused
   secondary retrieval sub-queries.
2. Corrective Confidence & Facet Coverage Gate: audits top-k passages and launches a
   targeted corrective rescue retrieval whenever a required clinical facet is under-covered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag_sfar.retrieval.medical_lexicon import fold_accents
from rag_sfar.schemas import QueryAnalysis, RetrievedChunk


@dataclass
class ClinicalFacet:
    """A mandatory clinical dimension detected in a user query that MUST be evidenced."""

    name: str
    subquery: str
    evidence_regex: re.Pattern[str]


# Rules mapping multi-hop clinical triggers -> targeted sub-query + verification regex
FACET_RULES: list[tuple[str, re.Pattern[str], str, re.Pattern[str]]] = [
    (
        "blse",
        re.compile(r"\b(?:e-?blse|blse|b[êe]ta-?lactamase\s+[àa]\s+spectre)\b", re.I),
        "colonisation rectale portage E-BLSE BLSE antibioprophylaxie antibiothérapie carbapénème ertapénème R1.7 R1.2",
        re.compile(r"\b(?:blse|ertap[ée]n[èe]me|carbap[ée]n[èe]me|r1\.7|r1\.2\.[235])\b", re.I),
    ),
    (
        "obesity",
        re.compile(r"\b(?:ob[èe]s\w*|imc|poids\s*>\s*100|100\s*kg)\b", re.I),
        "patient obèse IMC adaptation dose posologie antibioprophylaxie R1.5 R1.6 céfazoline amoxicilline clindamycine",
        re.compile(r"\b(?:ob[èe]s\w*|imc|r1\.5|r1\.6)\b", re.I),
    ),
    (
        "renal",
        re.compile(r"\b(?:insuffisance\s+r[ée]nale|clairance|dfg|clcr|cockcroft|fonction\s+r[ée]nale)\b", re.I),
        "insuffisance rénale DFG clairance créatinine adaptation délai arrêt AOD dabigatran apixaban rivaroxaban",
        re.compile(r"\b(?:dfg|clairance|r[ée]nal\w*|clcr|cockcroft)\b", re.I),
    ),
    (
        "pediatric",
        re.compile(r"\b(?:p[ée]diatr\w*|enfant\w*|nourrisson\w*|n[ée]onatal\w*)\b", re.I),
        "pédiatrie enfant posologie mg/kg dose initiale antibioprophylaxie pédiatrique",
        re.compile(r"\b(?:mg/kg|p[ée]diatri\w*|enfant)\b", re.I),
    ),
    # Note: Specialty allergy boxes are NOT run as procedure-blind Stage-1 subqueries (which would
    # flood Top-24 with allergy boxes from unrelated specialties); they are linked deterministically
    # via section-anchored `linked_callout_ids` on the matched surgical procedure's own specialty!
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
            # Contextualize sub-query with top domain anchor keywords from original query
            anchor_terms = _extract_anchor_terms(q_orig)
            subq = f"{anchor_terms} {base_subq}".strip()
            facets.append(ClinicalFacet(name=name, subquery=subq, evidence_regex=ev_re))

    return facets


def _extract_anchor_terms(query: str) -> str:
    """Keep concise topic anchor terms (e.g. antibioprophylaxie, intra-abdominale, AOD, colectomie)."""
    q_fold = fold_accents(query.lower())
    anchors = []
    for kw in (
        "antibioprophylaxie",
        "intra-abdominale",
        "anticoagulant",
        "aod",
        "avk",
        "colectomie",
        "colorectale",
        "orthopedique",
        "neurochirurgie",
        "hanche",
        "genou",
        "urgence",
        "programmee",
        "sepsis",
        "pediatrique",
    ):
        if kw in q_fold:
            anchors.append(kw)
    return " ".join(anchors[:4])


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


_PURE_DRUG_OR_DOSAGE_RE = re.compile(
    r"^(?:pas\s+d['’]antibioprophylaxie.*|aucune?.*|"
    r"(?:c[ée]fazoline|c[ée]furoxime|c[ée]foxitine|ceftriaxone|c[ée]fotaxime|amoxicilline|"
    r"clavulanate|clindamycine|vancomycine|t[ée]icoplanine|gentamicine|m[ée]tronidazole|"
    r"pip[ée]racilline|tazobactam|ertap[ée]n[èe]me|m[ée]rop[ée]n[èe]me|ciprofloxacine|"
    r"l[ée]vofloxacine|ofloxacine|fosfomycine|trim[ée]thoprime|sulfam[ée]thoxazole|aztr[ée]onam|"
    r"ou|et|\+|/|ivl|iv|po|im|per\s+os|\d+(?:[.,]\d+)?\s*(?:g|mg|mg/kg|ui|h|min|j-\d+)|"
    r"recommand[ée]e?|[\s,.;:-])+)$",
    re.I,
)
_MCQ_OPTION_LINE_RE = re.compile(r"^\s*([A-D])[.)]\s+(.+?)\s*$", re.M)
_COMPOSITE_SPLIT_RE = re.compile(
    r"\b(?:associ[ée]e?\s+[àa]|combin[ée]e?\s+[àa]|concomitante?\s+(?:d['’]une?|[àa])|"
    r"et\s+(?:la\s+pose\s+d['’]un|d['’]une?))\b",
    re.I,
)


def extract_mcq_option_subqueries(query: str) -> list[tuple[str, str]]:
    """For comparative MCQs whose choices are distinct clinical acts or statements (e.g.
    'Parmi ces interventions ORL... A. Implant cochléaire B. Amygdalectomie...'),
    build one targeted sub-query per option so EVERY option's SFAR evidence is retrieved.

    Skips pure drug-list / dosage-only MCQs (e.g. A. Gentamicine / B. Vancomycine) where
    the stem already identifies the single surgical act.
    """
    matches = _MCQ_OPTION_LINE_RE.findall(query)
    if len(matches) < 2:
        return []

    first_opt_pos = query.find(f"{matches[0][0]}.")
    stem = query[:first_opt_pos].strip() if first_opt_pos > 0 else query.splitlines()[0]
    stem_anchor = _extract_anchor_terms(stem)
    if "antibioprophylaxie" not in stem_anchor and (
        "antibioprophylaxie" in fold_accents(stem.lower()) or "orl" in stem.lower()
    ):
        stem_anchor = f"antibioprophylaxie {stem_anchor}".strip()

    substantive: list[tuple[str, str]] = []
    for letter, opt_text in matches:
        clean = opt_text.strip()
        if len(clean) < 4:
            continue
        if _PURE_DRUG_OR_DOSAGE_RE.match(clean):
            continue
        substantive.append((letter, f"{stem_anchor} {clean}".strip()))

    # Only trigger option-aware multi-retrieval when >= 2 options are substantive clinical statements/acts
    return substantive if len(substantive) >= 2 else []


def strip_mcq_distractor_options(query: str) -> str:
    """Prevent MCQ Distractor-Leakage Contamination during retrieval.

    When an MCQ lists candidate drug/dosage answers (e.g. `A. Amoxicilline/Clavulanate`,
    `B. Céfazoline`, `C. Clindamycine`, `D. Vancomycine` -> `extract_mcq_option_subqueries == []`),
    feeding those distractor drug names into BM25/Dense/Cross-Encoder hijacks retrieval toward
    unrelated specialties that prescribe those distractors (e.g. ORL/Orthopédie instead of
    Chirurgie Cardiaque or PTG!). Stripping the A/B/C/D distractor lines during retrieval
    keeps search 100% focused on the true clinical stem while the LLM still sees all choices.
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
    """Detect composite multi-act surgical queries (e.g. 'splénectomie d'hémostase associée à
    la pose d'un fixateur externe sur fracture fermée du fémur') and split into atomic
    procedure sub-queries so BOTH surgical acts are guaranteed retrieval coverage."""
    # Only operate on the question stem (before MCQ choices if any)
    m_opt = _MCQ_OPTION_LINE_RE.search(query)
    stem = query[: m_opt.start()].strip() if m_opt else query.strip()
    parts = [p.strip(" ,;?.:") for p in _COMPOSITE_SPLIT_RE.split(stem) if p and len(p.strip()) >= 12]
    if len(parts) < 2:
        return []
    anchor = _extract_anchor_terms(stem)
    out: list[str] = []
    for part in parts[:3]:
        if len(re.findall(r"[a-zA-ZÀ-ÿ]{4,}", part)) < 2:
            continue
        sub = part if anchor.split(" ")[0] in fold_accents(part.lower()) else f"{anchor} {part}".strip()
        out.append(sub)
    return out if len(out) >= 2 else []
