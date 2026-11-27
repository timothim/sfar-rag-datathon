# Évaluation — suite `multirfe_synth`, split `dev`

Date : 2026-11-27T06:26:26. Questions : 30. k = 0. Générateur : mlx:qwen3.5-9b-4bit-nothink.

Valeurs : moyenne en %, IC bootstrap 95 % entre crochets.

| Config | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Abstention correcte | Fausse abstention | Sourcé | Latence ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000|legacy|clinical_concise` | 100.0 [100–100] | 0.904 [0.79–1.00] | 100.0 [100–100] | 0.669 [0.52–0.82] | 0.0 [0–0] | 100.0 [100–100] | 75.0 [58–92] | 100.0 [100–100] | 0.0 [0–0] | 80.0 [63–93] | 34348 |

### `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000|legacy|clinical_concise` — par tag

| Groupe | n | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Abstention correcte | Fausse abstention | Sourcé |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| abstention | 6 | — | — | — | — | — | — | — | 100.0 [100–100] | — | 0.0 [0–0] |
| dosage | 2 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.667 [0.33–1.00] | 0.0 [0–0] | 100.0 [100–100] | 50.0 [0–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| drug_choice | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| edition_diff | 3 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.722 [0.17–1.00] | — | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| emergency | 5 | 100.0 [100–100] | 0.822 [0.47–1.00] | 100.0 [100–100] | 0.809 [0.43–1.00] | 0.0 [0–0] | 100.0 [100–100] | 60.0 [20–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| icu | 7 | 100.0 [100–100] | 0.873 [0.62–1.00] | 100.0 [100–100] | 0.445 [0.18–0.74] | 0.0 [0–0] | 100.0 [100–100] | 42.9 [14–86] | — | 0.0 [0–0] | 100.0 [100–100] |
| obstetric | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| other | 7 | 100.0 [100–100] | 0.766 [0.51–1.00] | 100.0 [100–100] | 0.497 [0.22–0.86] | 0.0 [0–0] | 100.0 [100–100] | 71.4 [43–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| pediatric | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 0.0 [0–0] | — | 0.0 [0–0] | 100.0 [100–100] |
| reco | 10 | 100.0 [100–100] | 0.933 [0.80–1.00] | 100.0 [100–100] | 0.798 [0.58–1.00] | 0.0 [0–0] | 100.0 [100–100] | 80.0 [50–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| table | 4 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.611 [0.22–1.00] | 0.0 [0–0] | 100.0 [100–100] | 50.0 [0–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| threshold | 4 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.559 [0.12–1.00] | 0.0 [0–0] | 100.0 [100–100] | 25.0 [0–75] | — | 0.0 [0–0] | 100.0 [100–100] |
| timing | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |

## Courbes (rang dans le contexte retourné)

| Config | Courbe | k=1 | k=3 | k=5 | k=8 | k=12 | k=16 | k=20 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000|legacy|clinical_concise` | Passage hit@k | 58.3 | 70.8 | 70.8 | 91.7 | 95.8 | 95.8 | 95.8 |
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000|legacy|clinical_concise` | Doc hit@k | 87.5 | 91.7 | 95.8 | 95.8 | 100.0 | 100.0 | 100.0 |

## Juge LLM (haiku (rubric v2))

| Config | Correct (juge) | Correct ou partiel | Erreurs graves | Types |
|---|---:|---:|---:|---|
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000|legacy|clinical_concise` | 86.7 [73–97] | 93.3 [83–100] | 6.7 [0–17] | {'wrong_conduct': 2} |
