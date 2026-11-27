"""Tables and paired bootstrap differences from results/*.jsonl (no model loaded).

    .venv/bin/python eval_internal/robustness/analyze.py > eval_internal/robustness/results/summary.md
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from rag_sfar.evaluation.harness import bootstrap_ci, paired_bootstrap_diff

HERE = Path(__file__).resolve().parent
CONFIGS = ["frozen", "subword", "lexicon", "subword_lexicon", "lexicon_plain", "glossary", "glossary_a2l", "bm25_only", "dense_only"]
PERTS = ["clean", "typo1", "typo3", "noaccent", "telegraphic", "abbr", "expand", "abbr_user"]
METRICS = {"abpe171": ["sufficiency", "evidence_recall"], "multirfe_synth": ["passage_hit"]}


def load():
    data = defaultdict(dict)  # (config, suite, pert) -> {id: row}
    for c in CONFIGS:
        p = HERE / "results" / f"{c}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            data[(c, r["suite"], r["perturbation"])][r["id"]] = r
    return data


def pct(x):
    return f"{100 * x:.1f}"


def diff_str(d):
    return f"{100 * d['diff']:+.1f} [{100 * d['ci_low']:+.1f} ; {100 * d['ci_high']:+.1f}]"


def paired(rows_a, rows_b, metric, ids=None):
    ids = [i for i in (ids or rows_a) if i in rows_b and metric in rows_a[i] and metric in rows_b[i]]
    if not ids:
        return None, 0
    return paired_bootstrap_diff([rows_a[i][metric] for i in ids], [rows_b[i][metric] for i in ids]), len(ids)


def main() -> None:
    data = load()
    out = {}
    print("# Robustesse du retrieval — tableaux bruts (généré par analyze.py)\n")
    for suite, metrics in METRICS.items():
        for metric in metrics:
            print(f"\n## {suite} — {metric} (moyenne %, IC 95 % bootstrap)\n")
            print("| config | " + " | ".join(PERTS) + " |")
            print("|---|" + "---|" * len(PERTS))
            for c in CONFIGS:
                cells = []
                for p in PERTS:
                    rows = data.get((c, suite, p))
                    vals = [r[metric] for r in (rows or {}).values() if metric in r]
                    if not vals:
                        cells.append("–")
                        continue
                    lo, hi = bootstrap_ci(vals)
                    cells.append(f"{pct(sum(vals) / len(vals))} [{pct(lo)}–{pct(hi)}]")
                    out[f"{c}|{suite}|{p}|{metric}"] = sum(vals) / len(vals)
                print(f"| {c} | " + " | ".join(cells) + " |")
            # (i) perturbed - clean, frozen
            print(f"\n### {suite} — {metric} : perturbé − propre, configuration figée (apparié ; toutes les questions / questions modifiées seulement)\n")
            print("| perturbation | n modifiées | Δ toutes | Δ modifiées |")
            print("|---|---|---|---|")
            for c in ["frozen"]:
                clean = data.get((c, suite, "clean"), {})
                for p in PERTS[1:]:
                    rows = data.get((c, suite, p))
                    if not rows:
                        continue
                    changed = [i for i, r in rows.items() if r["changed"]]
                    d_all, n_all = paired(clean, rows, metric)
                    d_ch, n_ch = paired(clean, rows, metric, changed)
                    print(f"| {p} | {len(changed)} (n métrique {n_ch}) | {diff_str(d_all) if d_all else '–'} | {diff_str(d_ch) if d_ch else '–'} |")
            # (ii) variant - frozen on each set
            print(f"\n### {suite} — {metric} : variante − figée, par jeu (apparié, toutes les questions du jeu ; pour abbr/expand/abbr_user : questions modifiées seulement)\n")
            print("| variante | " + " | ".join(PERTS) + " |")
            print("|---|" + "---|" * len(PERTS))
            for c in CONFIGS[1:]:
                cells = []
                for p in PERTS:
                    a, b = data.get(("frozen", suite, p)), data.get((c, suite, p))
                    if not a or not b:
                        cells.append("–")
                        continue
                    ids = [i for i, r in a.items() if r["changed"]] if p in ("abbr", "expand", "abbr_user") else None
                    d, n = paired(a, b, metric, ids)
                    cells.append(f"{diff_str(d)} (n={n})" if d else "–")
                print(f"| {c} | " + " | ".join(cells) + " |")
    # latency and context
    print("\n## Latence de `retrieve` et taille du contexte (toutes requêtes, tous jeux)\n")
    print("| config | n | latence moy. (ms) | médiane | p95 | contexte moy. (car.) | blocs moy. |")
    print("|---|---|---|---|---|---|---|")
    for c in CONFIGS:
        rows = [r for (cc, _s, _p), rs in data.items() if cc == c for r in rs.values()]
        if not rows:
            continue
        lat = sorted(r["latency_ms"] for r in rows)
        print(f"| {c} | {len(rows)} | {statistics.mean(lat):.0f} | {lat[len(lat) // 2]:.0f} | {lat[int(0.95 * len(lat))]:.0f} | "
              f"{statistics.mean(r['ctx_chars'] for r in rows):.0f} | {statistics.mean(r['n_chunks'] for r in rows):.1f} |")
    # glossary expansion coverage
    print("\n## Requêtes étendues par le glossaire du corpus (config `glossary`)\n")
    print("| suite | " + " | ".join(PERTS) + " |")
    print("|---|" + "---|" * len(PERTS))
    for suite in METRICS:
        cells = []
        for p in PERTS:
            rows = data.get(("glossary", suite, p), {})
            cells.append(f"{sum(1 for r in rows.values() if r['expansion'])}/{len(rows)}" if rows else "–")
        print(f"| {suite} | " + " | ".join(cells) + " |")
    (HERE / "results" / "means.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
