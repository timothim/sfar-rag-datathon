# LOCKBOX — empreintes des jeux de test

Ces fichiers ne doivent pas être modifiés après leur mise sous coffre-fort, ni évalués pendant la mise au point.
Vérification automatique : `pytest tests/test_lockbox.py`. Toute modification exige l'accord de l'utilisateur
et une nouvelle entrée datée ci-dessous expliquant pourquoi.

| Fichier | Questions | SHA-256 |
|---|---:|---|
| `eval/splits/abp171/test.jsonl` | 69 | `a1a938fedf552b51be89c1ecbb77d488d38770e2fceb90eda78ffcac7d34836f` |

## Historique

- 2026-11-26 : scellement de `abp171` (split stratifié type × classe de réponse × allergie, quasi-doublons groupés, graine `sfar-2026`, 102 dev / 69 test).
  Limite connue : les 171 questions ont toutes été vues par l'équipe précédente pendant le développement de la fondation (audit d'intégrité, `reports/agents/audit_integrite_evaluation.md`). Le test `abp171` n'est donc « tenu à l'écart » qu'à partir de cette date ; les jeux internes multi-RFE et les RFE jamais vues sont la mesure de généralisation de référence.
  Les réponses de référence (RFE V2.0 2024) ne changent pas en V3.0 2026 (0/171, même audit).
