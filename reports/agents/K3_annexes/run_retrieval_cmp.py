"""K3 - Retrieval-only comparison index/tas_v6 vs index/tas_v6_tablefix, frozen C10_context_notes,
dev splits only: abpe171 (sufficiency), abpvern (sufficiency), multirfe_synth (passage_hit =
gold passage in the returned context). Same call as V1/Q1 (`retriever.retrieve(item.formatted_query(),
config=cfg)` then `harness.retrieval_metrics(item, retrieved, K)`). Rows: ids + metrics only.

    scripts/with_gpu_lock.sh K3 env HF_HUB_OFFLINE=1 .venv/bin/python -I reports/agents/K3_annexes/run_retrieval_cmp.py
"""
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from rag_sfar.config import Settings  # noqa: E402
from rag_sfar.evaluation import harness  # noqa: E402
from rag_sfar.evaluation.datasets import SPLITS_DIR, read_jsonl  # noqa: E402

K = 64
OUT = Path(__file__).parent / "retrieval_rows.jsonl"
SETS = {
    "abpe171": (SPLITS_DIR / "abpe171" / "dev.jsonl", "sufficiency"),
    "abpvern": (SPLITS_DIR / "abpvern" / "dev.jsonl", "sufficiency"),
    "multirfe_synth": (ROOT / "eval_internal" / "splits" / "multirfe_synth" / "dev.jsonl", "passage_hit"),
}


def main() -> None:
    s = Settings()
    cfg = harness.select_configs("C10_context_notes")[0]
    assert cfg.name == "C10_context_notes"
    rows = []
    for index in ("tas_v6", "tas_v6_tablefix"):
        r = harness.load_retrievers(ROOT / "index", [cfg.chunking_strategy], s.reranker_provider, s.reranker_model,
                                    index_map={cfg.chunking_strategy: index})[cfg.chunking_strategy]
        for suite, (path, metric) in SETS.items():
            t0 = time.perf_counter()
            for it in read_jsonl(path):
                retrieved, _a, _t = r.retrieve(it.formatted_query(), config=cfg)
                m = harness.retrieval_metrics(it, retrieved, K)
                rows.append({"index": index, "suite": suite, "id": it.id, "metric": metric, "value": m.get(metric),
                             "chunk_ids": [rc.chunk.chunk_id for rc in retrieved]})
            print(index, suite, f"{time.perf_counter() - t0:.0f}s", flush=True)
        del r
        gc.collect()
    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    summary = {}
    for suite in SETS:
        a = {x["id"]: x["value"] for x in rows if x["index"] == "tas_v6" and x["suite"] == suite}
        b = {x["id"]: x["value"] for x in rows if x["index"] == "tas_v6_tablefix" and x["suite"] == suite}
        ids = sorted(a)
        va, vb = [a[i] for i in ids], [b[i] for i in ids]
        ok = [(x, y) for x, y in zip(va, vb) if x is not None and y is not None]
        ctx_changed = sum(
            1 for i in ids
            if next(x["chunk_ids"] for x in rows if x["index"] == "tas_v6" and x["suite"] == suite and x["id"] == i)
            != next(x["chunk_ids"] for x in rows if x["index"] == "tas_v6_tablefix" and x["suite"] == suite and x["id"] == i)
        )
        summary[suite] = {
            "metric": SETS[suite][1], "n": len(ok),
            "tas_v6": round(100 * sum(x for x, _ in ok) / len(ok), 1),
            "tas_v6_tablefix": round(100 * sum(y for _, y in ok) / len(ok), 1),
            "diff_ci": {k: round(100 * v, 1) if k != "p_le_zero" else round(v, 3) for k, v in harness.paired_bootstrap_diff(va, vb).items()},
            "won": [i for i in ids if a[i] is not None and b[i] is not None and b[i] > a[i]],
            "lost": [i for i in ids if a[i] is not None and b[i] is not None and b[i] < a[i]],
            "contexts_changed": ctx_changed,
        }
    (Path(__file__).parent / "retrieval_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
