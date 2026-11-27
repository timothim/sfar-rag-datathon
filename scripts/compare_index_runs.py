"""Paired comparison of two retrieval-only evaluation tags (same suites, same configs).

Usage:
  .venv/bin/python scripts/compare_index_runs.py <tag_a> <tag_b> [--suites abpe171,multirfe_synth,abp171]
      [--markdown out.md] [--per-item]

For every suite, picks the latest `reports/eval/*_<suite>_dev_<tag>.json` of each tag, and for
each config present in both prints the means of the main retrieval metrics and the paired
bootstrap difference b - a (rag_sfar.evaluation.harness.paired_bootstrap_diff, 2 000 draws),
plus passage hit@8 recomputed from passage ranks. With --per-item, lists the questions whose
passage rank / sufficiency changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_sfar.evaluation.harness import paired_bootstrap_diff  # noqa: E402

METRICS = ["passage_hit", "passage_hit@8", "passage_mrr", "evidence_recall", "sufficiency", "doc_hit", "obsolete_intrusion"]


def latest(suite: str, tag: str) -> Path | None:
    cands = sorted((ROOT / "reports" / "eval").glob(f"*_{suite}_dev_{tag}.json"))
    return cands[-1] if cands else None


def item_values(row: dict, metric: str):
    if metric == "passage_hit@8":
        r = row.get("passage_rank")
        if "passage_hit" not in row:
            return None
        return 1.0 if (r is not None and r <= 8) else 0.0
    return row.get(metric)


def compare(tag_a: str, tag_b: str, suites: list[str], per_item: bool) -> str:
    out: list[str] = []
    for suite in suites:
        pa, pb = latest(suite, tag_a), latest(suite, tag_b)
        if not pa or not pb:
            out.append(f"\n## {suite}: missing report ({pa}, {pb})")
            continue
        ra, rb = json.loads(pa.read_text()), json.loads(pb.read_text())
        runs_a = {r["config"]: r for r in ra["runs"]}
        runs_b = {r["config"]: r for r in rb["runs"]}
        out.append(f"\n## {suite} ({pa.name} vs {pb.name})")
        for cfg in runs_a:
            if cfg not in runs_b:
                continue
            rows_a = {r["id"]: r for r in runs_a[cfg]["rows"]}
            rows_b = {r["id"]: r for r in runs_b[cfg]["rows"]}
            ids = [i for i in rows_a if i in rows_b]
            short = "C9+fenêtres" if "context_window" in cfg else "C9"
            out.append(f"\n### {short} (n={len(ids)})\n")
            out.append("| Métrique | A | B | B − A [IC 95 %] |")
            out.append("|---|---:|---:|---|")
            for m in METRICS:
                va = [item_values(rows_a[i], m) for i in ids]
                vb = [item_values(rows_b[i], m) for i in ids]
                pairs = [(x, y) for x, y in zip(va, vb) if x is not None and y is not None]
                if not pairs:
                    continue
                d = paired_bootstrap_diff([x for x, _ in pairs], [y for _, y in pairs])
                ma = 100 * sum(x for x, _ in pairs) / len(pairs)
                mb = 100 * sum(y for _, y in pairs) / len(pairs)
                scale = 100
                out.append(
                    f"| {m} | {ma:.1f} | {mb:.1f} | {scale*d['diff']:+.1f} [{scale*d['ci_low']:+.1f} ; {scale*d['ci_high']:+.1f}] |"
                )
            if per_item:
                changed = []
                for i in ids:
                    a, b = rows_a[i], rows_b[i]
                    ka = (a.get("passage_rank"), a.get("sufficiency"), round(a.get("evidence_recall") or 0, 2))
                    kb = (b.get("passage_rank"), b.get("sufficiency"), round(b.get("evidence_recall") or 0, 2))
                    if ka != kb:
                        changed.append(f"- {i}: rang passage {ka[0]} → {kb[0]} ; suff {ka[1]} → {kb[1]} ; rappel preuves {ka[2]} → {kb[2]}")
                if changed:
                    out.append("\nQuestions modifiées :\n" + "\n".join(changed))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag_a")
    ap.add_argument("tag_b")
    ap.add_argument("--suites", default="abpe171,multirfe_synth,abp171")
    ap.add_argument("--markdown", type=Path)
    ap.add_argument("--per-item", action="store_true")
    a = ap.parse_args()
    txt = compare(a.tag_a, a.tag_b, a.suites.split(","), a.per_item)
    if a.markdown:
        a.markdown.write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
