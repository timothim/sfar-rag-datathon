# Évaluation — suite `multirfe_synth`, split `dev`

Date : 2026-11-27T07:29:11. Questions : 30. k = 0. Générateur : mlx:qwen3.5-9b-4bit-nothink.

Valeurs : moyenne en %, IC bootstrap 95 % entre crochets.

| Config | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Abstention correcte | Fausse abstention | Sourcé | Latence ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000|wide+max_tokens=700|clinical_production` | 100.0 [100–100] | 0.931 [0.85–1.00] | 100.0 [100–100] | 0.854 [0.74–0.95] | 0.0 [0–0] | 100.0 [100–100] | 66.7 [46–83] | 83.3 [50–100] | 0.0 [0–0] | 83.3 [70–97] | 32160 |

### `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000|wide+max_tokens=700|clinical_production` — par tag

| Groupe | n | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Abstention correcte | Fausse abstention | Sourcé |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| abstention | 6 | — | — | — | — | — | — | — | 83.3 [50–100] | — | 16.7 [0–50] |
| dosage | 2 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.750 [0.50–1.00] | 0.0 [0–0] | 100.0 [100–100] | 50.0 [0–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| drug_choice | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| edition_diff | 3 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.778 [0.33–1.00] | — | 100.0 [100–100] | 66.7 [0–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| emergency | 5 | 100.0 [100–100] | 0.867 [0.60–1.00] | 100.0 [100–100] | 0.867 [0.60–1.00] | 0.0 [0–0] | 100.0 [100–100] | 60.0 [20–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| icu | 7 | 100.0 [100–100] | 0.905 [0.71–1.00] | 100.0 [100–100] | 0.833 [0.62–1.00] | 0.0 [0–0] | 100.0 [100–100] | 42.9 [14–71] | — | 0.0 [0–0] | 100.0 [100–100] |
| obstetric | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| other | 7 | 100.0 [100–100] | 0.833 [0.64–1.00] | 100.0 [100–100] | 0.833 [0.64–1.00] | 0.0 [0–0] | 100.0 [100–100] | 85.7 [57–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| pediatric | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 0.0 [0–0] | — | 0.0 [0–0] | 100.0 [100–100] |
| reco | 10 | 100.0 [100–100] | 0.950 [0.85–1.00] | 100.0 [100–100] | 0.883 [0.72–1.00] | 0.0 [0–0] | 100.0 [100–100] | 70.0 [40–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| table | 4 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.875 [0.62–1.00] | 0.0 [0–0] | 100.0 [100–100] | 25.0 [0–75] | — | 0.0 [0–0] | 100.0 [100–100] |
| threshold | 4 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 25.0 [0–75] | — | 0.0 [0–0] | 100.0 [100–100] |
| timing | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |

## Courbes (rang dans le contexte retourné)

| Config | Courbe | k=1 | k=3 | k=5 | k=8 | k=12 | k=16 | k=20 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000|wide+max_tokens=700|clinical_production` | Passage hit@k | 75.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000|wide+max_tokens=700|clinical_production` | Doc hit@k | 87.5 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |

## Juge LLM (haiku (rubric v2))

| Config | Correct (juge) | Correct ou partiel | Erreurs graves | Types |
|---|---:|---:|---:|---|
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000|wide+max_tokens=700|clinical_production` | 76.7 [60–90] | 83.3 [67–97] | 13.3 [3–27] | {'wrong_conduct': 2, 'wrong_dose': 1, 'missing_abstention': 1} |
