"""Fast, serializable BM25+ sparse retriever tuned for French clinical terminology."""

from __future__ import annotations

import collections
import math
import pickle
from pathlib import Path

import numpy as np

from rag_sfar.retrieval.medical_lexicon import tokenize_medical_french


class BM25Index:
    """In-memory inverted-index BM25+ retriever with mask filtering and fast persistence.

    Uses BM25+ (with lower-bounding delta=0.5) which outperforms standard BM25Okapi on
    mixed-length medical chunks (short Row-Group Cards alongside longer prose paragraphs).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.65, delta: float = 0.5) -> None:
        self.k1 = k1
        self.b = b
        self.delta = delta
        self.num_docs: int = 0
        self.avg_dl: float = 0.0
        self.doc_lens: np.ndarray = np.zeros(0, dtype=np.float32)
        self.idf: dict[str, float] = {}
        # Inverted postings: term -> (np.ndarray[int32] doc_ids, np.ndarray[float32] tfs)
        self.postings: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    def build(self, texts: list[str]) -> "BM25Index":
        """Build inverted index from a list of chunk texts."""
        self.num_docs = len(texts)
        if self.num_docs == 0:
            return self

        doc_lens = np.zeros(self.num_docs, dtype=np.float32)
        postings_tmp: dict[str, list[tuple[int, int]]] = collections.defaultdict(list)

        for idx, text in enumerate(texts):
            toks = tokenize_medical_french(text)
            doc_lens[idx] = len(toks)
            if not toks:
                continue
            tf_counts = collections.Counter(toks)
            for term, tf in tf_counts.items():
                postings_tmp[term].append((idx, tf))

        self.doc_lens = doc_lens
        self.avg_dl = float(np.mean(doc_lens)) if self.num_docs > 0 else 1.0
        if self.avg_dl <= 0:
            self.avg_dl = 1.0

        self.idf = {}
        self.postings = {}
        n = float(self.num_docs)
        for term, plist in postings_tmp.items():
            df = len(plist)
            # Lucene/BM25+ smoothed IDF (always positive)
            self.idf[term] = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            d_ids = np.fromiter((p[0] for p in plist), dtype=np.int32, count=df)
            tfs = np.fromiter((p[1] for p in plist), dtype=np.float32, count=df)
            self.postings[term] = (d_ids, tfs)

        return self

    def search(
        self,
        query: str,
        top_k: int = 40,
        allowed_mask: np.ndarray | None = None,
        term_weights: dict[str, float] | None = None,
    ) -> list[tuple[int, float]]:
        """Return top-k `(chunk_idx, score)` pairs sorted by descending BM25+ score.

        `term_weights` optionally scales the contribution of some query tokens (default 1)."""
        if self.num_docs == 0:
            return []
        q_tokens = tokenize_medical_french(query)
        if not q_tokens:
            return []

        scores = np.zeros(self.num_docs, dtype=np.float32)
        k1 = self.k1
        b = self.b
        delta = self.delta
        inv_avg_dl = 1.0 / self.avg_dl

        # Count query term weights slightly sublinearly to avoid over-weighting repeated expansions
        q_counts = collections.Counter(q_tokens)
        for term, q_tf in q_counts.items():
            t_weight = term_weights.get(term, 1.0) if term_weights else 1.0
            posting = self.postings.get(term)
            if posting is None or t_weight <= 0.0:
                continue
            d_ids, tfs = posting
            idf = self.idf[term]
            dl = self.doc_lens[d_ids]
            norm = 1.0 - b + b * (dl * inv_avg_dl)
            tf_comp = ((tfs * (k1 + 1.0)) / (tfs + k1 * norm)) + delta
            q_weight = 1.0 + 0.35 * math.log1p(q_tf - 1) if q_tf > 1 else 1.0
            scores[d_ids] += (idf * q_weight * t_weight) * tf_comp

        if allowed_mask is not None:
            scores = np.where(allowed_mask, scores, -1.0)

        # Fast top-k via argpartition
        valid_count = int(np.sum(scores > 0))
        if valid_count == 0:
            return []
        k = min(top_k, valid_count)
        top_idx = np.argpartition(scores, -k)[-k:]
        top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]
        return [(int(i), float(scores[i])) for i in top_idx if scores[i] > 0]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(
                {
                    "k1": self.k1,
                    "b": self.b,
                    "delta": self.delta,
                    "num_docs": self.num_docs,
                    "avg_dl": self.avg_dl,
                    "doc_lens": self.doc_lens,
                    "idf": self.idf,
                    "postings": self.postings,
                },
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    @classmethod
    def load(cls, path: Path) -> "BM25Index":
        with path.open("rb") as f:
            state = pickle.load(f)
        obj = cls(k1=state["k1"], b=state["b"], delta=state["delta"])
        obj.num_docs = state["num_docs"]
        obj.avg_dl = state["avg_dl"]
        obj.doc_lens = state["doc_lens"]
        obj.idf = state["idf"]
        obj.postings = state["postings"]
        return obj
