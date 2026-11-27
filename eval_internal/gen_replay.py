"""Generation replay: cache the retrieval output once per question, then run any number of
generation variants on the cache without loading the embedder and the reranker again.

Generalises frontier_generator.py (any config, --ablate string, index map, prompt mode, id list,
local MLX / OpenAI-compatible backend, or prompt capture for the Claude stand-in).

    # 0. fixed, seeded, stratified iteration subsets of the dev splits (ids in eval_internal/work/b3_subsets/)
    .venv/bin/python eval_internal/gen_replay.py subsets --suites abpe171,multirfe_synth --n 30

    # 1. cache retrieval (one model load; run under scripts/with_gpu_lock.sh)
    .venv/bin/python eval_internal/gen_replay.py capture --suite abpe171 --configs C9 \
        --ablate "final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000" \
        --index-map table_aware_sota=tas_v3_errata --ids-file eval_internal/work/b3_subsets/abpe171_iter.json --name c9wide

    # 2. run a generation variant on the cache (scores: deterministic keys, abstention, sourcing,
    #    verifier; report readable by judge_io export)
    .venv/bin/python eval_internal/gen_replay.py run --cache c9wide --suite abpe171 --preset wide \
        --gen "context_order=document" --gen-mode clinical_concise --backend mlx \
        --mlx-model-path /Users/tim/.cache/rag_sfar_models/Qwen3.5-9B-MLX-4bit-nothink --model qwen3.5-9b --tag v1

    # 2b. same, but only record the prompts (context size in chars and tokens, no LLM); with
    #     --export-frontier the prompts are written for the Claude stand-in
    .venv/bin/python eval_internal/gen_replay.py run ... --backend record [--export-frontier DIR --parts 4]
    # 3. build the report from the stand-in's answers (DIR/gen_out_*.json)
    .venv/bin/python eval_internal/gen_replay.py import-frontier --dir DIR --model-label claude-sonnet-5-5

Caches live in eval_internal/work/replay/<name>/ (git-ignored data, derived from the corpus).
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import random
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_sfar.config import RetrievalConfig, Settings  # noqa: E402
from rag_sfar.evaluation import harness  # noqa: E402
from rag_sfar.evaluation.datasets import EvalItem, fold, load_suite  # noqa: E402
from rag_sfar.schemas import QueryAnalysis, RetrievedChunk  # noqa: E402

WORK = ROOT / "eval_internal/work"
REPLAY = WORK / "replay"
SUBSETS = WORK / "b3_subsets"
SEED = 20261127

# Deterministic proxy keys: abpe171 shares its ids and questions with abp171, whose answer keys
# (molecule terms, "no prophylaxis" label, MCQ letter) give a judge-free signal for iteration.
PROXY_KEY_SUITE = {"abpe171": "abp171"}
_NO_PROPHYLAXIS = re.compile(
    r"(pas d'antibioprophylaxie|aucune antibioprophylaxie|antibioprophylaxie (?:n'est|n est) pas"
    r"|sans antibioprophylaxie|pas recommande[e]? d'antibioprophylaxie|ne pas (?:realiser|faire|administrer) d'antibioprophylaxie"
    r"|antibioprophylaxie : non|pas d'abp)"
)


def _git_rev() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return ""


def _load_ids(path: str | None) -> list[str] | None:
    """Ids from one file or a comma list of files (union)."""
    if not path:
        return None
    ids: list[str] = []
    for one in path.split(","):
        data = json.loads(Path(one).read_text(encoding="utf-8"))
        ids += data["ids"] if isinstance(data, dict) else data
    return ids


def _items(suite: str, ids: list[str] | None) -> list[EvalItem]:
    items = load_suite(suite, "dev")
    if ids is not None:
        keep = set(ids)
        items = [it for it in items if it.id in keep]
    return items


# ---------------------------------------------------------------- subsets


def _strata(it: EvalItem) -> str:
    return f"{it.question_type}|{it.expected_behavior or ''}"


def make_subsets(suites: list[str], n: int, min_per_stratum: int = 3) -> None:
    """Seeded stratified subset per suite (question type x expected behaviour), proportional
    allocation with a floor; the rest of dev is kept for one confirmation run."""
    SUBSETS.mkdir(parents=True, exist_ok=True)
    for suite in suites:
        items = load_suite(suite, "dev")
        groups: dict[str, list[EvalItem]] = defaultdict(list)
        for it in items:
            groups[_strata(it)].append(it)
        rng = random.Random(f"{SEED}-{suite}")
        alloc = {g: max(min(min_per_stratum, len(v)), round(n * len(v) / len(items))) for g, v in groups.items()}
        while sum(alloc.values()) > n:  # trim the largest strata
            g = max(alloc, key=lambda k: alloc[k] - min_per_stratum)
            alloc[g] -= 1
        chosen = []
        for g, v in sorted(groups.items()):
            v = sorted(v, key=lambda it: it.id)
            rng.shuffle(v)
            chosen += [it.id for it in v[: alloc[g]]]
        rest = [it.id for it in items if it.id not in set(chosen)]
        meta = {"suite": suite, "split": "dev", "seed": SEED, "strata": {g: alloc[g] for g in sorted(alloc)}}
        (SUBSETS / f"{suite}_iter.json").write_text(json.dumps({**meta, "ids": sorted(chosen)}, indent=1), encoding="utf-8")
        (SUBSETS / f"{suite}_confirm.json").write_text(json.dumps({**meta, "ids": sorted(rest)}, indent=1), encoding="utf-8")
        print(f"{suite}: iter {len(chosen)} / confirm {len(rest)}  strata {meta['strata']}")


# ---------------------------------------------------------------- capture


def _retrieval_config(configs: str, ablate: str) -> RetrievalConfig:
    cfg = harness.select_configs(configs)[0]
    if ablate:
        cfg = harness.ablation_variants(cfg, ablate)[0]
    return cfg


def capture(suite: str, configs: str, ablate: str, index_map: str, ids_file: str | None, name: str, device: str) -> None:
    s = Settings()
    cfg = _retrieval_config(configs, ablate)
    imap = dict(kv.split("=", 1) for kv in index_map.split(",") if kv.strip())
    retriever = harness.load_retrievers(
        ROOT / "index", [cfg.chunking_strategy], s.reranker_provider, s.reranker_model, device=device, index_map=imap
    )[cfg.chunking_strategy]
    items = _items(suite, _load_ids(ids_file))
    out = REPLAY / name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with (out / f"{suite}.jsonl").open("w", encoding="utf-8") as f:
        for it in items:
            retrieved, analysis, timings = retriever.retrieve(it.formatted_query(), config=cfg)
            f.write(json.dumps({
                "id": it.id, "query": it.formatted_query(),
                "retrieved": [rc.model_dump() for rc in retrieved],
                "analysis": analysis.model_dump(), "timings": timings,
            }, ensure_ascii=False, default=str) + "\n")
    meta_p = out / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    meta.update({
        "config": cfg.name, "config_params": dataclasses.asdict(cfg), "ablate": ablate, "index_map": imap,
        "reranker_model": s.reranker_model, "git": _git_rev(),
    })
    meta.setdefault("suites", {})[suite] = {"n": len(items), "ids_file": ids_file or "", "captured": dt.datetime.now().isoformat(timespec="seconds")}
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"{len(items)} questions cached in {time.time() - t0:.0f}s -> {out}/{suite}.jsonl")


def load_cache(name: str, suite: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    d = REPLAY / name
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    rows = {}
    for line in (d / f"{suite}.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["id"]] = r
    return meta, rows


def config_from_meta(meta: dict[str, Any]) -> RetrievalConfig:
    names = {f.name for f in dataclasses.fields(RetrievalConfig)}
    return RetrievalConfig(**{k: v for k, v in meta["config_params"].items() if k in names})


# ---------------------------------------------------------------- scoring helpers


def proxy_correct(suite: str, item_id: str, answer: str, proxy_items: dict[str, EvalItem]) -> float | None:
    it = proxy_items.get(item_id)
    if it is None or not it.answer_key:
        return None
    key = it.answer_key
    a = fold(answer)
    if "mcq" in key:
        return 1.0 if harness.extract_mcq_letter(answer) == key["mcq"] else 0.0
    if "label" in key:
        return 1.0 if (fold(key["label"]) in a or _NO_PROPHYLAXIS.search(a)) else 0.0
    if "all_of" in key:
        return 1.0 if all(fold(t) in a for t in key["all_of"]) else 0.0
    return None


class _Tok:
    """Prompt token counter (tokenizer of the generator family; None if unavailable)."""

    def __init__(self, path: str | None) -> None:
        self.tok = None
        if path:
            try:
                from transformers import AutoTokenizer

                self.tok = AutoTokenizer.from_pretrained(path)
            except Exception:
                self.tok = None

    def count(self, text: str) -> int | None:
        return len(self.tok.encode(text)) if self.tok else None


class RecordingLLM:
    """Stands in for the LLM: records each (system, user) prompt and answers with an abstention."""

    model = "recorder"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str, temperature=None, max_tokens=None, **_):
        self.calls.append((system_prompt, user_prompt))
        return "Les recommandations SFAR fournies ne traitent pas cette question.", {}


# ---------------------------------------------------------------- run


def _build_llm(args):
    from rag_sfar.generation.client import LocalMlxLLM, OpenAICompatibleLLM

    if args.backend == "record":
        return RecordingLLM()
    if args.backend == "mlx":
        return LocalMlxLLM(model_path=args.mlx_model_path or args.model, model_label=args.model,
                           temperature=0.0, max_tokens=args.max_tokens)
    s = Settings()
    return OpenAICompatibleLLM(base_url=args.base_url or s.llm_base_url, api_key=args.api_key or s.llm_api_key,
                               model=args.model, temperature=0.0, max_tokens=args.max_tokens)


def run(args) -> Path | None:
    from rag_sfar.generation.answer_check import check_answer
    from rag_sfar.generation.client import SfarRagEngine
    from rag_sfar.generation.settings import resolve_generation_config

    gen_cfg = resolve_generation_config(args.preset, args.gen)
    llm = _build_llm(args)
    engine = SfarRagEngine(retriever=None, llm=llm)
    tok = _Tok(args.tokenizer or (args.mlx_model_path if args.backend == "mlx" else DEFAULT_TOKENIZER))
    all_rows = []
    gen_inputs = []
    suites = args.suite.split(",")
    for suite in suites:
        meta, cache = load_cache(args.cache, suite)
        cfg = config_from_meta(meta)
        proxy = {it.id: it for it in load_suite(PROXY_KEY_SUITE[suite], "dev")} if suite in PROXY_KEY_SUITE else {}
        items = [it for it in _items(suite, _load_ids(args.ids_file)) if it.id in cache]
        if args.limit:
            items = items[: args.limit]
        for i, it in enumerate(items):
            c = cache[it.id]
            retrieved = [RetrievedChunk.model_validate(x) for x in c["retrieved"]]
            analysis = QueryAnalysis.model_validate(c["analysis"])
            mode = args.mcq_mode if it.question_type == "mcq" else args.gen_mode
            n_calls = len(getattr(llm, "calls", []))
            t0 = time.perf_counter()
            resp = engine.generate(it.formatted_query(), retrieved, analysis, c["timings"], mode=mode,
                                   config=cfg, gen_config=gen_cfg)
            lat = (time.perf_counter() - t0) * 1000
            row: dict[str, Any] = {"id": it.id, "suite": suite, "provenance": it.provenance,
                                   "question_type": it.question_type, "tags": it.tags}
            row.update(harness.retrieval_metrics(it, resp.retrieved_chunks, k=10**6))
            row.update(harness.score_answer(it, resp.answer))
            pc = proxy_correct(suite, it.id, resp.answer, proxy) if proxy else None
            if pc is not None:
                row["proxy_correct"] = pc
            v = resp.verification
            if v is not None:
                row["verifier_flag"] = 1.0 if (v.invalid_citations or v.ungrounded_molecules) else 0.0
                row["verification"] = v.model_dump()
            chk = check_answer(resp.answer, resp.retrieved_chunks, is_abstention=harness.is_abstention(resp.answer))
            row["check_flag"] = 1.0 if chk.flagged else 0.0
            row["answer_check"] = dataclasses.asdict(chk)
            row["check_regenerated"] = bool(resp.extra.get("answer_check_regenerated"))
            row["answer"] = resp.answer
            row["mode"] = resp.mode
            row["usage"] = resp.token_usage
            row["context_chars"] = resp.extra.get("context_chars")
            row["n_passages"] = resp.extra.get("n_passages")
            row["coverage_supported"] = resp.extra.get("coverage_supported")
            row["coverage_refused"] = bool(resp.extra.get("coverage_refused"))
            row["self_corrected"] = bool(resp.extra.get("self_corrected"))
            row["latency_ms"] = lat
            row["retrieved"] = [(rc.chunk.doc_id, rc.chunk.chunk_id) for rc in resp.retrieved_chunks]
            if args.backend == "record" and len(llm.calls) > n_calls:
                system, user = llm.calls[n_calls]
                row["prompt_chars"] = len(system) + len(user)
                pt = tok.count(system + "\n" + user)
                if pt is not None:
                    row["prompt_tokens"] = pt
                gen_inputs.append({"case_id": it.id, "suite": suite, "system": system, "user": user})
                row.pop("answer")  # placeholder answer, not scored
                for k in ("correct", "abstention_correct", "false_abstention", "sourced", "proxy_correct", "verifier_flag", "check_flag", "answer_check"):
                    row.pop(k, None)
            else:
                row["prompt_tokens"] = (resp.token_usage or {}).get("prompt_tokens")
                row["completion_tokens"] = (resp.token_usage or {}).get("completion_tokens")
            all_rows.append(row)
            if (i + 1) % 5 == 0:
                print(f"[{suite}] {i + 1}/{len(items)}", flush=True)
    if args.export_frontier:
        d = Path(args.export_frontier)
        d.mkdir(parents=True, exist_ok=True)
        size = -(-len(gen_inputs) // args.parts)
        for i in range(args.parts):
            (d / f"gen_input_{i}.json").write_text(json.dumps(gen_inputs[i * size:(i + 1) * size], ensure_ascii=False, indent=1), encoding="utf-8")
        (d / "replay_rows.json").write_text(json.dumps(all_rows, ensure_ascii=False, default=str), encoding="utf-8")
        (d / "meta.json").write_text(json.dumps({"cache": args.cache, "suites": suites, "gen_config": gen_cfg.to_dict(),
                                                 "gen_mode": args.gen_mode, "mcq_mode": args.mcq_mode,
                                                 "ids_file": args.ids_file}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(gen_inputs)} prompts -> {d}")
    return _save(args, gen_cfg, all_rows, suites, label=getattr(llm, "model", args.backend))


def _extra_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("proxy_correct", "verifier_flag", "check_flag", "context_chars", "prompt_tokens", "completion_tokens", "n_passages", "coverage_refused"):
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        if vals:
            lo, hi = harness.bootstrap_ci(vals)
            out[key] = {"mean": sum(vals) / len(vals), "ci_low": lo, "ci_high": hi, "n": len(vals),
                        "median": sorted(vals)[len(vals) // 2], "max": max(vals)}
    return out


def _save(args, gen_cfg, rows, suites, label: str) -> Path | None:
    reports = []
    for suite in suites:
        srows = [r for r in rows if r["suite"] == suite]
        meta, _ = load_cache(args.cache, suite)
        summary = harness.summarize(srows)
        summary.update(_extra_summary(srows))
        name = f"{meta['config']}|{gen_cfg.name}|{args.gen_mode}"
        rep = {
            "suite": suite, "split": "dev", "k": 0, "n_items": len(srows),
            "generator": f"{args.backend}:{label}", "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "replay": {"cache": args.cache, "cache_meta": {k: meta[k] for k in ("config", "ablate", "index_map", "git") if k in meta},
                       "gen_config": gen_cfg.to_dict(), "gen_mode": args.gen_mode, "mcq_mode": args.mcq_mode,
                       "ids_file": args.ids_file, "git": _git_rev()},
            "runs": [{"config": name, "config_params": gen_cfg.to_dict(), "summary": summary, "rows": srows}],
            "comparisons": [],
        }
        out_dir = ROOT / "reports/eval/b3"
        jp, _ = harness.save_report(rep, out_dir=out_dir, tag=f"b3_{args.tag}")
        reports.append(jp)
        s = summary
        def m(k):
            return f"{s[k]['mean'] * 100:.1f}" if k in s else "—"
        print(f"{suite}: n={len(srows)} correct={m('correct')} proxy={m('proxy_correct')} sourced={m('sourced')} "
              f"abst_ok={m('abstention_correct')} false_abst={m('false_abstention')} flag={m('verifier_flag')} "
              f"ctx_chars={s.get('context_chars', {}).get('mean', 0):.0f} prompt_tok={s.get('prompt_tokens', {}).get('mean', 0):.0f} "
              f"lat={s.get('latency_ms', {}).get('mean', 0) / 1000:.1f}s -> {jp}")
    return reports[-1] if reports else None


DEFAULT_TOKENIZER = "/Users/tim/.cache/rag_sfar_models/Qwen3.5-9B-MLX-4bit-nothink"


def import_frontier(d: Path, model_label: str, tag: str) -> None:
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    rows = json.loads((d / "replay_rows.json").read_text(encoding="utf-8"))
    answers = {}
    for f in sorted(d.glob("gen_out_*.json")):
        for a in json.loads(f.read_text(encoding="utf-8")):
            answers[a["case_id"]] = a["answer"]
    from rag_sfar.generation.client import _final_answer

    by_suite = defaultdict(list)
    for r in rows:
        if r["id"] not in answers:
            continue
        suite = r["suite"]
        it = {x.id: x for x in load_suite(suite, "dev")}[r["id"]]
        ans = _final_answer(answers[r["id"]], r.get("mode", ""))
        r.update(harness.score_answer(it, ans))
        if suite in PROXY_KEY_SUITE:
            proxy = {x.id: x for x in load_suite(PROXY_KEY_SUITE[suite], "dev")}
            pc = proxy_correct(suite, r["id"], ans, proxy)
            if pc is not None:
                r["proxy_correct"] = pc
        r["answer"] = ans
        by_suite[suite].append(r)
    for suite, srows in by_suite.items():
        summary = harness.summarize(srows)
        summary.update(_extra_summary(srows))
        rep = {"suite": suite, "split": "dev", "k": 0, "n_items": len(srows),
               "generator": f"{model_label} (Claude Code subagent, prompts captured by gen_replay)",
               "timestamp": dt.datetime.now().isoformat(timespec="seconds"), "replay": meta,
               "runs": [{"config": f"{meta['cache']}|{meta['gen_config']['name']}|{model_label}", "config_params": meta["gen_config"],
                         "summary": summary, "rows": srows}], "comparisons": []}
        jp, _ = harness.save_report(rep, out_dir=ROOT / "reports/eval/b3", tag=f"b3_{tag}_{model_label}")
        print(f"{suite}: {len(srows)} answers -> {jp}")


def compare(a_path: str, b_path: str, metrics: list[str]) -> None:
    """Paired bootstrap B - A over shared ids, for each metric present in both reports."""
    def rows(p):
        rep = json.loads(Path(p).read_text(encoding="utf-8"))
        return {r["id"]: r for r in rep["runs"][0]["rows"]}
    ra, rb = rows(a_path), rows(b_path)
    ids = sorted(set(ra) & set(rb))
    print(f"n={len(ids)}  A={Path(a_path).name}  B={Path(b_path).name}")
    for m in metrics:
        pairs = [(ra[i].get(m), rb[i].get(m)) for i in ids]
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        if not pairs:
            continue
        res = harness.paired_bootstrap_diff([float(x) for x, _ in pairs], [float(y) for _, y in pairs])
        ma = sum(float(x) for x, _ in pairs) / len(pairs)
        mb = sum(float(y) for _, y in pairs) / len(pairs)
        scale = 100 if m not in ("context_chars", "prompt_tokens", "completion_tokens", "latency_ms") else 1
        print(f"  {m:24s} A={ma * scale:8.1f}  B={mb * scale:8.1f}  B-A={res['diff'] * scale:+7.1f} [{res['ci_low'] * scale:+.1f} ; {res['ci_high'] * scale:+.1f}]  n={len(pairs)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("subsets")
    p.add_argument("--suites", default="abpe171,multirfe_synth")
    p.add_argument("--n", type=int, default=30)
    p = sub.add_parser("capture")
    p.add_argument("--suite", required=True)
    p.add_argument("--configs", default="C9")
    p.add_argument("--ablate", default="")
    p.add_argument("--index-map", default="table_aware_sota=tas_v3_errata")
    p.add_argument("--ids-file", default=None)
    p.add_argument("--name", required=True)
    p.add_argument("--device", default="cpu")
    p = sub.add_parser("run")
    p.add_argument("--cache", required=True)
    p.add_argument("--suite", required=True, help="one suite or a comma list")
    p.add_argument("--ids-file", default=None)
    p.add_argument("--preset", default="wide")
    p.add_argument("--gen", default="", help="GenerationConfig overrides, 'field=value+field=value'")
    p.add_argument("--gen-mode", default="clinical_concise")
    p.add_argument("--mcq-mode", default="benchmark_mcq")
    p.add_argument("--backend", choices=["mlx", "openai", "record"], default="mlx")
    p.add_argument("--mlx-model-path", default="")
    p.add_argument("--model", default="qwen3.5-9b-4bit-nothink")
    p.add_argument("--base-url", default="")
    p.add_argument("--api-key", default="")
    p.add_argument("--max-tokens", type=int, default=400)
    p.add_argument("--tokenizer", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--tag", required=True)
    p.add_argument("--export-frontier", default="")
    p.add_argument("--parts", type=int, default=4)
    p = sub.add_parser("import-frontier")
    p.add_argument("--dir", required=True)
    p.add_argument("--model-label", required=True)
    p.add_argument("--tag", default="frontier")
    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--metrics", default="correct,proxy_correct,judge_correct,judge_serious_error,judge_behavior_ok,abstention_correct,false_abstention,sourced,verifier_flag,prompt_tokens,latency_ms")
    a = ap.parse_args()
    if a.cmd == "subsets":
        make_subsets(a.suites.split(","), a.n)
    elif a.cmd == "capture":
        capture(a.suite, a.configs, a.ablate, a.index_map, a.ids_file, a.name, a.device)
    elif a.cmd == "run":
        run(a)
    elif a.cmd == "import-frontier":
        import_frontier(Path(a.dir), a.model_label, a.tag)
    else:
        compare(a.a, a.b, a.metrics.split(","))
