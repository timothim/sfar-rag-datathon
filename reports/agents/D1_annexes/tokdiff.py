# tokdiff.py md pdf : dose tokens (number+mass/volume unit) present in md but absent from the PDF text layer
import sys, re, collections
sys.path.insert(0, sys.argv[3])
from detect_doses import latex_to_text, html_to_lines
from pypdf import PdfReader
md = html_to_lines(latex_to_text(open(sys.argv[1], encoding='utf-8').read()))
pdf = "\n".join((p.extract_text() or "") for p in PdfReader(sys.argv[2]).pages)
def norm(t):
    t = t.replace('µ','µ').replace('μ','µ').replace(',', '.')
    t = re.sub(r'\s+', ' ', t)
    return t
TOK = re.compile(r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(µg|mg|ng|g|ml|mL|UI|mmol)(?![a-zA-Z])')
def toks(t):
    c = collections.Counter()
    for m in TOK.finditer(norm(t)):
        c[(m.group(1), m.group(2).lower())] += 1
    return c
a, b = toks(md), toks(pdf)
# PDF text layer may render µ as 'm' (symbol font): count µg tokens matched by mg in PDF separately
miss = []
for k, n in a.items():
    if b.get(k, 0) == 0:
        alt = (k[0], 'mg') if k[1] == 'µg' else None
        miss.append((k, n, 'pdf has mg instead' if alt and b.get(alt) else ''))
print(f"md tokens {sum(a.values())} distinct {len(a)}; absent from PDF text: {len(miss)}")
for k, n, note in sorted(miss): print(' ', k, n, note)
