"""Random-chunk baseline for the README 'evidence recall' metric.

For each antibioprophylaxie question, draw 8 random non-reference chunks from the
current ABP edition and check whether all required evidence terms appear.
Run: HF_HUB_OFFLINE=1 .venv/bin/python reports/repro/random_baseline.py
"""
import json
import random
import sqlite3
import statistics
from pathlib import Path

from rag_sfar.evaluation.benchmarks import load_antibioprophylaxie_benchmark
from rag_sfar.retrieval.medical_lexicon import fold_accents

qs = load_antibioprophylaxie_benchmark(
    Path("data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json")
)
db = sqlite3.connect("index/table_aware_sota/metadata.sqlite")
cur = [r[0] for r in db.execute(
    "select doc_id from documents where topic_lineage='antibioprophylaxie' and is_latest_edition=1")]
rows = db.execute(
    f"select payload_json from chunks where doc_id in ({','.join('?' * len(cur))}) and is_reference_section=0",
    cur,
).fetchall()
texts = [fold_accents(json.loads(p)["indexed_text"].lower()) for (p,) in rows]
evq = [q for q in qs if q.required_evidence_terms]


def rate(seed: int, k: int = 8) -> float:
    rng = random.Random(seed)
    hits = 0
    for q in evq:
        blob = " ".join(rng.sample(texts, k))
        hits += all(fold_accents(t.lower()) in blob for t in q.required_evidence_terms)
    return hits / len(evq)


r = [rate(s) for s in range(30)]
print(f"chunks={len(texts)} questions={len(evq)} mean={statistics.mean(r):.3f} min={min(r):.3f} max={max(r):.3f}")
