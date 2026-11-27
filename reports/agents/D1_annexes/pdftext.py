import sys, re
from pypdf import PdfReader
r = PdfReader(sys.argv[1])
pat = re.compile(sys.argv[2]) if len(sys.argv)>2 else None
for i,p in enumerate(r.pages):
    t = p.extract_text() or ""
    if pat is None:
        print(f"=== page {i+1}"); print(t)
    else:
        for m in pat.finditer(t):
            s=max(0,m.start()-80); print(f"p{i+1}: {t[s:m.end()+60]!r}")
