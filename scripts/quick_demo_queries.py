#!/usr/bin/env python3
"""Run 6 flagship clinical demo queries against the built SOTA index and print a clean trace."""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from rag_sfar.config import RetrievalConfig
from rag_sfar.retrieval.embedder import build_embedder
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.reranker import build_reranker
from rag_sfar.retrieval.vector_store import LocalVectorStore

os.environ.setdefault("HF_HUB_OFFLINE", "1")
console = Console()

DEMO_QUERIES = [
    "Quelle est la recommandation d'antibioprophylaxie pour une PTH par voie antérieure chez un patient allergique aux bêtalactamines ?",
    "Quelle est la recommandation d'antibioprophylaxie pour une prothèse totale de genou chez un patient allergique aux bêtalactamines ?",
    "Quel est le délai d'arrêt des AOD avant une neurochirurgie intracrânienne ou une procédure neuraxiale programmée ?",
    "Chez un patient sous anticoagulant avec hémorragie intracrânienne en urgence, faut-il attendre les tests biologiques pour réverser ?",
    "Quelle antibiothérapie probabiliste pour une infection intra-abdominale communautaire sans sepsis ni choc septique chez l'adulte ?",
    "Qu'est-ce qui a changé dans les recommandations d'antibioprophylaxie entre 2018 et 2026 ?",
]


def main() -> None:
    idx_dir = Path("index/table_aware_sota")
    store = LocalVectorStore.load(idx_dir)
    embedder = build_embedder(
        provider=store.manifest["embedding_provider"],
        model_name=store.manifest["embedding_model"],
        index_dir=idx_dir,
    )
    reranker = build_reranker("cross_encoder", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
    retriever = SfarRagRetriever(store=store, embedder=embedder, reranker=reranker)
    cfg = RetrievalConfig()

    for q in DEMO_QUERIES:
        results, analysis, timings = retriever.retrieve(q, config=cfg)
        lines = [
            f"[bold cyan]Router[/bold cyan]: temporal={analysis.temporal_mode} | pop={analysis.population} | "
            f"setting={analysis.setting} | modifiers={analysis.modifiers} | acronyms={analysis.acronyms_expanded}",
            f"[bold cyan]Latency[/bold cyan]: {timings}",
            "",
        ]
        for i, r in enumerate(results[:5], 1):
            c = r.chunk
            ed = "[green]EN VIGUEUR[/green]" if c.is_latest_edition else f"[yellow]ANTÉRIEURE {c.effective_year}[/yellow]"
            exp = f" [magenta]+{r.expansion_reason}[/magenta]" if r.is_expanded_context else ""
            lines.append(
                f"  [bold][S{i}][/bold] ({c.effective_year} | {ed} | {c.chunk_type}{exp}) "
                f"[white]{c.doc_title}[/white] — score={r.final_score:.4f} (BM25=#{r.bm25_rank}, Dense=#{r.dense_rank}, CE={r.rerank_score})"
            )
            lines.append(f"       Section: {c.section_path[:110]}")
            lines.append(f"       Extrait: {c.text[:220].replace(chr(10), ' ')}")
        console.print(Panel("\n".join(lines), title=q, border_style="blue"))


if __name__ == "__main__":
    main()
