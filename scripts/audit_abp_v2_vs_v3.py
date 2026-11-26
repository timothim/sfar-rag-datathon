#!/usr/bin/env python3
"""Audit the 171-question Antibioprophylaxie benchmark (built on V2.0 2024) against
the latest June 2026 V3.0 RFE in `sfar_recommendations`.

Highlights:
- Official V2.0 -> V3.0 changelog items extracted directly from V3.0
- Which of the 171 questions touch areas modified in V3.0 (obesity R1.5.2/R1.6,
  allergy prolongation schemes, gender-affirming surgery, hand complex trauma,
  wall hernia, prostate biopsy fosfomycin, and new Champ 3 pediatrics!)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from rag_sfar.evaluation.benchmarks import load_antibioprophylaxie_benchmark
from rag_sfar.ingestion.loader import load_sfar_corpus


V3_CHANGED_TOPICS: list[tuple[str, str, list[str]]] = [
    ("Obésité (R1.5.2 Amox/Clav & R1.6 IMC Clindamycine)", "V3.0 p.25-30", [r"\bob[èe]s\w*", r"\bimc\b", r"100\s*kg", r"120\s*kg"]),
    ("Allergie bêtalactamines / prolongation postop", "V3.0 tableaux", [r"\ballerg\w*", r"\bp[ée]nicilline\w*", r"\bb[êe]talactamine\w*"]),
    ("Valve Zéphyr (posologie modifiée)", "V3.0 p.55", [r"z[ée]phyr", r"valve\s+endobronchique"]),
    ("Chirurgie d'affirmation de genre (vaginoplastie & encadré allergie céfoxitine)", "V3.0 p.60", [r"vaginoplastie", r"affirmation\s+de\s+genre"]),
    ("Traumatismes complexes de la main (encadré allergie ajouté)", "V3.0 p.75", [r"\bmain\b", r"[ée]crasement"]),
    ("Chirurgie des hernies de paroi (intitulés modifiés)", "V3.0 p.83", [r"\bhernie\w*", r"[ée]ventration\w*"]),
    ("Biopsie prostate transrectale (délais fosfomycine précisés)", "V3.0 p.88", [r"biopsie.*prostate", r"prostate.*biopsie", r"fosfomycine"]),
    ("Champ 3 : Pédiatrie & néonatalogie (9 nouveaux tableaux)", "V3.0 p.91+", [r"\benfant\w*", r"\bp[ée]diatr\w*", r"\bnourrisson\w*", r"\bn[ée]onatal\w*", r"\b\d+\s*(?:mois|ans)\b"]),
]


def main() -> None:
    bench = load_antibioprophylaxie_benchmark(
        Path("data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json")
    )
    docs = load_sfar_corpus(Path("data/sfar_recommendations/output"))
    abp_v3 = [d for d in docs if d.metadata.topic_lineage == "antibioprophylaxie" and d.metadata.is_latest_edition][0]

    # Extract official V3.0 changelog line
    m = re.search(r"V3\.0 du 04/05/2026[^\n]+", abp_v3.text)
    changelog_v3 = m.group(0).strip() if m else ""

    flagged = []
    for q in bench:
        blob = f"{q.title} {q.question} {q.expected_answer}".lower()
        hits = []
        for label, loc, pats in V3_CHANGED_TOPICS:
            if any(re.search(pat, blob, re.I) for pat in pats):
                hits.append(f"{label} ({loc})")
        if hits:
            flagged.append(
                {
                    "id": q.id,
                    "title": q.title,
                    "type": q.question_type,
                    "expected_v2": q.expected_answer,
                    "v3_impact_areas": hits,
                }
            )

    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "abp_v2_vs_v3_audit.json").write_text(
        json.dumps(
            {
                "v3_version": abp_v3.metadata.version_label,
                "v3_changelog": changelog_v3,
                "total_benchmark_questions": len(bench),
                "flagged_for_v3_review": len(flagged),
                "questions": flagged,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Audit de Dérive Temporelle : Benchmark Antibioprophylaxie V2.0 (2024) vs RFE V3.0 (04/05/2026)\n",
        f"- **Questions totales dans le benchmark officiel** : {len(bench)}",
        f"- **Questions touchant une zone modifiée ou ajoutée en V3.0** : **{len(flagged)}**\n",
        "## Changelog officiel extrait de la RFE V3.0 (04/05/2026)\n",
        f"> {changelog_v3}\n",
        "## Questions du benchmark à revérifier en priorité avec les médecins SFAR\n",
        "| ID | Titre | Type | Réponse V2.0 | Zone impactée en V3.0 |",
        "|---|---|---|---|---|",
    ]
    for f in flagged:
        lines.append(
            f"| `{f['id']}` | {f['title']} | {f['type']} | `{f['expected_v2']}` | {'; '.join(f['v3_impact_areas'])} |"
        )
    (out_dir / "abp_v2_vs_v3_audit.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"V2->V3 drift audit written: {len(flagged)}/{len(bench)} questions flagged for clinician review.")


if __name__ == "__main__":
    main()
