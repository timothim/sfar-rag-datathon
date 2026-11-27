"""Words (>= 6 letters) of the V3.1 overlay Markdown that do not occur in the official PDF text.

Run: .venv/bin/python -I reports/agents/B2_annexes/overlay_vs_pdf_words.py <overlay.md> <official.pdf>
Comparison is case-insensitive on NFC text; PDF hyphenation at line ends is undone, and words
are also searched without spaces in the PDF text (pdftotext splits words across columns)."""
import collections
import re
import sys
import unicodedata

from pypdf import PdfReader

md = unicodedata.normalize("NFC", open(sys.argv[1], encoding="utf-8").read())
md = re.sub(r"<[^>]+>", " ", md)
md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)
pdf = " ".join((p.extract_text() or "") for p in PdfReader(sys.argv[2]).pages)
pdf = unicodedata.normalize("NFC", pdf).replace("’", "'")
pdf = re.sub(r"-\s*\n\s*", "", pdf)
pdf_low = pdf.lower()
pdf_words = set(re.findall(r"[a-zà-ÿœ]+", pdf_low))
pdf_compact = re.sub(r"\s+", "", pdf_low)
md_words = collections.Counter(w for w in re.findall(r"[A-Za-zÀ-ÿŒœ]{6,}", md))
missing = []
for w, n in md_words.items():
    lw = w.lower()
    if lw in pdf_words or lw in pdf_compact:
        continue
    i = md.find(w)
    missing.append((w, n, md[max(0, i - 60): i + 60].replace("\n", " ")))
for w, n, ctx in sorted(missing, key=lambda x: x[0].lower()):
    print(f"{w}\t{n}\t{ctx}")
print(f"# {len(missing)} mots absents du PDF sur {len(md_words)} mots distincts", file=sys.stderr)
