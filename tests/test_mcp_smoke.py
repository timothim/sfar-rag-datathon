"""MCP servers through a real MCP client, without GPU or models (toy in-memory index).

- `scripts/mcp_smoke_test.py` (the deployment smoke test) runs green against the HTTP server
  and against the stdio server launched as a subprocess by the SDK's stdio client.
- Both servers serve the PRODUCTION profile: retrieval configuration `C10_context_notes`, and the
  default index directory of the profile (index/tas_v6, overridable by RAG_SFAR_INDEX_DIR).
Skipped when the optional `mcp` SDK is not installed (extra `mcp` of pyproject.toml).
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
import threading
import time
from pathlib import Path

import anyio
import pytest

pytest.importorskip("mcp")
import httpx  # noqa: E402
import uvicorn  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402

from rag_sfar.generation.profile import PRODUCTION  # noqa: E402
from rag_sfar.interfaces.mcp_http import create_http_app  # noqa: E402
from rag_sfar.retrieval.bm25 import BM25Index  # noqa: E402
from rag_sfar.retrieval.pipeline import SfarRagRetriever  # noqa: E402
from rag_sfar.retrieval.vector_store import LocalVectorStore  # noqa: E402
from rag_sfar.schemas import Chunk, DocumentMetadata  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _load_smoke():
    spec = importlib.util.spec_from_file_location("mcp_smoke_test", ROOT / "scripts" / "mcp_smoke_test.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def toy_retriever() -> SfarRagRetriever:
    """Two editions of one toy document (fictitious text), four sections each."""
    chunks, docs = [], []
    for doc_id, year, latest in (("toy-2026", 2026, True), ("toy-2016", 2016, False)):
        docs.append(
            DocumentMetadata(
                doc_id=doc_id, title=f"Intubation difficile (toy {year})", filename=f"{doc_id}.pdf",
                md_path=f"{doc_id}.md", effective_year=year, landing_url="https://sfar.org/toy/",
                domains=["Voies aériennes"], is_latest_edition=latest,
                superseded_by=None if latest else "toy-2026", superseded_by_year=None if latest else 2026,
            )
        )
        for i in range(4):
            text = (
                f"Section {i} de l'édition {year} : texte fictif sur l'intubation difficile imprévue "
                f"au bloc opératoire, oxygénation, vidéolaryngoscope et algorithme de prise en charge. "
                * 3
            )
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}-{i}", doc_id=doc_id, chunk_index=i, section_path=f"R{i} Intubation",
                    text=text, indexed_text=text, doc_title=f"Intubation difficile (toy {year})",
                    effective_year=year, grade_levels=["GRADE 1+"], domains=["Voies aériennes"],
                    is_latest_edition=latest, superseded_by=None if latest else "toy-2026",
                    landing_url="https://sfar.org/toy/",
                )
            )
    store = LocalVectorStore(
        chunks=chunks, documents=docs, embeddings=None, bm25=BM25Index().build([c.indexed_text for c in chunks])
    )
    return SfarRagRetriever(store=store)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def http_url():
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_http_app(toy_retriever()), host="127.0.0.1", port=port, log_level="warning")
    )
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


def _run_smoke(target, mode: str = "auto", concurrency: int = 0):
    smoke = _load_smoke()
    rep = smoke.Report()
    anyio.run(smoke.run, target, mode, concurrency, rep)
    return rep


@pytest.mark.parametrize("mode", ["auto", "legacy", "2026-07-28"])
def test_smoke_script_against_http(http_url, mode):
    rep = _run_smoke(http_url, mode, concurrency=3 if mode == "auto" else 0)
    assert rep.ok, [c for c in rep.checks if not c["ok"]]


STDIO_BOOT = (
    "import sys; sys.path[:0] = [{src!r}, {tests!r}]; "
    "from test_mcp_smoke import toy_retriever; "
    "from rag_sfar.interfaces.mcp_server import SfarMcpServer; "
    "SfarMcpServer(toy_retriever()).serve_stdio()"
)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_smoke_script_against_stdio(mode):
    code = STDIO_BOOT.format(src=str(ROOT / "src"), tests=str(ROOT / "tests"))
    params = StdioServerParameters(command=sys.executable, args=["-c", code], env=dict(os.environ))
    rep = _run_smoke(params, mode)
    assert rep.ok, [c for c in rep.checks if not c["ok"]]


def test_both_servers_retrieve_with_production_profile(http_url):
    """Every search path of both servers uses the PRODUCTION retrieval configuration."""
    from mcp import Client

    from rag_sfar.interfaces.mcp_http import build_structured_search
    from rag_sfar.interfaces.mcp_server import SfarMcpServer

    assert PRODUCTION.retrieval_config_name == "C10_context_notes"
    retriever = toy_retriever()
    seen: list[str] = []
    original = retriever.retrieve

    def spy(*args, **kwargs):
        seen.append(kwargs["config"].name)
        return original(*args, **kwargs)

    retriever.retrieve = spy  # type: ignore[method-assign]
    build_structured_search(retriever, "intubation difficile", 5, False, 1800)
    SfarMcpServer(retriever).call_tool("search_sfar_recommendations", {"query": "intubation difficile"})
    assert seen == ["C10_context_notes", "C10_context_notes"]

    async def index_id() -> str:
        async with Client(http_url) as client:
            res = await client.call_tool("sfar_search", {"query": "intubation difficile"})
            return res.structured_content["index_id"]

    assert anyio.run(index_id) == "unknown-2docs-8chunks"  # toy store, no manifest


def test_servers_default_to_production_index(monkeypatch):
    """Without arguments both entry points load the profile index (index/tas_v6)."""
    import rag_sfar.interfaces.mcp_http as http_mod
    import rag_sfar.interfaces.mcp_server as stdio_mod

    class Stop(Exception):
        pass

    loaded: list[Path] = []

    def fake_load(path):
        loaded.append(Path(path))
        raise Stop

    monkeypatch.delenv("RAG_SFAR_INDEX_DIR", raising=False)
    monkeypatch.setattr(http_mod, "load_retriever", fake_load)
    monkeypatch.setattr(stdio_mod.LocalVectorStore, "load", staticmethod(fake_load))
    monkeypatch.setattr(sys, "argv", ["rag-sfar-mcp-http"])
    with pytest.raises(Stop):
        http_mod.main()
    with pytest.raises(Stop):
        stdio_mod.main()
    assert loaded == [Path("index/tas_v6"), Path("index/tas_v6")]

    monkeypatch.setenv("RAG_SFAR_INDEX_DIR", "/data/index")
    with pytest.raises(Stop):
        http_mod.main()
    assert loaded[-1] == Path("/data/index")


def test_http_env_configuration(monkeypatch):
    """Host and port come from RAG_SFAR_MCP_HOST / RAG_SFAR_MCP_PORT; default bind is 127.0.0.1."""
    import rag_sfar.interfaces.mcp_http as http_mod

    captured: dict = {}
    monkeypatch.setattr(http_mod, "load_retriever", lambda path: toy_retriever())
    import uvicorn as uv

    monkeypatch.setattr(uv, "run", lambda app, host, port: captured.update(host=host, port=port))
    monkeypatch.setattr(sys, "argv", ["rag-sfar-mcp-http"])
    monkeypatch.delenv("RAG_SFAR_MCP_HOST", raising=False)
    monkeypatch.delenv("RAG_SFAR_MCP_PORT", raising=False)
    http_mod.main()
    assert captured == {"host": "127.0.0.1", "port": 8765}
    monkeypatch.setenv("RAG_SFAR_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("RAG_SFAR_MCP_PORT", "8020")
    monkeypatch.setenv("RAG_SFAR_MCP_ALLOWED_HOSTS", "127.0.0.1:*")
    http_mod.main()
    assert captured == {"host": "0.0.0.0", "port": 8020}
