"""Local end-to-end test of the prototype Streamable HTTP MCP server.

Starts the server on 127.0.0.1 (random free port) with a tiny in-memory index,
then talks to it with the official MCP Python client, both with the stateless
2026-07-28 protocol and with the legacy `initialize` handshake.
Skipped when the optional `mcp` SDK is not installed.
"""

from __future__ import annotations

import socket
import threading
import time

import anyio
import pytest

pytest.importorskip("mcp")
import httpx  # noqa: E402
import uvicorn  # noqa: E402
from mcp import Client  # noqa: E402

from rag_sfar.interfaces.mcp_http import create_http_app  # noqa: E402
from rag_sfar.retrieval.bm25 import BM25Index  # noqa: E402
from rag_sfar.retrieval.pipeline import SfarRagRetriever  # noqa: E402
from rag_sfar.retrieval.vector_store import LocalVectorStore  # noqa: E402
from rag_sfar.schemas import Chunk, DocumentMetadata  # noqa: E402


def _tiny_retriever() -> SfarRagRetriever:
    c1 = Chunk(
        chunk_id="c1",
        doc_id="d1",
        chunk_index=0,
        section_path="Arrêt des anticoagulants",
        text="Arrêt des AOD (apixaban, rivaroxaban) à J-3 avant procédure programmée.",
        indexed_text="Arrêt des AOD (apixaban, rivaroxaban) à J-3 avant procédure programmée.",
        doc_title="Gestion des anticoagulants",
        effective_year=2026,
        grade_levels=["GRADE 1+"],
        domains=["Hématologie – Coagulation – Transfusion"],
        is_latest_edition=True,
        landing_url="https://sfar.org/exemple/",
    )
    meta = DocumentMetadata(
        doc_id="d1",
        title="Gestion des anticoagulants",
        filename="anticoag.pdf",
        md_path="a.md",
        effective_year=2026,
        landing_url="https://sfar.org/exemple/",
        domains=["Hématologie – Coagulation – Transfusion"],
    )
    store = LocalVectorStore(
        chunks=[c1], documents=[meta], embeddings=None, bm25=BM25Index().build([c1.indexed_text])
    )
    return SfarRagRetriever(store=store)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url():
    port = _free_port()
    app = create_http_app(_tiny_retriever(), host="127.0.0.1")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:  # pragma: no cover
        pytest.fail("MCP HTTP server did not start")
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(timeout=10)


EXPECTED_TOOLS = {
    "sfar_search",
    "search_sfar_recommendations",
    "compare_sfar_editions",
    "list_sfar_catalog",
    "get_recommendation_sections",
}


async def _exercise(url: str, mode: str) -> None:
    async with Client(url, mode=mode) as client:
        tools = (await client.list_tools()).tools
        by_name = {t.name: t for t in tools}
        assert set(by_name) == EXPECTED_TOOLS
        for t in tools:
            assert t.annotations is not None and t.annotations.read_only_hint is True
        assert by_name["sfar_search"].output_schema is not None

        res = await client.call_tool("sfar_search", {"query": "arrêt AOD avant chirurgie"})
        assert not res.is_error
        data = res.structured_content
        assert data["passages"], data
        p = data["passages"][0]
        assert p["doc_id"] == "d1"
        assert p["status"] == "en_vigueur"
        assert p["url"] == "https://sfar.org/exemple/"
        assert "J-3" in p["excerpt"]
        assert data["usage_notice"]

        legacy = await client.call_tool("search_sfar_recommendations", {"query": "arrêt AOD"})
        assert "J-3" in legacy.content[0].text

        bad = await client.call_tool("sfar_search", {"query": "x", "top_k": 500})
        assert bad.is_error


def test_mcp_http_modern_stateless(server_url):
    anyio.run(_exercise, server_url, "2026-07-28")


def test_mcp_http_legacy_handshake(server_url):
    anyio.run(_exercise, server_url, "legacy")


def test_mcp_http_raw_initialize(server_url):
    """A bare JSON-RPC initialize (what older clients send) gets a valid answer."""
    r = httpx.post(
        server_url,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "raw-test", "version": "0"},
            },
        },
        headers={"Accept": "application/json, text/event-stream"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["serverInfo"]["name"] == "rag-sfar-mcp"
    assert "tools" in body["result"]["capabilities"]
