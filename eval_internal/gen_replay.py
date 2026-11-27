"""Generation replay: cache the retrieval output once per question, then run any number of
generation variants on the cache without loading the embedder and the reranker again.

    # 1. cache retrieval (one model load; run under scripts/with_gpu_lock.sh). Retrieval
    #    configuration and index are explicit: --profile production, or --configs + --index-map.
    .venv/bin/python eval_internal/gen_replay.py capture --suite abpe171 --profile production --name c10notes_v6
    # the sealed test split needs --split test --allow-test (lockbox verified first)

    # 1b. retrieval variants (default: none = the frozen, evaluated retrieval). The steps that
    #     call a language model (normalize, decompose) use the endpoint given here, through the
    #     client the API uses (interfaces/robustness.py composes the variant exactly as served).
    .venv/bin/python eval_internal/gen_replay.py capture --suite multirfe_synth --profile production \
        --robustness normalize --decompose --backend openai --base-url URL --model M --name c10_norm_dec
    #     --robustness: none | lexical | normalize | both ; --decompose: multi-query "decompose".
    #     Each cache row records what the steps did (pre_retrieval), meta.json the variant and model.

    # 2. a generation run on the cache: --profile production = exactly the served generation
    #    (generation/profile.py); or an explicit --preset/--gen/--gen-mode for ablations.
    .venv/bin/python eval_internal/gen_replay.py run --cache c10notes_v6 --suite abpe171,multirfe_synth \
        --profile production --backend openai --base-url URL --model M --tag final

    # 2b. prompts only (sizes in chars and tokens), and a blind export for stand-in generators:
    #     opaque ids, part_NN/ folders of <= 8 cases, mapping kept in work/replay/frontier_keys/.
    .venv/bin/python eval_internal/gen_replay.py run ... --backend record --export-frontier DIR
    # 3. map the stand-in's answers back (alignment checks, answer check), one report per suite
    .venv/bin/python eval_internal/gen_replay.py import-frontier --dir DIR --model-label claude-sonnet-5-5

Dev-only helpers: `subsets` (seeded iteration subsets), proxy answer keys (disabled outside dev).
Caches live in eval_internal/work/replay/<name>/ (git-ignored data, derived from the corpus).
Instructions for stand-in agents: eval_internal/GENERATOR_INSTRUCTIONS.md.
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


def check_split(split: str, allow_test: bool) -> None:
    """Same safeguard as rag-sfar-eval: the sealed test split needs --allow-test and a valid
    lockbox (hashes of the sealed files checked before anything is read)."""
    if split not in ("dev", "test"):
        raise SystemExit(f"unknown split {split!r}")
    if split == "test":
        if not allow_test:
            raise SystemExit("The test split is locked: evaluate it only on final configs, with --allow-test.")
        from rag_sfar.evaluation.datasets import verify_lockbox

        verify_lockbox(raise_on_error=True)


def _items(suite: str, ids: list[str] | None, split: str = "dev") -> list[EvalItem]:
    items = load_suite(suite, split)
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


def cache_file(name: str, suite: str, split: str) -> Path:
    return REPLAY / name / (f"{suite}.jsonl" if split == "dev" else f"{suite}_{split}.jsonl")


def capture(suite: str, configs: str, ablate: str, index_map: str, ids_file: str | None, name: str, device: str,
            split: str = "dev", robustness: str = "none", decompose: bool = False, llm: Any = None,
            llm_label: str = "") -> None:
    """Cache the retrieval output of every question. `robustness` / `decompose` select the
    retrieval variant (interfaces/robustness.py::compose, the composition the API serves);
    with the defaults the frozen retriever and configuration are used unchanged."""
    from rag_sfar.interfaces import robustness as rob

    s = Settings()
    base_cfg = _retrieval_config(configs, ablate)
    imap = dict(kv.split("=", 1) for kv in index_map.split(",") if kv.strip())
    base = harness.load_retrievers(
        ROOT / "index", [base_cfg.chunking_strategy], s.reranker_provider, s.reranker_model, device=device, index_map=imap
    )[base_cfg.chunking_strategy]
    if (rob.needs_llm(robustness) or decompose) and llm is None:
        raise SystemExit("--robustness normalize|both and --decompose call a language model: give --backend openai|mlx")
    variants = rob.RobustnessVariants(base, base_cfg)
    cfg = variants.retrieval_config(robustness)
    items = _items(suite, _load_ids(ids_file), split)
    out = REPLAY / name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    n_norm = n_norm_err = n_dec = n_dec_err = 0
    with cache_file(name, suite, split).open("w", encoding="utf-8") as f:
        for it in items:
            comp = rob.compose(variants, robustness, decompose, llm)
            retrieved, analysis, timings = comp.retriever.retrieve(it.formatted_query(), config=cfg)
            row = {"id": it.id, **cache_row(it.formatted_query(), retrieved, analysis, timings)}
            if not comp.frozen:  # rows of the frozen retrieval stay exactly as before
                md = comp.metadata()
                row["pre_retrieval"] = md
                nz, dc = md["normalization"] or {}, md["decomposition"] or {}
                n_norm += bool(nz.get("used"))
                n_norm_err += bool(nz.get("error"))
                n_dec += bool(dc.get("fired"))
                n_dec_err += bool(dc.get("error"))
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    meta_p = out / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    index_dirs = {k: str((ROOT / "index" / v).relative_to(ROOT)) for k, v in imap.items()}
    meta.update({
        "config": cfg.name, "config_params": dataclasses.asdict(cfg), "ablate": ablate, "index_map": imap,
        "index_dirs": index_dirs, "base_config": _strip_ablation(base_cfg.name, ablate),
        "reranker_model": s.reranker_model, "git": _git_rev(),
        "robustness": robustness, "decompose": bool(decompose), "pre_retrieval_llm": llm_label,
    })
    counts = {"normalize_changed": n_norm, "normalize_errors": n_norm_err,
              "decompose_fired": n_dec, "decompose_errors": n_dec_err}
    meta.setdefault("suites", {})[suite if split == "dev" else f"{suite}:{split}"] = {
        "n": len(items), "split": split, "ids_file": ids_file or "", "captured": dt.datetime.now().isoformat(timespec="seconds"),
        "robustness": robustness, "decompose": bool(decompose), "pre_retrieval_counts": counts}
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"{len(items)} questions ({split}) cached in {time.time() - t0:.0f}s -> {cache_file(name, suite, split)}")
    print(f"variant: robustness={robustness} decompose={bool(decompose)} config={cfg.name} index={imap} "
          f"pre-retrieval model={llm_label or '-'}")
    if robustness != "none" or decompose:
        n = max(len(items), 1)
        print(f"normalisation changed the question: {n_norm}/{len(items)} ({100 * n_norm / n:.0f} %), errors {n_norm_err}; "
              f"decomposition fired: {n_dec}/{len(items)} ({100 * n_dec / n:.0f} %), errors {n_dec_err}")


def _strip_ablation(name: str, ablate: str) -> str:
    """Base configuration name of an ablation variant ("C10_context_notes-use_crag_multihop=true")."""
    return name.split("-", 1)[0] if ablate else name


def load_cache(name: str, suite: str, split: str = "dev") -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    d = REPLAY / name
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    rows = {}
    for line in cache_file(name, suite, split).read_text(encoding="utf-8").splitlines():
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
    if "mcq" not in key and harness.is_abstention(answer):
        return 0.0
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


def replay_generate(engine, cache_row: dict[str, Any], cfg: RetrievalConfig, gen_cfg, mode: str):
    """Generation stage on one cached retrieval output (the same call as the served engine after
    its own retrieval: tests/test_generation_b3.py checks the prompts are byte-identical)."""
    retrieved = [RetrievedChunk.model_validate(x) for x in cache_row["retrieved"]]
    analysis = QueryAnalysis.model_validate(cache_row["analysis"])
    return engine.generate(cache_row["query"], retrieved, analysis, cache_row["timings"], mode=mode,
                           config=cfg, gen_config=gen_cfg)


def cache_row(query: str, retrieved, analysis, timings) -> dict[str, Any]:
    """The JSON row `capture` writes for one question (round trip included)."""
    return json.loads(json.dumps({
        "query": query, "retrieved": [rc.model_dump() for rc in retrieved],
        "analysis": analysis.model_dump(), "timings": timings,
    }, ensure_ascii=False, default=str))


def _build_pre_retrieval_llm(args):
    """Client for the language-model steps before retrieval (normalisation, decomposition): the
    client the HTTP API builds (interfaces/generator_runtime.py, thinking off unless
    --no-thinking-flag), or a local MLX model. None without --backend."""
    if not args.backend:
        return None
    if args.backend == "mlx":
        from rag_sfar.generation.client import LocalMlxLLM

        return LocalMlxLLM(model_path=args.mlx_model_path or args.model, model_label=args.model,
                           temperature=0.0, max_tokens=args.max_tokens, enable_thinking=False)
    from rag_sfar.interfaces.generator_runtime import GeneratorSettings

    s = Settings()
    return GeneratorSettings(base_url=args.base_url or s.llm_base_url, model=args.model or s.llm_model,
                             api_key=args.api_key or s.llm_api_key,
                             send_thinking_flag=not args.no_thinking_flag).build(s.llm_timeout_seconds)


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

    check_split(args.split, args.allow_test)
    profile = None
    if args.profile:
        from rag_sfar.generation.profile import get_profile

        profile = get_profile(args.profile)
        if args.preset or args.gen or args.system_file or args.drop_rule:
            raise SystemExit("--profile fixes the generation settings: do not combine it with --preset/--gen/--system-file/--drop-rule")
        gen_cfg = profile.generation_config()
        args.gen_mode, args.mcq_mode = profile.open_mode, "route"
    else:
        if not args.preset:
            raise SystemExit("give --profile or an explicit --preset (no silent default)")
        gen_cfg = resolve_generation_config(args.preset, args.gen)
    if args.system_file:
        # Prompt variant: system prompt read from a file, registered as a new open mode
        # (format/grounding rules only; files in eval_internal/work/b3_prompts/).
        from rag_sfar.generation import client as C, prompts as P

        new_mode = Path(args.system_file).stem
        P.SYSTEM_PROMPTS[new_mode] = Path(args.system_file).read_text(encoding="utf-8")
        C.OPEN_MODES = tuple(C.OPEN_MODES) + (new_mode,)
        args.gen_mode = new_mode
    if args.drop_rule:
        # Prompt ablation: remove numbered rule N of the system prompt of --gen-mode (new mode name).
        from rag_sfar.generation import prompts as P

        base = P.SYSTEM_PROMPTS[args.gen_mode]
        kept = [ln for ln in base.splitlines() if not re.match(rf"^\s*{args.drop_rule}\.\s", ln)]
        assert len(kept) == len(base.splitlines()) - 1, "rule not found"
        new_mode = f"{args.gen_mode}-no{args.drop_rule}"
        P.SYSTEM_PROMPTS[new_mode] = "\n".join(kept) + "\n"
        args.gen_mode = new_mode
        if args.mcq_mode == new_mode.split("-no")[0]:
            args.mcq_mode = new_mode
    llm = _build_llm(args)
    if profile is not None:
        from rag_sfar.generation.profile import build_engine

        engine = build_engine(None, llm, profile)  # exactly the served engine, without retrieval
    else:
        engine = SfarRagEngine(retriever=None, llm=llm)
    tok = _Tok(args.tokenizer or (args.mlx_model_path if args.backend == "mlx" else DEFAULT_TOKENIZER))
    all_rows = []
    gen_inputs = []
    suites = args.suite.split(",")
    for suite in suites:
        meta, cache = load_cache(args.cache, suite, args.split)
        cfg = config_from_meta(meta)
        if profile is not None and meta.get("base_config", cfg.name) != profile.retrieval_config_name:
            raise SystemExit(f"cache {args.cache} was captured with {cfg.name}, profile expects {profile.retrieval_config_name}")
        # Dev-only proxy keys (another suite's dev answer keys): never outside dev.
        proxy = proxy_items(suite, args.split)
        items = [it for it in _items(suite, _load_ids(args.ids_file), args.split) if it.id in cache]
        if args.limit:
            items = items[: args.limit]
        for i, it in enumerate(items):
            c = cache[it.id]
            # "route": the engine routes lettered-option questions itself (production behaviour).
            mode = args.gen_mode if (it.question_type != "mcq" or args.mcq_mode == "route") else args.mcq_mode
            n_calls = len(getattr(llm, "calls", []))
            t0 = time.perf_counter()
            resp = replay_generate(engine, c, cfg, gen_cfg, mode)
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
            chk = check_answer(resp.answer, resp.retrieved_chunks, is_abstention=harness.is_abstention(resp.answer), query=it.formatted_query())
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
            row["dependency_note"] = bool((resp.latency_ms or {}).get("dependency_note"))
            row["self_corrected"] = bool(resp.extra.get("self_corrected"))
            row["latency_ms"] = lat
            row["retrieved"] = [(rc.chunk.doc_id, rc.chunk.chunk_id) for rc in resp.retrieved_chunks]
            if "pre_retrieval" in c:  # retrieval variant: what the model steps did
                pr = c["pre_retrieval"]
                row["pre_retrieval"] = pr
                if pr.get("normalization") is not None:
                    row["normalize_changed"] = 1.0 if pr["normalization"].get("used") else 0.0
                if pr.get("decomposition") is not None:
                    row["decompose_fired"] = 1.0 if pr["decomposition"].get("fired") else 0.0
            if args.backend == "record" and len(llm.calls) > n_calls:
                system, user = llm.calls[n_calls]
                row["prompt_chars"] = len(system) + len(user)
                pt = tok.count(system + "\n" + user)
                if pt is not None:
                    row["prompt_tokens"] = pt
                gen_inputs.append({"id": it.id, "suite": suite, "query": it.formatted_query(), "mode": resp.mode,
                                   "system": system, "user": user})
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
        export_blind(Path(args.export_frontier), gen_inputs, all_rows, {
            "cache": args.cache, "split": args.split, "suites": suites, "gen_config": gen_cfg.to_dict(),
            "gen_mode": args.gen_mode, "mcq_mode": args.mcq_mode, "ids_file": args.ids_file,
            "profile": args.profile or "", "git": _git_rev()}, per_part=args.per_part)
    return _save(args, gen_cfg, all_rows, suites, label=getattr(llm, "model", args.backend))


def _extra_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("proxy_correct", "verifier_flag", "check_flag", "context_chars", "prompt_tokens", "completion_tokens", "n_passages", "coverage_refused",
                "normalize_changed", "decompose_fired"):
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
        meta, _ = load_cache(args.cache, suite, args.split)
        summary = harness.summarize(srows)
        summary.update(_extra_summary(srows))
        name = f"{meta['config']}|{gen_cfg.name}|{args.gen_mode}"
        rep = {
            "suite": suite, "split": args.split, "k": 0, "n_items": len(srows),
            "generator": f"{args.backend}:{label}", "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "replay": {"cache": args.cache, "cache_meta": {k: meta[k] for k in (
                           "config", "ablate", "index_map", "index_dirs", "git", "robustness", "decompose", "pre_retrieval_llm",
                           "base_config") if k in meta},
                       "gen_config": gen_cfg.to_dict(), "gen_mode": args.gen_mode, "mcq_mode": args.mcq_mode,
                       "ids_file": args.ids_file, "profile": args.profile or "", "git": _git_rev()},
            "runs": [{"config": name, "config_params": gen_cfg.to_dict(), "summary": summary, "rows": srows}],
            "comparisons": [],
        }
        out_dir = Path(args.out_dir) if getattr(args, "out_dir", "") else ROOT / "reports/eval/b3"
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


KEYS = WORK / "replay" / "frontier_keys"  # id mappings, outside every export folder
MAX_PER_PART = 8


def proxy_items(suite: str, split: str) -> dict[str, EvalItem]:
    """Dev-only proxy answer keys (abp171 keys for abpe171). Disabled outside dev: they would
    read another suite's split."""
    if split != "dev" or suite not in PROXY_KEY_SUITE:
        return {}
    return {it.id: it for it in load_suite(PROXY_KEY_SUITE[suite], "dev")}


def export_blind(d: Path, gen_inputs: list[dict[str, Any]], rows: list[dict[str, Any]], meta: dict[str, Any],
                 per_part: int = MAX_PER_PART) -> None:
    """Blind, isolated export for stand-in generator agents.

    - opaque random case ids (the real id, suite and benchmark never appear in a part folder);
    - cases shuffled, then split in `part_NN/` sub-folders of at most `per_part` cases, each
      holding only its own `gen_input.json` (an agent is given one folder);
    - the mapping opaque id -> real id, the prompts and the replay rows are written to
      eval_internal/work/replay/frontier_keys/<name>.json, outside the export folder."""
    import secrets

    if per_part > MAX_PER_PART:
        raise SystemExit(f"at most {MAX_PER_PART} cases per part")
    if d.exists() and any(d.iterdir()):
        raise SystemExit(f"{d} is not empty: export into a new folder")
    for g in gen_inputs:  # every prompt must contain its own question
        if g["query"] not in g["user"]:
            raise SystemExit(f"prompt of {g['id']} does not contain its question")
    rng = random.Random(secrets.randbits(64))
    cases = list(gen_inputs)
    rng.shuffle(cases)
    used: set[str] = set()
    mapping = []
    for g in cases:
        cid = f"c{secrets.token_hex(5)}"
        while cid in used:
            cid = f"c{secrets.token_hex(5)}"
        used.add(cid)
        mapping.append({**g, "case_id": cid})
    n_parts = -(-len(mapping) // per_part)
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n_parts):
        part = mapping[i * per_part:(i + 1) * per_part]
        pdir = d / f"part_{i:02d}"
        pdir.mkdir()
        for m in part:
            m["part"] = pdir.name
        (pdir / "gen_input.json").write_text(json.dumps(
            [{"case_id": m["case_id"], "system": m["system"], "user": m["user"]} for m in part],
            ensure_ascii=False, indent=1), encoding="utf-8")
    KEYS.mkdir(parents=True, exist_ok=True)
    (KEYS / f"{d.name}.json").write_text(json.dumps(
        {"export_dir": str(d), "meta": meta, "cases": mapping, "rows": rows}, ensure_ascii=False, default=str),
        encoding="utf-8")
    print(f"{len(mapping)} prompts in {n_parts} parts (<= {per_part}) -> {d}; keys -> {KEYS / (d.name + '.json')}")


def _norm_answer(a: str) -> str:
    return re.sub(r"\s+", " ", a).strip().lower()


def import_frontier(d: Path, model_label: str, tag: str) -> list[Path]:
    """Map the stand-in's answers back to the questions and build one report per suite.

    Refuses: a missing part output or answer, an unknown or duplicated case id, an answer filed in
    another part's output, and identical long answers given to different cases (cross-part
    contamination). Each prompt is re-checked to contain its own question. The deterministic
    answer check (`check_flag`) is computed on every imported answer."""
    from rag_sfar.generation.answer_check import check_answer
    from rag_sfar.generation.client import _final_answer, build_generation_context
    from rag_sfar.generation.settings import GenerationConfig

    keys = json.loads((KEYS / f"{d.name}.json").read_text(encoding="utf-8"))
    meta = keys["meta"]
    split = meta["split"]
    cases = {c["case_id"]: c for c in keys["cases"]}
    errors: list[str] = []
    answers: dict[str, str] = {}
    parts = sorted({c["part"] for c in cases.values()})
    for part in parts:
        out = d / part / "gen_out.json"
        if not out.exists():
            errors.append(f"{part}: gen_out.json missing")
            continue
        for a in json.loads(out.read_text(encoding="utf-8")):
            cid = a.get("case_id")
            if cid not in cases:
                errors.append(f"{part}: unknown case id {cid}")
            elif cases[cid]["part"] != part:
                errors.append(f"{part}: case {cid} belongs to {cases[cid]['part']}")
            elif cid in answers:
                errors.append(f"{part}: duplicate answer for {cid}")
            elif not str(a.get("answer", "")).strip():
                errors.append(f"{part}: empty answer for {cid}")
            else:
                answers[cid] = a["answer"]
    missing = sorted(set(cases) - set(answers))
    if missing:
        errors.append(f"{len(missing)} cases without answer: {missing[:10]}")
    seen: dict[str, str] = {}
    for cid, a in answers.items():
        n = _norm_answer(a)
        if len(n) >= 120:
            if n in seen:
                errors.append(f"identical answers for {seen[n]} and {cid}")
            seen.setdefault(n, cid)
    items_by_suite = {suite: {it.id: it for it in load_suite(suite, split)} for suite in meta["suites"]}
    for c in cases.values():
        it = items_by_suite[c["suite"]].get(c["id"])
        if it is None or it.formatted_query() not in c["user"]:
            errors.append(f"prompt {c['case_id']} does not contain the question of {c['id']}")
    if errors:
        raise SystemExit("import refused:\n  " + "\n  ".join(errors))

    g = GenerationConfig(**meta["gen_config"])
    rows_by_id = {(r["suite"], r["id"]): r for r in keys["rows"]}
    by_suite: dict[str, list[dict[str, Any]]] = defaultdict(list)
    caches: dict[str, tuple] = {}
    for cid, c in cases.items():
        suite = c["suite"]
        if suite not in caches:
            m, cache = load_cache(meta["cache"], suite, split)
            caches[suite] = (config_from_meta(m), cache)
        cfg, cache = caches[suite]
        it = items_by_suite[suite][c["id"]]
        r = dict(rows_by_id[(suite, c["id"])])
        ans = _final_answer(answers[cid], c["mode"])
        cr = cache[c["id"]]
        gen_chunks, _ = build_generation_context(
            [RetrievedChunk.model_validate(x) for x in cr["retrieved"]], QueryAnalysis.model_validate(cr["analysis"]),
            cfg, cr["query"], c["mode"], g)
        r.update(harness.score_answer(it, ans))
        proxy = proxy_items(suite, split)
        if proxy:
            pc = proxy_correct(suite, c["id"], ans, proxy)
            if pc is not None:
                r["proxy_correct"] = pc
        chk = check_answer(ans, gen_chunks, is_abstention=harness.is_abstention(ans), query=it.formatted_query())
        r["check_flag"] = 1.0 if chk.flagged else 0.0
        r["answer_check"] = dataclasses.asdict(chk)
        r["answer"] = ans
        r["opaque_case_id"] = cid
        by_suite[suite].append(r)
    out_paths = []
    for suite, srows in by_suite.items():
        srows.sort(key=lambda r: r["id"])
        summary = harness.summarize(srows)
        summary.update(_extra_summary(srows))
        rep = {"suite": suite, "split": split, "k": 0, "n_items": len(srows),
               "generator": f"{model_label} (stand-in agents, blind export {d.name})",
               "timestamp": dt.datetime.now().isoformat(timespec="seconds"), "replay": meta,
               "runs": [{"config": f"{meta['cache']}|{meta['gen_config']['name']}|{model_label}", "config_params": meta["gen_config"],
                         "summary": summary, "rows": srows}], "comparisons": []}
        jp, _ = harness.save_report(rep, out_dir=ROOT / "reports/eval/b3", tag=f"b3_{tag}_{model_label}")
        out_paths.append(jp)
        print(f"{suite} ({split}): {len(srows)} answers, check_flag {sum(r['check_flag'] for r in srows):.0f} -> {jp}")
    return out_paths


def recheck(report_path: Path) -> None:
    """Recompute deterministic scores and the answer check of a replay report with the current
    code (the shown context is rebuilt from the cache and the stored generation config)."""
    from rag_sfar.generation.answer_check import check_answer
    from rag_sfar.generation.client import build_generation_context
    from rag_sfar.generation.settings import GenerationConfig

    rep = json.loads(report_path.read_text(encoding="utf-8"))
    suite = rep["suite"]
    split = rep.get("split", "dev")
    meta, cache = load_cache(rep["replay"]["cache"], suite, split)
    cfg = config_from_meta(meta)
    g = GenerationConfig(**rep["replay"]["gen_config"])
    items = {it.id: it for it in load_suite(suite, split)}
    proxy = proxy_items(suite, split)
    for row in rep["runs"][0]["rows"]:
        if "answer" not in row:
            continue
        c = cache[row["id"]]
        retrieved = [RetrievedChunk.model_validate(x) for x in c["retrieved"]]
        analysis = QueryAnalysis.model_validate(c["analysis"])
        mode = row.get("mode", "")
        gen_chunks, _ = build_generation_context(retrieved, analysis, cfg, c["query"], mode, g)
        row.update(harness.score_answer(items[row["id"]], row["answer"]))
        if proxy:
            pc = proxy_correct(suite, row["id"], row["answer"], proxy)
            if pc is not None:
                row["proxy_correct"] = pc
        chk = check_answer(row["answer"], gen_chunks, is_abstention=harness.is_abstention(row["answer"]), query=c["query"])
        row["check_flag"] = 1.0 if chk.flagged else 0.0
        row["answer_check"] = dataclasses.asdict(chk)
    rows = rep["runs"][0]["rows"]
    keep = {k: v for k, v in rep["runs"][0]["summary"].items() if k.startswith("judge")}
    summary = harness.summarize(rows)
    summary.update(_extra_summary(rows))
    summary.update(keep)
    rep["runs"][0]["summary"] = summary
    report_path.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"rechecked {report_path.name}")


def export_predictions(report_path: Path, out: Path) -> None:
    """Answers of a run report as prediction lines for the experts' evaluator
    (data/benchmark_enrichi_alparagsfar/benchmark_evaluator: {question_id, status, answer});
    question_id = the benchmark's own id kept in the item's meta when there is one."""
    rep = json.loads(report_path.read_text(encoding="utf-8"))
    items = {it.id: it for it in load_suite(rep["suite"], rep.get("split", "dev"))}
    n = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rep["runs"][0]["rows"]:
            if "answer" not in row:
                continue
            it = items.get(row["id"])
            qid = (it.meta or {}).get("question_id", row["id"]) if it else row["id"]
            ok = bool(str(row["answer"]).strip())
            f.write(json.dumps({"question_id": qid, "status": "success" if ok else "error",
                                "answer": row["answer"] if ok else None}, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} predictions -> {out}")


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
    p.add_argument("--split", default="dev", choices=["dev", "test"])
    p.add_argument("--allow-test", action="store_true", help="required for --split test (lockbox verified)")
    p.add_argument("--profile", default="", help="serving profile (generation/profile.py): sets --configs and --index-map")
    p.add_argument("--configs", default="", help="retrieval configuration (required without --profile)")
    p.add_argument("--ablate", default="")
    p.add_argument("--index-map", default="", help="strategy=index folder (required without --profile)")
    p.add_argument("--ids-file", default=None)
    p.add_argument("--name", required=True)
    p.add_argument("--device", default="cpu")
    p.add_argument("--robustness", default="none", choices=["none", "lexical", "normalize", "both"],
                   help="retrieval variant (interfaces/robustness.py); none = frozen (default)")
    p.add_argument("--decompose", action="store_true", help="question decomposition before retrieval (multi_query 'decompose')")
    p.add_argument("--backend", choices=["openai", "mlx"], default="",
                   help="model of the normalisation / decomposition calls (required by normalize, both, --decompose)")
    p.add_argument("--base-url", default="")
    p.add_argument("--model", default="")
    p.add_argument("--api-key", default="")
    p.add_argument("--mlx-model-path", default="")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--no-thinking-flag", action="store_true",
                   help="do not send chat_template_kwargs.enable_thinking=false (servers that reject it)")
    p.add_argument("--replay-dir", default="", help="cache root (default eval_internal/work/replay)")
    p = sub.add_parser("run")
    p.add_argument("--cache", required=True)
    p.add_argument("--suite", required=True, help="one suite or a comma list")
    p.add_argument("--split", default="dev", choices=["dev", "test"])
    p.add_argument("--allow-test", action="store_true", help="required for --split test (lockbox verified)")
    p.add_argument("--profile", default="", help="serving profile: generation settings and modes exactly as served")
    p.add_argument("--ids-file", default=None)
    p.add_argument("--preset", default="", help="generation preset (required without --profile)")
    p.add_argument("--gen", default="", help="GenerationConfig overrides, 'field=value+field=value'")
    p.add_argument("--gen-mode", default="clinical_concise")
    p.add_argument("--mcq-mode", default="route", help="'route' = let the engine route MCQs (production); or force a mode")
    p.add_argument("--backend", choices=["mlx", "openai", "record"], required=True)
    p.add_argument("--mlx-model-path", default="")
    p.add_argument("--model", default="")
    p.add_argument("--base-url", default="")
    p.add_argument("--api-key", default="")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--tokenizer", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--tag", required=True)
    p.add_argument("--system-file", default="", help="prompt variant: system prompt file, registered as mode <file stem>")
    p.add_argument("--drop-rule", default="", help="ablation: drop numbered rule N of the --gen-mode system prompt")
    p.add_argument("--export-frontier", default="", help="blind export folder for stand-in generators (new folder)")
    p.add_argument("--per-part", type=int, default=MAX_PER_PART)
    p.add_argument("--replay-dir", default="", help="cache root (default eval_internal/work/replay)")
    p.add_argument("--out-dir", default="", help="report folder (default reports/eval/b3)")
    p = sub.add_parser("import-frontier")
    p.add_argument("--dir", required=True)
    p.add_argument("--model-label", required=True)
    p.add_argument("--tag", default="frontier")
    p = sub.add_parser("recheck")
    p.add_argument("reports", nargs="+")
    p = sub.add_parser("export-predictions")
    p.add_argument("report")
    p.add_argument("--out", required=True)
    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--metrics", default="correct,proxy_correct,judge_correct,judge_serious_error,judge_behavior_ok,abstention_correct,false_abstention,sourced,verifier_flag,prompt_tokens,latency_ms")
    a = ap.parse_args()
    if getattr(a, "replay_dir", ""):
        REPLAY = Path(a.replay_dir).resolve()
    if a.cmd == "subsets":
        make_subsets(a.suites.split(","), a.n)
    elif a.cmd == "capture":
        check_split(a.split, a.allow_test)
        if a.profile:
            from rag_sfar.generation.profile import get_profile

            prof = get_profile(a.profile)
            if a.configs or a.index_map or a.ablate:
                raise SystemExit("--profile fixes --configs/--index-map: do not combine")
            a.configs, a.index_map = prof.retrieval_config_name, prof.replay_index_map()
        if not a.configs or not a.index_map:
            raise SystemExit("give --profile, or both --configs and --index-map (no silent default)")
        if a.backend and not a.model and not a.mlx_model_path:
            raise SystemExit("--backend needs --model (or --mlx-model-path)")
        llm = _build_pre_retrieval_llm(a)
        capture(a.suite, a.configs, a.ablate, a.index_map, a.ids_file, a.name, a.device, a.split,
                robustness=a.robustness, decompose=a.decompose, llm=llm,
                llm_label=f"{a.backend}:{a.model or a.mlx_model_path}" if a.backend else "")
    elif a.cmd == "run":
        run(a)
    elif a.cmd == "recheck":
        for r in a.reports:
            recheck(Path(r))
    elif a.cmd == "import-frontier":
        import_frontier(Path(a.dir), a.model_label, a.tag)
    elif a.cmd == "export-predictions":
        export_predictions(Path(a.report), Path(a.out))
    else:
        compare(a.a, a.b, a.metrics.split(","))
