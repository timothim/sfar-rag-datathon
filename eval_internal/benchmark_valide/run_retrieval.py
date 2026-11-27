"""V1: retrieval-only runs on the validated standard (abpv171) and vernacular (abpvern) suites.

    scripts/with_gpu_lock.sh V1 env HF_HUB_OFFLINE=1 .venv/bin/python eval_internal/benchmark_valide/run_retrieval.py

One process, index tas_v6, configurations built exactly as in eval_internal/robustness/run_retrieval.py
(frozen C10_context_notes; + use_subword; + use_medical_lexicon; + both), imported read-only.
Same metric call as `rag-sfar-eval --retrieval-only`. Dev and test_posthoc parts of both suites.
Rows (ids + metrics, no text) -> eval_internal/work/v1/retrieval_rows.jsonl.
The test part is the abpe171 test, already used by the final evaluation: post hoc, fixed configurations.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

from rag_sfar.config import Settings
from rag_sfar.evaluation import harness
from rag_sfar.evaluation.datasets import SPLITS_DIR, read_jsonl

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("q1_run", ROOT / "eval_internal/robustness/run_retrieval.py")
q1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q1)  # read-only reuse of build_config / K

CONFIGS = ("frozen", "subword", "lexicon", "subword_lexicon")
OUT = ROOT / "eval_internal/work/v1/retrieval_rows.jsonl"


def main() -> None:
    s = Settings()
    cfgs = {n: q1.build_config(n) for n in CONFIGS}
    base = cfgs["frozen"]
    assert all(c.chunking_strategy == base.chunking_strategy for c in cfgs.values())
    retriever = harness.load_retrievers(ROOT / "index", [base.chunking_strategy], s.reranker_provider, s.reranker_model,
                                        index_map={base.chunking_strategy: "tas_v6"})[base.chunking_strategy]
    retriever.retrieve("antibioprophylaxie chirurgie", config=base)
    sets = {(suite, part): read_jsonl(SPLITS_DIR / suite / f"{part}.jsonl")
            for suite in ("abpv171", "abpvern") for part in ("dev", "test_posthoc")}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    t_all = time.perf_counter()
    with OUT.open("w", encoding="utf-8") as out:
        for name, cfg in cfgs.items():
            for (suite, part), items in sets.items():
                for it in items:
                    t0 = time.perf_counter()
                    retrieved, _a, _t = retriever.retrieve(it.formatted_query(), config=cfg)
                    lat = (time.perf_counter() - t0) * 1000
                    m = harness.retrieval_metrics(it, retrieved, q1.K)
                    row = {"config": name, "config_name": cfg.name, "suite": suite, "part": part, "id": it.id,
                           "latency_ms": lat, "n_chunks": len(retrieved)}
                    for key in ("sufficiency", "evidence_recall", "passage_hit", "doc_hit"):
                        if key in m:
                            row[key] = m[key]
                    out.write(json.dumps(row) + "\n")
                out.flush()
                print(f"{name} {suite} {part} done ({time.perf_counter() - t_all:.0f}s)", flush=True)
    print("ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
