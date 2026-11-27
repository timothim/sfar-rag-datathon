"""Single pre-declared run on the held-out set genprobe2 (agent G1). Retrieval only.

Plan: JOURNAL.md, section "Plan de l'exécution unique sur `genprobe2`" (written before any run).
Candidates are the existing, unmodified modules: LEX (frozen + use_subword + use_medical_lexicon,
built like eval_internal/robustness/run_retrieval.py), NORM (query_rewrite, variant normalize, use
add), DEC (multi_query, mode decompose, share 2), TOUT (NORM wrapping DEC wrapping the retriever,
retrieval config LEX). Language-model answers come from stand-in agents (file hand-off, same input /
output format as the Q2 and X2 tools, same instructions).

    .venv/bin/python eval_internal/genprobe2_run.py prep            # sets + round-1 exports (CPU)
    .venv/bin/python eval_internal/genprobe2_run.py import1         # NORM + DEC answers
    .venv/bin/python eval_internal/genprobe2_run.py export2         # TOUT: decomposition of normalised questions
    .venv/bin/python eval_internal/genprobe2_run.py import2
    scripts/with_gpu_lock.sh G1 env HF_HUB_OFFLINE=1 .venv/bin/python eval_internal/genprobe2_run.py run
    .venv/bin/python eval_internal/genprobe2_run.py analyze > <report tables>

Everything holding question text stays in eval_internal/work/g1/ (git-ignored). Metrics:
`harness.retrieval_metrics` (k = 64) on the context the generator reads (`wide`:
select_within_budget(40 chunks, 30 000 chars)), as in the Q2 and X2 evaluations.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import secrets
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_sfar.evaluation import harness  # noqa: E402
from rag_sfar.evaluation.datasets import EvalItem, read_jsonl, write_jsonl  # noqa: E402
from rag_sfar.generation.context import select_within_budget  # noqa: E402
from rag_sfar.retrieval import multi_query as mq  # noqa: E402
from rag_sfar.retrieval import query_rewrite as qr  # noqa: E402

SEALED = ROOT / "eval_internal" / "splits" / "genprobe2" / "dev.jsonl"
SHA = "76be3ccd020efec13f0913c608ac24fb19f1e84cb9da76b3d20f6e641e5ca255"
WORK = ROOT / "eval_internal" / "work" / "g1"
K = 64
GEN_CHUNKS, GEN_CHARS = 40, 30000
SEED = 20261127  # default seed of eval_internal/robustness/perturb.py
FAMILIES = ("two_source", "population", "table_note", "control")
# (condition, setup) pairs of the plan; DEC alone on clean questions only.
SETUPS = {"clean": ("REF", "LEX", "NORM", "DEC", "TOUT"), "typo1": ("REF", "LEX", "NORM", "TOUT")}


def check_seal() -> None:
    h = hashlib.sha256(SEALED.read_bytes()).hexdigest()
    if h != SHA:
        sys.exit(f"SHA-256 mismatch on {SEALED}: {h}")


def _perturb_module():
    spec = importlib.util.spec_from_file_location("perturb", ROOT / "eval_internal" / "robustness" / "perturb.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # type: ignore[union-attr]
    return m


def sets() -> dict[str, list[EvalItem]]:
    return {c: read_jsonl(WORK / "sets" / f"{c}.jsonl") for c in SETUPS}


def family(it: EvalItem) -> str:
    return next((t[4:] for t in it.tags if t.startswith("fam:")), "?")


# ---------------------------------------------------------------- prep / export


def _write_parts(name: str, cases: list[dict], max_per_part: int) -> None:
    """Parts of <= max_per_part cases, never two versions of the same question in one part."""
    d = WORK / "exports" / name
    if d.exists() and any(d.iterdir()):
        sys.exit(f"{d} is not empty")
    rng = random.Random(secrets.randbits(64))
    rng.shuffle(cases)
    n_parts = max(1, -(-len(cases) // max_per_part))
    parts: list[list[dict]] = [[] for _ in range(n_parts)]
    ids: list[set] = [set() for _ in range(n_parts)]
    for c in sorted(cases, key=lambda c: -len(c["ids"])):
        order = sorted(range(len(parts)), key=lambda p: len(parts[p]))
        t = next((p for p in order if len(parts[p]) < max_per_part and not (ids[p] & c["ids"])), None)
        if t is None:
            parts.append([]); ids.append(set()); t = len(parts) - 1
        parts[t].append(c); ids[t] |= c["ids"]
    used: set[str] = set()
    for i, p in enumerate(parts):
        rng.shuffle(p)
        pd = d / f"part_{i:02d}"
        pd.mkdir(parents=True)
        for c in p:
            cid = f"g{secrets.token_hex(5)}"
            while cid in used:
                cid = f"g{secrets.token_hex(5)}"
            used.add(cid)
            c["case_id"], c["part"] = cid, pd.name
        (pd / "input.json").write_text(json.dumps([{"case_id": c["case_id"], "system": c["system"], "user": c["user"]}
                                                   for c in p], ensure_ascii=False, indent=1), encoding="utf-8")
    keys = WORK / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    for c in cases:
        c["ids"] = sorted(c["ids"])
    (keys / f"{name}.json").write_text(json.dumps({"export_dir": str(d), "cases": cases}, ensure_ascii=False),
                                       encoding="utf-8")
    print(f"{name}: {len(cases)} prompts in {len(parts)} parts -> {d.relative_to(ROOT)}")


def _add(by_key: dict, s: str, u: str, kind: str, item_ref: str, qid: str, key_fn) -> None:
    k = key_fn(s, u)
    c = by_key.setdefault(k, {"kind": kind, "system": s, "user": u, "key": k, "items": [], "ids": set()})
    c["items"].append(item_ref)
    c["ids"].add(qid)


def prep() -> None:
    check_seal()
    gi = WORK / ".gitignore"
    if not gi.exists():
        sys.exit(f"{gi} missing (held-out text must stay local)")
    items = read_jsonl(SEALED)
    pt = _perturb_module()
    typo = []
    changed = 0
    for it in items:
        new, edits = pt.apply_typos(it.question, 1, pt.rng_for(SEED, "typo1", it.id))
        changed += new != it.question
        meta = dict(it.meta)
        meta["perturbation"] = {"name": "typo1", "seed": SEED, "changed": new != it.question, "edits": edits}
        typo.append(it.model_copy(update={"question": new, "meta": meta}))
    write_jsonl(items, WORK / "sets" / "clean.jsonl")
    write_jsonl(typo, WORK / "sets" / "typo1.jsonl")
    print(f"typo1: {changed}/{len(items)} questions changed (seed {SEED})")
    norm: dict = {}
    dec: dict = {}
    for cond, its in (("clean", items), ("typo1", typo)):
        for it in its:
            q = it.formatted_query()
            stem, _ = qr.split_options(q)
            s, u = qr.rewrite_prompt("normalize", stem)
            _add(norm, s, u, "normalize", f"{cond}::{it.id}", it.id, qr.prompt_key)
            s, u = mq.decompose_prompt(q)  # clean: DEC and TOUT; typo1: TOUT (original question)
            _add(dec, s, u, "decompose", f"{cond}::{it.id}", it.id, mq.prompt_key)
    _write_parts("norm_r1", list(norm.values()), 40)
    _write_parts("dec_r1", list(dec.values()), 20)


def _import(name: str) -> dict[str, str]:
    keys = json.loads((WORK / "keys" / f"{name}.json").read_text(encoding="utf-8"))
    d = Path(keys["export_dir"])
    cases = {c["case_id"]: c for c in keys["cases"]}
    answers: dict[str, str] = {}
    errors: list[str] = []
    for part in sorted({c["part"] for c in cases.values()}):
        f = d / part / "output.json"
        if not f.exists():
            errors.append(f"{part}: output.json missing"); continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{part}: does not parse ({e})"); continue
        for a in rows:
            cid = a.get("case_id") if isinstance(a, dict) else None
            if cid not in cases or cases[cid]["part"] != part or cid in answers:
                errors.append(f"{part}: bad or duplicate case id {cid}"); continue
            ans = str(a.get("answer", ""))
            try:
                if cases[cid]["kind"] == "normalize":
                    qr.parse_rewrite("normalize", ans)
                else:
                    mq.parse_decomposition(ans)
            except (qr.FormatError, mq.FormatError) as e:
                errors.append(f"{part}: {cid} format: {e}")
            answers[cid] = ans
    missing = sorted(set(cases) - set(answers))
    if missing:
        errors.append(f"{len(missing)} cases without answer")
    if errors:
        sys.exit(f"import {name} refused:\n  " + "\n  ".join(errors))
    table = {cases[c]["key"]: a for c, a in answers.items()}
    out = WORK / "answers" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"table": table}, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = Counter(c["kind"] for c in cases.values())
    print(f"imported {name}: {len(answers)} answers {dict(kinds)} -> {out.relative_to(ROOT)}")
    return table


def _table(*names: str) -> dict[str, str]:
    t: dict[str, str] = {}
    for n in names:
        p = WORK / "answers" / f"{n}.json"
        if p.exists():
            t.update(json.loads(p.read_text(encoding="utf-8"))["table"])
    return t


def _normalised(q: str, norm_table: dict[str, str]) -> str | None:
    """Rewritten full query of NORM (add mode, no guard), exactly as QueryRewriteRetriever.rewrite."""
    w = qr.QueryRewriteRetriever(None, qr.QueryRewriteConfig(variant="normalize", use="add"),
                                 lambda s, u: norm_table[qr.prompt_key(s, u)])
    w.last_trace = qr.QueryRewriteTrace(variant="normalize", use="add")
    new, _ = w.rewrite(q)
    if w.last_trace.format_error:
        sys.exit(f"normalisation answer missing or invalid: {w.last_trace.format_error}")
    return new


def export2() -> None:
    """TOUT: NORM (outer) calls DEC on the original AND on the normalised question."""
    check_seal()
    norm_t, dec_t = _table("norm_r1"), _table("dec_r1")
    dec: dict = {}
    for cond, its in sets().items():
        for it in its:
            new = _normalised(it.formatted_query(), norm_t)
            if new is None:
                continue
            s, u = mq.decompose_prompt(new)
            if mq.prompt_key(s, u) not in dec_t:
                _add(dec, s, u, "decompose", f"{cond}::{it.id}", it.id, mq.prompt_key)
    if not dec:
        print("export2: nothing to export (every needed prompt already answered)")
        return
    _write_parts("dec_r2", list(dec.values()), 20)


# ---------------------------------------------------------------- run


class FireCount:
    """Pass-through to the decomposition wrapper; remembers whether any call fired (TOUT calls it twice)."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.fired = inner, False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def retrieve(self, query: str, **kw: Any) -> tuple:
        out = self.inner.retrieve(query, **kw)
        self.fired = self.fired or bool(self.inner.last_trace and self.inner.last_trace.fired)
        return out


class Strict:
    def __init__(self, table: dict[str, str], key_fn) -> None:
        self.table, self.key_fn, self.missing = table, key_fn, 0

    def __call__(self, system: str, user: str) -> str:
        k = self.key_fn(system, user)
        if k not in self.table:
            self.missing += 1
            raise KeyError(k)
        return self.table[k]


def _metrics(it: EvalItem, ctx) -> dict[str, Any]:
    m = harness.retrieval_metrics(it, ctx, K)
    return {k: m.get(k) for k in ("sufficiency", "evidence_recall", "passage_hit", "doc_hit")}


def run() -> None:
    check_seal()
    from rag_sfar.config import Settings

    s = Settings()
    ref_cfg = harness.select_configs("C10_context_notes")[0]
    assert ref_cfg.name == "C10_context_notes"
    lex_cfg = harness.ablation_variants(ref_cfg, "use_subword=true+use_medical_lexicon=true")[0]
    base = harness.load_retrievers(ROOT / "index", [ref_cfg.chunking_strategy], s.reranker_provider, s.reranker_model,
                                   index_map={ref_cfg.chunking_strategy: "tas_v6"})[ref_cfg.chunking_strategy]
    base.retrieve("anesthésie", config=ref_cfg)  # warm-up
    base.retrieve("anesthésie", config=lex_cfg)
    norm_t, dec_t = _table("norm_r1"), _table("dec_r1", "dec_r2")
    norm_r, dec_r = Strict(norm_t, qr.prompt_key), Strict(dec_t, mq.prompt_key)
    ncfg = qr.QueryRewriteConfig(variant="normalize", use="add")
    dcfg = mq.MultiQueryConfig(mode="decompose", share_per_query=2)
    dec_w = FireCount(mq.MultiQueryRetriever(base, dcfg, dec_r))
    retrievers = {
        "REF": (base, ref_cfg),
        "LEX": (base, lex_cfg),
        "NORM": (qr.QueryRewriteRetriever(base, ncfg, norm_r), ref_cfg),
        "DEC": (dec_w, ref_cfg),
        "TOUT": (qr.QueryRewriteRetriever(dec_w, ncfg, norm_r), lex_cfg),
    }
    out = WORK / "runs" / "g1.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    t_all = time.perf_counter()
    with out.open("w", encoding="utf-8") as f:
        for cond, its in sets().items():
            for it in its:
                q = it.formatted_query()
                for name in SETUPS[cond]:
                    r, cfg = retrievers[name]
                    m0n, m0d = norm_r.missing, dec_r.missing
                    dec_w.fired = False
                    t0 = time.perf_counter()
                    ctx, analysis, timings = r.retrieve(q, config=cfg)
                    lat = (time.perf_counter() - t0) * 1000
                    gen = select_within_budget(ctx, GEN_CHUNKS, GEN_CHARS)
                    ntr = getattr(r, "last_trace", None) if name in ("NORM", "TOUT") else None
                    row = {
                        "cond": cond, "id": it.id, "setup": name, "family": family(it),
                        "weak": bool(it.meta.get("weak")), "latency_ms": round(lat, 1),
                        "gen_n_chunks": len(gen), "gen_chars": sum(len(x.chunk.text) for x in gen),
                        "norm_used": bool(ntr and ntr.used),
                        "dec_fired": bool(name in ("DEC", "TOUT") and dec_w.fired),
                        "missing_answers": (norm_r.missing - m0n) + (dec_r.missing - m0d),
                        "temporal": analysis.temporal_mode,
                        "gen": _metrics(it, gen), "full": _metrics(it, ctx),
                    }
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{cond} done ({time.perf_counter() - t_all:.0f}s)", flush=True)
    print(f"run -> {out.relative_to(ROOT)}; missing answers: norm {norm_r.missing}, dec {dec_r.missing}")


# ---------------------------------------------------------------- analysis


def analyze() -> None:
    rows = [json.loads(l) for l in (WORK / "runs" / "g1.jsonl").open(encoding="utf-8")]
    R: dict = {}
    for r in rows:
        R[(r["cond"], r["setup"], r["id"])] = r
    ids = list(dict.fromkeys(r["id"] for r in rows))
    fam = {r["id"]: r["family"] for r in rows}
    weak = {r["id"] for r in rows if r["weak"]}
    print(f"missing stand-in answers during the run: {sum(r['missing_answers'] for r in rows)}")
    P = lambda x: f"{100 * x:.1f}"  # noqa: E731

    def mean(cond, setup, m, sub):
        v = [R[(cond, setup, i)]["gen"][m] for i in sub if R[(cond, setup, i)]["gen"][m] is not None]
        return (sum(v) / len(v), len(v)) if v else (float("nan"), 0)

    def diff(cond, setup, m, sub):
        pairs = [(R[(cond, "REF", i)]["gen"][m], R[(cond, setup, i)]["gen"][m]) for i in sub
                 if R[(cond, "REF", i)]["gen"][m] is not None and R[(cond, setup, i)]["gen"][m] is not None]
        d = harness.paired_bootstrap_diff([a for a, _ in pairs], [b for _, b in pairs])
        won = [i for i in sub if R[(cond, setup, i)]["gen"][m] is not None and R[(cond, "REF", i)]["gen"][m] is not None
               and R[(cond, setup, i)]["gen"][m] > R[(cond, "REF", i)]["gen"][m]]
        lost = [i for i in sub if R[(cond, setup, i)]["gen"][m] is not None and R[(cond, "REF", i)]["gen"][m] is not None
                and R[(cond, setup, i)]["gen"][m] < R[(cond, "REF", i)]["gen"][m]]
        return d, won, lost

    subsets = {"toutes": ids, **{f: [i for i in ids if fam[i] == f] for f in FAMILIES},
               "sans weak": [i for i in ids if i not in weak]}
    for cond, setups in SETUPS.items():
        print(f"\n## Condition {cond}\n")
        print("### Référence gelée (C10_context_notes, tas_v6)\n")
        print("| sous-groupe | n | suffisance | rappel des preuves | passage dans le contexte |")
        print("|---|---:|---:|---:|---:|")
        for sn, sub in subsets.items():
            vals = [mean(cond, "REF", m, sub) for m in ("sufficiency", "evidence_recall", "passage_hit")]
            print(f"| {sn} | {len(sub)} | " + " | ".join(P(v) for v, _ in vals) + " |")
        for m in ("sufficiency", "evidence_recall", "passage_hit"):
            print(f"\n### {m} : candidat − référence (b − a, IC 95 % bootstrap apparié)\n")
            print("| candidat | sous-groupe | n | réf. | candidat | diff [IC 95 %] | gagnées | perdues |")
            print("|---|---|---:|---:|---:|---|---|---|")
            for s in setups:
                if s == "REF":
                    continue
                for sn, sub in subsets.items():
                    d, won, lost = diff(cond, s, m, sub)
                    a, n = mean(cond, "REF", m, sub)
                    b, _ = mean(cond, s, m, sub)
                    print(f"| {s} | {sn} | {n} | {P(a)} | {P(b)} | {100 * d['diff']:+.1f} [{100 * d['ci_low']:+.1f} ; "
                          f"{100 * d['ci_high']:+.1f}] | {len(won)} {','.join(won)} | {len(lost)} {','.join(lost)} |")
        print("\n### Coût\n")
        print("| config | latence retrieval médiane (ms) | p90 | contexte moyen (car.) | extraits moyens | NORM utilisée | DEC déclenchée |")
        print("|---|---:|---:|---:|---:|---:|---:|")
        for s in setups:
            rr = [R[(cond, s, i)] for i in ids]
            lat = sorted(r["latency_ms"] for r in rr)
            print(f"| {s} | {statistics.median(lat):.0f} | {lat[int(0.9 * len(lat))]:.0f} | "
                  f"{statistics.mean(r['gen_chars'] for r in rr):.0f} | {statistics.mean(r['gen_n_chunks'] for r in rr):.1f} | "
                  f"{sum(r['norm_used'] for r in rr)} | {sum(r['dec_fired'] for r in rr)} |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "import1", "export2", "import2", "run", "analyze"])
    a = ap.parse_args()
    if a.cmd == "prep":
        prep()
    elif a.cmd == "import1":
        _import("norm_r1"); _import("dec_r1")
    elif a.cmd == "export2":
        export2()
    elif a.cmd == "import2":
        _import("dec_r2")
    elif a.cmd == "run":
        run()
    else:
        analyze()


if __name__ == "__main__":
    main()
