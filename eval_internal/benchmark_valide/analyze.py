"""V1: tables from eval_internal/work/v1/retrieval_rows.jsonl (ids + metrics) -> reports/agents/V1_annexes/retrieval_tables.md"""

from __future__ import annotations

import json
from pathlib import Path

from rag_sfar.evaluation.harness import bootstrap_ci, paired_bootstrap_diff

ROOT = Path(__file__).resolve().parents[2]
ROWS = ROOT / "eval_internal/work/v1/retrieval_rows.jsonl"
OUT = ROOT / "reports/agents/V1_annexes/retrieval_tables.md"
CONFIGS = ("frozen", "subword", "lexicon", "subword_lexicon")
PARTS = (("dev", "dev"), ("test_posthoc", "test (post hoc)"))
METRICS = ("sufficiency", "evidence_recall")


def main() -> None:
    rows = [json.loads(l) for l in ROWS.read_text().splitlines() if l.strip()]
    R = {(r["config"], r["suite"], r["part"], r["id"]): r for r in rows}
    diff = json.loads((ROOT / "eval_internal/benchmark_valide/diff_ids.json").read_text())
    v = diff["vernacular"]
    paired = set(R_ids for R_ids in {r["id"] for r in rows}) - set(v["not_in_paired_149_ids"])
    subsets = {"88 énoncés modifiés": set(v["wording_changed_ids"]), "149 appariés (experts)": paired,
               "29 reformulations publiées": set(v["in_release_200_ids"])}
    ids = {p: sorted({r["id"] for r in rows if r["part"] == p}, key=lambda x: int(x[1:])) for p, _ in PARTS}
    L = ["# V1 — retrieval seul, benchmark validé (abpv171) et vernaculaire (abpvern)", "",
         "Index `tas_v6`, k = 64, configuration gelée `C10_context_notes` et variantes (n-grammes de caractères, lexique, les deux). "
         "IC 95 % bootstrap (moyenne ; différences appariées b − a, 2 000 tirages). n = questions où la métrique est définie. "
         "**Côté test : passe post hoc unique sur configurations fixes (test d'abpe171 déjà utilisé par l'évaluation finale), rien n'est réglé dessus.**", ""]
    def vals(cfg, suite, part, metric, keep):
        return [(i, R[(cfg, suite, part, i)].get(metric)) for i in ids[part] if i in keep and (cfg, suite, part, i) in R]
    def fmt_mean(xs):
        xs = [x for x in xs if x is not None]
        if not xs:
            return "—"
        lo, hi = bootstrap_ci(xs)
        return f"{100 * sum(xs) / len(xs):.1f} [{100 * lo:.1f}–{100 * hi:.1f}] (n={len(xs)})"
    def fmt_diff(a, b):
        pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
        if not pairs:
            return "—"
        d = paired_bootstrap_diff([p[0] for p in pairs], [p[1] for p in pairs])
        nchg = sum(1 for x, y in pairs if x != y)
        return f"{100 * d['diff']:+.1f} [{100 * d['ci_low']:+.1f} ; {100 * d['ci_high']:+.1f}] (n={len(pairs)}, {nchg} discordantes)"
    allids = set(R_ids for R_ids in {r["id"] for r in rows})
    for metric in METRICS:
        L += [f"## {metric} — niveaux", "", "| config | jeu | " + " | ".join(lbl for _, lbl in PARTS) + " |", "|---|---|" + "---|" * len(PARTS)]
        for cfg in CONFIGS:
            for suite in ("abpv171", "abpvern"):
                L.append(f"| {cfg} | {suite} | " + " | ".join(fmt_mean([x for _, x in vals(cfg, suite, p, metric, allids)]) for p, _ in PARTS) + " |")
        L.append("")
        L += [f"## {metric} — effet de formulation : vernaculaire − standard (apparié)", "",
              "| config | sous-ensemble | " + " | ".join(lbl for _, lbl in PARTS) + " |", "|---|---|" + "---|" * len(PARTS)]
        for cfg in CONFIGS:
            for sname, keep in subsets.items():
                cells = []
                for p, _ in PARTS:
                    a = dict(vals(cfg, "abpv171", p, metric, keep)); b = dict(vals(cfg, "abpvern", p, metric, keep))
                    k = [i for i in a if i in b]
                    cells.append(fmt_diff([a[i] for i in k], [b[i] for i in k]))
                L.append(f"| {cfg} | {sname} | " + " | ".join(cells) + " |")
        L.append("")
        L += [f"## {metric} — variante − gelée (apparié), par jeu", "",
              "| variante | jeu / sous-ensemble | " + " | ".join(lbl for _, lbl in PARTS) + " |", "|---|---|" + "---|" * len(PARTS)]
        for cfg in CONFIGS[1:]:
            for suite, sname, keep in (("abpv171", "standard, 171", allids), ("abpvern", "vernaculaire, 171", allids),
                                       ("abpvern", "vernaculaire, 88 modifiés", subsets["88 énoncés modifiés"])):
                cells = []
                for p, _ in PARTS:
                    a = dict(vals("frozen", suite, p, metric, keep)); b = dict(vals(cfg, suite, p, metric, keep))
                    k = [i for i in a if i in b]
                    cells.append(fmt_diff([a[i] for i in k], [b[i] for i in k]))
                L.append(f"| {cfg} | {sname} | " + " | ".join(cells) + " |")
        L.append("")
    # failing ids (frozen), for listing only
    L += ["## Questions sans suffisance (configuration gelée) — identifiants seulement", ""]
    for suite in ("abpv171", "abpvern"):
        for p, lbl in PARTS:
            f = [i for i, x in vals("frozen", suite, p, "sufficiency", allids) if x == 0]
            L.append(f"- {suite} {lbl} : {', '.join(f) or '—'}")
    lat = {c: sum(r["latency_ms"] for r in rows if r["config"] == c) / max(1, sum(1 for r in rows if r["config"] == c)) for c in CONFIGS}
    L += ["", "Latence moyenne de `retrieve` (ms) : " + ", ".join(f"{c} {v:.0f}" for c, v in lat.items()), ""]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
