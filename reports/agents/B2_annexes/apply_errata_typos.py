"""Erratum of two spelling errors of the V3.1 overlay (B2, 2026-11-27), checked against the
official PDF (pypdf text): p. 89 "Lithotritie extra-corporelle", p. 96 "Amygdalectomie",
"Adéno-amygdalectomie". Exact replacements, each checked for its expected count; the file is
left untouched if any count differs.

Usage: .venv/bin/python reports/agents/B2_annexes/apply_errata_typos.py <overlay .md>
"""
import sys

REPLACEMENTS = [
    # (old, new, expected occurrences)
    ("Lithotrite extra-corporelle", "Lithotritie extra-corporelle", 1),
    ("Adéno-amygdallectomie", "Adéno-amygdalectomie", 1),
    ("Amygdallectomie", "Amygdalectomie", 1),
]

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
for old, new, n in REPLACEMENTS:
    found = text.count(old)
    if found != n:
        sys.exit(f"Expected {n} x {old!r}, found {found}: nothing written")
for old, new, _ in REPLACEMENTS:
    text = text.replace(old, new)
open(path, "w", encoding="utf-8").write(text)
print("Applied", len(REPLACEMENTS), "replacements to", path)
