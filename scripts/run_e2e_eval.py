#!/usr/bin/env python3
"""End-to-end LLM + RAG evaluation & RAG-X 4-Quadrant diagnostics on the 171-question
official SFAR Antibioprophylaxie benchmark (`tomboulier/antibioprophylaxie-LLM-benchmark`).

Supports single-mode evaluation or `--compare-all` head-to-head comparison:
  1. `zero_shot`   : LLM seul (official benchmark system prompt, zero external evidence)
  2. `c0_naive`    : Naive Fixed-Size BM25 RAG (no table engine, no temporal graph)
  3. `c8_frontier` : RAG-SFAR Frontier 2026 (Tri-Canal DBSF+RRF + CRAG + U-Shape + Provence)

Metrics computed:
  - Open (138), MCQ (33), Overall (171), Allergy accuracy (exact `OpenScorer` / `QCMScorer`)
  - Official `SourcingScorer` sourcing rate (`\\b\\d{4}\\b`)
  - RAG-X 4-Quadrant diagnostics (`Q1` Grounded Success, `Q2` Parametric Lucky Guess,
    `Q3` Generator Error, `Q4` Retrieval Failure, `Grounded Accuracy`, `CUE`)
  - Molecule grounding score & hallucination count (`verifier.py`)
  - Prompt token usage & exact reduction vs ~95,000-token Long Context
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import track
from rich.table import Table

from rag_sfar.config import RetrievalConfig, Settings
from rag_sfar.evaluation.ablation import build_standard_ablation_configs
from rag_sfar.evaluation.benchmark_adapter import (
    score_antibioprophylaxie_answer,
    score_sourcing_present,
)
from rag_sfar.evaluation.benchmarks import EvalQuestion, load_antibioprophylaxie_benchmark
from rag_sfar.evaluation.rag_x import compute_rag_x_diagnostics
from rag_sfar.evaluation.retrieval_metrics import _evidence_present
from rag_sfar.generation.client import LocalMlxLLM, OpenAICompatibleLLM, SfarRagEngine
from rag_sfar.retrieval.embedder import build_embedder
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.reranker import build_reranker
from rag_sfar.retrieval.vector_store import LocalVectorStore

os.environ.setdefault("HF_HUB_OFFLINE", "1")
console = Console()

ZERO_SHOT_OPEN_PROMPT = (
    "Tu es un expert en antibioprophylaxie chirurgicale (recommandations SFAR). "
    "Réponds sur UNE SEULE LIGNE uniquement par le nom exact de la molécule ou association "
    "(ex : 'Céfazoline', 'Amoxicilline/Clavulanate', 'Clindamycine + Gentamicine'), "
    "ou 'Pas d'antibioprophylaxie', ou 'Hors périmètre'. Aucune explication."
)
ZERO_SHOT_MCQ_PROMPT = (
    "Tu es un expert en antibioprophylaxie chirurgicale (recommandations SFAR). "
    "Réponds uniquement par la lettre exacte (A, B, C ou D). Aucune explication."
)


def _evaluate_zero_shot(
    llm: OpenAICompatibleLLM,
    questions: list[EvalQuestion],
    label: str = "zero_shot",
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    open_ok = open_n = mcq_ok = mcq_n = allergy_ok = allergy_n = 0
    sourcing_ok = 0
    total_prompt_tokens = 0
    t_start = time.perf_counter()

    for q in track(questions, description=f"[{label}] {llm.model}"):
        t0 = time.perf_counter()
        prompt = q.formatted_query()
        sys_p = ZERO_SHOT_MCQ_PROMPT if q.question_type == "mcq" else ZERO_SHOT_OPEN_PROMPT
        ans, usage = llm.complete(sys_p, prompt)
        lat_ms = round((time.perf_counter() - t0) * 1000, 1)
        ok = score_antibioprophylaxie_answer(q.question_type, q.expected_answer, ans)
        src = score_sourcing_present(ans)
        if q.question_type == "mcq":
            mcq_n += 1
            mcq_ok += int(ok)
        else:
            open_n += 1
            open_ok += int(ok)
        if q.is_allergy_question:
            allergy_n += 1
            allergy_ok += int(ok)
        sourcing_ok += int(src)
        total_prompt_tokens += usage.get("prompt_tokens", 0)
        rows.append(
            {
                "id": q.id,
                "title": q.title,
                "type": q.question_type,
                "expected": q.expected_answer,
                "actual": ans,
                "is_correct": ok,
                "sourcing_present": src,
                # Zero-shot has zero retrieved evidence -> any correct answer is Q2 parametric memory
                "evidence_present": False,
                "is_allergy": q.is_allergy_question,
                "grounding_score": 0.0,
                "hallucinated_molecules": [],
                "latency_ms": lat_ms,
                "token_usage": usage,
                "top_source": "",
            }
        )

    return _summarize_run(
        name=label,
        model=llm.model,
        index_dir="none",
        rows=rows,
        open_ok=open_ok,
        open_n=open_n,
        mcq_ok=mcq_ok,
        mcq_n=mcq_n,
        allergy_ok=allergy_ok,
        allergy_n=allergy_n,
        sourcing_ok=sourcing_ok,
        total_prompt_tokens=total_prompt_tokens,
        elapsed_s=time.perf_counter() - t_start,
    )


def _evaluate_rag(
    engine: SfarRagEngine,
    config: RetrievalConfig,
    questions: list[EvalQuestion],
    label: str,
    index_dir: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    open_ok = open_n = mcq_ok = mcq_n = allergy_ok = allergy_n = 0
    sourcing_ok = 0
    total_prompt_tokens = 0
    t_start = time.perf_counter()

    for q in track(questions, description=f"[{label}] {engine.llm.model}"):
        mode = "benchmark_mcq" if q.question_type == "mcq" else "benchmark_open"
        full_q = q.formatted_query()
        resp = engine.answer(query=full_q, mode=mode, config=config)
        ok = score_antibioprophylaxie_answer(q.question_type, q.expected_answer, resp.answer)
        src = score_sourcing_present(resp.answer)
        if q.question_type == "mcq":
            mcq_n += 1
            mcq_ok += int(ok)
        else:
            open_n += 1
            open_ok += int(ok)
        if q.is_allergy_question:
            allergy_n += 1
            allergy_ok += int(ok)
        sourcing_ok += int(src)
        total_prompt_tokens += resp.token_usage.get("prompt_tokens", 0)
        ev_ok = _evidence_present(resp.retrieved_chunks, q.required_evidence_terms)
        # For MCQ (no explicit required_evidence_terms), check if current-edition ABP doc is retrieved
        if ev_ok is None:
            ev_ok = any(
                r.chunk.is_latest_edition and "antibioprophylaxie" in r.chunk.doc_title.lower()
                for r in resp.retrieved_chunks
            )
        rows.append(
            {
                "id": q.id,
                "title": q.title,
                "type": q.question_type,
                "expected": q.expected_answer,
                "actual": resp.answer,
                "is_correct": ok,
                "sourcing_present": src,
                "evidence_present": bool(ev_ok),
                "is_allergy": q.is_allergy_question,
                "grounding_score": resp.verification.grounding_score,
                "hallucinated_molecules": resp.verification.ungrounded_molecules,
                "latency_ms": resp.latency_ms,
                "token_usage": resp.token_usage,
                "top_source": resp.citations[0].doc_title if resp.citations else "",
                "reasoning_trace": resp.extra.get("reasoning_trace", ""),
            }
        )

    return _summarize_run(
        name=label,
        model=engine.llm.model,
        index_dir=index_dir,
        rows=rows,
        open_ok=open_ok,
        open_n=open_n,
        mcq_ok=mcq_ok,
        mcq_n=mcq_n,
        allergy_ok=allergy_ok,
        allergy_n=allergy_n,
        sourcing_ok=sourcing_ok,
        total_prompt_tokens=total_prompt_tokens,
        elapsed_s=time.perf_counter() - t_start,
    )


def _summarize_run(
    name: str,
    model: str,
    index_dir: str,
    rows: list[dict[str, Any]],
    open_ok: int,
    open_n: int,
    mcq_ok: int,
    mcq_n: int,
    allergy_ok: int,
    allergy_n: int,
    sourcing_ok: int,
    total_prompt_tokens: int,
    elapsed_s: float,
) -> dict[str, Any]:
    total_ok = open_ok + mcq_ok
    total_n = len(rows)
    rag_x = compute_rag_x_diagnostics(rows)
    mean_grounding = sum(r["grounding_score"] for r in rows) / max(1, total_n)
    halluc_q = sum(1 for r in rows if r["hallucinated_molecules"])
    avg_prompt_tok = total_prompt_tokens / max(1, total_n)
    return {
        "system": name,
        "model": model,
        "index_dir": index_dir,
        "total_questions": total_n,
        "overall_accuracy": round(total_ok / max(1, total_n), 4),
        "open_accuracy": round(open_ok / max(1, open_n), 4) if open_n else None,
        "open_counts": f"{open_ok}/{open_n}",
        "mcq_accuracy": round(mcq_ok / max(1, mcq_n), 4) if mcq_n else None,
        "mcq_counts": f"{mcq_ok}/{mcq_n}",
        "allergy_accuracy": round(allergy_ok / max(1, allergy_n), 4) if allergy_n else None,
        "allergy_counts": f"{allergy_ok}/{allergy_n}",
        "sourcing_rate": round(sourcing_ok / max(1, total_n), 4),
        "mean_grounding_score": round(mean_grounding, 4),
        "hallucinated_molecule_queries": halluc_q,
        "rag_x_diagnostics": rag_x.to_dict(),
        "avg_prompt_tokens": round(avg_prompt_tok, 1),
        "tokens_vs_long_context_pct": round((1.0 - avg_prompt_tok / 95000.0) * 100.0, 2) if avg_prompt_tok > 0 else None,
        "elapsed_seconds": round(elapsed_s, 2),
        "errors": [r for r in rows if not r["is_correct"]],
        "results": rows,
    }


def _format_comparison_markdown(summaries: list[dict[str, Any]]) -> str:
    lines = [
        "# RAG-SFAR — Évaluation End-to-End & Diagnostic RAG-X (4 Quadrants)\n",
        f"- **Modèle LLM** : `{summaries[0]['model']}` (`temperature = 0.0`)",
        f"- **Questions évaluées** : `{summaries[0]['total_questions']}` (Antibioprophylaxie SFAR — `OpenScorer` + `QCMScorer` + `SourcingScorer` officiels)\n",
        "| Système | Overall Acc. | Open Acc. | MCQ Acc. | Allergie Acc. | Sourcing | Q1 Succès Sourcé (Grounded Acc.) | Q2 Coup de Chance | Q3 Err. LLM | Q4 Err. Retr. | CUE | ~Prompt Tok |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        rx = s["rag_x_diagnostics"]
        lines.append(
            f"| **`{s['system']}`** "
            f"| **{s['overall_accuracy']*100:.1f}%** "
            f"| {s['open_accuracy']*100:.1f}% ({s['open_counts']}) "
            f"| {(s['mcq_accuracy'] or 0)*100:.1f}% ({s['mcq_counts']}) "
            f"| {(s['allergy_accuracy'] or 0)*100:.1f}% ({s['allergy_counts']}) "
            f"| {s['sourcing_rate']*100:.1f}% "
            f"| **{rx['q1_grounded_success']} ({rx['grounded_accuracy']*100:.1f}%)** "
            f"| {rx['q2_lucky_guess']} "
            f"| {rx['q3_generator_error']} "
            f"| {rx['q4_retrieval_failure']} "
            f"| {rx['context_utilization_efficiency']*100:.1f}% "
            f"| {s['avg_prompt_tokens']:.0f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    s = Settings()
    parser = argparse.ArgumentParser(description="Run E2E LLM+RAG evaluation & RAG-X diagnostics on 171 ABP questions.")
    parser.add_argument("--index-root", type=Path, default=Path("index"))
    parser.add_argument("--index-dir", type=Path, default=Path("index/table_aware_sota"))
    parser.add_argument("--benchmark-path", type=Path, default=s.benchmark_path)
    parser.add_argument("--backend", choices=["openai", "mlx"], default="openai")
    parser.add_argument("--base-url", default=s.llm_base_url)
    parser.add_argument("--api-key", default=s.llm_api_key)
    parser.add_argument("--model", default=s.llm_model)
    parser.add_argument("--mlx-model-path", default="", help="Local MLX model path or HF repo ID when --backend mlx.")
    parser.add_argument(
        "--mode",
        choices=["c8_frontier", "c6_fast", "c0_naive", "zero_shot", "compare_all"],
        default="c8_frontier",
        help="Single evaluation mode or `compare_all` (Zero-Shot vs C0 Naïf vs C8 Frontier).",
    )
    parser.add_argument(
        "--modes",
        default="",
        help="Optional comma-separated modes override (e.g. 'zero_shot,c8_frontier').",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit to first N questions (0 = all 171).")
    parser.add_argument(
        "--stratified",
        type=int,
        default=0,
        help="Optional deterministic stratified sample size (keeps all allergy questions + proportional open/MCQ).",
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        default=None,
        help="Optional JSON list of question IDs to evaluate (exact re-run of a previous sample).",
    )
    parser.add_argument("--max-tokens", type=int, default=48)
    parser.add_argument("--output", type=Path, default=Path("reports/e2e_eval.json"))
    parser.add_argument("--md-output", type=Path, default=Path("reports/e2e_comparison_report.md"))
    args = parser.parse_args()

    questions = load_antibioprophylaxie_benchmark(args.benchmark_path)
    if args.ids_file is not None:
        wanted = json.loads(args.ids_file.read_text(encoding="utf-8"))
        by_id = {q.id: q for q in questions}
        missing = [i for i in wanted if i not in by_id]
        if missing:
            raise SystemExit(f"Unknown question IDs in {args.ids_file}: {missing}")
        questions = [by_id[i] for i in wanted]
    elif args.stratified > 0 and args.stratified < len(questions):
        allergy_qs = [q for q in questions if q.is_allergy_question]
        mcq_qs = [q for q in questions if q.question_type == "mcq" and not q.is_allergy_question]
        open_qs = [q for q in questions if q.question_type == "open" and not q.is_allergy_question]
        rem = max(0, args.stratified - len(allergy_qs))
        n_mcq = min(len(mcq_qs), max(1, round(rem * len(mcq_qs) / max(1, len(mcq_qs) + len(open_qs)))))
        n_open = min(len(open_qs), rem - n_mcq)
        step_m = max(1, len(mcq_qs) // max(1, n_mcq))
        step_o = max(1, len(open_qs) // max(1, n_open))
        picked_ids = (
            {q.id for q in allergy_qs}
            | {q.id for q in mcq_qs[::step_m][:n_mcq]}
            | {q.id for q in open_qs[::step_o][:n_open]}
        )
        questions = [q for q in questions if q.id in picked_ids]
    elif args.limit > 0:
        questions = questions[: args.limit]

    if args.backend == "mlx":
        llm: Any = LocalMlxLLM(
            model_path=args.mlx_model_path or args.model,
            model_label=args.model,
            temperature=0.0,
            max_tokens=args.max_tokens,
        )
    else:
        llm = OpenAICompatibleLLM(
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            temperature=0.0,
            max_tokens=args.max_tokens,
        )

    cfgs = {c.name: c for c in build_standard_ablation_configs()}
    if args.modes:
        modes_to_run = [m.strip() for m in args.modes.split(",") if m.strip()]
    else:
        modes_to_run = ["zero_shot", "c0_naive", "c8_frontier"] if args.mode == "compare_all" else [args.mode]
    summaries: list[dict[str, Any]] = []

    torch_device = "cpu" if args.backend == "mlx" else None
    for m in modes_to_run:
        if m == "zero_shot":
            summaries.append(_evaluate_zero_shot(llm, questions, label="Zero-Shot (LLM seul)"))
        elif m == "c0_naive":
            naive_dir = args.index_root / "naive_fixed"
            store = LocalVectorStore.load(naive_dir)
            retriever = SfarRagRetriever(store=store, embedder=None, reranker=None)
            engine = SfarRagEngine(retriever=retriever, llm=llm, default_config=cfgs["C0_naive_fixed_bm25"])
            summaries.append(
                _evaluate_rag(engine, cfgs["C0_naive_fixed_bm25"], questions, label="C0 RAG Naïf", index_dir=str(naive_dir))
            )
        elif m == "c6_fast":
            store = LocalVectorStore.load(args.index_dir)
            embedder = build_embedder(
                provider=store.manifest.get("embedding_provider", s.embedding_provider),
                model_name=store.manifest.get("embedding_model", s.embedding_model),
                index_dir=args.index_dir,
                device=torch_device,
            )
            retriever = SfarRagRetriever(store=store, embedder=embedder, reranker=None)
            cfg = cfgs["C6_hybrid_temporal_metadata"]
            engine = SfarRagEngine(retriever=retriever, llm=llm, default_config=cfg)
            summaries.append(
                _evaluate_rag(engine, cfg, questions, label="C6 Hybrid Fast", index_dir=str(args.index_dir))
            )
        else:
            store = LocalVectorStore.load(args.index_dir)
            embedder = (
                build_embedder(
                    provider=store.manifest.get("embedding_provider", s.embedding_provider),
                    model_name=store.manifest.get("embedding_model", s.embedding_model),
                    index_dir=args.index_dir,
                    device=torch_device,
                )
                if store.embeddings is not None
                else None
            )
            reranker = (
                build_reranker(s.reranker_provider, s.reranker_model, device=torch_device)
                if s.reranker_provider != "none"
                else None
            )
            retriever = SfarRagRetriever(store=store, embedder=embedder, reranker=reranker)
            cfg = cfgs["C8_frontier_2026_tri_dbsf_crag"]
            engine = SfarRagEngine(retriever=retriever, llm=llm, default_config=cfg)
            summaries.append(
                _evaluate_rag(engine, cfg, questions, label="C8 RAG-SFAR Frontier 2026", index_dir=str(args.index_dir))
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload: Any = summaries[0] if len(summaries) == 1 else {"runs": summaries}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md = _format_comparison_markdown(summaries)
    args.md_output.parent.mkdir(parents=True, exist_ok=True)
    args.md_output.write_text(md, encoding="utf-8")

    tbl = Table(title=f"End-to-End & RAG-X Results — {args.model}")
    for col in ["System", "Overall", "Open", "MCQ", "Allergy", "Sourcing", "Q1 Grounded", "Q2 Lucky", "Q3 LLM", "Q4 Retr", "CUE", "~Tok"]:
        tbl.add_column(col)
    for r in summaries:
        rx = r["rag_x_diagnostics"]
        tbl.add_row(
            r["system"],
            f"{r['overall_accuracy']*100:.1f}%",
            f"{r['open_accuracy']*100:.1f}%",
            f"{(r['mcq_accuracy'] or 0)*100:.1f}%",
            f"{(r['allergy_accuracy'] or 0)*100:.1f}%",
            f"{r['sourcing_rate']*100:.1f}%",
            f"{rx['q1_grounded_success']} ({rx['grounded_accuracy']*100:.1f}%)",
            str(rx["q2_lucky_guess"]),
            str(rx["q3_generator_error"]),
            str(rx["q4_retrieval_failure"]),
            f"{rx['context_utilization_efficiency']*100:.1f}%",
            f"{r['avg_prompt_tokens']:.0f}",
        )
    console.print(tbl)
    console.print(f"Saved JSON -> {args.output} | Markdown -> {args.md_output}")


if __name__ == "__main__":
    main()
