# R2 — Revue indépendante du retrieval B1 (`C10_context_population`)

Date : 2026-11-27. Relecteur : agent R2 (Opus), qui n'a pas écrit le code relu. Référentiel : `CLAUDE.md`, `<principes_non_negociables>`. Objet : commits `482a678`, `2a5525b`, `3e8c552` (branche `rag-sfar-v2`) et `reports/agents/B1_retrieval.md`.

Périmètre : **dev uniquement** (aucun `test.jsonl` ouvert ni évalué), index `tas_v3_errata`. Deux sources :
- les lignes par question sauvegardées par B1 (`…/scratchpad/res/*.json`, contexte complet : identifiants de chunks et raison d'expansion), **non commitées** ;
- mes relances sur HEAD (`reports/agents/R2_annexes/r2eval.py`, lancé sous `scripts/with_gpu_lock.sh R2`) : C9, C10 et cinq variantes « C10 moins une règle » sur les trois jeux dev, sauvegardées dans `reports/agents/R2_annexes/res/`.

Scripts d'analyse (aucun modèle chargé) : `reports/agents/R2_annexes/a1_reproduce.py` à `a9_loo.py`. « Vérifié » = recalculé, ou lu dans le code ou les données ; « inféré » = mon interprétation.

## Synthèse

| Question | Verdict |
|---|---|
| 1. Surapprentissage | Aucun vocabulaire ABP dans le code (vérifié). Mais deux règles sont **génériques dans leur formulation et spécifiques à l'ABP dans leur effet** : le quota de population avec contrepartie (la structure « tableaux adulte et pédiatrique parallèles » n'existe à l'échelle que dans l'ABP : 1 document sur 153 à tableaux) et le quota QCM = 2 (gain = Q171 seule). Les notes de tableau et la levée du plafond par document sont génériques. |
| 2. Généralisation | Hors ABP, la donnée disponible (multirfe dev) ne montre **aucun gain de C10 sur le critère « passage dans le contexte »** (100 → 98,7). Avec des métriques plus strictes, la levée du plafond est **positive** (part du document gold +4 pts [+2,1 ; +5,9] ; rang gold ≤ 16 sur les questions « table » +23 pts) ; le quota de population est **du bruit** hors ABP (38 ajouts sur 41 sans rapport avec le gold, 18 des 20 ajouts pédiatriques viennent d'un autre document que le gold). Rien ne peut être dit sur les QCM hors ABP ni sur les questions à deux documents (3 en dev). |
| 3. Sécurité du contexte | Filtre d'édition intact sur tous les chemins (vérifié, 0 chunk remplacé hors requêtes comparatives d'éditions). Paires « même acte, conduite adulte ≠ pédiatrique » dans le contexte : 21 → 34 questions abpe171 (WN → C10) ; le texte des deux lignes ne les distingue que dans 3 cas sur 34, seul l'intitulé de section (montré dans l'en-tête de source) le fait toujours. Le quota de population ajoute surtout des **lignes d'un autre acte avec leur posologie** (38/43 ajouts pédiatriques sur abpe non pertinents). Seuil de couverture 0,2 : choisi et évalué sur les mêmes données (in-sample). |
| 4. Code | Pas de bug bloquant. C9 strictement inchangé (298/298 contextes identiques avant/après, vérifié), C10 déterministe et reproduit (298/298). Défauts : passages garantis hors budget de caractères, doublons de contenu non dédupliqués sur les chemins d'expansion, notes rattachées au mauvais tableau possibles, test « ne peut qu'ajouter » plus faible que ce qu'il prétend. |

Chiffres B1 : **tous les chiffres principaux se reproduisent** à partir des lignes sauvegardées (§5). Mais ces lignes ne sont pas dans le dépôt : en l'état, les tableaux de B1 ne sont pas reproductibles depuis les artefacts commités.

## 1. Constats classés par gravité

### Élevé 1 — Le quota de population ajoute surtout des passages hors sujet, y compris des posologies d'un autre acte (sécurité clinique, surapprentissage)

`src/rag_sfar/retrieval/pipeline.py:719-746` (`_guaranteed_extras`, branche population).

Preuves (vérifiées, `a2_rules.py`, `a3_show.py`, `a4_ce.py` sur les lignes C10 de B1) :

| Jeu dev | Questions où la règle ajoute un passage pédiatrique / adulte | Ajouts couvrant une preuve ou le passage gold | Ajouts venant d'un document gold | Questions où l'ajout est nécessaire (retrait post hoc → perte) |
|---|---|---|---|---|
| abpe171 (n = 102) | 43 / 14 | 5/43 / 2/14 | 43/43 / 14/14 | 3 (Q07, Q28, Q44) |
| abp171 (n = 102) | 45 / 16 | 4/45 / 3/16 | 45/45 / 16/16 | 0 |
| multirfe_synth (n = 94) | 20 / 21 | 0/15 / 1/14 (évaluables) | **2/20 / 7/21** | 0 |

Chaque ajout entraîne ses fenêtres (tableau parent, voisins, notes) : en moyenne 4,6 chunks et 2,3 k caractères par déclenchement sur abpe171 (199 chunks, 101 k caractères pour 43 déclenchements pédiatriques).

Lecture de 30 ajouts (extraits dans `R2_annexes`, `a3_show.py`) :
- ABP : l'ajout pédiatrique est presque toujours **une autre ligne** que l'acte demandé, avec sa posologie : « transplantation hépatique » → ligne CPRE « Lithotritie mécanique biliaire … Céfoxitine 40 mg/kg » (Q99) ; « lithotritie extra-corporelle » → « Adénoïdectomie … PAS D'ANTIBIOPROPHYLAXIE » (Q115) ; « prothèse totale de hanche » → « Chirurgie des parties molles sans implant » (Q01) ; « brachioplastie » → « Septorhinoplastie » (Q135). Cause : il n'existe souvent pas de ligne pédiatrique pour cet acte, et le quota prend quand même la meilleure ligne pédiatrique disponible.
- Hors ABP : tableaux pédiatriques sans rapport, issus d'étiquettes `population_hint` bruitées de `tas_v3_errata` : échelle de fragilité clinique (trauma crânien), durées d'archivage du dossier (avis cardiologique), grille de douleur post-amygdalectomie (anxiété préopératoire en chirurgie thoracique), tableau VNI (pancréatite), ligne ABP « Otoplastie » (IVG), posologie de dexaméthasone pédiatrique (question d'abstention MR-abst002). Les questions obstétricales sont traitées comme « population non précisée » : 3 sur 7 reçoivent un passage « pédiatrique » hors sujet.
- Le score cross-encoder des ajouts ne protège pas : sur ABP il est ≥ 0,97 pour la plupart des ajouts **non pertinents**, parce que la requête de contrepartie contient les 300 premiers caractères de la ligne adulte (même structure « Actes … | Molécules … | Dose … ») ; hors ABP il est bas (médiane 0,009 ; 31 ajouts sur 41 < 0,2).

Structure du corpus (vérifié sur `tas_v3_errata`, chunks en vigueur) : sur 153 documents ayant des tableaux, 9 ont des chunks de tableau étiquetés à la fois adulte et pédiatrique, et un seul en a en nombre (ABP : 319 adulte / 218 pédiatrique ; le suivant : 8 adulte). La justification « les RFE ont des tableaux adulte et pédiatrique parallèles » décrit l'ABP, pas le corpus.

Recommandation : ne pas figer C10 avec cette règle telle quelle. Version généralisée à mesurer (une seule variable, dev) : (a) ne la déclencher que si le **document du premier résultat** contient des tableaux des deux populations (pas « les documents des 3 premiers résultats ») ; (b) chercher la contrepartie avec la question seule, sans le texte de la ligne adulte, et exiger un recouvrement du libellé d'acte ou un plancher cross-encoder calculé sur la question seule ; (c) ne pas étendre les passages garantis par fenêtre (tableau parent, voisins). Si cette version ne garde pas Q07/Q28/Q44 sans bruit, retirer la règle et traiter l'ambiguïté de population côté génération (le prompt de B3 demande déjà de « donner la conduite de chaque cas » quand la population manque).

### Élevé 2 — Le quota QCM = 2 repose sur une question, et les sous-requêtes cherchent dans tout le corpus

`pipeline.py:713-716`, `config.py:136`, `ablation.py:282` (C10 : `mcq_option_quota=2`).

Vérifié : la règle se déclenche sur les 10 QCM de abpe171 dev (toutes ABP, multirfe n'a aucun QCM) ; 19 passages ajoutés, 5 pertinents ; le retrait post hoc ne fait perdre qu'une question (Q171). B1 a mesuré quota 1 = +0 et quota 2 = +1 (Q171) : la valeur 2 est choisie sur cette question. Les sous-requêtes utilisent le masque global, pas les documents de tête : ajouts lus hors sujet (cataracte → ligne « rachis » ; Q163 → briefing « Facteurs humains » d'un autre document ; Q159 → note d'anticoagulants d'une autre RFE).

Recommandation : retirer `mcq_option_quota` de la configuration figée (laisser le code, désactivé) tant qu'aucun jeu de QCM hors ABP ne le mesure ; si on le garde, quota 1, restreint aux documents des premiers résultats. C'est le cas d'école du principe 1 (option conservée sur une question du benchmark).

### Moyen 3 — Notes de tableau : idée générique, rattachement bruité

`pipeline.py:757-783` (`_table_notes`), appelée pour chaque chunk de tableau des 8 premiers résultats et des passages garantis (`:578-581`).

Vérifié : sur abpe171 la règle ajoute 489 notes pour 101 questions (≈ 5 par question, 2,1 k caractères), 8 couvrent une preuve, 3 questions en ont besoin (Q05, Q07, Q157) ; multirfe : 40 notes sur 27 questions, 0 pertinente sur 26 évaluables, aucune perte. Les notes ABP sont souvent celles d'un autre tableau ou d'une autre population (Q69, annexectomie adulte → note « entérocolite » du tableau néonatal ; Q28 → note sur les voies biliaires). Hors ABP, les `callout_footnote` liés à l'ingestion comprennent des adresses d'auteur (« \* Auteur correspondant … ») et des références bibliographiques (« \*Maisels … J Perinatol »). Contrairement au rapport B1 (« Les encadrés allergie n'en font pas partie »), 41 notes sur abpe171 sont des `callout_allergy` (début « # … ») : le chemin « paragraphes qui suivent le tableau » ne filtre pas le type de chunk. Le parcours « jusqu'à la fin du tableau » (`:768-776`) traverse les `table_markdown` suivants : pour 2 224 fiches ligne sur 6 110 de l'index, il passe par un autre tableau avant d'atteindre les notes, qui peuvent donc appartenir au tableau suivant (inféré : dans l'ABP ce sont souvent des suites de pages du même tableau, mais rien ne le garantit).

Recommandation : garder (gain sur 3 questions, aucune perte hors ABP, justification typographique générale) mais **généraliser** : n'attacher que les notes dont l'appel (*, **, #) figure dans la ligne retrouvée, s'arrêter au premier `table_markdown` rencontré, exclure les chunks qui ressemblent à une référence ou à une adresse. Mesurer le contexte économisé.

### Moyen 4 — Seuil de couverture choisi et évalué sur les mêmes données

`config.py:147` (`coverage_threshold=0.2`), `pipeline.py:624-644`, `reports/agents/B1_annexes/coverage.py`.

Vérifié (recalcul à partir de `D16P1C__*.json` et `ood_D16P1C.json`) : 2/280 positifs signalés à tort, 28/30 hors domaine et 9/18 abstentions détectés, comme annoncé. Mais : (a) le seuil est issu d'un balayage sur ces mêmes 328 requêtes puis rapporté sur elles (in-sample) ; (b) le plus bas positif hors ABP est à 0,233 (MR-g659a…) et deux requêtes hors domaine sont à 0,234 et 0,255 : 0,2 est posé juste sous un point de données, la marge réelle est inconnue ; (c) les 280 « positifs » comptent deux fois les mêmes 102 questions ABP (abpe171 et abp171) ; (d) les 30 requêtes hors domaine sont triviales (recettes, pneus, impôts), pas des questions médicales voisines du périmètre.

Recommandation : garder le signal comme indicatif (c'est le cas : `coverage_gate="off"` par défaut). Ne pas l'utiliser en mode `refuse` avant une évaluation sur des requêtes non vues : abstentions du benchmark enrichi, requêtes médicales hors anesthésie. Rapporter les chiffres actuels comme « calibration in-sample ».

### Moyen 5 — Plafond par document levé : générique et mesuré, effet sur les questions à deux documents non mesurable

`src/rag_sfar/evaluation/ablation.py:276` (C10 : `max_chunks_per_doc=16`).

Vérifié : le plafond 7 est contraignant dans 101/102 questions abpe171 et 55/94 multirfe (plus de 7 résultats classés d'un même document dans C10). Sur multirfe (WN → C10, notes constantes) : part du contexte venant du document gold +4,0 pts [+2,1 ; +5,9] ; questions `table` : rang gold ≤ 16 parmi les résultats classés 69 → 92 % (+23 pts [0 ; +46], n = 13) ; nombre de documents distincts 6,0 → 5,4. Effet secondaire mesuré : davantage de lignes adulte et pédiatrique d'un même acte dans le contexte (constat 6). Les questions à deux documents (3 `comparison` en dev) ne bougent pas ; les requêtes comparatives d'éditions utilisent leur propre plafond (`max_per_doc=3`, `pipeline.py:452-463`) et ne sont pas touchées. On ne peut rien conclure sur les questions qui croisent deux RFE : n = 3.

Recommandation : garder. Ajouter au jeu interne quelques questions croisant deux RFE avant le test scellé, ou documenter la limite.

### Moyen 6 — Lignes adulte et pédiatrique du même acte côte à côte

Vérifié (`a7_popsafety.py`, fiches ligne de sections « adultes » et « pédiatriques », libellé d'acte similaire à ≥ 50 %, molécule ou dose différente) :

| Config | abpe171 : questions avec une telle paire | abp171 |
|---|---|---|
| WN (C9 + fenêtres + notes) | 21 / 102 | 25 / 102 |
| C10 | 34 / 102 | 39 / 102 |

Dans les 34 cas abpe171, l'intitulé de section (« … par disciplines adultes » / « … pédiatriques et néonatales ») distingue toujours les deux lignes ; le texte du chunk ne le fait pour les deux lignes que 3 fois, pour l'une des deux 25 fois (surtout via « mg/kg »). L'en-tête de source montre la section (format legacy : `Section : …` ; format structuré : ligne `(Section : …)` ou `Population (titre de section)`), donc le générateur a l'information, à condition de la lire. L'augmentation vient surtout du plafond levé, pas du quota (3 paires seulement passent par un ajout de population). Inféré : sur `tas_v4`, où `populations` est faux pour ~700 chunks (R1), l'en-tête structuré afficherait une population fausse ; cette protection dépend donc de `tas_v5`.

Recommandation : mesurer en génération (B3) le taux de réponses qui donnent la dose pédiatrique pour un adulte ou l'inverse sur ces 34 questions ; ajouter au texte des fiches ligne la population du tableau (ingestion), comme B2 l'a fait pour la sous-catégorie.

### Faible 7 — Défauts de code sans effet mesuré en dev

- Budget : les passages garantis ne sont pas soumis à `context_char_budget` (`pipeline.py:546-548`, puis `_window_expand` ne fait que réduire le budget des fenêtres). Sonde synthétique : budget 10 caractères, 182 caractères renvoyés. En dev, maximum 29 996 caractères : sans effet. Recommandation : imputer les passages garantis au budget, ou plafonner explicitement leur nombre.
- Le budget des fenêtres est calculé après ajout des passages garantis (`:571`) : un passage garanti inutile (étiquette fausse) réduit les fenêtres des résultats classés. Le rapport B1 dit « le pire cas est un passage inutile de plus » : en réalité un passage garanti apporte aussi son tableau parent, ses voisins et ses notes (4,6 chunks en moyenne sur abpe171), et prend du budget aux résultats classés.
- Doublons de contenu : 32 contextes C10 (32 pour WN, 13 pour C9 + fenêtres) contiennent deux chunks au texte identique sous deux identifiants (surtout notes et `callout_allergy` répétés, fiches ligne présentes deux fois dans l'index) : le défaut vient des notes, pas du quota. `dedup_by_content` ne s'applique qu'à la sélection classée. Recommandation : dédupliquer par texte normalisé à la sortie de `_window_expand`.
- Le quota compte « déjà présent » par identifiant : si le tableau parent (qui contient la ligne) est retrouvé, la ligne correspondante peut encore être ajoutée, et inversement (sonde synthétique : quota adulte rempli par le `table_markdown` alors que la ligne est déjà là).
- Après la sélection côté génération du preset `wide` (40 chunks / 30 000 caractères), 11 contextes abpe171 et 12 abp171 dépassent 40 chunks : les passages garantis, placés en fin de liste, sont les premiers coupés. Sans perte de suffisance en dev (vérifié, `a8_genbudget.py`), mais la « garantie » n'en est une qu'au niveau du retrieval ; avec le preset `small` (6 chunks), elle disparaît.
- `_table_notes` s'arrête après 200 pas : sur un tableau de plus de 200 fiches, les notes ne sont jamais trouvées (silencieux).
- Test `test_population_quota_only_adds_and_survives_wrong_labels` (`tests/test_b1_retrieval.py`) : il vérifie la propriété sans fenêtres, sans reranker ni dense, avec `final_top_k=2`. La propriété est vraie par construction pour la liste classée (`selected[:final_top_k]` est calculée avant les ajouts, `pipeline.py:538-548`) et je l'ai vérifiée sur les données : aucun résultat classé de C10 ne disparaît. Mais le test ne couvre ni l'effet sur le budget des fenêtres ni le cas C10 réel. Recommandation : un second test avec `context_window=1`, `expand_table_parent=True` et un budget serré, qui vérifie que les fenêtres des résultats classés sont identiques avec ou sans quota.
- Reranker désactivé : `_focused_search` retombe sur la RRF seule, `coverage_*` vaut −1 (lu dans le code et vérifié par le test existant) : correct.
- Performance : chaque passage garanti coûte une recherche BM25 sur tout l'index, un encodage dense et 16 paires cross-encoder ; un QCM à 5 options et une population non précisée = 7 recherches. Latence médiane C10 314 ms selon B1 (non remesurée en isolement).

## 2. Question 1 — Surapprentissage, règle par règle

Vocabulaire : aucun terme d'acte, de molécule ou de question dans le code B1 (`query_tools.py`, nouveaux blocs de `pipeline.py`, `config.py`), vérifié par lecture et par recherche. Le test anti-fuite passe (17 tests B1 + fuite verts).

| Règle / constante (C10) | Fichier:ligne | Déclenchement dev (abpe / abp / multirfe) | Pertinence de ce qu'elle ajoute | Justification | Verdict | Reco |
|---|---|---|---|---|---|---|
| k = 16, ±1 voisin, tableau parent, fenêtres sur 8 (A1) | `pipeline.py:562-620` | toutes les questions | gain mesuré hors ABP (multirfe 85,5 → 100) | structure générale (petits chunks, tableaux) | générique | garder |
| `max_chunks_per_doc=16` | `ablation.py:276` | contraignant 101 / 101 / 55 | part du document gold +4 pts multirfe | une question = une RFE en général | générique | garder |
| `attach_table_notes`, `table_notes_max_chars=1200`, `_NOTE_START_RE`, 2 paragraphes, 200 pas | `pipeline.py:69-71, 757-783` | 101 / 101 / 27 questions | 8/489, 0/503, 0/26 notes pertinentes ; 3 questions abpe en dépendent | convention typographique des notes | générique, implémentation bruitée | généraliser (appel de note de la ligne) |
| `population_quota=1`, `population_tables_only=True`, documents des 3 premiers résultats | `pipeline.py:718-746` | 43+14 / 45+16 / 20+21 ajouts | 7/57, 7/61, 1/29 | « tableaux parallèles » = ABP seulement (1 document sur 153) | **surappris dans l'effet** | généraliser avec garde-fous, sinon retirer |
| `population_counterpart` (texte de la ligne adulte, 300 car.) | `pipeline.py:731-743` | idem | rend le cross-encoder aveugle (≥ 0,97 sur des ajouts faux) | idem | **surappris** | retirer, ou remplacer par recouvrement de libellé d'acte |
| `mcq_option_quota=2` | `pipeline.py:713-716`, `ablation.py:282` | 10 / 10 / 0 | 5/19, 6/22, n/a ; 1 question gagnée (Q171) | quota 2 = adulte + pédiatrique (ABP) | **surappris** (Q171) | retirer de la config figée |
| `_MCQ_OPTION_RE` (A–H, lettres consécutives) | `query_tools.py:17-30` | 10 QCM | — | format QCM générique | générique | garder |
| `_focused_search` pool 16, mélange 0,68 / 0,32 | `pipeline.py:657-683` | — | — | recopie le mélange du passage principal (`:429`), sans les pénalités de population | générique | garder ; noter l'absence des pénalités |
| Négation (`patient_negated_spans`, listes `_PATIENT_NOUN`, `_STOP_WORDS`…) | `query_tools.py:33-118` | désactivé dans C10 | — | règles de forme du français, pas de contenu ; `devant` en double dans `_STOP_WORDS` | générique, inutilisé | laisser désactivé |
| `coverage_threshold=0.2` | `config.py` | exposé seulement | — | calibré in-sample (constat 4) | limite | garder indicatif |

## 3. Question 2 — Généralisation mesurée

### 3.1 Métriques plus strictes sur multirfe dev (WN → C10, lignes B1 ; `a6_general.py`)

WN = C9 + fenêtres + notes (même réglage que C9 + fenêtres, avec notes). La différence WN → C10 = plafond levé + quota de population (multirfe n'a pas de QCM).

| Groupe (multirfe dev) | n | Passage dans le contexte | Rang gold ≤ 8 (résultats classés) | Rang gold ≤ 16 | Part du doc gold | Chunks hors doc gold | Caractères |
|---|---|---|---|---|---|---|---|
| tout | 94 (76 avec gold) | 100 → 98,7 | 85,5 → 86,8 | 92,1 → 94,7 | 43,1 → 47,1 % (+4,0 [+2,1 ; +5,9]) | 14,8 → 14,9 | 20,3 k → 21,6 k |
| `table` | 13 | 100 → 100 | 69 → 77 | 69 → 92 | +6,6 pts | 13,6 → 12,8 | |
| `clinical_case` | 21 | 100 → 95,2 | 76 → 76 | 95 → 90 | +2,9 pts | 17,2 → 18,3 | |
| doc gold avec tableau pédiatrique | 11 | 100 → 90,9 | 72,7 → 72,7 | 100 → 90,9 | +2,9 pts | 16,0 → 17,0 | |
| doc gold sans tableau | 23 | 100 → 100 | = | = | +2,5 pts | 17,6 → 18,5 | |
| question pédiatrique | 10 avec gold | 100 → 90 | = | 100 → 90 | +2,0 pts | 17,2 → 18,5 | |

Lecture (inférée, confirmée par l'ablation du §3.2) : le gain générique (part du document gold, rang des questions `table`) et la seule perte (MR-ga95d : le passage gold, faiblement lié, sort du contexte quand le document dominant prend toutes les places) viennent du plafond levé ; le quota de population n'y change rien en suffisance, il ajoute des chunks (surtout hors document gold).

### 3.2 Ablation « C10 moins une règle » (mes relances, HEAD)

Chaque ligne = C10 contre C10 sans la règle (différence appariée, IC bootstrap 95 %), sur HEAD, `tas_v3_errata` (`a9_loo.py`, sortie complète dans `R2_annexes/loo_output.txt`). « Part du doc gold » = part des caractères du contexte venant d'un document gold.

| Règle retirée | abpe171 suffisance (n = 96) | abp171 passage | multirfe passage (n = 76) | Caractères ajoutés par la règle (abpe / multirfe) | Part du doc gold (abpe / multirfe) | Latence médiane |
|---|---|---|---|---|---|---|
| quota de population (avec contrepartie) | +3,1 [0 ; +7,3] (Q07, Q28, Q44) | 0 | 0 | +1 235 / +862 | +0,9 / −0,3 pt | +260 ms ABP, +27 ms multirfe |
| contrepartie seule | +2,1 [0 ; +5,2] (Q07, Q28) | 0 | 0 | +386 / −12 | +0,2 / 0 | +10 ms |
| notes de tableau | +3,1 [0 ; +6,2] (Q05, Q07, Q157) | 0 | 0 | +1 880 / +195 | +0,6 / 0 | ≈ 0 |
| plafond par document (16 → 7) | +4,2 [+1,0 ; +8,3] (Q28, Q41, Q74, Q149) | +1,0 (Q74) | **−1,3 (MR-ga95d)** | +240 / +389 | **+16,8 / +4,2 pts** | ≈ 0 |
| quota QCM (2 → 0) | +1,0 [0 ; +3,1] (Q171) | 0 | 0 (aucun QCM) | +334 / 0 | −0,4 / 0 | ≈ 0 |

Lecture : hors ABP, **aucune règle n'apporte de gain mesurable** et une seule coûte (le plafond, une question à passage gold discutable) ; seules la levée du plafond et, marginalement, les notes rendent le contexte plus concentré sur le document gold. Le quota de population coûte 0,9 k caractères et 1,5 chunk par question multirfe sans rien gagner. Q28 dépend à la fois du plafond, du quota et de la contrepartie (retirer l'un des trois la perd) : les gains ne sont pas additifs et la somme des lignes surestime l'effet total.

### 3.3 Ce que les données peuvent et ne peuvent pas montrer

- Peuvent : les pertes et le bruit hors ABP (multirfe a 70 RFE), les effets de concentration sur le document gold, le rang des passages gold.
- Ne peuvent pas : un **gain** de suffisance hors ABP (multirfe est saturé à 100 % dès C9 + fenêtres) ; l'effet des QCM hors ABP (aucun QCM) ; les questions croisant deux RFE (3) ; une validation « leave-documents-out » de C10 (toutes les règles ont été réglées en regardant ABP et multirfe dev ; aucune RFE dev n'a été tenue à l'écart). Les questions multirfe sont synthétiques et non validées médicalement ; le gold est un passage unique, ce qui sous-estime la pertinence des ajouts (un ajout peut être utile sans être « le » passage gold) : les taux de pertinence ci-dessus sont des bornes basses, mais la lecture directe de 30 ajouts confirme qu'ils sont en majorité hors sujet.
- Le gain principal annoncé (+10,4 pts sur abpe171) est réel sur ces 96 questions mais porte sur un seul document, avec des règles conçues après lecture de ses échecs dev : le test scellé abpe171 mesurera la même famille de questions, pas la généralisation.

## 4. Question 3 — Sécurité clinique du contexte

- **Filtre d'édition (vérifié).** Les recherches ciblées (population, QCM) passent par le masque global (`pipeline.py:662-670`, `restrict = mask & …` en `:725`). Voisins, tableau parent et notes ne passent pas par le masque mais restent dans le document de l'ancre (`doc_id` testé), et les attributs filtrés (`is_latest_edition`, `is_active`, langue) sont constants à l'intérieur de chaque document de l'index (0 document mixte). Sur les 9 611 chunks des contextes C10 dev, 31 sont d'une édition remplacée, tous dans 3 questions multirfe de comparaison d'éditions (`temporal_mode = all_versions`, `current_edition_required = False`) : attendu. Aucun chunk abrogé, aucun chunk de bibliographie. Les notes liées (`linked_callout_ids`) ne sont pas contrôlées par le masque : sans effet aujourd'hui (même document), à garder en tête si l'ingestion lie un jour des notes entre documents.
- **Deux conduites pour le même acte** : constat 6 (21 → 34 questions abpe171 ; l'en-tête de section les distingue, le texte rarement).
- **Posologies d'un autre acte ajoutées par le quota** : constat 1.
- **Couverture** : constat 4. B1 annonce 9/18 abstentions in-domain détectées : reproduit, mais in-sample.

## 5. Reproductibilité des chiffres de B1

Recalcul avec `harness.paired_bootstrap_diff` et `bootstrap_ci` sur les lignes sauvegardées de B1 (`a1_reproduce.py`) :

| Chiffre du rapport B1 | Recalcul R2 |
|---|---|
| abpe171 suffisance C9 / C9+fenêtres / C10 : 83,3 / 88,5 / 99,0 | 83,3 [76–91] / 88,5 [82–95] / 99,0 [97–100] |
| C10 − (C9 + fenêtres) : +10,4 [+4,2 ; +16,7], 10 gagnées, 0 perdue | +10,4 [+4,2 ; +16,7], 10 / 0 |
| rappel des preuves +6,7 [+2,7 ; +11,3] | idem |
| abp171 +1,0 [0 ; +2,9] (Q74) ; multirfe −1,3 [−3,9 ; 0] (MR-ga95d) | idem |
| `tas_v4` : abpe171 +5,2 [+1,0 ; +9,4] ; abp171 0 ; multirfe 0 | idem |
| Contexte moyen C10 20 139 caractères | 20 139 (moyenne sur les 298 lignes) |
| Couverture : 2/280, 28/30, 9/18 | idem (in-sample, constat 4) |
| C9 inchangé quand les options sont coupées | **vérifié** : contextes C9 identiques 298/298 entre une exécution antérieure à B1 (`reports/eval/20261127-0145*_b2_base.json`) et HEAD |
| C10 reproductible | **vérifié** : C10 relancé sur HEAD = lignes B1, 298/298 contextes identiques ; deux exécutions B1 de la même config (`C10_M2`, `C10`) identiques 204/204 |

Non reproduit / non vérifiable : les latences (machine partagée, non remesurées) ; tous les tableaux d'ablation de B1 ne sont reproductibles que depuis le scratchpad de session, qui n'est pas dans le dépôt et peut être effacé. Recommandation : commiter les lignes par question de C9, C9W, WN, D16P1C, C10 (quelques Mo) sous `reports/agents/B1_annexes/res/`, ou les régénérer avec `rag-sfar-eval` pour qu'elles vivent dans `reports/eval/`.

## 6. Ce qui doit changer avant de figer la configuration pour le test scellé

1. Retirer `mcq_option_quota=2` de C10 (ou le remplacer par une version mesurée, quota 1 restreint aux documents de tête). Raison : une question.
2. Quota de population : soit la version restreinte (document du premier résultat ayant des tableaux des deux populations, requête sans le texte de la ligne adulte, pas de fenêtre sur le passage garanti), mesurée sur dev contre C10 sans population ; soit retrait. La configuration figée ne doit pas ajouter des posologies d'autres actes sur 40 % des questions ABP.
3. Notes : ne rattacher que les notes appelées par la ligne retrouvée ; s'arrêter au tableau courant ; filtrer références et adresses.
4. Dédupliquer par texte à la sortie du contexte ; imputer les passages garantis au budget.
5. Geler et documenter le seuil de couverture comme « calibré in-sample » ; l'évaluer sur des requêtes non vues avant tout usage `refuse`.
6. Commiter les lignes par question qui fondent les chiffres du rapport B1.
7. Pour la généralisation : ajouter au jeu interne `eval_internal/` quelques QCM et questions à deux RFE hors ABP, et tenir à l'écart au moins quelques RFE (leave-documents-out) avant de régler à nouveau. Remesurer sur `tas_v5`.

Chaque point est un changement à mesurer seul sur dev (principe 5) ; je n'ai rien modifié dans `src/`.

## 7. Fichiers

- Rapport : `reports/agents/R2_revue_retrieval.md`.
- Pilote et scripts : `reports/agents/R2_annexes/r2eval.py`, `common.py`, `a1_reproduce.py` (chiffres B1), `a2_rules.py` (déclenchement, pertinence, nécessité post hoc), `a3_show.py` (lecture des ajouts), `a4_ce.py` (scores cross-encoder des ajouts), `a5_edition.py` (éditions, doublons), `a6_general.py` (métriques strictes), `a7_popsafety.py` (paires adulte / pédiatrique), `a8_genbudget.py` (sélection côté génération), `a9_loo.py` (ablation par règle et identités).
- Résultats de mes relances : `reports/agents/R2_annexes/res/*.json`, journal `r2eval.log`.
