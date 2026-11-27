"""Erratum 3 (B2, 2026-11-27): spelling errors of the V3.1 overlay found by the systematic
comparison of its words with the official PDF text (overlay_vs_pdf_words.py ->
overlay_words_not_in_pdf.tsv). Only words whose PDF spelling was checked in context are
replaced; whole-word, case-sensitive replacements. Nothing is written if a word is absent.

Usage: .venv/bin/python reports/agents/B2_annexes/apply_errata_overlay_pass.py <overlay .md>
"""
import re
import sys

# (overlay form, PDF form, PDF page where the PDF form was checked)
REPLACEMENTS = [
    ("Céfuoxime", "Céfuroxime", 47), ("céfuoxime", "céfuroxime", 18),
    ("ANTIOPROPHYLAXIE", "ANTIBIOPROPHYLAXIE", 0), ("antiobiprophylaxie", "antibioprophylaxie", 0),
    ("antibiotoprophylaxie", "antibioprophylaxie", 0),
    ("Alteineier", "Altemeier", 77), ("amygdallectomie", "amygdalectomie", 5),
    ("Annexeectomie", "Annexectomie", 67), ("anévryhme", "anévrysme", 39),
    ("Bioprotèse", "Bioprothèse", 48), ("bioprotèse", "bioprothèse", 48),
    ("Bronchoscope", "Bronchoscopie", 55), ("Fibroscope", "Fibroscopie", 55),
    ("cœsophagienne", "œsophagienne", 116), ("emphyseme", "emphysème", 52),
    ("endométrieuse", "endométriose", 66), ("expendeur", "expandeur", 57),
    ("Gênioplastie", "Génioplastie", 58), ("siteopérateur", "site opérateur", 0),
    ("susgrigonale", "sustrigonale", 88), ("transfixant", "transfixiant", 97),
    ("tympons", "tympans", 96), ("Ténotomy", "Ténotomie", 109),
]

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
counts = {}
for old, new, _ in REPLACEMENTS:
    n = len(re.findall(rf"(?<![\w]){re.escape(old)}(?![\w])", text))
    if n == 0:
        sys.exit(f"{old!r} not found: nothing written")
    counts[old] = n
for old, new, _ in REPLACEMENTS:
    text = re.sub(rf"(?<![\w]){re.escape(old)}(?![\w])", new, text)
open(path, "w", encoding="utf-8").write(text)
for old, new, page in REPLACEMENTS:
    print(f"{old} -> {new} x{counts[old]} (PDF p. {page or 'plusieurs'})")
