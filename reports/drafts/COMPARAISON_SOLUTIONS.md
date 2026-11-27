# RAG-SFAR — Comparaison des solutions (brouillon du 2026-11-27)

> Ce document compare uniquement ce qui a été **mesuré dans ce projet**. Les solutions demandées par la mission mais non mesurées sont listées en section 5 avec la raison. Sources : `JOURNAL.md`, `reports/agents/B1_retrieval.md`, `B2_ingestion.md`, `B3_generation.md`, `A3_generateur_local.md`, `R2_revue_retrieval.md`, `X1_liens_structurels.md`, `reports/eval/judge_v4/blind_final/summary.md`, `eval_internal/robustness/results/summary.md`.

## 0. Lecture rapide

- **Configuration retenue** : `C10_context_notes` (BM25 + dense + fusion RRF + reranker, puis fenêtres de contexte et notes de tableau) sur l'index `tas_v6`, contexte structuré large, prompt `clinical_concise`.
- **Ce qui apporte vraiment** (mesuré hors antibioprophylaxie, y compris sur des RFE jamais vues) : la recherche hybride (dense + reranker) par rapport à BM25 seul, et les **fenêtres de contexte** (chunk voisin et tableau parent). Le reste de C10 n'apporte rien de démontré sur les jeux de test.
- **Le générateur compte plus que le retrieval** : à contexte égal, passer d'un modèle local de 7–9 milliards de paramètres à Claude Sonnet fait gagner 7 à 21 points de réponses correctes selon le jeu.
- **Non mesuré** : modèles frontier sans RAG, corpus ou documents entiers en contexte, RAG agentique via MCP, fine-tuning, modèle ouvert ~30B.

Rappel des jeux (détail dans `FINAL_REPORT.md` §2.1) : `abpe171` et `abp171` = questions validées par des médecins (antibioprophylaxie) ; `multirfe_synth`, `genprobe`, `genprobe2`, `x2_dev` = questions synthétiques générées par un LLM, non validées. Les chiffres `abpe171` sont jugés contre le brouillon du benchmark du 26/11 (commit `eabcefc`), pas contre sa version validée `sfar-abp-v31.1-valide` (en cours d'intégration).

Termes : **suffisance** = toutes les preuves exigées par les experts sont dans le contexte montré au générateur ; **passage** = le passage de référence est dans le contexte ; **fenêtres** = ajout du chunk voisin de chaque côté et du tableau parent autour des meilleurs résultats.

## 1. Stratégies de retrieval

### 1.1 Sur dev, index `tas_v6` (retrieval seul, déterministe)

| Configuration | abpe171 dev, suffisance (102) | abp171 dev, passage (102) | multirfe dev, passage (76 avec passage de référence) | Latence de recherche |
|---|---|---|---|---|
| BM25 seul, 8 résultats | 88,5 | 94,1 | 76,3 | 3–8 ms |
| BM25 + contexte de C10 (fenêtres, notes) | 94,8 | 95,1 | 86,8 | 9–28 ms |
| C9 : BM25 + dense + RRF + reranker | 88,5 | 97,1 | 82,9 | ~190 ms |
| C9 + fenêtres | 92,7 | 100 | 96,1 | ~190 ms |
| **C10_context_notes (retenue)** | **95,8 [92–99]** | **100** | **96,1** | ~190 ms (médiane 190, p95 204) |

Écarts appariés : C10 − BM25 seul : abpe171 +7,3 [+3,1 ; +13,5], abp171 +5,9 [+2,0 ; +10,8], multirfe +19,7 [+10,5 ; +28,9]. C10 − BM25 avec le même contexte : abpe171 +1,0 [−2,1 ; +5,2] (n.s.), abp171 +4,9 [+1,0 ; +9,8], multirfe **+9,2 [+3,9 ; +15,8]**. C10 − C9 + fenêtres : abpe171 +3,1 [0 ; +7,3].

### 1.2 Sur les jeux tenus à l'écart (une exécution ; test analysé post hoc)

| Configuration | abpe171 test, suffisance (64) | multirfe test, passage (RFE jamais vues) | genprobe, suffisance (48) | genprobe, passage |
|---|---|---|---|---|
| BM25 seul | 78,1 | 70,8 | non mesuré | non mesuré |
| C9 | 82,8 | 85,4 | 60,4 [46–73] | 81,2 |
| C9 + fenêtres | 82,8 | 97,9 | 75,0 [60–88] | 91,7 |
| **C10_context_notes** | **82,8** | **97,9** | **77,1 [65–88]** | **91,7** |

Écarts : fenêtres − C9 : multirfe test +12,5 [+4,2 ; +20,8], genprobe +14,6 [+6,2 ; +25,0] ; C10 − fenêtres : genprobe +2,1 [0 ; +6,2], abpe171 test 0 ; C9 − BM25 : abpe171 test +4,7 [−1,6 ; +12,5], multirfe test +14,6 [0 ; +29,2].

**Lecture.** Sur l'antibioprophylaxie (vocabulaire d'actes très spécifique), BM25 fait presque aussi bien que l'hybride. Le dense et le reranker paient sur les autres RFE. La construction du contexte (fenêtres, tableau parent) apporte autant ou plus que le modèle de recherche, et c'est le seul gain qui se retrouve sur tous les jeux tenus à l'écart. Les gains propres à C10 (notes, plafond par document) ont été obtenus en corrigeant des échecs du dev de l'antibioprophylaxie et ne se retrouvent pas sur son test.

### 1.3 Robustesse aux saisies (abpe171 dev, suffisance ; perturbations synthétiques)

| Configuration | Propre | 1 faute | 2 à 3 fautes | Sigles d'utilisateur |
|---|---|---|---|---|
| C10 figée | 95,8 | 89,6 | 84,4 | 87,5 |
| + n-grammes de caractères | 96,9 | 91,7 | 87,5 | 89,6 |
| + lexique médical | 95,8 | 89,6 | 84,4 | 94,8 |
| + n-grammes + lexique | 95,8 | 90,6 | 88,5 | 97,9 |
| BM25 seul | 94,8 | 88,5 | 69,8 | 86,5 |
| dense seul | 76,0 | 77,1 | 78,1 | 68,8 |

Tableaux bruts de l'agent Q1, IC dans `eval_internal/robustness/results/summary.md` et `FINAL_REPORT.md` §8.1. Aucune variante n'est adoptée.

À COMPLÉTER : décision de Q1 (`reports/agents/Q1_robustesse.md`) et, si un candidat est retenu, son résultat sur `genprobe2`.

À COMPLÉTER : effet de la formulation en langage courant − standard sur le benchmark validé des experts (variante complète des 171 questions et 29 reformulations approuvées de `sfar-abp-v31.2-200`), pour C10 figée, n-grammes et lexique (`reports/agents/V1_benchmark_valide.md`).

### 1.4 Modèles de recherche plus gros

| Variante | Effet | Latence | Décision |
|---|---|---|---|
| Embedder Qwen3-Embedding-0.6B au lieu de e5-small (C9) | multirfe doc hit −2,6 [−6,6 ; 0] ; passage +1,3 (n.s.) | non attribuable (mesurée dans d'autres conditions) | rejeté |
| Reranker bge-reranker-v2-m3 au lieu de mmarco (C9) | multirfe passage +3,9 [−1,3 ; +9,2] (n.s.) | ~1,7 s contre ~0,19 s (C9, Mac) | rejeté |
| idem sur C10 | abpe171 −1,0 [−3,1 ; 0] | 1,8–3,9 s en charge | rejeté |

### 1.5 Explorations du 27/11 (modules désactivés par défaut)

| Module | État | Résultat connu |
|---|---|---|
| Liens structurels adulte ↔ enfant (X1) | mesuré, rejeté | 42/42 liens corrects mais tous dans l'antibioprophylaxie ; effet sur dev 0 |
| Seconde passe corrective sans LLM (X2 option 2) | mesuré, rejeté | gain 0 ; abpe171 dev −1,0 [−3,1 ; 0] ; latence 192 → 330–690 ms |
| Décomposition par LLM (X2 option 1) | en cours | À COMPLÉTER : effet sur suffisance (abpe171 dev, multirfe dev, x2_dev), latence et coût en appels LLM, décision |
| Seconde passe corrective avec LLM (X2 option 3) | en cours | À COMPLÉTER : effet sur suffisance, latence, décision |
| Reformulation par LLM (Q2 : normalisation, reformulation, HyDE) | en cours | À COMPLÉTER : effet propre et perturbé, fidélité clinique des reformulations, latence, décision |
| Candidats sur `genprobe2` | non exécuté | À COMPLÉTER : résultats de l'exécution unique, par famille, candidat − figée avec IC |

## 2. Index (ingestion)

Dev, abpe171, suffisance. Toutes les comparaisons sont intra-projet ; l'index d'origine (`table_aware_sota`) a été reconstruit par un autre agent le 26/11 à 16:26, ce qui rend non fiables les comparaisons entre mesures faites avant et après.

| Index | C9 | C9 + fenêtres | C10 (version de l'époque) | Fidélité du texte | Statut |
|---|---|---|---|---|---|
| `tas_v3_errata` (erratum V3.1 appliqué) | 83,3 | 88,5 | 99,0 (C10 population) ; 94,8 (C10 figé) | référence | remplacé |
| `tas_v4` (tableaux éclatés, nettoyage OCR) | 90,6 | 93,8 | 99,0 | **défauts** : 1 472 tableaux aplatis, µg abîmés, ~700 chunks mal étiquetés pédiatriques | **rejeté** |
| `tas_v5` (corrections de fidélité) | 88,5 | 92,7 | 97,9 | compteurs de fidélité à 0 | remplacé |
| **`tas_v6`** (+ 3 errata officiels, glyphes, coquilles V3.1) | 88,5 | 92,7 | **95,8** (C10 figé) | compteurs à 0 ; 36 872 chunks | **retenu** |

Plus ancien : avec l'index et le pipeline d'origine, multirfe dev passage hit@8 C0 naïf 69,7 [59–80] contre C8 85,5 [76–93].

## 3. Générateurs

### 3.1 Petit modèle local contre substitut fort (dev, mêmes contextes)

| Générateur | Contexte | Jeu | Correct | Erreurs graves | Latence par question | Grille |
|---|---|---|---|---|---|---|
| Qwen2.5-7B 4 bits (MLX) | C9, 6 passages | multirfe dev (94) | 69,1 % | 7,4 % | 8,2 s | v1 |
| Qwen2.5-7B 4 bits | C9, 6 passages | abp171 dev (102) | 81,4 % | 3,9 % | — | v1 |
| Claude Sonnet | C9, 6 passages | multirfe dev | 90,4 % [84–96] | 0 % | non mesurée | v1 |
| Claude Sonnet | C9, 6 passages | abp171 dev | 91,2 % [85–96] | 2,0 % | non mesurée | v1 |
| Claude Sonnet | C9, 12 passages | multirfe / abp171 dev | 96,8 % / 95,1 % | 0 / 2,0 % | non mesurée | v1 |
| Qwen3.5-9B 4 bits (MLX) | C9 + fenêtres, large | itération 30 + 30 (abpe / multirfe) | 77 / 83 % | 3 / 7 % | ~30 s | v2 |
| Claude Sonnet | idem | idem | 83 / 90 % | 0 / 0 % | non mesurée | v2 |

Écarts appariés : Sonnet − 7B : +21,3 [+12,8 ; +30,9] (multirfe, synthétique), +9,8 [+2,0 ; +17,6] (abp171, médecins) ; Sonnet − 9B : +6,7 [0 ; +15,0], graves −5,0 [−11,7 ; 0]. Le gain plus fort sur le jeu écrit par Claude suggère un avantage de Claude d'une dizaine de points sur ce jeu.

Coût matériel du 9B sur la machine de développement (Mac 16 Go) : ~13,7 s par question avec ~2 200 tokens de prompt ; ~51 s avec le contexte large (17 à 30 passages, jusqu'à 8 800 tokens), sous contention ; pic mémoire 10,8 Go. Ministral-3-14B : 3 à 4 fois plus lent, échec mémoire dès 18 000 caractères, sources citées dans 5 réponses sur 12 → écarté.

Les grilles v1, v2, v3 et v4 du juge ne sont pas comparables entre elles (ruptures de série consignées dans `JOURNAL.md`).

### 3.2 Configuration finale avec le substitut Sonnet (grille v4, à l'aveugle, deux juges)

| Jeu | Correct | Erreurs graves (≥ 1 juge) |
|---|---|---|
| abpe171 test (médecins, 69) | 53,6 % [41,2–65,7] | 5,8 % [1,6–14,2] |
| multirfe_synth test (synthétique, 57) | 91,2 % [80,7–97,1] | 0 % [0–6,3] |
| genprobe (synthétique, 48) | 75,0 % [60,4–86,4] | 6,2 % [1,3–17,2] |

Formulation imposée : avec un générateur de substitution (Claude Sonnet) recevant exactement les prompts de notre configuration, ces taux de réponses sont jugés conformes à la référence par un juge LLM (Claude Haiku, grille v4, non validée médicalement). Le modèle déployé (~30B) n'a pas été mesuré.

À COMPLÉTER : rejugement post hoc des mêmes réponses sous les grilles validées `sfar-abp-v31.1-valide` (analyse secondaire).

### 3.3 Ancien système (pour mémoire)

Ancien pipeline, Qwen2.5-7B, abp171 dev, juge Haiku grille v1 : C0 naïf 64,7 % [56–74], erreurs graves 14,7 % ; ancien C8 80,4 % [72–88], erreurs graves 5,9 %. Sans RAG (« zero-shot »), le 7B reproduit 52 % (26/50) sur l'échantillon « stratifié 50 » du README, notation déterministe ; ce chiffre n'a pas été jugé ni remesuré sur les jeux actuels.

## 4. Tableau de décision

| Solution | Retrieval (hors ABP) | Génération mesurée | Erreurs graves | Latence recherche | Coût par requête | Déployable sur LibreDataHub | Mise à jour quand une RFE paraît | Ce qu'elle apporte |
|---|---|---|---|---|---|---|---|---|
| BM25 seul | faible (multirfe test 70,8) | non | non mesurées | 2–8 ms | nul (CPU) | oui | réindexation | base de comparaison, quasi aussi bon sur l'ABP |
| BM25 + contexte de C10 | moyen (multirfe dev 86,8) | non | non mesurées | 9–28 ms | nul | oui | réindexation | montre que la construction du contexte compte autant que la recherche |
| C9 (hybride simple) | bon pour le document, moyen pour le passage (multirfe test 85,4 ; genprobe 60,4) | oui (7B, Sonnet) | 5,3 % (7B, multirfe dev, v1) | ~190 ms | CPU, petits modèles | oui | réindexation + embeddings | dense + reranker : seuls composants utiles de l'ancien pipeline |
| C9 + fenêtres | bon (multirfe test 97,9 ; genprobe 75,0) | oui (9B, Sonnet) | indiscernable de C10 avec Sonnet | ~190 ms | idem, ~20 000 car. de contexte | oui | idem | **le gain qui généralise** |
| **C10_context_notes (retenue)** | idem C9 + fenêtres (genprobe 77,1) | oui (Sonnet, évaluation finale) | voir §3.2 | ~190 ms | ~8 600 tokens de prompt par question | oui | idem | notes de tableau ; gain non démontré sur test, sans coût mesurable |
| Ancien C8 (pipeline d'origine) | multirfe dev 85,5 (hit@8) | oui (7B) | 16,0 % (multirfe dev, v1) | ~480 ms | — | oui | — | remplacé : plus complexe, plus d'erreurs graves |
| Petit modèle local (7B / 9B) comme générateur | — | oui | 3–7 % (dev, 30 q.) | 8–51 s par réponse (Mac) | gratuit en local | oui | aucune | souverain, mais 7 à 21 points derrière Sonnet |
| Substitut Sonnet comme générateur | — | oui | §3.2 | non mesurée | non mesuré en $ (abonnement) | **non** (modèle propriétaire) | aucune | estimation de ce que permet un générateur fort |

Recommandation provisoire (à confirmer par la mesure du modèle cible) : servir C10_context_notes (ou C9 + fenêtres, équivalent mesuré) sur `tas_v6` avec un modèle ouvert de classe ~30B et le prompt concis ; ne pas présenter de chiffre de ce système tant que le modèle cible n'a pas été évalué ; garder le serveur MCP comme moteur de recherche cité en lecture seule pour un usage par des assistants tiers.

## 5. Ce qui n'a pas été mesuré, et pourquoi

| Solution demandée par la mission | Mesurée ? | Pourquoi |
|---|---|---|
| Modèles frontier sans RAG (Opus, Fable) | non | la clé API du projet a été refusée le 26/11 (401) ; l'utilisateur a décidé de continuer sans API ; les sous-agents ont servi au générateur de substitution et au juge, pas à cette baseline |
| Modèle ouvert sans RAG | seulement l'ancien 7B, 52 % sur 50 questions du README (notation déterministe) | non remesuré avec le juge sur les jeux actuels |
| Modèle ouvert ~30B avec notre RAG | non | ne tient pas dans les 16 Go de la machine ; GPU LibreDataHub disponible seulement le jour du datathon |
| Contexte long : document complet après sélection, approche hiérarchique, contexte structuré « recommandations extraites » | non | priorité donnée au retrieval et à l'évaluation scellée ; seul l'extracteur de recommandations GRADE existe (3 933 unités, précision manuelle 37/40), et son usage comme chunks a été neutre en retrieval |
| Courbe exactitude / taille de contexte | partielle | Sonnet 6 → 12 passages : +6,4 [+1,1 ; +12,8] (multirfe) et +3,9 [+1,0 ; +7,8] (abp171) ; 9B : C9 + fenêtres − C9 étroit +6,7 [−3,3 ; +16,7] (n.s.) ; rien au-delà de 30 000 caractères |
| RAG agentique via MCP | non | serveur MCP HTTP prototypé (médiane 219 ms par recherche) et architecture rédigée (`reports/MCP_ARCHITECTURE.md`), mais aucun mode agentique évalué |
| Fine-tuning (style RAFT) | non | pas de GPU d'entraînement adapté localement, pas de budget de génération de données ; risque de contenu périmé dans les poids |
| Coût par requête en dollars | non | aucune dépense API (ledger vide) ; seul le volume de tokens est connu |
| Qualité des citations jugée par des médecins | non | fidélité aux extraits cités jugée par LLM seulement (95,6 % sur abpe171 test) |
