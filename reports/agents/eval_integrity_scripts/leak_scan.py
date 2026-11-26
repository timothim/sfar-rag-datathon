#!/usr/bin/env python3
"""Audit d'intégrité : fuites benchmark -> système.

Compare systématiquement le texte du code (src/ et scripts/) aux questions, choix,
titres et réponses du benchmark antibioprophylaxie (171 questions) :
  1. n-grammes de mots (n=4..) partagés entre une ligne de code et une question/titre
     du benchmark, en excluant les n-grammes "gabarit" (présents dans > 5 questions) ;
     chaque match est qualifié "présent aussi dans la RFE V3.0" ou "formulation propre
     au benchmark" (absente de la RFE V3.0 = recopie du benchmark, pas du corpus).
  2. Réponses exactes du benchmark (chaînes complètes, ex. "Clindamycine + Gentamicine")
     retrouvées dans le code.
  3. Posologies/choix QCM retrouvés dans le code.
  4. Titres du benchmark (n-grammes de 3 mots) retrouvés dans le code.

Lecture seule. Aucune dépendance hors stdlib. Usage :
    python reports/agents/eval_integrity_scripts/leak_scan.py [--json out.json]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BENCH = ROOT / "data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json"
V3_MD = next(
    (ROOT / "data/sfar_recommendations/output/chandra/2023").glob(
        "RFE-antibioprophylaxie-2023_V3.0*/*.md"
    )
)
CODE_DIRS = [ROOT / "src", ROOT / "scripts", ROOT / "tests"]
# Code d'évaluation : les matches y sont attendus (chargement du benchmark), on les
# rapporte à part pour ne pas gonfler le compte "système".
EVAL_FILES = {"src/rag_sfar/evaluation/benchmarks.py", "scripts/build_masterclass_pdf.py"}


def is_eval(rel: str) -> bool:
    """Code d'évaluation, de présentation ou de test (rapporté à part)."""
    return rel in EVAL_FILES or rel.startswith("tests/")


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("’", "'")
    return s


def words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:[/+-][a-z0-9]+)*", fold(s))


def ngrams(toks: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(toks[i : i + n]) for i in range(len(toks) - n + 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--n", type=int, default=4)
    args = ap.parse_args()
    N = args.n

    data = json.loads(BENCH.read_text(encoding="utf-8"))
    qs = data["questions"]
    v3_text = V3_MD.read_text(encoding="utf-8")
    v3_toks = words(re.sub(r"<[^>]+>", " ", v3_text))
    v3_ngrams = ngrams(v3_toks, N)

    # ---- benchmark n-grams (question + choix) ----
    q_ngrams: dict[str, set[tuple[str, ...]]] = {}
    df: collections.Counter[tuple[str, ...]] = collections.Counter()
    for q in qs:
        blob = q["question"] + " " + " ".join((q.get("choices") or {}).values())
        g = ngrams(words(blob), N)
        q_ngrams[q["id"]] = g
        df.update(g)
    template = {g for g, c in df.items() if c > 5}
    ng_to_q: dict[tuple[str, ...], list[str]] = collections.defaultdict(list)
    for qid, g in q_ngrams.items():
        for x in g - template:
            ng_to_q[x].append(qid)

    # titres (3-grammes, plus courts)
    t_ng: dict[tuple[str, ...], list[str]] = collections.defaultdict(list)
    for q in qs:
        for x in ngrams(words(q["titre"]), 3):
            t_ng[x].append(q["id"])
    t_df = {g: len(v) for g, v in t_ng.items()}

    # réponses ouvertes complètes multi-mots / associations
    answers: dict[str, list[str]] = collections.defaultdict(list)
    for q in qs:
        if q["type"] == "open":
            answers[q["réponse"]].append(q["id"])
    # choix QCM (texte complet) et posologies
    choice_texts: dict[str, list[str]] = collections.defaultdict(list)
    dose_re = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:mg/kg|mg|g)\b(?:\s*ivl)?", re.I)
    doses: dict[str, list[str]] = collections.defaultdict(list)
    for q in qs:
        for v in (q.get("choices") or {}).values():
            choice_texts[fold(v).strip()].append(q["id"])
            for d in dose_re.findall(v):
                doses[re.sub(r"\s+", "", fold(d))].append(q["id"])

    # ---- scan code ----
    results = {"ngram": [], "answer": [], "choice": [], "dose": [], "title": []}
    files = sorted(p for d in CODE_DIRS for p in d.rglob("*.py") if "__pycache__" not in p.parts)
    for path in files:
        rel = str(path.relative_to(ROOT))
        lines = path.read_text(encoding="utf-8").splitlines()
        for ln, line in enumerate(lines, start=1):
            toks = words(line)
            if len(toks) < 2:
                continue
            fl = fold(line)
            # 1. n-grams
            hits = ngrams(toks, N) & set(ng_to_q)
            if hits:
                qids = sorted({q for h in hits for q in ng_to_q[h]}, key=lambda s: int(s[1:]))
                bench_only = sorted(" ".join(h) for h in hits if h not in v3_ngrams)
                results["ngram"].append(
                    {
                        "file": rel,
                        "line": ln,
                        "eval_code": is_eval(rel),
                        "qids": qids,
                        "n_hits": len(hits),
                        "bench_only_ngrams": bench_only,
                        "sample": sorted(" ".join(h) for h in hits)[:6],
                        "text": line.strip()[:220],
                    }
                )
            # 2. réponses complètes (multi-tokens uniquement : association ou slash)
            for ans, qids in answers.items():
                if ("+" in ans or "/" in ans or "-" in ans) and fold(ans) in fl:
                    results["answer"].append(
                        {"file": rel, "line": ln, "eval_code": is_eval(rel), "answer": ans, "qids": qids, "text": line.strip()[:200]}
                    )
            # 3. choix QCM complets (>= 12 caractères)
            for ch, qids in choice_texts.items():
                if len(ch) >= 12 and ch in fl:
                    results["choice"].append(
                        {"file": rel, "line": ln, "eval_code": is_eval(rel), "choice": ch, "qids": qids, "text": line.strip()[:200]}
                    )
            # 4. posologies
            fl_nospace = re.sub(r"\s+", "", fl)
            for d, qids in doses.items():
                if re.search(rf"(?<![0-9]){re.escape(d)}", fl_nospace):
                    results["dose"].append(
                        {"file": rel, "line": ln, "eval_code": is_eval(rel), "dose": d, "qids": sorted(set(qids)), "text": line.strip()[:200]}
                    )
            # 5. titres
            th = {h for h in ngrams(toks, 3) if h in t_ng and t_df[h] <= 3}
            if th:
                results["title"].append(
                    {
                        "file": rel,
                        "line": ln,
                        "eval_code": is_eval(rel),
                        "qids": sorted({q for h in th for q in t_ng[h]}, key=lambda s: int(s[1:])),
                        "title_ngrams": sorted(" ".join(h) for h in th),
                        "text": line.strip()[:200],
                    }
                )

    # ---- résumé chiffré ----
    def summarize(kind: str) -> dict:
        rows = results[kind]
        sys_rows = [r for r in rows if not r["eval_code"]]
        qids = {q for r in sys_rows for q in r["qids"]}
        return {
            "lines_total": len(rows),
            "lines_system_code": len(sys_rows),
            "files_system_code": sorted({r["file"] for r in sys_rows}),
            "distinct_questions_touched_by_system_code": len(qids),
            "question_ids": sorted(qids, key=lambda s: int(s[1:])),
        }

    bench_only_lines = [r for r in results["ngram"] if not r["eval_code"] and r["bench_only_ngrams"]]
    summary = {
        "benchmark_questions": len(qs),
        "ngram_size": N,
        "template_ngrams_excluded": len(template),
        "ngram": summarize("ngram"),
        "ngram_bench_only_system_lines": len(bench_only_lines),
        "ngram_bench_only_questions": sorted(
            {q for r in bench_only_lines for q in r["qids"]}, key=lambda s: int(s[1:])
        ),
        "answer": summarize("answer"),
        "choice": summarize("choice"),
        "dose": summarize("dose"),
        "title": summarize("title"),
    }
    all_sys_q = set()
    for k in ("ngram", "answer", "choice", "dose", "title"):
        all_sys_q |= set(summary[k]["question_ids"])
    summary["union_questions_touched_by_system_code"] = len(all_sys_q)
    summary["union_question_ids"] = sorted(all_sys_q, key=lambda s: int(s[1:]))

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("\n=== Lignes de code SYSTÈME partageant des n-grammes avec le benchmark ===")
    for r in results["ngram"]:
        if r["eval_code"]:
            continue
        tag = "BENCH-ONLY" if r["bench_only_ngrams"] else "aussi-RFE"
        print(f"{r['file']}:{r['line']} [{tag}] {','.join(r['qids'])} :: {r['sample'][:3]} :: {r['text'][:140]}")
    for kind in ("answer", "choice", "dose", "title"):
        print(f"\n=== {kind} (code système) ===")
        for r in results[kind]:
            if r["eval_code"]:
                continue
            key = r.get("answer") or r.get("choice") or r.get("dose") or r.get("title_ngrams")
            print(f"{r['file']}:{r['line']} {key} {','.join(r['qids'][:8])} :: {r['text'][:140]}")
    print("\n=== Code d'évaluation / présentation (attendu, pour info) ===")
    for r in results["ngram"]:
        if r["eval_code"]:
            print(f"{r['file']}:{r['line']} {','.join(r['qids'])} :: {r['text'][:120]}")

    if args.json:
        args.json.write_text(
            json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
