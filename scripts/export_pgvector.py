#!/usr/bin/env python3
"""Export a built LocalVectorStore into LibreDataHub PostgreSQL + pgvector (HNSW + French FTS)."""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from rag_sfar.config import Settings
from rag_sfar.retrieval.vector_store import LocalVectorStore, PgVectorStore

console = Console()


def main() -> None:
    s = Settings()
    parser = argparse.ArgumentParser(description="Export RAG-SFAR index to PostgreSQL + pgvector.")
    parser.add_argument("--index-dir", type=Path, default=Path("index/table_aware_sota"))
    parser.add_argument("--dsn", default=s.pgvector_dsn)
    args = parser.parse_args()

    store = LocalVectorStore.load(args.index_dir)
    if store.embeddings is None:
        raise RuntimeError("Index has no dense embeddings; rebuild without --skip-embeddings.")

    dim = int(store.embeddings.shape[1])
    console.print(f"[cyan]Initializing pgvector schema (dim={dim}) on {args.dsn}...[/cyan]")
    pg = PgVectorStore(dsn=args.dsn, dim=dim)
    pg.init_schema()
    n = pg.upsert_chunks(store.chunks, store.embeddings)
    console.print(f"[bold green]Upserted {n:,} chunks into PostgreSQL + pgvector![/bold green]")


if __name__ == "__main__":
    main()
