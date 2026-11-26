"""Post-generation clinical safety, citation, and molecule-grounding verifier."""

from __future__ import annotations

import re

from rag_sfar.retrieval.medical_lexicon import fold_accents
from rag_sfar.schemas import RetrievedChunk, VerificationReport

# High-risk clinical drug molecules tracked for ungrounded hallucination detection
TRACKED_MOLECULES: tuple[str, ...] = (
    "cefazoline",
    "cefuroxime",
    "cefoxitine",
    "ceftriaxone",
    "cefotaxime",
    "ceftazidime",
    "cefepime",
    "amoxicilline",
    "clavulanate",
    "piperacilline",
    "tazobactam",
    "ertapeneme",
    "meropeneme",
    "imipeneme",
    "metronidazole",
    "clindamycine",
    "vancomycine",
    "teicoplanine",
    "gentamicine",
    "amikacine",
    "tobramycine",
    "fosfomycine",
    "ciprofloxacine",
    "levofloxacine",
    "ofloxacine",
    "trimethoprime",
    "sulfamethoxazole",
    "pristinamycine",
    "aztreonam",
    "azithromycine",
    "clarithromycine",
    "erythromycine",
    "spiramycine",
    "rifampicine",
    "tigecycline",
    "colistine",
    "temocilline",
    "daptomycine",
    "linezolide",
    "linezolid",
    "fluconazole",
    "caspofungine",
    "micafungine",
    "apixaban",
    "rivaroxaban",
    "dabigatran",
    "edoxaban",
    "warfarine",
    "fluindione",
    "acenocoumarol",
    "enoxaparine",
    "tinzaparine",
    "heparine",
    "fondaparinux",
    "danaparoide",
    "argatroban",
    "aspirine",
    "clopidogrel",
    "prasugrel",
    "ticagrelor",
    "idarucizumab",
    "andexanet",
    "vitamine k",
    "protamine",
    "sugammadex",
    "dantrolene",
    "adrenaline",
    "noradrenaline",
    "tranexamique",
)

ABSTENTION_PATTERNS = (
    "hors perimetre",
    "non retrouve",
    "ne permettent pas de repondre",
    "information manquante",
    "non couverte par les recommandations",
    "ne traitent pas cette question",
)


def verify_generation(
    answer: str,
    retrieved: list[RetrievedChunk],
    mode: str = "clinical_detailed",
) -> VerificationReport:
    """Deterministically audit an LLM response against retrieved clinical evidence.

    Checks:
    1. All inline `[Si]` citations resolve to actual retrieved chunks (`1..len(retrieved)`).
    2. Every tracked drug molecule mentioned in the answer appears in the retrieved evidence
       (catches parametric hallucinations like inventing a wrong antibiotic or anticoagulant!).
    3. Flags if obsolete/superseded editions were cited in the retrieved context.
    """
    n_sources = len(retrieved)
    cited_nums = sorted(set(re.findall(r"\[S(\d+)\]", answer)))
    citations_found = [f"S{n}" for n in cited_nums]
    invalid_citations = [f"S{n}" for n in cited_nums if int(n) < 1 or int(n) > n_sources]

    ans_fold = fold_accents(answer.lower())
    ctx_fold = fold_accents(" ".join(r.chunk.indexed_text.lower() for r in retrieved))

    mentioned = [m for m in TRACKED_MOLECULES if re.search(rf"\b{re.escape(m)}\b", ans_fold)]
    ungrounded = [m for m in mentioned if not re.search(rf"\b{re.escape(m)}\b", ctx_fold)]

    obsolete_used = [
        f"S{i} ({r.chunk.doc_title}, {r.chunk.effective_year})"
        for i, r in enumerate(retrieved, start=1)
        if not r.chunk.is_latest_edition
    ]

    is_abstention = any(p in ans_fold for p in ABSTENTION_PATTERNS)

    warnings: list[str] = []
    score = 1.0

    if invalid_citations:
        warnings.append(f"Citations inexistantes détectées : {', '.join(invalid_citations)}")
        score -= 0.35
    if ungrounded:
        warnings.append(
            f"Molécule(s) mentionnée(s) absente(s) des extraits récupérés (risque d'hallucination) : {', '.join(ungrounded)}"
        )
        score -= min(0.5, 0.25 * len(ungrounded))
    if mode == "clinical_detailed" and not citations_found and not is_abstention:
        warnings.append("Aucune citation en ligne [S1], [S2]... détectée dans la réponse.")
        score -= 0.20
    if obsolete_used:
        warnings.append(f"Sources antérieures dans le contexte : {'; '.join(obsolete_used[:2])}")

    return VerificationReport(
        citations_found=citations_found,
        invalid_citations=invalid_citations,
        mentioned_molecules=mentioned,
        ungrounded_molecules=ungrounded,
        obsolete_sources_used=obsolete_used,
        is_abstention=is_abstention,
        grounding_score=round(max(0.0, score), 3),
        warnings=warnings,
    )
