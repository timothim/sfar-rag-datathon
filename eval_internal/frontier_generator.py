"""Frontier-generator experiment without API: capture the exact prompts our engine sends to the
LLM, have Claude Code subagents answer them, and turn their answers into a standard eval report
(scored by the same harness and the same judge as the local 7B runs).

    # 1. capture prompts (retrieval on CPU; the GPU may be busy)
    .venv/bin/python eval_internal/frontier_generator.py prepare --suite multirfe_synth --variant ctx6
    .venv/bin/python eval_internal/frontier_generator.py prepare --suite multirfe_synth --variant ctx12
    # 2. subagents read work/frontier/<suite>_<variant>/gen_input_*.json and write gen_out_*.json
    # 3. build the report (then judge it with judge_io export/merge)
    .venv/bin/python eval_internal/frontier_generator.py report --suite multirfe_synth --variant ctx6 --model-label claude-sonnet-5-5

Superseded for new experiments by eval_internal/gen_replay.py (any retrieval config / --ablate /
index map / generation preset / prompt mode / id list; `run --backend record --export-frontier DIR`
writes the same gen_input_*.json files, `import-frontier --dir DIR` builds the report). Kept as is to
reproduce the earlier ctx6 / ctx12 runs.

Variants (config C9, prompt mode clinical_concise):
  ctx6  : exactly the context the 7B gets (final_top_k=8, generation selection <= 6 chunks / 6 500 chars)
  ctx12 : wider context (final_top_k=12, no generation-side pruning or selection)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_sfar.config import Settings  # noqa: E402
from rag_sfar.evaluation import harness  # noqa: E402
from rag_sfar.evaluation.datasets import load_suite  # noqa: E402
from rag_sfar.schemas import RetrievedChunk  # noqa: E402

WORK = ROOT / "eval_internal/work/frontier"
MODE = "clinical_concise"


class RecordingLLM:
    """Stands in for the LLM: records the first (system, user) prompt pair of each question."""

    model = "recorder"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str, temperature=None, max_tokens=None):
        self.calls.append((system_prompt, user_prompt))
        return "Les recommandations SFAR fournies ne traitent pas cette question.", {}


def _config(variant: str):
    base = harness.select_configs("C9")[0]
    if variant == "ctx6":
        return base
    if variant == "ctx12":
        return dataclasses.replace(base, name=base.name + "-ctx12", final_top_k=12, use_context_pruning=False)
    raise SystemExit(f"unknown variant {variant}")


def prepare(suite: str, variant: str, parts: int) -> None:
    from rag_sfar.generation.client import SfarRagEngine

    s = Settings()
    cfg = _config(variant)
    retriever = harness.load_retrievers(ROOT / "index", [cfg.chunking_strategy], s.reranker_provider, s.reranker_model, device="cpu")[cfg.chunking_strategy]
    rec = RecordingLLM()
    engine = SfarRagEngine(retriever=retriever, llm=rec)
    items = load_suite(suite, "dev")
    cases, rows = [], []
    for it in items:
        mode = "benchmark_mcq" if it.question_type == "mcq" else MODE
        n0 = len(rec.calls)
        resp = engine.answer(it.formatted_query(), mode=mode, config=cfg)
        system, user = rec.calls[n0]
        cases.append({"case_id": it.id, "system": system, "user": user})
        rows.append({"id": it.id, "retrieved": [rc.model_dump() for rc in resp.retrieved_chunks]})
    out = WORK / f"{suite}_{variant}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "retrieval_rows.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    size = -(-len(cases) // parts)
    for i in range(parts):
        (out / f"gen_input_{i}.json").write_text(json.dumps(cases[i * size : (i + 1) * size], ensure_ascii=False, indent=1), encoding="utf-8")
    avg = sum(len(c["user"]) for c in cases) / max(1, len(cases))
    print(f"{len(cases)} prompts ({parts} batches, avg user prompt {avg:.0f} chars) -> {out}")


def report(suite: str, variant: str, model_label: str) -> None:
    out = WORK / f"{suite}_{variant}"
    answers = {}
    for f in sorted(out.glob("gen_out_*.json")):
        for a in json.loads(f.read_text(encoding="utf-8")):
            answers[a["case_id"]] = a["answer"]
    retr = {r["id"]: [RetrievedChunk.model_validate(x) for x in r["retrieved"]] for r in json.loads((out / "retrieval_rows.json").read_text(encoding="utf-8"))}
    items = load_suite(suite, "dev")
    cfg = _config(variant)
    rows = []
    for it in items:
        if it.id not in answers:
            continue
        row = {"id": it.id, "suite": it.suite, "provenance": it.provenance, "question_type": it.question_type, "tags": it.tags}
        row.update(harness.retrieval_metrics(it, retr[it.id], harness.K_DEFAULT))
        row.update(harness.score_answer(it, answers[it.id]))
        row["answer"] = answers[it.id]
        rows.append(row)
    name = f"{cfg.name}+{model_label}"
    rep = {
        "suite": suite, "split": "dev", "k": harness.K_DEFAULT, "n_items": len(rows),
        "generator": f"{model_label} (Claude Code subagent, prompts captured from the engine, variant {variant})",
        "timestamp": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "runs": [{"config": name, "config_params": dataclasses.asdict(cfg), "summary": harness.summarize(rows), "rows": rows}],
        "comparisons": [],
    }
    jp, mp = harness.save_report(rep, tag=f"frontier_{variant}_{model_label.replace('/', '-')}")
    print(f"{len(rows)}/{len(items)} answers -> {jp}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--suite", required=True)
    p.add_argument("--variant", required=True, choices=["ctx6", "ctx12"])
    p.add_argument("--parts", type=int, default=4)
    r = sub.add_parser("report")
    r.add_argument("--suite", required=True)
    r.add_argument("--variant", required=True, choices=["ctx6", "ctx12"])
    r.add_argument("--model-label", required=True)
    a = ap.parse_args()
    prepare(a.suite, a.variant, a.parts) if a.cmd == "prepare" else report(a.suite, a.variant, a.model_label)
