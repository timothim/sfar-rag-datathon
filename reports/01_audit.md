# 01 — Audit de la fondation RAG-SFAR et plan d'amélioration

Date : 2026-11-26. Sources : 5 audits indépendants dans `reports/agents/` (code retrieval, code ingestion/génération/interfaces, intégrité de l'évaluation, données, veille état de l'art) et la reproduction `reports/00_reproduction.md`. Chaque constat ci-dessous renvoie à un fichier:ligne vérifié dans ces rapports.

## Conclusions

1. **Aucun chiffre du README ne mesure la généralisation.** Le « 100 % (50/50) » se reproduit, mais sur un jeu qui a servi à mettre au point le système : 13 des 50 questions sont visées par une règle, un exemple de prompt ou un docstring écrit à partir d'elles. Les « 50 inédites » ont servi aux ablations de retrieval, et une baseline constante (« Pas d'antibioprophylaxie » / « C ») y fait déjà 58 %. Tout le bout-en-bout porte sur une seule RFE sur 264.
2. **Le système encode le benchmark.** Les exemples de réponse du prompt sont exactement les réponses des questions « allergie » (`prompts.py:35`). Des docstrings CRAG et des tests recopient Q16, Q143, Q146. Un bonus « main » (`pipeline.py:559`) ne sert que Q09, Q15, Q143. Les numéros R1.5–R1.7 et des molécules sont codés dans les facettes CRAG. Le test anti-fuite automatisé détecte 5 questions recopiées (Q04, Q06, Q16, Q22, Q28).
3. **Les métriques de retrieval sont quasi gratuites.** 8 chunks tirés au hasard dans la bonne RFE donnent 80,9 % d'« evidence recall » (C8 : 99,3 %). « Intrusion obsolète 0 % » résulte d'un filtre dur. 170 des 264 documents n'ont aucune lignée d'éditions et ne peuvent donc jamais être jugés obsolètes. Le « sourcing 100 % » vient d'une année ajoutée par le code (`client.py:372-379`).
4. **Il y a des défauts de sécurité clinique hors benchmark.**
   - Le lexique développe des mots français comme des acronymes, sans tenir compte de la casse : « ne pas » / « PAS » devient « pneumonie associée aux soins ».
   - Le routeur met une question en pédiatrie dès qu'elle contient « 6 mois ».
   - L'alerte « Patient ALLERGIQUE aux bêtalactamines » est injectée dans le prompt dès qu'apparaît « alternative » ou « pénicilline », y compris pour l'anaphylaxie.
   - Le vérificateur accepte « Céfazoline 20 g » quand la source dit 2 g. Il ne contrôle qu'une liste fermée de 70 molécules.
5. **Les métadonnées d'éditions ne sont pas génériques.** La supersession repose sur 25 regex écrites à la main. Le mot-clé « rac » donne à tort le domaine « Ambulatoire » à 59 documents, et 114 documents ont au moins un domaine faux, injecté dans le texte indexé.
6. **La fondation a de vraies forces.** Les éléments suivants sont vérifiés et à garder :
   - le parseur de tableaux HTML (rowspan/colspan, continuations de pages) ;
   - BM25+, la normalisation DBSF, les filtres et la recherche dense ;
   - l'exclusion des bibliographies (25 % du corpus) ;
   - la notation déterministe, identique aux scoreurs officiels du benchmark ;
   - les interfaces OpenAI / MCP / ApproachPort, utilisées par d'autres équipes ;
   - une latence compatible avec une démo (250–540 ms par requête de retrieval).
7. **Les plus gros gains attendus ailleurs sont mesurables à faible coût.**
   - **Embedder :** remplacer multilingual-e5-small (MMTEB retrieval 49,3) par Qwen3-Embedding-0.6B (64,6) ou EmbeddingGemma (62,5).
   - **Reranker :** remplacer mmarco-mMiniLM par bge-reranker-v2-m3 ou Qwen3-Reranker.
   - **Recommandations GRADE :** les extraire comme unités indexées et citables.
   - **Chunks :** ajouter des en-têtes de contexte déterministes.
   - **Ordre « U-shape » :** il n'a pas de soutien dans la littérature 2025–2026.

## Problèmes classés par gravité

### Critique — à corriger avant toute optimisation

| # | Problème | Où | Décision |
|---|---|---|---|
| C1 | Contenu du benchmark dans les prompts (exemples de molécules, actes, polarités) | `prompts.py:28-45` | Supprimer les exemples ; garder des règles génériques de format |
| C2 | Exemples et ancres ABP dans CRAG (Q16, Q146 verbatim ; R1.2/R1.5–R1.7 ; molécules) | `crag.py:31-43, 93-109, 129-149, 183-220` | Supprimer les exemples et identifiants ; garder les facettes génériques, à ré-évaluer |
| C3 | Bonus `\bmain\b`, déclencheurs conditionnels « voie antérieure, épaule… » | `pipeline.py:559-560, 586-605` | Supprimer ; généraliser l'extraction « En cas de X » si elle apporte un gain mesuré |
| C4 | Lexique insensible à la casse (« ne pas » → PAS, « rac »…) | `medical_lexicon.py:35, 144` | Correspondance sensible à la casse pour les acronymes ; tests de non-régression |
| C5 | Alerte allergie sur faux positifs, injectée dans le prompt | `client.py:280-286`, `router.py:45` | N'injecter que sur une allergie affirmée, ou supprimer ; mesurer |
| C6 | Sourcing fabriqué par le code | `client.py:372-379` | Mesurer le sourcing avant ajout ; garder l'ajout uniquement comme affichage |
| C7 | Vérificateur limité aux noms de 70 molécules, sans contrôle des doses | `verifier.py` | Vérification affirmation ↔ source (doses, unités) ; phase 3 |
| C8 | Tests unitaires embarquant Q16, Q143, Q146 | `tests/test_rag_sfar.py:567-588` | Remplacer par des exemples synthétiques |

### Important

| # | Problème | Où | Décision |
|---|---|---|---|
| I1 | Supersession par 25 regex manuelles, 170 documents sans lignée | `loader.py` | Lignées génériques (titre normalisé + métadonnées + mentions « remplace ») ; faire valider 2 cas douteux par un clinicien |
| I2 | Domaines imputés par sous-chaîne (« rac » → Ambulatoire, 114 docs faux) | `loader.py` | Correspondance par mots entiers ; ne plus injecter les domaines dans le texte indexé sans mesure |
| I3 | Pénalité pédiatrique par défaut ; règle « (hors X) » qui pénalise le bon document | `pipeline.py` | Ne pénaliser que si la population est affirmée ; mesurer |
| I4 | `final_top_k` non respecté, sortie non triée ; adaptateur avec le mauvais flag | `pipeline.py`, `benchmark_adapter.py:98` | Corriger |
| I5 | Encadrés allergie : 29/29 chunks d'une seule RFE ; 1 551 « notes » qui sont du gras | `chunker.py` | Généraliser ou supprimer selon mesure |
| I6 | Ablation C7→C8 change 5 options à la fois | `ablation.py` | Ablation une variable à la fois |
| I7 | Interfaces : MCP (notifications, `ping`), API (`stream`, `temperature`, erreurs 500 nues) | `mcp_server.py`, `api.py` | Corriger en restant rétrocompatible (contrats : `reports/agents/audit_code_ingestion_generation.md` §5) |
| I8 | Stress-test 30 circulaire (écrit par l'équipe, 3 paraphrases du benchmark, vérité = lignée du système) | `benchmarks.py:91-449` | Ne plus l'utiliser comme mesure ; remplacé par le jeu interne et les benchmarks experts |

### Mineur
Code mort (PgVectorStore jamais appelé, `LIMIT` sans `ORDER BY`), ordre en U dupliqué, `index_dir` par défaut inexistant, erreurs d'initialisation du reranker avalées, tokenizer qui coupe `R1.2.1`, chunks de prose jusqu'à 21 454 caractères.

## Données

Source : `reports/agents/audit_donnees.md` (scripts relançables : `reports/agents/data_audit_scripts/run_all.sh`).

- **Taille réelle.** 267 fichiers Markdown, 264 après déduplication, mais **176 titres distincts et 202 textes principaux en français** : le reste est fait de traductions, d'argumentaires, d'annexes et de textes courts. Le corpus fait environ 5,8 M tokens (médiane ~14 k par fichier). « 264 recommandations » est trompeur.
- **OCR fidèle, défauts réparables.** Sur la seule comparaison possible au PDF (les PDF de `pdfs/` sont des pointeurs Git LFS jamais tirés), 99,6 % des mots et 99,3 % des 881 posologies sont retrouvés. Défauts systématiques :
  - 4 133 formules LaTeX et 586 balises `<math>` ;
  - 2 051 entités HTML (`&gt;` dans les doses) ;
  - 1 707 titres collés au texte ;
  - 1 130 descriptions d'images générées en anglais ;
  - 161 organigrammes Mermaid ;
  - des octets NUL dans 2 documents.

  Il n'y a aucune marque de page : on ne peut pas citer une page depuis le Markdown.
- **La structure GRADE est exploitable, mais pas partout.** Le format SFAR complet (champs, recommandations cotées, accord) couvre 28 % des textes principaux, et 44 % au sens large. La part passe d'environ 4–32 % avant 2015 à 71 % en 2015–2019 et 87 % en 2023–2026 ; 31 % restent narratifs.

  Un prototype d'extraction par regex sort 2 355 recommandations dans 89 documents. L'écart avec le nombre annoncé par le document est inférieur à 10 % pour 25 documents sur 45, et 27 des 30 unités vérifiées sont correctes.

  Piège : dans le gabarit HAS 2024–2026, « Il est recommandé » peut être coté GRADE 2 (171 cas). La force se lit dans la cellule de cotation, pas dans la formulation.
- **Éditions.** Les 44 éditions remplacées sont confirmées, mais seulement 10 sont attestées par le texte et 6 sont douteuses (sepsis, AVK, recommandation BJA). Il y a 2 erreurs : Urgences obstétricales 2010 reste en vigueur malgré la RPP 2022, et une RPP COVID abrogée reste active par son quasi-doublon. L'année de `discovery.json` est parfois la date de mise en ligne.
- **Domaines.** L'imputation par sous-chaîne ajoute de faux domaines à 102 documents (« rac » dans « caractéristiques »).
- **Tableaux.** 2 060 tableaux, tous en HTML. 49 % n'ont pas d'en-tête, mais seulement ~16 % sont des suites de pages (le README dit 49 %). 452 sont des encadrés de recommandation. Les références font 19–26 % du texte.

**Conséquences génériques pour le plan :** nettoyage OCR déterministe (entités, LaTeX simple, NUL, titres collés) ; unités « recommandation » extraites pour les ~90 documents structurés, avec repli sur les chunks ailleurs ; force GRADE lue dans la cotation ; lignées d'éditions recalculées et les 2 erreurs corrigées ; domaines par mots entiers.

## Plan d'amélioration priorisé

Chaque étape est une hypothèse, mesurée sur **dev** contre la meilleure configuration courante, une variable à la fois, avec IC bootstrap. Les tests (`abp171` scellé, jeu interne à venir) ne s'exécutent qu'en fin de phase.

**Étape 0 — Fondation d'évaluation (phase 2, en cours, ne dépend d'aucun choix).**
- Fait : format commun, harnais `rag-sfar-eval --suite --split`, coffre-fort `abp171`, test anti-fuite, ledger API.
- Reste :
  - jeu interne multi-RFE avec vérité terrain au niveau du passage ;
  - sous-ensemble de RFE jamais vues ;
  - liste de questions à faire relire par les médecins ;
  - juge LLM calibré ;
  - baselines équitables (constante, zero-shot au même budget).

**Étape 1 — Version « générique » de C8 (C1–C6, C8).** Retirer en bloc tout ce qui encode le benchmark et corriger les défauts de sécurité. Mesurer C8-générique contre C8 sur `abp171` dev et sur le jeu interne. L'écart sur ABP estime le sur-ajustement ; le jeu interne dit si l'on perd quelque chose ailleurs. C8-générique devient la référence.

**Étape 2 — Simplification.** Ablation composant par composant de C8-générique : CRAG, U-shape, élagage « Provence », canal n-grammes, boost métadonnées, expansion de voisins. Tout composant sans gain mesuré sur le jeu interne est retiré.

**Étape 3 — Hypothèses à fort gain attendu, par ordre de gain/coût.**
1. Embedder Qwen3-Embedding-0.6B / EmbeddingGemma / BGE-M3 (réindexation dans un nouveau dossier).
2. Reranker bge-reranker-v2-m3 puis Qwen3-Reranker-0.6B.
3. En-têtes de contexte déterministes (titre, année, section, statut d'édition) sur chaque chunk.
4. Unités « recommandation GRADE » extraites (énoncé, force, édition, statut) et indexées.
5. Supersession et domaines génériques (I1, I2), mesurés sur les questions temporelles.
6. Nombre de passages et taille de contexte, à la place de l'ordre en U.

**Étape 4 — Génération et vérification.** Prompts génériques, citations par phrase, vérification affirmation ↔ source (doses), abstention calibrée (« sufficient context »). Comparaison de générateurs ouverts déployables : Qwen2.5/3 7B–32B, Mistral Small, Gemma.

**Étape 5 — Pistes exploratoires (phase 4).** Contexte long avec sélection de documents, approche hiérarchique, RAG agentique via MCP, RAFT (sous réserve), baselines frontier. Le tout est rassemblé dans `reports/COMPARAISON_SOLUTIONS.md`.

## Ce qui n'est pas à faire (veille)
Chunking sémantique ou par proposition, GraphRAG/RAPTOR, HyDE, rerank listwise par LLM en ligne, contexte long intégral (corpus ~6 M tokens), Self-RAG, modèles médicaux spécialisés (faibles en français : BioMistral-7B 12,2 % contre Qwen2.5-72B 45,9 % sur MediQAl). Raisons et sources : `reports/agents/veille_sota.md`.

## Blocage en cours
La clé `ANTHROPIC_API_KEY` présente dans l'environnement est refusée par l'API (401). Tout ce qui appelle l'API attend une clé valide : génération et vérification du jeu interne, juge LLM, baselines frontier. Le reste continue avec les modèles locaux.
