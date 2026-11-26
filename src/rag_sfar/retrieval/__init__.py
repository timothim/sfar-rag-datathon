"""Hybrid retrieval, reranking, routing, and context-building components."""

from rag_sfar.retrieval.bm25 import BM25Index
from rag_sfar.retrieval.embedder import (
    BaseEmbedder,
    OpenAICompatibleEmbedder,
    SentenceTransformerEmbedder,
    TfidfSvdEmbedder,
    build_embedder,
)
from rag_sfar.retrieval.medical_lexicon import expand_medical_query, tokenize_medical_french
from rag_sfar.retrieval.pipeline import SfarRagRetriever, format_context_for_llm
from rag_sfar.retrieval.reranker import BaseReranker, CrossEncoderReranker, NoOpReranker, build_reranker
from rag_sfar.retrieval.router import analyze_query
from rag_sfar.retrieval.vector_store import LocalVectorStore, PgVectorStore

__all__ = [
    "BM25Index",
    "BaseEmbedder",
    "BaseReranker",
    "CrossEncoderReranker",
    "LocalVectorStore",
    "NoOpReranker",
    "OpenAICompatibleEmbedder",
    "PgVectorStore",
    "SentenceTransformerEmbedder",
    "SfarRagRetriever",
    "TfidfSvdEmbedder",
    "analyze_query",
    "build_embedder",
    "build_reranker",
    "expand_medical_query",
    "format_context_for_llm",
    "tokenize_medical_french",
]
