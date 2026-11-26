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
- Décision utilisateur (2026-11-26) : « Continue without API ». Le jeu interne est généré par des sous-agents Claude Code (abonnement) au lieu de la Batch API : 4 générateurs (entrées `eval_internal/work/gen_input_{0,1,2,compare}.json` + `catalogue.json`, sorties `gen_out_{0,1,2,compare,abstention}.json`), puis vérification par des sous-agents distincts n'ayant pas généré, puis contrôles programmatiques (`build_multirfe.py`). Provenance `llm_synthetic`.
- e2e « inédites 50 » C8 reproduit exactement : 43/50 = 86 % (mêmes 7 erreurs Q14, Q23, Q44, Q74, Q86, Q98, Q154). Baseline constante sur ces 50 : 58 % (« Pas d'ABP » / « C »).
- `eval_internal/README.md` (avertissement synthétique, méthode, limites). `build_multirfe.py` : commandes `import-gen`, `prepare-verify --parts N`, `import-verify` pour la voie sous-agents.
- Baseline constante dans le harnais : `rag-sfar-eval --suite abp171 --split dev --baseline constant` → 47,1 % [37–57] (open « pas d'antibioprophylaxie », QCM « C »).
- Audit données terminé : `reports/agents/audit_donnees.md` (+ `data_audit_scripts/run_all.sh`). 176 titres / 202 textes FR principaux ; OCR fidèle (99,3 % des posologies) ; PDF = pointeurs LFS non tirés ; GRADE complet 28 % des textes (87 % en 2023–2026) ; prototype d'extraction de recommandations : 2 355 unités / 89 docs, 27/30 correctes ; force GRADE à lire dans la cotation (gabarit HAS) ; 2 erreurs de supersession (Urgences obstétricales 2010 vs RPP 2022 ; RPP COVID abrogée) ; faux domaines sur 102 docs. Section « Données » de `reports/01_audit.md` complétée.
- `src/rag_sfar/evaluation/judge.py` écrit (grille, schéma, backends local/Anthropic, kappa, sonde de biais de longueur). Pas encore calibré.
- Phase 3 étape 1 lancée en parallèle (sous-agent unique autorisé à modifier le pipeline) : « C8 générique » (retrait des fuites, défauts de sécurité, bugs I3/I4, sourcing désactivable, tests). Rapport attendu : `reports/agents/generic_c8_changes.md`, commits atomiques sur `rag-sfar-v2`. **Référence « avant nettoyage » = commit `fa0426a`** : la mesurer via `git worktree add ../sfar-legacy fa0426a` (ne pas re-mesurer sur le code nettoyé).
- Génération jeu interne partie 0 : 46/65 utilisables (`eval_internal/work/gen_out_0.json`).
- Génération jeu interne partie 2 : 42/64 utilisables (`gen_out_2.json`).
- Génération comparaisons : 8/11 utilisables ; 40 questions hors corpus (`gen_out_compare.json`, `gen_out_abstention.json`). En attente : partie 1.
- Génération partie 1 : 49/65. Total : 137 questions ancrées + 8 comparaisons + 40 hors corpus.
- `import-gen` → `work/gen_results.jsonl` ; `prepare-verify --parts 3` → 185 candidats (0 rejet programmatique) ; 3 vérificateurs lancés (sorties `work/verify_out_{0,1,2}.json`). Ensuite : `import-verify`, `write`, split avec `--holdout-doc-fraction`, lockbox.
- Vérification partie 1 : 59 keep / 3 drop (1 réponse corrigée).
- Vérification partie 0 : 51 keep / 11 drop (5 réponses corrigées).
- Vérification partie 2 : 14 keep / 7 drop ; abstention 27 non couvertes / 13 couvertes (écartées).
- Jeu interne `multirfe_synth` écrit : 151 questions (61 reco, 22 tableau, 37 cas clinique, 4 comparaison, 27 hors corpus) sur 185 candidats ; trace des rejets `eval_internal/work/audit_trail.json`. Split leave-documents-out : 94 dev / 57 test, 22 docs uniquement en test, 0 doc commun. Scellé dans `eval/LOCKBOX.md`.
- `eval_internal/a_valider_medecins.csv` : 40 questions (12 open, 10 cas, 8 tableau, 4 comparaison, 6 hors corpus ; 1 par document max) avec colonnes de validation. Les validations s'appliqueront par surcouche `eval_internal/validations_medecins.csv` (à implémenter dans le harnais quand elles arrivent).
- Worktree de référence « avant nettoyage » : `../sfar-legacy` (commit d0cbc08, src identique à fa0426a). Lancer avec `PYTHONPATH=$PWD/src` depuis ce dossier et `--index-root /Users/tim/Me/SFAR-datathon/index`.
- Ancien C8, retrieval, `multirfe_synth` dev (94 q.) : doc hit@8 C0 88,2 / C4 90,8 / C5 92,1 / C6 93,4 / C8 96,1 % ; passage hit@8 C0 69,7 [59–80] / C5 82,9 / C6 81,6 / C8 85,5 [76–93] ; intrusion obsolète C0 31,5 % / C5 23,3 % / C6-C8 0 (filtre dur, et dépend des lignées du système). Latence C8 480 ms. Rapport : `reports/eval/*multirfe_synth_dev_legacy_retrieval.md`.
- e2e terminé : zero-shot stratifié 52 % (= annoncé) ; **C0 naïf 72 % (36/50) contre 84 % annoncés** (non reproduit). `reports/00_reproduction.md` complété (§3 + conclusion 5) et commité avec `reports/repro/`.
- Lancé (arrière-plan) : génération ancien système C0+C8, Qwen2.5-7B MLX, mode clinical_detailed (QCM : benchmark_mcq), max 400 tokens, sur abp171 dev puis multirfe_synth dev, depuis `../sfar-legacy`. Logs `reports/eval/legacy_gen_*.log`, rapports copiés dans `reports/eval/*legacy_gen_7b*`. Ensuite : calibrer le juge local sur ces réponses (vérité = clés déterministes QCM/molécules).
- C8 générique terminé (8 commits b09c2f5…5af2ec6, rapport `reports/agents/generic_c8_changes.md`). Vérifié : 42 tests verts, scan anti-fuite vide, `xfail` retiré, worktree legacy d0cbc08 antérieur à tous les commits de nettoyage. Décision conservée : l'API HTTP garde l'ajout de provenance par défaut (`RAG_SFAR_API_ATTACH_PROVENANCE=true`) pour rétrocompatibilité ; l'évaluation le désactive et lit `provenance_added_by_code`. Les corrections de domaines dans `loader.py` n'agiront qu'à la réindexation.
- C8 générique vs ancien, retrieval, dev (comparaison appariée) : abp171 doc hit 100 % = ; doc MRR 0,993 → 0,987 (n.s.). multirfe_synth : doc hit 96,1 % = ; doc MRR 0,836 → 0,869 (+0,033 [+0,006 ; +0,071]) ; passage hit 85,5 → 86,8 % (n.s.) ; latence 480 → 392 ms. Conclusion : le sur-ajustement du retrieval était faible ; l'essentiel est dans les prompts de génération (mesure e2e en cours).
- Option `--ablate f1,f2` (variante par composant désactivé, une variable à la fois). Lancé : ablation retrieval de C8 générique (10 composants) sur multirfe_synth dev puis abp171 dev → `reports/eval/*ablation_c8*`, logs `reports/eval/ablation_c8_*.log`.
- Ablation un-composant-à-la-fois de C8 générique (retrieval, dev, appariée) : seuls **dense** (multirfe passage hit −7,9 pts [−14 ; −3], passage MRR −0,080) et **reranker** (passage MRR −0,085 [−0,15 ; −0,02]) ont un gain mesurable. CRAG, n-grammes, DBSF, boost métadonnées, lexique, routeur, expansion voisins, encadrés : effet nul ou non significatif sur les deux jeux.
- Ajout de `C9_simple_hybrid_rerank` (`ablation.py`) : BM25 + dense + RRF + reranker + filtre d'édition + routeur (gardé pour les comparaisons d'éditions, fonctionnel mais trop rare pour être mesuré). C8 vs C9 (dev) : multirfe doc hit 96,1 → 97,4 (n.s.), doc MRR 0,869 → 0,840 (−0,029 [−0,075 ; +0,011]), passage hit 86,8 → 85,5 (n.s.) ; abp doc hit 100 = . Équivalents dans le bruit → C9 candidat référence, à confirmer en génération.
- Étape 3, hypothèse 1 (embedder) préparée : `embedder.py` utilise les prompts query/document natifs des modèles à instructions (Qwen3-Embedding, EmbeddingGemma) et plafonne max_seq_length à 1024 ; `scripts/reembed_index.py` (ré-embarque un index existant dans un NOUVEAU dossier, mêmes chunks/BM25) ; harnais : `--index-map table_aware_sota=<dossier>` et `--reranker <modèle>`.
- Téléchargement en cours (arrière-plan) : Qwen/Qwen3-Embedding-0.6B (1,2 Go, Apache-2.0), BAAI/bge-reranker-v2-m3 (2,3 Go, Apache-2.0), safetensors seulement. BGE-M3 écarté pour l'instant (poids seulement en `.bin` pickle). EmbeddingGemma : dépôt à accès restreint (licence à accepter), non tenté.
- À faire ensuite : `HF_HUB_OFFLINE=1 .venv/bin/python scripts/reembed_index.py --src index/table_aware_sota --dst index/tas_qwen3emb06 --model Qwen/Qwen3-Embedding-0.6B` puis `rag-sfar-eval --suite multirfe_synth --split dev --configs C9 --retrieval-only --index-map table_aware_sota=tas_qwen3emb06`, comparer à C9 e5-small ; idem reranker `--reranker BAAI/bge-reranker-v2-m3`.
- Ancien système, génération mode générique (clinical_detailed ; QCM benchmark_mcq), Qwen2.5-7B, abp171 dev (102 q.), notation déterministe : **C0 57,8 % [48–68], C8 67,6 % [58–76]** (Δ +9,8 pts [−2 ; +22.5]) ; sourcé 64 / 69 % ; latence 21 s / 11 s. Rapport dans `../sfar-legacy/reports/eval/` (copié en fin de boucle). Hors prompts calqués, l'ancien C8 tombe de 86–100 % à 68 %.
- Limite de la notation déterministe : « Il n'y a pas de recommandation d'antibioprophylaxie pour … » n'est pas compté comme « pas d'antibioprophylaxie » → borne basse ; juge calibré nécessaire. `is_abstention` restreint à la tête de réponse (ligne « Réponse synthétique » ou 300 premiers caractères).
- En cours (arrière-plan) : ancien système génération multirfe_synth dev ; ré-embarquement Qwen3-Embedding-0.6B → `index/tas_qwen3emb06` ; C9 + bge-reranker-v2-m3 retrieval dev.
- **ÉCHEC** : génération ancien système sur multirfe_synth dev → `RuntimeError: [METAL] ... Insufficient Memory` (MLX 7B + ré-embarquement Qwen3 + reranker bge en même temps). **Règle : un seul job GPU à la fois** (génération MLX, ré-embarquement, rerankers). À relancer : génération legacy multirfe_synth dev (commande dans le log `reports/eval/legacy_gen_multirfe_synth.log`, même boucle que pour abp171, depuis `../sfar-legacy`).
- Hypothèse reranker bge-reranker-v2-m3 vs mmarco-mMiniLMv2 (C9, retrieval, dev, apparié) : multirfe passage hit 85,5 → 89,5 % (+3,9 [−1,3 ; +9,2]), passage MRR +0,059 [−0,014 ; +0,137], doc hit +1,3 (n.s.) ; abp = . Latence 0,4 → 13 s/requête sur Mac (mesurée sous contention GPU avec le ré-embarquement : pessimiste). Décision : tendance favorable non significative, latence prohibitive en local → candidat pour LibreDataHub (GPU), non adopté ; à re-tester seul et avec `rerank_top_k` réduit.
- Décisions utilisateur (2026-11-26 ~15h) : (1) juge = sous-agents Claude sur modèle bon marché (Haiku), calibré ; (2) **pousser sur git (`origin`, branche `rag-sfar-v2`) dès qu'il y a des changements de code**. Branche poussée (`git push -u origin rag-sfar-v2`) après scan de secrets (aucun).
- Calibration du juge : `eval_internal/judge/calibration_cases.json` (200 cas : 180 réponses réelles de 5 runs, vérité = clé déterministe QCM / molécules, libellés ambigus « pas d'ABP » / « hors périmètre » exclus ; + 20 doublons rallongés d'une phrase neutre pour le biais de longueur, paires dans `length_probe_pairs.json`). Consignes : `JUDGE_INSTRUCTIONS.md` (= grille de `judge.py`). 4 juges Haiku lancés (`judge_out_{0..3}.json`).
- `src/rag_sfar/evaluation/judge_io.py` : `export` (rapport → lots pour juges), `merge` (verdicts → métriques judge_correct / judge_serious_error avec IC dans le rapport JSON+MD), `calibrate` (kappa, accord par source, sonde de longueur, désaccords).
