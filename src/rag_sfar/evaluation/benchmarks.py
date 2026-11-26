"""Benchmark dataset loaders:
1. Official 171-question SFAR Antibioprophylaxie benchmark (`tomboulier/antibioprophylaxie-LLM-benchmark`)
2. Curated 30-question Multi-RFE Clinical Stress Benchmark grounded in the 2024–2026 SFAR corpus
   (testing all 3 flagship RFEs, pediatric vs adult, allergy split-chunks, urgence vs programmé,
   and longitudinal supersession traps).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class EvalQuestion(BaseModel):
    """Unified evaluation question schema for both retrieval and E2E generation benchmarks."""

    id: str
    title: str = ""
    category: str = "general"
    question_type: Literal["open", "mcq", "vignette", "temporal_diff"] = "open"
    question: str
    choices: dict[str, str] = Field(default_factory=dict)
    expected_answer: str = ""
    # Retrieval ground truth
    expected_topic_lineage: str | None = None
    expected_title_keywords: list[str] = Field(default_factory=list)
    expected_min_year: int | None = None
    required_evidence_terms: list[str] = Field(default_factory=list)
    is_allergy_question: bool = False
    is_pediatric_question: bool = False
    expects_multiple_editions: bool = False

    def formatted_query(self) -> str:
        """Return full prompt query including lettered choices for MCQ items."""
        if not self.choices:
            return self.question
        choices_lines = "\n".join(f"{k}. {v}" for k, v in self.choices.items())
        return f"{self.question}\n{choices_lines}"


def _extract_abp_evidence_terms(expected_answer: str, q_type: str, question: str) -> list[str]:
    """Derive ground-truth evidence tokens that MUST appear in retrieved passages to answer
    an Antibioprophylaxie question faithfully."""
    if q_type != "open":
        return []
    ans = expected_answer.strip().lower()
    if "pas d'antibioprophylaxie" in ans:
        return ["pas d'antibioprophylaxie"]
    if "hors périmètre" in ans:
        return []
    # Split drug combinations (`Clindamycine + Gentamicine`, `Amoxicilline/Clavulanate`)
    parts = [p.strip() for p in re.split(r"[+/]", expected_answer) if p.strip()]
    return [p for p in parts if len(p) >= 3]


def load_antibioprophylaxie_benchmark(benchmark_json_path: Path) -> list[EvalQuestion]:
    """Load all 171 questions from the official SFAR Antibioprophylaxie benchmark."""
    data = json.loads(benchmark_json_path.read_text(encoding="utf-8"))
    out: list[EvalQuestion] = []
    for item in data.get("questions", []):
        q_text = item["question"]
        q_type = item.get("type", "open")
        ans = item.get("réponse", "")
        title = item.get("titre", "")
        is_allergy = "allerg" in q_text.lower() or "allerg" in title.lower()
        is_ped = bool(re.search(r"\b(enfant|pédiatr|nourrisson|néonatal)\b", q_text, re.I))
        out.append(
            EvalQuestion(
                id=item["id"],
                title=title,
                category="antibioprophylaxie_allergy" if is_allergy else f"antibioprophylaxie_{q_type}",
                question_type="mcq" if q_type == "mcq" else "open",
                question=q_text,
                choices=item.get("choices") or {},
                expected_answer=ans,
                expected_topic_lineage="antibioprophylaxie",
                expected_title_keywords=["antibioprophylaxie"],
                expected_min_year=2023,
                required_evidence_terms=_extract_abp_evidence_terms(ans, q_type, q_text),
                is_allergy_question=is_allergy,
                is_pediatric_question=is_ped,
            )
        )
    return out


def load_multi_rfe_stress_benchmark() -> list[EvalQuestion]:
    """30-question Multi-RFE Clinical Stress Benchmark grounded directly in the 2024–2026 SFAR
    corpus, targeting every failure mode uncovered during our forensic corpus audit:
    - Flagship 1: Antibioprophylaxie V3.0 (2026) incl. allergies, obésité R1.5.2/R1.6, pédiatrie
    - Flagship 2: Infections Intra-Abdominales 2026 (vs obsolete 2015 trap)
    - Flagship 3: Anticoagulants procédure programmée 2026 (vs obsolete 2008/2015/2021 trap)
    - Scope separation: Anticoagulation Urgence 2024 vs Programmé 2026
    - Other major 2024–2026 RFEs: Voies aériennes 2026, Sepsis 2025, Hypersensibilité 2025,
      MTEV 2024, Nutrition 2026, ECBU 2026, ALR pédiatrique 2026, Sédation urgence 2026
    - Longitudinal diff queries requiring multi-edition retrieval
    """
    return [
        # --- FLAGSHIP 1: ANTIBIOPROPHYLAXIE 2026 (V3.0) ---
        EvalQuestion(
            id="M01",
            title="ABP délai administration R1.1",
            category="flagship_abp_2026",
            question="Quel est le délai recommandé (R1.1) pour administrer l'antibioprophylaxie par céphalosporine avant l'incision chirurgicale ?",
            expected_answer="Au plus tôt 60 minutes avant et au plus tard avant l'incision chirurgicale (R1.1, GRADE 1).",
            expected_topic_lineage="antibioprophylaxie",
            expected_title_keywords=["antibioprophylaxie"],
            expected_min_year=2026,
            required_evidence_terms=["60 minutes", "incision"],
        ),
        EvalQuestion(
            id="M02",
            title="ABP PTH voie antérieure allergie (split-chunk allergy box)",
            category="flagship_abp_allergy",
            question="Quelle antibioprophylaxie administrer pour une PTH par voie antérieure chez un patient allergique aux bêtalactamines ?",
            expected_answer="Préférer la vancomycine ou la teicoplanine à la clindamycine.",
            expected_topic_lineage="antibioprophylaxie",
            expected_title_keywords=["antibioprophylaxie"],
            expected_min_year=2026,
            required_evidence_terms=["vancomycine"],
            is_allergy_question=True,
        ),
        EvalQuestion(
            id="M03",
            title="ABP PTG allergie bêtalactamines (split-chunk allergy box)",
            category="flagship_abp_allergy",
            question="Quelle est l'alternative recommandée pour une PTG chez un patient allergique aux bêtalactamines ?",
            expected_answer="Clindamycine (encadré allergie orthopédie).",
            expected_topic_lineage="antibioprophylaxie",
            expected_title_keywords=["antibioprophylaxie"],
            expected_min_year=2026,
            required_evidence_terms=["clindamycine"],
            is_allergy_question=True,
        ),
        EvalQuestion(
            id="M04",
            title="ABP obèse R1.5.2 / R1.6 V3.0 (nouveauté 2026)",
            category="flagship_abp_2026",
            question="Comment adapter la dose d'antibioprophylaxie (amoxicilline-clavulanate et alternatives en cas d'allergie) chez le patient obèse selon la RFE SFAR ?",
            expected_answer="Adaptation selon R1.5.2 (amoxicilline-clavulanate) et R1.6 (clindamycine, vancomycine, gentamicine chez l'obèse).",
            expected_topic_lineage="antibioprophylaxie",
            expected_title_keywords=["antibioprophylaxie"],
            expected_min_year=2026,
            required_evidence_terms=["obese", "r1.6"],
            is_allergy_question=True,
        ),
        EvalQuestion(
            id="M05",
            title="ABP pédiatrie Champ 3 (nouveauté V3.0 2026)",
            category="flagship_abp_pediatrie",
            question="Quelle est l'antibioprophylaxie recommandée en chirurgie pédiatrique (Champ 3) pour une chirurgie orthopédique ou neurochirurgicale chez l'enfant ?",
            expected_answer="Champ 3 tableaux pédiatriques V3.0 (2026) — Céfazoline avec posologie pédiatrique en mg/kg.",
            expected_topic_lineage="antibioprophylaxie",
            expected_title_keywords=["antibioprophylaxie"],
            expected_min_year=2026,
            required_evidence_terms=["cefazoline", "mg/kg"],
            is_pediatric_question=True,
        ),
        EvalQuestion(
            id="M06",
            title="ABP fracture ouverte Gustilo 3 allergie pénicillines",
            category="flagship_abp_allergy",
            question="Quelle antibioprophylaxie prescrire pour une fracture ouverte Gustilo 3 chez un patient allergique aux pénicillines ?",
            expected_answer="Clindamycine + Gentamicine.",
            expected_topic_lineage="antibioprophylaxie",
            expected_title_keywords=["antibioprophylaxie"],
            expected_min_year=2026,
            required_evidence_terms=["clindamycine", "gentamicine"],
            is_allergy_question=True,
        ),
        EvalQuestion(
            id="M07",
            title="ABP chirurgie rhinologique avec greffon (rowspan table test)",
            category="flagship_abp_2026",
            question="Quelle antibioprophylaxie et quelle alternative pour une chirurgie rhinologique avec mise en place d'un greffon ou une chirurgie sinusienne tumorale ?",
            expected_answer="Céfazoline 2g IVL (GRADE 2), alternative Amoxicilline/Clavulanate 2g IVL.",
            expected_topic_lineage="antibioprophylaxie",
            expected_title_keywords=["antibioprophylaxie"],
            expected_min_year=2026,
            required_evidence_terms=["cefazoline", "amoxicilline"],
        ),
        # --- FLAGSHIP 2: INFECTIONS INTRA-ABDOMINALES 2026 (vs 2015 trap) ---
        EvalQuestion(
            id="M08",
            title="IIA communautaire sans sepsis antibiothérapie probabiliste (R1.2.1 2026)",
            category="flagship_iia_2026",
            question="Quelle antibiothérapie probabiliste est recommandée pour une infection intra-abdominale (IIA) communautaire sans sepsis ni choc septique chez l'adulte ?",
            expected_answer="Céphalosporine de 3e génération + métronidazole (imidazolé) ou alternative (R1.2.1, RFE 2026).",
            expected_topic_lineage="infections_intra_abdominales",
            expected_title_keywords=["intra-abdominales"],
            expected_min_year=2026,
            required_evidence_terms=["3", "metronidazole"],
        ),
        EvalQuestion(
            id="M09",
            title="IIA communautaire BLSE sans sepsis (R1.2.2 2026)",
            category="flagship_iia_2026",
            question="Faut-il couvrir les entérobactéries BLSE en probabiliste dans une infection intra-abdominale communautaire sans sepsis ni choc septique ?",
            expected_answer="Non, il n'est pas recommandé de prendre en compte les E-BLSE sans sepsis/choc septique (R1.2.2).",
            expected_topic_lineage="infections_intra_abdominales",
            expected_title_keywords=["intra-abdominales"],
            expected_min_year=2026,
            required_evidence_terms=["blse"],
        ),
        EvalQuestion(
            id="M10",
            title="IIA choc septique avec facteur de risque BLSE (R1.2.5 2026)",
            category="flagship_iia_2026",
            question="Quelle antibiothérapie probabiliste initier devant une IIA communautaire en choc septique avec facteur de risque de portage BLSE ?",
            expected_answer="Carbapénème selon R1.2.5 (RFE 2026).",
            expected_topic_lineage="infections_intra_abdominales",
            expected_title_keywords=["intra-abdominales"],
            expected_min_year=2026,
            required_evidence_terms=["blse", "choc septique"],
        ),
        EvalQuestion(
            id="M11",
            title="IIA instabilité hémodynamique Damage Control (R1.1.2 2026)",
            category="flagship_iia_2026",
            question="Quelle stratégie chirurgicale est suggérée en cas d'infection intra-abdominale avec instabilité hémodynamique non contrôlée en peropératoire ?",
            expected_answer="Chirurgie de type Damage Control ou laparotomie écourtée (R1.1.2).",
            expected_topic_lineage="infections_intra_abdominales",
            expected_title_keywords=["intra-abdominales"],
            expected_min_year=2026,
            required_evidence_terms=["damage control"],
        ),
        EvalQuestion(
            id="M12",
            title="IIA diverticulite Hinchey III sans sepsis (R1.1.5 2026)",
            category="flagship_iia_2026",
            question="Quelle est la recommandation SFAR pour une diverticulite sigmoïdienne perforée purulente (Hinchey III) sans sepsis ?",
            expected_answer="Recommandation R1.1.5 (RFE IIA 2026).",
            expected_topic_lineage="infections_intra_abdominales",
            expected_title_keywords=["intra-abdominales"],
            expected_min_year=2026,
            required_evidence_terms=["hinchey"],
        ),
        EvalQuestion(
            id="M13",
            title="IIA traitement antifongique probabiliste (2026)",
            category="flagship_iia_2026",
            question="Quelles sont les indications du traitement antifongique probabiliste au cours des infections intra-abdominales de l'adulte ?",
            expected_answer="Section traitement probabiliste antifongique (RFE IIA 2026).",
            expected_topic_lineage="infections_intra_abdominales",
            expected_title_keywords=["intra-abdominales"],
            expected_min_year=2026,
            required_evidence_terms=["antifongique"],
        ),
        # --- FLAGSHIP 3: ANTICOAGULANTS PROCÉDURE INVASIVE PROGRAMMÉE 2026 (vs 2008/2015/2021 trap) ---
        EvalQuestion(
            id="M14",
            title="AVK arrêt avant procédure risque hémorragique élevé (3.1 2026)",
            category="flagship_anticoag_2026",
            question="Quand arrêter les AVK (warfarine, fluindione, acénocoumarol) avant une procédure invasive programmée à risque hémorragique élevé ?",
            expected_answer="Dernière prise à J-6 pour la warfarine, J-5 pour la fluindione, J-4 pour l'acénocoumarol, contrôle INR la veille (3.1, GRADE 2+).",
            expected_topic_lineage="anticoagulants_procedure_programmee",
            expected_title_keywords=["anticoagulants"],
            expected_min_year=2026,
            required_evidence_terms=["warfarine", "j-6", "inr"],
        ),
        EvalQuestion(
            id="M15",
            title="AVK INR au-dessus du seuil et vitamine K (3.2 2026)",
            category="flagship_anticoag_2026",
            question="Quelle conduite tenir si l'INR la veille d'une procédure programmée reste supérieur au seuil de sécurité hémostatique sous AVK ?",
            expected_answer="Seuil INR=1,5 (ou 1,2 en neurochirurgie/neuraxial), administrer 2 à 5 mg de vitamine K per os la veille et contrôler l'INR le lendemain (3.2).",
            expected_topic_lineage="anticoagulants_procedure_programmee",
            expected_title_keywords=["anticoagulants"],
            expected_min_year=2026,
            required_evidence_terms=["vitamine k", "1,5"],
        ),
        EvalQuestion(
            id="M16",
            title="AOD arrêt avant procédure risque hémorragique élevé (3.3 2026)",
            category="flagship_anticoag_2026",
            question="Quel est le délai d'arrêt des AOD (apixaban, rivaroxaban, dabigatran, edoxaban) avant une procédure invasive programmée à risque hémorragique élevé sans insuffisance rénale ?",
            expected_answer="Dernière prise à J-3 en l'absence d'insuffisance rénale (3.3, GRADE 2+).",
            expected_topic_lineage="anticoagulants_procedure_programmee",
            expected_title_keywords=["anticoagulants"],
            expected_min_year=2026,
            required_evidence_terms=["j-3", "apixaban"],
        ),
        EvalQuestion(
            id="M17",
            title="AOD neurochirurgie intracrânienne ou procédure neuraxiale (3.4 2026)",
            category="flagship_anticoag_2026",
            question="Quel est le délai d'arrêt d'un AOD avant une neurochirurgie intracrânienne ou une procédure neuraxiale programmée (risque très élevé) ?",
            expected_answer="Dernière prise à J-5 (3.4, Avis d'experts, Accord fort).",
            expected_topic_lineage="anticoagulants_procedure_programmee",
            expected_title_keywords=["anticoagulants"],
            expected_min_year=2026,
            required_evidence_terms=["j-5", "neuraxial"],
        ),
        EvalQuestion(
            id="M18",
            title="AVK/AOD procédure programmée FA et coronaropathie",
            category="flagship_anticoag_2026",
            question="Comment gérer un patient traité par anticoagulant oral pour fibrillation atriale associée à une coronaropathie avant une procédure invasive programmée ?",
            expected_answer="Section FA associée à une coronaropathie (RFE Anticoagulants 2026).",
            expected_topic_lineage="anticoagulants_procedure_programmee",
            expected_title_keywords=["anticoagulants"],
            expected_min_year=2026,
            required_evidence_terms=["fibrillation atriale", "coronaropathie"],
        ),
        # --- SCOPE SEPARATION: ANTICOAGULATION URGENCE 2024 vs PROGRAMMÉ 2026 ---
        EvalQuestion(
            id="M19",
            title="Anticoagulation urgence hémorragie intracrânienne réversion (R2.1.2 2024)",
            category="scope_separation_urgence",
            question="Chez un patient sous anticoagulant présentant une hémorragie intracrânienne ou un choc hémorragique en urgence, faut-il attendre le résultat des tests biologiques pour réverser ?",
            expected_answer="Non, il est recommandé de réverser sans attendre le résultat des examens biologiques (R2.1.2, RFE Urgence 2024).",
            expected_topic_lineage="anticoagulants_urgence",
            expected_title_keywords=["urgence", "anticoagulation"],
            expected_min_year=2024,
            required_evidence_terms=["reverser", "intracranienne"],
        ),
        EvalQuestion(
            id="M20",
            title="Anticoagulation urgence acide tranexamique (R2.2.1 2024)",
            category="scope_separation_urgence",
            question="Quelle est la place de l'acide tranexamique chez un patient sous anticoagulant présentant une hémorragie en urgence ?",
            expected_answer="Il est recommandé d'administrer de l'acide tranexamique selon les mêmes indications qu'un patient non anticoagulé (R2.2.1, RFE Urgence 2024).",
            expected_topic_lineage="anticoagulants_urgence",
            expected_title_keywords=["urgence", "anticoagulation"],
            expected_min_year=2024,
            required_evidence_terms=["tranexamique"],
        ),
        # --- OTHER MAJOR 2024-2026 SFAR RFEs (FULL CORPUS BREADTH + SUPERSESSION TRAPS) ---
        EvalQuestion(
            id="M21",
            title="Voies aériennes adulte au bloc 2026 (vs 2003/2017 trap)",
            category="supersession_2026",
            question="Quelles sont les recommandations actuelles pour la prise en charge des voies aériennes de l'adulte au bloc opératoire et l'intubation difficile ?",
            expected_answer="RFE Voies aériennes adulte au bloc opératoire 2026.",
            expected_topic_lineage="voies_aeriennes_adulte_bloc",
            expected_title_keywords=["voies aériennes"],
            expected_min_year=2026,
            required_evidence_terms=["intubation"],
        ),
        EvalQuestion(
            id="M22",
            title="Hypersensibilité immédiate périopératoire 2025 (vs 2011 trap)",
            category="supersession_2025",
            question="Quelle est la prise en charge d'une réaction d'hypersensibilité immédiate (anaphylaxie) périopératoire et le bilan biologique à réaliser ?",
            expected_answer="RFE SFAR-SFA 2025 Hypersensibilité immédiate (adrénaline, tryptase).",
            expected_topic_lineage="hypersensibilite_allergie_perioperatoire",
            expected_title_keywords=["hypersensibilité"],
            expected_min_year=2025,
            required_evidence_terms=["tryptase"],
        ),
        EvalQuestion(
            id="M23",
            title="Sepsis HAS 2025 (vs 2004/2005/2006 trap)",
            category="supersession_2025",
            question="Quelles sont les recommandations actuelles pour la prise en charge initiale du sepsis chez l'adulte et l'enfant ?",
            expected_answer="Recommandations HAS 2025 Sepsis.",
            expected_topic_lineage="sepsis_general",
            expected_title_keywords=["sepsis"],
            expected_min_year=2025,
            required_evidence_terms=["sepsis"],
        ),
        EvalQuestion(
            id="M24",
            title="Prévention MTEV péri-opératoire 2024 (vs 2011 trap)",
            category="supersession_2024",
            question="Quelles sont les recommandations actuelles pour la prévention de la maladie thromboembolique veineuse (MTEV) péri-opératoire ?",
            expected_answer="RFE Prévention MTEV péri-opératoire 2024.",
            expected_topic_lineage="prevention_mtev_perioperatoire",
            expected_title_keywords=["thromboembolique"],
            expected_min_year=2024,
            required_evidence_terms=["thromboembolique"],
        ),
        EvalQuestion(
            id="M25",
            title="Nutrition clinique périopératoire 2026 (vs 2010/2014 trap)",
            category="supersession_2026",
            question="Quelles sont les recommandations SFAR sur la nutrition clinique de l'adulte en contexte périopératoire et en soins critiques ?",
            expected_answer="RFE Nutrition clinique 2026.",
            expected_topic_lineage="nutrition_clinique_adulte",
            expected_title_keywords=["nutrition"],
            expected_min_year=2026,
            required_evidence_terms=["nutrition"],
        ),
        EvalQuestion(
            id="M26",
            title="Place de l'ECBU avant chirurgie urologique 2026",
            category="recent_2026",
            question="Quelle est la place de l'ECBU avant une prise en charge urologique chirurgicale ou interventionnelle chez l'adulte et comment traiter une colonisation ?",
            expected_answer="RPP ECBU urologie 2026.",
            expected_topic_lineage=None,
            expected_title_keywords=["ecbu"],
            expected_min_year=2026,
            required_evidence_terms=["ecbu", "colonisation"],
        ),
        EvalQuestion(
            id="M27",
            title="ALR en chirurgie pédiatrique 2026 (vs 2010 trap)",
            category="supersession_2026",
            question="Quelles sont les recommandations SFAR pour l'anesthésie locorégionale (ALR) en chirurgie pédiatrique chez l'enfant ?",
            expected_answer="RFE ALR en chirurgie pédiatrique 2026.",
            expected_topic_lineage="alr_pediatrique",
            expected_title_keywords=["locorégionale", "pédiatrique"],
            expected_min_year=2026,
            required_evidence_terms=["locoregionale"],
            is_pediatric_question=True,
        ),
        EvalQuestion(
            id="M28",
            title="Sédation procédurale médecine d'urgence 2026 (vs 2010 trap)",
            category="supersession_2026",
            question="Quelles sont les recommandations pour la sédation procédurale en structure de médecine d'urgence ?",
            expected_answer="RFE Sédation procédurale en structure de Médecine d'Urgence 2026.",
            expected_topic_lineage="sedation_urgences",
            expected_title_keywords=["sédation", "urgence"],
            expected_min_year=2026,
            required_evidence_terms=["sedation"],
        ),
        # --- TEMPORAL DIFF QUERIES (multi-edition router test!) ---
        EvalQuestion(
            id="M29",
            title="Comparaison longitudinale Antibioprophylaxie 2018 vs 2026",
            category="temporal_diff",
            question_type="temporal_diff",
            question="Qu'est-ce qui a changé dans les recommandations d'antibioprophylaxie entre la version 2018 et la version 2026 (V3.0) ?",
            expected_answer="Ajout de la pédiatrie (Champ 3), nouvelles doses obèse (R1.5.2/R1.6), mises à jour allergies.",
            expected_topic_lineage="antibioprophylaxie",
            expected_title_keywords=["antibioprophylaxie"],
            expected_min_year=2018,
            required_evidence_terms=["antibioprophylaxie"],
            expects_multiple_editions=True,
        ),
        EvalQuestion(
            id="M30",
            title="Comparaison longitudinale IIA 2015 vs 2026",
            category="temporal_diff",
            question_type="temporal_diff",
            question="Comparer les recommandations de prise en charge des infections intra-abdominales entre 2015 et 2026.",
            expected_answer="Évolution entre RFE 2015 et RFE 2026.",
            expected_topic_lineage="infections_intra_abdominales",
            expected_title_keywords=["intra-abdominales"],
            expected_min_year=2015,
            required_evidence_terms=["intra-abdominale"],
            expects_multiple_editions=True,
        ),
    ]
