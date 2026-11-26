"""Thin wrapper around the Anthropic Message Batches API (-50 % cost) for evaluation jobs.

- Every result's real usage is logged to the cost ledger (`cost_ledger.record_usage`, batch=True).
- Results are cached in a JSONL file keyed by custom_id: re-running a job only submits the
  requests that have no successful cached result, so nothing is paid twice.
- The budget guard runs before submission with a caller-provided estimate.

Credentials come from the environment only (ANTHROPIC_API_KEY exported by the user); this
module never reads .env and never prints or logs the key.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from rag_sfar.evaluation import cost_ledger


def _client():
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set in the environment; export it before running API experiments.")
    return anthropic.Anthropic()


def text_of(message: Any) -> str:
    return next((b.text for b in message.content if getattr(b, "type", "") == "text"), "")


def read_cache(cache_path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["custom_id"]] = rec
    return out


def run_batch(
    requests: list[dict[str, Any]],
    experiment: str,
    cache_path: Path,
    estimated_cost_usd: float,
    approved_by_user: bool = False,
    poll_seconds: int = 30,
    log: Callable[[str], None] = print,
) -> dict[str, dict[str, Any]]:
    """Submit `requests` ([{custom_id, params}]) not already cached; wait; cache and return results.

    Returns {custom_id: {"custom_id", "status", "text", "model", "usage", "stop_reason"}}.
    """
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    cache = read_cache(cache_path)
    todo = [r for r in requests if cache.get(r["custom_id"], {}).get("status") != "succeeded"]
    if not todo:
        log(f"[{experiment}] all {len(requests)} results cached")
        return {r["custom_id"]: cache[r["custom_id"]] for r in requests}

    model = todo[0]["params"]["model"]
    share = estimated_cost_usd * len(todo) / max(1, len(requests))
    cost_ledger.guard_experiment(experiment, model, share, approved_by_user=approved_by_user,
                                 note=f"{len(todo)} batch requests")
    client = _client()
    batch = client.messages.batches.create(
        requests=[Request(custom_id=r["custom_id"], params=MessageCreateParamsNonStreaming(**r["params"])) for r in todo]
    )
    log(f"[{experiment}] batch {batch.id} submitted ({len(todo)} requests)")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    (cache_path.parent / f"{cache_path.stem}.batch_ids.txt").open("a").write(batch.id + "\n")
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        c = batch.request_counts
        log(f"[{experiment}] processing={c.processing} succeeded={c.succeeded} errored={c.errored}")
        time.sleep(poll_seconds)

    total = 0.0
    with cache_path.open("a", encoding="utf-8") as f:
        for res in client.messages.batches.results(batch.id):
            rec: dict[str, Any] = {"custom_id": res.custom_id, "status": res.result.type}
            if res.result.type == "succeeded":
                msg = res.result.message
                usage = msg.usage.model_dump() if hasattr(msg.usage, "model_dump") else dict(msg.usage)
                rec.update(text=text_of(msg), model=msg.model, usage=usage, stop_reason=msg.stop_reason)
                total += cost_ledger.record_usage(experiment, model, msg.usage, batch=True, note=res.custom_id)
            else:
                rec["error"] = str(getattr(res.result, "error", ""))
            cache[res.custom_id] = rec
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(f"[{experiment}] batch done, cost {total:.3f} $ (ledger total {cost_ledger.total_spent():.2f} $)")
    return {r["custom_id"]: cache.get(r["custom_id"], {"status": "missing"}) for r in requests}
