"""Summary table of B3 replay reports (reports/eval/b3/*.json, skipping prompt-only 'rec' runs).

    .venv/bin/python eval_internal/b3_table.py [substring ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ["correct", "proxy_correct", "judge_correct", "judge_serious_error", "judge_behavior_ok",
        "abstention_correct", "false_abstention", "sourced", "check_flag", "sufficiency"]


def main(filters: list[str]) -> None:
    rows = []
    for f in sorted((ROOT / "reports/eval/b3").glob("*.json")):
        if "_rec" in f.name or "smoke" in f.name:
            continue
        if filters and not any(x in f.name for x in filters):
            continue
        rep = json.loads(f.read_text(encoding="utf-8"))
        s = rep["runs"][0]["summary"]
        cells = []
        for k in KEYS:
            a = s.get(k)
            cells.append(f"{a['mean'] * 100:5.1f}" if a else "   — ")
        pt = s.get("prompt_tokens", {}).get("mean", 0)
        ct = s.get("completion_tokens", {}).get("mean", 0)
        lat = s.get("latency_ms", {}).get("mean", 0) / 1000
        rows.append(f"{f.stem[:15]} {f.stem.split('_b3_')[-1][:26]:26s} {rep['suite'][:8]:8s} n={rep['n_items']:3d} "
                    + " ".join(cells) + f"  ptok={pt:6.0f} ctok={ct:4.0f} lat={lat:5.1f}s")
    print(" " * 63 + " ".join(f"{k[:5]:>5s}" for k in KEYS))
    print("\n".join(rows))


if __name__ == "__main__":
    main(sys.argv[1:])
