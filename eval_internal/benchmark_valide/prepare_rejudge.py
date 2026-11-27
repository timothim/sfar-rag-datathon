"""V1: re-judging of the final-evaluation answers under the validated grids (sfar-abp-v31.1-valide).

    .venv/bin/python eval_internal/benchmark_valide/prepare_rejudge.py          # derived reports only
    HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.judge_io export-blind --run blind_v31grid \
        --reports eval_internal/work/v1/reports/*.json

Derived copies (git-ignored, eval_internal/work/v1/reports/) of the three abpe171 reports of the final
evaluation (dev iter 30, dev confirm 72, test 69), restricted to the 37 ids whose grid the physician
revised, with `suite = abpv171` so that `judge_io` loads the validated grid (mandatory / forbidden
claims, expected and acceptable behaviours, reference); the answers, retrieval rows and `replay`
metadata are copied unchanged (same cited excerpts). The test part is `split = test_posthoc`
(eval/splits/abpv171/test_posthoc.jsonl, ids of the abpe171 test): post hoc scoring of fixed
answers. The original reports are not modified. For the 134 unchanged ids the grid is identical and
the blind_final verdicts stand.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = [
    "reports/eval/b3/20261127-080147_abpe171_dev_b3_v6_c10n_iter_claude-sonnet-5-5.json",
    "reports/eval/b3/20261127-081059_abpe171_dev_b3_v6_c10n_confirm_claude-sonnet-5-5.json",
    "reports/eval/b3/20261127-084611_abpe171_test_b3_v6_c10n_test_claude-sonnet-5-5.json",
]
OUT = ROOT / "eval_internal/work/v1/reports"


def main() -> None:
    changed = set(json.loads((ROOT / "eval_internal/benchmark_valide/diff_ids.json").read_text())["ids"]["manifest_clinical"])
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for rel in SRC:
        rep = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        assert rep["suite"] == "abpe171" and len(rep["runs"]) == 1
        rep["derived_from"] = rel
        rep["suite"] = "abpv171"
        rep["split"] = "test_posthoc" if rep["split"] == "test" else rep["split"]
        for run in rep["runs"]:
            # row suite kept (abpe171): it keys the replay prompts, hence the cited excerpts
            run["rows"] = [r for r in run["rows"] if r["id"] in changed]
            total += len(run["rows"])
        rep["n_items"] = len(rep["runs"][0]["rows"])
        name = Path(rel).name.replace("abpe171", "abpv171").replace(".json", "_v31grid.json")
        (OUT / name).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, rep["split"], rep["n_items"])
    print("total rows", total)


if __name__ == "__main__":
    main()
