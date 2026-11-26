# Audit d'intégrité de l'évaluation — RAG-SFAR

*Audit en lecture seule du dépôt à l'état du 26/11/2026 (commit unique `943e0cd` et modifications non commitées en cours). Aucun appel LLM n'a été fait et aucun calcul lourd n'a été lancé. Les scripts et leurs sorties sont dans `reports/agents/eval_integrity_scripts/`.*

---

## 0. Conclusions classées par gravité

### CRITIQUE : les chiffres phares ne peuvent pas être présentés comme une mesure de généralisation

1. **Le « 100 % (50/50) » est un score sur un jeu de développement.** Le jeu « stratifié 50 » (`run_e2e_eval.py:311-325`, toujours le même tirage déterministe) a servi à itérer : premiers runs 3B à 01:10, modifications de `prompts.py`, `client.py`, `crag.py`, `pipeline.py` et `context_optimizer.py` entre 06:36 et 07:08, puis le run « 100 % » à 07:27. La masterclass le reconnaît elle-même (`scripts/build_masterclass_pdf.py:495-501`) : les corrections visent nommément Q04, Q16, Q28, Q143 et Q167 (*« la suppression des distracteurs QCM + garde-fou (hors main) propulse les QCM de 70 % → 100 % (stratifié) »*). **13 des 50 questions stratifiées** sont ciblées directement par une règle, un exemple de prompt ou un docstring écrits à partir de ces questions. C'est le cas de **seulement 2 questions du jeu « inédites »**.
2. **Les « 50 inédites, jamais observées » ne sont pas tenues à l'écart.** (a) Les 171 questions, ces 50 comprises, ont servi à régler le retrieval : les ablations C0→C8 tournent sur les 171, et `reports/ablation_results.json` liste en `sample_failures` six questions dites « inédites » (Q14, Q34, Q40, Q44, Q111, Q140), corrigées avant le gel du code (Q40 échoue en C6 et réussit en C7/C8). (b) Leur liste n'existait pas dans le code au moment du run : `--ids-file` a été ajouté aujourd'hui, et `reports/repro/*_ids.json` date de 12:55. (c) Le dépôt n'a qu'un commit, donc aucun hash ne prouve l'ordre « gel puis test ». Seul élément favorable : d'après les dates de modification, le run « inédites » (07:37) est postérieur à la dernière modification de `src/` (07:08).
3. **Fuite benchmark → système, mesurée.** Le scan automatique (`leak_scan.py`) trouve **20 lignes de code système** qui partagent un 4-gramme non générique avec **22 questions** du benchmark. Parmi elles, **11 lignes** contiennent des formulations **absentes de la RFE V3.0**, donc copiées du benchmark et non du corpus (14 questions). Le tri manuel (§1) ajoute des fuites sémantiques que le scan ne voit pas :
   - la liste d'exemples de réponse du prompt (`prompts.py:35`) est **exactement l'ensemble des réponses des questions « allergie »** (Clindamycine, Vancomycine, Triméthoprime/Sulfaméthoxazole, Clindamycine + Gentamicine) ;
   - les docstrings CRAG recopient Q16 et Q146 mot pour mot (`crag.py:149`, `crag.py:204-205`) ;
   - le bonus `\bmain\b` (`pipeline.py:559-560`) n'est déclenché que par Q09, Q15 et Q143 ;
   - les tests unitaires reprennent Q16, Q143 et Q146 verbatim (`tests/test_rag_sfar.py:567-588`).
4. **L'« evidence recall 99,3 % » est proche du hasard.** La « preuve » attendue est la chaîne de la réponse elle-même (`benchmarks.py:45-57`), et « Pas d'antibioprophylaxie » est comptée comme preuve dans 59/138 questions. Résultat :
   - **8 chunks tirés au hasard dans la RFE ABP V3.0 donnent déjà 80,7 %** (`metric_triviality.py`, Monte-Carlo, graine fixe) ;
   - le BM25 naïf C0 donne 92,0 % ;
   - pour 101/138 questions, le terme attendu figure dans ≥ 20 % des chunks ABP (« céfazoline » dans 35,6 %, « pas d'antibioprophylaxie » dans 27,8 %).
   
   L'« Allergie Recall 100 % » porte sur **6 questions** (4 sur le stress-test).

### MAJEURE

5. **La généralisation n'est pas testée.** Toute l'évaluation end-to-end porte sur 1 RFE (1/264 documents). Le stress-test `multi_rfe_stress_30` a été écrit par l'équipe dans `benchmarks.py:91-449`, sans annotateur externe :
   - 3 questions paraphrasent le benchmark (M02≈Q04, M03≈Q03, M06≈Q12) ;
   - 12/30 « réponses attendues » ne sont pas des réponses cliniques (« RFE Nutrition clinique 2026. ») ;
   - 7/30 termes-preuves sont des mots du titre présents dans ≥ 30 % des chunks du document cible (« nutrition », « sepsis », « sedation »…) ;
   - 15/30 questions déclenchent une règle codée à la main, par exemple la regex `r1\.2\.[235]` de la facette BLSE (`crag.py:36`) qui correspond aux réponses de M09/M10 ;
   - la vérité terrain « bon document » est le `topic_lineage` **défini par le système lui-même** (`loader.py:257`). L'évaluation est donc circulaire.
6. **« Obsolète Intrusion 0 % » et « Édition Hit 100 % » sont vrais par construction.**
   - C6-C8 activent un filtre dur `latest_edition_only` (`pipeline.py:110-117`).
   - Les 170/264 documents sans lineage sont toujours considérés « en vigueur » : la métrique ne peut pas détecter leur obsolescence.
   - Pour l'ABP, « édition hit » vaut « au moins un chunk ABP V3.0 dans le top-8 » (`expected_min_year=2023`, `benchmarks.py:80-82`).
7. **Les comparaisons avec les baselines sont biaisées ou absentes.**
   - Zero-shot : prompt d'une ligne et 48 tokens (`run_e2e_eval.py:50-59, 305`), contre un raisonnement en 2 étapes, 200/320 tokens et une boucle de réparation pour C8 (`client.py:320-370`).
   - **Aucune baseline n'a tourné sur les « inédites »** : sur ce jeu, répondre toujours « Pas d'antibioprophylaxie » / « C » donne déjà **58 %**.
   - Le « 93 % combiné » mélange jeu de développement et jeu de test.
   - Le « ~75 % des LLM frontières » n'est mesuré nulle part dans le dépôt.
   - Intervalles de confiance à 95 % (Wilson) : 50/50 → [92,9 ; 100] ; 43/50 → [73,8 ; 93,1] ; QCM 11/12 → [64,6 ; 98,5].
8. **Des heuristiques ABP dégradent la sécurité hors benchmark.**
   - L'« ALERTE CLINIQUE : Patient ALLERGIQUE aux bêtalactamines » (`client.py:280-286`) se déclenche sur tout « alternative », « pénicilline » ou « bêtalactamine » (`router.py:45`). Elle part donc à tort sur M07 (« quelle alternative ») et M22 (anaphylaxie).
   - L'acronyme `PAS` → « pneumonie associée aux soins » (`medical_lexicon.py:35`) se déclenche sur « ne nécessite **PAS** d'antibioprophylaxie » (Q140, Q146, Q154, Q166, Q171).

### MODÉRÉE

9. Plusieurs métriques sont à 100 % par artefact :
   - « Sourcing 100 % » : l'année est ajoutée de façon déterministe si le LLM l'oublie (`client.py:372-379`), et le scorer officiel ne cherche qu'un nombre à 4 chiffres.
   - « Grounding 100 % / 0 molécule hallucinée » : c'est mesuré *après* une boucle de réparation qui force la réécriture, et cela ne vérifie que la présence du nom de la molécule dans le contexte (céfazoline est dans 36 % des chunks ABP).
   - Pour les QCM, `evidence_present` = « un chunk ABP en vigueur est présent » (`run_e2e_eval.py:159-165`) : jamais faux en pratique, d'où Q2/Q4 = 0 pour les QCM.
10. Le chiffre « 88 % clin. » repose sur une ré-adjudication manuelle non documentée. Le scorer officiel produit au moins un faux négatif de format : Q98, « Pipéracilline + Tazobactam » contre la référence « Pipéracilline/Tazobactam ».
11. **71/171 questions n'ont jamais été évaluées end-to-end**, dont les réponses rares et difficiles (Q38, Q90, Q108…). Les 8 questions allergie sont toutes dans le jeu de développement ; les « inédites » n'en contiennent aucune.
12. **Édition V2.0 vs V3.0 : aucune réponse de référence ne change** (§5). Les scores ne sont donc pas faussés par l'édition. En revanche, le benchmark ABP **ne teste pas du tout** la gestion temporelle : V2.0 et V3.0 donnent les mêmes réponses, et le système cite « SFAR 2026 » pour des références de 2024.

### Points positifs (à garder)

- Le scorer reproduit **exactement** `OpenScorer`/`QCMScorer`/`SourcingScorer` (`benchmark_adapter.py:14-43` comparé à `data/antibioprophylaxie_benchmark/src/llm_benchmark/domain/scorer.py:16-153`). Le scoring est déterministe, sans LLM-juge.
- Le système n'exploite pas le scorer par sous-chaîne : 1 seule réponse ouverte sur 88 contient 2 réponses candidates (Q65). La faille existe pourtant : une réponse « fusil de chasse » obtiendrait 85,4 % sur les 171.
- L'équipe a elle-même audité la dérive V2→V3 (`scripts/audit_abp_v2_vs_v3.py`), même si la méthode par mots-clés produit des faux positifs (Q92 signalée à cause de « 82 ans »).

---

## Chiffres clés recalculés

| Mesure | Valeur | Source |
|---|---|---|
| Lignes de code système partageant un 4-gramme non générique avec le benchmark | 20 lignes, 9 fichiers, 22 questions | `leak_scan.py` |
| … dont formulations absentes de la RFE V3.0 (copiées du benchmark) | 11 lignes, 14 questions | `leak_scan.py` |
| Réponses de référence exactes (associations) présentes dans le prompt système | 3 (`Amoxicilline/Clavulanate`, `Clindamycine + Gentamicine`, `Triméthoprime/Sulfaméthoxazole`) + noms simples `Clindamycine`, `Vancomycine` | `leak_scan.py`, `prompts.py:35` |
| Questions du stratifié-50 ciblées par une règle/exemple dédiés | 13/50 (Q03, Q04, Q09, Q12, Q16, Q27, Q28, Q43, Q139, Q141, Q143, Q146, Q167) | tri manuel + `rule_coverage.py` |
| Questions des « inédites-50 » ciblées | 2/50 (Q140, Q153) | idem |
| Questions « inédites » visibles dans les listes d'échecs des ablations | 6 (Q14, Q34, Q40, Q44, Q111, Q140) | `reports/ablation_results.json` |
| Evidence recall, 8 chunks ABP V3.0 au hasard | **80,7 %** (C0 naïf : 92,0 % ; C8 : 99,3 %) | `metric_triviality.py` |
| Effectif « Allergie Recall » (retrieval) | 6 questions (ABP), 4 (stress) | idem |
| Baseline constante « Pas d'ABP » + QCM « C » | 46,8 % (171) / 36 % (stratifié) / **58 % (inédites)** | idem |
| Baseline « fusil de chasse » (4 molécules + « Pas d'ABP ») | 85,4 % (171) / 90 % (inédites) | idem |
| Réponses de référence qui changent entre V2.0 et V3.0 | **0/171** (champs adultes, vérifié via le journal des modifications V3.0 et des contrôles ciblés) | §5 |
| Documents sans lineage (jamais « obsolètes » pour la métrique) | 170/264 | SQLite index |
| Encadrés `callout_allergy` hors RFE ABP | 0/29 | SQLite index |

---

## 1. Fuites benchmark → système

### Méthode (`eval_integrity_scripts/leak_scan.py`)
Le script normalise (minuscules, accents retirés) toutes les lignes de `src/`, `scripts/` et `tests/`, puis cherche :
1. les **4-grammes de mots** partagés avec les questions et choix du benchmark, en excluant les 25 4-grammes « gabarit » présents dans plus de 5 questions (« quelle est la recommandation… ») ; chaque correspondance est marquée **BENCH-ONLY** si le 4-gramme est absent du texte de la RFE V3.0, ce qui indique une recopie du benchmark plutôt que du corpus ;
2. les **réponses complètes** (associations et formes avec « / ») ;
3. les **choix QCM** complets ;
4. les **posologies** des choix ;
5. les **3-grammes de titres** de questions.

Le code d'évaluation et de présentation (`benchmarks.py`, `build_masterclass_pdf.py`, `tests/`) est compté à part.

### Résultats (code système uniquement)
- n-grammes : 20 lignes, 22 questions, dont 11 lignes BENCH-ONLY (Q01, Q03, Q04, Q06, Q10, Q12, Q16, Q22, Q27, Q28, Q43, Q139, Q146, Q171) ;
- réponses complètes : 8 lignes (prompts, prompt zero-shot, docstrings CRAG) ;
- titres : 9 lignes (Q04, Q28, Q63, Q108, Q169).

### Tri manuel
- **Faux positifs** : `medical_lexicon.py:11-12` (PTH/PTG, expansions générales) ; `chunker.py:14,567` et `pipeline.py:664` (« en cas d'allergie aux bêtalactamines » est la formulation du corpus) ; `audit_abp_v2_vs_v3.py` (audit, pas le système).
- **Démos contenant des questions du benchmark verbatim** (sans effet sur le score, mais à ne pas présenter comme des cas nouveaux) : `run_clinical_showcase.py:36,40` (Q04, Q28), `interfaces/api.py:144-145`, `quick_demo_queries.py:22-23`.
- **Vraies fuites ayant un effet sur le score** : le scan les attrape en partie (`crag.py:149, 204-205`, `prompts.py:34-35, 42`). Les autres sont sémantiques et détaillées au §2 et dans le tableau final.
- **Exemple cité dans la consigne** (`"C1G": "céphalosporine de première génération céfazoline"`, `medical_lexicon.py:26`) : **aucune question du benchmark ne contient C1G/C2G/C3G** (`rule_coverage.py`), donc ce n'est pas une fuite. C'est de la connaissance pharmacologique générale ; on peut la garder.

---

## 2. Heuristiques taillées pour l'antibioprophylaxie

| Heuristique | Où | Pourquoi elle ne généralise pas |
|---|---|---|
| Encadrés allergie de spécialité (`callout_allergy`) | `chunker.py:37-42, 458-480, 567-605, 635-646` | La regex reprend la formulation des tableaux ABP V3.0. **29/29** encadrés détectés sont dans la RFE ABP ; aucune autre RFE ne produit cette structure. |
| Ancrage « row-card + encadré allergie en [S1]/[S2] » | `context_optimizer.py:107-145` ; `pipeline.py:376, 664-700` | Ne s'active que s'il existe des `callout_allergy`, donc sur l'ABP seulement. Exclure ces encadrés sur les questions sans allergie est aussi un réglage propre à l'ABP. |
| Alerte « Patient ALLERGIQUE aux bêtalactamines » | `client.py:280-286, 436-442` | Déclenchée par `router.py:45` (« alternative », « pénicilline », « bêtalactamine » suffisent). Mauvaise injection sur M07 et M22 et sur toute question d'anaphylaxie ou d'allergie hors ABP. |
| Garde-fous de portée (`hors <site>`, bonus `main`, exceptions conditionnelles) | `pipeline.py:548-560, 564-607` | Le bonus `main` ne cible que Q09/Q15/Q143. La liste `cond_triggers` (voie antérieure, épaule, ouverture articulaire, dure-mère) est la liste des lignes « En cas de… » des tableaux ABP orthopédie/neurochirurgie. |
| Facettes CRAG (BLSE, obésité, rénal, pédiatrie) | `crag.py:31-59` | Les sous-requêtes injectent des molécules et des identifiants de recommandation ABP/IIA (« ertapénème R1.7 R1.2 », « R1.5 R1.6 céfazoline amoxicilline clindamycine »), c'est-à-dire la réponse attendue (Q90, M04, M09, M10). |
| Ancres de sujet | `crag.py:93-109` | Liste fermée de 15 mots tirés des jeux d'évaluation (hanche, genou, colectomie, intra-abdominale, aod…). |
| Sous-requêtes par option QCM / retrait des distracteurs | `crag.py:129-200` | La regex « médicament pur » ne liste que les antibiotiques de l'ABP et « pas d'antibioprophylaxie ». Les docstrings décrivent Q146, Q141 et Q167. |
| Décomposition d'actes composites | `crag.py:140-144, 203-220` | Construite sur Q16 (docstring et test verbatim) ; ne se déclenche que sur Q15 et Q16 dans les 171. |
| Prompts « benchmark » | `prompts.py:28-45` | Règles et exemples écrits à partir des erreurs sur le stratifié (voir tableau). |
| Bonus « diff » sur `"v3.0"` | `pipeline.py:536-546` | Littéral propre à la RFE ABP V3.0. |
| Année effective tirée du nom de fichier (`juin-2026`) | `loader.py:516-519, 622-624` | Règle écrite pour le fichier ABP V3.0. |
| Budgets de contexte par mode benchmark | `client.py:261-262` | 5 chunks / 5 200 caractères en `benchmark_open`, réglés sur le stratifié. |

---

## 3. Métriques : définition, vérité terrain, biais

| Métrique | Calcul (code) | Vérité terrain | Biais |
|---|---|---|---|
| **Evidence recall** | `retrieval_metrics.py:37-41` : tous les `required_evidence_terms` sont-ils présents (sous-chaîne, accents retirés) dans les 8 chunks ? | `benchmarks.py:45-57` : la **réponse de référence découpée sur `+` et `/`**. QCM : aucun terme, donc exclus (138/171 évalués). | Aucune annotation de passage. « Pas d'antibioprophylaxie » et « céfazoline » sont partout, d'où un hasard à 80,7 %. La métrique ne vérifie pas que c'est **la bonne ligne** du tableau. |
| **Édition hit@8** | `retrieval_metrics.py:15-34` : un chunk du bon lineage ou titre, avec `effective_year ≥ expected_min_year` | Lineage et année fixés par l'équipe (`benchmarks.py:80-82` : `antibioprophylaxie`, 2023) ; lineages définis par `loader.py:257` | Circulaire : c'est le système qui définit le bon document. Pour l'ABP, cela revient à « au moins un chunk ABP V3.0 ». |
| **Obsolète intrusion** | `retrieval_metrics.py:104-107` : au moins un chunk avec `is_latest_edition=False` dans le top-k | Graphe de supersession du système (`loader.py:818-852`) | Filtre dur en C6-C8, donc 0 % par construction ; 170/264 documents sont toujours « en vigueur ». |
| **Allergie recall** | Evidence recall restreint à `is_allergy_question` (« allerg » dans la question ou le titre) avec termes | Idem evidence recall | n = 6 (ABP) / 4 (stress) ; 100 % = 6/6. |
| **MRR** | Rang du premier chunk qui satisfait « édition hit » | Idem | Hérite des biais d'« édition hit ». |
| **Exactitude end-to-end** | `benchmark_adapter.py:22-38`, copie exacte du scorer officiel : **sous-chaîne** de chaque molécule (découpée sur `+`), « pas d'antibioprophylaxie » en sous-chaîne, QCM = première lettre A-D | Réponses du benchmark (V2.0, 2024), écrites par une autre équipe : **c'est la seule vérité terrain indépendante** | Déterministe (bon point), mais exploitable par énumération (85,4 %). Faux négatifs de format (Q98). Le « 88 % clin. » est une ré-adjudication manuelle non tracée. Aucun LLM-juge. |
| **RAG-X Q1-Q4, CUE** | `rag_x.py:59-80` sur `evidence_present` × `is_correct` | `evidence_present` = evidence recall (questions ouvertes) ou « un chunk ABP en vigueur » (QCM, `run_e2e_eval.py:159-165`) | Q1 gonflé et Q2 (« coup de chance ») sous-estimé, car la preuve est triviale. |
| **Sourcing** | Présence d'un nombre à 4 chiffres | — | Année ajoutée par le code (`client.py:372-379`), donc 100 % par construction. |
| **Grounding / molécules hallucinées** | `verifier.py:92-150` : molécules de la réponse présentes quelque part dans le contexte | — | Mesuré après la boucle de réparation (`client.py:337-370`). Une mauvaise molécule présente dans le contexte compte comme « ancrée ». |

---

## 4. Jeux « 50 inédites » et `multi_rfe_stress_30`

**« 50 inédites » (`reports/e2e_heldout_unseen_50_7b.json`)**
- **Construction.** Il s'agit d'un échantillonnage systématique décalé d'un cran par rapport au stratifié pour les questions ouvertes (Q02, Q07…), plus les QCM Q140-Q157 non retenus. La règle n'est pas dans le code de l'époque : la liste d'identifiants n'existe que depuis le 26/11 à 12:55.
- **Fuite.** Toutes ces questions ont servi au réglage du retrieval (ablations sur les 171, échecs visibles pour 6 d'entre elles). Elles sont donc « inédites » seulement pour le prompt et la génération.
- **Composition.** Aucune question allergie. Le jeu est plus facile pour une réponse constante (58 % contre 36 % sur le stratifié), donc les deux jeux ne sont pas comparables.
- **Sans baseline.** Ni zero-shot ni C0 n'ont tourné sur ce jeu : on ne peut pas y attribuer de gain au système.
- **Point favorable.** Le run date de 07:37, après la dernière modification de `src/` (07:08) : un seul passage, a priori sans réglage ensuite. Ce n'est pas prouvable sans historique git.

**Stress-test 30 (`stress_test_audit.py`)**
- **Auteur.** L'équipe système (`benchmarks.py:91-449`), sans relecture clinique tracée.
- **Recopies.**
  - 10/30 questions contiennent une séquence de ≥ 8 mots recopiée du document cible ; par exemple M26 recopie 17 mots, M25 en recopie 14.
  - 9/30 réponses attendues contiennent ≥ 6 mots copiés du document.
  - Ces recopies avantagent le retrieval lexical.
- **Alignement sur le système.**
  - 15/30 questions déclenchent une règle codée à la main : routeur temporel (M29, M30), facettes CRAG (M04, M05, M09, M10, M16, M23, M27), identifiant de recommandation (M01), routeur allergie (M02, M03, M04, M06, M07, M22).
  - M09/M10 correspondent à la regex `r1\.2\.[235]` ; M04 exige le terme `r1.6`, que la facette obésité injecte.
- **Vérité terrain faible.** 12/30 réponses attendues ne sont qu'une référence (« RFE … 2026. ») ; les termes-preuves de 7/30 questions figurent dans ≥ 30 % des chunks du document ; M08 exige le terme « 3 ».
- **Recouvrement avec le benchmark ABP.** M02 ≈ Q04, M03 ≈ Q03, M06 ≈ Q12.

---

## 5. Édition du benchmark : V2.0 (2024) contre V3.0 (2026)

- **Les deux éditions en présence.** Le benchmark se réfère à la « RFE SFAR 2024 (V2.0 du 22/05/2024) » (`metadata.yaml`). Le corpus contient la V3.0 du 04/05/2026, marquée en vigueur, et les éditions 2017 et 2018, marquées obsolètes. **La V2.0 n'est pas dans le corpus.**
- **Ce qui change en V3.0.** Le journal des modifications officiel de la V3.0 liste 11 changements par rapport à la V2.0 : obésité R1.5.2/R1.6, prolongation post-opératoire chez l'allergique, posologie de la valve Zéphyr, alternative allergie en chirurgie d'affirmation de genre, intitulé « vaginoplastie », encadré allergie main, intitulés des hernies, lien ECBU AFU, délais de la fosfomycine, Champ 3 pédiatrique.
- **Contrôles ciblés.** Comparaison du texte `pdftotext` de la V2.0 avec le Markdown de la V3.0 sur les 19 questions signalées par l'audit de l'équipe, plus les questions allergie :
  - Q63 : Amoxicilline/Clavulanate inchangé (seul l'intitulé est reformulé) ;
  - Q100, Q101, Q161 : Céfazoline / pas d'ABP inchangés ; le périmètre s'élargit (ombilicale, hiatale) ;
  - Q108, Q109, Q160 : fosfomycine-trométamol inchangée ; le délai passe de « au moins 2 h » à « 2 à 4 h » ;
  - Q28 : TMP/SMX inchangé, prolongation ajoutée ;
  - Q04 : exception voie antérieure identique ;
  - Q09, Q15, Q143 (sans allergie) : non concernées ;
  - Q92 : faux positif de l'audit de l'équipe (« 82 ans » correspond à la regex pédiatrique).
- **Résultat : 0 réponse de référence sur 171 ne change.** Aucune question ne porte sur l'obésité, la Zéphyr ou la pédiatrie.
- **Limite.** Le diff mot à mot automatique (`edition_diff.py`) est inexploitable comme décompte : la mise en page du PDF intercale les colonnes et produit 460 régions « modifiées » qui sont des artefacts. La conclusion repose sur le journal officiel et sur les contrôles ciblés.
- **Impact sur les scores annoncés.**
  - Les scores ne sont ni gonflés ni pénalisés par l'écart d'édition.
  - En revanche, aucune des 171 questions ne peut distinguer V2.0 de V3.0. Les métriques temporelles sur l'ABP (édition hit, intrusion) ne mesurent donc pas la capacité à choisir la bonne édition.
  - L'éventuel gain du filtre temporel par rapport aux éditions 2017/2018 n'a pas été quantifié question par question.
  - Les réponses citent « SFAR 2026 » pour une vérité terrain de 2024 ; c'est acceptable puisque les réponses sont identiques, mais il faut le dire.

---

## 6. Ce qu'il faut pour une évaluation honnête (par priorité)

1. **Corriger la communication tout de suite.** Retirer « 100 % (50/50) » comme résultat ; présenter le stratifié comme **jeu de développement**. Retirer « jamais observées » et « ~75 % frontier ». Ne plus combiner développement et test.
2. **Geler et tracer.** Commiter, taguer le code, et publier le hash *avant* tout run de test ; écrire le hash dans chaque rapport.
3. **Jeu de test indépendant et scellé.**
   - 60 à 100 questions rédigées par des cliniciens extérieurs à l'équipe (jury, SFAR), sur au moins 5 RFE hors ABP ;
   - réponse et **passage-preuve** (document, page ou ligne de tableau) annotés indépendamment ;
   - inclure des questions hors périmètre, des allergies hors ABP (anaphylaxie) et des questions temporelles dont la réponse **a changé** entre éditions ;
   - hash publié avant le run, une seule exécution.
4. **Ablation « générique contre spécifique ».** Désactiver en bloc les éléments du tableau ci-dessous marqués « supprimer » ou « généraliser » (exemples du prompt, bonus `main`, `cond_triggers`, alerte allergie, docstrings-règles, molécules dans les facettes). Mesurer C8-générique contre C8 sur les 171 et sur le jeu indépendant : l'écart estime le sur-ajustement.
5. **Évaluer end-to-end les 171 questions** avec, sur le **même** jeu : baseline constante, zero-shot **à prompt, budget de tokens et raisonnement identiques**, C0 et C8. Rapporter des intervalles de confiance de Wilson et un test de McNemar apparié.
6. **Réparer les métriques.**
   - Evidence recall : passage ou ligne gold annotés, et baseline de hasard rapportée à côté.
   - Exclure « pas d'antibioprophylaxie » comme preuve.
   - QCM : une preuve par option.
   - Intrusion : mesurée sans filtre dur et sur tous les documents datés.
   - Sourcing : mesuré **avant** l'ajout automatique, et en vérifiant que l'édition citée est la bonne.
   - Grounding : mesuré avant la réparation, plus le taux de réparations déclenchées.
7. **Scorer.** Garder le scorer officiel comme métrique primaire. Publier en parallèle une adjudication par 2 cliniciens en aveugle, avec kappa, pour les écarts de format (Q98), et pénaliser les réponses à plusieurs molécules candidates.
8. **Corriger les deux défauts de sécurité** (alerte allergie par faux positif, acronyme `PAS`) et ajouter des tests de non-régression hors ABP.
9. **Remplacer les tests unitaires** qui embarquent des questions du benchmark (Q16, Q143, Q146) par des exemples synthétiques.
10. **Stress-test.** Le faire réécrire ou relire par un tiers, avec de vraies réponses cliniques et des termes-preuves non triviaux. Retirer M02, M03 et M06, qui doublonnent le benchmark.

---

## 7. Tableau des éléments suspects

Les décisions possibles sont : **garder** (avec justification générique), **généraliser** ou **supprimer**.

| # | fichier:ligne | Extrait | Question(s) du benchmark | Décision proposée |
|---|---|---|---|---|
| 1 | `src/rag_sfar/generation/prompts.py:32` | « si 2 actes chirurgicaux sont associés, vérifie CHAQUE acte et retiens la molécule si au moins l'un des deux indique une antibioprophylaxie » | Q16, Q15 | **Généraliser** : règle clinique à faire valider par un médecin, puis tester sur des actes combinés nouveaux. |
| 2 | `prompts.py:33` | « N'applique JAMAIS une exception conditionnelle (« ouverture articulaire », « geste difficile », « temps opératoire long », « voie antérieure », « épaule ») » | Q04, Q140, lignes ortho | **Généraliser** : « n'applique une ligne conditionnelle que si sa condition figure dans la question », sans liste. |
| 3 | `prompts.py:34` | « (ex. PTH voie antérieure ou prothèse d'épaule) … « Si amoxicilline/clavulanate : ... » vs « Si céfazoline : ... » … 1re intention (jamais la 2e intention) » | Q04, Q140, Q28, Q03, Q27, Q141 | **Supprimer** les exemples ; garder la règle générique « appliquer l'encadré de la même spécialité ». |
| 4 | `prompts.py:35` | « (ex : Céfazoline, Amoxicilline/Clavulanate, Clindamycine, Vancomycine, Triméthoprime/Sulfaméthoxazole, Clindamycine + Gentamicine) » | Q03, Q04, Q12, Q27, Q28, Q43 (= toutes les réponses allergie) | **Supprimer** les molécules ; garder le format « molécule ou association ». |
| 5 | `prompts.py:41-42` | « proposition CORRECTE, INCORRECTE … intervention SANS antibioprophylaxie » ; « « plaie de la main » vs « hors main », « genou » vs « hanche voie antérieure » » | Q143, Q15, Q141, Q04, Q140, Q146, Q162 | **Supprimer** les exemples ; garder « repérer la polarité de la question ». |
| 6 | `prompts.py:28-45` (modes `benchmark_*`) | Prompts dédiés au format du benchmark | toutes | **Garder** (adaptateur de format officiel) mais **sans contenu clinique**, et figé avant le test. |
| 7 | `src/rag_sfar/generation/client.py:280-286` (et `436-442`) | « ⚠️ ALERTE CLINIQUE : Patient ALLERGIQUE aux bêtalactamines/pénicillines. Ne donne PAS la molécule de 1re intention » | Q03, Q04, Q12, Q27, Q28, Q43, Q141, Q167 ; faux positifs M07, M22 | **Généraliser** : n'injecter que sur une allergie affirmée, dans le domaine ABP ; sinon **supprimer**. |
| 8 | `client.py:372-379` | « Deterministic provenance attachment … (SFAR {year} [S1]) » | toutes (Sourcing) | **Garder** pour l'interface, **mais** mesurer le Sourcing avant l'ajout. |
| 9 | `client.py:261-262` | `gen_max_chunks = … 5 if mode == "benchmark_open"`, `5200` | toutes | **Garder** en le déclarant comme hyperparamètre réglé sur le jeu de développement. |
| 10 | `src/rag_sfar/retrieval/crag.py:31-37` | facette BLSE : « … carbapénème ertapénème R1.7 R1.2 », regex `r1\.2\.[235]` | Q90 ; M09, M10 | **Supprimer** molécules et identifiants de la sous-requête ; garder la facette « BLSE » générique. |
| 11 | `crag.py:38-43` | facette obésité : « … R1.5 R1.6 céfazoline amoxicilline clindamycine » | M04 (terme exigé `r1.6`) | **Supprimer** identifiants et molécules ; garder la facette. |
| 12 | `crag.py:93-109` | ancres « antibioprophylaxie, intra-abdominale, …, colectomie, hanche, genou… » | Q01, Q03, Q90, M-ABP/IIA | **Généraliser** : ancres tirées des titres ou du lexique du corpus. |
| 13 | `crag.py:129-138` | `_PURE_DRUG_OR_DOSAGE_RE` = antibiotiques ABP + « pas d'antibioprophylaxie » | Q139, Q141, Q143, Q153, Q167, Q169 | **Généraliser** : liste de molécules issue d'un référentiel (ATC). |
| 14 | `crag.py:147-149` | « 'Parmi ces interventions ORL... A. Implant cochléaire B. Amygdalectomie...' » | Q146, Q171 | **Supprimer** l'exemple ; **garder** la méthode, à ré-évaluer sur des QCM nouveaux. |
| 15 | `crag.py:183-187` | « `A. Amoxicilline/Clavulanate`, `B. Céfazoline`, `C. Clindamycine`, `D. Vancomycine` … Chirurgie Cardiaque or PTG » | Q141, Q167 | **Supprimer** l'exemple ; **garder** la méthode (générique), à tester hors ABP. |
| 16 | `crag.py:140-144, 203-220` | split « associée à », « et la pose d'un » ; docstring « splénectomie d'hémostase associée à la pose d'un fixateur externe sur fracture fermée du fémur » | Q16 (verbatim), Q15 | **Généraliser** et valider sur des questions composites écrites par un tiers ; supprimer l'exemple. |
| 17 | `src/rag_sfar/retrieval/pipeline.py:559-560` | `if re.search(r"\bmain\b", q_fold) … boost += 0.35` | Q09, Q15, Q143 | **Supprimer** (règle anatomique ad hoc). |
| 18 | `pipeline.py:548-558, 579-584` | exclusion `hors <site>` dans l'intitulé de section | Q143, Q15 | **Garder** : analyse générique d'une exclusion explicite ; à évaluer hors ABP. |
| 19 | `pipeline.py:586-605` | `cond_triggers` : voie antérieure, épaule, ouverture articulaire, dure-mère | Q04, Q140, lignes ortho et neurochirurgie | **Généraliser** : extraire la condition « En cas de X » et la comparer à la question ; sinon **supprimer**. |
| 20 | `pipeline.py:539` | `if "historique des versions" in sec_lo or "v3.0" in txt_lo: boost += 0.55` | M29 | **Supprimer** le littéral « v3.0 ». |
| 21 | `pipeline.py:376, 664-700` ; `context_optimizer.py:107-145` | liaison et ancrage « specialty_allergy_box » en [S1]/[S2] | 8 questions allergie | **Garder** en le présentant comme **spécifique ABP** (29/29 encadrés), pas comme générique. |
| 22 | `src/rag_sfar/ingestion/chunker.py:37-42` | `ALLERGY_BOX_RE` (« si antibioprophylaxie indiquée », « chirurgie prothétique… ») | allergie ABP | **Garder** (tiré du corpus, pas du benchmark), avec la même mention de spécificité. |
| 23 | `src/rag_sfar/ingestion/loader.py:516-519, 622-624` | `if "juin-2026" in fn_low or "2026" in fn_low` ; contrôle « V3.0 antibioprophylaxie added pediatric Champ 3 » | — (édition ABP) | **Généraliser** : date lue dans la page de garde et le journal des modifications. |
| 24 | `src/rag_sfar/retrieval/router.py:45` | `"allergy": … alternative\w* | b[êe]talactamine\w* | p[ée]nicilline\w*` | Q03…Q167 ; faux positifs M07, M22 | **Généraliser** : séparer « allergie » de « alternative ». |
| 25 | `src/rag_sfar/retrieval/medical_lexicon.py:35` | `"PAS": "pneumonie associée aux soins"` | Q140, Q146, Q154, Q166, Q171 (déclenchement à tort) | **Généraliser** : exiger le contexte, ou exclure « PAS d' ». |
| 26 | `medical_lexicon.py:26-28` | `"C1G": "céphalosporine de première génération céfazoline"` (+ C2G, C3G) | aucune (0 question ne contient C1G/C2G/C3G) | **Garder** : connaissance pharmacologique générale, pas une fuite. |
| 27 | `medical_lexicon.py:11-12, 19` | PTH, PTG, AMO | aucune directement (la question écrit l'expression en toutes lettres) | **Garder** : acronymes usuels. |
| 28 | `src/rag_sfar/evaluation/benchmarks.py:45-57` | `required_evidence_terms` = réponse découpée sur `+` et `/` | 138 questions ouvertes | **Généraliser** : passage gold annoté indépendamment ; exclure « pas d'antibioprophylaxie ». |
| 29 | `benchmarks.py:80-82` | `expected_topic_lineage="antibioprophylaxie"`, `expected_min_year=2023` | 171 | **Généraliser** : édition gold annotée hors système. |
| 30 | `benchmarks.py:91-449` | stress-test de 30 questions | M02≈Q04, M03≈Q03, M06≈Q12 | **Supprimer** M02, M03, M06 ; **faire réécrire** le reste par un tiers. |
| 31 | `src/rag_sfar/evaluation/retrieval_metrics.py:104-107` | intrusion = `not r.chunk.is_latest_edition` | 171 + 28 | **Généraliser** : mesurer sans filtre dur ; rapporter le filtre comme une contrainte, pas comme un score. |
| 32 | `scripts/run_e2e_eval.py:159-165` | QCM : `ev_ok = any(latest and "antibioprophylaxie" in title)` | 33 QCM | **Supprimer** : remplacer par une preuve par option. |
| 33 | `run_e2e_eval.py:50-59, 305` | zero-shot : une ligne, `--max-tokens 48` | toutes | **Généraliser** : même prompt, même budget et même raisonnement que C8, contexte vide. |
| 34 | `run_e2e_eval.py:311-325` | tirage stratifié qui inclut 100 % des questions allergie | 8 allergie | **Garder** comme jeu de **développement** déclaré ; ne pas l'appeler résultat. |
| 35 | `tests/test_rag_sfar.py:567-588` | Q146 (énoncé et choix), Q143 (choix), Q16 (énoncé) verbatim | Q16, Q143, Q146 | **Supprimer** : remplacer par des exemples synthétiques. |
| 36 | `scripts/run_clinical_showcase.py:36,40` ; `src/rag_sfar/interfaces/api.py:144-145` ; `scripts/quick_demo_queries.py:22-23` | démos = Q04, Q28, Q03 verbatim | Q03, Q04, Q28 | **Garder** comme démos, **mais** ne pas les présenter comme cas nouveaux. |
| 37 | `README.md:121-124` ; `scripts/build_masterclass_pdf.py:465-468, 478, 495-501` | « 50 questions 100 % inédites jamais observées », « ~75 % frontier », « 93 % combiné » | — | **Supprimer** ou corriger ces affirmations (voir §6.1). |

---

## Annexe : scripts (lecture seule, reproductibles)

| Script | Rôle | Sortie |
|---|---|---|
| `eval_integrity_scripts/leak_scan.py` | n-grammes, réponses, choix, posologies et titres du benchmark retrouvés dans `src/`, `scripts/`, `tests/` | `leak_scan_results.json`, `leak_scan_stdout.txt` |
| `eval_integrity_scripts/metric_triviality.py` | Hasard pour l'evidence recall, baselines constantes, effectifs allergie, sourcing | `metric_triviality_results.json` |
| `eval_integrity_scripts/rule_coverage.py` | Questions qui déclenchent chaque règle codée à la main | `rule_coverage_results.json` |
| `eval_integrity_scripts/stress_test_audit.py` | Recopie du corpus, trivialité des preuves, alignement sur les règles, recouvrement avec l'ABP | `stress_test_audit_results.json` |
| `eval_integrity_scripts/edition_diff.py` | Diff V2.0 (PDF) contre V3.0 (Markdown) ; **bruité**, à utiliser seulement pour repérer des zones | `edition_diff_results.json` |

Lancement : `python3 -I …/leak_scan.py` et `python3 -I …/edition_diff.py <dossier_tmp>` (stdlib seule) ; `HF_HUB_OFFLINE=1 .venv/bin/python …/{metric_triviality,rule_coverage,stress_test_audit}.py` (lecture SQLite en mode `ro`, aucun modèle chargé).

**Limites de l'audit**
- Les dates de modification des fichiers servent d'indice chronologique ; il n'y a pas d'historique git.
- La comparaison V2/V3 repose sur le journal officiel et sur des contrôles ciblés, pas sur un alignement ligne à ligne des tableaux.
- Le classement « ciblé par une règle » (13 contre 2) est un tri manuel, appuyé sur `rule_coverage.py` et les mentions explicites de la masterclass.
