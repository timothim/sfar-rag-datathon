#!/usr/bin/env python3
"""Audit d'intégrité : pouvoir discriminant des métriques annoncées.

Calculs légers (lecture SQLite + JSON, aucun modèle chargé) :
  A. Evidence recall : pour chaque question ouverte, fraction des chunks de la RFE ABP V3.0
     (non bibliographiques) qui contiennent déjà les "required_evidence_terms" ;
     baseline "8 chunks ABP V3.0 tirés au hasard" (Monte-Carlo, graine fixe).
  B. Distribution des réponses de référence et baselines à réponse constante avec le
     scorer officiel (OpenScorer/QCMScorer, recopié à l'identique) sur 171 / stratifié 50 /
     "inédites" 50.
  C. Effectif réel des sous-métriques "allergie" (retrieval et E2E).
  D. Réponses du système contenant plusieurs réponses candidates (exploitation du scorer
     par sous-chaîne) et "Sourcing" forcé.
Usage : .venv/bin/python reports/agents/eval_integrity_scripts/metric_triviality.py
"""

from __future__ import annotations

import collections
import json
import random
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from rag_sfar.evaluation.benchmarks import load_antibioprophylaxie_benchmark  # noqa: E402

BENCH = ROOT / "data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json"
DB = ROOT / "index/table_aware_sota/metadata.sqlite"
V3_DOC_PREFIX = "2026_RFE-antibioprophylaxie"


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def norm(t: str) -> str:  # scorer.normalize officiel
    t = t.lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t.rstrip(".").strip()


def official_score(qtype: str, expected: str, actual: str) -> bool:
    if qtype == "mcq":
        m = re.search(r"\b([A-D])\b", actual.upper())
        return (m.group(1) if m else None) == expected.strip().upper()
    ne, na = norm(expected), norm(actual)
    if ne in ("pas d'antibioprophylaxie", "hors périmètre"):
        return ne in na
    return all(norm(m) in na for m in expected.split("+"))


def main() -> None:
    qs = load_antibioprophylaxie_benchmark(BENCH)
    out: dict = {}

    # ---------- A. evidence recall triviality ----------
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "select payload_json from chunks where doc_id like ? and is_reference_section=0",
        (V3_DOC_PREFIX + "%",),
    ).fetchall()
    v3_texts = [fold(json.loads(r[0])["indexed_text"]) for r in rows]
    n_v3 = len(v3_texts)
    rng = random.Random(1234)
    per_q = []
    open_with_terms = [q for q in qs if q.required_evidence_terms]
    rand_hits_total = 0.0
    TRIALS = 2000
    for q in open_with_terms:
        terms = [fold(t) for t in q.required_evidence_terms]
        has = [all(t in tx for t in terms) for tx in v3_texts]
        frac = sum(has) / n_v3
        hits = 0
        for _ in range(TRIALS):
            idx = rng.sample(range(n_v3), 8)
            blob = " ".join(v3_texts[i] for i in idx)
            hits += all(t in blob for t in terms)
        p8 = hits / TRIALS
        rand_hits_total += p8
        per_q.append({"id": q.id, "terms": q.required_evidence_terms, "frac_v3_chunks": round(frac, 3), "p_random8": round(p8, 3)})
    out["A_evidence"] = {
        "abp_v3_non_reference_chunks": n_v3,
        "questions_with_evidence_terms": len(open_with_terms),
        "mcq_without_terms": sum(1 for q in qs if q.question_type == "mcq"),
        "term_sets": collections.Counter(" + ".join(q.required_evidence_terms) for q in open_with_terms).most_common(),
        "expected_recall_8_random_abp_v3_chunks": round(rand_hits_total / len(open_with_terms), 4),
        "questions_where_term_in_>=20pct_of_v3_chunks": sum(1 for r in per_q if r["frac_v3_chunks"] >= 0.20),
        "questions_where_random8_p>=0.9": sum(1 for r in per_q if r["p_random8"] >= 0.9),
        "hardest": sorted(per_q, key=lambda r: r["p_random8"])[:12],
    }

    # ---------- B. reference answer distribution & constant baselines ----------
    raw = json.loads(BENCH.read_text(encoding="utf-8"))["questions"]
    open_ans = collections.Counter(q["réponse"] for q in raw if q["type"] == "open")
    mcq_ans = collections.Counter(q["réponse"] for q in raw if q["type"] == "mcq")
    strat_ids = set(json.loads((ROOT / "reports/repro/e2e_c8_v3_7b_ids.json").read_text())) if (ROOT / "reports/repro/e2e_c8_v3_7b_ids.json").exists() else {r["id"] for r in json.loads((ROOT / "reports/e2e_c8_v3_7b.json").read_text())["results"]}
    unseen_ids = {r["id"] for r in json.loads((ROOT / "reports/e2e_heldout_unseen_50_7b.json").read_text())["results"]}
    subsets = {
        "all_171": [q for q in qs],
        "stratified_50": [q for q in qs if q.id in strat_ids],
        "unseen_50": [q for q in qs if q.id in unseen_ids],
    }
    strategies = {
        "constant 'Pas d'antibioprophylaxie' / QCM 'C'": ("Pas d'antibioprophylaxie", "C"),
        "constant 'Céfazoline' / QCM 'C'": ("Céfazoline", "C"),
        "shotgun 'Céfazoline, Amoxicilline/Clavulanate, Céfoxitine ou Pas d'antibioprophylaxie' / QCM 'C'": (
            "Céfazoline, Amoxicilline/Clavulanate, Céfoxitine ou Pas d'antibioprophylaxie",
            "C",
        ),
    }
    base = {}
    for sname, qsub in subsets.items():
        base[sname] = {"n": len(qsub), "open": sum(q.question_type == "open" for q in qsub)}
        for label, (oa, ma) in strategies.items():
            ok = sum(official_score(q.question_type, q.expected_answer, ma if q.question_type == "mcq" else oa) for q in qsub)
            base[sname][label] = f"{ok}/{len(qsub)} = {ok/len(qsub):.1%}"
    out["B_answers"] = {
        "open_answer_distribution": open_ans.most_common(),
        "mcq_letter_distribution": mcq_ans.most_common(),
        "constant_baselines_official_scorer": base,
    }

    # ---------- C. allergy effective sizes ----------
    out["C_allergy"] = {
        "is_allergy_questions": [q.id for q in qs if q.is_allergy_question],
        "allergy_with_evidence_terms (retrieval 'Allergie Recall' denominator)": [q.id for q in qs if q.is_allergy_question and q.required_evidence_terms],
        "allergy_in_stratified_50": sorted(q.id for q in subsets["stratified_50"] if q.is_allergy_question),
        "allergy_in_unseen_50": sorted(q.id for q in subsets["unseen_50"] if q.is_allergy_question),
    }

    # ---------- D. system answers: multi-candidate / sourcing ----------
    candidates = [norm(a) for a in open_ans] + ["céfuroxime", "clindamycine", "vancomycine"]
    d = {}
    for f in ["reports/e2e_c8_v3_7b.json", "reports/e2e_heldout_unseen_50_7b.json"]:
        res = json.loads((ROOT / f).read_text())["results"]
        multi = []
        for r in res:
            if r["type"] != "open":
                continue
            na = norm(r["actual"])
            found = {c for c in candidates if c in na}
            # retirer les composantes d'une association déjà comptée
            if len(found) >= 2 and not any(a != b and a in b for a in found for b in found):
                multi.append((r["id"], r["actual"]))
        year_from_llm = sum(1 for r in res if re.search(r"\b20\d\d\b", r["actual"]))
        d[f] = {
            "open_answers_with_>=2_distinct_candidate_answers": multi,
            "answers_containing_a_year (Sourcing)": f"{year_from_llm}/{len(res)}",
            "evidence_present_true": sum(1 for r in res if r["evidence_present"]),
            "mcq_evidence_present_true": f"{sum(1 for r in res if r['type']=='mcq' and r['evidence_present'])}/{sum(1 for r in res if r['type']=='mcq')}",
        }
    out["D_system_answers"] = d
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
