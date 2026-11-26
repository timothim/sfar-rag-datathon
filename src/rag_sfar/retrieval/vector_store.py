"""Vector & metadata stores: LocalVectorStore (SQLite + NumPy) and PgVectorStore (LibreDataHub)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from rag_sfar.retrieval.bm25 import BM25Index
from rag_sfar.retrieval.subword import CharNgramIndex
from rag_sfar.schemas import Chunk, DocumentMetadata


class LocalVectorStore:
    """Zero-dependency, ultra-fast tri-channel hybrid index stored on disk
    (NumPy float32 Dense + BM25+ Word + Char 3-5 N-Gram Subword + SQLite).

    Performs exact cosine similarity via BLAS matrix multiply in <5ms across 30,000+ chunks
    and stores full chunk/document metadata in SQLite for instant browsing, filtering, and
    small-to-big context expansion.
    """

    def __init__(
        self,
        chunks: list[Chunk],
        documents: list[DocumentMetadata],
        embeddings: np.ndarray | None,
        bm25: BM25Index,
        manifest: dict[str, Any] | None = None,
        subword: CharNgramIndex | None = None,
    ) -> None:
        self.chunks = chunks
        self.documents = documents
        self.embeddings = embeddings  # (N, D) L2-normalized float32
        self.bm25 = bm25
        self.subword = subword
        self.manifest = manifest or {}

        # Fast lookup tables
        self.chunk_id_to_idx: dict[str, int] = {c.chunk_id: i for i, c in enumerate(chunks)}
        self.doc_id_to_meta: dict[str, DocumentMetadata] = {d.doc_id: d for d in documents}

        # Precompute fast NumPy boolean masks for instant filtering
        n = len(chunks)
        self.mask_active = np.fromiter((c.is_active for c in chunks), dtype=bool, count=n)
        self.mask_latest = np.fromiter((c.is_latest_edition for c in chunks), dtype=bool, count=n)
        self.mask_non_ref = np.fromiter((not c.is_reference_section for c in chunks), dtype=bool, count=n)
        self.mask_french = np.fromiter((c.language != "en" for c in chunks), dtype=bool, count=n)
        self.years_arr = np.fromiter(
            (c.effective_year if c.effective_year is not None else -1 for c in chunks),
            dtype=np.int32,
            count=n,
        )

    def build_filter_mask(
        self,
        exclude_references: bool = True,
        prefer_french: bool = True,
        latest_edition_only: bool = True,
        exclude_abrogated: bool = True,
        allowed_years: list[int] | None = None,
        required_domains: list[str] | None = None,
        doc_ids: list[str] | None = None,
    ) -> np.ndarray:
        """Compute a boolean mask of eligible chunks in microseconds."""
        mask = np.ones(len(self.chunks), dtype=bool)
        if exclude_abrogated:
            mask &= self.mask_active
        if exclude_references:
            mask &= self.mask_non_ref
        if prefer_french:
            mask &= self.mask_french
        if latest_edition_only:
            mask &= self.mask_latest
        if allowed_years:
            yr_mask = np.isin(self.years_arr, allowed_years)
            if np.any(mask & yr_mask):
                mask &= yr_mask
        if required_domains:
            req_set = {d.lower() for d in required_domains}
            dom_mask = np.fromiter(
                (any(d.lower() in req_set for d in c.domains) for c in self.chunks),
                dtype=bool,
                count=len(self.chunks),
            )
            if np.any(mask & dom_mask):
                mask &= dom_mask
        if doc_ids:
            doc_set = set(doc_ids)
            d_mask = np.fromiter(
                (c.doc_id in doc_set for c in self.chunks),
                dtype=bool,
                count=len(self.chunks),
            )
            mask &= d_mask
        return mask

    def dense_search(
        self,
        query_vec: np.ndarray,
        top_k: int = 40,
        allowed_mask: np.ndarray | None = None,
    ) -> list[tuple[int, float]]:
        """Exact cosine similarity search over normalized float32 embeddings."""
        if self.embeddings is None or len(self.embeddings) == 0:
            return []
        sims = self.embeddings @ query_vec.astype(np.float32)
        if allowed_mask is not None:
            sims = np.where(allowed_mask, sims, -2.0)
        valid = int(np.sum(sims > -1.5))
        if valid == 0:
            return []
        k = min(top_k, valid)
        top_idx = np.argpartition(sims, -k)[-k:]
        top_idx = top_idx[np.argsort(sims[top_idx])[::-1]]
        return [(int(i), float(sims[i])) for i in top_idx if sims[i] > -1.5]

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        idx = self.chunk_id_to_idx.get(chunk_id)
        return self.chunks[idx] if idx is not None else None

    def save(self, directory: Path) -> None:
        """Persist embeddings (.npy), BM25 index (.pkl), manifest (.json), and metadata (SQLite)."""
        directory.mkdir(parents=True, exist_ok=True)
        if self.embeddings is not None:
            np.save(directory / "embeddings.npy", self.embeddings)
        self.bm25.save(directory / "bm25.pkl")
        if self.subword is not None:
            self.subword.save(directory / "subword.pkl")
        (directory / "manifest.json").write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        db_path = directory / "metadata.sqlite"
        if db_path.exists():
            db_path.unlink()
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE documents (
                    doc_id TEXT PRIMARY KEY,
                    title TEXT,
                    effective_year INTEGER,
                    doc_type TEXT,
                    language TEXT,
                    is_latest_edition INTEGER,
                    topic_lineage TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE chunks (
                    idx INTEGER PRIMARY KEY,
                    chunk_id TEXT UNIQUE NOT NULL,
                    doc_id TEXT NOT NULL,
                    chunk_type TEXT,
                    effective_year INTEGER,
                    is_latest_edition INTEGER,
                    is_reference_section INTEGER,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.executemany(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        d.doc_id,
                        d.title,
                        d.effective_year,
                        d.doc_type,
                        d.language,
                        int(d.is_latest_edition),
                        d.topic_lineage,
                        d.model_dump_json(),
                    )
                    for d in self.documents
                ],
            )
            conn.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        i,
                        c.chunk_id,
                        c.doc_id,
                        c.chunk_type,
                        c.effective_year,
                        int(c.is_latest_edition),
                        int(c.is_reference_section),
                        c.model_dump_json(),
                    )
                    for i, c in enumerate(self.chunks)
                ],
            )
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def load(cls, directory: Path) -> "LocalVectorStore":
        """Load persisted hybrid index from directory."""
        db_path = directory / "metadata.sqlite"
        if not db_path.exists():
            raise FileNotFoundError(f"Index not found at {directory}")

        conn = sqlite3.connect(db_path)
        try:
            doc_rows = conn.execute("SELECT payload_json FROM documents").fetchall()
            chunk_rows = conn.execute("SELECT payload_json FROM chunks ORDER BY idx ASC").fetchall()
        finally:
            conn.close()

        documents = [DocumentMetadata.model_validate_json(r[0]) for r in doc_rows]
        chunks = [Chunk.model_validate_json(r[0]) for r in chunk_rows]

        emb_path = directory / "embeddings.npy"
        embeddings = np.load(emb_path) if emb_path.exists() else None
        bm25 = BM25Index.load(directory / "bm25.pkl")
        subword = CharNgramIndex.load(directory / "subword.pkl")
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        return cls(
            chunks=chunks,
            documents=documents,
            embeddings=embeddings,
            bm25=bm25,
            manifest=manifest,
            subword=subword,
        )


class PgVectorStore:
    """Production PostgreSQL + pgvector (HNSW) + French tsvector store for LibreDataHub.

    Implements native SQL hybrid retrieval directly inside InterHop's LibreDataHub PostgreSQL.
    Requires `pip install psycopg[binary] pgvector` and `CREATE EXTENSION IF NOT EXISTS vector;`.
    """

    SCHEMA_SQL = """
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS sfar_chunks (
        chunk_id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        doc_title TEXT NOT NULL,
        effective_year INTEGER,
        doc_type TEXT,
        language TEXT,
        doc_role TEXT,
        chunk_type TEXT,
        section_path TEXT,
        domains TEXT[],
        is_active BOOLEAN DEFAULT TRUE,
        is_latest_edition BOOLEAN DEFAULT TRUE,
        is_reference_section BOOLEAN DEFAULT FALSE,
        payload_json JSONB NOT NULL,
        text_tsv TSVECTOR GENERATED ALWAYS AS (
            to_tsvector('french', coalesce(doc_title, '') || ' ' || coalesce(section_path, '') || ' ' || coalesce(payload_json->>'text', ''))
        ) STORED,
        embedding VECTOR({dim})
    );

    CREATE INDEX IF NOT EXISTS idx_sfar_chunks_embedding_hnsw
        ON sfar_chunks USING hnsw (embedding vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_sfar_chunks_tsv
        ON sfar_chunks USING gin (text_tsv);
    CREATE INDEX IF NOT EXISTS idx_sfar_chunks_filters
        ON sfar_chunks (is_active, is_latest_edition, is_reference_section, language, effective_year);
    """

    def __init__(self, dsn: str, dim: int = 1024) -> None:
        self.dsn = dsn
        self.dim = dim

    def init_schema(self) -> None:
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.execute(self.SCHEMA_SQL.format(dim=self.dim))
            conn.commit()

    def upsert_chunks(self, chunks: list[Chunk], embeddings: np.ndarray) -> int:
        import psycopg
        from pgvector.psycopg import register_vector

        with psycopg.connect(self.dsn) as conn:
            register_vector(conn)
            with conn.cursor() as cur:
                for chunk, emb in zip(chunks, embeddings):
                    cur.execute(
                        """
                        INSERT INTO sfar_chunks (
                            chunk_id, doc_id, doc_title, effective_year, doc_type, language,
                            doc_role, chunk_type, section_path, domains, is_active,
                            is_latest_edition, is_reference_section, payload_json, embedding
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            payload_json = EXCLUDED.payload_json,
                            embedding = EXCLUDED.embedding
                        """,
                        (
                            chunk.chunk_id,
                            chunk.doc_id,
                            chunk.doc_title,
                            chunk.effective_year,
                            chunk.doc_type,
                            chunk.language,
                            chunk.doc_role,
                            chunk.chunk_type,
                            chunk.section_path,
                            chunk.domains,
                            chunk.is_active,
                            chunk.is_latest_edition,
                            chunk.is_reference_section,
                            chunk.model_dump_json(),
                            emb.tolist(),
                        ),
                    )
            conn.commit()
        return len(chunks)

    def hybrid_search_sql(
        self,
        query: str,
        query_vec: np.ndarray,
        top_k: int = 20,
        latest_only: bool = True,
        exclude_refs: bool = True,
        rrf_k: int = 60,
    ) -> list[tuple[Chunk, float]]:
        """Execute native PostgreSQL RRF fusion (pgvector HNSW + French tsvector FTS)."""
        import psycopg
        from pgvector.psycopg import register_vector

        where_clauses = ["is_active = TRUE", "language != 'en'"]
        if latest_only:
            where_clauses.append("is_latest_edition = TRUE")
        if exclude_refs:
            where_clauses.append("is_reference_section = FALSE")
        where_sql = " AND ".join(where_clauses)

        sql = f"""
        WITH dense AS (
            SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS r_dense
            FROM sfar_chunks
            WHERE {where_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT 40
        ),
        sparse AS (
            SELECT chunk_id, ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(text_tsv, websearch_to_tsquery('french', %s)) DESC
            ) AS r_sparse
            FROM sfar_chunks
            WHERE {where_sql}
              AND text_tsv @@ websearch_to_tsquery('french', %s)
            LIMIT 40
        ),
        fused AS (
            SELECT
                COALESCE(d.chunk_id, s.chunk_id) AS chunk_id,
                COALESCE(1.0 / (%s + d.r_dense), 0.0) + COALESCE(1.0 / (%s + s.r_sparse), 0.0) AS rrf_score
            FROM dense d
            FULL OUTER JOIN sparse s ON d.chunk_id = s.chunk_id
        )
        SELECT c.payload_json, f.rrf_score
        FROM fused f
        JOIN sfar_chunks c ON c.chunk_id = f.chunk_id
        ORDER BY f.rrf_score DESC
        LIMIT %s;
        """
        vec_list = query_vec.tolist()
        with psycopg.connect(self.dsn) as conn:
            register_vector(conn)
            rows = conn.execute(
                sql, (vec_list, vec_list, query, query, rrf_k, rrf_k, top_k)
            ).fetchall()
        return [(Chunk.model_validate(r[0]), float(r[1])) for r in rows]
