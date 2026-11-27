"""Shared driver for test_k3_table_headers: parses every table of a document the way the chunker
feeds the parser (last explicit headers, contiguity = only blank text in between) and digests the
results. Corpus text is read from data/ at test time; nothing of it is stored."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re

DOC_PATTERNS = [
    "antibioprophylaxie-2023_V3_1", "Reco_ECBU_Argumentaire", "HAS_transfusion", "argu_sepsis",
    "RFE-gestion-de-lanticoagu", "RESECTION_-HEPATIQUE_-RECOMMANDATIONS", "RFE-analgesie-obstetricale",
    "gestion_voies_aeriennes_recommandations", "Dossier-AnesthRea", "Securisation-des-procedures",
    "Nutrition-artificielle", "RPP-FHS",
]


def table_digests(text: str, parse) -> str:
    toks = re.split(r"(<table\b.*?</table>)", text, flags=re.S | re.I)
    prev_headers = None
    contiguous = False
    out = []
    for tok in toks:
        if not tok or not tok.strip():
            continue
        if not tok.lstrip().lower().startswith("<table"):
            contiguous = False
            continue
        t = parse(tok, previous_headers=prev_headers, previous_is_contiguous=contiguous)
        out.append(json.dumps(dataclasses.asdict(t), ensure_ascii=False, sort_keys=True))
        if t.has_explicit_headers and t.headers:
            prev_headers = t.headers
        contiguous = True
    return hashlib.sha256("\n".join(out).encode()).hexdigest()
