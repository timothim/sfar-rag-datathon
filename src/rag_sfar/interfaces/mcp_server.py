"""Model Context Protocol (MCP) JSON-RPC 2.0 stdio server exposing SFAR guidelines tools.

Zero extra MCP SDK dependency required — implements the official MCP stdio JSON-RPC
handshake (`initialize`, `tools/list`, `tools/call`) directly over our SOTA hybrid index!
Exposes 4 clinical tools:
1. `search_sfar_recommendations` — Hybrid + reranked search with temporal & population routing
2. `compare_sfar_editions` — Longitudinal diff retrieval across multiple guideline editions
3. `list_sfar_catalog` — Browse all 267 enriched SFAR documents, domains, and supersession status
4. `get_recommendation_sections` — Inspect structured sections/tables of a specific SFAR document
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from rag_sfar.config import RetrievalConfig, Settings
from rag_sfar.retrieval.embedder import build_embedder
from rag_sfar.retrieval.pipeline import SfarRagRetriever, format_context_for_llm
from rag_sfar.retrieval.reranker import build_reranker
from rag_sfar.retrieval.vector_store import LocalVectorStore

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "search_sfar_recommendations",
        "description": (
            "Recherche hybride (BM25+ médical + embeddings multilingues + reranking) dans les "
            "267 recommandations de la SFAR (2000–2026) avec gestion des éditions en vigueur, "
            "tableaux structurés et encadrés allergie."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Question clinique en français (ex: PTH allergie bêtalactamines, arrêt AOD neurochirurgie)."},
                "top_k": {"type": "integer", "default": 6, "description": "Nombre de passages retournés."},
                "latest_only": {"type": "boolean", "default": True, "description": "Limiter aux éditions en vigueur (défaut: true)."},
                "domain": {"type": "string", "description": "Filtre optionnel par domaine clinique SFAR."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "compare_sfar_editions",
        "description": (
            "Compare les éditions successives d'une recommandation SFAR (ex : antibioprophylaxie "
            "2018 vs 2026, infections intra-abdominales 2015 vs 2026, anticoagulants 2021 vs 2026)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic_query": {"type": "string", "description": "Sujet ou question clinique à comparer entre éditions."},
                "top_k": {"type": "integer", "default": 10},
            },
            "required": ["topic_query"],
        },
    },
    {
        "name": "list_sfar_catalog",
        "description": "Liste les recommandations SFAR indexées avec année effective, domaine, rôle et statut (en vigueur vs remplacée).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Mot-clé filtrant le titre ou le domaine."},
                "latest_only": {"type": "boolean", "default": True},
                "limit": {"type": "integer", "default": 25},
            },
        },
    },
    {
        "name": "get_recommendation_sections",
        "description": "Récupère les passages/tableaux d'un document SFAR précis via son `doc_id`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Identifiant exact du document (obtenu via search ou list_sfar_catalog)."},
                "section_filter": {"type": "string", "description": "Sous-chaîne optionnelle filtrant le chemin de section."},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["doc_id"],
        },
    },
]


class SfarMcpServer:
    """Minimal, spec-compliant MCP stdio server for SFAR guidelines."""

    def __init__(self, retriever: SfarRagRetriever) -> None:
        self.retriever = retriever
        self.store = retriever.store

    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        if name == "search_sfar_recommendations":
            cfg = RetrievalConfig(final_top_k=int(args.get("top_k", 6)))
            domains = [args["domain"]] if args.get("domain") else None
            retrieved, analysis, _ = self.retriever.retrieve(
                query=args["query"],
                config=cfg,
                override_latest_only=args.get("latest_only", True),
                override_domains=domains,
            )
            header = (
                f"Analyse requête : mode={analysis.temporal_mode}, pop={analysis.population}, "
                f"contexte={analysis.setting}, acronymes={analysis.acronyms_expanded}\n\n"
            )
            return header + format_context_for_llm(retrieved)

        if name == "compare_sfar_editions":
            cfg = RetrievalConfig(
                latest_edition_only=False,
                final_top_k=int(args.get("top_k", 10)),
                max_chunks_per_doc=3,
            )
            retrieved, _, _ = self.retriever.retrieve(
                query=args["topic_query"],
                config=cfg,
                override_latest_only=False,
            )
            return format_context_for_llm(retrieved)

        if name == "list_sfar_catalog":
            kw = (args.get("keyword") or "").lower().strip()
            latest_only = bool(args.get("latest_only", True))
            limit = int(args.get("limit", 25))
            rows = []
            for d in sorted(
                self.store.documents,
                key=lambda x: (-(x.effective_year or 0), x.title),
            ):
                if latest_only and not d.is_latest_edition:
                    continue
                if kw and kw not in f"{d.title} {' '.join(d.domains)} {d.topic_lineage or ''}".lower():
                    continue
                status = "EN VIGUEUR" if d.is_latest_edition else f"REMPLACÉE ({d.superseded_by_year})"
                rows.append(
                    f"- [{d.effective_year or '?'}] ({d.doc_type}/{d.doc_role}) [{status}] "
                    f"`{d.doc_id}` — {d.title} | Domaines: {', '.join(d.domains[:3])}"
                )
                if len(rows) >= limit:
                    break
            return "\n".join(rows) if rows else "Aucun document correspondant."

        if name == "get_recommendation_sections":
            doc_id = args["doc_id"]
            sec_f = (args.get("section_filter") or "").lower().strip()
            limit = int(args.get("limit", 10))
            matched = [
                c
                for c in self.store.chunks
                if c.doc_id == doc_id
                and not c.is_reference_section
                and (not sec_f or sec_f in c.section_path.lower())
            ][:limit]
            if not matched:
                return f"Aucun passage trouvé pour doc_id={doc_id}."
            return "\n\n---\n\n".join(
                f"### [{c.chunk_type}] {c.section_path}\n{c.text}" for c in matched
            )

        raise ValueError(f"Unknown MCP tool: {name}")

    def handle_message(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        method = msg.get("method")
        req_id = msg.get("id")
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "rag-sfar-mcp", "version": "1.0.0"},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_SCHEMA}}
        if method == "tools/call":
            params = msg.get("params", {})
            try:
                text = self.call_tool(params.get("name", ""), params.get("arguments", {}))
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": text}]},
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": f"Error: {exc}"}],
                    },
                }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def serve_stdio(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                resp = self.handle_message(msg)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                    sys.stdout.flush()
            except Exception as exc:
                sys.stderr.write(f"[rag-sfar-mcp] error: {exc}\n")
                sys.stderr.flush()


def main() -> None:
    settings = Settings()
    idx_dir = Path(settings.index_dir)
    store = LocalVectorStore.load(idx_dir)
    embedder = None
    if store.embeddings is not None:
        embedder = build_embedder(
            provider=store.manifest.get("embedding_provider", settings.embedding_provider),
            model_name=store.manifest.get("embedding_model", settings.embedding_model),
            index_dir=idx_dir,
        )
    reranker = None
    if settings.reranker_provider != "none":
        try:
            reranker = build_reranker(settings.reranker_provider, settings.reranker_model)
        except Exception:
            reranker = None
    retriever = SfarRagRetriever(store=store, embedder=embedder, reranker=reranker)
    SfarMcpServer(retriever).serve_stdio()


if __name__ == "__main__":
    main()
