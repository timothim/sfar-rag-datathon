# Évaluation — suite `abp171`, split `dev`

Date : 2026-11-26T18:24:44. Questions : 102. k = 8. Générateur : claude-sonnet-5-5 (Claude Code subagent, prompts captured from the engine, variant ctx12).

Valeurs : moyenne en %, IC bootstrap 95 % entre crochets.

| Config | Doc hit@k | Doc MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Fausse abstention | Sourcé |
|---|---:|---:|---:|---:|---:|---:|---:|
| `C9_simple_hybrid_rerank-ctx12+claude-sonnet-5-5` | 0.0 [0–0] | 0.000 [0.00–0.00] | 0.0 [0–0] | 98.8 [96–100] | 86.3 [79–92] | 3.9 [1–8] | 98.0 [95–100] |

### `C9_simple_hybrid_rerank-ctx12+claude-sonnet-5-5` — par tag

| Groupe | n | Doc hit@k | Doc MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Fausse abstention | Sourcé |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| allergy | 5 | 0.0 [0–0] | 0.000 [0.00–0.00] | 0.0 [0–0] | 100.0 [100–100] | 80.0 [40–100] | 40.0 [0–80] | 100.0 [100–100] |
| no_abp | 37 | 0.0 [0–0] | 0.000 [0.00–0.00] | 0.0 [0–0] | 100.0 [100–100] | 67.6 [51–81] | 2.7 [0–8] | 97.3 [92–100] |
