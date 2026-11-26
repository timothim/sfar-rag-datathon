"""Corpus ingestion, metadata enrichment, HTML table parsing, and chunking."""

from rag_sfar.ingestion.chunker import chunk_corpus, chunk_document
from rag_sfar.ingestion.loader import LoadedDocument, load_sfar_corpus
from rag_sfar.ingestion.table_parser import ParsedTable, parse_html_table

__all__ = [
    "LoadedDocument",
    "ParsedTable",
    "chunk_corpus",
    "chunk_document",
    "load_sfar_corpus",
    "parse_html_table",
]
