"""03a - Vérifie l'imputation des domaines du loader : déclencheurs par sous-chaîne vs mot entier.
Relancer : PYTHONPATH=src .venv/bin/python reports/agents/data_audit_scripts/03a_domain_check.py
"""
import collections
import json
import re
from pathlib import Path

from common import OUT, ROOT
from rag_sfar.ingestion.loader import DOMAIN_KEYWORDS, clean_chandra_markdown

rows = json.loads((OUT / 'loader_metadata.json').read_text())
substr_only = collections.Counter()
examples = []
per_doc_bad = 0
for r in rows:
    text = clean_chandra_markdown(Path(r['md_path']).read_text(encoding='utf-8', errors='ignore'))
    blob = f"{r['title']} {text[:2000][:1500]}".lower()
    bad_here = False
    for dom, kws in DOMAIN_KEYWORDS.items():
        hits = [kw for kw in kws if kw in blob]
        if not hits:
            continue
        whole = [kw for kw in hits if re.search(r'(?<![a-zà-ÿ])' + re.escape(kw) + r'(?![a-zà-ÿ])', blob) or len(kw) > 6]
        if not whole:
            substr_only[dom] += 1
            bad_here = True
            if len(examples) < 25:
                m = re.search(re.escape(hits[0]), blob)
                examples.append((r['title'][:60], dom, hits[:3], blob[max(0, m.start() - 25): m.end() + 25].replace('\n', ' ')))
    per_doc_bad += bad_here
print('docs avec au moins un domaine déclenché uniquement par sous-chaîne :', per_doc_bad, '/', len(rows))
print(substr_only.most_common())
for e in examples:
    print(e)
