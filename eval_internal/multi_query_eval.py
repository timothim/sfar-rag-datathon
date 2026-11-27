"""Evaluation of multi-query retrieval (agent X2, dev only). See reports/agents/X2_decomposition.md.

Stages (language-model modes go through stand-in agents, file hand-off):

    # 1. export prompts (decompose: no model needed; llm_correct: runs the frozen retrieval)
    .venv/bin/python eval_internal/multi_query_eval.py export --mode decompose --name dec_r1
    scripts/with_gpu_lock.sh X2 env HF_HUB_OFFLINE=1 .venv/bin/python eval_internal/multi_query_eval.py \
        export --mode llm_correct --name cor_r1
    # stand-in agents answer eval_internal/work/x2/exports/<name>/part_NN/input.json -> output.json
    # (instructions: reports/agents/X2_annexes/STANDIN_INSTRUCTIONS.md)
    # 2. import (strict format check; refuses the whole export on any error)
    .venv/bin/python eval_internal/multi_query_eval.py import --name dec_r1
    # 3. retrieval runs (frozen = mode off), then paired comparison against the frozen run
    scripts/with_gpu_lock.sh X2 env HF_HUB_OFFLINE=1 .venv/bin/python eval_internal/multi_query_eval.py \
        run --mode decompose --answers dec_r1 --tag dec_r1
    .venv/bin/python eval_internal/multi_query_eval.py compare --a off --b dec_r1

Suites: abpe171 dev, multirfe_synth dev (never test, never genprobe/genprobe2) and x2_dev (16
two-source questions written for development by X2's helper; eval_internal/work/x2_dev/).
Metrics: `harness.retrieval_metrics` on the context the generator would read (wide preset:
`select_within_budget(40 chunks, 30 000 chars)`), and on the full returned list.
"""

from __future__ import annotations

import argparse
import json
import secrets
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from rag_sfar.evaluation import harness
from rag_sfar.evaluation.datasets import EvalItem, load_suite, read_jsonl
from rag_sfar.generation.context import select_within_budget
from rag_sfar.retrieval.multi_query import (
    FormatError,
    MultiQueryConfig,
    MultiQueryRetriever,
    correct_prompt,
    decompose_prompt,
    parse_correction,
    parse_decomposition,
    prompt_key,
)

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "eval_internal" / "work" / "x2"
X2_DEV = ROOT / "eval_internal" / "work" / "x2_dev" / "x2_dev.jsonl"
SUITES = ("abpe171", "multirfe_synth", "x2_dev")
MAX_PER_PART = 20
K = 64
GEN_CHUNKS, GEN_CHARS = 40, 30000
PARSERS = {"decompose": parse_decomposition, "llm_correct": parse_correction}


def items(suite: str) -> list[EvalItem]:
    if suite == "x2_dev":
        return read_jsonl(X2_DEV)
    return load_suite(suite, "dev")


def all_items(suites=SUITES) -> list[tuple[str, EvalItem]]:
    return [(s, it) for s in suites for it in items(s)]


def load_retriever():
    from rag_sfar.config import Settings

    s = Settings()
    cfg = harness.select_configs("C10_context_notes")[0]
    assert cfg.name == "C10_context_notes"
    r = harness.load_retrievers(ROOT / "index", [cfg.chunking_strategy], s.reranker_provider, s.reranker_model,
                                index_map={cfg.chunking_strategy: "tas_v6"})[cfg.chunking_strategy]
    r.retrieve("anesthésie", config=cfg)  # warm-up
    return r, cfg


class TableResponder:
    """Evaluation responder: answers looked up by prompt key; records missing prompts."""

    def __init__(self, table: dict[str, str] | None = None, default: str | None = None) -> None:
        self.table = table or {}
        self.default = default
        self.missing: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> str:
        k = prompt_key(system, user)
        if k in self.table:
            return self.table[k]
        self.missing.append((system, user))
        if self.default is None:
            raise KeyError(k)
        return self.default


# ---------------------------------------------------------------- export / import


def export(mode: str, name: str) -> None:
    d = WORK / "exports" / name
    if d.exists() and any(d.iterdir()):
        sys.exit(f"{d} is not empty")
    prompts: list[dict[str, Any]] = []
    if mode == "decompose":
        for suite, it in all_items():
            s, u = decompose_prompt(it.formatted_query())
            prompts.append({"suite": suite, "id": it.id, "system": s, "user": u})
    elif mode == "llm_correct":
        retr, cfg = load_retriever()
        c = MultiQueryConfig()
        for suite, it in all_items():
            main, analysis, _ = retr.retrieve(it.formatted_query(), config=cfg)
            if analysis.temporal_mode == "all_versions":
                continue  # the wrapper does not run the corrective pass on edition comparisons
            s, u = correct_prompt(it.formatted_query(), main, c.correct_list_n, c.correct_first_chars)
            prompts.append({"suite": suite, "id": it.id, "system": s, "user": u})
    else:
        sys.exit("mode must be decompose or llm_correct")
    rng = __import__("random").Random(secrets.randbits(64))
    rng.shuffle(prompts)
    used: set[str] = set()
    for p in prompts:
        cid = f"m{secrets.token_hex(5)}"
        while cid in used:
            cid = f"m{secrets.token_hex(5)}"
        used.add(cid)
        p["case_id"] = cid
        p["key"] = prompt_key(p["system"], p["user"])
    n_parts = -(-len(prompts) // MAX_PER_PART)
    d.mkdir(parents=True)
    for i in range(n_parts):
        part = prompts[i * MAX_PER_PART:(i + 1) * MAX_PER_PART]
        pd = d / f"part_{i:02d}"
        pd.mkdir()
        for p in part:
            p["part"] = pd.name
        (pd / "input.json").write_text(json.dumps(
            [{"case_id": p["case_id"], "system": p["system"], "user": p["user"]} for p in part],
            ensure_ascii=False, indent=1), encoding="utf-8")
    keys = WORK / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    (keys / f"{name}.json").write_text(json.dumps({"mode": mode, "export_dir": str(d), "cases": prompts},
                                                  ensure_ascii=False), encoding="utf-8")
    print(f"{mode}: {len(prompts)} prompts in {n_parts} parts (<= {MAX_PER_PART}) -> {d}")


def import_(name: str) -> None:
    keys = json.loads((WORK / "keys" / f"{name}.json").read_text(encoding="utf-8"))
    parser = PARSERS[keys["mode"]]
    d = Path(keys["export_dir"])
    cases = {c["case_id"]: c for c in keys["cases"]}
    answers: dict[str, str] = {}
    errors: list[str] = []
    for part in sorted({c["part"] for c in cases.values()}):
        f = d / part / "output.json"
        if not f.exists():
            errors.append(f"{part}: output.json missing")
            continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{part}: output.json does not parse ({e})")
            continue
        for a in rows:
            cid = a.get("case_id")
            if cid not in cases:
                errors.append(f"{part}: unknown case id {cid}")
            elif cases[cid]["part"] != part:
                errors.append(f"{part}: {cid} belongs to {cases[cid]['part']}")
            elif cid in answers:
                errors.append(f"{part}: duplicate {cid}")
            else:
                try:
                    parser(str(a.get("answer", "")))
                except FormatError as e:
                    errors.append(f"{part}: {cid} format: {e}")
                answers[cid] = str(a.get("answer", ""))
    missing = sorted(set(cases) - set(answers))
    if missing:
        errors.append(f"{len(missing)} cases without answer: {missing[:8]}")
    if errors:
        sys.exit("import refused:\n  " + "\n  ".join(errors))
    table = {cases[cid]["key"]: a for cid, a in answers.items()}
    out = WORK / "answers" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"mode": keys["mode"], "table": table,
                               "by_item": {f"{cases[c]['suite']}::{cases[c]['id']}": a for c, a in answers.items()}},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    fired = sum(1 for a in answers.values() if parser(a))
    print(f"imported {len(answers)} answers ({fired} multi-part / incomplete) -> {out}")


# ---------------------------------------------------------------- runs


def _metrics(it: EvalItem, ctx) -> dict[str, Any]:
    m = harness.retrieval_metrics(it, ctx, K)
    return {k: m[k] for k in ("sufficiency", "evidence_recall", "passage_hit", "passage_recall", "doc_hit", "doc_recall")
            if k in m}


def run(mode: str, answers: str, tag: str, gap_threshold: float, share: int, keep_main: bool) -> None:
    retr, cfg = load_retriever()
    table = json.loads((WORK / "answers" / f"{answers}.json").read_text())["table"] if answers else {}
    responder = TableResponder(table) if mode in PARSERS else None
    mq = MultiQueryRetriever(retr, MultiQueryConfig(mode=mode, gap_threshold=gap_threshold, share_per_query=share,
                                                    keep_main=keep_main), responder)
    out = WORK / "runs" / f"{tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for suite, it in all_items():
            q = it.formatted_query()
            t0 = time.perf_counter()
            try:
                ctx, analysis, timings = mq.retrieve(q, config=cfg)
            except KeyError:
                sys.exit(f"no stand-in answer for {suite}::{it.id} (prompt changed?)")
            lat = (time.perf_counter() - t0) * 1000
            tr = mq.last_trace
            gen = select_within_budget(ctx, GEN_CHUNKS, GEN_CHARS)
            row = {
                "suite": suite, "id": it.id, "mode": mode, "tag": tag, "latency_ms": round(lat, 1),
                "n_chunks": len(ctx), "chars": sum(len(r.chunk.text) for r in ctx),
                "gen_n_chunks": len(gen), "gen_chars": sum(len(r.chunk.text) for r in gen),
                "fired": tr.fired, "extra_queries": tr.extra_queries, "format_error": tr.format_error,
                "clause_support": tr.clause_support, "llm_raw": tr.raw_answer,
                "extra_ms": tr.extra_retrieval_ms,
                "chunks": [[r.chunk.chunk_id, r.expansion_reason or ""] for r in ctx],
                "gen": _metrics(it, gen), "full": _metrics(it, ctx),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    print(f"{tag}: {n} items -> {out}")


def clause_scan(tag: str) -> None:
    """Clause support of every dev item against the frozen output (signal study for ce_gap)."""
    retr, cfg = load_retriever()
    mq = MultiQueryRetriever(retr, MultiQueryConfig(mode="ce_gap"))
    out = WORK / "runs" / f"{tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for suite, it in all_items():
            q = it.formatted_query()
            main, analysis, _ = retr.retrieve(q, config=cfg)
            t0 = time.perf_counter()
            sup = mq.clause_support(q, main)
            ms = (time.perf_counter() - t0) * 1000
            gen = select_within_budget(main, GEN_CHUNKS, GEN_CHARS)
            f.write(json.dumps({"suite": suite, "id": it.id, "clause_support": sup, "ce_ms": round(ms, 1),
                                "gen": _metrics(it, gen), "temporal": analysis.temporal_mode}, ensure_ascii=False) + "\n")
    print(f"clause scan -> {out}")


# ---------------------------------------------------------------- comparison


def _rows(tag: str) -> dict[tuple[str, str], dict]:
    return {(r["suite"], r["id"]): r for r in map(json.loads, (WORK / "runs" / f"{tag}.jsonl").open())}


def compare(a: str, b: str, out_md: str | None) -> None:
    A, B = _rows(a), _rows(b)
    lines = [f"# {b} vs {a} (paired, b - a; contexte vu par le générateur : 40 extraits / 30 000 car.)", ""]
    for suite in SUITES:
        keys = [k for k in A if k[0] == suite and k in B]
        if not keys:
            continue
        fired = [k for k in keys if B[k]["fired"]]
        lines.append(f"## {suite} (n = {len(keys)}, déclenchements {len(fired)} = {100 * len(fired) / len(keys):.1f} %)")
        lines.append("")
        lines.append("| métrique | n | a | b | b − a [IC 95 %] | gagnés / perdus |")
        lines.append("|---|---:|---:|---:|---|---|")
        for m in ("sufficiency", "evidence_recall", "passage_hit", "doc_hit"):
            pa = [A[k]["gen"].get(m) for k in keys]
            pb = [B[k]["gen"].get(m) for k in keys]
            pairs = [(x, y) for x, y in zip(pa, pb) if x is not None and y is not None]
            if not pairs:
                continue
            d = harness.paired_bootstrap_diff([x for x, _ in pairs], [y for _, y in pairs])
            won = sum(1 for x, y in pairs if y > x)
            lost = sum(1 for x, y in pairs if y < x)
            ma = 100 * sum(x for x, _ in pairs) / len(pairs)
            mb = 100 * sum(y for _, y in pairs) / len(pairs)
            lines.append(f"| {m} | {len(pairs)} | {ma:.1f} | {mb:.1f} | {100 * d['diff']:+.1f} [{100 * d['ci_low']:+.1f} ; "
                         f"{100 * d['ci_high']:+.1f}] | {won} / {lost} |")
        lat_a = statistics.median(A[k]["latency_ms"] for k in keys)
        lat_b = statistics.median(B[k]["latency_ms"] for k in keys)
        lat_bf = statistics.median([B[k]["latency_ms"] for k in fired]) if fired else float("nan")
        ch_a = statistics.mean(A[k]["gen_chars"] for k in keys)
        ch_b = statistics.mean(B[k]["gen_chars"] for k in keys)
        nq = sum(len(B[k]["extra_queries"]) for k in fired)
        lines += ["", f"Latence médiane retrieval (hors appel LLM) : {lat_a:.0f} → {lat_b:.0f} ms (déclenchés : {lat_bf:.0f} ms) ; "
                  f"caractères moyens du contexte générateur : {ch_a:.0f} → {ch_b:.0f} ; requêtes supplémentaires : {nq}.",
                  f"Erreurs de format : {sum(1 for k in keys if B[k]['format_error'])}.", ""]
    txt = "\n".join(lines)
    print(txt)
    if out_md:
        Path(out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(out_md).write_text(txt + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export"); p.add_argument("--mode", required=True); p.add_argument("--name", required=True)
    p = sub.add_parser("import"); p.add_argument("--name", required=True)
    p = sub.add_parser("run")
    p.add_argument("--mode", required=True); p.add_argument("--answers", default=""); p.add_argument("--tag", required=True)
    p.add_argument("--gap-threshold", type=float, default=0.05); p.add_argument("--share", type=int, default=2)
    p.add_argument("--no-main", action="store_true")
    p = sub.add_parser("clause-scan"); p.add_argument("--tag", default="clause_scan")
    p = sub.add_parser("compare"); p.add_argument("--a", required=True); p.add_argument("--b", required=True)
    p.add_argument("--out", default="")
    a = ap.parse_args()
    if a.cmd == "export":
        export(a.mode, a.name)
    elif a.cmd == "import":
        import_(a.name)
    elif a.cmd == "run":
        run(a.mode, a.answers, a.tag, a.gap_threshold, a.share, not a.no_main)
    elif a.cmd == "clause-scan":
        clause_scan(a.tag)
    else:
        compare(a.a, a.b, a.out or None)


if __name__ == "__main__":
    main()
