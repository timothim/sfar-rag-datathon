"""API cost ledger: every Anthropic API call made by an experiment is logged here.

Rows are appended to `reports/cost_ledger.csv` with the real usage returned by the API
(input, output, cache-write and cache-read tokens), the computed cost and a running total.
Estimates written before an experiment are logged with kind="estimate" and are not counted
in the running total.

Budget rules (see CLAUDE.md): API experiments ~60 $, reserve ~20 $. Any single experiment
estimated above 15 $ needs the user's explicit approval (`guard_experiment`).
"""

from __future__ import annotations

import csv
import datetime as dt
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_LEDGER_PATH = Path("reports/cost_ledger.csv")

# USD per million tokens (Anthropic first-party prices, cached 2026-11-03).
# cache_write = 1.25x input (5-minute TTL); cache_read as published per model.


@dataclass(frozen=True)
class ModelPrice:
    input: float
    output: float
    cache_read: float

    @property
    def cache_write(self) -> float:
        return self.input * 1.25


PRICES: dict[str, ModelPrice] = {
    "claude-fable-5-2": ModelPrice(8.0, 40.0, 0.20),
    "claude-opus-5-5": ModelPrice(4.0, 20.0, 0.20),
    "claude-sonnet-5-5": ModelPrice(2.0, 10.0, 0.10),
    "claude-haiku-5-5": ModelPrice(0.10, 0.50, 0.01),
}

API_EXPERIMENT_BUDGET_USD = 60.0
API_RESERVE_USD = 20.0
SINGLE_EXPERIMENT_APPROVAL_USD = 15.0
ESTIMATE_LOG_THRESHOLD_USD = 5.0

FIELDS = [
    "timestamp",
    "kind",
    "experiment",
    "model",
    "batch",
    "input_tokens",
    "output_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "cost_usd",
    "cumulative_usd",
    "note",
]

_lock = threading.Lock()


def _usage_field(usage: Any, name: str) -> int:
    if usage is None:
        return 0
    val = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
    return int(val or 0)


def compute_cost(model: str, usage: Any, batch: bool = False) -> float:
    """Cost in USD of one API response's `usage` (SDK object or dict)."""
    if model not in PRICES:
        raise KeyError(f"No price for model {model!r}; add it to PRICES before calling the API.")
    p = PRICES[model]
    cost = (
        _usage_field(usage, "input_tokens") * p.input
        + _usage_field(usage, "output_tokens") * p.output
        + _usage_field(usage, "cache_creation_input_tokens") * p.cache_write
        + _usage_field(usage, "cache_read_input_tokens") * p.cache_read
    ) / 1_000_000
    return cost * (0.5 if batch else 1.0)


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def total_spent(path: Path = DEFAULT_LEDGER_PATH) -> float:
    """Sum of actual (non-estimate) costs logged so far."""
    return sum(float(r["cost_usd"]) for r in _read_rows(path) if r["kind"] == "actual")


def spent_by_experiment(path: Path = DEFAULT_LEDGER_PATH) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in _read_rows(path):
        if r["kind"] == "actual":
            out[r["experiment"]] = out.get(r["experiment"], 0.0) + float(r["cost_usd"])
    return out


def _append(row: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)


def record_usage(
    experiment: str,
    model: str,
    usage: Any,
    batch: bool = False,
    note: str = "",
    path: Path = DEFAULT_LEDGER_PATH,
) -> float:
    """Append one actual-usage row and return its cost in USD."""
    cost = compute_cost(model, usage, batch=batch)
    with _lock:
        cumulative = total_spent(path) + cost
        _append(
            {
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "kind": "actual",
                "experiment": experiment,
                "model": model,
                "batch": int(batch),
                "input_tokens": _usage_field(usage, "input_tokens"),
                "output_tokens": _usage_field(usage, "output_tokens"),
                "cache_creation_tokens": _usage_field(usage, "cache_creation_input_tokens"),
                "cache_read_tokens": _usage_field(usage, "cache_read_input_tokens"),
                "cost_usd": f"{cost:.6f}",
                "cumulative_usd": f"{cumulative:.6f}",
                "note": note,
            },
            path,
        )
    return cost


def record_estimate(
    experiment: str,
    model: str,
    estimated_cost_usd: float,
    note: str = "",
    path: Path = DEFAULT_LEDGER_PATH,
) -> None:
    """Log a pre-run estimate (not counted in the running total)."""
    with _lock:
        _append(
            {
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "kind": "estimate",
                "experiment": experiment,
                "model": model,
                "batch": "",
                "input_tokens": "",
                "output_tokens": "",
                "cache_creation_tokens": "",
                "cache_read_tokens": "",
                "cost_usd": f"{estimated_cost_usd:.6f}",
                "cumulative_usd": f"{total_spent(path):.6f}",
                "note": note,
            },
            path,
        )


def estimate_cost(
    model: str,
    n_requests: int,
    input_tokens_per_request: int,
    output_tokens_per_request: int,
    batch: bool = False,
) -> float:
    usage = {
        "input_tokens": n_requests * input_tokens_per_request,
        "output_tokens": n_requests * output_tokens_per_request,
    }
    return compute_cost(model, usage, batch=batch)


class BudgetExceeded(RuntimeError):
    pass


def guard_experiment(
    experiment: str,
    model: str,
    estimated_cost_usd: float,
    approved_by_user: bool = False,
    note: str = "",
    path: Path = DEFAULT_LEDGER_PATH,
) -> None:
    """Enforce the budget rules before launching an API experiment.

    - > 5 $: the estimate is written to the ledger first.
    - > 15 $: refuse unless the user approved this experiment explicitly.
    - Refuse if the experiment would push API spending into the reserve.
    """
    if estimated_cost_usd > SINGLE_EXPERIMENT_APPROVAL_USD and not approved_by_user:
        raise BudgetExceeded(
            f"{experiment}: estimated {estimated_cost_usd:.2f} $ > {SINGLE_EXPERIMENT_APPROVAL_USD} $; "
            "ask the user before running it."
        )
    spent = total_spent(path)
    if spent + estimated_cost_usd > API_EXPERIMENT_BUDGET_USD and not approved_by_user:
        raise BudgetExceeded(
            f"{experiment}: {spent:.2f} $ spent + {estimated_cost_usd:.2f} $ estimated exceeds the "
            f"{API_EXPERIMENT_BUDGET_USD} $ API experiment budget (reserve {API_RESERVE_USD} $ untouched)."
        )
    if estimated_cost_usd > ESTIMATE_LOG_THRESHOLD_USD:
        record_estimate(experiment, model, estimated_cost_usd, note=note, path=path)
