"""Subword Character N-Gram TF-IDF channel (3–5 char n-grams) for French medical morphology
and OCR typo resilience (e.g. `colectomie`<->`colique`, `morsure`<->`mordu`, `cefuoxime`<->`cefuroxime`)."""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from rag_sfar.retrieval.medical_lexicon import fold_accents


class CharNgramIndex:
    """Sparse L2-normalized character n-gram (3..5) retriever.

    Complements word-level BM25+ and semantic dense vectors by capturing French clinical
    derivations, compound drug stems, and OCR character glitches in <3 ms on 30k chunks.
    """

    def __init__(self, max_features: int = 120000) -> None:
        self.max_features = max_features
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=2,
            max_df=0.85,
            max_features=max_features,
            sublinear_tf=True,
            dtype=np.float32,
        )
        self.matrix: sparse.csr_matrix | None = None
        self._csc: sparse.csc_matrix | None = None

    def build(self, texts: list[str]) -> "CharNgramIndex":
        if not texts:
            self.matrix = None
            self._csc = None
            return self
        self.vectorizer.set_params(min_df=1 if len(texts) < 25 else 2, max_df=1.0 if len(texts) < 10 else 0.85)
        folded = [fold_accents(t.lower()) for t in texts]
        self.matrix = self.vectorizer.fit_transform(folded).tocsr()
        self._csc = self.matrix.tocsc()
        return self

    def search(
        self,
        query: str,
        top_k: int = 45,
        allowed_mask: np.ndarray | None = None,
    ) -> list[tuple[int, float]]:
        if self.matrix is None or self.matrix.shape[0] == 0:
            return []
        if self._csc is None:
            self._csc = self.matrix.tocsc()
        q_vec = self.vectorizer.transform([fold_accents(query.lower())])
        if q_vec.nnz == 0:
            return []
        # Fast inverted-column accumulation over CSC (touches only active query n-gram columns)
        scores = np.zeros(self.matrix.shape[0], dtype=np.float32)
        indptr = self._csc.indptr
        indices = self._csc.indices
        data = self._csc.data
        for col, weight in zip(q_vec.indices, q_vec.data):
            start = indptr[col]
            end = indptr[col + 1]
            if start < end:
                scores[indices[start:end]] += data[start:end] * weight
        if allowed_mask is not None:
            scores = np.where(allowed_mask, scores, -1.0)
        valid = int(np.sum(scores > 0))
        if valid == 0:
            return []
        k = min(top_k, valid)
        top_idx = np.argpartition(scores, -k)[-k:]
        top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]
        return [(int(i), float(scores[i])) for i in top_idx if scores[i] > 0]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(
                {"max_features": self.max_features, "vectorizer": self.vectorizer, "matrix": self.matrix},
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    @classmethod
    def load(cls, path: Path) -> "CharNgramIndex | None":
        if not path.exists():
            return None
        with path.open("rb") as f:
            state = pickle.load(f)
        obj = cls(max_features=state["max_features"])
        obj.vectorizer = state["vectorizer"]
        obj.matrix = state["matrix"]
        obj._csc = obj.matrix.tocsc() if obj.matrix is not None else None
        return obj
