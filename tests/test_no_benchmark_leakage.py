"""Anti-leakage guard (principle 3): no evaluation question or reference answer may be encoded
in the system's code (lexicons, prompts, routing rules, few-shot examples).

Scans every file under src/ except the evaluation package (which legitimately loads datasets)
for:
- any 7-word sequence of a question (or MCQ choice) that is specific to that question
  (appears in at most 2 questions, so shared templates like "quelle est la recommandation
  d'antibioprophylaxie pour une" are ignored);
- any reference answer of 3 words or more, verbatim, unless it is an answer class shared by
  more than 5 % of the questions (e.g. "pas d'antibioprophylaxie").

Text is accent-folded and lower-cased before matching.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "rag_sfar"
EXCLUDED_DIRS = {SRC / "evaluation"}
NGRAM = 7

EVAL_SOURCES = [
    ROOT / "data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json",
    *sorted((ROOT / "eval" / "datasets").glob("*.jsonl")),
    *sorted((ROOT / "eval_internal" / "datasets").glob("*.jsonl")),
]


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", t))


def _load_eval_texts() -> list[dict[str, object]]:
    out = []
    for path in EVAL_SOURCES:
        if not path.exists():
            continue
        if path.suffix == ".json":
            rows = json.loads(path.read_text(encoding="utf-8")).get("questions", [])
            for r in rows:
                out.append({
                    "src": f"{path.name}:{r['id']}",
                    "question": r["question"],
                    "choices": list((r.get("choices") or {}).values()),
                    "answer": r.get("réponse", ""),
                })
        else:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    out.append({
                        "src": f"{path.name}:{r['id']}",
                        "question": r["question"],
                        "choices": list((r.get("choices") or {}).values()),
                        "answer": r.get("reference_answer", ""),
                    })
    return out


def _src_blob() -> str:
    parts = []
    for p in sorted(SRC.rglob("*.py")):
        if any(ex in p.parents for ex in EXCLUDED_DIRS):
            continue
        parts.append(_fold(p.read_text(encoding="utf-8")))
    return "\n".join(parts)


def _ngrams(words: list[str], n: int) -> list[str]:
    return [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]


def find_leaks() -> list[str]:
    items = _load_eval_texts()
    texts = {it["src"]: [_fold(it["question"])] + [_fold(c) for c in it["choices"]] for it in items}
    # Document frequency over unique question texts (the same benchmark can be loaded twice:
    # source JSON and normalized copy).
    ngram_df: Counter[str] = Counter()
    for segs in {tuple(v) for v in texts.values()}:
        ngram_df.update({g for s in segs for g in _ngrams(s.split(), NGRAM)})
    blob = _src_blob()
    # Answer classes shared by many questions ("pas d'antibioprophylaxie") are output labels,
    # not question-specific content; they are checked by the n-gram rule only.
    answer_df = Counter(_fold(str(it["answer"])) for it in items)
    max_answer_df = max(3, int(0.05 * len(items)))
    leaks = []
    for it in items:
        for g in {g for s in texts[it["src"]] for g in _ngrams(s.split(), NGRAM)}:
            if ngram_df[g] <= 2 and g in blob:
                leaks.append(f"{it['src']} question n-gram: '{g}'")
        ans = _fold(str(it["answer"]))
        if len(ans.split()) >= 3 and answer_df[ans] <= max_answer_df and ans in blob:
            leaks.append(f"{it['src']} reference answer: '{ans}'")
    return sorted(set(leaks))


def test_eval_sources_found():
    assert any(p.exists() for p in EVAL_SOURCES), "no evaluation dataset found to check against"


# Known leaks found by the phase-1 audit; strict xfail forces removing this marker once fixed.
@pytest.mark.xfail(strict=True, reason="Benchmark text still present in src/ (phase-1 audit); remove marker after cleanup")
def test_no_benchmark_text_in_system_code():
    leaks = find_leaks()
    assert not leaks, "Evaluation text found in system code:\n" + "\n".join(leaks)


if __name__ == "__main__":
    for leak in find_leaks():
        print(leak)
