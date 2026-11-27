"""K2 — Retrieval-only comparison tas_v6 vs tas_v7, frozen configuration C10_context_notes, k=64,
dev splits only: abpe171 (sufficiency), abpvern (sufficiency), multirfe_synth (passage_hit).
Rows (ids + metrics, no question text) -> reports/agents/K2_annexes/retrieval_rows.jsonl.

    scripts/with_gpu_lock.sh K2 env HF_HUB_OFFLINE=1 .venv/bin/python reports/agents/K2_annexes/run_retrieval_v7.py
"""
from __future__ import annotations
import json, time
from pathlib import Path
from rag_sfar.config import Settings
from rag_sfar.evaluation import harness
from rag_sfar.evaluation.datasets import read_jsonl, split_path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "retrieval_rows.jsonl"
K = 64
SUITES = {"abpe171": "sufficiency", "abpvern": "sufficiency", "multirfe_synth": "passage_hit"}


def main() -> None:
    s = Settings()
    cfg = harness.select_configs("C10_context_notes")[0]
    assert cfg.name == "C10_context_notes"
    sets = {suite: read_jsonl(split_path(suite, "dev")) for suite in SUITES}
    with OUT.open("w", encoding="utf-8") as out:
        for index in ("tas_v6", "tas_v7"):
            r = harness.load_retrievers(ROOT / "index", [cfg.chunking_strategy], s.reranker_provider, s.reranker_model,
                                        index_map={cfg.chunking_strategy: index})[cfg.chunking_strategy]
            t0 = time.perf_counter()
            for suite, items in sets.items():
                for it in items:
                    retrieved, _a, _t = r.retrieve(it.formatted_query(), config=cfg)
                    m = harness.retrieval_metrics(it, retrieved, K)
                    row = {"index": index, "suite": suite, "id": it.id, "n_chunks": len(retrieved),
                           "n_ref_like": sum(1 for x in retrieved[:K] if getattr(x.chunk, "chunk_type", "") == "references")}
                    for key in ("sufficiency", "evidence_recall", "passage_hit", "doc_hit"):
                        if key in m:
                            row[key] = m[key]
                    out.write(json.dumps(row) + "\n")
                out.flush()
                print(index, suite, f"{time.perf_counter() - t0:.0f}s", flush=True)
    print("ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
