#!/usr/bin/env python3
"""Audit du stress-test multi_rfe_stress_30 (benchmarks.py) :
  1. Recouvrement avec le benchmark ABP 171 (paraphrases / recopies de questions).
  2. Recopie de formulations du corpus : plus longue séquence de mots commune entre la
     question (et la réponse attendue) et les chunks du document cible (lineage attendu).
  3. Trivialité des required_evidence_terms : fraction des chunks du lineage cible qui les
     contiennent (un terme présent dans >50 % des chunks du document = test quasi gratuit).
  4. Alignement avec les règles du système : la question déclenche-t-elle une règle codée
     à la main (TEMPORAL_DIFF_PATTERNS, FACET_RULES, MODIFIER_PATTERNS allergie, rec_id) ?
Lecture seule (SQLite en mode ro). Usage :
    .venv/bin/python reports/agents/eval_integrity_scripts/stress_test_audit.py
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from rag_sfar.evaluation.benchmarks import load_multi_rfe_stress_benchmark  # noqa: E402
from rag_sfar.retrieval.crag import FACET_RULES  # noqa: E402
from rag_sfar.retrieval.router import MODIFIER_PATTERNS, TEMPORAL_DIFF_PATTERNS  # noqa: E402

BENCH = ROOT / "data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json"
DB = ROOT / "index/table_aware_sota/metadata.sqlite"


def fold(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    return s.replace("’", "'")


def words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:[./-][a-z0-9]+)*", fold(s))


def longest_common_run(a: list[str], text_ngrams: dict[int, set]) -> int:
    best = 0
    for n in range(2, min(len(a), 25) + 1):
        grams = {tuple(a[i : i + n]) for i in range(len(a) - n + 1)}
        if grams & text_ngrams.setdefault(n, set()):
            best = n
        else:
            break
    return best


def main() -> None:
    ms = load_multi_rfe_stress_benchmark()
    bench = json.loads(BENCH.read_text(encoding="utf-8"))["questions"]
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    doc_rows = con.execute("select doc_id, title, topic_lineage, is_latest_edition from documents").fetchall()
    rows_out = []
    for m in ms:
        # documents cibles : même lineage, ou mots-clés du titre
        target_docs = [
            d for d, t, lin, latest in doc_rows
            if (m.expected_topic_lineage and lin == m.expected_topic_lineage)
            or (m.expected_title_keywords and all(fold(k) in fold(t or "") for k in m.expected_title_keywords))
        ]
        texts = []
        for d in target_docs:
            for (pj,) in con.execute("select payload_json from chunks where doc_id=? and is_reference_section=0", (d,)):
                texts.append(fold(json.loads(pj)["text"]))
        ngr: dict[int, set] = {}
        for tx in texts:
            tw = words(tx)
            for n in range(2, 26):
                s = ngr.setdefault(n, set())
                s.update(tuple(tw[i : i + n]) for i in range(len(tw) - n + 1))
        q_run = longest_common_run(words(m.question), ngr)
        a_run = longest_common_run(words(m.expected_answer), ngr)
        terms = [fold(t) for t in m.required_evidence_terms]
        frac = (sum(all(t in tx for t in terms) for tx in texts) / len(texts)) if texts else None

        # recouvrement avec le benchmark ABP (5-grammes)
        qw = words(m.question)
        q5 = {tuple(qw[i : i + 5]) for i in range(len(qw) - 4)}
        bench_hits = []
        for b in bench:
            bw = words(b["question"])
            b5 = {tuple(bw[i : i + 5]) for i in range(len(bw) - 4)}
            if q5 & b5:
                bench_hits.append(b["id"])

        triggers = []
        if any(re.search(p, m.question.lower()) for p in TEMPORAL_DIFF_PATTERNS):
            triggers.append("router:TEMPORAL_DIFF")
        for name, trig, _sq, _ev in FACET_RULES:
            if trig.search(m.question):
                triggers.append(f"crag:{name}")
        if re.search(r"\bR\d+\.\d+(?:\.\d+)?\b", m.question):
            triggers.append("crag:rec_id")
        if MODIFIER_PATTERNS["allergy"].search(m.question):
            triggers.append("router:allergy")

        rows_out.append(
            {
                "id": m.id,
                "category": m.category,
                "n_target_docs": len(target_docs),
                "n_target_chunks": len(texts),
                "longest_question_run_in_target_doc": q_run,
                "longest_answer_run_in_target_doc": a_run,
                "evidence_terms": m.required_evidence_terms,
                "frac_target_chunks_with_terms": None if frac is None else round(frac, 3),
                "benchmark_ABP_overlap_5gram": bench_hits,
                "system_rule_triggers": triggers,
                "expected_answer": m.expected_answer,
            }
        )

    n = len(rows_out)
    summary = {
        "n": n,
        "authored_by": "équipe système (src/rag_sfar/evaluation/benchmarks.py, aucun annotateur externe mentionné)",
        "questions_paraphrasing_ABP_benchmark": [r["id"] for r in rows_out if r["benchmark_ABP_overlap_5gram"]],
        "questions_with_>=8_word_run_copied_from_target_doc": [r["id"] for r in rows_out if r["longest_question_run_in_target_doc"] >= 8],
        "answers_with_>=6_word_run_copied_from_target_doc": [r["id"] for r in rows_out if r["longest_answer_run_in_target_doc"] >= 6],
        "evidence_terms_in_>=30pct_of_target_chunks": [r["id"] for r in rows_out if (r["frac_target_chunks_with_terms"] or 0) >= 0.30],
        "questions_triggering_hand_coded_rules": [r["id"] for r in rows_out if r["system_rule_triggers"]],
        "expected_answer_is_not_a_clinical_answer (cite only a RFE/section)": [
            r["id"] for r in rows_out if re.match(r"^(RFE|RPP|Recommandations HAS|Section|Recommandation R|Évolution)", r["expected_answer"])
        ],
    }
    print(json.dumps({"summary": summary, "rows": rows_out}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
