# LOCKBOX — empreintes des jeux de test

Ces fichiers ne doivent pas être modifiés après leur mise sous coffre-fort, ni évalués pendant la mise au point.
Vérification automatique : `pytest tests/test_lockbox.py`. Toute modification exige l'accord de l'utilisateur
et une nouvelle entrée datée ci-dessous expliquant pourquoi.

| Fichier | Questions | SHA-256 |
|---|---:|---|
| `eval/splits/abp171/test.jsonl` | 69 | `a1a938fedf552b51be89c1ecbb77d488d38770e2fceb90eda78ffcac7d34836f` |
| `eval_internal/splits/multirfe_synth/test.jsonl` | 57 | `00c8dc43df34d2e2104d5f213d98b57a59bac3004f17bd3ff092ebc43ed5b24e` |

## Historique

- 2026-11-26 : scellement de `abp171` (split stratifié type × classe de réponse × allergie, quasi-doublons groupés, graine `sfar-2026`, 102 dev / 69 test).
  Limite connue : les 171 questions ont toutes été vues par l'équipe précédente pendant le développement de la fondation (audit d'intégrité, `reports/agents/audit_integrite_evaluation.md`). Le test `abp171` n'est donc « tenu à l'écart » qu'à partir de cette date ; les jeux internes multi-RFE et les RFE jamais vues sont la mesure de généralisation de référence.
  Les réponses de référence (RFE V2.0 2024) ne changent pas en V3.0 2026 (0/171, même audit).
- 2026-11-26 : scellement de `multirfe_synth` (jeu interne synthétique, 151 questions : 94 dev / 57 test). Split « leave-documents-out » : 22 recommandations entières (35 % des documents sources) ne sont qu'en test (tag `unseen_doc`), aucun document commun dev/test ; questions hors corpus réparties 18/9. Générées et vérifiées par des sous-agents Claude Code distincts (voir `eval_internal/README.md`). Les validations médicales futures s'appliqueront par surcouche (`eval_internal/validations_medecins.csv`), sans modifier ce fichier.
