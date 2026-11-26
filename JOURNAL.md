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
- Module `src/rag_sfar/evaluation/cost_ledger.py` (prix, `record_usage`, `record_estimate`, `guard_experiment` : refus > 15 $ sans accord et au-delà de 60 $ cumulés) + `tests/test_cost_ledger.py`. Tests : 23/23.
- Branche de travail locale `rag-sfar-v2` créée depuis `main`. Commits : `--ids-file`, ledger, PLAN/JOURNAL. `reports/00_reproduction.md` et `reports/repro/` seront commités quand l'e2e sera fini.
- Prochaine étape pendant l'attente : spécification du format d'évaluation commun (`eval/README.md`) et du harnais `rag-sfar-eval --suite ... --split ...` (phase 2), indépendante des audits.
- Veille SOTA terminée : `reports/agents/veille_sota.md`. Top hypothèses : (1) embedder Qwen3-Embedding-0.6B / EmbeddingGemma à la place de e5-small (MMTEB retrieval 64,6 vs 49,3) ; (2) reranker bge-reranker-v2-m3 puis Qwen3-Reranker ; (3) extraction des recommandations GRADE en unités ; (4) en-têtes de contexte déterministes sur les chunks ; (5) générateur 24–31B en prod. Ordre « U-shape » non soutenu par la littérature 2025–2026.
- Phase 2 : `eval/README.md` (format commun), `src/rag_sfar/evaluation/datasets.py` (EvalItem, import générique CSV/JSON/JSONL, conversion ABP, split stratifié déterministe avec regroupement des quasi-doublons en ignorant les mots-gabarits, coffre-fort SHA-256), `src/rag_sfar/evaluation/harness.py` (métriques doc/passage/obsolète/exactitude/abstention, IC bootstrap, comparaisons appariées, rapports JSON+MD dans `reports/eval/`).
- `eval/datasets/abp171.jsonl` créé (gold doc = V3.0 2026 `2026_RFE-antibioprophylaxie-2023_V3_0_pour-mise-sur-site-juin-2026_sa_9ff419`). Split prévisualisé : 102 dev / 69 test, 8 groupes de quasi-doublons. Coffre-fort PAS encore scellé (attente de l'audit d'intégrité).
- Audit code retrieval terminé : `reports/agents/audit_code_retrieval.md`. Critiques : lexique insensible à la casse (« ne pas » → « pneumonie associée aux soins », `medical_lexicon.py:144`) ; routeur (« 6 mois » → pédiatrie, « alternative » → flag allergie qui injecte l'alerte « Patient ALLERGIQUE » `client.py:280`, « rac » → ambulatoire). Importants : heuristiques ABP codées en dur (R1.5–R1.7, voie antérieure, encadrés allergie), question du benchmark recopiée dans `crag.py`, pénalité pédiatrique par défaut, `final_top_k` non respecté, ablation C7→C8 change 5 options à la fois. Latence 250–540 ms/requête.
- Harnais branché sur `rag-sfar-eval --suite S --split dev [--configs C0,C8] [--retrieval-only]` (sans `--suite` : ablation historique inchangée ; `--split test` exige `--allow-test`). Smoke test ABP dev (102 q.) retrieval : doc hit C0 94 %, C6/C8 99–100 % ; intrusion obsolète C0 ~61 %, C6/C8 0 %. Rapport : `reports/eval/20261126-130429_abp171_dev_smoke.md`. Pas encore de vérité terrain passage pour ABP.
- Audit ingestion/génération/interfaces terminé : `reports/agents/audit_code_ingestion_generation.md`. Critiques : prompts `prompts.py:28-45` calqués sur des questions (Q04, Q15, Q139–Q143, Q28) ; en mode benchmark le moteur ajoute lui-même « (SFAR <année> [S1]) » (`client.py:372-379`) → sourcing gagné par construction ; adaptateur `SfarRagApproach` mal noté par la plateforme (sortie 2 lignes) ; vérificateur = liste fermée de 70 molécules, ne vérifie pas les doses. Importants : supersession = 25 regex manuelles, 170/264 docs sans lignée ; domaines faux par sous-chaîne (« rac ») sur 114 docs ; encadrés allergie uniquement ABP ; MCP/API : écarts au protocole. Contrats d'interface à préserver : §5 du rapport.
- Test anti-fuite `tests/test_no_benchmark_leakage.py` (7-grammes spécifiques à une question + réponses ≥ 3 mots hors classes partagées, sur `src/` hors `evaluation/`). Détecte Q04, Q06, Q16, Q22, Q28 (dans `crag.py`, `verifier.py`, prompts). Marqué `xfail(strict=True)` : retirer le marqueur après nettoyage (phase 3). Suite : 24 passed, 1 xfailed.
- Accès à `.env` par du code lancé par l'agent : refusé par le classifieur de sécurité. Décision : `src/rag_sfar/evaluation/anthropic_batch.py` (helper Batch API −50 %, cache JSONL par custom_id, ledger, garde budgétaire) lit UNIQUEMENT `ANTHROPIC_API_KEY` dans l'environnement, jamais `.env`. La variable est présente dans l'environnement de la session.
- e2e « stratifié 50 » C8 (7B MLX) reproduit : 50/50 (40/40 open, 10/10 QCM, 8/8 allergie), réponses courtes ; 1 réponse hésitante listant 2 molécules (Q42) comptée juste. Le score est réel pour ce pipeline mais les prompts ont été écrits sur ces questions (fuites), donc non probant.
- Audit d'intégrité terminé : `reports/agents/audit_integrite_evaluation.md` (+ scripts). Constats : stratifié-50 = jeu de développement (13/50 questions visées par une règle) ; « inédites 50 » vues pendant le dev, baseline constante (« Pas d'ABP » / « C ») = 58 % sur ce jeu ; 20 lignes de code partagent des formulations avec 22 questions ; « C1G → céfazoline » n'est PAS une fuite ; sourcing 100 % fabriqué par le code ; stress-test 30 circulaire ; **0/171 réponses ne changent entre V2.0 et V3.0** ; défauts de sécurité (alerte allergie sur « alternative », `PAS` développé à tort). Tableau de 37 éléments avec décisions proposées.
- Coffre-fort scellé : `eval/LOCKBOX.md`, `eval/splits/abp171/{dev,test}.jsonl` (102/69). `tests/test_lockbox.py` vérifie les empreintes. `write_lockbox()` conserve l'historique.
- `eval_internal/build_multirfe.py` écrit (sample → generate [Sonnet 5.5 batch] → verify [Opus 5.5 batch + contrôles programmatiques] → write). Pas encore lancé.
- **BLOCAGE API** : la variable `ANTHROPIC_API_KEY` présente dans l'environnement est refusée par l'API (401 invalid x-api-key, 2026-11-26 ~13h30). Aucun coût engagé (ledger vide). Tout ce qui appelle l'API (génération/vérification du jeu interne, juge LLM, baselines frontier) attend une clé valide fournie par l'utilisateur (export dans l'environnement de la session ; l'agent ne lit pas `.env`). Étape prête : `eval_internal/build_multirfe.py generate` puis `verify` puis `write` ; `sample` déjà fait (`eval_internal/work/anchors.json` : 70 docs, 194 passages, 11 lignées de comparaison).
- `reports/01_audit.md` rédigé (synthèse des 4 audits reçus + plan priorisé : étape 0 éval → 1 C8-générique (retrait des fuites + défauts sécurité) → 2 simplification par ablation → 3 embedder/reranker/en-têtes/unités GRADE/supersession → 4 génération/vérification → 5 exploration). Section « Données » en attente de `reports/agents/audit_donnees.md` (agent encore en cours).
- En attente : fin de l'e2e (inédites 50 C8, puis zero-shot + C0) → compléter `reports/00_reproduction.md` §3 (placeholder `RÉSULTATS_E2E`) et le commiter avec `reports/repro/`.
