"""RAG-X Component-Level Diagnostic Framework (arXiv 2026).

Unmasks the "Accuracy Fallacy" in medical RAG by partitioning end-to-end outcomes into
4 explicit safety quadrants:
  - Q1 (Grounded Success): Evidence retrieved AND answer correct (ONLY true clinical win!)
  - Q2 (Lucky Guess / Parametric Leakage): Evidence MISSING yet answer correct (unsafe!)
  - Q3 (Generator Reading Error): Evidence retrieved yet answer WRONG (prompt/LLM issue)
  - Q4 (Retrieval Failure): Evidence MISSING and answer WRONG (retrieval/chunking issue)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RagXDiagnostics:
    total: int
    q1_grounded_success: int
    q2_lucky_guess: int
    q3_generator_error: int
    q4_retrieval_failure: int

    @property
    def raw_accuracy(self) -> float:
        return round((self.q1_grounded_success + self.q2_lucky_guess) / max(1, self.total), 4)

    @property
    def grounded_accuracy(self) -> float:
        """True clinical accuracy: correct AND backed by retrieved guideline evidence."""
        return round(self.q1_grounded_success / max(1, self.total), 4)

    @property
    def accuracy_fallacy_gap(self) -> float:
        """Portion of apparent accuracy caused by ungrounded parametric guessing."""
        return round(self.q2_lucky_guess / max(1, self.total), 4)

    @property
    def context_utilization_efficiency(self) -> float:
        """CUE = P(Correct | Evidence Retrieved): isolates generator comprehension."""
        ev_present = self.q1_grounded_success + self.q3_generator_error
        return round(self.q1_grounded_success / max(1, ev_present), 4) if ev_present else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "q1_grounded_success": self.q1_grounded_success,
            "q2_lucky_guess": self.q2_lucky_guess,
            "q3_generator_error": self.q3_generator_error,
            "q4_retrieval_failure": self.q4_retrieval_failure,
            "raw_accuracy": self.raw_accuracy,
            "grounded_accuracy": self.grounded_accuracy,
            "accuracy_fallacy_gap": self.accuracy_fallacy_gap,
            "context_utilization_efficiency": self.context_utilization_efficiency,
        }


def compute_rag_x_diagnostics(records: list[dict[str, Any]]) -> RagXDiagnostics:
    """Compute RAG-X 4-quadrant breakdown from per-question evaluation records
    containing boolean fields `evidence_present` and `is_correct`."""
    q1 = q2 = q3 = q4 = 0
    for r in records:
        ev = bool(r.get("evidence_present"))
        ok = bool(r.get("is_correct"))
        if ev and ok:
            q1 += 1
        elif (not ev) and ok:
            q2 += 1
        elif ev and (not ok):
            q3 += 1
        else:
            q4 += 1
    return RagXDiagnostics(
        total=len(records),
        q1_grounded_success=q1,
        q2_lucky_guess=q2,
        q3_generator_error=q3,
        q4_retrieval_failure=q4,
    )
