#!/usr/bin/env python3
"""Generate the official SFAR Antibioprophylaxie V3.1 (10/07/2026) overlay Markdown.

Based on the bit-for-bit audit of V3.0 (04/05/2026) vs V3.1 (10/07/2026, SHA-256
642ad1f1c2ae3a050d1165eb41caab9e0f418deb2770538afb2dc0005ced9e03):
- Pages 1–119 are identical except page 6 (Historique des versions: V3.1 entry).
- Pages 120–121 (PARTIE 9 : Chirurgie néonatalogique, Chirurgie du tube digestif *)
  amend the regimen for neonatal small-bowel and colorectal surgery to:
  * Céfazoline 30 mg/kg IVL + Métronidazole 15 mg/kg IVL (Enfant <7j: pas de réinjection;
    Enfant >=7j: Céfazoline 30 mg/kg si durée >4h puis /4h, Métronidazole pas de réinjection)
  * Alternative : Céfoxitine 40 mg/kg IVL (Enfant <7j: pas de réinjection;
    Enfant >=7j: 40 mg/kg si durée >2h puis /2h jusqu'à fin de chirurgie).
"""

from __future__ import annotations

import json
from pathlib import Path

V30_MD = Path(
    "data/sfar_recommendations/output/chandra/2023/"
    "RFE-antibioprophylaxie-2023_V3.0_pour-mise-sur-site-juin-2026_sans-code-CCAM/"
    "RFE-antibioprophylaxie-2023_V3.0_pour-mise-sur-site-juin-2026_sans-code-CCAM.md"
)
OUT_DIR = Path("data/corpus_updates")
OUT_MD = OUT_DIR / "RFE-antibioprophylaxie-2023_V3.1_pour-mise-sur-site-juillet-2026_sans-code-CCAM.md"
OUT_MANIFEST = OUT_DIR / "updates_manifest.json"

V31_HISTORY_ENTRY = (
    "\n- - V3.1 du 10/07/2026 : amendement du schéma pour les chirurgies digestives "
    "néonatales grêliques ou colorectales avec en alternatives soit l'association "
    "céfazoline + métronidazole soit la céfoxitine (pages 120-121)."
)

OLD_ILEAL_ROW = """<tr>
<td>
<ul style="list-style-type: none; padding-left: 0;">
<li>▪ Cure d'atrésie de l'intestin grêle</li>
</ul>
</td>
<td>Céfoxitine</td>
<td>40 mg/kg IVL</td>
<td>
<u>Enfant &lt; 7j :</u><br/>
          Pas de réinjection<br/>
<u>Enfant ≥ 7j :</u><br/>
          40 mg/kg si durée &gt; 2h puis toutes les 2h jusqu'à fin de chirurgie
        </td>
<td>●●● (Avis d'experts)</td>
</tr>"""

NEW_ILEAL_ROW = """<tr>
<td rowspan="2">
<ul style="list-style-type: none; padding-left: 0;">
<li>▪ Cure d'atrésie de l'intestin grêle</li>
</ul>
</td>
<td>Céfazoline + Métronidazole</td>
<td>Céfazoline : 30 mg/kg IVL + Métronidazole : 15 mg/kg IVL</td>
<td>
Céfazoline — <u>Enfant &lt; 7j :</u> Pas de réinjection ; <u>Enfant ≥ 7j :</u> 30 mg/kg si durée &gt; 4h puis toutes les 4h jusqu'à fin de chirurgie.<br/>
Métronidazole — Pas de réinjection.
</td>
<td rowspan="2">◉◎◎ (Avis d'experts)</td>
</tr>
<tr>
<td>Alternative : Céfoxitine</td>
<td>40 mg/kg IVL</td>
<td>
<u>Enfant &lt; 7j :</u> Pas de réinjection ; <u>Enfant ≥ 7j :</u> 40 mg/kg si durée &gt; 2h puis toutes les 2h jusqu'à fin de chirurgie
</td>
</tr>"""

OLD_COLORECTAL_ROW = """<tr>
<td>
<ul style="list-style-type: none; padding-left: 0;">
<li>▪ Colectomie</li>
<li>▪ Chirurgie de la maladie de Hirschsprung (colostomie)</li>
<li>▪ Atrésie post-entérocolite</li>
<li>▪ Anoplastie **</li>
</ul>
</td>
<td>Céfoxitine</td>
<td>40 mg/kg IVL</td>
<td>
<u>Enfant &lt; 7j :</u><br/>
          Pas de réinjection<br/>
<u>Enfant ≥ 7j :</u><br/>
          40 mg/kg si durée &gt; 2h puis toutes les 2h jusqu'à fin de chirurgie
        </td>
<td>●●● (Avis d'experts)</td>
</tr>"""

NEW_COLORECTAL_ROW = """<tr>
<td rowspan="2">
<ul style="list-style-type: none; padding-left: 0;">
<li>▪ Colectomie</li>
<li>▪ Chirurgie de la maladie de Hirschsprung (colostomie)</li>
<li>▪ Atrésie post-entérocolite</li>
<li>▪ Anoplastie **</li>
</ul>
</td>
<td>Céfazoline + Métronidazole</td>
<td>Céfazoline : 30 mg/kg IVL + Métronidazole : 15 mg/kg IVL</td>
<td>
Céfazoline — <u>Enfant &lt; 7j :</u> Pas de réinjection ; <u>Enfant ≥ 7j :</u> 30 mg/kg si durée &gt; 4h puis toutes les 4h jusqu'à fin de chirurgie.<br/>
Métronidazole — Pas de réinjection.
</td>
<td rowspan="2">◉◎◎ (Avis d'experts)</td>
</tr>
<tr>
<td>Alternative : Céfoxitine</td>
<td>40 mg/kg IVL</td>
<td>
<u>Enfant &lt; 7j :</u> Pas de réinjection ; <u>Enfant ≥ 7j :</u> 40 mg/kg si durée &gt; 2h puis toutes les 2h jusqu'à fin de chirurgie
</td>
</tr>"""


def main() -> None:
    if not V30_MD.exists():
        raise FileNotFoundError(f"Base V3.0 Markdown not found: {V30_MD}")
    text = V30_MD.read_text(encoding="utf-8")

    anchor = "(à partir de la page 91).## INTRODUCTION"
    if anchor not in text:
        raise ValueError("Could not find V3.0 history anchor in source Markdown")
    text = text.replace(anchor, f"(à partir de la page 91).{V31_HISTORY_ENTRY}\n\n## INTRODUCTION", 1)

    if OLD_ILEAL_ROW not in text:
        raise ValueError("Could not find V3.0 neonatal ileal row in source Markdown")
    text = text.replace(OLD_ILEAL_ROW, NEW_ILEAL_ROW, 1)

    if OLD_COLORECTAL_ROW not in text:
        raise ValueError("Could not find V3.0 neonatal colorectal row in source Markdown")
    text = text.replace(OLD_COLORECTAL_ROW, NEW_COLORECTAL_ROW, 1)

    # Fix Chandra OCR typo on page 120 ("laparoscisis" -> "laparoschisis" in official PDF)
    text = text.replace("laparoscisis/omphalocèle", "laparoschisis/omphalocèle")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(text, encoding="utf-8")

    manifest = {
        "documents": [
            {
                "filename": "RFE-antibioprophylaxie-2023_V3.1_pour-mise-sur-site-juillet-2026_sans-code-CCAM.pdf",
                "md_file": OUT_MD.name,
                "title": "Antibioprophylaxie en chirurgie et médecine interventionnelle",
                "type": "RFE",
                "year": 2023,
                "discipline": "Anesthesie",
                "subdomain": "Infectiologie",
                "sha256": "642ad1f1c2ae3a050d1165eb41caab9e0f418deb2770538afb2dc0005ced9e03",
                "landing_url": "https://sfar.org/antibioprophylaxie-en-chirurgie-et-medecine-interventionnelle/",
                "download_url": "https://www.cnpcea.fr/wp-content/uploads/2026/11/RFE-antibioprophylaxie-2023_V3.1_pour-mise-sur-site-juillet-2026_sans-code-CCAM-1.pdf",
                "num_pages": 122,
                "source_tabs": ["update_v3.1"],
            }
        ]
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_MD} ({len(text):,} chars) and {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
