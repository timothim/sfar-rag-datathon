"""Neural Cross-Encoder rerankers (BAAI/bge-reranker-v2-m3, mmarco-mMiniLMv2) and fast fallback."""

from __future__ import annotations

import abc
import math


class BaseReranker(abc.ABC):
    """Unified interface for passage reranking."""

    model_name: str

    @abc.abstractmethod
    def score_pairs(self, query: str, passages: list[str]) -> list[float]:
        """Return relevance scores aligned 1-to-1 with `passages`."""


class CrossEncoderReranker(BaseReranker):
    """Multilingual neural cross-encoder reranker via sentence-transformers (MPS/CUDA/CPU)."""

    def __init__(
        self,
        model_name: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        device: str | None = None,
        max_length: int = 512,
    ) -> None:
        import torch
        from sentence_transformers import CrossEncoder

        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self.model_name = model_name
        self.device = device
        try:
            self._model = CrossEncoder(
                model_name, max_length=max_length, device=device, local_files_only=True
            )
        except Exception:
            self._model = CrossEncoder(model_name, max_length=max_length, device=device)

    def score_pairs(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(query, p[:2400]) for p in passages]
        raw_scores = self._model.predict(pairs, show_progress_bar=False)
        # Apply sigmoid so logits map smoothly into (0, 1) for interpretable UI & fusion
        out: list[float] = []
        for s in raw_scores:
            val = float(s)
            try:
                prob = 1.0 / (1.0 + math.exp(-val))
            except OverflowError:
                prob = 0.0 if val < 0 else 1.0
            out.append(prob)
        return out


class NoOpReranker(BaseReranker):
    """Disabled reranker for ablation studies."""

    model_name = "none"

    def score_pairs(self, query: str, passages: list[str]) -> list[float]:
        return [0.0] * len(passages)


def build_reranker(
    provider: str = "cross_encoder",
    model_name: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
    device: str | None = None,
) -> BaseReranker:
    if provider == "cross_encoder":
        return CrossEncoderReranker(model_name=model_name, device=device)
    if provider == "none":
        return NoOpReranker()
    raise ValueError(f"Unsupported reranker provider: {provider}")
