Annexes de la revue R1 (scripts en lecture seule sur `data/` et `index/`, CPU uniquement, DEV uniquement). Lancer depuis la racine du dépôt avec `HF_HUB_OFFLINE=1 .venv/bin/python reports/agents/R1_annexes/<script>.py`.

- `recompute_b2_diffs.py` → `recompute_b2_diffs.tsv` : différences appariées B2 recalculées à partir des lignes par question.
- `editions_audit.py` → `editions_audit.txt` : effets et quasi-déclenchements des deux règles d'éditions.
- `table_fidelity.py`, `table_words.py` → `table_fidelity_*.txt`, `table_words_*.txt` : couverture des jetons cliniques et des mots des cellules sources.
- `table_sample.py` → `table_sample.txt` : 42 tableaux (source vs chunks) pour la relecture manuelle.
- `mermaid_check.py` → `mermaid_check.txt` : arêtes et contenus perdus par la réécriture des organigrammes.
- `population_sample.py` → `population_sample.txt` : échantillon relu des étiquettes de population.
- `rule_firing.py` → `rule_firing.json`, `full_width_examples.txt` : nombre de documents et d'événements par règle.
- `carry_check.py` → `carry_check.txt` : reprises de clé de ligne après saut de page.
- `text_regressions.py` → `text_regressions.txt` : tableaux aplatis, unités micro corrompues, doses perdues.
