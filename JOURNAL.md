# JOURNAL.md — journal de travail et passation

But : permettre à un nouvel agent de reprendre le travail exactement où il s'est arrêté. Mis à jour au fil de l'eau (entrées les plus récentes en bas). À lire avec `CLAUDE.md` (règles), `PLAN.md` (tableau de bord) et `PROMPT_CLAUDE_CODE.md` §1 (mission complète).

## Comment reprendre (à lire en premier)

1. Lire `CLAUDE.md`, puis `PLAN.md`, puis la section « État courant » ci-dessous, puis la fin du journal.
2. Vérifier l'état réel : `git status`, `git log --oneline | head`, `ls reports/ reports/agents/ reports/repro/`.
3. Reprendre à la première ligne « À FAIRE » de l'état courant. Ne pas relancer ce qui est marqué fait sans raison.
4. Ajouter une entrée datée à la fin de ce journal à chaque étape significative (commande lancée, résultat chiffré, décision, fichier créé).

Conventions :
- venv : `.venv/bin/python` (Python 3.14). Toujours `HF_HUB_OFFLINE=1` (modèles en cache local).
- Ne jamais lire ni afficher `.env` (lecture refusée par l'utilisateur ; les scripts peuvent le charger via `Settings`).
- Le coût de la session agentique n'est plus suivi (abonnement). Les appels API Anthropic des expériences restent soumis à `<budget_et_couts>` et au ledger `reports/cost_ledger.csv`.
- `CLAUDE.md`, `PROMPT*.md`, `index/`, `data/*` (hors submodules), `.env` sont ignorés par git : ne pas forcer leur ajout.
- Aucun commit poussé ; pas de push sans accord.

## État courant

Phase : 0 terminée en grande partie, 1 en cours, 2 commencée.

| Élément | Statut | Où |
|---|---|---|
| `CLAUDE.md` (règles recopiées) | fait | racine |
| `PLAN.md` | fait, à tenir à jour | racine |
| Install + tests | fait : 19/19 | — |
| Reproduction ablation retrieval | fait : identique au README | `reports/repro/ablation_*` |
| Baseline aléatoire evidence recall | fait : 80,9 % | `reports/repro/random_baseline.py` |
| Reproduction end-to-end (MLX 7B) | lancée en arrière-plan à 2026-11-26 ~13h | `reports/repro/run_e2e_repro.sh`, sorties `reports/repro/e2e_*`, log `reports/repro/e2e_stdout.log` |
| `reports/00_reproduction.md` | brouillon ; section 3 = placeholder `RÉSULTATS_E2E` à remplir | `reports/` |
| Audits phase 1 (5 sous-agents) | lancés ; rapports attendus | `reports/agents/` (voir ci-dessous) |
| Ledger de coûts API | À FAIRE (SDK `anthropic` 2.14.0 installé) | `src/rag_sfar/evaluation/cost_ledger.py`, `reports/cost_ledger.csv` |
| Split dev/test + coffre-fort | À FAIRE après l'audit d'intégrité (doublons à garder du même côté) | `eval/LOCKBOX.md` |
| `reports/01_audit.md` + résumé à l'utilisateur | À FAIRE quand les 5 rapports sont là | — |

Rapports d'audit attendus dans `reports/agents/` (si un fichier manque, l'agent n'a pas fini : relancer l'audit correspondant avec le même périmètre) :
- `audit_code_retrieval.md` — retrieval/ + config.py
- `audit_code_ingestion_generation.md` — ingestion/, generation/, interfaces/, cli, scripts, tests ; contient les contrats d'interface à préserver
- `audit_donnees.md` (+ `data_audit_scripts/`) — corpus, OCR, éditions, structure GRADE des RFE
- `audit_integrite_evaluation.md` (+ `eval_integrity_scripts/`) — fuites benchmark→système, heuristiques ABP, métriques, édition v2.0 vs V3.0
- `veille_sota.md` — hypothèses classées avec sources

## Faits établis (à ne pas re-vérifier)

- Le benchmark antibioprophylaxie (171 q., 138 open / 33 QCM) porte sur la RFE **V2.0 du 22/05/2024** (`metadata.yaml`). Le corpus contient une **V3.0 « mise sur site juin 2026 »** que le système considère en vigueur (`expected_min_year=2023` dans `benchmarks.py`).
- Métriques de retrieval (`src/rag_sfar/evaluation/retrieval_metrics.py`) : « evidence recall » = tous les termes de réponse présents dans le texte indexé concaténé du top 8 ; « édition hit » = un chunk du bon titre/lignée avec année ≥ seuil. Pas de vérité terrain au niveau du passage.
- 59/138 questions exigent seulement « pas d'antibioprophylaxie », 42 seulement « céfazoline ».
- Notation end-to-end (`benchmark_adapter.py:22-43`) : open = toutes les molécules attendues en sous-chaîne ; QCM = première lettre isolée A–D (le verbe « a » compte comme « A ») ; sourcing = un nombre à 4 chiffres.
- Le jeu « stress multi-RFE 30 » est codé en dur dans `benchmarks.py`, écrit par l'équipe du système.
- Les échantillons e2e du README : « stratifié 50 » = ids dans `reports/repro/e2e_c8_v3_7b_ids.json` ; « inédites 50 » = `reports/repro/e2e_heldout_unseen_50_7b_ids.json`.
- Prix API (par M tokens in/out) : Fable 5.2 8/40, Opus 5.5 4/20, Sonnet 5.5 2/10, Haiku 5.5 0,10/0,50 ; cache read Opus/Fable 0,20, Sonnet 0,10 ; Batch −50 %.

## Journal

### 2026-11-26

- Lecture de la mission. La section `<git_et_libredatahub>` citée en phase 0 n'existe pas dans le prompt ; règles appliquées : respecter `.gitignore`, commits locaux seulement.
- Création de `CLAUDE.md` (sections recopiées par `sed` depuis le prompt, lignes 62-73, 75-89, 173-179) et `PLAN.md`.
- `pip install -e ".[neural,dev]"` puis `pytest -q` : 19 passed.
- `rag-sfar-eval --index-root index --output-dir reports/repro` (~10 min) : métriques identiques au README à ±1 % de tokens ; latence C8 210 ms vs 744 ms annoncés.
- Baseline aléatoire (`reports/repro/random_baseline.py`) : 8 chunks au hasard de la RFE ABP 2026 → evidence recall 80,9 % (74,6–85,5 %, 30 tirages) vs C0 92,0 % vs C8 99,3 %.
- Ajout de l'option rétrocompatible `--ids-file` à `scripts/run_e2e_eval.py` pour rejouer exactement les échantillons du README.
- Lancement de `reports/repro/run_e2e_repro.sh` (C8 sur stratifié 50, C8 sur inédites 50, zero-shot + C0 sur stratifié 50 ; Qwen2.5-7B-Instruct-4bit MLX). Durée attendue ~35 min.
- Lancement de 5 sous-agents d'audit (phase 1), sorties dans `reports/agents/`.
- Rédaction du brouillon `reports/00_reproduction.md`.
- Installation du SDK `anthropic` 2.14.0 dans le venv.
