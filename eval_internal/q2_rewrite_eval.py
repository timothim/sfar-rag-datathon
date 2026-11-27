"""Evaluation of LLM query rewriting before retrieval (agent Q2, dev only).
See reports/agents/Q2_reformulation.md and src/rag_sfar/retrieval/query_rewrite.py.

Stages (the language model is played by stand-in agents, file hand-off):

    # 1. export every prompt variant at once (no model needed): opaque ids, parts of <= 40 cases,
    #    one variant per part, never two versions of the same question in one part
    .venv/bin/python eval_internal/q2_rewrite_eval.py export --name r1
    # stand-in agents answer eval_internal/work/q2/exports/<name>/part_NN/input.json -> output.json
    # (instructions: reports/agents/Q2_annexes/STANDIN_INSTRUCTIONS.md)
    # 2. import (strict format check; refuses the whole export on any error)
    .venv/bin/python eval_internal/q2_rewrite_eval.py import --name r1
    # 3. retrieval runs (frozen, then every variant x use x guard), one model load
    scripts/with_gpu_lock.sh Q2 env HF_HUB_OFFLINE=1 .venv/bin/python eval_internal/q2_rewrite_eval.py run --answers r1 --tag r1
    # 4. tables (paired bootstrap against the frozen run, same condition), fidelity checks, hand-reading sheets
    .venv/bin/python eval_internal/q2_rewrite_eval.py analyze --tag r1

Data: Q1's perturbed copies of the dev splits (eval_internal/robustness/sets/, read-only). Suites
abpe171 and multirfe_synth, split dev only; never test, genprobe or genprobe2.
Everything that contains question text (exports, keys, answers, result rows, hand-reading sheets)
stays in eval_internal/work/q2/ (git-ignored through its own .gitignore).
Metrics: `harness.retrieval_metrics` (k = 64) on the context the generator would read (wide preset,
`select_within_budget(40 chunks, 30 000 chars)`).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import secrets
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_sfar.evaluation import harness  # noqa: E402
from rag_sfar.evaluation.datasets import EvalItem, load_suite, read_jsonl  # noqa: E402
from rag_sfar.generation.context import select_within_budget  # noqa: E402
from rag_sfar.retrieval.query_rewrite import (  # noqa: E402
    SYSTEMS,
    FormatError,
    QueryRewriteConfig,
    QueryRewriteRetriever,
    _pop_words,
    fold,
    guard_violations,
    parse_rewrite,
    prompt_key,
    rewrite_prompt,
    same_text,
    split_options,
)

WORK = ROOT / "eval_internal" / "work" / "q2"
SETS = ROOT / "eval_internal" / "robustness" / "sets"
CONDITIONS = {
    "abpe171": ("clean", "typo1", "typo3", "abbr_user"),
    "multirfe_synth": ("clean", "typo1", "typo3", "abbr_user", "abbr"),
}
VARIANT_CONDITIONS = {
    "normalize": ("clean", "typo1", "typo3", "abbr_user", "abbr"),
    "reformulate": ("clean", "typo1", "typo3", "abbr_user", "abbr"),
    "hyde": ("clean", "typo3"),
}
MAX_PER_PART = 40
K = 64
GEN_CHUNKS, GEN_CHARS = 40, 30000
METRICS = {"abpe171": ("sufficiency", "evidence_recall"), "multirfe_synth": ("passage_hit",)}
TOKENIZER = "/Users/tim/.cache/rag_sfar_models/Qwen3.5-9B-MLX-4bit-nothink"


def _ensure_work() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    gi = WORK / ".gitignore"
    if not gi.exists():
        gi.write_text("# benchmark question text: local only\n*\n", encoding="utf-8")


def condition_items() -> list[tuple[str, str, EvalItem]]:
    out = []
    for suite, conds in CONDITIONS.items():
        dev_ids = {it.id for it in load_suite(suite, "dev")}
        for cond in conds:
            for it in read_jsonl(SETS / suite / f"{cond}.jsonl"):
                if it.id not in dev_ids:
                    sys.exit(f"{suite}/{cond}: {it.id} is not in the dev split")
                out.append((suite, cond, it))
    return out


# ---------------------------------------------------------------- export / import


def export(name: str) -> None:
    _ensure_work()
    d = WORK / "exports" / name
    if d.exists() and any(d.iterdir()):
        sys.exit(f"{d} is not empty")
    rng = random.Random(secrets.randbits(64))
    used: set[str] = set()
    cases: list[dict[str, Any]] = []
    for variant, conds in VARIANT_CONDITIONS.items():
        by_key: dict[str, dict[str, Any]] = {}
        for suite, cond, it in condition_items():
            if cond not in conds:
                continue
            stem, _opts = split_options(it.formatted_query())
            s, u = rewrite_prompt(variant, stem)
            k = prompt_key(s, u)
            c = by_key.setdefault(k, {"variant": variant, "system": s, "user": u, "key": k, "items": []})
            c["items"].append(f"{suite}::{cond}::{it.id}")
        vcases = list(by_key.values())
        rng.shuffle(vcases)
        # parts: <= MAX_PER_PART cases, never two versions of the same question in one part
        n_parts = -(-len(vcases) // MAX_PER_PART)
        parts: list[list[dict[str, Any]]] = [[] for _ in range(n_parts)]
        qids: list[set[str]] = [set() for _ in range(n_parts)]
        for c in sorted(vcases, key=lambda c: -len({i.split("::")[0] + i.split("::")[2] for i in c["items"]})):
            ids = {i.split("::")[0] + "::" + i.split("::")[2] for i in c["items"]}
            order = sorted(range(n_parts), key=lambda p: len(parts[p]))
            target = next((p for p in order if len(parts[p]) < MAX_PER_PART and not (qids[p] & ids)), None)
            if target is None:
                parts.append([]); qids.append(set()); target = len(parts) - 1
            parts[target].append(c)
            qids[target] |= ids
        for p in parts:
            rng.shuffle(p)
        for p in parts:
            pid = f"part_{len({c['part'] for c in cases if 'part' in c}):02d}"
            for c in p:
                cid = f"q{secrets.token_hex(5)}"
                while cid in used:
                    cid = f"q{secrets.token_hex(5)}"
                used.add(cid)
                c["case_id"], c["part"] = cid, pid
                cases.append(c)
    d.mkdir(parents=True)
    for pid in sorted({c["part"] for c in cases}):
        pd = d / pid
        pd.mkdir()
        part = [c for c in cases if c["part"] == pid]
        (pd / "input.json").write_text(json.dumps(
            [{"case_id": c["case_id"], "system": c["system"], "user": c["user"]} for c in part],
            ensure_ascii=False, indent=1), encoding="utf-8")
    keys = WORK / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    (keys / f"{name}.json").write_text(json.dumps({"export_dir": str(d), "cases": cases}, ensure_ascii=False),
                                       encoding="utf-8")
    per = Counter(c["variant"] for c in cases)
    parts_per = Counter(c["variant"] for c in {c["part"]: c for c in cases}.values())
    print(f"{len(cases)} prompts in {len({c['part'] for c in cases})} parts -> {d}")
    for v in per:
        print(f"  {v}: {per[v]} prompts, {parts_per[v]} parts")


def import_(name: str) -> None:
    keys = json.loads((WORK / "keys" / f"{name}.json").read_text(encoding="utf-8"))
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
        expected = [c["case_id"] for c in keys["cases"] if c["part"] == part]
        got = [a.get("case_id") for a in rows if isinstance(a, dict)]
        if got != expected:
            errors.append(f"{part}: case ids differ from the input (order or set)")
        for a in rows:
            cid = a.get("case_id") if isinstance(a, dict) else None
            if cid not in cases:
                errors.append(f"{part}: unknown case id {cid}")
            elif cases[cid]["part"] != part:
                errors.append(f"{part}: {cid} belongs to {cases[cid]['part']}")
            elif cid in answers:
                errors.append(f"{part}: duplicate {cid}")
            else:
                ans = str(a.get("answer", ""))
                try:
                    parse_rewrite(cases[cid]["variant"], ans)
                except FormatError as e:
                    errors.append(f"{part}: {cid} format: {e}")
                answers[cid] = ans
    missing = sorted(set(cases) - set(answers))
    if missing:
        errors.append(f"{len(missing)} cases without answer: {missing[:8]}")
    if errors:
        sys.exit("import refused:\n  " + "\n  ".join(errors))
    table = {cases[cid]["key"]: a for cid, a in answers.items()}
    out = WORK / "answers" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"table": table}, ensure_ascii=False, indent=1), encoding="utf-8")
    by_v = Counter(cases[c]["variant"] for c in answers)
    kept = Counter(cases[c]["variant"] for c, a in answers.items() if parse_rewrite(cases[c]["variant"], a) is None)
    print(f"imported {len(answers)} answers -> {out}; " + ", ".join(f"{v}: {by_v[v]} ({kept[v]} INCHANGEE)" for v in by_v))


# ---------------------------------------------------------------- runs


class TableResponder:
    def __init__(self, table: dict[str, str]) -> None:
        self.table = table

    def __call__(self, system: str, user: str) -> str:
        return self.table[prompt_key(system, user)]  # KeyError = prompt not exported: stop


class CachingRetriever:
    """Memoises the frozen retriever by query string (it is deterministic; checked in `run`)."""

    def __init__(self, base: Any) -> None:
        self.base = base
        self.cache: dict[str, tuple] = {}
        self.ms: dict[str, float] = {}

    def retrieve(self, query: str, **kw: Any) -> tuple:
        if query not in self.cache:
            t0 = time.perf_counter()
            self.cache[query] = self.base.retrieve(query, **kw)
            self.ms[query] = (time.perf_counter() - t0) * 1000
        return self.cache[query]


def load_retriever():
    from rag_sfar.config import Settings

    s = Settings()
    cfg = harness.select_configs("C10_context_notes")[0]
    assert cfg.name == "C10_context_notes"
    r = harness.load_retrievers(ROOT / "index", [cfg.chunking_strategy], s.reranker_provider, s.reranker_model,
                                index_map={cfg.chunking_strategy: "tas_v6"})[cfg.chunking_strategy]
    r.retrieve("anesthésie", config=cfg)  # warm-up
    return r, cfg


def _metrics(suite: str, it: EvalItem, ctx) -> dict[str, Any]:
    m = harness.retrieval_metrics(it, ctx, K)
    return {k: m.get(k) for k in METRICS[suite]}


def run(answers: str, tag: str) -> None:
    _ensure_work()
    retr, cfg = load_retriever()
    cache = CachingRetriever(retr)
    table = json.loads((WORK / "answers" / f"{answers}.json").read_text())["table"]
    responder = TableResponder(table)
    setups = [("frozen", "off", "add", False)]
    for v, conds in VARIANT_CONDITIONS.items():
        for use in ("replace", "add"):
            setups.append((f"{v}_{use}", v, use, False))
        if v == "normalize":
            for use in ("replace", "add"):
                setups.append((f"{v}_guard_{use}", v, use, True))
    out = WORK / "runs" / f"{tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    t_all = time.perf_counter()
    with out.open("w", encoding="utf-8") as f:
        for suite, cond, it in condition_items():
            q = it.formatted_query()
            for name, variant, use, guard in setups:
                if variant != "off" and cond not in VARIANT_CONDITIONS[variant]:
                    continue
                w = QueryRewriteRetriever(cache, QueryRewriteConfig(variant=variant, use=use, guard=guard),
                                          responder if variant != "off" else None)
                ctx, analysis, _timings = w.retrieve(q, config=cfg)
                tr = w.last_trace
                gen = select_within_budget(ctx, GEN_CHUNKS, GEN_CHARS)
                row = {
                    "suite": suite, "cond": cond, "id": it.id, "setup": name, "variant": variant, "use": use,
                    "guard": guard, "changed_input": bool(it.meta.get("perturbation", {}).get("changed")),
                    "edits": it.meta.get("perturbation", {}).get("edits", []),
                    "stem": tr.stem if variant != "off" else split_options(q)[0],
                    "raw": tr.raw_answer, "rewrite": tr.rewrite, "used": tr.used,
                    "format_error": tr.format_error, "guard_rejected": tr.guard_rejected,
                    "n_added": tr.n_added, "temporal": analysis.temporal_mode,
                    "n_chunks": len(gen), "chars": sum(len(r.chunk.text) for r in gen),
                    "trimmed": len(ctx) - len(gen),
                    "chunks": [r.chunk.chunk_id for r in gen],
                    "m": _metrics(suite, it, gen),
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
            f.flush()
    # determinism of the cache: a fresh call on a sample of cached queries returns the same chunks
    sample = random.Random(0).sample(sorted(cache.cache), min(25, len(cache.cache)))
    same = sum(1 for qq in sample if [r.chunk.chunk_id for r in retr.retrieve(qq, config=cfg)[0]]
               == [r.chunk.chunk_id for r in cache.cache[qq][0]])
    lat = sorted(cache.ms.values())
    meta = {"rows": n, "unique_queries": len(cache.cache), "determinism_sample": f"{same}/{len(sample)}",
            "retrieval_ms_median": statistics.median(lat), "retrieval_ms_p90": lat[int(0.9 * len(lat))],
            "seconds": round(time.perf_counter() - t_all, 1)}
    (WORK / "runs" / f"{tag}.meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"{tag}: {n} rows -> {out}; {meta}")


# ---------------------------------------------------------------- analysis


_STOP = frozenset(
    "les des une un le la de du au aux et ou en est sont quel quelle quels quelles quoi comment faut doit peut "
    "pour par sur dans avec chez sans sous que qui dont son ses leur leurs cette ces ce cet il elle ils elles on "
    "lors cas avant apres pendant tout tous toute toutes plus moins tres entre selon faire etre avoir a l d n s "
    "y se ne pas quelle recommandation recommandations recommande conduite tenir patient patiente".split()
)


def _words(s: str) -> list[str]:
    return [w for w in fold(s).replace("-", " ").split() if len(w) >= 3 and w not in _STOP]


def _present(word: str, text_words: set[str]) -> bool:
    """Tolerant to plural / feminine endings."""
    if word in text_words:
        return True
    w = word.rstrip("sx")
    return any(t.rstrip("sx") == w or (len(w) >= 5 and t.startswith(w[:-1]) and abs(len(t) - len(w)) <= 2)
               for t in text_words)


def fidelity_flags(original: str, rewrite: str) -> dict[str, Any]:
    """Automatic checks of a rewrite against the question it rewrites (stems)."""
    g = guard_violations(original, rewrite)
    ow, rw = _words(original), set(_words(rewrite))
    dropped = sorted({w for w in ow if not _present(w, rw)})
    added = sorted({w for w in rw if not _present(w, set(ow))})
    return {"numbers": [x for x in g if x.startswith("number")], "negation": [x for x in g if x.startswith("negation")],
            "population": [x for x in g if x.startswith("population")],
            "population_added": sorted(_pop_words(rewrite) - _pop_words(original)), "dropped_words": dropped,
            "added_words": added}


def _edit_outcome(edit: dict, rewrite_text: str) -> str:
    """For a perturbation edit (from -> to): restored / left / other (neither form present).
    Exact word match (plural tolerated); accents kept for accent edits, folded otherwise."""
    keep_acc = edit.get("op") in ("accent", "noaccent")

    def toks(s: str) -> list[str]:
        s = s.lower() if keep_acc else fold(s)
        return re.findall(r"[^\W_]+", s)

    rw = set(toks(rewrite_text))

    def has(words: list[str]) -> bool:
        return bool(words) and all(w in rw or w + "s" in rw or w.rstrip("s") in rw for w in words)

    frm, to = toks(edit["from"]), toks(edit["to"])
    if has(frm):
        return "restored"
    if has(to):
        return "left"
    return "other"


def _load_rows(tag: str) -> list[dict]:
    return [json.loads(l) for l in (WORK / "runs" / f"{tag}.jsonl").open(encoding="utf-8")]


def _fmt_ci(d: dict) -> str:
    return f"{100 * d['diff']:+.1f} [{100 * d['ci_low']:+.1f} ; {100 * d['ci_high']:+.1f}]"


def analyze(tag: str) -> None:
    rows = _load_rows(tag)
    by = defaultdict(dict)  # (suite, cond, setup) -> id -> row
    for r in rows:
        by[(r["suite"], r["cond"], r["setup"])][r["id"]] = r
    setups = list(dict.fromkeys(r["setup"] for r in rows))
    L = [f"# Q2 — réécriture de la question avant retrieval : résultats `{tag}` (dev seulement)", "",
         "Contexte vu par le générateur (préréglage `wide` : 40 extraits / 30 000 caractères), k = 64. "
         "Différences appariées contre le retrieval gelé sur la même condition, b − a en points, IC 95 % bootstrap "
         "(2 000 tirages). « réécr. utilisée » = la réécriture a changé la requête (ni INCHANGEE, ni identique, ni "
         "erreur de format, ni rejet par le garde-fou).", ""]
    for suite, conds in CONDITIONS.items():
        for m in METRICS[suite]:
            L += [f"## {suite} — {m}", "", "| condition | configuration | n | gelé | variante | variante − gelé [IC 95 %] | gagnés / perdus | réécr. utilisée |",
                  "|---|---|---:|---:|---:|---|---|---:|"]
            for cond in conds:
                F = by.get((suite, cond, "frozen"), {})
                for s in setups:
                    if s == "frozen" or (suite, cond, s) not in by:
                        continue
                    B = by[(suite, cond, s)]
                    ids = [i for i in F if i in B and F[i]["m"].get(m) is not None and B[i]["m"].get(m) is not None]
                    if not ids:
                        continue
                    a = [F[i]["m"][m] for i in ids]
                    b = [B[i]["m"][m] for i in ids]
                    d = harness.paired_bootstrap_diff(a, b)
                    won = sum(1 for x, y in zip(a, b) if y > x)
                    lost = sum(1 for x, y in zip(a, b) if y < x)
                    usedn = sum(1 for i in B if B[i]["used"])
                    L.append(f"| {cond} | {s} | {len(ids)} | {100 * sum(a) / len(a):.1f} | {100 * sum(b) / len(b):.1f} | "
                             f"{_fmt_ci(d)} | {won} / {lost} | {usedn}/{len(B)} |")
            L.append("")
    # pooled over the two suites, primary metric per suite (sufficiency / passage_hit)
    L += ["## Les deux suites regroupées (sufficiency pour abpe171, passage_hit pour multirfe_synth)", "",
          "| condition | configuration | n | gelé | variante | variante − gelé [IC 95 %] | gagnés / perdus |", "|---|---|---:|---:|---:|---|---|"]
    prim = {"abpe171": "sufficiency", "multirfe_synth": "passage_hit"}
    for cond in ("clean", "typo1", "typo3", "abbr_user"):
        for s in setups:
            if s == "frozen":
                continue
            a, b = [], []
            for suite in CONDITIONS:
                F, B = by.get((suite, cond, "frozen"), {}), by.get((suite, cond, s), {})
                for i in F:
                    if i in B and F[i]["m"].get(prim[suite]) is not None:
                        a.append(F[i]["m"][prim[suite]]); b.append(B[i]["m"][prim[suite]])
            if not a:
                continue
            d = harness.paired_bootstrap_diff(a, b)
            L.append(f"| {cond} | {s} | {len(a)} | {100 * sum(a) / len(a):.1f} | {100 * sum(b) / len(b):.1f} | {_fmt_ci(d)} | "
                     f"{sum(1 for x, y in zip(a, b) if y > x)} / {sum(1 for x, y in zip(a, b) if y < x)} |")
    L.append("")
    # fidelity (one row per distinct stem and variant)
    L += ["## Fidélité automatique des réécritures (une ligne par question distincte et par variante)", "",
          "| variante | condition | n | INCHANGEE | modifiée | erreur de format | nombre perdu/ajouté | négation perdue | population perdue | population ajoutée | mot de contenu perdu | mot de contenu ajouté | rejet garde-fou |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    seen: dict[tuple, dict] = {}
    for r in rows:
        if r["variant"] == "off" or r["use"] != "replace" or r["guard"]:
            continue
        seen.setdefault((r["variant"], r["cond"], r["suite"], r["stem"]), r)
    for v in VARIANT_CONDITIONS:
        for cond in ("clean", "typo1", "typo3", "abbr_user", "abbr"):
            rs = [r for (vv, c, _s, _st), r in seen.items() if vv == v and c == cond]
            if not rs:
                continue
            unchanged = sum(1 for r in rs if r["rewrite"] is None and not r["format_error"])
            ferr = sum(1 for r in rs if r["format_error"])
            mod = [r for r in rs if r["rewrite"] is not None and not same_text(r["rewrite"], r["stem"])]
            fl = [fidelity_flags(r["stem"], r["rewrite"]) for r in mod]
            grej = sum(1 for r in mod if guard_violations(r["stem"], r["rewrite"]))
            L.append(f"| {v} | {cond} | {len(rs)} | {unchanged} | {len(mod)} | {ferr} | {sum(1 for x in fl if x['numbers'])} | "
                     f"{sum(1 for x in fl if x['negation'])} | {sum(1 for x in fl if x['population'])} | "
                     f"{sum(1 for x in fl if x['population_added'])} | "
                     f"{sum(1 for x in fl if x['dropped_words'])} | {sum(1 for x in fl if x['added_words'])} | {grej} |")
    L.append("")
    # perturbation edits: restored / left / other
    L += ["## Corrections des perturbations (chaque modification de Q1 : forme d'origine rétablie, faute laissée, autre forme)", "",
          "| variante | condition | modifications | rétablies | laissées | autre forme |", "|---|---|---:|---:|---:|---:|"]
    for v in VARIANT_CONDITIONS:
        for cond in ("typo1", "typo3", "abbr_user", "abbr"):
            rs = [r for (vv, c, _s, _st), r in seen.items() if vv == v and c == cond and r["edits"]]
            if not rs:
                continue
            cnt = Counter()
            for r in rs:
                text = r["rewrite"] if r["rewrite"] is not None else r["stem"]
                for e in r["edits"]:
                    cnt[_edit_outcome(e, text)] += 1
            tot = sum(cnt.values())
            L.append(f"| {v} | {cond} | {tot} | {cnt['restored']} | {cnt['left']} | {cnt['other']} |")
    L.append("")
    # context size and cost
    L += ["## Taille du contexte et coût", ""]
    for s in setups:
        rs = [r for r in rows if r["setup"] == s]
        added = [r["n_added"] for r in rs if r["use"] == "add" and r["used"]]
        L.append(f"- `{s}` : {statistics.mean(r['chars'] for r in rs):.0f} car. et {statistics.mean(r['n_chunks'] for r in rs):.1f} extraits en moyenne"
                 + (f" ; extraits ajoutés par la réécriture quand elle est utilisée : moyenne {statistics.mean(added):.1f}, "
                    f"0 ajouté dans {sum(1 for x in added if x == 0)}/{len(added)} cas" if added else ""))
    try:
        meta = json.loads((WORK / "runs" / f"{tag}.meta.json").read_text())
        L.append(f"- retrieval gelé, une requête : médiane {meta['retrieval_ms_median']:.0f} ms, p90 {meta['retrieval_ms_p90']:.0f} ms "
                 f"(cache déterministe : {meta['determinism_sample']} identiques sur un échantillon rappelé)")
    except FileNotFoundError:
        pass
    L += _prompt_sizes(seen)
    txt = "\n".join(L) + "\n"
    out = WORK / "results" / f"summary_{tag}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(txt, encoding="utf-8")
    print(txt)
    handread(tag, seen)


def _prompt_sizes(seen: dict) -> list[str]:
    try:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(TOKENIZER)
        count = lambda t: len(tok.encode(t))  # noqa: E731
        unit = "jetons (tokenizer Qwen)"
    except Exception:
        count = lambda t: round(len(t) / 4)  # noqa: E731
        unit = "jetons estimés (car./4)"
    out = ["", f"Taille des appels ({unit}) :", ""]
    for v in VARIANT_CONDITIONS:
        rs = [r for (vv, *_), r in seen.items() if vv == v]
        if not rs:
            continue
        sys_t = count(SYSTEMS[v])
        user_t = [count(rewrite_prompt(v, r["stem"])[1]) for r in rs]
        outs = [count(r["raw"]) for r in rs if r["raw"]]
        out.append(f"- `{v}` : prompt système {sys_t}, message {statistics.mean(user_t):.0f} en moyenne ; sortie "
                   f"moyenne {statistics.mean(outs):.0f}, p90 {sorted(outs)[int(0.9 * len(outs))]}, max {max(outs)}")
    return out


def handread(tag: str, seen: dict) -> None:
    """Hand-reading sheets (local only): every modified rewrite of a clean question (normalize,
    reformulate), and 40 perturbed ones per variant, with the automatic flags."""
    rng = random.Random(7)
    d = WORK / "handread"
    d.mkdir(parents=True, exist_ok=True)
    for v in ("normalize", "reformulate", "hyde"):
        rs = [r for (vv, c, s, st), r in seen.items() if vv == v]
        clean = [r for r in rs if r["cond"] == "clean"]
        pert = [r for r in rs if r["cond"] != "clean" and r["rewrite"] is not None]
        pert = rng.sample(pert, min(40, len(pert)))
        lines = [f"# {v} — {tag}", ""]
        for title, sel in (("clean", clean), ("perturbed (40 random)", pert)):
            lines += [f"## {title}", ""]
            for r in sel:
                fl = fidelity_flags(r["stem"], r["rewrite"]) if r["rewrite"] else {}
                lines += [f"### {r['suite']} {r['cond']} {r['id']}", f"- Q : {r['stem']}",
                          f"- R : {r['rewrite'] if r['rewrite'] is not None else '(INCHANGEE)'}"]
                if r["edits"]:
                    lines.append(f"- edits : {[(e['from'], e['to']) for e in r['edits']]} → "
                                 f"{[_edit_outcome(e, r['rewrite'] or r['stem']) for e in r['edits']]}")
                if fl:
                    lines.append(f"- auto : {fl}")
                lines.append("")
        (d / f"{tag}_{v}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"hand-reading sheets -> {d}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export"); p.add_argument("--name", required=True)
    p = sub.add_parser("import"); p.add_argument("--name", required=True)
    p = sub.add_parser("run"); p.add_argument("--answers", required=True); p.add_argument("--tag", required=True)
    p = sub.add_parser("analyze"); p.add_argument("--tag", required=True)
    a = ap.parse_args()
    if a.cmd == "export":
        export(a.name)
    elif a.cmd == "import":
        import_(a.name)
    elif a.cmd == "run":
        run(a.answers, a.tag)
    else:
        analyze(a.tag)


if __name__ == "__main__":
    main()
