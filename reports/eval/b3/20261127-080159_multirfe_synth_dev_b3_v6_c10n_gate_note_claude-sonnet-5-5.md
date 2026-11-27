# Évaluation — suite `multirfe_synth`, split `dev`

Date : 2026-11-27T08:01:59. Questions : 9. k = 0. Générateur : claude-sonnet-5-5 (Claude Code subagent, prompts captured by gen_replay).

Valeurs : moyenne en %, IC bootstrap 95 % entre crochets.

| Config | Abstention correcte | Sourcé | Latence ms |
|---|---:|---:|---:|
| `c10notes_v6|wide+coverage_gate=note|claude-sonnet-5-5` | 100.0 [100–100] | 0.0 [0–0] | 2 |

### `c10notes_v6|wide+coverage_gate=note|claude-sonnet-5-5` — par tag

| Groupe | n | Abstention correcte | Sourcé |
|---|---:|---:|---:|
| abstention | 9 | 100.0 [100–100] | 0.0 [0–0] |

## Juge LLM (haiku (rubric v3))

| Config | Correct (juge) | Correct ou partiel | Erreurs graves | Types |
|---|---:|---:|---:|---|
| `c10notes_v6|wide+coverage_gate=note|claude-sonnet-5-5` | 100.0 [100–100] | 100.0 [100–100] | 0.0 [0–0] | {} |
