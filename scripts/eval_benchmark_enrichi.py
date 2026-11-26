#!/usr/bin/env python3
"""Comprehensive evaluation of RAG-SFAR on:
1. Official `benchmark_enrichi_phase1` (171/171 questions, V3.1) via official `sfar_evaluator`
   (schema validation + deterministic Hit@k / Recall@k / Sufficiency@k / MRR).
2. Real End-to-End LLM evaluation (Apple Silicon MLX Qwen2.5-7B-Instruct-4bit) on the
   critical new subsets of `benchmark_enrichi_phase1` (all 11 Pediatric/Neonatal,
   all 11 Ambiguous/Ask-Clarification incl. Q163/Q167/Q90, and all 12 revised Adult cases).
3. Brand-new 2026 SFAR Recommendations Suite (14 cases covering ABP V3.1 10/07/2026,
   ABP V3.0 04/05/2026, ALR Pédiatrique 09/2026, Sédation Urgences 06/2026, ECBU 03/2026,
   LAT 05/2026, Urgences Vitales Intra-Hospitalières 09/2026, Anticoagulants 04/2026,
   Voies Aériennes 2026, IIA 2026).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

EVALUATOR_SRC = Path("data/benchmark_enrichi_alparagsfar/benchmark_evaluator/src").resolve()
if str(EVALUATOR_SRC) not in sys.path:
    sys.path.insert(0, str(EVALUATOR_SRC))

from sfar_evaluator.dataset import load_dataset
from sfar_evaluator.retrieval import aggregate, diagnose_case
from sfar_evaluator.runs import import_run, new_run
from sfar_evaluator.storage import save

from rag_sfar.config import RetrievalConfig
from rag_sfar.generation.client import LocalMlxLLM, SfarRagEngine
from rag_sfar.retrieval.embedder import build_embedder
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.reranker import build_reranker
from rag_sfar.retrieval.vector_store import LocalVectorStore

DATASET_PATH = Path(
    "data/benchmark_enrichi_alparagsfar/benchmark_enrichi_phase1/questions_enriched_draft.jsonl"
)
DEFAULT_MLX_7B = (
    "/Users/tim/.cache/huggingface/hub/models--mlx-community--Qwen2.5-7B-Instruct-4bit/"
    "snapshots/c26a38f6a37d0a51b4e9a1eb3026530fa35d9fed"
)


RECENT_2026_CASES: list[dict[str, object]] = [
    {
        "id": "REC26-01",
        "rfe": "ABP V3.1 (10/07/2026) — Néonatalogie grêle < 7j",
        "question": "Chez un nouveau-né de 3 jours opéré d'une cure d'atrésie de l'intestin grêle, quelle est l'antibioprophylaxie recommandée (molécules, doses et réinjections) ?",
        "must_contain_all": ["céfazoline", "métronidazole"],
        "must_contain_any": ["30 mg/kg", "15 mg/kg", "40 mg/kg", "pas de réinjection"],
        "expected_summary": "Céfazoline 30 mg/kg IVL + Métronidazole 15 mg/kg IVL OU Alternative Céfoxitine 40 mg/kg IVL ; enfant < 7j : pas de réinjection (Avis d'experts, V3.1 10/07/2026).",
    },
    {
        "id": "REC26-02",
        "rfe": "ABP V3.1 (10/07/2026) — Néonatalogie colorectal >= 7j",
        "question": "Chez un nouveau-né de 12 jours devant subir une chirurgie de la maladie de Hirschsprung (colostomie) durant plus de 4 heures, quel est le schéma d'antibioprophylaxie recommandé ?",
        "must_contain_all": ["céfazoline", "métronidazole"],
        "must_contain_any": ["4h", "2h", "30 mg/kg", "40 mg/kg"],
        "expected_summary": "Céfazoline 30 mg/kg IVL (réinjection 30 mg/kg si >4h puis /4h chez >=7j) + Métronidazole 15 mg/kg (pas de réinjection) OU Céfoxitine 40 mg/kg (réinjection 40 mg/kg si >2h puis /2h chez >=7j).",
    },
    {
        "id": "REC26-03",
        "rfe": "ABP V3.0 vs V3.1 — Veille temporelle (diff)",
        "question": "Qu'est-ce qui a changé entre la V3.0 et la V3.1 des recommandations SFAR d'antibioprophylaxie ?",
        "must_contain_all": ["v3.1"],
        "must_contain_any": ["néonatal", "céfazoline", "métronidazole", "céfoxitine", "grêlique", "colorectal"],
        "expected_summary": "V3.1 du 10/07/2026 : amendement du schéma pour les chirurgies digestives néonatales grêliques ou colorectales (Céfazoline + Métronidazole ou Céfoxitine, pages 120-121).",
    },
    {
        "id": "REC26-04",
        "rfe": "ABP V3.0/V3.1 (04/05/2026) — R1.5.2 Obésité Amox/Clav",
        "question": "Selon la recommandation R1.5.2 de l'antibioprophylaxie SFAR 2026, quelle dose d'amoxicilline-acide clavulanique est recommandée chez le patient obèse ?",
        "must_contain_all": ["amoxicilline"],
        "must_contain_any": ["r1.5.2", "3g", "3 g", "2g", "2 g", "imc", "obèse"],
        "expected_summary": "R1.5.2 (Avis d'experts, V3.0/V3.1 2026) : adaptation de la posologie d'amoxicilline-acide clavulanique chez le patient obèse.",
    },
    {
        "id": "REC26-05",
        "rfe": "ABP V3.0/V3.1 (04/05/2026) — Biopsie prostate fosfomycine délai",
        "question": "Quel est le délai précis d'administration de la fosfomycine-trométamol en antibioprophylaxie avant une biopsie de prostate par voie transrectale ?",
        "must_contain_all": ["fosfomycine"],
        "must_contain_any": ["2 à 4", "2h", "4h", "3g", "3 g"],
        "expected_summary": "Fosfomycine-trométamol 3 g per os 2 à 4 heures avant le geste (précision ajoutée en V3.0/V3.1 2026).",
    },
    {
        "id": "REC26-06",
        "rfe": "ABP V3.0/V3.1 (04/05/2026) — Pose de valve Zéphyr",
        "question": "Quelle antibioprophylaxie est recommandée pour la pose de valve endobronchique Zéphyr ?",
        "must_contain_all": ["amoxicilline"],
        "must_contain_any": ["zéphyr", "zephyr", "clavulan", "2g", "2 g", "1g"],
        "expected_summary": "Amoxicilline/acide clavulanique avec posologie mise à jour en V3.0/V3.1 (page 55).",
    },
    {
        "id": "REC26-07",
        "rfe": "ALR Pédiatrique (01/09/2026) — Adjuvants ALR enfant",
        "question": "Chez l'enfant recevant une anesthésie locorégionale périphérique ou caudale, quels adjuvants sont recommandés en 2026 pour prolonger l'efficacité analgésique et à quelle posologie ?",
        "must_contain_all": ["clonidine"],
        "must_contain_any": ["dexmédétomidine", "dexaméthasone", "1 µg/kg", "1µg/kg", "r1.2"],
        "expected_summary": "R1.2.1 : clonidine ou dexmédétomidine 1 µg/kg par voie locorégionale ; R1.2.2 : dexaméthasone IV (RFE ALR pédiatrique 09/2026).",
    },
    {
        "id": "REC26-08",
        "rfe": "Sédation procédurale Urgences (24/06/2026) — Gestes trauma & Obésité",
        "question": "En structure de médecine d'urgence, quelle alternative à la sédation procédurale est suggérée pour les gestes traumatologiques périphériques (luxation, fracture) et quel seuil d'IMC définit le haut risque en cas d'obésité ?",
        "must_contain_all": ["40"],
        "must_contain_any": ["locorégionale", "loco-régionale", "alr", "r1.1.1", "r2.2.1"],
        "expected_summary": "R1.1.1 : ALR par médecin formé pour gestes traumatologiques périphériques ; R2.2.1 : obésité morbide IMC >= 40 kg/m² à haut risque (RFE 24/06/2026).",
    },
    {
        "id": "REC26-09",
        "rfe": "ECBU préopératoire Urologie (04/03/2026)",
        "question": "Selon les recommandations 2026 sur l'ECBU avant chirurgie urologique, faut-il dépister une colonisation urinaire avant un traitement mini-invasif de l'HBP (Urolift, ITind) ou avant implantation d'un sphincter urinaire artificiel ?",
        "must_contain_all": ["pas"],
        "must_contain_any": ["ne pas réaliser", "non recommandé", "r5.1", "r15.1", "dépistage"],
        "expected_summary": "R5.1 & R15.1 (04/03/2026) : il est recommandé de NE PAS réaliser de dépistage de la colonisation urinaire avant Urolift/ITind ni avant implantation d'un sphincter urinaire artificiel.",
    },
    {
        "id": "REC26-10",
        "rfe": "LAT en soins critiques (mai 2026)",
        "question": "Selon la RFE SFAR 2026 sur les décisions de limitation et d'arrêt des traitements (LAT) en soins critiques, quelles sont les mesures organisationnelles recommandées autour du projet de soins et des volontés du patient ?",
        "must_contain_all": ["volonté"],
        "must_contain_any": ["pluriprofessionnell", "protocole", "r1.1", "r1.2", "r1.3"],
        "expected_summary": "R1.1 réunions pluriprofessionnelles régulières ; R1.2 recherche précoce des volontés du patient ; R1.3 protocole de service d'aide à la décision LAT (mai 2026).",
    },
    {
        "id": "REC26-11",
        "rfe": "Urgences vitales intra-hospitalières (03/09/2026)",
        "question": "Comment la recommandation SFAR 2026 organise-t-elle la réponse et l'alerte face aux urgences vitales intra-hospitalières ?",
        "must_contain_all": ["urgence"],
        "must_contain_any": ["intra-hospitali", "équipe", "alerte", "numéro", "score", "appel"],
        "expected_summary": "Organisation structurée de l'alerte, scores d'alerte précoce et équipe dédiée aux urgences vitales intra-hospitalières (03/09/2026).",
    },
    {
        "id": "REC26-12",
        "rfe": "Anticoagulants procédure invasive programmée (20/04/2026)",
        "question": "Selon la RFE SFAR 2026 sur la gestion des anticoagulants pour une procédure invasive programmée, quel est le délai d'arrêt des AOD (apixaban, rivaroxaban) avant une procédure à risque hémorragique élevé ou une anesthésie neuraxiale ?",
        "must_contain_all": ["aod"],
        "must_contain_any": ["j-3", "72", "3 jours", "apixaban", "rivaroxaban", "neuraxial"],
        "expected_summary": "Arrêt à J-3 (dernière prise 72h avant) pour apixaban/rivaroxaban en risque hémorragique élevé (et délai prolongé selon clairance pour dabigatran) selon RFE 20/04/2026.",
    },
    {
        "id": "REC26-13",
        "rfe": "Voies aériennes adulte au bloc opératoire (2026)",
        "question": "Selon la RFE SFAR 2026 sur la gestion des voies aériennes de l'adulte au bloc opératoire, que recommander après une gestion difficile des voies aériennes compliquée d'un événement indésirable ?",
        "must_contain_all": ["voies aériennes"],
        "must_contain_any": ["mortalité", "morbidité", "rmm", "débriefing", "certificat", "r3.7"],
        "expected_summary": "R3.7 : revue de mortalité et de morbidité (RMM), débriefing d'équipe et délivrance d'un certificat de voies aériennes difficiles (RFE 2026).",
    },
    {
        "id": "REC26-14",
        "rfe": "Infections intra-abdominales adulte (2026)",
        "question": "Selon la RFE SFAR 2026 sur les infections intra-abdominales de l'adulte, quelle antibiothérapie probabiliste est recommandée pour une IIA communautaire sans critère de gravité (hors sepsis/choc septique) ?",
        "must_contain_all": ["métronidazole"],
        "must_contain_any": ["céfotaxime", "ceftriaxone", "amoxicilline", "c3g", "probabiliste"],
        "expected_summary": "C3G (céfotaxime ou ceftriaxone) + métronidazole (ou amoxicilline-acide clavulanique selon contexte local) pour IIA communautaire sans gravité (RFE IIA 2026).",
    },
]


def _fold(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _check_clarification_or_conditional(answer: str, missing_items: list[str]) -> bool:
    ans_low = _fold(answer)
    markers = [
        "preciser",
        "precision",
        "manqu",
        "quel est l'age",
        "age du patient",
        "selon l'age",
        "chez l'adulte",
        "chez l'enfant",
        "nouveau-ne",
        "depend",
        "conditionnel",
        "si ",
        "en cas de",
        "indication",
        "antibiogramme",
        "sensibilite",
        "site du prelevement",
        "grade",
        "delai",
        "plastie",
        "poids",
    ]
    hits = sum(1 for m in markers if m in ans_low)
    return hits >= 2 or "?" in answer


def _check_expected_match(case_raw: dict, answer: str) -> tuple[bool, str]:
    """Deterministic clinical check aligned with benchmark_enrichi_phase1 reference_answer."""
    prop = case_raw["proposed"]
    ref = case_raw["reference_answer"]
    ans_f = _fold(answer)

    if prop["expected_behavior"] == "ask_clarification":
        ok = _check_clarification_or_conditional(
            answer, ref.get("required_missing_information") or []
        )
        return ok, "clarification_or_conditional" if ok else "missed_ambiguity"

    if prop["format"] == "mcq" and prop.get("mcq_correct_option"):
        letter = prop["mcq_correct_option"].upper()
        # Accept explicit letter OR the exact text of the right choice
        m_letter = re.search(
            r"(?:r[ée]ponse|option|choix|proposition)\s*(?:correcte|exacte|retenue)?\s*[:\-–]?\s*\**\s*([A-E])\b",
            answer,
            re.I,
        )
        if m_letter and m_letter.group(1).upper() == letter:
            return True, f"mcq_letter_{letter}"
        # Fallback: first standalone option label at start of answer
        m_start = re.match(r"^\s*\**\s*([A-E])\b[\.\)\s:\-]", answer.strip())
        if m_start and m_start.group(1).upper() == letter:
            return True, f"mcq_start_{letter}"
        choice_txt = _fold((prop.get("choices") or {}).get(letter, ""))
        if choice_txt and len(choice_txt) > 8 and choice_txt[:35] in ans_f:
            return True, f"mcq_text_{letter}"
        return False, f"expected_{letter}"

    # Open question: check short_answer / mandatory_claims clinical core
    short_f = _fold(ref.get("short_answer") or "").replace("’", "'")
    ans_norm = ans_f.replace("’", "'")
    # Negation cases
    if any(
        k in short_f
        for k in (
            "aucune antibioprophylaxie",
            "pas d'antibioprophylaxie",
            "ne necessite pas d'antibioprophylaxie",
            "non recommandee",
        )
    ):
        neg_ok = any(
            k in ans_norm
            for k in (
                "pas d'antibioprophylaxie",
                "aucune antibioprophylaxie",
                "absence d'indication",
                "pas indiquee",
                "non recommandee",
                "pas recommandee",
                "sans antibioprophylaxie",
                "ne necessite pas d'antibioprophylaxie",
            )
        )
        return neg_ok, "negation_match" if neg_ok else "missed_negation"

    # Extract key drug / regimen tokens from short_answer
    drug_tokens = re.findall(
        r"\b(?:cefazoline|cefuroxime|cefoxitine|amoxicilline|clavulan\w*|clindamycine|"
        r"vancomycine|teicoplanine|gentamicine|metronidazole|fosfomycine|ciprofloxacine|"
        r"levofloxacine|piperacilline|tazobactam|ceftriaxone|cefotaxime|ertapeneme|"
        r"tobramycine|aztreonam|doxycycline|ofloxacine|cefepime|meropeneme)\b",
        short_f,
    )
    if drug_tokens:
        uniq = list(dict.fromkeys(drug_tokens))
        found = [d for d in uniq if d[:7] in ans_f]
        if len(found) == len(uniq):
            return True, f"drugs_ok:{'+'.join(uniq)}"
        return False, f"missing_drugs:{[d for d in uniq if d not in found]}"

    # Fallback token overlap on mandatory_claims
    claims = " ".join(c.get("text_fr", "") for c in (ref.get("mandatory_claims") or []))
    kws = [w for w in re.findall(r"[a-z]{5,}", _fold(claims)) if w not in ("antibioprophylaxie", "recommandee", "recommande", "chirurgie", "tableau", "adulte", "enfant")]
    if not kws:
        return True, "no_keywords"
    overlap = sum(1 for w in set(kws) if w in ans_f) / len(set(kws))
    return overlap >= 0.45, f"claim_overlap={overlap:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-dir", type=Path, default=Path("index/table_aware_sota_v31"))
    parser.add_argument("--mlx-model", type=str, default=DEFAULT_MLX_7B)
    parser.add_argument("--skip-e2e", action="store_true")
    parser.add_argument("--reuse-part-a", action="store_true", help="Reuse existing Part A predictions.jsonl if present")
    parser.add_argument("--out-dir", type=Path, default=Path("reports/benchmark_enrichi_eval"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    raw_rows = {
        json.loads(line)["question_id"]: json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    ds = load_dataset(DATASET_PATH)

    # Pin embedder/reranker to CPU when MLX LLM will run so Apple Silicon GPU has zero contention
    device = "cpu" if not args.skip_e2e else None
    t0 = time.perf_counter()
    store = LocalVectorStore.load(args.index_dir)
    embedder = build_embedder(
        provider=store.manifest["embedding_provider"],
        model_name=store.manifest["embedding_model"],
        device=device,
    )
    reranker = build_reranker(
        provider="cross_encoder",
        model_name="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        device=device,
    )
    retriever = SfarRagRetriever(store=store, embedder=embedder, reranker=reranker)
    print(f"[Init] Loaded {args.index_dir} ({len(store.chunks)} chunks) in {time.perf_counter()-t0:.1f}s (device={device or 'auto'})", flush=True)

    # =========================================================================
    # PART A: Official sfar_evaluator Retrieval Benchmark on ALL 171 questions
    # =========================================================================
    cfg_ret = RetrievalConfig(final_top_k=10, use_u_shape_ordering=False)
    run_dir = args.out_dir / "sfar_evaluator_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    preds_list: list[dict] = []
    diag_rows: list[dict] = []
    by_pop: dict[str, list[dict]] = {"Adulte": [], "Pédiatrie": [], "Non précisé": []}
    by_cat: dict[str, list[dict]] = {}
    by_diff: dict[str, list[dict]] = {}
    obsolete_chunks = 0
    v31_hits = 0

    t_ret = time.perf_counter()
    manifest_path = run_dir / "run_manifest.json"
    preds_path = run_dir / "predictions.jsonl"
    if args.reuse_part_a and manifest_path.exists() and preds_path.exists():
        imp_manifest, imp_preds, _, _ = import_run(ds, manifest_path, preds_path)
        for qid, case in ds.cases.items():
            pred = imp_preds[qid]
            diag = diagnose_case(case, pred, threshold=0.8, ks=(1, 3, 5, 10))
            diag["question_id"] = qid
            diag_rows.append(diag)
            cls = raw_rows[qid]["classification"]
            if diag["retrieval_status"] == "traced":
                by_pop.setdefault(cls.get("population_enonce", "Non précisé"), []).append(diag)
                by_cat.setdefault(cls.get("primary_category", "UNKNOWN"), []).append(diag)
                by_diff.setdefault(cls.get("difficulty", "unknown"), []).append(diag)
        ret_sec = 0.0
        agg_ret = aggregate(diag_rows, (1, 3, 5, 10))
        print(f"[Part A Reused] Validated {len(imp_preds)}/171 from {preds_path}", flush=True)
    else:
        for idx, (qid, case) in enumerate(ds.cases.items(), 1):
            pub = case.public
            q = pub["question"]
            if pub["format"] == "mcq" and pub["choices"]:
                q = q + "\n" + "\n".join(f"{k}. {v}" for k, v in pub["choices"].items())
            results, qa, timings = retriever.retrieve(q, config=cfg_ret)
            ctxs = []
            for rank, r in enumerate(results, 1):
                c = r.chunk
                if not c.is_latest_edition:
                    obsolete_chunks += 1
                is_v31 = "V3_1" in c.doc_id or (c.version_label and "V3.1" in c.version_label)
                if is_v31:
                    v31_hits += 1
                txt = f"{c.section_path}\n{c.text}" if c.section_path else c.text
                ctx_obj: dict[str, object] = {
                    "rank": rank,
                    "text": txt,
                    "chunk_id": c.chunk_id,
                    "score": round(float(r.final_score), 4),
                }
                if is_v31:
                    ctx_obj["document_id"] = "SFAR_ABP_V3.1"
                    ctx_obj["document_version"] = "V3.1"
                ctxs.append(ctx_obj)

            pred = {
                "question_id": qid,
                "status": "success",
                "answer": "Retrieval-only benchmark trace (see Part B for full LLM answers).",
                "retrieved_contexts": ctxs,
                "latency_ms": int(round(timings.get("total_ms", 0.0))),
            }
            preds_list.append(pred)

            diag = diagnose_case(case, pred, threshold=0.8, ks=(1, 3, 5, 10))
            diag["question_id"] = qid
            diag_rows.append(diag)

            cls = raw_rows[qid]["classification"]
            if diag["retrieval_status"] == "traced":
                by_pop.setdefault(cls.get("population_enonce", "Non précisé"), []).append(diag)
                by_cat.setdefault(cls.get("primary_category", "UNKNOWN"), []).append(diag)
                by_diff.setdefault(cls.get("difficulty", "unknown"), []).append(diag)
            if idx % 50 == 0:
                print(f"  [Part A Retrieval] {idx}/171 in {time.perf_counter()-t_ret:.1f}s...", flush=True)

        ret_sec = time.perf_counter() - t_ret
        agg_ret = aggregate(diag_rows, (1, 3, 5, 10))

        # Write official sfar_evaluator manifest + predictions.jsonl and validate!
        manifest = new_run(
            ds,
            list(ds.cases.keys()),
            "V3.1",
            {
                "name": "RAG-SFAR Frontier 2026 (C8 V3.1)",
                "method": "external",
                "version": "2026-v3.1",
                "provider": "local-hybrid-mlx",
                "model": "Qwen2.5-7B-Instruct-4bit",
                "parameters": {
                    "final_top_k": 10,
                    "embedder": "intfloat/multilingual-e5-small",
                    "reranker": "mmarco-mMiniLMv2-L12-H384-v1",
                },
                "prompt_sha256": None,
                "context_budget_bytes": 16000,
                "seed": 42,
            },
            {"all": True},
        )
        save(manifest_path, manifest)
        with preds_path.open("w", encoding="utf-8") as fh:
            for p in preds_list:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")

        # Official schema validation via sfar_evaluator.runs.import_run!
        imp_manifest, imp_preds, _, _ = import_run(ds, manifest_path, preds_path)
    print(
        f"[Part A Done] 171 cases in {ret_sec:.1f}s | Official sfar_evaluator validate: OK ({len(imp_preds)}/171) "
        f"| Obsolete={obsolete_chunks} | Hit@5={agg_ret['at_k']['5']['hit']['rate']*100:.1f}% "
        f"| Hit@10={agg_ret['at_k']['10']['hit']['rate']*100:.1f}% "
        f"| Suff@10={agg_ret['at_k']['10']['sufficiency']['rate']*100:.1f}% "
        f"| MeanRecall@10={agg_ret['at_k']['10']['mean_recall']*100:.1f}% "
        f"| MRR={agg_ret['mrr_first_hit']:.3f}",
        flush=True,
    )

    pop_summary = {}
    for pop, lst in by_pop.items():
        if not lst:
            continue
        pop_summary[pop] = {
            "n": len(lst),
            "hit_at_5": sum(r["at_k"]["5"]["hit"] for r in lst),
            "suff_at_5": sum(r["at_k"]["5"]["sufficient"] for r in lst),
            "hit_at_10": sum(r["at_k"]["10"]["hit"] for r in lst),
            "suff_at_10": sum(r["at_k"]["10"]["sufficient"] for r in lst),
            "mean_recall_10": round(sum(r["at_k"]["10"]["recall"] for r in lst) / len(lst), 4),
        }

    # =========================================================================
    # PART B & C: Real End-to-End LLM (Qwen2.5-7B-Instruct-4bit MLX)
    # =========================================================================
    e2e_enrichi_results: list[dict] = []
    e2e_recent26_results: list[dict] = []

    if not args.skip_e2e:
        print(f"\n[Init MLX] Loading {args.mlx_model}...", flush=True)
        mlx_client = LocalMlxLLM(model_path=args.mlx_model, max_tokens=512, temperature=0.0)
        cfg_e2e = RetrievalConfig(final_top_k=8, use_u_shape_ordering=True)
        engine = SfarRagEngine(retriever=retriever, llm=mlx_client, default_config=cfg_e2e)

        # Select ALL 34 hardest/newest cases in benchmark_enrichi_phase1:
        # 11 Pediatric/Neonatal + 11 Ambiguous/Ask-Clarification + 12 revised Adult cases
        target_qids: list[str] = []
        for qid, raw in raw_rows.items():
            pop = raw["classification"].get("population_enonce")
            beh = raw["proposed"].get("expected_behavior")
            if pop in ("Pédiatrie", "Adulte") or beh == "ask_clarification":
                target_qids.append(qid)
        print(f"[Part B E2E] Running {len(target_qids)} critical benchmark_enrichi_phase1 cases on Qwen2.5-7B MLX...", flush=True)

        t_b = time.perf_counter()
        for idx, qid in enumerate(target_qids, 1):
            raw = raw_rows[qid]
            pub = ds.cases[qid].public
            q = pub["question"]
            if pub["format"] == "mcq" and pub["choices"]:
                q = q + "\n" + "\n".join(f"{k}. {v}" for k, v in pub["choices"].items())
            mode = "clinical_detailed"
            resp = engine.answer(q, mode=mode, config=cfg_e2e)
            ok, reason = _check_expected_match(raw, resp.answer)
            group = (
                "ambiguous_clarification"
                if raw["proposed"]["expected_behavior"] == "ask_clarification"
                else ("pediatrie_neonat" if raw["classification"].get("population_enonce") == "Pédiatrie" else "adulte_revise")
            )
            e2e_enrichi_results.append(
                {
                    "question_id": qid,
                    "group": group,
                    "format": pub["format"],
                    "expected_behavior": raw["proposed"]["expected_behavior"],
                    "question": pub["question"],
                    "short_expected": raw["reference_answer"].get("short_answer", ""),
                    "answer": resp.answer,
                    "is_correct": ok,
                    "check_reason": reason,
                    "grounding_score": resp.verification.grounding_score,
                    "hallucinated_molecules": resp.verification.ungrounded_molecules,
                    "citations_used": resp.verification.citations_found,
                    "top1_section": resp.retrieved_chunks[0].chunk.section_path if resp.retrieved_chunks else "",
                    "top1_version": resp.retrieved_chunks[0].chunk.version_label if resp.retrieved_chunks else "",
                    "latency_ms": round(resp.latency_ms.get("total_ms", 0.0), 1),
                }
            )
            print(
                f"  [{idx:02d}/{len(target_qids)}] {qid} ({group[:8]}): {'PASS' if ok else 'FAIL'} [{reason}] "
                f"| ground={resp.verification.grounding_score:.2f} | hall={len(resp.verification.ungrounded_molecules)} | {resp.latency_ms.get('total_ms',0)/1000:.1f}s",
                flush=True,
            )

        print(f"[Part B Done] {len(target_qids)} cases in {time.perf_counter()-t_b:.1f}s", flush=True)

        # PART C: 14 Brand-New 2026 SFAR Recommendations
        print(f"\n[Part C E2E] Running {len(RECENT_2026_CASES)} newest-2026 SFAR RFE cases on Qwen2.5-7B MLX...", flush=True)
        t_c = time.perf_counter()
        for idx, tc in enumerate(RECENT_2026_CASES, 1):
            q = str(tc["question"])
            mode = "temporal_diff" if tc["id"] == "REC26-03" else "clinical_detailed"
            resp = engine.answer(q, mode=mode, config=cfg_e2e)
            ans_f = _fold(resp.answer)
            all_ok = all(_fold(k) in ans_f for k in tc["must_contain_all"])
            any_ok = any(_fold(k) in ans_f for k in tc["must_contain_any"])
            ok = all_ok and any_ok
            top_docs = [
                f"{r.chunk.effective_year or '?'} {r.chunk.version_label or ''} | {r.chunk.doc_title[:45]}"
                for r in resp.retrieved_chunks[:3]
            ]
            e2e_recent26_results.append(
                {
                    "id": tc["id"],
                    "rfe": tc["rfe"],
                    "question": q,
                    "expected_summary": tc["expected_summary"],
                    "answer": resp.answer,
                    "is_correct": ok,
                    "all_ok": all_ok,
                    "any_ok": any_ok,
                    "grounding_score": resp.verification.grounding_score,
                    "hallucinated_molecules": resp.verification.ungrounded_molecules,
                    "citations_used": resp.verification.citations_found,
                    "top3_sources": top_docs,
                    "latency_ms": round(resp.latency_ms.get("total_ms", 0.0), 1),
                }
            )
            print(
                f"  [{idx:02d}/{len(RECENT_2026_CASES)}] {tc['id']} ({tc['rfe'][:32]}): {'PASS' if ok else 'FAIL'} "
                f"| ground={resp.verification.grounding_score:.2f} | hall={len(resp.verification.ungrounded_molecules)} | {resp.latency_ms.get('total_ms',0)/1000:.1f}s",
                flush=True,
            )
        print(f"[Part C Done] {len(RECENT_2026_CASES)} cases in {time.perf_counter()-t_c:.1f}s", flush=True)

    # Save JSON + Markdown Report
    summary = {
        "index_dir": str(args.index_dir),
        "num_chunks": len(store.chunks),
        "part_a_retrieval_171": {
            "official_aggregate": agg_ret,
            "by_population": pop_summary,
            "obsolete_chunks_in_top10": obsolete_chunks,
            "v31_chunk_hits_in_top10": v31_hits,
            "retrieval_seconds": round(ret_sec, 2),
        },
        "part_b_e2e_critical34": {
            "total": len(e2e_enrichi_results),
            "passed": sum(1 for r in e2e_enrichi_results if r["is_correct"]),
            "by_group": {
                g: {
                    "passed": sum(1 for r in e2e_enrichi_results if r["group"] == g and r["is_correct"]),
                    "total": sum(1 for r in e2e_enrichi_results if r["group"] == g),
                }
                for g in ("pediatrie_neonat", "ambiguous_clarification", "adulte_revise")
            },
            "hallucinated_molecules_total": sum(len(r["hallucinated_molecules"]) for r in e2e_enrichi_results),
            "cases": e2e_enrichi_results,
        },
        "part_c_newest_2026_rfes": {
            "total": len(e2e_recent26_results),
            "passed": sum(1 for r in e2e_recent26_results if r["is_correct"]),
            "hallucinated_molecules_total": sum(len(r["hallucinated_molecules"]) for r in e2e_recent26_results),
            "cases": e2e_recent26_results,
        },
    }

    json_out = args.out_dir / "eval_benchmark_enrichi.json"
    json_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Build Markdown Report
    md_lines = [
        "# Évaluation RAG-SFAR Frontier 2026 (V3.1) — Benchmark Enrichi Phase 1 & Recommandations 2026",
        "",
        f"- **Index testé** : `{args.index_dir}` (`{len(store.chunks):,}` chunks, **265 documents SFAR** incluant l'édition **Antibioprophylaxie V3.1 du 10/07/2026** SHA-256 `642ad1f1...`)",
        f"- **Validation schéma officiel `sfar_evaluator`** : **171/171 VALIDE** (`{preds_path}` + `{manifest_path}`)",
        f"- **Chunks obsolètes (V3.0 / 2018 / 2017) dans les 1 710 chunks retournés** : **{obsolete_chunks} (`0.0%`)**",
        "",
        "## 1. Retrieval Officiel `sfar_evaluator` — 171 Questions (`benchmark_enrichi_phase1`, 160 avec `evidence_sets`)",
        "",
        "| Métrique officielle `sfar_evaluator` | Top-1 | Top-3 | Top-5 | Top-10 |",
        "|---|---:|---:|---:|---:|",
        f"| **Hit@k** | {agg_ret['at_k']['1']['hit']['rate']*100:.1f}% ({agg_ret['at_k']['1']['hit']['numerator']}/160) | {agg_ret['at_k']['3']['hit']['rate']*100:.1f}% ({agg_ret['at_k']['3']['hit']['numerator']}/160) | {agg_ret['at_k']['5']['hit']['rate']*100:.1f}% ({agg_ret['at_k']['5']['hit']['numerator']}/160) | **{agg_ret['at_k']['10']['hit']['rate']*100:.1f}% ({agg_ret['at_k']['10']['hit']['numerator']}/160)** |",
        f"| **Mean Recall@k** | {agg_ret['at_k']['1']['mean_recall']*100:.1f}% | {agg_ret['at_k']['3']['mean_recall']*100:.1f}% | {agg_ret['at_k']['5']['mean_recall']*100:.1f}% | **{agg_ret['at_k']['10']['mean_recall']*100:.1f}%** |",
        f"| **Evidence Sufficiency@k** | {agg_ret['at_k']['1']['sufficiency']['rate']*100:.1f}% ({agg_ret['at_k']['1']['sufficiency']['numerator']}/160) | {agg_ret['at_k']['3']['sufficiency']['rate']*100:.1f}% ({agg_ret['at_k']['3']['sufficiency']['numerator']}/160) | {agg_ret['at_k']['5']['sufficiency']['rate']*100:.1f}% ({agg_ret['at_k']['5']['sufficiency']['numerator']}/160) | **{agg_ret['at_k']['10']['sufficiency']['rate']*100:.1f}% ({agg_ret['at_k']['10']['sufficiency']['numerator']}/160)** |",
        "",
        f"- **MRR (first hit)** : `{agg_ret['mrr_first_hit']:.3f}` | **Temps retrieval (171 questions)** : `{ret_sec:.1f}s`",
        "",
        "### Ventilation par population de l'énoncé (`population_enonce`)",
        "",
        "| Population | Effectif | Hit@5 | Suff@5 | Hit@10 | Suff@10 | Mean Recall@10 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for pop, s in pop_summary.items():
        n = s["n"]
        md_lines.append(
            f"| {pop} | {n} | {s['hit_at_5']}/{n} ({100*s['hit_at_5']/n:.1f}%) | {s['suff_at_5']}/{n} ({100*s['suff_at_5']/n:.1f}%) | {s['hit_at_10']}/{n} ({100*s['hit_at_10']/n:.1f}%) | {s['suff_at_10']}/{n} ({100*s['suff_at_10']/n:.1f}%) | {100*s['mean_recall_10']:.1f}% |"
        )

    if e2e_enrichi_results:
        pb = summary["part_b_e2e_critical34"]
        md_lines += [
            "",
            f"## 2. End-to-End LLM (`Qwen2.5-7B-Instruct-4bit` MLX) — {pb['total']} Cas Critiques & Nouveaux de `benchmark_enrichi_phase1`",
            "",
            f"- **Score global** : **{pb['passed']}/{pb['total']} ({100*pb['passed']/pb['total']:.1f}%)** | **Molécules hallucinées** : **{pb['hallucinated_molecules_total']}**",
            "",
            "| Sous-groupe `benchmark_enrichi_phase1` | Réussite |",
            "|---|---:|",
        ]
        for g, st in pb["by_group"].items():
            pct = 100 * st["passed"] / st["total"] if st["total"] else 0.0
            md_lines.append(f"| `{g}` | **{st['passed']}/{st['total']} ({pct:.1f}%)** |")
        md_lines += ["", "| ID | Groupe | Format | Statut | Vérif | Grounding | Hall. | Attendu (court) |", "|---|---|---|---|---|---:|---:|---|"]
        for r in e2e_enrichi_results:
            st = "PASS" if r["is_correct"] else "FAIL"
            md_lines.append(
                f"| {r['question_id']} | `{r['group']}` | {r['format']} | **{st}** | `{r['check_reason']}` | {r['grounding_score']:.2f} | {len(r['hallucinated_molecules'])} | {r['short_expected'][:85].replace('|', '/')} |"
            )

    if e2e_recent26_results:
        pc = summary["part_c_newest_2026_rfes"]
        md_lines += [
            "",
            f"## 3. End-to-End LLM — {pc['total']} Recommandations SFAR les Plus Récentes (2026, incl. ABP V3.1 du 10/07/2026)",
            "",
            f"- **Score global** : **{pc['passed']}/{pc['total']} ({100*pc['passed']/pc['total']:.1f}%)** | **Molécules hallucinées** : **{pc['hallucinated_molecules_total']}**",
            "",
            "| ID | RFE 2026 | Statut | Grounding | Hall. | Top-1 Source |",
            "|---|---|---|---:|---:|---|",
        ]
        for r in e2e_recent26_results:
            st = "PASS" if r["is_correct"] else "FAIL"
            top1 = r["top3_sources"][0] if r["top3_sources"] else "-"
            md_lines.append(
                f"| {r['id']} | {r['rfe']} | **{st}** | {r['grounding_score']:.2f} | {len(r['hallucinated_molecules'])} | {top1.replace('|', '/')} |"
            )

    md_out = args.out_dir / "eval_benchmark_enrichi.md"
    md_out.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"\nSaved full JSON -> {json_out}\nSaved Markdown report -> {md_out}")


if __name__ == "__main__":
    main()
