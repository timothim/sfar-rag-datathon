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

## Décisions
- 2026-11-26 : pas d'API (clé invalide) → jeu interne généré/vérifié par sous-agents Claude Code ; juge : backend local d'abord.
- 2026-11-26 : `abp171` scellé (102 dev / 69 test). Réponses V2.0 = V3.0 (0/171 changent).
- 2026-11-26 : les chiffres du README ne mesurent pas la généralisation (voir reports/01_audit.md). Nouvelle référence = C8 générique, mesuré contre l'ancien C8 (commit fa0426a).

## Coûts API
Ledger : `reports/cost_ledger.csv`. Cumul : 0 $.
