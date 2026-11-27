# Évaluation — suite `multirfe_synth`, split `test`

Date : 2026-11-27T08:46:13. Questions : 57. k = 0. Générateur : claude-sonnet-5-5 (stand-in agents, blind export v6_c10n_test).

Valeurs : moyenne en %, IC bootstrap 95 % entre crochets.

| Config | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Abstention correcte | Fausse abstention | Sourcé | Latence ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c10notes_v6|production:wide|claude-sonnet-5-5` | 97.9 [94–100] | 0.865 [0.78–0.94] | 97.9 [94–100] | 0.790 [0.69–0.88] | 0.0 [0–0] | 100.0 [100–100] | 79.2 [67–90] | 100.0 [100–100] | 6.2 [0–15] | 84.2 [74–93] | 5 |

### `c10notes_v6|production:wide|claude-sonnet-5-5` — par tag

| Groupe | n | Doc hit@k | Doc MRR | Passage hit@k | Passage MRR | Intrusion obsolète | Termes réponse (laxiste) | Exactitude | Abstention correcte | Fausse abstention | Sourcé |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| abstention | 9 | — | — | — | — | — | — | — | 100.0 [100–100] | — | 0.0 [0–0] |
| contraindication | 5 | 100.0 [100–100] | 0.822 [0.47–1.00] | 100.0 [100–100] | 0.822 [0.47–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| dosage | 6 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.867 [0.60–1.00] | 0.0 [0–0] | 100.0 [100–100] | 83.3 [50–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| drug_choice | 11 | 90.9 [73–100] | 0.760 [0.51–1.00] | 90.9 [73–100] | 0.760 [0.51–1.00] | 0.0 [0–0] | 100.0 [100–100] | 90.9 [73–100] | — | 18.2 [0–45] | 100.0 [100–100] |
| edition_diff | 1 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 1.000 [1.00–1.00] | — | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| emergency | 12 | 100.0 [100–100] | 0.854 [0.64–1.00] | 100.0 [100–100] | 0.757 [0.54–0.94] | 0.0 [0–0] | 100.0 [100–100] | 91.7 [75–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| icu | 19 | 100.0 [100–100] | 0.918 [0.79–1.00] | 100.0 [100–100] | 0.850 [0.71–0.97] | 0.0 [0–0] | 100.0 [100–100] | 84.2 [63–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| other | 16 | 93.8 [81–100] | 0.818 [0.64–0.96] | 93.8 [81–100] | 0.768 [0.58–0.93] | 0.0 [0–0] | 100.0 [100–100] | 75.0 [50–94] | — | 6.2 [0–19] | 100.0 [100–100] |
| pediatric | 8 | 100.0 [100–100] | 0.830 [0.57–1.00] | 100.0 [100–100] | 0.830 [0.57–1.00] | 0.0 [0–0] | 100.0 [100–100] | 75.0 [38–100] | — | 12.5 [0–38] | 100.0 [100–100] |
| reco | 22 | 100.0 [100–100] | 0.907 [0.79–1.00] | 100.0 [100–100] | 0.838 [0.72–0.95] | 0.0 [0–0] | 100.0 [100–100] | 86.4 [73–100] | — | 4.5 [0–14] | 100.0 [100–100] |
| table | 9 | 100.0 [100–100] | 0.831 [0.61–1.00] | 100.0 [100–100] | 0.686 [0.45–0.91] | 0.0 [0–0] | 100.0 [100–100] | 66.7 [33–89] | — | 11.1 [0–33] | 100.0 [100–100] |
| threshold | 7 | 100.0 [100–100] | 0.687 [0.41–0.90] | 100.0 [100–100] | 0.573 [0.32–0.88] | 0.0 [0–0] | 100.0 [100–100] | 57.1 [14–86] | — | 0.0 [0–0] | 100.0 [100–100] |
| timing | 2 | 100.0 [100–100] | 1.000 [1.00–1.00] | 100.0 [100–100] | 0.750 [0.50–1.00] | 0.0 [0–0] | 100.0 [100–100] | 100.0 [100–100] | — | 0.0 [0–0] | 100.0 [100–100] |
| unseen_doc | 48 | 97.9 [94–100] | 0.865 [0.78–0.94] | 97.9 [94–100] | 0.790 [0.69–0.88] | 0.0 [0–0] | 100.0 [100–100] | 79.2 [67–90] | — | 6.2 [0–15] | 100.0 [100–100] |

## Courbes (rang dans le contexte retourné)

| Config | Courbe | k=1 | k=3 | k=5 | k=8 | k=12 | k=16 | k=20 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `c10notes_v6|production:wide|claude-sonnet-5-5` | Passage hit@k | 68.8 | 87.5 | 93.8 | 95.8 | 97.9 | 97.9 | 97.9 |
| `c10notes_v6|production:wide|claude-sonnet-5-5` | Doc hit@k | 81.2 | 91.7 | 93.8 | 95.8 | 97.9 | 97.9 | 97.9 |

## Juge LLM — grille v4, 2 passes à l'aveugle (claude-haiku (subagents), lot `blind_final`)

Combinaison déclarée d'avance : headline: correct/behaviour accepted only if every pass agrees; serious error if any pass reports one; '_any' = either judge (good outcomes), '_all' = every judge (bad outcomes). Verdicts manquants ou invalides : 0. IC exacts de Clopper-Pearson pour les taux (0/1), bootstrap pour le taux de faits.

| Config | Correct (tous) | Correct (un juge) | Correct ou partiel | Erreur grave (un juge) | Erreur grave (tous) | Comportement strict | Comportement élargi | Comportement au cas par cas | Abstention à tort | Abstention manquante | Fidèle aux extraits |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `c10notes_v6|production:wide|claude-sonnet-5-5` | 91.2 [80.7–97.1] (52/57) | 93.0 [83.0–98.1] (53/57) | 98.2 [90.6–100.0] (56/57) | 0.0 [0.0–6.3] (0/57) | 0.0 [0.0–6.3] (0/57) | — | — | — | 0.0 [0.0–7.4] (0/48) | 0.0 [0.0–33.6] (0/9) | 100.0 [91.8–100.0] (43/43) |

Par juge :

| Config | Juge | Correct | Correct ou partiel | Erreur grave | Comportement strict | Types d'erreurs graves |
|---|---|---|---|---|---|---|
| `c10notes_v6|production:wide|claude-sonnet-5-5` | a | 93.0 [83.0–98.1] (53/57) | 100.0 [93.7–100.0] (57/57) | 0.0 [0.0–6.3] (0/57) | — | {} |
| `c10notes_v6|production:wide|claude-sonnet-5-5` | b | 91.2 [80.7–97.1] (52/57) | 98.2 [90.6–100.0] (56/57) | 0.0 [0.0–6.3] (0/57) | — | {} |

Accord entre juges (`c10notes_v6|production:wide|claude-sonnet-5-5`) :

| Juges | n | Correctness (3 classes) : accord brut / κ | Erreur grave : accord brut / κ | Comportement : accord brut / κ |
|---|---:|---|---|---|
| a-b | 57 | 96.5 % / 0.76 (n=57) | 100.0 % / 1.00 (n=57) | — |
