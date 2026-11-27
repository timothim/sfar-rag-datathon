# Évaluation — suite `multirfe_synth`, split `dev`

Date : 2026-11-27T03:50:35. Questions : 12. k = 8. Générateur : mlx:qwen3.5-9b-4bit-nothink.

Valeurs : moyenne en %, IC bootstrap 95 % entre crochets.

| Config | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Fausse abstention | Sourcé | Latence ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `C9_simple_hybrid_rerank` | 91.7 [75–100] | 0.861 [0.67–1.00] | 91.7 [75–100] | 0.753 [0.54–0.94] | 0.0 [0–0] | 100.0 [100–100] | 58.3 [33–83] | 8.3 [0–25] | 91.7 [75–100] | 20040 |
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000` | 91.7 [75–100] | 0.850 [0.63–1.00] | 91.7 [75–100] | 0.735 [0.51–0.93] | 0.0 [0–0] | 91.7 [75–100] | 66.7 [42–92] | 0.0 [0–0] | 100.0 [100–100] | 50938 |

### `C9_simple_hybrid_rerank` — par tag

| Groupe | n | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Fausse abstention | Sourcé |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| contraindication | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | 0.0 [0–0] | 100.0 [100–100] |
| emergency | 3 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 33.3 [0–100] | 0.0 [0–0] | 100.0 [100–100] |
| icu | 4 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.675 [0.35–1.00] | 0.0 [0–0] | 100.0 [100–100] | 75.0 [25–100] | 0.0 [0–0] | 100.0 [100–100] |
| other | 5 | 80.0 [40–100] | 0.667 [0.27–1.00] | 80.0 [40–100] | 0.507 [0.15–0.87] | 0.0 [0–0] | 100.0 [100–100] | 20.0 [0–60] | 20.0 [0–60] | 80.0 [40–100] |
| pediatric | 3 | 100.0 [100–100] | 0.778 [0.33–1.00] | 100.0 [100–100] | 0.611 [0.33–1.00] | 0.0 [0–0] | 100.0 [100–100] | 66.7 [0–100] | 0.0 [0–0] | 100.0 [100–100] |
| reco | 5 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.900 [0.70–1.00] | 0.0 [0–0] | 100.0 [100–100] | 80.0 [40–100] | 0.0 [0–0] | 100.0 [100–100] |
| table | 2 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | 0.0 [0–0] | 100.0 [100–100] |
| threshold | 2 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.600 [0.20–1.00] | 0.0 [0–0] | 100.0 [100–100] | 50.0 [0–100] | 0.0 [0–0] | 100.0 [100–100] |
| timing | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | 0.0 [0–0] | 100.0 [100–100] |

### `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000` — par tag

| Groupe | n | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Fausse abstention | Sourcé |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| contraindication | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | 0.0 [0–0] | 100.0 [100–100] |
| emergency | 3 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | 0.0 [0–0] | 100.0 [100–100] |
| icu | 4 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.656 [0.31–1.00] | 0.0 [0–0] | 100.0 [100–100] | 75.0 [25–100] | 0.0 [0–0] | 100.0 [100–100] |
| other | 5 | 80.0 [40–100] | 0.640 [0.24–1.00] | 80.0 [40–100] | 0.465 [0.09–0.84] | 0.0 [0–0] | 80.0 [40–100] | 40.0 [0–80] | 0.0 [0–0] | 100.0 [100–100] |
| pediatric | 3 | 100.0 [100–100] | 0.733 [0.20–1.00] | 100.0 [100–100] | 0.567 [0.20–1.00] | 0.0 [0–0] | 100.0 [100–100] | 66.7 [0–100] | 0.0 [0–0] | 100.0 [100–100] |
| reco | 5 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.900 [0.70–1.00] | 0.0 [0–0] | 100.0 [100–100] | 80.0 [40–100] | 0.0 [0–0] | 100.0 [100–100] |
| table | 2 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | 0.0 [0–0] | 100.0 [100–100] |
| threshold | 2 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.562 [0.12–1.00] | 0.0 [0–0] | 100.0 [100–100] | 50.0 [0–100] | 0.0 [0–0] | 100.0 [100–100] |
| timing | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | 0.0 [0–0] | 100.0 [100–100] |

## Courbes (rang dans le contexte retourné)

| Config | Courbe | k=1 | k=3 | k=5 | k=8 | k=12 | k=16 | k=20 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `C9_simple_hybrid_rerank` | Passage hit@k | 66.7 | 83.3 | 91.7 | 91.7 | 91.7 | 91.7 | 91.7 |
| `C9_simple_hybrid_rerank` | Doc hit@k | 83.3 | 91.7 | 91.7 | 91.7 | 91.7 | 91.7 | 91.7 |
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000` | Passage hit@k | 66.7 | 75.0 | 83.3 | 91.7 | 91.7 | 91.7 | 100.0 |
| `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000` | Doc hit@k | 83.3 | 83.3 | 91.7 | 91.7 | 91.7 | 91.7 | 100.0 |

## Comparaisons appariées (bootstrap)

| Métrique | A | B | B − A | IC 95 % | P(B ≤ A) |
|---|---|---|---:|---|---:|
| passage_hit | `C9_simple_hybrid_rerank` | `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000` | +0.0 pts | [+0.0 ; +0.0] | 1.000 |
| doc_hit | `C9_simple_hybrid_rerank` | `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000` | +0.0 pts | [+0.0 ; +0.0] | 1.000 |
| correct | `C9_simple_hybrid_rerank` | `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000` | +8.3 pts | [-16.7 ; +33.3] | 0.379 |
| obsolete_intrusion | `C9_simple_hybrid_rerank` | `C9_simple_hybrid_rerank-final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000` | +0.0 pts | [+0.0 ; +0.0] | 1.000 |
