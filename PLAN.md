# PLAN.md — RAG-SFAR (tableau de bord de la session)

Mission : `PROMPT_CLAUDE_CODE.md` §1. Règles actives : `CLAUDE.md`. Relire ce fichier après chaque compaction.

## Phase en cours
Phase 3 (boucle d'amélioration). Référence courante : C9 (BM25+dense+RRF+reranker+routeur), générateur Qwen2.5-7B local. Voir JOURNAL.md.

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
| Ancien C8, génération 7B, juge Haiku | multirfe dev | correct 68,1 % [59–78], erreurs graves 16,0 % (8 abstentions manquées) | référence « avant » multi-RFE |
| Ancien C8 → C9 détaillé, génération 7B, juge | multirfe dev | correct −1,1 n.s. ; **graves 16,0 → 5,3 % (−10,6 [−18,1 ; −4,3])** | **C9 adopté** |
| idem | abp dev | correct 80,4 → 76,5 (n.s.) ; graves 5,9 = | cohérent (sur-ajustement retiré) |
| Prompt concis vs détaillé (C9) | abp dev | correct +4,9 n.s., graves −2,0, latence −2,7 s | prometteur |
| idem | multirfe dev | correct +2,1 n.s., latence −4,8 s, mais abstention 83 → 61 % | à corriger (abstention) avant adoption |
| Générateur Sonnet vs 7B, mêmes contextes C9 (6 passages) | multirfe dev | correct 69,1 → 90,4 % (+21,3 [+12,8 ; +30,9]), graves 7,4 → 0 % | générateur = goulot principal ; viser un modèle ouvert plus fort sur LibreDataHub |
| Embedder Qwen3-Embedding-0.6B vs e5-small (C9) | les deux dev | toutes différences n.s. (doc hit −2,6 tendance) | non adopté ; tester en dense seul |
| Ancien C0 vs ancien C8, génération 7B mode générique, juge Haiku (κ 0,88) | abp171 dev | correct 64,7 → 80,4 % (+15,7 [+2,9 ; +27,5]) ; erreurs graves 14,7 → 5,9 % | référence « avant » pour la génération |
| Reranker bge-reranker-v2-m3 vs mmarco (C9) | multirfe dev | passage hit +3,9 [−1,3 ; +9,2], MRR +0,059 n.s. ; latence ×30 sur Mac | candidat GPU, non adopté localement |

## Décisions
- 2026-11-26 : pas d'API (clé invalide) → jeu interne généré/vérifié par sous-agents Claude Code ; juge : backend local d'abord.
- 2026-11-26 : `abp171` scellé (102 dev / 69 test). Réponses V2.0 = V3.0 (0/171 changent).
- 2026-11-26 : les chiffres du README ne mesurent pas la généralisation (voir reports/01_audit.md). Nouvelle référence = C8 générique, mesuré contre l'ancien C8 (commit fa0426a).

## Coûts API
Ledger : `reports/cost_ledger.csv`. Cumul : 0 $.
