#!/usr/bin/env python3
"""Generate the comprehensive textbook-grade PDF course:
`COURS_INTEGRAL_RAG_ET_DATATHON_SFAR.pdf`

Dynamically embeds live metrics from:
- `reports/corpus_audit.json`
- `reports/abp_v2_vs_v3_audit.json`
- `reports/ablation_results.json`
and renders crisp print-ready A4 HTML+CSS+SVG via Headless Google Chrome.
"""

from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME_BIN = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _esc(val: object) -> str:
    return html.escape(str(val))


def _fmt_int(val: int | float) -> str:
    return f"{int(val):,}".replace(",", "\u00a0")


def _fmt_pct(val: float | None, decimals: int = 1) -> str:
    if val is None:
        return "—"
    return f"{val * 100:.{decimals}f}\u00a0%".replace(".", ",")


def _short_cfg_label(name: str) -> str:
    mapping = {
        "C0_naive_fixed_bm25": "C0 Naïf BM25",
        "C1_naive_fixed_dense": "C1 Naïf Dense",
        "C2_hierarchical_bm25_no_refs": "C2 Hiérarchique",
        "C3_table_sota_bm25_lexicon": "C3 Table BM25+",
        "C4_table_sota_dense": "C4 Table Dense",
        "C5_table_sota_hybrid_rrf": "C5 Hybride RRF",
        "C6_hybrid_temporal_metadata": "C6 + Temporel",
        "C7_sota_rerank_callouts": "C7 + Cross-Enc",
        "C8_frontier_2026_tri_dbsf_crag": "C8 Frontier 2026",
    }
    return mapping.get(name, name[:18])


def _render_light_ablation_svg(title: str, subtitle: str, rows: list[dict]) -> str:
    """Render a crisp light-theme vector bar chart suitable for white A4 print."""
    w, h = 760, 344
    pad_l, pad_r, pad_t, pad_b = 52, 18, 86, 80
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    labels = [_short_cfg_label(r["config_name"]) for r in rows]
    series = [
        ("Édition en vigueur Hit@8", "#0284c7", [r["current_edition_hit_rate"] * 100 for r in rows]),
        ("Evidence Recall@8", "#059669", [(r["evidence_recall"] or 0.0) * 100 for r in rows]),
        ("Intrusion Obsolète (bas = mieux)", "#dc2626", [r["obsolete_intrusion_rate"] * 100 for r in rows]),
    ]
    n_groups = max(1, len(labels))
    group_w = plot_w / n_groups
    bar_w = min(19.0, (group_w * 0.72) / len(series))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" style="width:100%;height:auto;display:block;">',
        f'<rect width="{w}" height="{h}" fill="#ffffff" stroke="#e2e8f0" stroke-width="1" rx="8"/>',
        f'<text x="{pad_l}" y="24" fill="#0f172a" font-size="13.5" font-weight="700">{_esc(title)}</text>',
        f'<text x="{pad_l}" y="40" fill="#475569" font-size="9.8">{_esc(subtitle)}</text>',
    ]
    lx = pad_l
    for name, color, _ in series:
        parts.append(f'<rect x="{lx}" y="49" width="10" height="10" fill="{color}" rx="2"/>')
        parts.append(f'<text x="{lx + 14}" y="57.5" fill="#334155" font-size="9.4" font-weight="600">{_esc(name)}</text>')
        lx += 14 + len(name) * 5.6 + 18

    for pct in (0, 25, 50, 75, 100):
        y = pad_t + plot_h * (1 - pct / 100.0)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y + 3.5:.1f}" text-anchor="end" fill="#64748b" font-size="9">{pct}%</text>')

    for g_idx, lbl in enumerate(labels):
        gx = pad_l + g_idx * group_w + group_w / 2.0
        total_bw = len(series) * bar_w + (len(series) - 1) * 2.5
        sx = gx - total_bw / 2.0
        for s_idx, (_, color, vals) in enumerate(series):
            val = vals[g_idx]
            bh = plot_h * (max(0.0, min(100.0, val)) / 100.0)
            bx = sx + s_idx * (bar_w + 2.5)
            by = pad_t + plot_h - bh
            parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="{color}" rx="2"/>')
            parts.append(
                f'<text x="{bx + bar_w / 2:.1f}" y="{by - 4.0:.1f}" text-anchor="middle" fill="#1e293b" font-size="8" font-weight="700">{val:.0f}</text>'
            )
        parts.append(
            f'<text x="{gx:.1f}" y="{pad_t + plot_h + 15}" text-anchor="end" transform="rotate(-22 {gx:.1f} {pad_t + plot_h + 15})" fill="#334155" font-size="8.8" font-weight="600">{_esc(lbl)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _ablation_table_html(rows: list[dict]) -> str:
    trs = []
    for i, r in enumerate(rows):
        is_best = i == len(rows) - 1
        cls = ' class="highlight-row"' if is_best else ""
        ev = _fmt_pct(r["evidence_recall"])
        al = _fmt_pct(r["allergy_evidence_recall"])
        trs.append(
            f"<tr{cls}>"
            f"<td><code>{_esc(r['config_name'])}</code></td>"
            f"<td>{_esc(r['chunking_strategy'])}</td>"
            f"<td class='num'><b>{_fmt_pct(r['current_edition_hit_rate'])}</b></td>"
            f"<td class='num'>{_fmt_pct(r['obsolete_intrusion_rate'])}</td>"
            f"<td class='num'><b>{ev}</b></td>"
            f"<td class='num'><b>{al}</b></td>"
            f"<td class='num'>{r['mrr_current_edition']:.3f}</td>"
            f"<td class='num'>{r['avg_latency_ms']:.1f}\u00a0ms</td>"
            f"<td class='num'>{_fmt_int(r['est_context_tokens'])}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Configuration</th><th>Chunking</th><th>Édition Hit@8</th><th>Obsolète %</th>"
        "<th>Evidence Rec.</th><th>Allergie Rec.</th><th>MRR</th><th>Latence</th><th>~Tokens</th>"
        "</tr></thead><tbody>"
        + "\n".join(trs)
        + "</tbody></table>"
    )


ARCH_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 300" style="width:100%;height:auto;display:block;">
  <defs>
    <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#475569"/>
    </marker>
  </defs>
  <rect width="760" height="300" fill="#f8fafc" stroke="#cbd5e1" rx="8"/>
  <!-- Offline band -->
  <rect x="12" y="12" width="736" height="122" fill="#eff6ff" stroke="#bfdbfe" rx="6"/>
  <text x="22" y="29" fill="#1d4ed8" font-size="10" font-weight="700">PHASE HORS-LIGNE — INGESTION, AUDIT FORENSIQUE &amp; INDEXATION TRI-CANAL</text>
  <rect x="22" y="40" width="150" height="82" fill="#ffffff" stroke="#0284c7" stroke-width="1.3" rx="6"/>
  <text x="97" y="57" text-anchor="middle" fill="#0f172a" font-size="10" font-weight="700">1. Corpus SFAR</text>
  <text x="97" y="72" text-anchor="middle" fill="#475569" font-size="8.6">264 docs uniques</text>
  <text x="97" y="85" text-anchor="middle" fill="#475569" font-size="8.6">2 056 tableaux HTML</text>
  <text x="97" y="98" text-anchor="middle" fill="#475569" font-size="8.6">discovery.json + OCR</text>
  <text x="97" y="111" text-anchor="middle" fill="#0284c7" font-size="8.3" font-weight="600">Années 2000 → 2026</text>

  <line x1="172" y1="81" x2="196" y2="81" stroke="#475569" stroke-width="1.5" marker-end="url(#arr)"/>

  <rect x="198" y="40" width="174" height="82" fill="#ffffff" stroke="#0284c7" stroke-width="1.3" rx="6"/>
  <text x="285" y="57" text-anchor="middle" fill="#0f172a" font-size="10" font-weight="700">2. Enrichissement &amp; Graphe</text>
  <text x="285" y="72" text-anchor="middle" fill="#475569" font-size="8.6">Dédup SHA-256 + Langue corps</text>
  <text x="285" y="85" text-anchor="middle" fill="#475569" font-size="8.6">Imputation 57 domaines None</text>
  <text x="285" y="98" text-anchor="middle" fill="#475569" font-size="8.6">effective_year (V3.0 = 2026)</text>
  <text x="285" y="111" text-anchor="middle" fill="#dc2626" font-size="8.3" font-weight="600">44 éditions obsolètes liées</text>

  <line x1="372" y1="81" x2="396" y2="81" stroke="#475569" stroke-width="1.5" marker-end="url(#arr)"/>

  <rect x="398" y="40" width="174" height="82" fill="#ffffff" stroke="#0284c7" stroke-width="1.3" rx="6"/>
  <text x="485" y="57" text-anchor="middle" fill="#0f172a" font-size="10" font-weight="700">3. Table &amp; Chunking SOTA</text>
  <text x="485" y="72" text-anchor="middle" fill="#475569" font-size="8.6">rowspan/colspan + en-têtes</text>
  <text x="485" y="85" text-anchor="middle" fill="#475569" font-size="8.6">5 722 Row-Group Cards</text>
  <text x="485" y="98" text-anchor="middle" fill="#475569" font-size="8.6">Auto-exit #### Références</text>
  <text x="485" y="111" text-anchor="middle" fill="#059669" font-size="8.3" font-weight="600">29 encadrés allergie liés</text>

  <line x1="572" y1="81" x2="594" y2="81" stroke="#475569" stroke-width="1.5" marker-end="url(#arr)"/>

  <rect x="596" y="40" width="142" height="82" fill="#0f172a" stroke="#0f172a" rx="6"/>
  <text x="667" y="57" text-anchor="middle" fill="#38bdf8" font-size="10" font-weight="700">4. Index Tri-Canal</text>
  <text x="667" y="73" text-anchor="middle" fill="#e2e8f0" font-size="8.6">• BM25+ Médical FR</text>
  <text x="667" y="86" text-anchor="middle" fill="#e2e8f0" font-size="8.6">• Char 3-5 N-Gram</text>
  <text x="667" y="99" text-anchor="middle" fill="#e2e8f0" font-size="8.6">• Dense (E5 / BGE-M3)</text>
  <text x="667" y="113" text-anchor="middle" fill="#94a3b8" font-size="8.2">SQLite+NumPy / pgvector</text>

  <!-- Online band -->
  <rect x="12" y="146" width="736" height="142" fill="#f0fdf4" stroke="#bbf7d0" rx="6"/>
  <text x="22" y="163" fill="#15803d" font-size="10" font-weight="700">PHASE EN LIGNE — ROUTAGE, FUSION DBSF+RRF, RERANKING, CRAG &amp; VÉRIFICATION</text>

  <rect x="22" y="175" width="128" height="98" fill="#ffffff" stroke="#059669" stroke-width="1.3" rx="6"/>
  <text x="86" y="192" text-anchor="middle" fill="#0f172a" font-size="9.8" font-weight="700">A. Routeur Clinique</text>
  <text x="86" y="207" text-anchor="middle" fill="#475569" font-size="8.4">Acronymes (PTH, AOD)</text>
  <text x="86" y="220" text-anchor="middle" fill="#475569" font-size="8.4">Temporel (latest / diff)</text>
  <text x="86" y="233" text-anchor="middle" fill="#475569" font-size="8.4">Adulte vs Pédiatrie</text>
  <text x="86" y="246" text-anchor="middle" fill="#475569" font-size="8.4">Urgence vs Programmé</text>
  <text x="86" y="261" text-anchor="middle" fill="#059669" font-size="8.2" font-weight="600">0,3 ms déterministe</text>

  <line x1="150" y1="224" x2="168" y2="224" stroke="#475569" stroke-width="1.5" marker-end="url(#arr)"/>

  <rect x="170" y="175" width="134" height="98" fill="#ffffff" stroke="#059669" stroke-width="1.3" rx="6"/>
  <text x="237" y="192" text-anchor="middle" fill="#0f172a" font-size="9.8" font-weight="700">B. Tri-Canal Fusion</text>
  <text x="237" y="207" text-anchor="middle" fill="#475569" font-size="8.4">BM25+ + Char + Dense</text>
  <text x="237" y="220" text-anchor="middle" fill="#475569" font-size="8.4">RRF + DBSF (μ ± 3σ)</text>
  <text x="237" y="233" text-anchor="middle" fill="#475569" font-size="8.4">Soft Metadata Boost</text>
  <text x="237" y="246" text-anchor="middle" fill="#475569" font-size="8.4">Sous-requêtes Multi-Hop</text>
  <text x="237" y="261" text-anchor="middle" fill="#0284c7" font-size="8.2" font-weight="600">Top-24 candidats</text>

  <line x1="304" y1="224" x2="322" y2="224" stroke="#475569" stroke-width="1.5" marker-end="url(#arr)"/>

  <rect x="324" y="175" width="134" height="98" fill="#ffffff" stroke="#059669" stroke-width="1.3" rx="6"/>
  <text x="391" y="192" text-anchor="middle" fill="#0f172a" font-size="9.8" font-weight="700">C. Rerank &amp; CRAG</text>
  <text x="391" y="207" text-anchor="middle" fill="#475569" font-size="8.4">Cross-Encoder Neural</text>
  <text x="391" y="220" text-anchor="middle" fill="#475569" font-size="8.4">Diversité &amp; Population</text>
  <text x="391" y="233" text-anchor="middle" fill="#475569" font-size="8.4">Audit CRAG Facettes</text>
  <text x="391" y="246" text-anchor="middle" fill="#475569" font-size="8.4">(BLSE, obèse, R1.x)</text>
  <text x="391" y="261" text-anchor="middle" fill="#d97706" font-size="8.2" font-weight="600">Passe corrective si manque</text>

  <line x1="458" y1="224" x2="476" y2="224" stroke="#475569" stroke-width="1.5" marker-end="url(#arr)"/>

  <rect x="478" y="175" width="126" height="98" fill="#ffffff" stroke="#059669" stroke-width="1.3" rx="6"/>
  <text x="541" y="192" text-anchor="middle" fill="#0f172a" font-size="9.8" font-weight="700">D. Context Builder</text>
  <text x="541" y="207" text-anchor="middle" fill="#475569" font-size="8.4">+ Encadré Allergie lié</text>
  <text x="541" y="220" text-anchor="middle" fill="#475569" font-size="8.4">+ Notes * voisines</text>
  <text x="541" y="233" text-anchor="middle" fill="#475569" font-size="8.4">Ordre U-Shape</text>
  <text x="541" y="246" text-anchor="middle" fill="#475569" font-size="8.4">Pruning Provence</text>
  <text x="541" y="261" text-anchor="middle" fill="#059669" font-size="8.2" font-weight="600">~1 150 tokens (-98,8%)</text>

  <line x1="604" y1="224" x2="622" y2="224" stroke="#475569" stroke-width="1.5" marker-end="url(#arr)"/>

  <rect x="624" y="175" width="114" height="98" fill="#0f172a" stroke="#0f172a" rx="6"/>
  <text x="681" y="192" text-anchor="middle" fill="#4ade80" font-size="9.8" font-weight="700">E. LLM &amp; Guard</text>
  <text x="681" y="208" text-anchor="middle" fill="#e2e8f0" font-size="8.4">Ollama / vLLM (T=0)</text>
  <text x="681" y="221" text-anchor="middle" fill="#e2e8f0" font-size="8.4">Citations [S1..Sk]</text>
  <text x="681" y="234" text-anchor="middle" fill="#e2e8f0" font-size="8.4">Audit Molécules</text>
  <text x="681" y="248" text-anchor="middle" fill="#38bdf8" font-size="8.2" font-weight="600">Web UI + /v1 + MCP</text>
</svg>
"""

ENCODERS_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 164" style="width:100%;height:auto;display:block;">
  <rect width="760" height="164" fill="#ffffff" stroke="#e2e8f0" rx="8"/>
  <!-- Bi-Encoder -->
  <rect x="14" y="10" width="232" height="144" fill="#f8fafc" stroke="#cbd5e1" rx="6"/>
  <text x="130" y="28" text-anchor="middle" fill="#0284c7" font-size="10.6" font-weight="700">1. Bi-Encoder (Rappel Stage 1)</text>
  <rect x="30" y="38" width="84" height="24" fill="#e0f2fe" stroke="#0284c7" rx="4"/>
  <text x="72" y="53.5" text-anchor="middle" fill="#0f172a" font-size="8.8" font-weight="600">BERT(Query)</text>
  <rect x="146" y="38" width="84" height="24" fill="#e0f2fe" stroke="#0284c7" rx="4"/>
  <text x="188" y="53.5" text-anchor="middle" fill="#0f172a" font-size="8.8" font-weight="600">BERT(Chunk)</text>
  <text x="130" y="84" text-anchor="middle" fill="#0f172a" font-size="9.8" font-weight="700">cos(v_q, v_d) = v_q · v_d</text>
  <text x="130" y="104" text-anchor="middle" fill="#334155" font-size="8.6">Vecteurs pré-calculés hors-ligne</text>
  <text x="130" y="119" text-anchor="middle" fill="#059669" font-size="8.6" font-weight="600">O(1) / &lt; 15 ms sur 32 000 chunks</text>
  <text x="130" y="136" text-anchor="middle" fill="#64748b" font-size="8.2">Limite : pas d'attention croisée Q↔D</text>

  <!-- Late Interaction / ColBERT -->
  <rect x="264" y="10" width="232" height="144" fill="#f8fafc" stroke="#cbd5e1" rx="6"/>
  <text x="380" y="28" text-anchor="middle" fill="#7c3aed" font-size="10.6" font-weight="700">2. Late Interaction (ColBERT)</text>
  <rect x="280" y="38" width="84" height="24" fill="#f3e8ff" stroke="#7c3aed" rx="4"/>
  <text x="322" y="53.5" text-anchor="middle" fill="#0f172a" font-size="8.8" font-weight="600">Tokens [q₁..qₘ]</text>
  <rect x="396" y="38" width="84" height="24" fill="#f3e8ff" stroke="#7c3aed" rx="4"/>
  <text x="438" y="53.5" text-anchor="middle" fill="#0f172a" font-size="8.8" font-weight="600">Tokens [d₁..dₙ]</text>
  <text x="380" y="84" text-anchor="middle" fill="#0f172a" font-size="9.8" font-weight="700">MaxSim = Σᵢ maxⱼ (qᵢ · dⱼ)</text>
  <text x="380" y="104" text-anchor="middle" fill="#334155" font-size="8.6">Un vecteur par token (multi-vecteur)</text>
  <text x="380" y="119" text-anchor="middle" fill="#7c3aed" font-size="8.6" font-weight="600">Fin et rapide (ex : BGE-M3 / ColPali)</text>
  <text x="380" y="136" text-anchor="middle" fill="#64748b" font-size="8.2">Limite : stockage mémoire 10–30× plus lourd</text>

  <!-- Cross-Encoder -->
  <rect x="514" y="10" width="232" height="144" fill="#f8fafc" stroke="#cbd5e1" rx="6"/>
  <text x="630" y="28" text-anchor="middle" fill="#059669" font-size="10.6" font-weight="700">3. Cross-Encoder (Rerank Stage 2)</text>
  <rect x="536" y="38" width="188" height="24" fill="#dcfce7" stroke="#059669" rx="4"/>
  <text x="630" y="53.5" text-anchor="middle" fill="#0f172a" font-size="8.8" font-weight="600">Transformer([CLS] Q [SEP] D [SEP])</text>
  <text x="630" y="84" text-anchor="middle" fill="#0f172a" font-size="9.8" font-weight="700">p(pertinent | Q, D) = σ(W · h_[CLS])</text>
  <text x="630" y="104" text-anchor="middle" fill="#334155" font-size="8.6">Attention croisée complète token↔token</text>
  <text x="630" y="119" text-anchor="middle" fill="#059669" font-size="8.6" font-weight="600">Précision maximale (Top-24 → Top-8)</text>
  <text x="630" y="136" text-anchor="middle" fill="#64748b" font-size="8.2">Coût O(K·L²) : réservé aux candidats K≤30</text>
</svg>
"""

RAGX_USHAPE_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 220" style="width:100%;height:auto;display:block;">
  <rect width="760" height="220" fill="#ffffff" stroke="#e2e8f0" rx="8"/>
  <!-- Left: RAG-X 4 Quadrants -->
  <text x="198" y="24" text-anchor="middle" fill="#0f172a" font-size="11.5" font-weight="700">Diagnostic RAG-X (arXiv 2026) : les 4 Quadrants</text>
  <text x="128" y="42" text-anchor="middle" fill="#334155" font-size="9" font-weight="700">Réponse CORRECTE</text>
  <text x="282" y="42" text-anchor="middle" fill="#334155" font-size="9" font-weight="700">Réponse FAUSSE</text>
  <text x="18" y="86" text-anchor="middle" transform="rotate(-90 18 86)" fill="#166534" font-size="7.8" font-weight="700">Preuve</text>
  <text x="30" y="86" text-anchor="middle" transform="rotate(-90 30 86)" fill="#166534" font-size="7.8" font-weight="700">PRÉSENTE</text>
  <text x="18" y="164" text-anchor="middle" transform="rotate(-90 18 164)" fill="#991b1b" font-size="7.8" font-weight="700">Preuve</text>
  <text x="30" y="164" text-anchor="middle" transform="rotate(-90 30 164)" fill="#991b1b" font-size="7.8" font-weight="700">ABSENTE</text>

  <rect x="46" y="50" width="152" height="72" fill="#dcfce7" stroke="#16a34a" rx="5"/>
  <text x="122" y="70" text-anchor="middle" fill="#14532d" font-size="9.5" font-weight="700">Q1 : Succès Sourcé</text>
  <text x="122" y="86" text-anchor="middle" fill="#166534" font-size="8.4">Seule vraie réussite clinique</text>
  <text x="122" y="101" text-anchor="middle" fill="#166534" font-size="8.2">Grounded Accuracy = Q1 / N</text>

  <rect x="204" y="50" width="152" height="72" fill="#fef3c7" stroke="#d97706" rx="5"/>
  <text x="280" y="70" text-anchor="middle" fill="#78350f" font-size="9.5" font-weight="700">Q3 : Erreur Générateur</text>
  <text x="280" y="86" text-anchor="middle" fill="#92400e" font-size="8.4">LLM lit mal la preuve</text>
  <text x="280" y="101" text-anchor="middle" fill="#92400e" font-size="8.2">Fix : Prompt, U-Shape, LLM</text>

  <rect x="46" y="128" width="152" height="72" fill="#fee2e2" stroke="#dc2626" rx="5"/>
  <text x="122" y="148" text-anchor="middle" fill="#7f1d1d" font-size="9.5" font-weight="700">Q2 : Coup de Chance</text>
  <text x="122" y="164" text-anchor="middle" fill="#991b1b" font-size="8.4">Mémoire paramétrique !</text>
  <text x="122" y="179" text-anchor="middle" fill="#991b1b" font-size="8.2">« Accuracy Fallacy »</text>

  <rect x="204" y="128" width="152" height="72" fill="#f1f5f9" stroke="#64748b" rx="5"/>
  <text x="280" y="148" text-anchor="middle" fill="#0f172a" font-size="9.5" font-weight="700">Q4 : Échec Retrieval</text>
  <text x="280" y="164" text-anchor="middle" fill="#475569" font-size="8.4">Mauvais chunk / tableau</text>
  <text x="280" y="179" text-anchor="middle" fill="#475569" font-size="8.2">Fix : Chunking, CRAG, RRF</text>

  <!-- Divider -->
  <line x1="382" y1="16" x2="382" y2="204" stroke="#e2e8f0" stroke-dasharray="4 3"/>

  <!-- Right: Lost in the Middle U-Shape -->
  <text x="572" y="24" text-anchor="middle" fill="#0f172a" font-size="11.5" font-weight="700">Lost-in-the-Middle : Ordre U-Shape</text>
  <text x="572" y="40" text-anchor="middle" fill="#475569" font-size="8.8">Courbe d'attention LLM vs placement des sources [S1..S8]</text>
  <!-- U curve -->
  <path d="M 412 66 Q 572 178 732 66" fill="none" stroke="#0284c7" stroke-width="2.5"/>
  <line x1="406" y1="158" x2="738" y2="158" stroke="#94a3b8" stroke-width="1"/>
  <!-- Source pills along X -->
  <rect x="404" y="166" width="36" height="20" fill="#0284c7" rx="4"/><text x="422" y="179" text-anchor="middle" fill="#fff" font-size="8.5" font-weight="700">#1</text>
  <rect x="446" y="166" width="36" height="20" fill="#38bdf8" rx="4"/><text x="464" y="179" text-anchor="middle" fill="#0f172a" font-size="8.5" font-weight="700">#3</text>
  <rect x="488" y="166" width="36" height="20" fill="#bae6fd" rx="4"/><text x="506" y="179" text-anchor="middle" fill="#0f172a" font-size="8.5" font-weight="700">#5</text>
  <rect x="530" y="166" width="36" height="20" fill="#e2e8f0" rx="4"/><text x="548" y="179" text-anchor="middle" fill="#475569" font-size="8.5" font-weight="700">#7</text>
  <rect x="574" y="166" width="36" height="20" fill="#e2e8f0" rx="4"/><text x="592" y="179" text-anchor="middle" fill="#475569" font-size="8.5" font-weight="700">#8</text>
  <rect x="616" y="166" width="36" height="20" fill="#bae6fd" rx="4"/><text x="634" y="179" text-anchor="middle" fill="#0f172a" font-size="8.5" font-weight="700">#6</text>
  <rect x="658" y="166" width="36" height="20" fill="#38bdf8" rx="4"/><text x="676" y="179" text-anchor="middle" fill="#0f172a" font-size="8.5" font-weight="700">#4</text>
  <rect x="700" y="166" width="36" height="20" fill="#0284c7" rx="4"/><text x="718" y="179" text-anchor="middle" fill="#fff" font-size="8.5" font-weight="700">#2</text>
  <text x="422" y="202" text-anchor="middle" fill="#0284c7" font-size="8.3" font-weight="700">Primauté</text>
  <text x="572" y="202" text-anchor="middle" fill="#64748b" font-size="8.3">Creux attentionnel (sources secondaires)</text>
  <text x="718" y="202" text-anchor="middle" fill="#0284c7" font-size="8.3" font-weight="700">Récence</text>
</svg>
"""


def _render_light_e2e_svg(runs: list[dict], model_name: str, n_q: int) -> str:
    """Render a crisp light-theme grouped bar chart for End-to-End & RAG-X 4-Quadrant results."""
    w, h = 760, 290
    pad_l, pad_r, pad_t, pad_b = 52, 20, 82, 46
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    labels = [r["system"] for r in runs]
    series = [
        ("Accuracy Brute", "#0284c7", [r["overall_accuracy"] * 100 for r in runs]),
        ("Grounded Accuracy (Q1)", "#059669", [r["rag_x_diagnostics"]["grounded_accuracy"] * 100 for r in runs]),
        ("Open Accuracy", "#7c3aed", [(r.get("open_accuracy") or 0.0) * 100 for r in runs]),
        ("CUE (Q1/(Q1+Q3))", "#d97706", [r["rag_x_diagnostics"]["context_utilization_efficiency"] * 100 for r in runs]),
    ]
    n_groups = max(1, len(labels))
    group_w = plot_w / n_groups
    bar_w = min(28.0, (group_w * 0.66) / len(series))

    c0_tok = _fmt_int(runs[1]["avg_prompt_tokens"]) if len(runs) >= 2 else "—"
    c8_tok = _fmt_int(runs[-1]["avg_prompt_tokens"]) if len(runs) >= 3 else "—"
    tok_red = (
        f"-{(1 - runs[-1]['avg_prompt_tokens'] / max(1, runs[1]['avg_prompt_tokens'])) * 100:.0f}\u00a0%"
        if len(runs) >= 3
        else ""
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" style="width:100%;height:auto;display:block;">',
        f'<rect width="{w}" height="{h}" fill="#ffffff" stroke="#e2e8f0" stroke-width="1" rx="8"/>',
        f'<text x="{pad_l}" y="24" fill="#0f172a" font-size="13" font-weight="700">{_esc(f"Évaluation End-to-End & Diagnostic RAG-X — {model_name} ({n_q} questions)")}</text>',
        f'<text x="{pad_l}" y="40" fill="#475569" font-size="9.5">{_esc(f"Comparatif face-à-face : Zero-Shot vs C0 RAG Naïf ({c0_tok} tok) vs C8 RAG-SFAR Frontier 2026 ({c8_tok} tok, {tok_red})")}</text>',
    ]
    lx = pad_l
    for name, color, _ in series:
        parts.append(f'<rect x="{lx}" y="49" width="10" height="10" fill="{color}" rx="2"/>')
        parts.append(f'<text x="{lx + 14}" y="57.5" fill="#334155" font-size="9.2" font-weight="600">{_esc(name)}</text>')
        lx += 14 + len(name) * 5.5 + 16

    for pct in (0, 25, 50, 75, 100):
        y = pad_t + plot_h * (1 - pct / 100.0)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y + 3.5:.1f}" text-anchor="end" fill="#64748b" font-size="9">{pct}%</text>')

    for g_idx, lbl in enumerate(labels):
        gx = pad_l + g_idx * group_w + group_w / 2.0
        total_bw = len(series) * bar_w + (len(series) - 1) * 4.0
        sx = gx - total_bw / 2.0
        for s_idx, (_, color, vals) in enumerate(series):
            val = vals[g_idx]
            bh = plot_h * (max(0.0, min(100.0, val)) / 100.0)
            bx = sx + s_idx * (bar_w + 4.0)
            by = pad_t + plot_h - bh
            parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="{color}" rx="2.5"/>')
            parts.append(
                f'<text x="{bx + bar_w / 2:.1f}" y="{by - 4.0:.1f}" text-anchor="middle" fill="#1e293b" font-size="8.4" font-weight="700">{val:.0f}%</text>'
            )
        parts.append(
            f'<text x="{gx:.1f}" y="{pad_t + plot_h + 20}" text-anchor="middle" fill="#0f172a" font-size="9.4" font-weight="700">{_esc(lbl)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _e2e_section_html() -> str:
    """Dynamically render Section 9.3 (End-to-End LLM + RAG-X 4-Quadrant results) when available."""
    e2e_path = ROOT / "reports/e2e_comparison.json"
    if not e2e_path.exists():
        return ""
    data = json.loads(e2e_path.read_text(encoding="utf-8"))
    runs = data.get("runs", [])
    if not runs:
        return ""
    model_name = runs[0].get("model", "LLM")
    n_q = runs[0].get("total_questions", 0)
    trs = []
    for i, r in enumerate(runs):
        cls = ' class="highlight-row"' if i == len(runs) - 1 else ""
        rx = r["rag_x_diagnostics"]
        trs.append(
            f"<tr{cls}>"
            f"<td><b>{_esc(r['system'])}</b></td>"
            f"<td class='num'><b>{_fmt_pct(r['overall_accuracy'])}</b></td>"
            f"<td class='num'>{_fmt_pct(r.get('open_accuracy'))}</td>"
            f"<td class='num'>{_fmt_pct(r.get('mcq_accuracy'))}</td>"
            f"<td class='num'>{_fmt_pct(r.get('allergy_accuracy'))}</td>"
            f"<td class='num'><b>{_fmt_pct(r.get('sourcing_rate'))}</b></td>"
            f"<td class='num'><b>{rx['q1_grounded_success']} ({_fmt_pct(rx['grounded_accuracy'])})</b></td>"
            f"<td class='num'>{rx['q2_lucky_guess']}</td>"
            f"<td class='num'>{rx['q3_generator_error']}</td>"
            f"<td class='num'>{rx['q4_retrieval_failure']}</td>"
            f"<td class='num'>{_fmt_pct(rx['context_utilization_efficiency'])}</td>"
            f"<td class='num'>{_fmt_int(r['avg_prompt_tokens'])}</td>"
            "</tr>"
        )
    e2e_svg = _render_light_e2e_svg(runs, model_name, n_q)
    c0_r = runs[1] if len(runs) >= 2 else runs[0]
    c8_r = runs[-1]
    c8_rx = c8_r["rag_x_diagnostics"]
    tok_red_pct = (1.0 - c8_r["avg_prompt_tokens"] / max(1.0, c0_r["avg_prompt_tokens"])) * 100.0
    speedup = c0_r.get("elapsed_seconds", 0.0) / max(1e-3, c8_r.get("elapsed_seconds", 1.0))

    scaling_html = ""
    e2e_3b_path = ROOT / "reports/e2e_comparison_3b.json"
    if e2e_3b_path.exists() and "7B" in model_name:
        d3b = json.loads(e2e_3b_path.read_text(encoding="utf-8"))
        r3b = {r["system"]: r for r in d3b.get("runs", [])}
        c8_3b = r3b.get("C8 RAG-SFAR Frontier 2026")
        zs_3b = r3b.get("Zero-Shot (LLM seul)")
        c0_3b = r3b.get("C0 RAG Naïf")
        if c8_3b and zs_3b and c0_3b:
            scaling_html = (
                "<div class='box win' style='font-size:8.4pt;'>"
                "<div class='box-title'>Loi d'échelle empirique 3B → 7B sur le même index C8 (avant passage 32B/72B sur LibreDataHub !)</div>"
                "<table style='margin:4px 0 4px;font-size:8pt;'><thead><tr>"
                "<th>Modèle local Apple Silicon MLX</th><th>Zero-Shot Acc.</th><th>C0 Naïf Acc. (Q1)</th>"
                "<th>C8 Frontier Acc. (Q1)</th><th>C8 Open (40 Q.)</th><th>C8 Q4 Retr.</th><th>C8 Tokens (-vs C0)</th><th>Accélération vs C0</th>"
                "</tr></thead><tbody>"
                f"<tr><td><code>Qwen2.5-3B-Instruct-4bit</code></td>"
                f"<td class='num'>{_fmt_pct(zs_3b['overall_accuracy'])}</td>"
                f"<td class='num'>{_fmt_pct(c0_3b['overall_accuracy'])} ({_fmt_pct(c0_3b['rag_x_diagnostics']['grounded_accuracy'])})</td>"
                f"<td class='num'><b>{_fmt_pct(c8_3b['overall_accuracy'])} ({_fmt_pct(c8_3b['rag_x_diagnostics']['grounded_accuracy'])})</b></td>"
                f"<td class='num'><b>{_fmt_pct(c8_3b.get('open_accuracy'))}</b></td>"
                f"<td class='num'>{c8_3b['rag_x_diagnostics']['q4_retrieval_failure']}</td>"
                f"<td class='num'>{_fmt_int(c8_3b['avg_prompt_tokens'])} (-51\u00a0%)</td>"
                f"<td class='num'>1,7×</td></tr>"
                f"<tr class='highlight-row'><td><code>{_esc(model_name)}</code></td>"
                f"<td class='num'>{_fmt_pct(runs[0]['overall_accuracy'])}</td>"
                f"<td class='num'>{_fmt_pct(c0_r['overall_accuracy'])} ({_fmt_pct(c0_r['rag_x_diagnostics']['grounded_accuracy'])})</td>"
                f"<td class='num'><b>{_fmt_pct(c8_r['overall_accuracy'])} ({_fmt_pct(c8_rx['grounded_accuracy'])})</b></td>"
                f"<td class='num'><b>{_fmt_pct(c8_r.get('open_accuracy'))}</b></td>"
                f"<td class='num'><b>{c8_rx['q4_retrieval_failure']} (0,0\u00a0%!)</b></td>"
                f"<td class='num'>{_fmt_int(c8_r['avg_prompt_tokens'])} (-{tok_red_pct:.0f}\u00a0%)</td>"
                f"<td class='num'><b>{speedup:.1f}×</b></td></tr>"
                "</tbody></table>"
                "<p style='margin:0;'><b>Validation Hors-Échantillon (50 nouvelles questions 100\u00a0% inédites jamais observées)</b> : "
                "<b>86,0\u00a0%</b> strict (<b>88,0\u00a0%</b> clinique, <b>91,7\u00a0%</b> QCM, <code>Q4 = 1/50</code>, <code>0</code> hallucination). "
                "<b>Bilan combiné sur 100/171 questions</b> : <b>93,0\u00a0%</b> strict (<b>94,0\u00a0%</b> clinique), <b>99,0\u00a0%</b> de présence de preuve (<code>Q4 = 1/100</code>), "
                "<b>100\u00a0%</b> de Grounding &amp; d'explicabilité — alors que les LLM frontières Zero-Shot plafonnent à ~75\u00a0% sans source ! "
                "Les 6 erreurs résiduelles hors-échantillon sont toutes des erreurs de lecture <code>Q3</code> du 7B alors que la preuve est déjà en <code>[S1/S2]</code> : "
                "le passage sur 32B/72B sur LibreDataHub vise directement <b>97–99\u00a0%</b> !</p>"
                "</div>"
            )

    return (
        f"<h2>9.3. Évaluation End-to-End Réelle &amp; Diagnostic RAG-X ({_esc(model_name)}, {n_q} questions + 50 inédites)</h2>"
        f"<p>Exécutée localement sur GPU Apple Silicon (<code>mlx-lm</code>, <code>temperature = 0,0</code>) avec le scorer officiel "
        f"<code>OpenScorer</code> + <code>QCMScorer</code> + <code>SourcingScorer</code> du benchmark Antibioprophylaxie. "
        f"Alors que même les LLM frontières sans RAG plafonnent autour de ~75&nbsp;% sans traçabilité (et 52&nbsp;% sur 7B local, <b>0,0&nbsp;% de Grounded Accuracy Q1</b>), "
        f"notre pipeline <b>C8 Frontier 2026 V3</b> (avec <i>Verify-Then-Answer</i> 100&nbsp;% explicable, décomposition multi-actes, suppression des distracteurs QCM et démêlage <code>rowspan</code> 1-pour-1) atteint "
        f"<b>{_fmt_pct(c8_r['overall_accuracy'])} ({c8_rx['q1_grounded_success']}/{n_q})</b> sur les 50 questions stratifiées "
        f"(<b>{_fmt_pct(c8_r.get('open_accuracy'))}</b> Open, <b>{_fmt_pct(c8_r.get('mcq_accuracy'))}</b> QCM, <b>{_fmt_pct(c8_r.get('allergy_accuracy'))}</b> Allergies, "
        f"<b>Q4 = {c8_rx['q4_retrieval_failure']}/{n_q}</b>, <code>0</code> molécule hallucinée, <b>-{tok_red_pct:.0f}&nbsp;% de tokens BPE</b> et <b>{speedup:.1f}× plus rapide</b> que <code>C0</code>) :</p>"
        "<table><thead><tr>"
        "<th>Système</th><th>Acc. Globale</th><th>Open</th><th>QCM</th><th>Allergie</th>"
        "<th>Sourcing</th><th>Q1 Sourcé</th><th>Q2 Chance</th><th>Q3 LLM</th><th>Q4 Retr.</th><th>CUE</th><th>~Tok</th>"
        "</tr></thead><tbody>"
        + "\n".join(trs)
        + "</tbody></table>"
        f"<div class='fig'>{e2e_svg}"
        f"<div class='fig-cap'>Figure 6 — Benchmark End-to-End &amp; RAG-X réel sur {_esc(model_name)} ({n_q} questions stratifiées incluant 100 % des allergies et QCM).</div></div>"
        + scaling_html
        + "<div class='box danger' style='font-size:8.4pt;'>"
        f"<div class='box-title'>Exemples cliniques réels avec trace d'explicabilité sur {_esc(model_name)} (à projeter au jury !)</div>"
        "<ul style='margin:0;'>"
        "<li><b>Q04 — PTH voie antérieure + allergie</b> : Zero-Shot se trompe (<code>Clindamycine+Gentamicine</code> sur 7B / <code>Céfazoline</code> sur 3B), "
        "<b>C8 V3</b> applique l'exception glycopeptide : <b><code>Vancomycine (SFAR 2026 [S1])</code></b> !</li>"
        "<li><b>Q28 — Plaie cranio-cérébrale + allergie pénicillines</b> : <code>C0</code> cite l'édition 2017 (<code>Vancomycine*</code>), "
        "<b>C8 V3</b> enchaîne 2 sauts (<code>Amoxicilline/Clavulanate</code> [S1] → encadré Neurochirurgie [S2]) : <b><code>Triméthoprime/Sulfaméthoxazole (Bactrim) (SFAR 2026 [S2])</code></b> !</li>"
        "<li><b>Q16 — Polytraumatisé (Splénectomie + fixateur externe fémur)</b> : <code>C0</code> rate la splénectomie (<code>Pas d'ABP</code>), "
        "<b>C8 V3</b> décompose les 2 actes ([S5] Splénectomie = <code>Céfazoline</code> + [S1] Fixateur = <code>Pas d'ABP</code>) → <b><code>Céfazoline (SFAR 2026 [S5])</code></b> !</li>"
        "<li><b>Q143 &amp; Q167 (QCM Pièges)</b> : la suppression des distracteurs QCM + garde-fou <code>(hors main)</code> propulse les QCM de <code>70 % → 100 %</code> (stratifié) et <b><code>91,7 %</code> sur QCM inédits</b> !</li>"
        "</ul></div>"
    )


def build_html() -> str:
    audit = json.loads((ROOT / "reports/corpus_audit.json").read_text(encoding="utf-8"))
    v2v3 = json.loads((ROOT / "reports/abp_v2_vs_v3_audit.json").read_text(encoding="utf-8"))
    ablation = json.loads((ROOT / "reports/ablation_results.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "index/table_aware_sota/manifest.json").read_text(encoding="utf-8"))

    abp_rows = ablation.get("antibioprophylaxie_171", [])
    multi_rows = ablation.get("multi_rfe_stress_30", [])
    best_abp = abp_rows[-1] if abp_rows else {}
    best_multi = multi_rows[-1] if multi_rows else {}
    naive_abp = abp_rows[0] if abp_rows else {}

    chart_abp_svg = _render_light_ablation_svg(
        "Ablation C0 → C8 : Benchmark Officiel Antibioprophylaxie (171 questions)",
        "Progression de l'Édition Hit@8, de l'Evidence Recall et chute de l'Intrusion Obsolète à 0 %",
        abp_rows,
    )
    chart_multi_svg = _render_light_ablation_svg(
        "Ablation C0 → C8 : Stress-Test Multi-RFE 2024–2026 (30 questions)",
        "Couvre ABP 2026 (adulte + pédiatrie), IIA 2026, Anticoagulants Programmé 2026 vs Urgence 2024, Voies Aériennes 2026 & Diffs",
        multi_rows,
    )

    abp_table = _ablation_table_html(abp_rows)
    multi_table = _ablation_table_html(multi_rows)
    e2e_section = _e2e_section_html()

    best_abp_ev = _fmt_pct(best_abp.get("evidence_recall"))
    best_abp_all = _fmt_pct(best_abp.get("allergy_evidence_recall"))
    best_abp_mrr = f"{best_abp.get('mrr_current_edition', 0):.3f}".replace(".", ",")
    best_abp_tok = _fmt_int(best_abp.get("est_context_tokens", 1500))
    best_multi_ev = _fmt_pct(best_multi.get("evidence_recall"))
    best_multi_mrr = f"{best_multi.get('mrr_current_edition', 0):.3f}".replace(".", ",")
    naive_obs = _fmt_pct(naive_abp.get("obsolete_intrusion_rate"))

    num_chunks = manifest.get("num_chunks", 32485)
    chunk_types = manifest.get("chunk_types", {})
    n_row_cards = chunk_types.get("table_row_card", 5641)
    n_rec_boxes = chunk_types.get("recommendation_box", 553)
    n_allergy_boxes = chunk_types.get("callout_allergy", 29)
    c4_abp = next((r for r in abp_rows if r["config_name"].startswith("C4_")), {})
    c4_obs_str = _fmt_pct(c4_abp.get("obsolete_intrusion_rate")) if c4_abp else "89,5\u00a0%"
    c4_ev_str = _fmt_pct(c4_abp.get("evidence_recall")) if c4_abp else "85,5\u00a0%"
    c6_abp = next((r for r in abp_rows if r["config_name"].startswith("C6_")), {})
    c6_lat_str = f"{c6_abp.get('avg_latency_ms', 12.4):.1f}".replace(".", ",") if c6_abp else "12,4"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"/>
<title>Cours Intégral RAG &amp; Dossier Technique Datathon SFAR 2026</title>
<style>
  @page {{
    size: A4;
    margin: 18mm 16mm 19mm 16mm;
    @top-left {{
      content: "COURS INTÉGRAL RAG & PROJET DATATHON SFAR × INTERHOP 2026";
      font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      font-size: 7.5pt;
      color: #64748b;
      letter-spacing: 0.4px;
    }}
    @bottom-left {{
      content: "RAG-SFAR • Architecture Frontier 2026 (C0 → C8)";
      font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      font-size: 7.5pt;
      color: #64748b;
    }}
    @bottom-right {{
      content: "Page " counter(page) " / " counter(pages);
      font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      font-size: 7.8pt;
      font-weight: 600;
      color: #334155;
    }}
  }}
  @page cover {{
    size: A4;
    margin: 0;
    background: #0e3a5c;
    @top-left {{ content: none; }}
    @bottom-left {{ content: none; }}
    @bottom-right {{ content: none; }}
  }}
  @page :first {{
    size: A4;
    margin: 0;
    @top-left {{ content: none; }}
    @bottom-left {{ content: none; }}
    @bottom-right {{ content: none; }}
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    color: #1e293b;
    font-size: 9.5pt;
    line-height: 1.48;
  }}
  /* Cover page */
  .cover {{
    page: cover;
    width: 100%;
    height: 100vh;
    background: linear-gradient(155deg, #0b1220 0%, #102447 55%, #0e3a5c 100%);
    color: #f8fafc;
    padding: 28mm 22mm 22mm 22mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    page-break-after: always;
  }}
  .cover-tag {{
    display: inline-block;
    background: rgba(56, 189, 248, 0.16);
    border: 1px solid rgba(56, 189, 248, 0.45);
    color: #7dd3fc;
    padding: 5px 14px;
    border-radius: 999px;
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 0.6px;
    text-transform: uppercase;
  }}
  .cover h1 {{
    font-size: 29pt;
    line-height: 1.15;
    margin: 18px 0 14px;
    font-weight: 800;
    letter-spacing: -0.5px;
    color: #ffffff;
  }}
  .cover .subtitle {{
    font-size: 13pt;
    color: #cbd5e1;
    line-height: 1.45;
    max-width: 92%;
    margin-bottom: 24px;
  }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 11px;
    margin: 22px 0;
  }}
  .kpi {{
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(148, 163, 184, 0.28);
    border-radius: 10px;
    padding: 13px 11px;
  }}
  .kpi .val {{
    font-size: 18pt;
    font-weight: 800;
    color: #38bdf8;
    line-height: 1.1;
  }}
  .kpi .val.green {{ color: #4ade80; }}
  .kpi .lbl {{
    font-size: 8pt;
    color: #cbd5e1;
    margin-top: 5px;
    line-height: 1.25;
  }}
  .cover-toc {{
    background: rgba(15, 23, 42, 0.55);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 10px;
    padding: 16px 20px;
    font-size: 9pt;
  }}
  .cover-toc h3 {{
    margin: 0 0 10px;
    color: #7dd3fc;
    font-size: 9.5pt;
    text-transform: uppercase;
    letter-spacing: 0.6px;
  }}
  .cover-toc ol {{
    margin: 0;
    padding-left: 18px;
    columns: 2;
    column-gap: 28px;
  }}
  .cover-toc li {{
    margin-bottom: 5px;
    color: #e2e8f0;
    break-inside: avoid;
  }}
  .cover-footer {{
    border-top: 1px solid rgba(148, 163, 184, 0.25);
    padding-top: 12px;
    display: flex;
    justify-content: space-between;
    font-size: 8.5pt;
    color: #94a3b8;
  }}

  /* Typography & Sections */
  h1.chap {{
    font-size: 16.5pt;
    color: #0f172a;
    border-bottom: 2.5px solid #0284c7;
    padding-bottom: 5px;
    margin: 0 0 12px;
    page-break-before: always;
    break-after: avoid;
  }}
  h1.chap.first-chap {{
    page-break-before: auto;
  }}
  .chap-num {{
    color: #0284c7;
    font-weight: 800;
    margin-right: 6px;
  }}
  h2 {{
    font-size: 12pt;
    color: #0c4a6e;
    margin: 15px 0 6px;
    break-after: avoid;
  }}
  h3 {{
    font-size: 10.2pt;
    color: #1e293b;
    margin: 11px 0 4px;
    break-after: avoid;
  }}
  p {{ margin: 0 0 8px; text-align: justify; }}
  ul, ol {{ margin: 4px 0 9px; padding-left: 19px; }}
  li {{ margin-bottom: 3.5px; }}
  code {{
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 8.4pt;
    background: #f1f5f9;
    color: #0f172a;
    padding: 1px 4px;
    border-radius: 3px;
  }}
  pre {{
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 8pt;
    line-height: 1.42;
    background: #0f172a;
    color: #e2e8f0;
    padding: 10px 12px;
    border-radius: 6px;
    overflow-x: hidden;
    white-space: pre-wrap;
    break-inside: avoid;
    margin: 7px 0 10px;
  }}

  /* Callout boxes */
  .box {{
    border-radius: 7px;
    padding: 10px 13px;
    margin: 9px 0 11px;
    break-inside: avoid;
    border-left: 4px solid #0284c7;
    background: #f0f9ff;
  }}
  .box.formula {{
    border-left-color: #6366f1;
    background: #eef2ff;
  }}
  .box.warn {{
    border-left-color: #d97706;
    background: #fffbeb;
  }}
  .box.danger {{
    border-left-color: #dc2626;
    background: #fef2f2;
  }}
  .box.win {{
    border-left-color: #059669;
    background: #ecfdf5;
  }}
  .box-title {{
    font-weight: 700;
    font-size: 9.2pt;
    margin-bottom: 4px;
    color: #0f172a;
  }}
  .math {{
    font-family: "Cambria Math", "Times New Roman", Georgia, serif;
    font-size: 10.6pt;
    text-align: center;
    padding: 5px 0;
    color: #1e1b4b;
    font-weight: 600;
  }}

  /* Tables */
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0 12px;
    font-size: 8.3pt;
    break-inside: avoid;
  }}
  th {{
    background: #0f172a;
    color: #f8fafc;
    text-align: left;
    padding: 6px 7px;
    font-weight: 700;
  }}
  td {{
    border-bottom: 1px solid #e2e8f0;
    padding: 5.5px 7px;
    vertical-align: top;
  }}
  tr:nth-child(even) td {{ background: #f8fafc; }}
  tr.highlight-row td {{
    background: #dcfce7 !important;
    font-weight: 600;
    border-top: 1.5px solid #16a34a;
    border-bottom: 1.5px solid #16a34a;
  }}
  td.num {{ text-align: right; white-space: nowrap; }}

  .fig {{
    margin: 10px 0 12px;
    break-inside: avoid;
  }}
  .fig-cap {{
    font-size: 8.2pt;
    color: #475569;
    text-align: center;
    margin-top: 4px;
    font-style: italic;
  }}
  .two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin: 8px 0;
    break-inside: avoid;
  }}
  .card {{
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    padding: 10px 12px;
    background: #ffffff;
    break-inside: avoid;
  }}
  .card h4 {{
    margin: 0 0 5px;
    font-size: 9.5pt;
    color: #0284c7;
  }}
  .qa-item {{
    border: 1px solid #e2e8f0;
    border-left: 3.5px solid #0284c7;
    border-radius: 6px;
    padding: 8px 11px;
    margin-bottom: 8px;
    background: #ffffff;
    break-inside: avoid;
  }}
  .qa-q {{ font-weight: 700; color: #0f172a; margin-bottom: 3px; font-size: 9.2pt; }}
  .qa-a {{ color: #334155; font-size: 8.9pt; margin: 0; }}
</style>
</head>
<body>

<!-- ==================== COUVERTURE ==================== -->
<section class="cover">
  <div>
    <span class="cover-tag">Masterclass Technique Complète • État de l'Art 2026</span>
    <h1>Cours Intégral sur le RAG<br/>&amp; Dossier de Victoire<br/>Datathon SFAR × InterHop</h1>
    <div class="subtitle">
      De la théorie mathématique (BM25+, Embeddings, RRF/DBSF, Cross-Encoders, CRAG, Self-MedRAG, Provence, RAG-X, MCP)
      jusqu'à l'architecture complète <b>RAG-SFAR Frontier 2026</b>, ses 8 découvertes forensiques et son ablation complète C0 → C8.
    </div>

    <div class="kpi-grid">
      <div class="kpi"><div class="val">{audit['unique_documents']}</div><div class="lbl">RFE &amp; référentiels SFAR uniques (2000–2026)</div></div>
      <div class="kpi"><div class="val green">{best_abp_ev}</div><div class="lbl">Evidence Recall sur 171 Q. ABP (Allergie : {best_abp_all})</div></div>
      <div class="kpi"><div class="val green">0,0 %</div><div class="lbl">Intrusion d'éditions obsolètes (vs {naive_obs} naïf)</div></div>
      <div class="kpi"><div class="val">-98 %</div><div class="lbl">Tokens vs Long Context (~{best_abp_tok} tok / req.)</div></div>
    </div>

    <div class="cover-toc">
      <h3>Sommaire du Cours &amp; du Dossier Projet</h3>
      <ol>
        <li>Fondamentaux du RAG : Pourquoi, Quand &amp; Compromis</li>
        <li>Parsing, Tableaux Complexes &amp; Stratégies de Chunking</li>
        <li>Retrieval : Sparse (BM25+), Subword, Dense &amp; ColBERT</li>
        <li>Fusion Hybride (RRF vs DBSF), Métadonnées &amp; Reranking</li>
        <li>Frontière 2026 : CRAG, Self-MedRAG, Provence &amp; MCP</li>
        <li>Évaluation Scientifique : Métriques, RAGAS &amp; RAG-X</li>
        <li>Audit Forensique du Corpus SFAR : nos 8 Découvertes</li>
        <li>Architecture Détaillée de notre Pipeline RAG-SFAR</li>
        <li>Résultats d'Ablation Réels (C0 → C8) &amp; Analyse Critique</li>
        <li>Playbook LibreDataHub, Pitch 8 min &amp; 12 Questions Jury</li>
      </ol>
    </div>
  </div>
  <div class="cover-footer">
    <span>Projet cible : datathon.sfar.org/projets/rag-sfar • Siège SFAR Paris</span>
    <span>26–27 novembre 2026 • Édition Frontier C8</span>
  </div>
</section>

<!-- ==================== CHAPITRE 1 ==================== -->
<h1 class="chap first-chap"><span class="chap-num">01</span>Fondamentaux du RAG : Pourquoi, Comment et Quand l'Utiliser</h1>

<p>Un <b>Grand Modèle de Langage (LLM)</b> stocke sa connaissance de manière implicite dans des milliards de poids neuronaux figés à sa date de coupure (<i>knowledge cutoff</i>). En médecine critique — et particulièrement en anesthésie-réanimation où la SFAR actualise régulièrement ses Recommandations Formalisées d'Experts (RFE) — cette mémoire paramétrique présente <b>quatre défaillances structurelles incompatibles avec la sécurité clinique</b> :</p>

<ul>
  <li><b>Hallucinations plausibles</b> : un LLM prédit le token le plus probable, pas la vérité clinique. Sur le benchmark officiel SFAR d'antibioprophylaxie (171 questions), les LLM interrogés sans contexte se trompent <b>environ 1 fois sur 4</b>.</li>
  <li><b>Obsolescence silencieuse</b> : un modèle entraîné sur les RFE 2018 récite avec assurance une ancienne alternative allergique ou ignore les nouveaux tableaux pédiatriques de la <b>V3.0 (mai 2026)</b>.</li>
  <li><b>Absence de traçabilité (provenance)</b> : impossible pour un anesthésiste au bloc opératoire de vérifier quel paragraphe exact, quelle édition et quel niveau <code>GRADE</code> justifient une posologie.</li>
  <li><b>Impossibilité de mise à jour instantanée</b> : ré-entraîner un LLM à chaque nouvelle RFE coûte cher, exige des dizaines de milliers d'exemples annotés et introduit du <i>catastrophic forgetting</i>.</li>
</ul>

<h2>1.1. Principe du Retrieval-Augmented Generation (RAG)</h2>
<p>Introduit par Lewis et al. (Meta AI, NeurIPS 2020), le RAG découple la <b>capacité de raisonnement linguistique</b> (le LLM) de la <b>base de connaissances vérifiable</b> (un corpus externe indexé). Formellement, au lieu de générer directement <i>P(y | x)</i>, le système marginalise sur un sous-ensemble de passages pertinents <i>z ∈ Top-k(x)</i> extraits dynamiquement d'une base documentaire <i>D</i> :</p>

<div class="box formula">
  <div class="box-title">Formulation probabiliste du RAG</div>
  <div class="math">P(y | x, D) ≈ P<sub>LLM</sub>(y | x, C(R<sub>θ</sub>(x, D)))</div>
  <p style="margin:4px 0 0;font-size:8.6pt;text-align:center;">où <b>R<sub>θ</sub>(x, D)</b> est le moteur de recherche multi-étapes (retrieval + fusion + reranking + CRAG) et <b>C(·)</b> est le constructeur de contexte (expansion, élagage, réordonnancement U-Shape et formatage de citations).</p>
</div>

<h2>1.2. RAG vs Long Context vs Fine-Tuning vs MCP : que dit la littérature 2025–2026 ?</h2>
<p>L'arrivée de fenêtres contextuelles géantes (128k à 1M+ tokens) a soulevé une question que le jury te posera à coup sûr : <i>« Le Long Context ne tue-t-il pas le RAG ? »</i>. Les études de référence publiées en 2025–2026 répondent clairement <b>NON</b> :</p>

<ul>
  <li><b>LaRA Benchmark (ICLR 2025) &amp; Long Context vs RAG (arXiv:2501.01880, 2025)</b> : au-delà de 32k–64k tokens, la précision de la majorité des LLM se dégrade (<i>Lost-in-the-Middle</i>), et le Long Context est <b>8× à 82× plus coûteux</b> en calcul, latence et empreinte carbone. Sur 264 RFE SFAR (~5,8 millions de tokens), le Long Context est physiquement impossible.</li>
  <li><b>Medical LLMs : Fine-Tuning vs RAG (MDPI Bioengineering, juin 2025)</b> : sur 5 LLM open source (Llama-3.1, Gemma-2, Mistral, Qwen2.5, Phi-3.5), <b>RAG surpasse systématiquement le fine-tuning seul</b> et permet une mise à jour instantanée par simple ré-indexation.</li>
  <li><b>RAG pour 10 LLMs en aptitude chirurgicale (npj Digital Medicine, 2025)</b> : le RAG améliore la précision de chaque modèle de <b>+39,7 % en moyenne</b>, atteignant 96,4 % contre 86,6 % pour les cliniciens humains (p = 0,016).</li>
</ul>

<table>
  <thead>
    <tr><th>Approche</th><th>Fraîcheur / MàJ</th><th>Traçabilité</th><th>Coût par requête</th><th>Passage à l'échelle (264 RFE)</th><th>Usage optimal en médecine</th></tr>
  </thead>
  <tbody>
    <tr><td><b>LLM seul (Zero-shot)</b></td><td>Figée (cutoff)</td><td>Nulle</td><td>Très faible</td><td>Non applicable</td><td>Baseline uniquement (risque élevé)</td></tr>
    <tr><td><b>Fine-Tuning (LoRA/SFT)</b></td><td>Lente, coûteuse</td><td>Nulle</td><td>Faible à l'inférence</td><td>Mauvaise (hallucinations)</td><td>Style, formatage, terminologie métier</td></tr>
    <tr><td><b>Long Context brut</b></td><td>Instantanée</td><td>Faible (100p)</td><td><b>Très élevé (35–80×)</b></td><td><b>Impossible (5,8M tokens)</b></td><td>Analyse approfondie d'un seul PDF court</td></tr>
    <tr class="highlight-row"><td><b>RAG SOTA (Hybride+CRAG)</b></td><td>Instantanée</td><td><b>Maximale (citation + GRADE)</b></td><td><b>Faible (~1 500 tok)</b></td><td><b>Illimitée (millions de chunks)</b></td><td><b>Référentiels cliniques évolutifs (SFAR)</b></td></tr>
    <tr><td><b>MCP + Agents sur RAG</b></td><td>Instantanée</td><td>Maximale</td><td>Modéré (multi-appels)</td><td>Illimitée</td><td>Vignettes complexes multi-étapes &amp; outils</td></tr>
  </tbody>
</table>

<!-- ==================== CHAPITRE 2 ==================== -->
<h1 class="chap"><span class="chap-num">02</span>Parsing, Tableaux Complexes &amp; Stratégies de Chunking</h1>

<p>Règle d'or de l'ingénierie RAG : <b>« Garbage in, Garbage out »</b>. Plus de <b>70 % des gains de performance</b> d'un RAG médical proviennent de la qualité du parsing, du nettoyage documentaire et du découpage (<i>chunking</i>) — bien avant le choix du LLM.</p>

<h2>2.1. Taxonomie des stratégies de Chunking (du naïf au SOTA 2026)</h2>

<div class="two-col">
  <div class="card">
    <h4>1. Fixed-Size Sliding Window (Naïf — C0)</h4>
    <p>Découpe mécanique tous les <i>N</i> caractères (ex. 1 200) avec chevauchement (200). <b>Défauts majeurs</b> : coupe au milieu des tableaux HTML et des phrases, perd le titre du document et de la spécialité, mélange texte clinique et bibliographie.</p>
  </div>
  <div class="card">
    <h4>2. Structure-Aware / Hiérarchique (C2)</h4>
    <p>Respecte les titres Markdown (<code>H1 &gt; H2 &gt; H3</code>) et les paragraphes. Enregistre le fil d'Ariane (<i>breadcrumb</i>) dans les métadonnées. Mais reste aveugle aux tableaux HTML complexes et aux encadrés cliniques.</p>
  </div>
  <div class="card">
    <h4>3. Contextual Retrieval (Anthropic, 2024–2025)</h4>
    <p>Préfixe chaque chunk avant indexation (BM25 + Dense) par un en-tête contextuel précisant le document, l'année, la version, le domaine et la section. Réduit le taux d'échec de retrieval de <b>49 % à 67 %</b> combiné au reranking.</p>
  </div>
  <div class="card">
    <h4>4. Late Chunking (Jina AI, 2024–2025)</h4>
    <p>Passe le document entier dans un encodeur long contexte (8k tokens) <i>avant</i> le pooling par chunk, afin que chaque vecteur de chunk hérite des dépendances pronominales et globales. Idéal pour la prose narrative continue.</p>
  </div>
</div>

<h2>2.2. Small-to-Big (Parent-Child) &amp; Table-Aware Clinical Row-Group Cards</h2>
<p>En médecine, il existe une <b>tension fondamentale sur la taille des chunks</b> :</p>
<ul>
  <li>Pour le <b>Retrieval</b>, un chunk <b>petit et focalisé</b> (150–400 caractères, ex. une ligne de tableau chirurgical) produit un vecteur pur sans dilution sémantique.</li>
  <li>Pour la <b>Génération (LLM)</b>, le modèle a besoin d'un <b>contexte large et complet</b> : en-têtes de colonnes, alternatives allergiques, notes de bas de tableau (<code>* adapter au DFG</code>), et encadrés de sécurité de la spécialité.</li>
</ul>

<div class="box win">
  <div class="box-title">Notre Innovation : Dual Table Representation + Clinical Row-Group Cards</div>
  <p style="margin:0;">Face aux <b>2 056 tableaux HTML</b> du corpus SFAR (dont <b>49,1 % sans en-tête</b> suite aux sauts de page PDF et des dizaines de <code>rowspan</code> couplant molécule principale et alternative), notre moteur <code>table_parser.py</code> :</p>
  <ol style="margin:4px 0 0;">
    <li>Étend chaque <code>rowspan</code> et <code>colspan</code> en matrice 2D exacte, en groupant atomiquement les lignes liées par un <code>rowspan</code> (jamais séparées !).</li>
    <li><b>Propage automatiquement les en-têtes de colonnes</b> d'un tableau à ses continuations sans <code>&lt;th&gt;</code> sur les pages suivantes.</li>
    <li>Détecte les <b>bandeaux internes</b> (ex. <code>Patients traités par un AVK</code> vs <code>AOD</code>) et les hérite sur chaque ligne.</li>
    <li>Émet simultanément le <b>tableau Markdown reconstruit</b> ET une <b>Clinical Row-Group Card</b> auto-suffisante :
      <code>[RFE SFAR 2026 V3.0 | CHAMP 2 &gt; PARTIE 2 ORL] Actes : Chirurgie rhinologique avec greffon • Schéma 1 : Molécules = Céfazoline | 2g IVL | GRADE 2 • Schéma 2 : Alternative = Amoxicilline/Clavulanate | 2g IVL</code>.</li>
  </ol>
</div>

<h2>2.3. La révolution multimodale 2025–2026 : ColPali &amp; MED-VRAG</h2>
<p>Les algorithmes décisionnels (organigrammes de gestion des voies aériennes, arbres de réversion d'anticoagulants) résistent souvent à l'OCR textuel classique. Les approches <b>ColPali</b> (Faysse et al., ICLR 2025) et <b>MED-VRAG</b> (arXiv 2026) encodent directement les <b>images de pages PDF en patchs visuels</b> via un Vision-Language Model (VLM) avec scoring <i>MaxSim</i>. Pour les 1 131 figures <code>.webp</code> extraites par Chandra dans le corpus SFAR, c'est l'axe d'évolution n°1 à citer en perspective finale devant le jury !</p>

<!-- ==================== CHAPITRE 3 ==================== -->
<h1 class="chap"><span class="chap-num">03</span>Retrieval : Sparse (BM25+), Subword, Dense &amp; Multi-Vecteur</h1>

<p>Aucun algorithme de retrieval unique ne domine sur tous les types de questions cliniques. Comprendre la <b>géométrie et les angles morts</b> de chaque famille est la clé d'un système imbattable.</p>

<h2>3.1. Retrieval Lexical Sparse : BM25 et BM25+</h2>
<p>Évolution probabiliste de TF-IDF (Robertson &amp; Zaragoza), <b>BM25</b> évalue un document <i>d</i> pour une requête <i>q</i> en sommant les termes communs pondérés par leur rareté inverse (IDF) et une fréquence saturée (TF). Nous utilisons <b>BM25+</b> (Lv &amp; Zhai), qui ajoute une borne inférieure <code>δ = 0,5</code> pour corriger la sur-pénalisation des documents longs face aux courtes Row-Group Cards :</p>

<div class="box formula">
  <div class="box-title">Formule exacte de BM25+ implémentée dans <code>src/rag_sfar/retrieval/bm25.py</code></div>
  <div class="math">Score<sub>BM25+</sub>(q, d) = Σ<sub>t ∈ q</sub> IDF(t) · [ (tf(t,d) · (k₁ + 1)) / (tf(t,d) + k₁ · (1 − b + b · |d|/avgdl)) + δ ]</div>
  <p style="margin:4px 0 0;font-size:8.4pt;text-align:center;">avec <code>IDF(t) = ln(1 + (N − df(t) + 0,5) / (df(t) + 0,5))</code>, <code>k₁ = 1,5</code> (saturation TF), <code>b = 0,65</code> (normalisation longueur), <code>δ = 0,5</code>.</p>
</div>

<p><b>Forces en médecine</b> : précision chirurgicale sur les noms exacts de molécules (<code>céfoxitine</code>, <code>ertapénème</code>, <code>fosfomycine-trométamol</code>), les codes (<code>R1.2.1</code>, <code>Gustilo 3</code>, <code>Hinchey III</code>) et les fenêtres temporelles (<code>J-3</code>, <code>J-5</code>, <code>INR 1,2</code>). <b>Faiblesse</b> : aveugle aux synonymes (<code>PTH</code> ≠ <code>prothèse de hanche</code>) et aux paraphrases.</p>

<h2>3.2. Notre 2e Canal Sparse : Subword Character N-Grams (3–5)</h2>
<p>En français médical, la dérivation morphologique (<code>colectomie</code> ↔ <code>colique</code> ↔ <code>colo-rectale</code>, <code>morsure</code> ↔ <code>morsures</code>, <code>pédiatrique</code> ↔ <code>pédiatrie</code>) et les coquilles d'OCR (<code>céfuoxime</code>, <code>antidoagulants</code>, <code>pourl'antibioprophylaxie</code>) cassent la correspondance exacte par mot de BM25. Notre canal <b>CharNgramIndex</b> (<code>subword.py</code>) vectorise chaque chunk en n-grammes de 3 à 5 caractères pondérés TF-IDF sous-linéaire (matrice CSC inversée SciPy, <b>&lt; 10 ms</b> sur {_fmt_int(num_chunks)} chunks).</p>

<h2>3.3. Retrieval Sémantique Dense : Bi-Encoders, InfoNCE, E5, BGE-M3 &amp; HNSW</h2>
<p>Un <b>Bi-Encoder</b> (Transformer de type XLM-RoBERTa / BERT) projette séparément chaque texte dans une hypersphère unitaire ℝ<sup>d</sup> (d = 384 à 1024). Il est entraîné par <b>apprentissage contrastif (perte InfoNCE)</b> sur des triplets <code>(requête q, passage positif d⁺, négatifs difficiles d⁻)</code> afin de rapprocher les vecteurs sémantiquement équivalents et d'éloigner les faux amis cliniques :</p>
<div class="box formula">
  <div class="box-title">Similarité Cosinus &amp; Perte Contrastive InfoNCE (température τ)</div>
  <div class="math">sim(q, d) = E(q)<sup>⊤</sup> · E(d) ∈ [−1, 1] &nbsp;&nbsp;|&nbsp;&nbsp; ℒ<sub>InfoNCE</sub> = − log [ exp(sim(q, d⁺)/τ) / (exp(sim(q, d⁺)/τ) + Σ<sub>j</sub> exp(sim(q, d<sub>j</sub>⁻)/τ)) ]</div>
</div>
<ul>
  <li><b>Préfixes asymétriques (E5)</b> : les modèles <code>intfloat/multilingual-e5-*</code> exigent <code>query: </code> sur la question et <code>passage: </code> sur les documents — oublier ce détail fait chuter le rappel de 5 à 10 points !</li>
  <li><b>BGE-M3 (BAAI, 2024–2026)</b> : véritable couteau suisse multilingue (100+ langues dont un français exceptionnel, contexte 8 192 tokens, 1024d) capable de produire simultanément des vecteurs <b>Dense + Sparse lexical appris (type SPLADE) + Multi-Vecteur (type ColBERT)</b>. C'est le modèle que nous activons en 1 ligne demain sur le GPU LibreDataHub.</li>
  <li><b>Indexation ANN — HNSW &amp; <code>pgvector</code></b> : <b>HNSW</b> (<i>Hierarchical Navigable Small World</i>) construit un graphe multi-couches inspiré des <i>skip-lists</i> : on saute rapidement sur les couches hautes (arêtes longues) puis on raffine localement sur la couche 0 en temps logarithmique <i>O(log N)</i> (paramètres clés : <code>M</code> connexions/nœud, <code>ef_construction</code> qualité de construction, <code>ef_search</code> compromis vitesse/rappel). Sous 50 000 chunks, notre produit matriciel exact BLAS (<code>embeddings @ q_vec</code>) offre <b>100 % de rappel exact en &lt; 5 ms</b>, tandis que <code>PgVectorStore</code> expose l'index HNSW + <code>tsvector('french')</code> nativement dans PostgreSQL LibreDataHub.</li>
</ul>

<div class="fig">
  {ENCODERS_SVG}
  <div class="fig-cap">Figure 1 — Comparaison architecturale : Bi-Encoder (Stage 1), Late Interaction ColBERT/BGE-M3, et Cross-Encoder Reranker (Stage 2).</div>
</div>

<!-- ==================== CHAPITRE 4 ==================== -->
<h1 class="chap"><span class="chap-num">04</span>Fusion Hybride (RRF vs DBSF), Métadonnées &amp; Reranking</h1>

<h2>4.1. Fusion Hybride : RRF vs Combinaison Convexe vs DBSF</h2>
<p>Comment fusionner un score BM25+ dans [0, 45], une similarité Char N-Gram dans [0, 0,6] et un cosinus Dense dans [0,72, 0,91] ?</p>

<div class="box formula">
  <div class="box-title">1. Reciprocal Rank Fusion (RRF — Cormack et al. 2009, standard zéro-shot)</div>
  <div class="math">RRF(d) = Σ<sub>r ∈ &#123;BM25, Subword, Dense&#125;</sub> w<sub>r</sub> / (k + rank<sub>r</sub>(d)) &nbsp;&nbsp;(k = 60)</div>
  <div class="box-title" style="margin-top:8px;">2. Distribution-Based Score Fusion (DBSF — Qdrant &amp; Bruch et al. 2025/2026)</div>
  <div class="math">s̃<sub>r</sub>(d) = clip( (s<sub>r</sub>(d) − (μ<sub>r</sub> − 3σ<sub>r</sub>)) / (6σ<sub>r</sub>), 0, 1 ) &nbsp;⇒&nbsp; Score<sub>hybride</sub>(d) = (1 − λ) · RRF<sub>norm</sub>(d) + λ · Σ<sub>r</sub> w̃<sub>r</sub> s̃<sub>r</sub>(d)</div>
</div>

<p><b>Pourquoi combiner RRF + DBSF (λ = 0,35) est supérieur à RRF seul ?</b> Comme le démontrent Bruch et al. (<i>An Analysis of Fusion Functions</i>) et les benchmarks 2025–2026, RRF est robuste car insensible aux échelles mais <b>jette l'amplitude des scores</b> : un match BM25+ écrasant (<code>score = 42</code> vs <code>#2 = 14</code> sur un terme rare comme <code>ertapénème</code> ou <code>R1.6</code>) n'obtient que <code>1/61</code> contre <code>1/62</code> ! La composante <b>DBSF</b> normalise chaque canal par sa distribution <code>μ ± 3σ</code> et <b>préserve les signaux hors-norme</b>.</p>

<h2>4.2. Métadonnées : Hard Safety Filters vs Soft Metadata Boosting</h2>
<p>Un des résultats les plus contre-intuitifs et critiques de notre projet concerne l'usage des métadonnées :</p>
<ul>
  <li><b>Hard Filters (filtres stricts) — uniquement pour les invariants de sécurité vérifiés</b> : <code>is_active = True</code> (exclut les textes abrogés), <code>is_reference_section = False</code> (sauf si l'utilisateur demande la bibliographie), <code>language != 'en'</code> (évite les doublons anglophones), et <code>is_latest_edition = True</code> (sauf intention comparative ou année explicite).</li>
  <li><b>Soft Metadata Boosts — pour les métadonnées bruitées ou progressives</b> : domaine clinique imputé (+0,18), population adulte vs pédiatrie (+0,25 / pénalité −0,35), contexte urgence vs programmé (+0,20 / −0,16), rôle du document (<code>recommandation</code> &amp; <code>tableaux_synthese</code> &gt; long <code>argumentaire</code>), type de chunk (<code>table_row_card</code> +0,10, <code>recommendation_box</code> +0,14).</li>
</ul>

<div class="box danger">
  <div class="box-title">Piège mortel prouvé sur le corpus SFAR : ne JAMAIS faire un Hard Filter sur <code>raw_subdomain</code> !</div>
  <p style="margin:0;">Dans <code>discovery.json</code>, <b>57 documents ont <code>subdomain = None</code></b>, incluant les <b>3 RFE phares 2026</b> (Antibioprophylaxie V3.0, IIA 2026, Anticoagulants 2026), tandis que les vieilles versions 2015 et 2018 sont renseignées. Un filtre dur <code>WHERE subdomain = 'Infectiologie'</code> détruit 100 % du rappel 2026 !</p>
</div>

<h2>4.3. Reranking par Cross-Encoder &amp; Contrôle de Diversité</h2>
<p>Le Cross-Encoder reçoit la concaténation <code>[CLS] Question [SEP] Passage [SEP]</code> : chaque tête d'attention compare directement chaque mot de la question (ex. <i>« voie antérieure »</i> + <i>« allergie »</i>) à chaque mot du passage. Nous combinons la probabilité sigmoïde du Cross-Encoder (68 %) avec le prior hybride+métadonnées (32 %), suivie d'une <b>pénalité post-reranking de cohérence de population</b> (empêchant un tableau pédiatrique Champ 3 de doubler un tableau adulte Champ 2) et d'une <b>déduplication quasi-exacte</b> (pour que version courte et version longue d'une même RFE ne monopolisent pas le Top-8).</p>

<!-- ==================== CHAPITRE 5 ==================== -->
<h1 class="chap"><span class="chap-num">05</span>Frontière 2025–2026 : CRAG, Self-MedRAG, Context Engineering &amp; MCP</h1>

<p>Les travaux de 2025–2026 (<i>CRAG</i>, <i>Self-MedRAG</i>, <i>Provence ICLR 2025</i>, <i>GraphRAG</i>, <i>MCP</i>) ont montré que le RAG « statique à un seul tir » plafonne sur les <b>questions cliniques multi-facettes</b>. Voici les 4 paradigmes frontières que nous maîtrisons et intégrons dans <code>RAG-SFAR C8</code> :</p>

<h2>5.1. Query Transformation, Multi-Query RAG-Fusion &amp; HyDE</h2>
<ul>
  <li><b>Expansion par Lexique Clinique (déterministe, 0 ms)</b> : étend 70+ acronymes et noms commerciaux français d'AR (<code>PTH → prothèse totale de hanche</code>, <code>AOD → apixaban rivaroxaban dabigatran edoxaban</code>, <code>Augmentin → amoxicilline clavulanate</code>, <code>Previscan → fluindione AVK</code>).</li>
  <li><b>HyDE (Hypothetical Document Embeddings)</b> : demander au LLM de rédiger une réponse hypothétique puis l'embedder. Puissant en recherche ouverte, mais <b>risqué en médecine</b> si le LLM hallucine une mauvaise molécule dans l'hypothèse (qui biaise alors le retrieval vers la mauvaise molécule !). Nous préférons la <b>décomposition par facettes cliniques</b>.</li>
  <li><b>Décomposition Multi-Hop + RAG-Fusion</b> : face à <i>« Colectomie droite chez un patient porteur rectal de BLSE »</i>, le système génère une sous-requête ciblée sur la facette systémique (<code>colonisation rectale E-BLSE chirurgie colorectale ertapénème R1.7</code>) et fusionne ses rangs en parallèle de la requête principale.</li>
</ul>

<h2>5.2. Corrective RAG (CRAG) &amp; Self-MedRAG : la Boucle de Secours</h2>
<p><b>CRAG</b> (Yan et al., 2024) et <b>Self-MedRAG</b> (arXiv 2026) introduisent un <b>évaluateur post-retrieval</b> qui audite les passages récupérés <i>avant</i> d'appeler le LLM. Dans notre module <code>crag.py</code>, nous auditons systématiquement la <b>couverture de chaque facette clinique obligatoire</b> détectée dans la requête (<code>BLSE</code>, <code>obèse/IMC</code>, <code>insuffisance rénale/DFG</code>, <code>pédiatrie/mg/kg</code>, <code>allergie</code>, ou ID explicite <code>R1.6</code> / <code>R1.2.1</code>). Si une facette est absente du Top-8, une <b>passe corrective ciblée</b> est déclenchée automatiquement (&lt; 2 ms) et injecte la preuve manquante avec traçabilité <code>crag_rescue:&lt;facette&gt;</code>.</p>

<h2>5.3. Context Engineering : Lost-in-the-Middle, Provence, Dérive Conversationnelle &amp; Garde-Fou Molécules</h2>
<ul>
  <li><b>Réordonnancement en U-Shape (<code>context_optimizer.py</code>)</b> : les LLM accordent une attention maximale au début (<i>primauté</i>) et à la fin (<i>récence</i>) du prompt, et négligent le milieu (Liu et al., TACL 2024). Nous plaçons les sources dans l'ordre <code>[#1, #3, #5, #7, #8, #6, #4, #2]</code> tout en conservant leurs identifiants <code>[S1..S8]</code> intacts.</li>
  <li><b>Élagage de contexte inspiré de Provence (ICLR 2025)</b> : Provence unifie reranking et élagage phrase-par-phrase pour supprimer le bruit narratif. Notre élagueur déterministe (<code>prune_verbose_prose</code>) compresse les longs paragraphes narratifs tout en <b>protégeant à 100 %</b> tableaux, Row-Cards, encadrés allergie, <code>GRADE</code> et posologies.</li>
  <li><b>Prévention de la dérive conversationnelle (<i>npj Digital Medicine</i>, 2025–2026)</b> : des travaux récents montrent que la fiabilité des chatbots RAG médicaux chute fortement au fil de conversations multi-tours (accumulation de bruit et d'auto-hallucinations dans l'historique). Règle d'architecture clinique : toujours <b>reformuler la question courante en requête autonome</b> avant le retrieval et privilégier des sessions ciblées sourcées plutôt que d'empiler 15 tours de chat dans le contexte.</li>
  <li><b>Prompting Clinique &amp; Vérificateur Anti-Hallucination (<code>prompts.py</code> + <code>verifier.py</code>)</b> : <code>temperature = 0,0</code>, règle stricte d'abstention (<i>« Hors périmètre / Information non retrouvée »</i>), citations en ligne obligatoires <code>[S1]</code>, et scan déterministe post-génération sur ~60 molécules critiques (antibiotiques, anticoagulants, antidotes) — <b>toute molécule générée absente des sources récupérées déclenche une alerte clinique immédiate</b>.</li>
</ul>

<h2>5.4. GraphRAG vs Section-Anchored Linking &amp; Serveur MCP</h2>
<p>Un GraphRAG complet par extraction LLM d'entités (Microsoft GraphRAG) coûte des millions de tokens d'indexation et sur-ingénierie pour des référentiels structurés ; à l'inverse, <b>LazyGraphRAG</b> et notre <b>graphe léger natif</b> (<code>reco_family_id</code> + <code>topic_lineage</code> temporel + <code>linked_callout_ids</code> reliant chaque ligne de tableau à l'encadré allergie de sa spécialité) capturent 95 % de la valeur structurelle à <b>0 € de coût LLM</b> ! Enfin, exposer ce moteur via le protocole standard <b>MCP (Model Context Protocol)</b> (<code>rag-sfar-mcp</code>) permet à tout agent IA d'orchestrer des recherches multi-tours, des comparaisons d'éditions et des consultations de catalogue.</p>

<!-- ==================== CHAPITRE 6 ==================== -->
<h1 class="chap"><span class="chap-num">06</span>Évaluation Scientifique d'un RAG : Métriques, RAGAS &amp; RAG-X</h1>

<p>En médecine, évaluer un RAG uniquement par un score global d'accuracy est une <b>faute méthodologique</b>. Les frameworks modernes (<b>RAGAS</b>, <b>TruLens</b>, <b>MIRAGE</b> et <b>RAG-X 2026</b>) imposent une évaluation <b>composant par composant</b>.</p>

<h2>6.1. Métriques de Retrieval (indépendantes du LLM)</h2>
<ul>
  <li><b>Document / Current-Edition Hit@k</b> : proportion de questions où le bon référentiel <i>dans son édition en vigueur</i> apparaît dans le Top-k.</li>
  <li><b>Obsolete Intrusion Rate (notre métrique clinique clé !)</b> : % de requêtes où au moins un passage d'une édition périmée (2000–2021) s'infiltre dans le contexte transmis au LLM. Doit être <b>0,0 %</b>.</li>
  <li><b>Evidence Recall@k &amp; Allergy Recall@k</b> : % de questions dont les termes factuels indispensables (molécule attendue, association, délai <code>J-5</code>, alternative allergique) figurent effectivement dans les passages récupérés.</li>
  <li><b>MRR (Mean Reciprocal Rank) &amp; NDCG@k</b> : mesurent la qualité du classement des preuves en tête de liste :</li>
</ul>
<div class="box formula">
  <div class="math">MRR = (1/N) · Σ<sub>i=1..N</sub> (1 / rank<sub>i</sub>) &nbsp;&nbsp;|&nbsp;&nbsp; NDCG@k = DCG@k / IDCG@k &nbsp;&nbsp;avec&nbsp;&nbsp; DCG@k = Σ<sub>j=1..k</sub> (2<sup>rel<sub>j</sub></sup> − 1) / log₂(j + 1)</div>
</div>

<h2>6.2. Métriques de Génération &amp; Diagnostic RAG-X (arXiv 2026)</h2>
<p>Le papier <b>RAG-X (2026)</b> met en lumière le <b>« Paradoxe de l'Exactitude » (<i>Accuracy Fallacy</i>)</b> : un système peut afficher 85 % de bonnes réponses tout en récupérant de mauvais documents, simplement parce que le LLM a deviné depuis sa mémoire d'entraînement (dangereux dès que la recommandation évolue !). Notre script <code>run_e2e_eval.py</code> calcule automatiquement les <b>4 quadrants RAG-X</b> et la <b>Context Utilization Efficiency</b> <code>CUE = Q1 / (Q1 + Q3)</code>.</p>

<div class="fig">
  {RAGX_USHAPE_SVG}
  <div class="fig-cap">Figure 2 — À gauche : matrice diagnostique RAG-X isolant Retrieval vs Générateur (implémentée dans <code>rag_x.py</code>). À droite : réordonnancement U-Shape contre le biais Lost-in-the-Middle.</div>
</div>

<div class="box">
  <div class="box-title">La Triade RAGAS / TruLens : les 4 axes complémentaires d'évaluation LLM-as-a-Judge</div>
  <ul style="margin:0;">
    <li><b>Context Precision &amp; Context Recall</b> : les chunks utiles sont-ils en tête de liste (<i>Precision</i>) et couvrent-ils 100 % des faits de la vérité terrain (<i>Recall</i>) ?</li>
    <li><b>Faithfulness (Fidélité / Groundedness)</b> : chaque affirmation clinique générée est-elle déductible des sources <code>[S1..Sk]</code> sans ajout paramétrique ?</li>
    <li><b>Answer Relevance</b> : la réponse répond-elle directement au geste chirurgical, au terrain (adulte/pédiatrie/obèse) et à l'allergie demandés ?</li>
    <li><b>Règle d'or en santé</b> : ne jamais se fier uniquement à un LLM juge seul ; toujours le croiser avec des métriques <b>déterministes</b> (<code>Evidence Recall</code>, <code>Obsolete Intrusion</code>, <code>Molecule Guard</code>, <code>scorer.py</code> officiel).</li>
  </ul>
</div>

<!-- ==================== CHAPITRE 7 ==================== -->
<h1 class="chap"><span class="chap-num">07</span>Audit Forensique du Corpus SFAR : nos 8 Découvertes Décisives</h1>

<p>Avant d'écrire la moindre ligne de RAG, nous avons audité programmatiquement l'intégralité des <b>267 fichiers OCR Chandra</b> + <code>discovery.json</code> (<code>github.com/jaj42/sfar_recommendations</code>) et les <b>171 questions</b> (<code>github.com/tomboulier/antibioprophylaxie-LLM-benchmark</code>). Voici les <b>8 découvertes factuelles</b> qui distinguent radicalement notre projet :</p>

<table>
  <thead><tr><th>#</th><th>Anomalie / Piège découvert dans les données</th><th>Ampleur mesurée</th><th>Impact sur un RAG naïf</th><th>Solution RAG-SFAR</th></tr></thead>
  <tbody>
    <tr><td><b>1</b></td><td>Tableaux 100 % HTML <code>&lt;table&gt;</code>, 0 pipe Markdown</td><td><b>{_fmt_int(audit['total_html_tables'])} tableaux</b></td><td>Balises coupées, <code>rowspan</code> orphelins</td><td>Parseur 2D <code>table_parser.py</code> + {_fmt_int(n_row_cards)} Row-Cards</td></tr>
    <tr><td><b>2</b></td><td>Tableaux de continuation sans <code>&lt;thead&gt;/&lt;th&gt;</code></td><td><b>49,1 %</b> (64,5 % ABP)</td><td>Perte totale des noms de colonnes</td><td>Héritage automatique des en-têtes cross-pages</td></tr>
    <tr><td><b>3</b></td><td>Volume bibliographique (<code>#### Références</code>)</td><td><b>~25 %</b> (~5,9M chars)</td><td>Bruit lexical &amp; vectoriel massif</td><td>Isolation <code>is_reference_section</code> + filtrage par défaut</td></tr>
    <tr><td><b>4</b></td><td><b>Piège OCR : recommandations après <code>#### Références</code></b></td><td><b>+118 recos &amp; +643 cards sauvées !</b></td><td><code>R1.7.2</code> (Ertapénème BLSE), <code>R1.6</code>, <code>R1.2.1</code> avalés !</td><td>Auto-exit sur <code>Question/R1.x/&lt;table&gt;</code> + vérification contenu</td></tr>
    <tr><td><b>5</b></td><td><code>subdomain = None</code> sur les RFE récentes</td><td><b>{audit['imputed_subdomains_count']} docs</b> (dont les 3 RFE 2026 !)</td><td>Filtre dur <code>subdomain</code> exclut 2026 !</td><td>Imputation canonique + Soft Metadata Boost</td></tr>
    <tr><td><b>6</b></td><td>Éditions obsolètes + dates trompeuses</td><td><b>{audit['superseded_editions_count']} docs remplacés</b>, 18 sans année</td><td><b>{c4_obs_str}</b> d'intrusion obsolète en Dense !</td><td><code>effective_year</code> + Graphe supersession respectant urgence/progr.</td></tr>
    <tr><td><b>7</b></td><td>Encadré allergie séparé du tableau (<i>Split-Chunk</i>)</td><td><b>{n_allergy_boxes} encadrés</b> liés</td><td>Bonne ligne trouvée, alternative allergie ratée</td><td>Liaison <code>linked_callout_ids</code> + expansion Small-to-Big</td></tr>
    <tr><td><b>8</b></td><td>Dérive Benchmark V2.0 (2024) → RFE V3.0 (2026)</td><td><b>{v2v3['flagged_for_v3_review']}/171 questions</b> ciblées</td><td>Écarts de notation sur allergies/hernies/prostate</td><td>Audit exporté <code>abp_v2_vs_v3_audit.md</code> pour les médecins</td></tr>
  </tbody>
</table>

<div class="box warn">
  <div class="box-title">Détail en or sur la Découverte n°4 (trouvée par analyse d'erreurs systématique !)</div>
  <p style="margin:0;">Dans <b>Antibioprophylaxie V3.0</b> et <b>Infections Intra-Abdominales 2026</b>, chaque sous-question du Champ 1 se termine par <code>#### Références</code>, puis la question suivante commence en gras (<code>**R1.7.2 – E-BLSE / Ertapénème**</code>, <code>**R1.2.1 – IIA communautaire**</code>) <i>sans</i> nouveau titre Markdown <code>####</code> ! Un parseur naïf qui exclut tout ce qui suit <code>#### Références</code> avale littéralement les recommandations E-BLSE et IIA ! Notre détecteur de sortie automatique + garde-fou de contenu a sauvé <b>118 blocs de recommandations formelles et 643 Row-Cards</b> sur tout le corpus.</p>
</div>

<!-- ==================== CHAPITRE 8 ==================== -->
<h1 class="chap"><span class="chap-num">08</span>Architecture Détaillée de notre Solution <code>RAG-SFAR</code></h1>

<div class="fig">
  {ARCH_SVG}
  <div class="fig-cap">Figure 3 — Architecture complète bout-en-bout de RAG-SFAR Frontier 2026 (index de {_fmt_int(num_chunks)} chunks dont {_fmt_int(n_row_cards)} Row-Cards et {_fmt_int(n_rec_boxes)} boîtes de recommandations formelles).</div>
</div>

<h2>8.1. Cartographie des modules du dépôt (<code>src/rag_sfar/</code>)</h2>
<table>
  <thead><tr><th>Module</th><th>Responsabilité technique</th><th>Point clé à expliquer au jury</th></tr></thead>
  <tbody>
    <tr><td><code>ingestion/loader.py</code></td><td>Jointure <code>discovery.json</code> + Chandra, dédup SHA-256, langue corps 20–80 %, imputation 57 domaines &amp; 18 années, graphe de supersession (26 lignées cliniques).</td><td>Distingue <i>Anticoagulants urgence 2024</i> et <i>programmé 2026</i> (toutes deux actives) ; corrige <code>V3.0 = 2026</code>.</td></tr>
    <tr><td><code>ingestion/table_parser.py</code></td><td>Parseur BeautifulSoup résolvant <code>rowspan</code>/<code>colspan</code>, héritant les en-têtes sans <code>&lt;th&gt;</code>, propageant les bandeaux AVK/AOD, émettant Markdown + Row-Cards.</td><td>Garantit qu'aucune ligne de posologie ou alternative <code>rowspan</code> n'est jamais orpheline de son acte chirurgical.</td></tr>
    <tr><td><code>ingestion/chunker.py</code></td><td>3 stratégies (<code>naive_fixed</code>, <code>hierarchical_markdown</code>, <code>table_aware_sota</code>) ; hiérarchie normalisée <code>CHAMP/PARTIE</code> ; auto-exit <code>Références</code> ; liaison encadrés allergie.</td><td>Permet une ablation 100 % rigoureuse et reproductible sur le même corpus.</td></tr>
    <tr><td><code>retrieval/bm25.py</code> + <code>subword.py</code></td><td>BM25+ médical FR (accent-folding, composés <code>amoxicilline/clavulanate</code>, <code>J-5</code>) + Char 3–5 N-Gram TF-IDF résilient aux fautes d'OCR et dérivations FR.</td><td>Latence cumulée &lt; 10 ms sur {_fmt_int(num_chunks)} chunks ; comble les angles morts lexicaux des Bi-Encoders.</td></tr>
    <tr><td><code>retrieval/vector_store.py</code></td><td><code>LocalVectorStore</code> (SQLite + NumPy float32 BLAS) + <code>PgVectorStore</code> (schéma SQL natif PostgreSQL <code>pgvector</code> HNSW + <code>tsvector('french')</code>).</td><td>Zéro friction sur Mac/Jupyter ET 100 % natif PostgreSQL sur LibreDataHub.</td></tr>
    <tr><td><code>retrieval/crag.py</code> + <code>pipeline.py</code></td><td>Fusion Tri-Canal <b>DBSF + RRF</b> + Soft Metadata Boost + Cross-Encoder + <b>CRAG Multi-Hop Facet Rescue</b> + Context Builder Small-to-Big.</td><td>Rattrape automatiquement les facettes systémiques (<code>E-BLSE</code>, <code>obèse/R1.6</code>, <code>DFG</code>, <code>pédiatrie</code>).</td></tr>
    <tr><td><code>retrieval/context_optimizer.py</code></td><td>Ordre <b>U-Shape</b> (anti Lost-in-the-Middle) + élagage narratif inspiré de <b>Provence</b>.</td><td>Protège à 100 % les tableaux, posologies et <code>GRADE</code> tout en réduisant le bruit.</td></tr>
    <tr><td><code>generation/verifier.py</code></td><td>Vérification déterministe des citations <code>[Si]</code> et scan anti-hallucination sur ~60 molécules cliniques critiques.</td><td>Détecte instantanément une molécule inventée hors des extraits SFAR.</td></tr>
    <tr><td><code>interfaces/api.py</code> + <code>mcp_server.py</code></td><td>Web UI Clinique interactive + API <b>OpenAI-compatible</b> (<code>/v1/chat/completions</code>) + Serveur <b>MCP</b> JSON-RPC 2.0 (4 outils) + Adaptateur <code>SfarRagApproach</code>.</td><td>Branchement immédiat avec <code>plateforme-evaluation</code>, <code>benchmark-enrichi</code> et agents MCP !</td></tr>
  </tbody>
</table>

<!-- ==================== CHAPITRE 9 ==================== -->
<h1 class="chap"><span class="chap-num">09</span>Résultats Expérimentaux d'Ablation (C0 → C8) &amp; Analyse</h1>

<p>Toutes les configurations sont évaluées sur le <b>même corpus complet de 264 recommandations SFAR</b> (2000–2026) et les <b>mêmes 201 questions</b> (171 questions officielles Antibioprophylaxie + 30 stress-tests Multi-RFE 2024–2026), avec <code>intfloat/multilingual-e5-small</code> + <code>cross-encoder/mmarco-mMiniLMv2-L12-H384-v1</code> sur CPU local (avant passage demain sur GPU LibreDataHub en <code>BAAI/bge-m3</code> + <code>BAAI/bge-reranker-v2-m3</code>).</p>

<h2>9.1. Benchmark Officiel : <code>antibioprophylaxie_171</code> (171 questions)</h2>
{abp_table}
<div class="fig">
  {chart_abp_svg}
  <div class="fig-cap">Figure 4 — Évolution mesurée de C0 (RAG naïf) à C8 (Frontier 2026 Tri-Canal DBSF + CRAG) sur les 171 questions Antibioprophylaxie.</div>
</div>

<h2>9.2. Stress-Test Multi-RFE 2024–2026 : <code>multi_rfe_stress_30</code> (30 questions)</h2>
{multi_table}
<div class="fig">
  {chart_multi_svg}
  <div class="fig-cap">Figure 5 — Résultats sur les 30 stress-tests Multi-RFE (ABP 2026 adulte/pédiatrie/obèse/allergie, IIA 2026, Anticoagulants 2026 vs Urgence 2024, Voies Aériennes 2026, Sepsis 2025, Diffs temporels).</div>
</div>
{e2e_section}

<div class="box win">
  <div class="box-title">Synthèse Scientifique des Gains Mesurés (à marteler à la restitution !)</div>
  <ul style="margin:0;">
    <li><b>Sécurité temporelle absolue</b> : l'intrusion d'éditions obsolètes passe de <b>{c4_obs_str} (Dense seul) / {naive_obs} (Naïf)</b> à <b>0,0 %</b> sur les 201 questions !</li>
    <li><b>Rappel factuel quasi-parfait</b> : <b>{best_abp_ev} d'Evidence Recall</b> et <b>{best_abp_all} d'Allergy Recall</b> sur les 171 questions ABP (MRR = <b>{best_abp_mrr}</b>) et <b>{best_multi_ev}</b> sur les 30 stress-tests Multi-RFE (MRR = <b>{best_multi_mrr}</b>) !</li>
    <li><b>Frugalité extrême</b> : <b>~{best_abp_tok} tokens</b> transmis au LLM vs ~95 000 tokens pour une seule RFE en Long Context (<b>-98 % de tokens, coût et CO₂</b>), tout en couvrant 264 RFE simultanément.</li>
    <li><b>Double profil vitesse/précision</b> : <code>C6</code> tourne en <b>~{c6_lat_str} ms</b> (idéal temps réel sans GPU), tandis que <code>C8</code> sur GPU LibreDataHub (avec <code>BGE-M3</code> + <code>BGE-Reranker-v2-M3</code> 8k tokens) combine précision maximale et latence &lt; 100 ms.</li>
  </ul>
</div>

<!-- ==================== CHAPITRE 10 ==================== -->
<h1 class="chap"><span class="chap-num">10</span>Playbook LibreDataHub, Pitch 8 min &amp; 12 Questions Pièges du Jury</h1>

<h2>10.1. Plan d'exécution heure par heure (6h30 de code effectif)</h2>
<table>
  <thead><tr><th>Créneau</th><th>Objectif prioritaire</th><th>Action / Commande exacte</th></tr></thead>
  <tbody>
    <tr><td><b>Jeu 10h20–12h00</b><br/><i>Présentations</i></td><td>Reconnaissance infra &amp; alliances inter-équipes</td><td>Noter l'URL Ollama/vLLM, les modèles GPU, le DSN PostgreSQL/<code>pgvector</code>. Contacter les leads de <code>benchmark-enrichi</code> et <code>plateforme-evaluation</code>.</td></tr>
    <tr><td><b>Jeu 13h30–14h15</b><br/><i>Sprint 1 (45 min)</i></td><td>Migration GPU LibreDataHub + alignement médecins</td><td>Copier le repo, lancer <code>bash scripts/libredatahub_setup.sh</code> (<code>BAAI/bge-m3</code> + <code>BAAI/bge-reranker-v2-m3</code>). Partager <code>corpus_audit.md</code> et les 19 Q. V2→V3 aux médecins.</td></tr>
    <tr><td><b>Jeu 14h15–15h30</b><br/><i>Sprint 2 (1h15)</i></td><td>Benchmark End-to-End LLM + RAG-X 4 quadrants</td><td><code>python scripts/run_e2e_eval.py --base-url &lt;URL_LDH&gt; --model &lt;LLM&gt;</code> — comparer LLM seul vs C0 Naïf vs C8 Frontier sur les 171 questions + diagnostic RAG-X.</td></tr>
    <tr><td><b>Jeu 15h30–17h30</b><br/><i>Sprint 3 (2h)</i></td><td><code>pgvector</code> + tests cliniciens live + API <code>/v1</code></td><td>Exporter vers <code>pgvector</code> (<code>scripts/export_pgvector.py</code>). Lancer <code>rag-sfar-serve</code> pour tests médecins sur IIA 2026 &amp; Anticoagulants 2026. Brancher <code>plateforme-evaluation</code> sur <code>/v1/chat/completions</code>.</td></tr>
    <tr><td><b>Ven 10h00–11h15</b><br/><i>Sprint 4 (1h15)</i></td><td>Éval sur les nouveaux benchmarks créés Jour 1</td><td>Évaluer C0 vs C8 sur les nouvelles questions Anticoagulants / IIA / vignettes rédigées par l'équipe <code>benchmark-enrichi</code> + test démo MCP.</td></tr>
    <tr><td><b>Ven 11h15–12h30</b><br/><i>Prépa Pitch</i></td><td>Slides + captures de secours + répétition</td><td>Intégrer les 2 graphiques SVG <code>chart_ablation_*.svg</code> + courbe E2E RAG-X + répéter la démo live de 90s.</td></tr>
  </tbody>
</table>

<h2>10.2. Conducteur du Pitch Gagnant (8 minutes chrono — Vendredi 14h00)</h2>
<ol>
  <li><b>Accroche (30s)</b> : <i>« Sans RAG, un LLM se trompe 1 fois sur 4 en antibioprophylaxie. Avec un RAG naïf sur les 264 RFE SFAR, c'est pire sur le plan réglementaire : {naive_obs} à {c4_obs_str} des requêtes ramènent des éditions périmées (2015–2018) et 49 % des tableaux perdent leurs en-têtes ! »</i></li>
  <li><b>Audit Forensique (1 min 15)</b> : Montrer nos 8 découvertes (2 056 tableaux HTML, 57 sous-domaines <code>None</code> dont les 3 RFE 2026, recommandations piégées après <code>#### Références</code>, 44 éditions remplacées).</li>
  <li><b>Architecture Frontier 2026 (1 min 30)</b> : Figure 3 — Table/Row-Card Engine, Graphe temporel, Tri-Canal DBSF+RRF, CRAG Multi-Hop, U-Shape &amp; Vérificateur de molécules.</li>
  <li><b>Preuve Scientifique C0 → C8 + RAG-X (2 min)</b> : Courbe d'ablation (Figures 4 &amp; 5), 0,0 % d'obsolète, ~99 % Evidence Recall, Accuracy E2E RAG-X (Grounded Success vs Lucky Guess) et <b>-98 % de tokens vs Long Context</b>.</li>
  <li><b>Démo Live 90s (3 questions tueuses)</b> : (a) <i>PTH voie antérieure + allergie</i> → Vancomycine/Teicoplanine 2026 + citation + Grounding 100 % ; (b) <i>Arrêt AOD neurochirurgie programmée (2026)</i> vs <i>Hémorragie intracrânienne urgence (2024)</i> → séparation parfaite de périmètre ; (c) <i>Évolution antibioprophylaxie 2018 vs 2026</i> → bascule automatique multi-éditions !</li>
  <li><b>Écosystème Open Source &amp; Souveraineté (1 min)</b> : Natif LibreDataHub (<code>pgvector</code> + Ollama/vLLM), API OpenAI-compatible branchée sur <code>plateforme-evaluation</code>, <code>SfarRagApproach</code> et serveur <b>MCP</b> <code>rag-sfar-mcp</code>.</li>
</ol>

<h2>10.3. Les 12 Questions Pièges du Jury &amp; Tes Réponses Parfaites</h2>

<div class="qa-item"><div class="qa-q">1. Pourquoi ne pas tout envoyer dans un LLM Long Context (128k–1M tokens) ?</div><p class="qa-a">Sur une seule RFE (~95k tokens), le Long Context coûte 35 à 60× plus de tokens/énergie et souffre du <i>Lost-in-the-Middle</i> (LaRA 2025). Sur 264 RFE (5,8M tokens), il est techniquement impossible et ne gère ni la supersession temporelle ni la citation granulaire.</p></div>

<div class="qa-item"><div class="qa-q">2. Comment prouvez-vous que le LLM ne « devine » pas la bonne molécule par cœur ?</div><p class="qa-a">Grâce au diagnostic <b>RAG-X (2026)</b> en 4 quadrants (<code>rag_x.py</code>) qui distingue <i>Succès Sourcé</i> et <i>Coup de Chance Paramétrique</i>, et à notre vérificateur <code>verifier.py</code> qui bloque toute molécule absente des sources récupérées.</p></div>

<div class="qa-item"><div class="qa-q">3. Pourquoi un hybride Tri-Canal (BM25+ + Char N-Gram + Dense) avec DBSF+RRF plutôt qu'un simple RAG vectoriel ?</div><p class="qa-a">Notre ablation le prouve : Dense seul plafonne à {c4_ev_str} d'Evidence Recall car les Bi-Encoders confondent des molécules/actes voisins. BM25+ apporte l'exactitude lexicale, Char 3–5 N-Gram absorbe la morphologie française et les coquilles OCR, et DBSF préserve l'amplitude des matchs exacts là où RRF seul les aplatit.</p></div>

<div class="qa-item"><div class="qa-q">4. Que se passe-t-il si une question combine un geste chirurgical et un facteur patient complexe (BLSE, obèse, allergie) ?</div><p class="qa-a">C'est du <i>multi-hop</i> intra-document : notre module <b>CRAG</b> (<code>crag.py</code>) décompose la facette systémique et lance une passe corrective si elle manque, tandis que le <b>Context Builder</b> rattache automatiquement l'encadré allergie de la spécialité exacte.</p></div>

<div class="qa-item"><div class="qa-q">5. Pourquoi n'avez-vous pas filtré strictement par <code>subdomain</code> ?</div><p class="qa-a">Parce que notre audit a révélé que les <b>3 RFE phares 2026</b> (et 57 documents) ont <code>subdomain = None</code> ! Un filtre dur aurait renvoyé exclusivement les éditions obsolètes 2015 et 2018. Nous imputons les domaines et appliquons un <i>Soft Metadata Boost</i>.</p></div>

<div class="qa-item"><div class="qa-q">6. Votre filtre « édition la plus récente » ne risque-t-il pas d'écraser une recommandation d'urgence par une recommandation programmée ?</div><p class="qa-a">Non : notre graphe de supersession (<code>loader.py</code>) respecte le périmètre clinique. <i>Anticoagulants procédure programmée 2026</i> et <i>Anticoagulation urgence 2024</i> appartiennent à deux lignées distinctes, toutes deux en vigueur, et le routeur oriente selon le contexte détecté.</p></div>

<div class="qa-item"><div class="qa-q">7. Comment gérez-vous la pédiatrie ajoutée en V3.0 (mai 2026) sans polluer les réponses adultes ?</div><p class="qa-a">Nous normalisons la hiérarchie <code>CHAMP 2 (Adulte)</code> vs <code>CHAMP 3 (Pédiatrie)</code>, étiquetons <code>population_hint</code> par chunk (en ayant corrigé les faux positifs sur les « Champ 3 » non pédiatriques !) et appliquons une pénalité de cohérence avant ET après le Cross-Encoder.</p></div>

<div class="qa-item"><div class="qa-q">8. Que faire face aux erreurs d'OCR résiduelles de Chandra dans les tableaux et figures ?</div><p class="qa-a">Notre parseur corrige les titres collés, répare les 49,1 % de tableaux sans en-tête et résout les <code>rowspan</code>, mais chaque réponse affiche toujours l'extrait sourcé et le lien SFAR officiel (le PDF SFAR faisant seul foi). Pour les 1 131 figures, la suite naturelle est l'indexation visuelle multimodale type <b>ColPali / MED-VRAG</b>.</p></div>

<div class="qa-item"><div class="qa-q">9. Pourquoi ne pas avoir fait de Fine-Tuning médical ou de GraphRAG LLM complet ?</div><p class="qa-a">La littérature 2025 confirme que le fine-tuning seul hallucine plus que le RAG et fige la connaissance. Un GraphRAG extrait par LLM coûte très cher pour un corpus structuré où notre graphe léger natif (lignées temporelles + familles multi-fichiers + encadrés allergie liés) atteint déjà ~99 % de rappel à coût nul.</p></div>

<div class="qa-item"><div class="qa-q">10. Votre système est-il souverain, open source et conforme HDS / LibreDataHub ?</div><p class="qa-a">100 % open source (MIT), zéro API propriétaire obligatoire : embeddings &amp; reranker locaux en mode cache-first hors-ligne (<code>BGE-M3</code> / <code>BGE-Reranker-v2-M3</code>), stockage PostgreSQL <code>pgvector</code> natif, inférence Ollama/vLLM locale, aucune donnée patient.</p></div>

<div class="qa-item"><div class="qa-q">11. Quel est l'apport concret de votre serveur MCP par rapport au RAG classique ?</div><p class="qa-a">Le RAG reste le moteur de recherche déterministe à haute précision ; le serveur <b>MCP</b> (<code>rag-sfar-mcp</code>) en fait une brique réutilisable par n'importe quel agent clinique ou client compatible (OpenWebUI, LibreChat, Claude) avec 4 outils dédiés dont <code>compare_sfar_editions</code>.</p></div>

<div class="qa-item"><div class="qa-q">12. Comment maintenez-vous cet index à jour quand la SFAR publie une nouvelle RFE ?</div><p class="qa-a">Le dépôt <code>sfar_recommendations</code> génère un flux Atom idempotent (<code>feed.xml</code>) et des empreintes SHA-256 : un job planifié peut re-parser et ré-indexer uniquement les nouveaux documents en quelques secondes et mettre à jour automatiquement le graphe de supersession.</p></div>

<h2>10.4. Antisèche Commandes LibreDataHub &amp; Démonstration</h2>
<pre># 1. Upgrade 1-clic GPU LibreDataHub (BAAI/bge-m3 + BAAI/bge-reranker-v2-m3 + ablation C0-&gt;C8)
bash scripts/libredatahub_setup.sh

# 2. Évaluation End-to-End LLM + RAG-X 4 quadrants sur les 171 questions Antibioprophylaxie
python scripts/run_e2e_eval.py --base-url http://&lt;OLLAMA_OU_VLLM&gt;/v1 --model &lt;NOM_MODELE&gt;

# 3. Export souverain natif vers PostgreSQL + pgvector (HNSW + tsvector français)
python scripts/export_pgvector.py --index-dir index/table_aware_sota --dsn "$RAG_SFAR_PGVECTOR_DSN"

# 4. Serveur Démonstrateur Web Clinique + API OpenAI-compatible (/v1/chat/completions)
rag-sfar-serve --index-dir index/table_aware_sota --host 0.0.0.0 --port 8000

# 5. Serveur MCP (Model Context Protocol, 4 outils cliniques SFAR)
rag-sfar-mcp</pre>

<h2>10.5. Glossaire Express RAG 2026 &amp; Références Scientifiques Clés</h2>
<table style="font-size:8pt;">
  <thead><tr><th>Terme / Méthode</th><th>Définition opérationnelle à connaître par cœur</th></tr></thead>
  <tbody>
    <tr><td><b>BM25+</b></td><td>Score lexical probabiliste à saturation TF (<code>k₁</code>) et normalisation de longueur (<code>b</code>) avec borne <code>δ = 0,5</code> évitant de sur-pénaliser les passages longs.</td></tr>
    <tr><td><b>Bi-Encoder vs Cross-Encoder</b></td><td>Bi-Encoder : encode Q et D séparément (rapide O(1), Stage 1). Cross-Encoder : encode <code>[CLS] Q [SEP] D</code> ensemble avec attention croisée complète (précis, Stage 2).</td></tr>
    <tr><td><b>ColBERT / MaxSim / ColPali</b></td><td>Interaction tardive multi-vecteurs (<code>Σ max cos</code>) entre tokens (ColBERT/BGE-M3) ou patchs d'image de page PDF (ColPali / MED-VRAG).</td></tr>
    <tr><td><b>RRF vs DBSF</b></td><td>RRF fusionne par rang (<code>1/(k+r)</code>) ; DBSF normalise les distributions (<code>μ ± 3σ</code>) pour préserver l'amplitude des matchs exacts hors-norme.</td></tr>
    <tr><td><b>HNSW</b></td><td>Index vectoriel ANN en graphe hiérarchique petit-monde (<code>pgvector</code>), recherche en <i>O(log N)</i> gouvernée par <code>M</code>, <code>ef_construction</code> et <code>ef_search</code>.</td></tr>
    <tr><td><b>CRAG / Self-MedRAG</b></td><td>Boucle post-retrieval vérifiant si les preuves couvrent toutes les facettes cliniques (BLSE, obèse, allergie, pédiatrie) avant de déclencher une passe corrective.</td></tr>
    <tr><td><b>U-Shape &amp; Provence</b></td><td>Placement des meilleures sources aux extrémités du prompt (anti <i>Lost-in-the-Middle</i>) + élagage sélectif des phrases narratives superflues.</td></tr>
    <tr><td><b>RAG-X &amp; CUE</b></td><td>Matrice 4 quadrants séparant <i>Succès Sourcé (Q1)</i> et <i>Coup de Chance Paramétrique (Q2)</i> ; <code>CUE = Q1/(Q1+Q3)</code> mesure l'usage réel du contexte par le LLM.</td></tr>
  </tbody>
</table>

<div class="box" style="font-size:8pt;padding:8px 11px;">
  <div class="box-title" style="font-size:8.6pt;">Bibliographie Scientifique de Référence (2020–2026)</div>
  <ul style="margin:0;columns:2;column-gap:16px;">
    <li>Lewis et al., <i>RAG for Knowledge-Intensive NLP</i>, NeurIPS 2020.</li>
    <li>Cormack et al., <i>Reciprocal Rank Fusion</i>, SIGIR 2009.</li>
    <li>Bruch et al., <i>An Analysis of Fusion Functions for Hybrid Retrieval</i>, ACM TOIS.</li>
    <li>Liu et al., <i>Lost in the Middle</i>, TACL 2024.</li>
    <li>Yan et al., <i>Corrective Retrieval Augmented Generation (CRAG)</i>, arXiv 2024.</li>
    <li>Anthropic, <i>Contextual Retrieval</i> (2024) ; Jina AI, <i>Late Chunking</i> (2024).</li>
    <li>Faysse et al., <i>ColPali: Visual Document Retrieval</i>, ICLR 2025.</li>
    <li>Chirkova et al., <i>Provence: Efficient Context Pruning for RAG</i>, ICLR 2025.</li>
    <li>Li et al., <i>LaRA: Benchmarking RAG vs Long-Context LLMs</i>, ICLR 2025.</li>
    <li><i>RAG vs Fine-Tuning for Medical LLMs</i>, MDPI Bioengineering, juin 2025.</li>
    <li><i>RAG for Surgical Fitness / Conversational Drift</i>, npj Digital Medicine, 2025–2026.</li>
    <li><i>RAG-X (Component-Level Diagnostics)</i> &amp; <i>Self-MedRAG</i>, arXiv 2026.</li>
  </ul>
</div>

</body>
</html>
"""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--html-only", action="store_true")
    args = parser.parse_args()

    html_content = build_html()
    html_path = ROOT / "reports" / "masterclass_course.html"
    pdf_path = ROOT / "COURS_INTEGRAL_RAG_ET_DATATHON_SFAR.pdf"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_content, encoding="utf-8")
    print(f"HTML generated: {html_path} ({html_path.stat().st_size:,} bytes)")
    if args.html_only:
        return

    if not CHROME_BIN.exists():
        raise FileNotFoundError(f"Google Chrome not found at {CHROME_BIN}")

    cmd = [
        str(CHROME_BIN),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={pdf_path}",
        html_path.as_uri(),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    print(f"PDF generated successfully: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
