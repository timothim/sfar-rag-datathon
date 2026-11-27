# LOCKBOX — empreintes des jeux de test

Ces fichiers ne doivent pas être modifiés après leur mise sous coffre-fort, ni évalués pendant la mise au point.
Vérification automatique : `pytest tests/test_lockbox.py`. Toute modification exige l'accord de l'utilisateur
et une nouvelle entrée datée ci-dessous expliquant pourquoi.

| Fichier | Questions | SHA-256 |
|---|---:|---|
| `eval/splits/abp171/test.jsonl` | 69 | `a1a938fedf552b51be89c1ecbb77d488d38770e2fceb90eda78ffcac7d34836f` |
| `eval/splits/abpe171/test.jsonl` | 69 | `0408ba8c5dc13efcf0de8a5b98379a39df8231650d220ad863d013577b648549` |
| `eval_internal/splits/multirfe_synth/test.jsonl` | 57 | `00c8dc43df34d2e2104d5f213d98b57a59bac3004f17bd3ff092ebc43ed5b24e` |

## Historique

- 2026-11-26 : scellement de `abp171` (split stratifié type × classe de réponse × allergie, quasi-doublons groupés, graine `sfar-2026`, 102 dev / 69 test).
  Limite connue : les 171 questions ont toutes été vues par l'équipe précédente pendant le développement de la fondation (audit d'intégrité, `reports/agents/audit_integrite_evaluation.md`). Le test `abp171` n'est donc « tenu à l'écart » qu'à partir de cette date ; les jeux internes multi-RFE et les RFE jamais vues sont la mesure de généralisation de référence.
  Les réponses de référence (RFE V2.0 2024) ne changent pas en V3.0 2026 (0/171, même audit).
- 2026-11-26 : scellement de `multirfe_synth` (jeu interne synthétique, 151 questions : 94 dev / 57 test). Split « leave-documents-out » : 22 recommandations entières (35 % des documents sources) ne sont qu'en test (tag `unseen_doc`), aucun document commun dev/test ; questions hors corpus réparties 18/9. Générées et vérifiées par des sous-agents Claude Code distincts (voir `eval_internal/README.md`). Les validations médicales futures s'appliqueront par surcouche (`eval_internal/validations_medecins.csv`), sans modifier ce fichier.
- 2026-11-27 : scellement de `abpe171` (benchmark enrichi `benchmark_enrichi_phase1/questions_enriched_draft.jsonl`, 171 questions validées par médecin, référence V3.1 provisoire), converti par `datasets convert-enriched` (normalisation des fragments mise au point sur le dev uniquement, avant scellement). Répartition reprise **à l'identique** de `abp171` par identifiant legacy (102 dev / 69 test) ; les fichiers de test `abp171` et `multirfe_synth` ne sont pas modifiés.
  Limite : ces 171 questions (version historique) ont été vues par les équipes précédentes et par un autre agent (Gemini Neon) qui a réglé le pipeline dessus sans jeu tenu à l'écart (`retest_9_cases`). Le test `abpe171` n'est donc « tenu à l'écart » qu'à partir de cette date et seulement pour nos propres réglages ; il ne mesure pas la généralisation. La conversion du test est mécanique (même code que le dev) ; aucune question test n'a été examinée ni évaluée.
