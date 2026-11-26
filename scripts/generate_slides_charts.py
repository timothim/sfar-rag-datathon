#!/usr/bin/env python3
"""Generate clean, publication-grade SVG charts from `reports/ablation_results.json`
for Friday's SFAR Datathon restitution slides (zero external plotting dependencies!)."""

from __future__ import annotations

import json
from pathlib import Path


def _render_bar_svg(
    title: str,
    subtitle: str,
    labels: list[str],
    series: list[tuple[str, str, list[float]]],  # (name, color, values in 0..100)
    output_path: Path,
) -> None:
    w, h = 960, 480
    pad_l, pad_r, pad_t, pad_b = 70, 30, 108, 122
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    n_groups = len(labels)
    n_series = len(series)
    group_w = plot_w / max(1, n_groups)
    bar_w = min(28, (group_w * 0.72) / max(1, n_series))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#0b1220" rx="14"/>',
        f'<text x="{pad_l}" y="34" fill="#f1f5f9" font-family="system-ui,-apple-system,sans-serif" font-size="19" font-weight="700">{title}</text>',
        f'<text x="{pad_l}" y="56" fill="#94a3b8" font-family="system-ui,-apple-system,sans-serif" font-size="12.5">{subtitle}</text>',
    ]

    # Legend
    lx = pad_l
    for name, color, _ in series:
        parts.append(f'<rect x="{lx}" y="66" width="12" height="12" fill="{color}" rx="2"/>')
        parts.append(
            f'<text x="{lx + 18}" y="76" fill="#cbd5e1" font-family="system-ui,-apple-system,sans-serif" font-size="12">{name}</text>'
        )
        lx += 18 + len(name) * 7.2 + 22

    # Grid lines (0..100 step 20)
    for pct in (0, 20, 40, 60, 80, 100):
        y = pad_t + plot_h * (1 - pct / 100.0)
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" stroke="#1e293b" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_l - 10}" y="{y + 4:.1f}" text-anchor="end" fill="#64748b" font-family="system-ui,-apple-system,sans-serif" font-size="11">{pct}%</text>'
        )

    # Bars
    for g_idx, lbl in enumerate(labels):
        gx = pad_l + g_idx * group_w + group_w / 2.0
        total_bw = n_series * bar_w + (n_series - 1) * 4
        start_x = gx - total_bw / 2.0
        for s_idx, (_, color, vals) in enumerate(series):
            val = vals[g_idx]
            bh = plot_h * (max(0.0, min(100.0, val)) / 100.0)
            bx = start_x + s_idx * (bar_w + 4)
            by = pad_t + plot_h - bh
            parts.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="{color}" rx="3"/>'
            )
            parts.append(
                f'<text x="{bx + bar_w / 2:.1f}" y="{by - 5:.1f}" text-anchor="middle" fill="#e2e8f0" font-family="system-ui,-apple-system,sans-serif" font-size="10" font-weight="600">{val:.0f}%</text>'
            )
        short_lbl = lbl.replace("_", " ")
        parts.append(
            f'<text x="{gx:.1f}" y="{pad_t + plot_h + 18}" text-anchor="end" transform="rotate(-24 {gx:.1f} {pad_t + plot_h + 18})" fill="#cbd5e1" font-family="system-ui,-apple-system,sans-serif" font-size="11">{short_lbl}</text>'
        )

    parts.append("</svg>")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    res_path = Path("reports/ablation_results.json")
    if not res_path.exists():
        raise FileNotFoundError("Run `rag-sfar-eval` first to generate reports/ablation_results.json")
    data = json.loads(res_path.read_text(encoding="utf-8"))

    for ds_name, rows in data.items():
        if not rows:
            continue
        labels = [r["config_name"] for r in rows]
        ed_hit = [r["current_edition_hit_rate"] * 100.0 for r in rows]
        ev_rec = [(r["evidence_recall"] or 0.0) * 100.0 for r in rows]
        obs_rate = [r["obsolete_intrusion_rate"] * 100.0 for r in rows]
        _render_bar_svg(
            title=f"RAG-SFAR Ablation — {ds_name}",
            subtitle="Progression C0 (naïf) → C8 (Frontier 2026) : Édition en vigueur, Evidence Recall & Intrusion d'éditions obsolètes",
            labels=labels,
            series=[
                ("Édition en vigueur Hit@8", "#38bdf8", ed_hit),
                ("Evidence Recall@8", "#22c55e", ev_rec),
                ("Intrusion Obsolète (bas = mieux)", "#ef4444", obs_rate),
            ],
            output_path=Path(f"reports/chart_ablation_{ds_name}.svg"),
        )
    e2e_path = Path("reports/e2e_comparison.json")
    if e2e_path.exists():
        e2e = json.loads(e2e_path.read_text(encoding="utf-8"))
        runs = e2e.get("runs", [])
        if runs:
            model_name = runs[0].get("model", "LLM")
            n_q = runs[0].get("total_questions", 0)
            labels = [r["system"] for r in runs]
            raw_acc = [r["overall_accuracy"] * 100.0 for r in runs]
            q1_acc = [r["rag_x_diagnostics"]["grounded_accuracy"] * 100.0 for r in runs]
            src_rate = [r["sourcing_rate"] * 100.0 for r in runs]
            cue = [r["rag_x_diagnostics"]["context_utilization_efficiency"] * 100.0 for r in runs]
            _render_bar_svg(
                title=f"RAG-SFAR End-to-End & Diagnostic RAG-X — {model_name} ({n_q} questions)",
                subtitle="Raw Accuracy vs Grounded Accuracy (Q1) vs Sourcing Officiel vs CUE (Context Utilization Efficiency)",
                labels=labels,
                series=[
                    ("Accuracy Brute", "#38bdf8", raw_acc),
                    ("Grounded Accuracy (Q1)", "#22c55e", q1_acc),
                    ("Sourcing Officiel", "#a855f7", src_rate),
                    ("CUE (Q1 / (Q1+Q3))", "#f59e0b", cue),
                ],
                output_path=Path("reports/chart_e2e_rag_x.svg"),
            )
    print("Generated SVG charts in reports/")


if __name__ == "__main__":
    main()
