# Évaluation — suite `multirfe_synth`, split `dev`

Date : 2026-11-27T08:01:47. Questions : 30. k = 0. Générateur : claude-sonnet-5-5 (Claude Code subagent, prompts captured by gen_replay).

Valeurs : moyenne en %, IC bootstrap 95 % entre crochets.

| Config | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Abstention correcte | Fausse abstention | Sourcé | Latence ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c10notes_v6|wide|claude-sonnet-5-5` | 95.8 [88–100] | 0.868 [0.75–0.96] | 91.7 [79–100] | 0.823 [0.69–0.94] | 0.0 [0–0] | 91.7 [79–100] | 75.0 [54–92] | 100.0 [100–100] | 4.2 [0–12] | 76.7 [60–90] | 2 |

### `c10notes_v6|wide|claude-sonnet-5-5` — par tag

| Groupe | n | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Abstention correcte | Fausse abstention | Sourcé |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| abstention | 6 | — | — | — | — | — | — | — | 100.0 [100–100] | — | 0.0 [0–0] |
| dosage | 2 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 100.0 [100–100] | 50.0 [0–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| drug_choice | 1 | 0.0 [0–0] | 0.000 [0.00–0.00] | 0.0 [0–0] | 0.000 [0.00–0.00] | 0.0 [0–0] | 0.0 [0–0] | 0.0 [0–0] | — | 100.0 [100–100] | 0.0 [0–0] |
| edition_diff | 3 | 100.0 [100–100] | 0.833 [0.50–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | — | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| emergency | 5 | 100.0 [100–100] | 0.767 [0.50–1.00] | 80.0 [40–100] | 0.650 [0.25–1.00] | 0.0 [0–0] | 80.0 [40–100] | 60.0 [20–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| icu | 7 | 85.7 [57–100] | 0.762 [0.43–1.00] | 85.7 [57–100] | 0.679 [0.36–0.93] | 0.0 [0–0] | 85.7 [57–100] | 57.1 [29–86] | — | 14.3 [0–43] | 85.7 [57–100] |
| obstetric | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.500 [0.50–0.50] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| other | 7 | 100.0 [100–100] | 0.762 [0.55–0.93] | 85.7 [57–100] | 0.679 [0.39–0.93] | 0.0 [0–0] | 100.0 [100–100] | 85.7 [57–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| pediatric | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 0.0 [0–0] | 0.0 [0–0] | — | 0.0 [0–0] | 100.0 [100–100] |
| reco | 10 | 90.0 [70–100] | 0.900 [0.70–1.00] | 90.0 [70–100] | 0.850 [0.65–1.00] | 0.0 [0–0] | 80.0 [50–100] | 70.0 [40–100] | — | 10.0 [0–30] | 90.0 [70–100] |
| table | 4 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.875 [0.62–1.00] | 0.0 [0–0] | 100.0 [100–100] | 50.0 [0–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| threshold | 4 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | 0.0 [0–0] | 75.0 [25–100] | 50.0 [0–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| timing | 1 | 0.0 [0–0] | 0.000 [0.00–0.00] | 0.0 [0–0] | 0.000 [0.00–0.00] | 0.0 [0–0] | 0.0 [0–0] | 0.0 [0–0] | — | 100.0 [100–100] | 0.0 [0–0] |

## Courbes (rang dans le contexte retourné)

| Config | Courbe | k=1 | k=3 | k=5 | k=8 | k=12 | k=16 | k=20 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `c10notes_v6|wide|claude-sonnet-5-5` | Passage hit@k | 75.0 | 87.5 | 91.7 | 91.7 | 91.7 | 91.7 | 91.7 |
| `c10notes_v6|wide|claude-sonnet-5-5` | Doc hit@k | 79.2 | 95.8 | 95.8 | 95.8 | 95.8 | 95.8 | 95.8 |

## Juge LLM — grille v4, 2 passes à l'aveugle (claude-haiku (subagents), lot `blind_final`)

Combinaison déclarée d'avance : headline: correct/behaviour accepted only if every pass agrees; serious error if any pass reports one; '_any' = either judge (good outcomes), '_all' = every judge (bad outcomes). Verdicts manquants ou invalides : 0. IC exacts de Clopper-Pearson pour les taux (0/1), bootstrap pour le taux de faits.

| Config | Correct (tous) | Correct (un juge) | Correct ou partiel | Erreur grave (un juge) | Erreur grave (tous) | Comportement strict | Comportement élargi | Comportement au cas par cas | Abstention à tort | Abstention manquante | Fidèle aux extraits |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `c10notes_v6|wide|claude-sonnet-5-5` | 86.7 [69.3–96.2] (26/30) | 90.0 [73.5–97.9] (27/30) | 96.7 [82.8–99.9] (29/30) | 0.0 [0.0–11.6] (0/30) | 0.0 [0.0–11.6] (0/30) | — | — | — | 4.2 [0.1–21.1] (1/24) | 0.0 [0.0–45.9] (0/6) | 100.0 [83.9–100.0] (21/21) |

Par juge :

| Config | Juge | Correct | Correct ou partiel | Erreur grave | Comportement strict | Types d'erreurs graves |
|---|---|---|---|---|---|---|
| `c10notes_v6|wide|claude-sonnet-5-5` | a | 90.0 [73.5–97.9] (27/30) | 96.7 [82.8–99.9] (29/30) | 0.0 [0.0–11.6] (0/30) | — | {} |
| `c10notes_v6|wide|claude-sonnet-5-5` | b | 86.7 [69.3–96.2] (26/30) | 96.7 [82.8–99.9] (29/30) | 0.0 [0.0–11.6] (0/30) | — | {} |

Accord entre juges (`c10notes_v6|wide|claude-sonnet-5-5`) :

| Juges | n | Correctness (3 classes) : accord brut / κ | Erreur grave : accord brut / κ | Comportement : accord brut / κ |
|---|---:|---|---|---|
| a-b | 30 | 96.7 % / 0.84 (n=30) | 100.0 % / 1.00 (n=30) | — |
