# Évaluation — suite `abp171`, split `dev`

Date : 2026-11-26T18:24:03. Questions : 102. k = 8. Générateur : claude-sonnet-5-5 (Claude Code subagent, prompts captured from the engine, variant ctx6).

Valeurs : moyenne en %, IC bootstrap 95 % entre crochets.

| Config | Doc hit@k | Doc MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Fausse abstention | Sourcé |
|---|---:|---:|---:|---:|---:|---:|---:|
| `C9_simple_hybrid_rerank+claude-sonnet-5-5` | 0.0 [0–0] | 0.000 [0.00–0.00] | 0.0 [0–0] | 97.6 [94–100] | 95.1 [90–99] | 6.9 [2–12] | 96.1 [92–99] |

### `C9_simple_hybrid_rerank+claude-sonnet-5-5` — par tag

| Groupe | n | Doc hit@k | Doc MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Fausse abstention | Sourcé |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| allergy | 5 | 0.0 [0–0] | 0.000 [0.00–0.00] | 0.0 [0–0] | 100.0 [100–100] | 60.0 [20–100] | 60.0 [20–100] | 80.0 [40–100] |
| no_abp | 37 | 0.0 [0–0] | 0.000 [0.00–0.00] | 0.0 [0–0] | 100.0 [100–100] | 97.3 [92–100] | 2.7 [0–8] | 97.3 [92–100] |

## Juge LLM (claude-haiku-5-5 subagent (κ=0.88))

| Config | Correct (juge) | Correct ou partiel | Erreurs graves | Types |
|---|---:|---:|---:|---|
| `C9_simple_hybrid_rerank+claude-sonnet-5-5` | 91.2 [85–96] | 94.1 [89–98] | 2.0 [0–5] | {'wrong_drug': 2} |
