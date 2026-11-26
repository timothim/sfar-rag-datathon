"""06 - Part des bibliographies : estimation indépendante de celle du loader.
Méthode A (titres) : texte situé après un titre « Références/Bibliographie » jusqu'au titre suivant de niveau <= .
Méthode B (lignes) : lignes ressemblant à une référence (auteurs + année + volume/pages ou « et al. »).
Relancer : .venv/bin/python reports/agents/data_audit_scripts/06_references_share.py
"""
import json
import re

from common import OUT, ROOT, read

inv = json.loads((OUT / "inventory.json").read_text())["rows"]
REFH = re.compile(r"^(#{1,6})\s*(?:\*\*)?\s*(?:[\dIVX]+[.)]?\s*)?(r[ée]f[ée]rences?(?: bibliographiques)?|bibliographie|references)\b", re.I)
BOLDREF = re.compile(r"^\*\*\s*(r[ée]f[ée]rences?|bibliographie|references)\s*:?\s*\*\*\s*:?\s*$", re.I)
CIT = re.compile(r"(?:\bet al\b|[A-Z][a-zà-ü\-]+ [A-Z]{1,3}[,.]).{0,300}\b(?:19|20)\d\d\b.{0,80}(?:;\s?\d+|:\s?\d+|\d+\s?[-–]\s?\d+|doi)", re.I)
totA = totB = tot = 0
noA = 0
for r in inv:
    t = read(ROOT / r["md"])
    lines = t.split("\n")
    inref, lvl, a = False, 9, 0
    for l in lines:
        m = REFH.match(l.strip())
        h = re.match(r"^(#{1,6})\s", l)
        if m or BOLDREF.match(l.strip()):
            inref, lvl = True, len(m.group(1)) if m else 9
            continue
        if inref and h and len(h.group(1)) <= lvl:
            inref = False
        if inref:
            a += len(l) + 1
    b = sum(len(l) + 1 for l in lines if CIT.search(l) and len(l) < 1500)
    totA += a; totB += b; tot += len(t); noA += (a == 0)
print(f"Méthode A (sections titrées) : {totA/tot:.3f} ; docs sans section repérée : {noA}/{len(inv)}")
print(f"Méthode B (lignes de citation) : {totB/tot:.3f}")
