"""V1: NORM (query_rewrite, variant normalize, use add) on the clinicians' wordings (abpvern). Retrieval only.

    .venv/bin/python eval_internal/benchmark_valide/norm_vern.py export      # prompts -> eval_internal/work/v1/exports/norm_vern/part_NN/input.json
    .venv/bin/python eval_internal/benchmark_valide/norm_vern.py import      # output.json -> answers table (strict format check)
    scripts/with_gpu_lock.sh V1 env HF_HUB_OFFLINE=1 .venv/bin/python eval_internal/benchmark_valide/norm_vern.py run
    .venv/bin/python eval_internal/benchmark_valide/norm_vern.py analyze

Same prompt and wrapper as agent Q2 (`rag_sfar.retrieval.query_rewrite`, unchanged; MCQ options split off
by `split_options` and never shown to the model), file hand-off as in eval_internal/genprobe2_run.py.
Setups on tas_v6: REF = frozen C10_context_notes; NORM = QueryRewriteRetriever(normalize, add) over REF;
LEX+NORM = the same wrapper with retrieval config frozen + use_subword + use_medical_lexicon.
Metrics `harness.retrieval_metrics` (k = 64) on the full retrieved context ("full", as in the V1 tables)
and on the generator's context ("gen": select_within_budget(40, 30 000), as in Q2/G1).
Everything with question text stays in eval_internal/work/v1/ (git-ignored). The test part
(test_posthoc) is one post hoc pass on fixed configurations.
"""

from __future__ import annotations

import argparse
import json
import random
import secrets
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
from rag_sfar.evaluation import harness  # noqa: E402
from rag_sfar.evaluation.datasets import SPLITS_DIR, read_jsonl  # noqa: E402
from rag_sfar.generation.context import select_within_budget  # noqa: E402
from rag_sfar.retrieval import query_rewrite as qr  # noqa: E402

WORK = ROOT / "eval_internal/work/v1"
EXPORT = WORK / "exports/norm_vern"
KEYS = WORK / "keys/norm_vern.json"
ANSWERS = WORK / "answers/norm_vern.json"
ROWS = WORK / "norm_vern_rows.jsonl"
PARTS = ("dev", "test_posthoc")
K = 64
GEN_CHUNKS, GEN_CHARS = 40, 30000


def items() -> list[tuple[str, Any]]:
    return [(p, it) for p in PARTS for it in read_jsonl(SPLITS_DIR / "abpvern" / f"{p}.jsonl")]


def export() -> None:
    if EXPORT.exists() and any(EXPORT.iterdir()):
        sys.exit(f"{EXPORT} is not empty")
    by_key: dict[str, dict] = {}
    for part, it in items():
        stem, _ = qr.split_options(it.formatted_query())
        s, u = qr.rewrite_prompt("normalize", stem)
        k = qr.prompt_key(s, u)
        c = by_key.setdefault(k, {"system": s, "user": u, "key": k, "ids": []})
        c["ids"].append(f"{part}::{it.id}")
    cases = list(by_key.values())
    random.Random(secrets.randbits(64)).shuffle(cases)
    n_parts = max(1, round(len(cases) / 40))
    used: set[str] = set()
    for i in range(n_parts):
        pc = cases[i::n_parts]
        pd = EXPORT / f"part_{i:02d}"
        pd.mkdir(parents=True)
        for c in pc:
            cid = f"n{secrets.token_hex(5)}"
            while cid in used:
                cid = f"n{secrets.token_hex(5)}"
            used.add(cid)
            c["case_id"], c["part"] = cid, pd.name
        (pd / "input.json").write_text(json.dumps([{"case_id": c["case_id"], "system": c["system"], "user": c["user"]} for c in pc],
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    KEYS.parent.mkdir(parents=True, exist_ok=True)
    KEYS.write_text(json.dumps({"export_dir": str(EXPORT), "cases": cases}, ensure_ascii=False), encoding="utf-8")
    print(f"norm_vern: {len(cases)} prompts ({sum(len(c['ids']) for c in cases)} questions) in {n_parts} parts -> {EXPORT.relative_to(ROOT)}")
    for i in range(n_parts):
        print(f"  part_{i:02d}: {len(cases[i::n_parts])}")


def import_() -> None:
    keys = json.loads(KEYS.read_text(encoding="utf-8"))
    cases = {c["case_id"]: c for c in keys["cases"]}
    answers: dict[str, str] = {}
    errors: list[str] = []
    for part in sorted({c["part"] for c in cases.values()}):
        f = EXPORT / part / "output.json"
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
                qr.parse_rewrite("normalize", ans)
            except qr.FormatError as e:
                errors.append(f"{part}: {cid} format: {e}")
            answers[cid] = ans
    missing = sorted(set(cases) - set(answers))
    if missing:
        errors.append(f"{len(missing)} cases without answer")
    if errors:
        sys.exit("import refused:\n  " + "\n  ".join(errors))
    ANSWERS.parent.mkdir(parents=True, exist_ok=True)
    ANSWERS.write_text(json.dumps({"table": {cases[c]["key"]: a for c, a in answers.items()}}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"imported {len(answers)} answers -> {ANSWERS.relative_to(ROOT)}")


class Strict:
    def __init__(self, table: dict[str, str]) -> None:
        self.table, self.missing = table, 0

    def __call__(self, system: str, user: str) -> str:
        k = qr.prompt_key(system, user)
        if k not in self.table:
            self.missing += 1
            raise KeyError(k)
        return self.table[k]


def _m(it, ctx) -> dict[str, Any]:
    m = harness.retrieval_metrics(it, ctx, K)
    return {k: m.get(k) for k in ("sufficiency", "evidence_recall")}


def run() -> None:
    from rag_sfar.config import Settings

    s = Settings()
    ref = harness.select_configs("C10_context_notes")[0]
    assert ref.name == "C10_context_notes"
    lex = harness.ablation_variants(ref, "use_subword=true+use_medical_lexicon=true")[0]
    base = harness.load_retrievers(ROOT / "index", [ref.chunking_strategy], s.reranker_provider, s.reranker_model,
                                   index_map={ref.chunking_strategy: "tas_v6"})[ref.chunking_strategy]
    base.retrieve("anesthésie", config=ref)
    base.retrieve("anesthésie", config=lex)
    strict = Strict(json.loads(ANSWERS.read_text(encoding="utf-8"))["table"])
    norm = qr.QueryRewriteRetriever(base, qr.QueryRewriteConfig(variant="normalize", use="add"), strict)
    setups = {"REF": (base, ref), "NORM": (norm, ref), "LEX_NORM": (norm, lex)}
    t_all = time.perf_counter()
    with ROWS.open("w", encoding="utf-8") as f:
        for part, it in items():
            q = it.formatted_query()
            for name, (r, cfg) in setups.items():
                m0 = strict.missing
                t0 = time.perf_counter()
                ctx, _a, _t = r.retrieve(q, config=cfg)
                lat = (time.perf_counter() - t0) * 1000
                tr = getattr(r, "last_trace", None) if name != "REF" else None
                gen = select_within_budget(ctx, GEN_CHUNKS, GEN_CHARS)
                f.write(json.dumps({"part": part, "id": it.id, "setup": name, "latency_ms": round(lat, 1),
                                    "norm_used": bool(tr and tr.used), "missing_answers": strict.missing - m0,
                                    "full": _m(it, ctx), "gen": _m(it, gen)}) + "\n")
        print(f"done ({time.perf_counter() - t_all:.0f}s), missing answers: {strict.missing}", flush=True)
    print("ALL_DONE", flush=True)


def _fmt_mean(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "—"
    lo, hi = harness.bootstrap_ci(xs)
    return f"{100 * sum(xs) / len(xs):.1f} [{100 * lo:.1f}–{100 * hi:.1f}] (n={len(xs)})"


def _fmt_diff(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if not pairs:
        return "—"
    d = harness.paired_bootstrap_diff([p[0] for p in pairs], [p[1] for p in pairs])
    gain = sum(1 for x, y in pairs if y > x)
    loss = sum(1 for x, y in pairs if y < x)
    return f"{100 * d['diff']:+.1f} [{100 * d['ci_low']:+.1f} ; {100 * d['ci_high']:+.1f}] (n={len(pairs)}, +{gain}/−{loss})"


def analyze() -> None:
    rows = [json.loads(l) for l in ROWS.read_text().splitlines() if l.strip()]
    assert not any(r["missing_answers"] for r in rows)
    R = {(r["setup"], r["part"], r["id"]): r for r in rows}
    v = json.loads((ROOT / "eval_internal/benchmark_valide/diff_ids.json").read_text())["vernacular"]
    allids = {r["id"] for r in rows}
    subsets = {"171": allids, "88 modifiés": set(v["wording_changed_ids"]), "29 publiées": set(v["in_release_200_ids"])}
    L = ["## NORM sur les formulations des cliniciens (`abpvern`)", "",
         "REF = gelée ; NORM = normalisation de la question par LLM (Q2, variante normalize, mode add) ; LEX+NORM = NORM avec n-grammes + lexique. "
         "« full » = tout le contexte retourné (k = 64, comme les tableaux précédents) ; « gen » = contexte lu par le générateur (40 extraits, 30 000 caractères, comme Q2/G1). "
         "Différences appariées setup − REF, IC 95 % bootstrap ; +g/−p = questions gagnées / perdues. Test : passe post hoc unique.", ""]
    for scope in ("full", "gen"):
        for metric in ("sufficiency", "evidence_recall"):
            L += [f"### {metric} ({scope})", "", "| setup | sous-ensemble | dev | test (post hoc) |", "|---|---|---|---|"]
            for sname, keep in subsets.items():
                cells = []
                for part in PARTS:
                    ids = sorted(i for i in keep if ("REF", part, i) in R)
                    cells.append(_fmt_mean([R[("REF", part, i)][scope][metric] for i in ids]))
                L.append(f"| REF (niveau) | {sname} | " + " | ".join(cells) + " |")
            for setup in ("NORM", "LEX_NORM"):
                for sname, keep in subsets.items():
                    cells = []
                    for part in PARTS:
                        ids = sorted(i for i in keep if ("REF", part, i) in R)
                        cells.append(_fmt_diff([R[("REF", part, i)][scope][metric] for i in ids],
                                               [R[(setup, part, i)][scope][metric] for i in ids]))
                    L.append(f"| {setup} − REF | {sname} | " + " | ".join(cells) + " |")
            L.append("")
    used = Counter((r["part"], r["norm_used"]) for r in rows if r["setup"] == "NORM")
    lat = {s: sum(r["latency_ms"] for r in rows if r["setup"] == s) / sum(1 for r in rows if r["setup"] == s) for s in ("REF", "NORM", "LEX_NORM")}
    L += [f"Normalisation utilisée (requête ajoutée) : dev {used[('dev', True)]}/{used[('dev', True)] + used[('dev', False)]}, "
          f"test {used[('test_posthoc', True)]}/{used[('test_posthoc', True)] + used[('test_posthoc', False)]}. "
          "Latence de retrieval hors appel LLM (ms) : " + ", ".join(f"{k} {x:.0f}" for k, x in lat.items()), ""]
    print("\n".join(L))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "import", "run", "analyze"])
    a = ap.parse_args()
    {"export": export, "import": import_, "run": run, "analyze": analyze}[a.cmd]()


if __name__ == "__main__":
    main()
