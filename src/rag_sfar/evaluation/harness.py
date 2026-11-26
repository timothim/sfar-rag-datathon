"""Unified evaluation harness: one command, any suite/split, retrieval + generation metrics,
bootstrap confidence intervals, JSON + Markdown reports.

    rag-sfar-eval --suite full --split dev [--configs C0,C8] [--retrieval-only]
                  [--backend mlx --mlx-model-path P | --backend openai --base-url U --model M]

Metric levels (see eval/README.md):
- retrieval: doc hit@k / recall@k / MRR / nDCG@k against `gold_doc_ids`; passage hit@k / MRR
  against `gold_passages` (chunking-independent quote matching); obsolete-edition intrusion;
  legacy answer-term presence (lenient, kept only for comparison with the original README).
- generation: deterministic `answer_key` scoring (MCQ letter, all_of / any_of terms, label),
  abstention correctness, sourcing rate. LLM-judge metrics are added by `judge.py`.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import random
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

from rag_sfar.config import RetrievalConfig, Settings
from rag_sfar.evaluation.datasets import EvalItem, fold, load_suite, tokens
from rag_sfar.schemas import RetrievedChunk

K_DEFAULT = 8

# ---------------------------------------------------------------- statistics


def bootstrap_ci(values: list[float], n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean. Returns (nan, nan) on empty input."""
    vals = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not vals:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(vals)
    means = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return (means[int(alpha / 2 * n_boot)], means[int((1 - alpha / 2) * n_boot) - 1])


def paired_bootstrap_diff(a: list[float], b: list[float], n_boot: int = 2000, seed: int = 0) -> dict[str, float]:
    """Mean difference b - a over paired items, its 95 % CI and the share of resamples where b <= a."""
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if not pairs:
        return {"diff": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"), "p_le_zero": float("nan")}
    rng = random.Random(seed)
    n = len(pairs)
    diffs = []
    for _ in range(n_boot):
        s = [pairs[rng.randrange(n)] for _ in range(n)]
        diffs.append(sum(y - x for x, y in s) / n)
    diffs.sort()
    return {
        "diff": sum(y - x for x, y in pairs) / n,
        "ci_low": diffs[int(0.025 * n_boot)],
        "ci_high": diffs[int(0.975 * n_boot) - 1],
        "p_le_zero": sum(1 for d in diffs if d <= 0) / n_boot,
    }


# ---------------------------------------------------------------- retrieval metrics


def _shingles(toks: list[str], n: int = 3) -> set[tuple[str, ...]]:
    if len(toks) < n:
        return {tuple(toks)} if toks else set()
    return {tuple(toks[i : i + n]) for i in range(len(toks) - n + 1)}


def passage_match(quote: str, chunk_text: str, threshold: float = 0.5) -> bool:
    """True if at least `threshold` of the quote's word trigrams occur in the chunk.

    Independent of chunk boundaries and robust to OCR whitespace / accents."""
    q = _shingles(tokens(quote))
    if not q:
        return False
    c = _shingles(tokens(chunk_text))
    return len(q & c) / len(q) >= threshold


def retrieval_metrics(item: EvalItem, retrieved: list[RetrievedChunk], k: int = K_DEFAULT) -> dict[str, Any]:
    top = retrieved[:k]
    out: dict[str, Any] = {}
    gold_docs = set(item.gold_doc_ids)
    if gold_docs:
        rels = [1 if rc.chunk.doc_id in gold_docs else 0 for rc in top]
        first = next((i for i, r in enumerate(rels) if r), None)
        out["doc_hit"] = 1.0 if first is not None else 0.0
        out["doc_mrr"] = 1.0 / (first + 1) if first is not None else 0.0
        out["doc_recall"] = len({rc.chunk.doc_id for rc in top} & gold_docs) / len(gold_docs)
        dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rels))
        idcg = sum(1 / math.log2(i + 2) for i in range(min(k, len(top) or k)))
        out["doc_ndcg"] = dcg / idcg if idcg else 0.0
    if item.gold_passages:
        hits = []
        for i, rc in enumerate(top):
            text = rc.chunk.text
            if any(passage_match(gp.quote, text) for gp in item.gold_passages if gp.doc_id in ("", rc.chunk.doc_id) or True):
                hits.append(i)
        out["passage_hit"] = 1.0 if hits else 0.0
        out["passage_mrr"] = 1.0 / (hits[0] + 1) if hits else 0.0
        covered = sum(
            1 for gp in item.gold_passages if any(passage_match(gp.quote, rc.chunk.text) for rc in top)
        )
        out["passage_recall"] = covered / len(item.gold_passages)
    if item.current_edition_required and not item.should_abstain:
        out["obsolete_intrusion"] = 1.0 if any(not rc.chunk.is_latest_edition for rc in top) else 0.0
    terms = item.answer_key.get("all_of") or ([item.answer_key["label"]] if "label" in item.answer_key else [])
    if terms:
        blob = fold(" ".join(rc.chunk.text for rc in top))
        out["answer_terms_in_context"] = 1.0 if all(fold(t) in blob for t in terms) else 0.0
    return out


# ---------------------------------------------------------------- generation scoring

_ABSTAIN_PATTERNS = [
    r"ne (?:couvre|traite|precise|mentionne|permet) pas",
    r"pas (?:d'information|de recommandation|d'element|de donnee)s?",
    r"aucune? (?:information|recommandation|donnee|element)",
    r"je ne (?:peux|sais) pas",
    r"hors (?:du )?(?:perimetre|champ)",
    r"n'est pas (?:couvert|aborde|traite)",
    r"ne figure pas",
    r"insuffisant",
]


def is_abstention(answer: str) -> bool:
    a = fold(answer)
    return any(re.search(p, a) for p in _ABSTAIN_PATTERNS)


def extract_mcq_letter(answer: str) -> str | None:
    """Robust letter extraction. Case-sensitive on purpose: the French verb « a » is not « A »."""
    m = re.search(r"r[ée]ponse\s*(?:correcte|exacte)?\s*(?:est)?\s*[:：]?\s*\(?([A-D])\b", answer, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"(?m)^\s*\**\(?([A-D])[\).:\]]", answer)
    if m:
        return m.group(1)
    m = re.search(r"(?<![A-Za-zÀ-ÿ'’])([A-D])(?![A-Za-zÀ-ÿ'’])", answer)
    return m.group(1) if m else None


def score_answer(item: EvalItem, answer: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    key = item.answer_key
    a = fold(answer)
    abst = is_abstention(answer)
    if item.should_abstain:
        out["abstention_correct"] = 1.0 if abst or ("label" in key and fold(key["label"]) in a) else 0.0
    else:
        out["false_abstention"] = 1.0 if abst else 0.0
    if "mcq" in key:
        out["correct"] = 1.0 if extract_mcq_letter(answer) == key["mcq"] else 0.0
    elif "all_of" in key:
        out["correct"] = 1.0 if all(fold(t) in a for t in key["all_of"]) else 0.0
    elif "any_of" in key:
        out["correct"] = 1.0 if any(fold(t) in a for t in key["any_of"]) else 0.0
    elif "label" in key:
        out["correct"] = 1.0 if fold(key["label"]) in a else 0.0
    out["sourced"] = 1.0 if re.search(r"\[S\d+\]", answer) else 0.0
    return out


# ---------------------------------------------------------------- loading systems


def load_retrievers(index_root: Path, strategies: Iterable[str], reranker_provider: str, reranker_model: str, device: str | None = None):
    from rag_sfar.retrieval.embedder import build_embedder
    from rag_sfar.retrieval.pipeline import SfarRagRetriever
    from rag_sfar.retrieval.reranker import build_reranker
    from rag_sfar.retrieval.vector_store import LocalVectorStore

    s = Settings()
    reranker = build_reranker(reranker_provider, reranker_model, device=device) if reranker_provider != "none" else None
    cache: dict[tuple[str, str], Any] = {}
    out = {}
    for strat in strategies:
        idx = index_root / strat
        if not (idx / "metadata.sqlite").exists():
            continue
        store = LocalVectorStore.load(idx)
        emb = None
        if store.embeddings is not None:
            prov = store.manifest.get("embedding_provider", s.embedding_provider)
            mod = store.manifest.get("embedding_model", s.embedding_model)
            if prov == "tfidf_svd":
                emb = build_embedder(provider=prov, model_name=mod, index_dir=idx)
            else:
                if (prov, mod) not in cache:
                    cache[(prov, mod)] = build_embedder(provider=prov, model_name=mod, device=device)
                emb = cache[(prov, mod)]
        out[strat] = SfarRagRetriever(store=store, embedder=emb, reranker=reranker)
    return out


def select_configs(spec: str) -> list[RetrievalConfig]:
    from rag_sfar.evaluation.ablation import build_standard_ablation_configs

    all_cfgs = build_standard_ablation_configs()
    if not spec or spec == "all":
        return all_cfgs
    wanted = [w.strip() for w in spec.split(",") if w.strip()]
    out = []
    for w in wanted:
        match = [c for c in all_cfgs if c.name == w or c.name.split("_")[0] == w]
        if not match:
            raise SystemExit(f"Unknown config {w!r}; known: {[c.name for c in all_cfgs]}")
        out.extend(match)
    return out


# ---------------------------------------------------------------- run


def _aggregate(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    vals = [r[key] for r in rows if key in r]
    if not vals:
        return None
    lo, hi = bootstrap_ci(vals)
    return {"mean": sum(vals) / len(vals), "ci_low": lo, "ci_high": hi, "n": len(vals)}


METRIC_KEYS = [
    "doc_hit", "doc_mrr", "doc_recall", "doc_ndcg",
    "passage_hit", "passage_mrr", "passage_recall",
    "obsolete_intrusion", "answer_terms_in_context",
    "correct", "abstention_correct", "false_abstention", "sourced",
]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"n": len(rows)}
    for k in METRIC_KEYS + ["latency_ms"]:
        agg = _aggregate(rows, k)
        if agg:
            summary[k] = agg
    for facet in ("provenance", "question_type", "suite"):
        groups: dict[str, list] = defaultdict(list)
        for r in rows:
            groups[r[facet]].append(r)
        if len(groups) > 1:
            summary[f"by_{facet}"] = {
                g: {k: _aggregate(rs, k) for k in METRIC_KEYS if _aggregate(rs, k)} | {"n": len(rs)}
                for g, rs in sorted(groups.items())
            }
    tag_groups: dict[str, list] = defaultdict(list)
    for r in rows:
        for t in r["tags"]:
            tag_groups[t].append(r)
    if tag_groups:
        summary["by_tag"] = {
            t: {k: _aggregate(rs, k) for k in METRIC_KEYS if _aggregate(rs, k)} | {"n": len(rs)}
            for t, rs in sorted(tag_groups.items())
        }
    return summary


def run_config(
    items: list[EvalItem],
    cfg: RetrievalConfig,
    retriever,
    k: int = K_DEFAULT,
    answer_fn: Callable[[EvalItem, RetrievalConfig], dict[str, Any]] | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for i, item in enumerate(items):
        t0 = time.perf_counter()
        row: dict[str, Any] = {
            "id": item.id, "suite": item.suite, "provenance": item.provenance,
            "question_type": item.question_type, "tags": item.tags,
        }
        if answer_fn is None:
            retrieved, _analysis, _t = retriever.retrieve(item.formatted_query(), config=cfg)
            row.update(retrieval_metrics(item, retrieved, k))
            row["retrieved"] = [(rc.chunk.doc_id, rc.chunk.chunk_id) for rc in retrieved[:k]]
        else:
            gen = answer_fn(item, cfg)
            row.update(retrieval_metrics(item, gen["retrieved"], k))
            row.update(score_answer(item, gen["answer"]))
            row["answer"] = gen["answer"]
            row["retrieved"] = [(rc.chunk.doc_id, rc.chunk.chunk_id) for rc in gen["retrieved"][:k]]
            row["usage"] = gen.get("usage", {})
        row["latency_ms"] = (time.perf_counter() - t0) * 1000
        rows.append(row)
        if progress and (i + 1) % 25 == 0:
            progress(f"{cfg.name}: {i + 1}/{len(items)}")
    return rows


def _fmt(agg: dict[str, Any] | None, pct: bool = True) -> str:
    if not agg:
        return "—"
    if pct:
        return f"{agg['mean'] * 100:.1f} [{agg['ci_low'] * 100:.0f}–{agg['ci_high'] * 100:.0f}]"
    return f"{agg['mean']:.3f} [{agg['ci_low']:.2f}–{agg['ci_high']:.2f}]"


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Évaluation — suite `{report['suite']}`, split `{report['split']}`",
        "",
        f"Date : {report['timestamp']}. Questions : {report['n_items']}. k = {report['k']}. "
        f"Générateur : {report.get('generator') or 'aucun (retrieval seul)'}.",
        "",
        "Valeurs : moyenne en %, IC bootstrap 95 % entre crochets.",
        "",
    ]
    cols = [
        ("doc_hit", "Doc hit@k", True), ("doc_mrr", "Doc MRR", False), ("passage_hit", "Passage hit@k", True),
        ("passage_mrr", "Passage MRR", False), ("obsolete_intrusion", "Intrusion obsolète", True),
        ("answer_terms_in_context", "Termes réponse (laxiste)", True), ("correct", "Exactitude", True),
        ("abstention_correct", "Abstention correcte", True), ("false_abstention", "Fausse abstention", True),
        ("sourced", "Sourcé", True), ("latency_ms", "Latence ms", None),
    ]
    present = [c for c in cols if any(c[0] in r["summary"] for r in report["runs"])]
    lines.append("| Config | " + " | ".join(c[1] for c in present) + " |")
    lines.append("|---|" + "---:|" * len(present))
    for run in report["runs"]:
        cells = []
        for key, _label, pct in present:
            agg = run["summary"].get(key)
            if key == "latency_ms":
                cells.append(f"{agg['mean']:.0f}" if agg else "—")
            else:
                cells.append(_fmt(agg, pct))
        lines.append(f"| `{run['config']}` | " + " | ".join(cells) + " |")
    for run in report["runs"]:
        for facet in ("by_provenance", "by_suite", "by_tag"):
            if facet in run["summary"]:
                lines += ["", f"### `{run['config']}` — {facet.replace('by_', 'par ')}", ""]
                lines.append("| Groupe | n | " + " | ".join(c[1] for c in present if c[0] != "latency_ms") + " |")
                lines.append("|---|---:|" + "---:|" * len([c for c in present if c[0] != "latency_ms"]))
                for g, aggs in run["summary"][facet].items():
                    lines.append(
                        f"| {g} | {aggs['n']} | "
                        + " | ".join(_fmt(aggs.get(c[0]), c[2]) for c in present if c[0] != "latency_ms")
                        + " |"
                    )
    if report.get("comparisons"):
        lines += ["", "## Comparaisons appariées (bootstrap)", "", "| Métrique | A | B | B − A | IC 95 % | P(B ≤ A) |", "|---|---|---|---:|---|---:|"]
        for c in report["comparisons"]:
            lines.append(
                f"| {c['metric']} | `{c['a']}` | `{c['b']}` | {c['diff'] * 100:+.1f} pts | "
                f"[{c['ci_low'] * 100:+.1f} ; {c['ci_high'] * 100:+.1f}] | {c['p_le_zero']:.3f} |"
            )
    return "\n".join(lines) + "\n"


def run_eval(
    suite: str,
    split: str,
    configs: list[RetrievalConfig],
    retrievers: dict[str, Any],
    k: int = K_DEFAULT,
    answer_fn_factory: Callable[[Any], Callable] | None = None,
    generator_label: str = "",
    limit: int = 0,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    items = load_suite(suite, split)  # type: ignore[arg-type]
    if limit:
        items = items[:limit]
    runs = []
    for cfg in configs:
        retriever = retrievers.get(cfg.chunking_strategy)
        if retriever is None:
            if progress:
                progress(f"skip {cfg.name}: missing index {cfg.chunking_strategy}")
            continue
        answer_fn = answer_fn_factory(retriever) if answer_fn_factory else None
        rows = run_config(items, cfg, retriever, k=k, answer_fn=answer_fn, progress=progress)
        runs.append({"config": cfg.name, "config_params": (cfg.model_dump() if hasattr(cfg, "model_dump") else dataclasses.asdict(cfg)), "summary": summarize(rows), "rows": rows})
    comparisons = []
    if len(runs) >= 2:
        base = runs[0]
        for other in runs[1:]:
            for metric in ("passage_hit", "doc_hit", "correct", "obsolete_intrusion"):
                a = {r["id"]: r.get(metric) for r in base["rows"]}
                b = {r["id"]: r.get(metric) for r in other["rows"]}
                ids = [i for i in a if a[i] is not None and b.get(i) is not None]
                if ids:
                    res = paired_bootstrap_diff([a[i] for i in ids], [b[i] for i in ids])
                    comparisons.append({"metric": metric, "a": base["config"], "b": other["config"], **res})
    return {
        "suite": suite,
        "split": split,
        "k": k,
        "n_items": len(items),
        "generator": generator_label,
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "runs": runs,
        "comparisons": comparisons,
    }


def save_report(report: dict[str, Any], out_dir: Path = Path("reports/eval"), tag: str = "") -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = out_dir / f"{stamp}_{report['suite']}_{report['split']}{('_' + tag) if tag else ''}"
    jp, mp = base.with_suffix(".json"), base.with_suffix(".md")
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    mp.write_text(to_markdown(report), encoding="utf-8")
    return jp, mp
