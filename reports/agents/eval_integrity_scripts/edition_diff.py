#!/usr/bin/env python3
"""Audit d'édition : RFE antibioprophylaxie V2.0 (22/05/2024, source du benchmark)
vs V3.0 (04/05/2026, édition que le système considère "en vigueur").

1. Extrait le texte V2.0 (pdftotext -layout) et V3.0 (Markdown Chandra, balises HTML ôtées),
   restreint aux Champs 1-2 (adulte) car le benchmark ne porte que sur l'adulte.
2. Diff au niveau mot (difflib, flux de mots normalisés) -> régions modifiées.
3. Ne garde que les régions modifiées qui touchent une molécule, "pas d'antibioprophylaxie",
   une posologie ou un intitulé d'acte, et affiche leur contexte.
4. Pour chaque question du benchmark, cherche si un mot-clé d'acte de la question tombe dans
   une fenêtre de +/- 40 mots autour d'une région modifiée (=> question "à risque" de
   changement de réponse, à vérifier manuellement).
Usage : python3 -I reports/agents/eval_integrity_scripts/edition_diff.py <scratch_dir>
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
V2_PDF = ROOT / "data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/RFE-antibioprophylaxie-SFAR-v2.0.pdf"
V3_MD = next((ROOT / "data/sfar_recommendations/output/chandra/2023").glob("RFE-antibioprophylaxie-2023_V3.0*/*.md"))
BENCH = ROOT / "data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json"

MOLS = (
    "cefazoline cefuroxime cefoxitine ceftriaxone cefotaxime ceftazidime amoxicilline clavulanate "
    "clindamycine vancomycine teicoplanine gentamicine metronidazole ertapeneme piperacilline "
    "tazobactam fosfomycine trimethoprime sulfamethoxazole ciprofloxacine levofloxacine ofloxacine "
    "aztreonam daptomycine linezolide doxycycline cotrimoxazole amikacine"
).split()
STOP = set(
    "quelle est la recommandation d antibioprophylaxie pour une un des de du le les la l chez patient "
    "avec sans et ou en a au aux par sur dans cas lors prise charge chirurgicale chirurgie".split()
)


def fold(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    return s.replace("’", "'")


def words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:[/+-][a-z0-9]+)*", fold(s))


def main() -> None:
    scratch = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp")
    v2_txt = scratch / "v2.txt"
    if not v2_txt.exists():
        subprocess.run(["pdftotext", "-layout", str(V2_PDF), str(v2_txt)], check=True)
    v2 = v2_txt.read_text(encoding="utf-8", errors="ignore")
    v3 = V3_MD.read_text(encoding="utf-8")
    v3 = re.sub(r"<[^>]+>", " ", v3)

    # Champs 1-2 seulement (le Champ 3 pédiatrique est absent/vide en V2.0)
    def cut_before_champ3(t: str) -> str:
        idx = [m.start() for m in re.finditer(r"CHAMP\s*3\s*[:\-–]?\s*(?:TABLEAUX|RECOMMANDATIONS|ANTIBIOPROPHYLAXIE)", t, re.I)]
        # garder la dernière occurrence plausible après la moitié du texte (pas l'intro)
        idx = [i for i in idx if i > len(t) * 0.4]
        return t[: idx[0]] if idx else t

    w2 = words(cut_before_champ3(v2))
    w3 = words(cut_before_champ3(v3))
    sm = difflib.SequenceMatcher(a=w2, b=w3, autojunk=False)
    ratio = sm.quick_ratio()
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    clin_re = re.compile(r"(" + "|".join(MOLS) + r"|^pas$|antibioprophylaxie|\d+(?:[.,]\d+)?(?:g|mg|mg/kg)$)")
    regions = []
    for tag, i1, i2, j1, j2 in ops:
        old, new = w2[i1:i2], w3[j1:j2]
        if not any(clin_re.search(t) for t in old + new):
            continue
        # ignorer le bruit typographique pur (<= 2 mots, pas de molécule)
        if len(old) + len(new) <= 2 and not any(t in MOLS for t in old + new):
            continue
        regions.append(
            {
                "tag": tag,
                "v2_pos": i1,
                "v3_pos": j1,
                "v2": " ".join(old)[:300],
                "v3": " ".join(new)[:300],
                "ctx_v3": " ".join(w3[max(0, j1 - 25) : j2 + 15])[:500],
                "mols_v2": sorted({t for t in old if t in MOLS}),
                "mols_v3": sorted({t for t in new if t in MOLS}),
            }
        )

    # mapping question -> régions proches (fenêtre +/- 40 mots en V3)
    qs = json.loads(BENCH.read_text(encoding="utf-8"))["questions"]
    at_risk = []
    for q in qs:
        kws = [t for t in words(q["titre"] + " " + q["question"]) if t not in STOP and len(t) >= 5 and t not in MOLS]
        near = []
        for k, r in enumerate(regions):
            win = set(w3[max(0, r["v3_pos"] - 40) : r["v3_pos"] + 60])
            hit = [kw for kw in kws if kw in win]
            if len(set(hit)) >= 2:
                near.append((k, sorted(set(hit))))
        if near:
            at_risk.append({"id": q["id"], "titre": q["titre"], "reponse": q["réponse"], "regions": near[:5]})

    out = {
        "v2_words_champ1_2": len(w2),
        "v3_words_champ1_2": len(w3),
        "quick_ratio": round(ratio, 4),
        "non_equal_opcodes": len(ops),
        "clinically_relevant_regions": len(regions),
        "regions_changing_a_molecule": sum(1 for r in regions if r["mols_v2"] != r["mols_v3"]),
        "questions_near_a_clinical_change (>=2 mots-clés d'acte)": len(at_risk),
        "at_risk": at_risk,
        "regions": regions,
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
