"""Command-line entrypoints for RAG-SFAR (audit, index, eval, serve)."""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from rag_sfar.config import Settings
from rag_sfar.evaluation.ablation import (
    build_standard_ablation_configs,
    format_ablation_markdown,
    run_ablation_suite,
)
from rag_sfar.evaluation.benchmarks import (
    load_antibioprophylaxie_benchmark,
    load_multi_rfe_stress_benchmark,
)
from rag_sfar.ingestion.chunker import ChunkingStrategy, ChunkOptions, chunk_corpus
from rag_sfar.ingestion.loader import (
    corpus_updates_fingerprint,
    load_sfar_corpus,
    resolve_corpus_updates_dir,
)
from rag_sfar.retrieval.bm25 import BM25Index
from rag_sfar.retrieval.embedder import build_embedder
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.reranker import build_reranker
from rag_sfar.retrieval.subword import CharNgramIndex
from rag_sfar.retrieval.vector_store import LocalVectorStore

console = Console()


def build_and_save_index(
    corpus_dir: Path,
    output_dir: Path,
    strategy: ChunkingStrategy = "table_aware_sota",
    embedding_provider: str = "sentence_transformer",
    embedding_model: str = "intfloat/multilingual-e5-small",
    skip_embeddings: bool = False,
    batch_size: int = 32,
    corpus_updates_dir: Path | None = None,
    use_corpus_updates: bool = True,
    chunk_options: ChunkOptions | None = None,
) -> LocalVectorStore:
    """Ingest corpus, chunk with chosen strategy, build BM25+ & dense index, and save to disk."""
    t0 = time.perf_counter()
    console.print(f"[bold cyan]Loading SFAR corpus from {corpus_dir}...[/bold cyan]")
    updates_dir = resolve_corpus_updates_dir(corpus_dir, corpus_updates_dir, use_corpus_updates)
    console.print(f"  Corpus updates overlay: [bold]{updates_dir or 'none'}[/bold]")
    docs = load_sfar_corpus(corpus_dir, updates_dir=updates_dir, use_corpus_updates=updates_dir is not None)
    console.print(f"  Loaded [green]{len(docs)}[/green] enriched unique SFAR documents.")

    t_c = time.perf_counter()
    opts = chunk_options or ChunkOptions()
    if strategy == "table_aware_sota":
        console.print(f"  Chunker options: {opts}")
        chunks = chunk_corpus(docs, strategy=strategy, options=opts)
    else:
        chunks = chunk_corpus(docs, strategy=strategy)
    chunk_types = collections.Counter(c.chunk_type for c in chunks)
    console.print(
        f"  Chunked ([bold]{strategy}[/bold]): [green]{len(chunks):,}[/green] chunks "
        f"in {time.perf_counter() - t_c:.1f}s -> {dict(chunk_types)}"
    )

    t_b = time.perf_counter()
    indexed_texts = [c.indexed_text for c in chunks]
    bm25 = BM25Index().build(indexed_texts)
    console.print(
        f"  Built BM25+ index ({len(bm25.idf):,} terms) in {time.perf_counter() - t_b:.1f}s"
    )

    t_sw = time.perf_counter()
    subword = CharNgramIndex().build(indexed_texts)
    console.print(
        f"  Built Subword Char 3-5 N-Gram index in {time.perf_counter() - t_sw:.1f}s"
    )

    embeddings = None
    embedder = None
    if not skip_embeddings:
        import numpy as np

        t_e = time.perf_counter()
        console.print(
            f"  Computing dense embeddings ([bold]{embedding_provider}:{embedding_model}[/bold])..."
        )
        embedder = build_embedder(provider=embedding_provider, model_name=embedding_model)
        # Skip dense embedding on pure bibliography chunks (searched via BM25 when requested)
        active_indices = [i for i, c in enumerate(chunks) if not c.is_reference_section]
        active_texts = [chunks[i].indexed_text for i in active_indices]
        active_vecs = embedder.embed_documents(active_texts, batch_size=batch_size)
        embeddings = np.zeros((len(chunks), active_vecs.shape[1]), dtype=np.float32)
        embeddings[active_indices] = active_vecs
        embedder.save_state(output_dir)
        console.print(
            f"  Embedded {len(active_indices):,}/{len(chunks):,} clinical chunks "
            f"{embeddings.shape} in {time.perf_counter() - t_e:.1f}s"
        )

    manifest = {
        "strategy": strategy,
        "num_documents": len(docs),
        "num_chunks": len(chunks),
        "chunk_types": dict(chunk_types),
        "has_subword": True,
        "embedding_provider": embedding_provider if not skip_embeddings else "none",
        "embedding_model": embedder.model_name if embedder else "none",
        "embedding_dim": int(embeddings.shape[1]) if embeddings is not None else 0,
        "build_seconds": round(time.perf_counter() - t0, 2),
        "corpus_updates": corpus_updates_fingerprint(updates_dir),
        "chunker_options": dataclasses.asdict(opts) if strategy == "table_aware_sota" else None,
    }

    store = LocalVectorStore(
        chunks=chunks,
        documents=[d.metadata for d in docs],
        embeddings=embeddings,
        bm25=bm25,
        manifest=manifest,
        subword=subword,
    )
    store.save(output_dir)
    console.print(f"[bold green]Saved index to {output_dir}[/bold green] ({manifest['build_seconds']}s)")
    return store


def audit_cmd() -> None:
    parser = argparse.ArgumentParser(description="Run forensic metadata & quality audit on SFAR corpus.")
    parser.add_argument("--corpus-dir", type=Path, default=Settings().corpus_dir)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    args = parser.parse_args()

    docs = load_sfar_corpus(args.corpus_dir)
    metas = [d.metadata for d in docs]

    total_chars = sum(m.char_count for m in metas)
    total_tables = sum(m.table_count for m in metas)
    ref_chars = sum(int(m.char_count * m.reference_char_ratio) for m in metas)
    langs = collections.Counter(m.language for m in metas)
    roles = collections.Counter(m.doc_role for m in metas)
    types = collections.Counter(m.doc_type for m in metas)
    superseded = [m for m in metas if not m.is_latest_edition]
    imputed_years = [m for m in metas if m.year_was_imputed]
    imputed_sub = [m for m in metas if m.subdomain_was_imputed]
    abrogated = [m for m in metas if not m.is_active]

    summary = {
        "unique_documents": len(metas),
        "total_chars": total_chars,
        "estimated_words": int(total_chars / 6.2),
        "total_html_tables": total_tables,
        "reference_chars": ref_chars,
        "reference_share_pct": round(100 * ref_chars / max(1, total_chars), 2),
        "languages": dict(langs),
        "doc_types": dict(types),
        "doc_roles": dict(roles),
        "imputed_years_count": len(imputed_years),
        "imputed_subdomains_count": len(imputed_sub),
        "abrogated_count": len(abrogated),
        "superseded_editions_count": len(superseded),
        "superseded_examples": [
            {
                "title": m.title,
                "year": m.effective_year,
                "lineage": m.topic_lineage,
                "superseded_by_year": m.superseded_by_year,
                "filename": m.filename,
            }
            for m in superseded
        ],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "corpus_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# Audit Forensique du Corpus SFAR (2000–2026)\n",
        f"- **Documents uniques (dédupliqués SHA-256)** : {summary['unique_documents']}",
        f"- **Volume total** : {total_chars:,} caractères (~{summary['estimated_words']:,} mots)",
        f"- **Tableaux HTML `<table>`** : **{total_tables:,}** (0 tableau pipe Markdown !)",
        f"- **Volume Bibliographie / Références** : **{summary['reference_share_pct']}%** du corpus ({ref_chars:,} caractères de bruit potentiel)",
        f"- **Langues détectées (corps du texte)** : {dict(langs)}",
        f"- **Sous-domaines manquants imputés** : **{len(imputed_sub)}** documents (dont les 3 RFE phares 2026 !)",
        f"- **Années manquantes imputées** : **{len(imputed_years)}** documents",
        f"- **Documents explicitement abrogés** : **{len(abrogated)}**",
        f"- **Éditions historiques remplacées (graphe de supersession)** : **{len(superseded)}** documents\n",
        "## Éditions historiques détectées comme remplacées\n",
        "| Lignée clinique | Année | Remplacée en | Titre | Fichier |",
        "|---|---:|---:|---|---|",
    ]
    for ex in summary["superseded_examples"]:
        md_lines.append(
            f"| `{ex['lineage']}` | {ex['year']} | **{ex['superseded_by_year']}** | {ex['title'][:65]} | `{ex['filename'][:45]}` |"
        )
    (args.output_dir / "corpus_audit.md").write_text("\n".join(md_lines), encoding="utf-8")

    console.print("[bold green]Corpus audit written to reports/corpus_audit.{json,md}[/bold green]")
    console.print(f"  Docs: {len(metas)} | Tables: {total_tables} | Refs: {summary['reference_share_pct']}% | Superseded: {len(superseded)} | Imputed subdomains: {len(imputed_sub)}")


def index_cmd() -> None:
    parser = argparse.ArgumentParser(description="Build hybrid RAG-SFAR index.")
    s = Settings()
    parser.add_argument("--corpus-dir", type=Path, default=s.corpus_dir)
    parser.add_argument("--output-dir", type=Path, default=s.index_dir)
    parser.add_argument(
        "--strategy",
        choices=["naive_fixed", "hierarchical_markdown", "table_aware_sota"],
        default="table_aware_sota",
    )
    parser.add_argument("--embedding-provider", default=s.embedding_provider)
    parser.add_argument("--embedding-model", default=s.embedding_model)
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument("--batch-size", type=int, default=s.embedding_batch_size)
    parser.add_argument(
        "--corpus-updates-dir",
        type=Path,
        default=None,
        help="Overlay of newer editions (default: <corpus-dir>/../../corpus_updates if present).",
    )
    parser.add_argument("--no-corpus-updates", action="store_true", help="Ignore any overlay.")
    parser.add_argument(
        "--chunker-options",
        default="",
        help="table_aware_sota options as key=value pairs separated by commas "
        "(see ChunkOptions: clean_ocr, hard_max_chars, header_domains, header_status, "
        "population_hint, reco_units, table_cards_min_cols).",
    )
    args = parser.parse_args()

    build_and_save_index(
        corpus_dir=args.corpus_dir,
        output_dir=args.output_dir,
        strategy=args.strategy,
        embedding_provider=args.embedding_provider,
        embedding_model=args.embedding_model,
        skip_embeddings=args.skip_embeddings,
        batch_size=args.batch_size,
        corpus_updates_dir=args.corpus_updates_dir,
        use_corpus_updates=not args.no_corpus_updates,
        chunk_options=parse_chunker_options(args.chunker_options),
    )


def parse_chunker_options(spec: str) -> ChunkOptions:
    """ChunkOptions from "key=value,key=value" (booleans: 1/0/true/false)."""
    opts = ChunkOptions()
    fields = {f.name: f for f in dataclasses.fields(ChunkOptions)}
    for kv in (spec or "").split(","):
        if not kv.strip():
            continue
        key, _, raw = kv.partition("=")
        key = key.strip()
        if key not in fields:
            raise SystemExit(f"Unknown chunker option: {key} (known: {', '.join(fields)})")
        default = getattr(opts, key)
        if isinstance(default, bool):
            val: object = raw.strip().lower() in ("1", "true", "yes", "on")
        elif isinstance(default, int):
            val = int(raw)
        else:
            val = raw.strip()
        setattr(opts, key, val)
    return opts


def _run_unified_eval(args: argparse.Namespace) -> None:
    from rag_sfar.evaluation import harness

    if args.split == "test" and not args.allow_test:
        raise SystemExit("The test split is locked: evaluate it only on final configs, with --allow-test.")
    if args.baseline == "constant":
        report = harness.run_constant_baseline(args.suite, args.split)
        jp, mp = harness.save_report(report, out_dir=args.report_dir, tag=args.tag or "baseline_constant")
        console.print(harness.to_markdown(report))
        console.print(f"[bold green]Saved {jp} and {mp}[/bold green]")
        return
    configs = harness.select_configs(args.configs)
    if args.ablate:
        configs = [configs[0]] + harness.ablation_variants(configs[0], args.ablate)
    strategies = sorted({c.chunking_strategy for c in configs})
    device = "cpu" if (not args.retrieval_only and args.backend == "mlx") else None
    index_map = dict(kv.split("=", 1) for kv in args.index_map.split(",") if kv.strip())
    reranker_model = args.reranker_override or args.reranker_model
    retrievers = harness.load_retrievers(
        args.index_root, strategies, args.reranker_provider, reranker_model, device=device, index_map=index_map
    )

    factory = None
    label = ""
    if not args.retrieval_only:
        from rag_sfar.generation.client import LocalMlxLLM, OpenAICompatibleLLM, SfarRagEngine
        from rag_sfar.generation.settings import resolve_generation_config

        gen_config = (
            resolve_generation_config(args.gen_preset or "legacy", args.gen) if (args.gen_preset or args.gen) else None
        )
        if args.backend == "mlx":
            llm = LocalMlxLLM(
                model_path=args.mlx_model_path or args.model, model_label=args.model,
                temperature=0.0, max_tokens=args.max_tokens,
            )
        else:
            llm = OpenAICompatibleLLM(
                base_url=args.base_url, api_key=args.api_key, model=args.model,
                temperature=0.0, max_tokens=args.max_tokens,
            )
        label = f"{args.backend}:{args.model}"

        def factory(retriever):
            engine = SfarRagEngine(retriever=retriever, llm=llm, gen_config=gen_config)

            def answer_fn(item, cfg):
                # Every question goes through the requested open mode; the engine itself routes a
                # question with lettered options to its MCQ mode (generation.client.route_mode), as
                # in production.
                mode = "clinical_detailed" if args.gen_mode == "auto" else args.gen_mode
                resp = engine.answer(item.formatted_query(), mode=mode, config=cfg)
                return {"answer": resp.answer, "retrieved": resp.retrieved_chunks, "usage": resp.token_usage}

            return answer_fn

    report = harness.run_eval(
        args.suite, args.split, configs, retrievers, k=args.k, answer_fn_factory=factory,
        generator_label=label, limit=args.limit, progress=lambda m: console.print(f"[dim]{m}[/dim]"),
    )
    report["index_map"] = index_map
    if not args.retrieval_only and (args.gen_preset or args.gen):
        report["gen_config"] = resolve_generation_config(args.gen_preset or "legacy", args.gen).to_dict()
    report["reranker_model"] = reranker_model
    jp, mp = harness.save_report(report, out_dir=args.report_dir, tag=args.tag)
    console.print(harness.to_markdown(report))
    console.print(f"[bold green]Saved {jp} and {mp}[/bold green]")


def eval_cmd() -> None:
    parser = argparse.ArgumentParser(description="Run full RAG-SFAR ablation benchmark suite.")
    s = Settings()
    parser.add_argument("--index-root", type=Path, default=Path("index"))
    parser.add_argument("--benchmark-path", type=Path, default=s.benchmark_path)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"), help="legacy benchmark path only (no --suite)")
    parser.add_argument("--report-dir", type=Path, default=Path("reports/eval"), help="folder of the --suite reports (.json and .md)")
    parser.add_argument("--reranker-provider", default=s.reranker_provider)
    parser.add_argument("--reranker-model", default=s.reranker_model)
    # --- Unified harness (eval/README.md). Without --suite the legacy ablation below runs. ---
    parser.add_argument("--suite", default=None, help="Suite name from eval/ or eval_internal/, or 'full'.")
    parser.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    parser.add_argument("--configs", default="all", help="Comma list, e.g. C0,C6,C8 (prefix or full name).")
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--backend", choices=["mlx", "openai"], default="mlx")
    parser.add_argument("--mlx-model-path", default="")
    parser.add_argument("--model", default=s.llm_model)
    parser.add_argument("--base-url", default=s.llm_base_url)
    parser.add_argument("--api-key", default=s.llm_api_key)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--gen-mode", default="auto", help="Prompt mode for open questions ('auto' = clinical_detailed); questions with lettered options are routed by the engine to clinical_mcq.")
    parser.add_argument("--gen-preset", default="", help="Generation settings preset (legacy, small, wide; see generation/settings.py). Empty = historical behaviour.")
    parser.add_argument("--gen", default="", help="GenerationConfig overrides 'field=value+field=value', e.g. enable_thinking=false+max_context_chars=20000.")
    parser.add_argument("--tag", default="")
    parser.add_argument("--allow-test", action="store_true", help="Required to evaluate the locked test split.")
    parser.add_argument("--baseline", choices=["constant"], default=None, help="Score a corpus-free baseline instead of configs.")
    parser.add_argument("--index-map", default="", help="strategy=folder pairs to load another index for a chunking strategy, e.g. table_aware_sota=tas_qwen3emb06")
    parser.add_argument("--reranker", dest="reranker_override", default="", help="Override reranker model for this run.")
    parser.add_argument("--ablate", default="", help="Comma list of RetrievalConfig flags/fields: one variant of the first config per item (flag=false or field=value).")
    args = parser.parse_args()

    if args.suite:
        _run_unified_eval(args)
        return

    reranker = (
        build_reranker(args.reranker_provider, args.reranker_model)
        if args.reranker_provider != "none"
        else None
    )

    retrievers: dict[str, SfarRagRetriever] = {}
    embedder_cache: dict[tuple[str, str], object] = {}

    for strat in ("naive_fixed", "hierarchical_markdown", "table_aware_sota"):
        idx_dir = args.index_root / strat
        if not (idx_dir / "metadata.sqlite").exists():
            console.print(f"[yellow]Skipping missing index: {idx_dir}[/yellow]")
            continue
        store = LocalVectorStore.load(idx_dir)
        emb = None
        if store.embeddings is not None:
            prov = store.manifest.get("embedding_provider", s.embedding_provider)
            mod = store.manifest.get("embedding_model", s.embedding_model)
            key = (prov, mod)
            if prov == "tfidf_svd":
                emb = build_embedder(provider=prov, model_name=mod, index_dir=idx_dir)
            else:
                if key not in embedder_cache:
                    embedder_cache[key] = build_embedder(provider=prov, model_name=mod)
                emb = embedder_cache[key]
        retrievers[strat] = SfarRagRetriever(store=store, embedder=emb, reranker=reranker)

    datasets = {
        "antibioprophylaxie_171": load_antibioprophylaxie_benchmark(args.benchmark_path),
        "multi_rfe_stress_30": load_multi_rfe_stress_benchmark(),
    }
    configs = build_standard_ablation_configs()
    results = run_ablation_suite(retrievers, datasets, configs=configs)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "ablation_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = format_ablation_markdown(results)
    (args.output_dir / "ablation_report.md").write_text(md, encoding="utf-8")

    # Pretty console table
    for ds_name, rows in results.items():
        tbl = Table(title=f"Ablation Results — {ds_name}")
        for col in ["Config", "Ed.Hit@8", "Obsol.%", "Ev.Rec", "Allerg.Rec", "MRR", "ms", "~Tok"]:
            tbl.add_column(col)
        for r in rows:
            ev = f"{r['evidence_recall']*100:.1f}%" if r["evidence_recall"] is not None else "—"
            al = (
                f"{r['allergy_evidence_recall']*100:.1f}%"
                if r["allergy_evidence_recall"] is not None
                else "—"
            )
            tbl.add_row(
                r["config_name"],
                f"{r['current_edition_hit_rate']*100:.1f}%",
                f"{r['obsolete_intrusion_rate']*100:.1f}%",
                ev,
                al,
                f"{r['mrr_current_edition']:.3f}",
                f"{r['avg_latency_ms']:.1f}",
                f"{int(r['est_context_tokens'])}",
            )
        console.print(tbl)
    console.print(f"[bold green]Saved reports to {args.output_dir}/ablation_report.md[/bold green]")


def serve_cmd() -> None:
    import uvicorn

    from rag_sfar.interfaces.api import create_app

    s = Settings()
    parser = argparse.ArgumentParser(description="Start RAG-SFAR Demonstrator & OpenAI API server.")
    # Default: the serving profile's index (RAG_SFAR_INDEX_DIR environment variable, else the
    # PRODUCTION profile's index/tas_v6), not Settings.index_dir, so that the evaluated index is served.
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--host", default=s.api_host)
    parser.add_argument("--port", type=int, default=s.api_port)
    parser.add_argument("--no-llm", action="store_true", help="Start in retrieval-only mode.")
    parser.add_argument("--mlx-model", default=None, help="Optional local Apple Silicon MLX model path/repo.")
    args = parser.parse_args()

    app = create_app(
        index_dir=args.index_dir,
        settings=s,
        enable_llm=not args.no_llm,
        mlx_model_path=args.mlx_model,
    )
    uvicorn.run(app, host=args.host, port=args.port)
