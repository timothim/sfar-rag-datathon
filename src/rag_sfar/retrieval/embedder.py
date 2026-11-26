"""Pluggable multilingual embedding engines (SentenceTransformers, OpenAI/Ollama/vLLM, TF-IDF SVD)."""

from __future__ import annotations

import abc
import pickle
from pathlib import Path

import numpy as np


class BaseEmbedder(abc.ABC):
    """Unified interface for document and query embeddings (L2-normalized float32)."""

    model_name: str
    dim: int

    @abc.abstractmethod
    def embed_documents(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """Return `(N, D)` L2-normalized float32 embedding matrix for corpus chunks."""

    @abc.abstractmethod
    def embed_query(self, query: str) -> np.ndarray:
        """Return `(D,)` L2-normalized float32 vector for a query."""

    def save_state(self, directory: Path) -> None:
        """Optional hook for stateful embedders (e.g. TF-IDF SVD)."""

    @classmethod
    def load_state(cls, directory: Path) -> "BaseEmbedder | None":
        return None


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=-1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (mat / norms).astype(np.float32)


class SentenceTransformerEmbedder(BaseEmbedder):
    """Local neural embedder via sentence-transformers (MPS / CUDA / CPU).

    Automatically applies E5 asymmetric prefixes (`query: ` / `passage: `) when using
    `intfloat/multilingual-e5-*` models, and uses native normalized embeddings for BGE-M3.
    """

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small", device: str | None = None) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self.model_name = model_name
        self.device = device
        self._is_e5 = "e5" in model_name.lower()
        try:
            self._model = SentenceTransformer(model_name, device=device, local_files_only=True)
        except Exception:
            self._model = SentenceTransformer(model_name, device=device)
        dim_fn = getattr(
            self._model, "get_embedding_dimension", self._model.get_sentence_embedding_dimension
        )
        self.dim = int(dim_fn())
        # Instruction-tuned embedders (Qwen3-Embedding, EmbeddingGemma...) ship their own
        # query/document prompts in the sentence-transformers config: use them when present.
        prompts = getattr(self._model, "prompts", None) or {}
        self._query_prompt = "query" if "query" in prompts and not self._is_e5 else None
        self._doc_prompt = next((n for n in ("document", "passage") if n in prompts), None) if not self._is_e5 else None
        # Cap sequence length: long-context embedders default to 8k-32k tokens, far beyond our chunks.
        if getattr(self._model, "max_seq_length", 512) and self._model.max_seq_length > 1024:
            self._model.max_seq_length = 1024

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        prefixed = [f"passage: {t}" for t in texts] if self._is_e5 else texts
        vecs = self._model.encode(
            prefixed,
            prompt_name=self._doc_prompt,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 200,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return np.asarray(vecs, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        text = f"query: {query}" if self._is_e5 else query
        vec = self._model.encode(
            [text],
            prompt_name=self._query_prompt,
            batch_size=1,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0]
        return np.asarray(vec, dtype=np.float32)


class OpenAICompatibleEmbedder(BaseEmbedder):
    """API embedder compatible with LibreDataHub Ollama, vLLM, OpenAI, and Mistral."""

    def __init__(
        self,
        model_name: str,
        base_url: str,
        api_key: str = "ollama",
    ) -> None:
        from openai import OpenAI

        self.model_name = model_name
        self._is_e5 = "e5" in model_name.lower()
        self._client = OpenAI(base_url=base_url, api_key=api_key or "none")
        # Probe dimension lazily on first call
        self.dim = 0

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        prefixed = [f"passage: {t}" for t in texts] if self._is_e5 else texts
        all_vecs: list[list[float]] = []
        for i in range(0, len(prefixed), batch_size):
            batch = [t[:8000] for t in prefixed[i : i + batch_size]]
            resp = self._client.embeddings.create(model=self.model_name, input=batch)
            for item in resp.data:
                all_vecs.append(item.embedding)
        mat = _l2_normalize(np.asarray(all_vecs, dtype=np.float32))
        self.dim = mat.shape[1]
        return mat

    def embed_query(self, query: str) -> np.ndarray:
        text = f"query: {query}" if self._is_e5 else query
        resp = self._client.embeddings.create(model=self.model_name, input=[text[:8000]])
        vec = np.asarray(resp.data[0].embedding, dtype=np.float32)
        self.dim = len(vec)
        return _l2_normalize(vec)


class TfidfSvdEmbedder(BaseEmbedder):
    """Fast, deterministic offline latent-semantic embedder (word + char n-grams + TruncatedSVD).

    Provides an instant zero-download fallback for unit tests and offline environments.
    """

    def __init__(self, n_components: int = 384) -> None:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.model_name = f"tfidf_svd_{n_components}"
        self.dim = n_components
        self._vectorizer = TfidfVectorizer(
            max_features=40000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            strip_accents="unicode",
        )
        self._svd = TruncatedSVD(n_components=n_components, random_state=42)
        self._fitted = False

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        tfidf = self._vectorizer.fit_transform(texts)
        max_comp = min(self.dim, tfidf.shape[0] - 1, tfidf.shape[1] - 1)
        if max_comp < 2:
            arr = tfidf.toarray().astype(np.float32)
            self.dim = arr.shape[1]
            self._fitted = True
            return _l2_normalize(arr)
        if max_comp != self._svd.n_components:
            from sklearn.decomposition import TruncatedSVD

            self._svd = TruncatedSVD(n_components=max_comp, random_state=42)
            self.dim = max_comp
        dense = self._svd.fit_transform(tfidf).astype(np.float32)
        self._fitted = True
        return _l2_normalize(dense)

    def embed_query(self, query: str) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("TfidfSvdEmbedder must be fitted via embed_documents() or loaded first.")
        tfidf = self._vectorizer.transform([query])
        if hasattr(self._svd, "components_"):
            vec = self._svd.transform(tfidf)[0].astype(np.float32)
        else:
            vec = tfidf.toarray()[0].astype(np.float32)
        return _l2_normalize(vec)

    def save_state(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "tfidf_svd_embedder.pkl").open("wb") as f:
            pickle.dump(
                {
                    "dim": self.dim,
                    "vectorizer": self._vectorizer,
                    "svd": self._svd,
                    "fitted": self._fitted,
                },
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    @classmethod
    def load_state(cls, directory: Path) -> "TfidfSvdEmbedder | None":
        p = directory / "tfidf_svd_embedder.pkl"
        if not p.exists():
            return None
        with p.open("rb") as f:
            state = pickle.load(f)
        obj = cls(n_components=state["dim"])
        obj._vectorizer = state["vectorizer"]
        obj._svd = state["svd"]
        obj._fitted = state["fitted"]
        return obj


def build_embedder(
    provider: str = "sentence_transformer",
    model_name: str = "intfloat/multilingual-e5-small",
    base_url: str = "",
    api_key: str = "",
    index_dir: Path | None = None,
    device: str | None = None,
) -> BaseEmbedder:
    """Factory creating the requested embedding backend."""
    if provider == "sentence_transformer":
        return SentenceTransformerEmbedder(model_name=model_name, device=device)
    if provider == "openai_compatible":
        return OpenAICompatibleEmbedder(model_name=model_name, base_url=base_url, api_key=api_key)
    if provider == "tfidf_svd":
        if index_dir is not None:
            loaded = TfidfSvdEmbedder.load_state(index_dir)
            if loaded is not None:
                return loaded
        return TfidfSvdEmbedder()
    raise ValueError(f"Unsupported embedding provider: {provider}")
