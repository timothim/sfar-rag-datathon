#!/usr/bin/env python3
"""Couverture des règles codées à la main par les jeux d'évaluation.

Pour chaque règle déterministe du système (acronymes, synonymes, motifs du routeur,
facettes CRAG, sous-requêtes QCM/composites, garde-fous de portée du pipeline), compte
combien de questions du benchmark ABP 171 et du stress-test 30 la déclenchent.
Une règle déclenchée presque uniquement par des questions du benchmark (et par aucune
requête d'un autre domaine) est un indice de sur-ajustement.
Usage : .venv/bin/python reports/agents/eval_integrity_scripts/rule_coverage.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from rag_sfar.evaluation.benchmarks import (  # noqa: E402
    load_antibioprophylaxie_benchmark,
    load_multi_rfe_stress_benchmark,
)
from rag_sfar.retrieval.crag import (  # noqa: E402
    FACET_RULES,
    extract_composite_procedure_subqueries,
    extract_mcq_option_subqueries,
    strip_mcq_distractor_options,
)
from rag_sfar.retrieval.medical_lexicon import CLINICAL_SYNONYMS, MEDICAL_ACRONYMS, expand_medical_query, fold_accents  # noqa: E402
from rag_sfar.retrieval.router import MODIFIER_PATTERNS, TEMPORAL_DIFF_PATTERNS  # noqa: E402

BENCH = ROOT / "data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json"


def main() -> None:
    abp = load_antibioprophylaxie_benchmark(BENCH)
    mrfe = load_multi_rfe_stress_benchmark()
    out: dict = {}

    def ids(pred, qs):
        return [q.id for q in qs if pred(q)]

    # 1. lexique
    lex = {}
    for name, table in (("acronym", MEDICAL_ACRONYMS), ("synonym", CLINICAL_SYNONYMS)):
        for k in table:
            a = ids(lambda q, k=k: k in expand_medical_query(q.formatted_query())[1], abp)
            m = ids(lambda q, k=k: k in expand_medical_query(q.formatted_query())[1], mrfe)
            if a or m:
                lex[f"{name}:{k}"] = {"abp171": a, "stress30": m}
    out["lexicon_entries_triggered"] = lex
    out["lexicon_entries_total"] = len(MEDICAL_ACRONYMS) + len(CLINICAL_SYNONYMS)

    # 2. router modifiers / temporal
    out["router"] = {
        f"modifier:{k}": {"abp171": len(ids(lambda q, p=p: bool(p.search(q.question)), abp)), "stress30": len(ids(lambda q, p=p: bool(p.search(q.question)), mrfe))}
        for k, p in MODIFIER_PATTERNS.items()
    }
    out["router"]["temporal_diff"] = {
        "abp171": ids(lambda q: any(re.search(p, q.question.lower()) for p in TEMPORAL_DIFF_PATTERNS), abp),
        "stress30": ids(lambda q: any(re.search(p, q.question.lower()) for p in TEMPORAL_DIFF_PATTERNS), mrfe),
    }

    # 3. CRAG
    crag = {}
    for name, trig, _s, _e in FACET_RULES:
        crag[f"facet:{name}"] = {"abp171": ids(lambda q, t=trig: bool(t.search(q.formatted_query())), abp), "stress30": ids(lambda q, t=trig: bool(t.search(q.formatted_query())), mrfe)}
    crag["mcq_option_subqueries"] = {"abp171": ids(lambda q: bool(extract_mcq_option_subqueries(q.formatted_query())), abp)}
    crag["mcq_distractor_stripping"] = {"abp171": ids(lambda q: strip_mcq_distractor_options(q.formatted_query()) != q.formatted_query(), abp)}
    crag["composite_multi_act"] = {
        "abp171": ids(lambda q: bool(extract_composite_procedure_subqueries(q.formatted_query())), abp),
        "stress30": ids(lambda q: bool(extract_composite_procedure_subqueries(q.formatted_query())), mrfe),
    }
    out["crag"] = crag

    # 4. pipeline scope guards (pipeline.py:556-559 et 586-605)
    def f(q):
        return fold_accents(q.question.lower())

    out["pipeline_guards"] = {
        "main_boost (\\bmain\\b)": {"abp171": ids(lambda q: bool(re.search(r"\bmain\b", f(q))), abp), "stress30": ids(lambda q: bool(re.search(r"\bmain\b", f(q))), mrfe)},
        "cond_trigger voie anterieure": {"abp171": ids(lambda q: "anterieure" in f(q), abp)},
        "cond_trigger epaule": {"abp171": ids(lambda q: "epaule" in f(q), abp)},
        "cond_trigger ouverture articulaire/difficile/temps operatoire long": {
            "abp171": ids(lambda q: any(k in f(q) for k in ("ouverture articulaire", "difficile", "temps operatoire long", "duree longue")), abp)
        },
        "cond_trigger dure-mere": {"abp171": ids(lambda q: any(k in f(q) for k in ("dure-mere", "ouverture")), abp)},
        "allergy_alert_prefix (client.py:280)": {"abp171": ids(lambda q: bool(MODIFIER_PATTERNS["allergy"].search(q.question)), abp), "stress30": ids(lambda q: bool(MODIFIER_PATTERNS["allergy"].search(q.question)), mrfe)},
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
