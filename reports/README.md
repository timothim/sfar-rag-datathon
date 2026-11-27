# Rapports

## À lire en premier

| Document | Contenu |
|---|---|
| [FINAL_REPORT.md](FINAL_REPORT.md) | Rapport final : ce qui a été mesuré, résultats, erreurs graves, faiblesses, résultats négatifs, écarts au protocole, limites |
| [COMPARAISON_SOLUTIONS.md](COMPARAISON_SOLUTIONS.md) | Comparaison des solutions mesurées, et ce qui n'a pas été mesuré |
| [DEMO.md](DEMO.md) | Lancer la page de démonstration, brancher un modèle de langage, options de robustesse |
| [MCP_DEPLOIEMENT.md](MCP_DEPLOIEMENT.md) | Lancer et tester le serveur MCP, conteneur, ce qui manque pour un service public |
| [MCP_ARCHITECTURE.md](MCP_ARCHITECTURE.md) | Note d'architecture d'un serveur MCP public des recommandations |

## À faire relire par des médecins

| Document | Contenu |
|---|---|
| [A_VALIDER_MEDECINS.md](A_VALIDER_MEDECINS.md) | Points de sécurité clinique : corrections de doses, statut des éditions, écarts relevés dans les textes |
| [lexique_a_valider_medecins.csv](lexique_a_valider_medecins.csv) | Les 98 entrées du lexique écrit à la main |
| [lexique_cliniciens_a_verifier.csv](lexique_cliniciens_a_verifier.csv) | Les 473 entrées du dictionnaire des cliniciens, avec leur statut (ajouté, déjà présent, écarté) |

## Rapports détaillés (`agents/`)

| Sujet | Rapports |
|---|---|
| Audits de départ | [00_reproduction.md](00_reproduction.md), [01_audit.md](01_audit.md), `agents/audit_donnees.md`, `agents/audit_code_retrieval.md`, `agents/audit_code_ingestion_generation.md`, `agents/audit_integrite_evaluation.md` |
| Ingestion et index | `agents/B2_ingestion.md`, `agents/D1_audit_doses.md`, `agents/K1_audit_structure_corpus.md` |
| Recherche | `agents/B1_retrieval.md`, `agents/X1_liens_structurels.md`, `agents/X2_decomposition.md` |
| Robustesse aux fautes et aux sigles | `agents/Q1_robustesse.md`, `agents/Q2_reformulation.md` |
| Génération | `agents/B3_generation.md`, `agents/A3_generateur_local.md` |
| Évaluation et juge | `agents/J1_juge_v4.md`, `agents/A1_benchmark_enrichi.md`, `agents/V1_benchmark_valide.md`, `agents/E1_genprobe.md`, `agents/E2_genprobe2.md`, `agents/G1_genprobe2_run.md` |
| Revues indépendantes | `agents/R1_revue_ingestion.md`, `agents/R2_revue_retrieval.md`, `agents/R3_revue_finale.md` |

## Résultats bruts

- `eval/` : sorties des évaluations (une par exécution) ; `eval/judge_v4/` : verdicts du juge, dont `blind_final/summary.md` (évaluation finale) et `blind_v31grid2/combined_validated_grid.md` (grilles validées).
- `repro/` : tentative de reproduction des chiffres de la version d'origine.
- `legacy/` : rapports de la version d'origine, conservés pour la traçabilité.
