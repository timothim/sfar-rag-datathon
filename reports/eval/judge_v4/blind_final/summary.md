# Jugement à l'aveugle `blind_final` — grille v4

370 réponses, passes a, b (claude-haiku (subagents)). Verdicts manquants ou invalides : **0**. Corrections de cohérence v4 (ne peuvent que baisser correctness) : {'abstention on a covered question': 1}.

Combinaison déclarée d'avance : correct et comportement accepté seulement si tous les juges l'accordent ; erreur grave si un juge en signale une. « un juge » / « tous » donnent l'écart. IC 95 % exacts (Clopper-Pearson).

| Rapport | Split | n | Correct (tous) | Correct (un juge) | Correct ou partiel (tous) | Erreur grave (un juge) | Erreur grave (tous) | Comportement strict | Comportement élargi | Abstention à tort | Abstention manquante | Échec technique |
|---|---|---:|---|---|---|---|---|---|---|---|---|---|
| 20261127-080147_multirfe_synth_dev_b3_v6_c10n_iter_claude-sonnet-5-5 | dev | 30 | 86.7 [69.3–96.2] (26/30) | 90.0 [73.5–97.9] (27/30) | 96.7 [82.8–99.9] (29/30) | 0.0 [0.0–11.6] (0/30) | 0.0 [0.0–11.6] (0/30) | — | — | 4.2 [0.1–21.1] (1/24) | 0.0 [0.0–45.9] (0/6) | 0.0 [0.0–11.6] (0/30) |
| 20261127-080147_abpe171_dev_b3_v6_c10n_iter_claude-sonnet-5-5 | dev | 30 | 73.3 [54.1–87.7] (22/30) | 80.0 [61.4–92.3] (24/30) | 93.3 [77.9–99.2] (28/30) | 3.3 [0.1–17.2] (1/30) | 0.0 [0.0–11.6] (0/30) | 93.3 [77.9–99.2] (28/30) | 93.3 [77.9–99.2] (28/30) | 0.0 [0.0–11.6] (0/30) | — | 0.0 [0.0–11.6] (0/30) |
| 20261127-081101_multirfe_synth_dev_b3_v6_c10n_confirm_claude-sonnet-5-5 | dev | 64 | 98.4 [91.6–100.0] (63/64) | 98.4 [91.6–100.0] (63/64) | 100.0 [94.4–100.0] (64/64) | 0.0 [0.0–5.6] (0/64) | 0.0 [0.0–5.6] (0/64) | — | — | 0.0 [0.0–6.8] (0/52) | 0.0 [0.0–26.5] (0/12) | 0.0 [0.0–5.6] (0/64) |
| 20261127-084613_multirfe_synth_test_b3_v6_c10n_test_claude-sonnet-5-5 | test | 57 | 91.2 [80.7–97.1] (52/57) | 93.0 [83.0–98.1] (53/57) | 98.2 [90.6–100.0] (56/57) | 0.0 [0.0–6.3] (0/57) | 0.0 [0.0–6.3] (0/57) | — | — | 0.0 [0.0–7.4] (0/48) | 0.0 [0.0–33.6] (0/9) | 0.0 [0.0–6.3] (0/57) |
| 20261127-084611_abpe171_test_b3_v6_c10n_test_claude-sonnet-5-5 | test | 69 | 53.6 [41.2–65.7] (37/69) | 62.3 [49.8–73.7] (43/69) | 97.1 [89.9–99.6] (67/69) | 5.8 [1.6–14.2] (4/69) | 2.9 [0.4–10.1] (2/69) | 92.8 [83.9–97.6] (64/69) | 92.8 [83.9–97.6] (64/69) | 1.4 [0.0–7.8] (1/69) | — | 0.0 [0.0–5.2] (0/69) |
| 20261127-081059_abpe171_dev_b3_v6_c10n_confirm_claude-sonnet-5-5 | dev | 72 | 73.6 [61.9–83.3] (53/72) | 77.8 [66.4–86.7] (56/72) | 97.2 [90.3–99.7] (70/72) | 2.8 [0.3–9.7] (2/72) | 2.8 [0.3–9.7] (2/72) | 95.8 [88.3–99.1] (69/72) | 95.8 [88.3–99.1] (69/72) | 1.4 [0.0–7.5] (1/72) | — | 0.0 [0.0–5.0] (0/72) |
| 20261127-084617_genprobe_dev_b3_v6_c10n_genprobe_claude-sonnet-5-5 | dev | 48 | 75.0 [60.4–86.4] (36/48) | 77.1 [62.7–88.0] (37/48) | 93.8 [82.8–98.7] (45/48) | 6.2 [1.3–17.2] (3/48) | 4.2 [0.5–14.3] (2/48) | — | — | 4.2 [0.5–14.3] (2/48) | — | 0.0 [0.0–7.4] (0/48) |

## Accord entre juges (toutes réponses)

| Juges | n | Correctness (3 classes) : accord brut / κ | Erreur grave : accord brut / κ | Comportement : accord brut / κ |
|---|---:|---|---|---|
| a-b | 370 | 94.3 % / 0.83 (n=370) | 98.9 % / 0.74 (n=370) | 100.0 % / 1.00 (n=169) |
