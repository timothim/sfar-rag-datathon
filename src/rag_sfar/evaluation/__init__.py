"""Retrieval & end-to-end clinical benchmark loaders and ablation harness."""

from rag_sfar.evaluation.ablation import build_standard_ablation_configs, run_ablation_suite
from rag_sfar.evaluation.benchmark_adapter import SfarRagApproach, score_antibioprophylaxie_answer
from rag_sfar.evaluation.benchmarks import (
    EvalQuestion,
    load_antibioprophylaxie_benchmark,
    load_multi_rfe_stress_benchmark,
)
from rag_sfar.evaluation.retrieval_metrics import evaluate_retrieval_dataset

__all__ = [
    "EvalQuestion",
    "SfarRagApproach",
    "build_standard_ablation_configs",
    "evaluate_retrieval_dataset",
    "load_antibioprophylaxie_benchmark",
    "load_multi_rfe_stress_benchmark",
    "run_ablation_suite",
    "score_antibioprophylaxie_answer",
]
