"""Integration tests for FastAPI Clinical UI & OpenAI-compatible API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from rag_sfar.config import Settings
from rag_sfar.interfaces.api import create_app
from rag_sfar.retrieval.bm25 import BM25Index
from rag_sfar.retrieval.vector_store import LocalVectorStore
from rag_sfar.schemas import Chunk, DocumentMetadata


def test_fastapi_endpoints_and_openai_compat(tmp_path: Path):
    meta = DocumentMetadata(
        doc_id="doc_anticoag_2026",
        title="Gestion des anticoagulants pour une procédure invasive programmée",
        filename="RFE_anticoag_2026.pdf",
        md_path="a.md",
        effective_year=2026,
        domains=["Hématologie – Coagulation – Transfusion"],
        is_latest_edition=True,
        topic_lineage="anticoagulants_procedure_programmee",
    )
    chunk = Chunk(
        chunk_id="c_001",
        doc_id=meta.doc_id,
        chunk_index=0,
        chunk_type="table_row_card",
        section_path="Patients traités par AOD",
        text="3.4 — Procédure à risque hémorragique très élevé (neurochirurgie, neuraxial) : arrêt des AOD à J-5 (Avis d'experts, Accord fort).",
        indexed_text="[RFE SFAR 2026 | Gestion des anticoagulants] 3.4 — Procédure neuraxiale : arrêt AOD J-5.",
        doc_title=meta.title,
        effective_year=2026,
        domains=meta.domains,
        is_latest_edition=True,
        grade_levels=["Avis d'experts", "Accord fort"],
    )
    store = LocalVectorStore(
        chunks=[chunk],
        documents=[meta],
        embeddings=None,
        bm25=BM25Index().build([chunk.indexed_text]),
        manifest={"embedding_provider": "none", "embedding_model": "none"},
    )
    store.save(tmp_path)

    app = create_app(
        index_dir=tmp_path,
        settings=Settings(reranker_provider="none"),
        enable_llm=False,
    )
    client = TestClient(app)

    r_home = client.get("/")
    assert r_home.status_code == 200
    assert "RAG-SFAR" in r_home.text

    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["num_documents"] == 1

    r_search = client.post("/api/search", json={"query": "arrêt AOD neuraxial", "use_reranker": False})
    assert r_search.status_code == 200
    data = r_search.json()
    assert len(data["retrieved_chunks"]) == 1
    assert "J-5" in data["retrieved_chunks"][0]["chunk"]["text"]

    r_models = client.get("/v1/models")
    assert r_models.status_code == 200
    assert any(m["id"] == "rag-sfar-sota" for m in r_models.json()["data"])

    r_chat = client.post(
        "/v1/chat/completions",
        json={"model": "rag-sfar-sota", "messages": [{"role": "user", "content": "arrêt AOD neuraxial"}]},
    )
    assert r_chat.status_code == 200
    assert "sfar_citations" in r_chat.json()

    r_stream = client.post(
        "/api/query/stream",
        json={"query": "arrêt AOD neuraxial", "use_reranker": False, "retrieval_only": True},
    )
    assert r_stream.status_code == 200
    assert '"type": "retrieval"' in r_stream.text
    assert '"type": "done"' in r_stream.text
