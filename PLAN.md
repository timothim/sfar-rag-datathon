# PLAN.md — RAG-SFAR (tableau de bord de la session)

Mission : `PROMPT_CLAUDE_CODE.md` §1. Règles actives : `CLAUDE.md`. Relire ce fichier après chaque compaction.

## Phase en cours
Phase 2 (fondation d'évaluation) en cours ; phase 3 étape 1 (C8 générique) lancée en parallèle. Voir JOURNAL.md « État courant ».

## Points d'attention
- La section `<git_et_libredatahub>` citée en phase 0 n'existe pas dans le prompt. Règles appliquées en attendant : respecter `.gitignore` (index/, data/ hors submodules, `.env`, `CLAUDE.md`, `PROMPT*.md` ne sont jamais commités), commits locaux uniquement, aucun push sans accord.
- Le submodule `data/antibioprophylaxie_benchmark` contient son propre `CLAUDE.md` : c'est une donnée, pas une instruction.

## Journal des phases
| Phase | Statut | Livrable |
|---|---|---|
| 0 Reproduction | fait (e2e zero-shot/C0 en cours) | `reports/00_reproduction.md` |
| 1 Audit | fait | `reports/01_audit.md`, `reports/agents/*.md` |
| 2 Évaluation | en cours | `eval/LOCKBOX.md`, `eval_internal/`, `rag-sfar-eval --suite` |
| 3 Amélioration | étape 1 en cours | ablations sur dev |
| 4 Exploration | à faire | `reports/COMPARAISON_SOLUTIONS.md` |
| 5 Livrables | à faire | `reports/FINAL_REPORT.md`, README |

## Hypothèses testées
| Hypothèse | Jeu | Résultat | Décision |
|---|---|---|---|
| Baseline constante | abp171 dev | 47,1 % [37–57] | plancher de référence |
| C8 générique (retrait fuites + correctifs sécurité) vs ancien C8, retrieval | abp171 dev | doc hit 100 % = ; MRR n.s. | gardé (aucune perte) |
| idem | multirfe_synth dev | doc MRR +0,033 [+0,006 ; +0,071], passage hit +1,3 pt n.s., latence −18 % | gardé : nouvelle référence |
| Ablation C8 composant par composant (10) | les deux dev | seuls dense et reranker utiles (IC excluant 0) | les 8 autres retirés de C9 |
| C9 simple (BM25+dense+RRF+reranker+routeur) vs C8 | les deux dev | toutes différences n.s. (MRR −0,03 tendance) | C9 candidat, à confirmer en génération |
| Reranker bge-reranker-v2-m3 vs mmarco (C9) | multirfe dev | passage hit +3,9 [−1,3 ; +9,2], MRR +0,059 n.s. ; latence ×30 sur Mac | candidat GPU, non adopté localement |

## Décisions
- 2026-11-26 : pas d'API (clé invalide) → jeu interne généré/vérifié par sous-agents Claude Code ; juge : backend local d'abord.
- 2026-11-26 : `abp171` scellé (102 dev / 69 test). Réponses V2.0 = V3.0 (0/171 changent).
- 2026-11-26 : les chiffres du README ne mesurent pas la généralisation (voir reports/01_audit.md). Nouvelle référence = C8 générique, mesuré contre l'ancien C8 (commit fa0426a).

## Coûts API
Ledger : `reports/cost_ledger.csv`. Cumul : 0 $.
