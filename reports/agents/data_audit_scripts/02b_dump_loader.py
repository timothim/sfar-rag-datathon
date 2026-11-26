"""02b - Exécute le loader du projet (lecture seule) et sauvegarde les métadonnées calculées.
Relancer : .venv/bin/python reports/agents/data_audit_scripts/02b_dump_loader.py
Sortie   : out/loader_metadata.json
"""
import collections
import json
import time
from pathlib import Path

from common import CORPUS, OUT
from rag_sfar.ingestion.loader import load_sfar_corpus

t = time.time()
docs = load_sfar_corpus(CORPUS)
FIELDS = ['doc_id', 'title', 'filename', 'md_path', 'raw_year', 'effective_year', 'year_was_imputed', 'version_label',
          'language', 'doc_role', 'topic_lineage', 'is_latest_edition', 'superseded_by', 'superseded_by_year', 'domains',
          'raw_subdomain', 'subdomain_was_imputed', 'population_scope', 'setting_scope', 'is_active',
          'reference_char_ratio', 'table_count', 'char_count', 'doc_type']
rows = [{k: getattr(d.metadata, k, None) for k in FIELDS} for d in docs]
(OUT / 'loader_metadata.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str))
print(len(rows), 'docs chargés en', round(time.time() - t, 1), 's')
print('langue', collections.Counter(r['language'] for r in rows))
print('doc_role', collections.Counter(r['doc_role'] for r in rows))
print('superseded', sum(1 for r in rows if not r['is_latest_edition']))
print('docs avec lignée', sum(1 for r in rows if r['topic_lineage']), 'lignées', len({r['topic_lineage'] for r in rows if r['topic_lineage']}))
print('année imputée', sum(1 for r in rows if r['year_was_imputed']), '| domaine imputé', sum(1 for r in rows if r['subdomain_was_imputed']),
      '| raw_subdomain None', sum(1 for r in rows if not r['raw_subdomain']))
print('domaines=[Général]', sum(1 for r in rows if r['domains'] == ['Général']))
print('nb domaines par doc', sorted(collections.Counter(len(r['domains']) for r in rows).items()))
print('ref ratio global', round(sum(r['reference_char_ratio'] * r['char_count'] for r in rows) / sum(r['char_count'] for r in rows), 4))
print('tables', sum(r['table_count'] for r in rows))
