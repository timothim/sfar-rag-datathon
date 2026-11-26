#!/usr/bin/env python3
"""Run 6 flagship cross-RFE clinical queries End-to-End (Retrieval + LLM + Grounding Audit)
and export a jury-ready Markdown showcase (`reports/clinical_e2e_showcase.md`).

Covers all 3 flagship 2026 SFAR RFEs + scope separation + longitudinal diff:
  1. Antibioprophylaxie V3.0 (2026): PTH voie antérieure + allergie bêtalactamines
  2. Antibioprophylaxie V3.0 (2026): Plaie cranio-cérébrale + allergie pénicillines (Neurochirurgie)
  3. Anticoagulants Procédure Programmée (2026): Délai arrêt AOD avant neurochirurgie intracrânienne
  4. Anticoagulation Urgence (2024): Hémorragie intracrânienne grave sous anticoagulant
  5. Infections Intra-Abdominales (2026): Antibiothérapie probabiliste IIA communautaire sans sepsis
  6. Comparaison Temporelle Multi-Éditions: Évolution antibioprophylaxie SFAR 2018 vs 2026
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from rich.console import Console

from rag_sfar.config import RetrievalConfig, Settings
from rag_sfar.generation.client import LocalMlxLLM, OpenAICompatibleLLM, SfarRagEngine
from rag_sfar.retrieval.embedder import build_embedder
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.reranker import build_reranker
from rag_sfar.retrieval.vector_store import LocalVectorStore

os.environ.setdefault("HF_HUB_OFFLINE", "1")
console = Console()

FLAGSHIP_CLINICAL_CASES = [
    (
        "1. Antibioprophylaxie 2026 — PTH voie antérieure + allergie (Exception + Encadré)",
        "Quelle est la recommandation d'antibioprophylaxie pour une PTH par voie antérieure chez un patient allergique aux bêtalactamines ?",
    ),
    (
        "2. Antibioprophylaxie 2026 — Neurochirurgie + allergie pénicillines (Split-Chunk)",
        "Quelle est la recommandation d'antibioprophylaxie pour une plaie cranio-cérébrale chez un patient allergique aux pénicillines ?",
    ),
    (
        "3. Anticoagulants Programmés 2026 — Arrêt AOD neurochirurgie intracrânienne",
        "Quel est le délai d'arrêt des AOD avant une neurochirurgie intracrânienne ou une procédure neuraxiale programmée ?",
    ),
    (
        "4. Anticoagulation Urgence 2024 — Hémorragie intracrânienne (Séparation périmètre)",
        "Chez un patient sous anticoagulant avec hémorragie intracrânienne grave en urgence, quelle est la conduite immédiate et faut-il attendre les dosages biologiques pour réverser ?",
    ),
    (
        "5. Infections Intra-Abdominales 2026 — IIA communautaire sans sepsis (R1.2.1)",
        "Quelle antibiothérapie probabiliste recommander pour une infection intra-abdominale communautaire sans sepsis ni choc septique chez l'adulte (R1.2.1) ?",
    ),
    (
        "6. Veille Longitudinale — Comparaison Antibioprophylaxie 2018 vs 2026",
        "Qu'est-ce qui a changé dans les recommandations d'antibioprophylaxie SFAR entre 2018 et 2026 ?",
    ),
]


def main() -> None:
    s = Settings()
    parser = argparse.ArgumentParser(description="Run 6 flagship clinical cases End-to-End.")
    parser.add_argument("--index-dir", type=Path, default=Path("index/table_aware_sota"))
    parser.add_argument("--backend", choices=["openai", "mlx"], default="mlx")
    parser.add_argument("--base-url", default=s.llm_base_url)
    parser.add_argument("--api-key", default=s.llm_api_key)
    parser.add_argument("--model", default="Qwen2.5-7B-Instruct-4bit")
    parser.add_argument("--mlx-model-path", default="")
    parser.add_argument("--output", type=Path, default=Path("reports/clinical_e2e_showcase.md"))
    args = parser.parse_args()

    store = LocalVectorStore.load(args.index_dir)
    embedder = build_embedder(
        provider=store.manifest.get("embedding_provider", s.embedding_provider),
        model_name=store.manifest.get("embedding_model", s.embedding_model),
        index_dir=args.index_dir,
    )
    reranker = build_reranker(s.reranker_provider, s.reranker_model) if s.reranker_provider != "none" else None
    retriever = SfarRagRetriever(store=store, embedder=embedder, reranker=reranker)

    if args.backend == "mlx":
        llm: Any = LocalMlxLLM(
            model_path=args.mlx_model_path or args.model,
            model_label=args.model,
            temperature=0.0,
            max_tokens=500,
        )
    else:
        llm = OpenAICompatibleLLM(
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            temperature=0.0,
            max_tokens=500,
        )

    engine = SfarRagEngine(retriever=retriever, llm=llm, default_config=RetrievalConfig())

    md_lines = [
        f"# RAG-SFAR Frontier 2026 — Démonstration Clinique End-to-End (`{args.model}`)\n",
        "> 6 cas cliniques couvrant les **3 RFE phares 2026**, la séparation **Urgence 2024 vs Programmé 2026**, les **allergies split-chunk** et le mode **comparaison longitudinale multi-éditions**.\n",
    ]

    for title, query in FLAGSHIP_CLINICAL_CASES:
        console.print(f"[bold cyan]Running:[/bold cyan] {title}")
        resp = engine.answer(query=query, mode="clinical_detailed")
        v = resp.verification
        md_lines.append(f"## {title}\n")
        md_lines.append(f"**Question** : *{query}*\n")
        md_lines.append(
            f"- **Routeur** : `temporal={resp.query_analysis.temporal_mode}` | "
            f"`setting={resp.query_analysis.setting}` | `modifiers={resp.query_analysis.modifiers}`\n"
            f"- **Vérificateur** : Grounding = **{v.grounding_score*100:.0f}%** | "
            f"Citations = `{v.citations_found}` | Molécules hors-source = `{v.ungrounded_molecules}` | "
            f"Auto-corrigé = `{resp.extra.get('self_corrected', False)}`\n"
            f"- **Tokens prompt** : `{resp.token_usage.get('prompt_tokens', 0)}` | "
            f"**Latence totale** : `{resp.latency_ms.get('total_ms', 0):.0f} ms`\n"
        )
        md_lines.append("### Réponse clinique générée\n")
        md_lines.append(resp.answer + "\n")
        md_lines.append("### Sources SFAR citées\n")
        for c in resp.citations[:5]:
            ed = "EN VIGUEUR" if c.is_latest_edition else f"ANTÉRIEURE {c.effective_year}"
            md_lines.append(
                f"- **[{c.citation_id}]** `{c.effective_year} | {ed} | {c.chunk_type}` — **{c.doc_title}** (*{c.section_path[:90]}*)"
            )
        md_lines.append("\n---\n")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(md_lines), encoding="utf-8")
    console.print(f"[bold green]Showcase saved to {args.output}[/bold green]")


if __name__ == "__main__":
    main()
