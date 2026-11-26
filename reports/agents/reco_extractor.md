# Extracteur générique des recommandations cotées (unités « recommandation »)

*2026-11-26. Module `src/rag_sfar/ingestion/reco_extractor.py`, script `scripts/extract_recommendations.py`, tests `tests/test_reco_extractor.py`, sortie `data_derived/recommendations.jsonl` (4,2 Mo) et `data_derived/recommendations_stats.json`. Relance : `HF_HUB_OFFLINE=1 .venv/bin/python scripts/extract_recommendations.py` (environ 8 s de CPU, sans GPU ni API). Ce n'est pas encore l'indexation.*

## Chiffres clés

| Mesure | Valeur |
|---|---:|
| Documents parcourus (FR + bilingues, hors traductions, en vigueur ou non) | 241 |
| Documents avec au moins une unité | **130** (117 avec 5 unités ou plus) |
| Unités extraites | **3 933** |
| Unités « primaires » (hors doublons du même texte dans un document frère de la même édition) | 3 579 (354 doublons marqués `duplicate_of`) |
| Unités d'éditions en vigueur (`is_latest_edition`) | 3 575 (3 221 primaires, 115 documents) |
| Avec identifiant (R1.2, RP 3.1, Recommandation 12, Encadré 4.1…) | 2 684 |
| Avec accord d'experts (fort, faible, relatif, professionnel) | 2 462 |
| Avec champ / question PICO | 1 608 / 1 493 |
| **Précision mesurée sur 40 unités tirées au hasard (graine 99)** | **37/40 = 92,5 %** (IC 95 % de Wilson ≈ 80–97 %) |
| **Écart au nombre annoncé** (49 documents qui annoncent « … a abouti à N recommandations ») | **écart relatif médian 2,6 %** ; 40/49 à 10 % ou moins ; 45/49 à 20 % ou moins ; 18 exacts |

Répartition des forces (toutes unités / primaires) :

| Force normalisée | Toutes | Primaires |
|---|---:|---:|
| `grade_1_plus` | 574 | 486 |
| `grade_1_minus` | 167 | 148 |
| `grade_2_plus` | 585 | 536 |
| `grade_2_minus` | 142 | 125 |
| `expert_opinion` | 1 207 | 1 062 |
| `no_recommendation` | 23 | 16 |
| `unknown` | 1 235 | 1 206 |

Source de la force : la cotation du document pour 2 431 unités, la formulation pour 310 (repli, voir plus bas), aucune pour 1 192. Les `unknown` viennent surtout des documents cotés par le seul accord (RAND/UCLA, accord professionnel) ou par l'ancienne gradation A/B/C : leur cotation n'a pas d'équivalent GRADE, et l'extracteur ne l'invente pas.

Par période (année effective du document) :

| Période | Documents | Avec unités | Unités | GRADE 1/2 | Avis d'experts | Inconnue |
|---|---:|---:|---:|---:|---:|---:|
| 2000-2004 | 30 | 5 | 60 | 0 | 17 | 43 |
| 2005-2009 | 38 | 14 | 658 | 127 | 4 | 527 |
| 2010-2014 | 32 | 19 | 755 | 234 | 151 | 367 |
| 2015-2019 | 56 | 40 | 854 | 449 | 216 | 188 |
| 2020-2022 | 31 | 16 | 392 | 116 | 255 | 21 |
| 2023-2026 | 53 | 36 | 1 214 | 542 | 564 | 89 |

Couverture par format (classement des textes FR de l'audit des données, `reports/agents/audit_donnees.md` § 4.3) : GRADE SFAR complet 57/57 documents (1 628 unités) ; RPP / avis d'experts numérotés 20/20 (506) ; cotation d'accord seule 22/22 (1 057) ; GRADE sans identifiants 14/16 (317) ; gradation ancienne A/B/C 9/28 (328, seulement quand ces documents portent aussi un accord ou un AE) ; narratif 5/94 (13 unités).

Le prototype de l'audit donnait 2 355 recommandations dans 89 documents, 25/45 documents à moins de 10 % du nombre annoncé et 27/30 unités correctes.

## Mesure de qualité

### Nombre annoncé

`declared_recommendation_count()` lit la phrase de méthode « … ont abouti à / ont permis d'établir N recommandations » (chiffres ou nombres en lettres, texte entier). Le compte extrait est celui du document après déduplication interne. Écarts restants au-delà de 20 % :

- optimisation hémodynamique 2024 (24 annoncées, 13 extraites) : le document ne contient que 13 identifiants R distincts (le nombre annoncé couvre sans doute aussi la version pédiatrique) ;
- RPP bêta-lactamines 2018 (21/26), tenue vestimentaire 2021 (13/16) : sous-recommandations R1.2.1/R1.2.2 comptées une fois par le document ;
- sédation procédurale 2026 (33/26) : les 27 identifiants présents dans l'OCR sont tous extraits ; le reste manque au Markdown.

Les cas où le document se trompe sur son propre total ne sont pas corrigés : la mesure reste brute.

### Échantillons vérifiés à la main

Critères : (a) l'unité est une vraie recommandation cotée du document, pas un faux positif ; (b) l'énoncé contient tout le texte coté, sans texte d'une autre recommandation ni de l'argumentaire ; (c) la force normalisée est juste au regard de la cotation lue autour (ou `unknown` quand le document n'en donne pas d'équivalent GRADE). J'ai lu le Markdown autour de chaque `char_span`.

J'ai corrigé l'extracteur entre les échantillons, avec des règles génériques uniquement. Chaque tirage porte donc sur une version différente :

| Échantillon | Version | Correctes | Erreurs |
|---|---|---:|---|
| A, graine 2026 | intermédiaire | 34/40 | 2 énoncés de liste tronqués, 1 bloc fusionnant deux recommandations, 1 phrase méta (« Ces recommandations devront être réactualisées… »), 1 énoncé de puce tronqué, 1 force « (Grade AE) » non lue |
| B, graine 7 | intermédiaire | 36/40 | 1 commentaire de relecteur (tableau Delphi), 1 fusion par phrases collées par l'OCR, 1 énoncé suivi de l'argumentaire collé, 1 item de liste sans sa phrase d'introduction |
| C, graine 11 | intermédiaire | 37/40 | 1 force inventée par la formulation alors que la cotation est « Grade C », 1 énoncé coupé par un saut de page, 1 item de liste sans les items non cotés qui le précèdent |
| **D, graine 99** | **finale** (avant les 3 derniers correctifs) | **37/40** | 1 cotation « (GRADE 2–) ACCORD FORT**Argumentaire** » collée, donc non lue (force `unknown` au lieu de `grade_2_minus`) ; 1 fusion de deux propositions numérotées (« « Accord fort »13) … ») ; 1 énoncé qui annonce une liste citée entre guillemets sans l'inclure |

Les trois erreurs de D ont ensuite reçu un correctif générique (gras collé, numéro de proposition collé après une cotation, liste citée après « : »), vérifié sur ces trois unités. Mais aucun nouveau tirage n'a été fait après : 92,5 % est la dernière mesure, pas celle de l'état final exact. Dans D, aucun faux positif ; deux défauts mineurs comptés comme corrects : un « ): » en tête d'énoncé (depuis nettoyé) et un accord manqué derrière « Accord FORT**Argumentaire ».

Sur les 160 unités vérifiées, aucune erreur de **sens** de la force (pour / contre) n'a été trouvée. Le piège du gabarit HAS est bien traité : « il est recommandé » coté 2 donne `grade_2_plus` (D-34, C-8).

## Règles utilisées

Toutes découlent de la structure générale des recommandations SFAR. Aucune ne vise un document ou une question. Aucun module existant n'a été modifié : le nouveau n'importe que pydantic et la bibliothèque standard.

1. **Segmentation** en blocs avec leurs positions dans le Markdown (`char_span`, ligne). Les frontières sont les lignes, les cellules `<td>`, les `<br>`, les `</p>` et les `</li>`, avec suivi tableau / rangée / cellule. On ajoute deux frontières pour des artefacts OCR courants : un identifiant en gras collé au paragraphe précédent (`…383-7**R2.3 –`) et un titre Markdown collé (`…).## 2.4`).
2. **Unités à identifiant** (`labelled`, 2 401 unités) :
   - identifiant en tête de bloc ou seul dans une cellule : `R1.2.3`, `R 2.4`, `RP 3.1`, `Recommandation 12`, `Encadré 4.1` ;
   - identifiant sans « R » perdu par l'OCR (`5.1.3 – …`) : accepté seulement dans un document déjà numéroté en R et suivi d'une cotation ;
   - l'énoncé suit l'identifiant. Il se poursuit dans la même cellule, sur la liste qui suit un « : » (y compris une liste citée) et après un saut de page (minuscule en tête) ;
   - la cotation est lue dans les blocs courts qui suivent (`GRADE 2+ (Accord fort)`, `(Grade 2-) Accord FORT`, `Avis d'experts`, `AVIS D'EXPERTS (accord fort)`, `ABSENCE DE RECOMMANDATION`), dans la même rangée de tableau (cellules nues `1`, `2`, `1+`, `AE` du gabarit HAS) ou en fin d'énoncé (`… (GRADE 1+, accord fort)`) ;
   - si un identifiant de question précède un identifiant de recommandation, on garde l'identifiant interne.
3. **Lignes de tableau sans identifiant** (`table_row`, 54 unités) : une cellule de formulation (« il est recommandé », « les experts suggèrent »…) suivie d'une cellule de cotation dans la même rangée.
4. **Énoncés à cotation en ligne** (`inline_rating`, 1 478 unités), pour les documents sans identifiants (moins de 3 identifiants distincts ; au-delà, les phrases cotées sans identifiant sont de l'argumentaire, des légendes ou des tableaux de posologie) :
   - phrase terminée par une cotation : `(G1+)`, `(GRADE I – Accord fort)`, `(Avis d'experts) Accord fort`, `(AE)`, `(recommandation forte, niveau modéré de certitude)` ;
   - ou précédée d'une cotation : `(G1+) Il est recommandé…` ;
   - dans les documents cotés par accord (au moins 5 mentions), cotation d'accord seule : `(accord fort)`, `« Accord fort »`, `[Accord fort]`, `(accord professionnel)`.

   Le découpage est fait par phrase. Les phrases non cotées qui précèdent la phrase cotée dans le même paragraphe lui sont rattachées (1 500 caractères au plus). Un item de liste coté reçoit sa phrase d'introduction et les items non cotés qui le précèdent.
5. **Rejets génériques** :
   - définitions de l'échelle de cotation (« G1+ = il faut faire », formulations entre guillemets) ;
   - questions (terminées par « ? ») ;
   - énoncés de moins de 5 mots ou surtout numériques ;
   - lignes de tableaux de vote Delphi (au moins 2 cellules numériques) ;
   - identifiants cités dans une autre colonne que la première (tableaux de commentaires de relecteurs) ;
   - première personne (« je », « me ») ;
   - phrases méta sur le texte lui-même ;
   - prose de type « aboutissant à un avis d'experts » ;
   - entrées de bibliographie ;
   - énoncés en anglais (traductions incluses dans un document FR).
6. **Force** (`strength`, `strength_raw`, `strength_source`) :
   - la cotation prime. `GRADE 1/2` ou `I/II` avec signe donne `grade_x_plus` ou `grade_x_minus` ; sans signe (gabarit HAS `1` / `2`, `GRADE 2 (accord fort)`), le **sens** vient de la formulation négative (« il n'est pas recommandé », « de ne pas », « il ne faut pas »…), le **niveau** de la cotation. « Recommandation forte » vaut 1, « faible / conditionnelle » vaut 2. `AE` / « avis d'experts » donne `expert_opinion`. « Absence / pas de recommandation » et « ne permettent pas d'émettre de recommandation » donnent `no_recommendation` ;
   - sans cotation, une formulation « les experts suggèrent / proposent » donne `expert_opinion` ;
   - la formulation « il faut (probablement) », « il est (probablement) recommandé » ne donne un grade que si la méthode du document définit les formulations à la manière SFAR classique (« il faut faire » = GRADE 1+). C'est exclu si le document suit le gabarit HAS (« recommandation faible, qualité des preuves élevée »), car « Il est recommandé » peut y être GRADE 2. Dans ce cas, la force reste `unknown` ;
   - une ancienne gradation (Grade A/B/C) est conservée dans `strength_raw` et donne `unknown`, jamais un GRADE.
7. **Accord** : « accord / consensus fort, faible, relatif, modéré, professionnel », normalisé dans `agreement` (brut dans `agreement_raw`).
8. **Contexte** : `field` est le dernier titre « Champ n » (y compris dans une rangée `colspan` du gabarit HAS), `section` la dernière « Question … » ou ligne PICO, `heading` le dernier titre Markdown.
9. **Doublons** :
   - dans un document, même identifiant et texte proche (Jaccard ≥ 0,5 ou inclusion) ou, sans identifiant, Jaccard ≥ 0,9. Deux identifiants différents ne sont jamais fusionnés, parce que les RFE répètent une même phrase type pour plusieurs populations ;
   - entre documents de la même famille et de la même année (texte court / long / argumentaire), l'unité est marquée `duplicate_of`, pas supprimée. La copie gardée est celle du texte de recommandations.
10. **Nettoyage de `statement`** :
    - entités HTML, y compris doublement échappées (`&amp;gt;`) ;
    - `<math>` et `$…$` simples : `\geq`→≥, `\leq`→≤, `\times`, `\text{}`, `^2`→², indices ;
    - balises HTML, `<sub>` / `<sup>`, gras / italique Markdown, images `![…](…)` ;
    - octets NUL, apostrophes typographiques, normalisation NFC, espaces, phrases collées par l'OCR (`fin.Début`), puces doublées (`- - `).
11. **Identité** : `unit_id = {doc_id}:{label|u}:{sha1(énoncé normalisé)[:8]}`. Il est stable d'une exécution à l'autre, mais change si l'énoncé nettoyé change, par exemple après une évolution des règles de nettoyage. `extract_corpus()` lit `index/table_aware_sota/metadata.sqlite` (table `documents`) en lecture seule. On peut aussi lui passer une liste de documents (`documents=`).

## Erreurs restantes et limites connues

- **Énoncés non autonomes.** Dans les textes cotés phrase par phrase (accord seul, 2005-2014), une proposition peut commencer par un pronom (« Il est contre-indiqué chez l'insuffisant respiratoire sévère » pour le phénobarbital). L'énoncé correspond exactement au texte coté, mais il faut le titre (`heading`) pour le comprendre. À l'indexation, préfixer le titre et le champ.
- **Fusion après une liste** : un item de liste collé par l'OCR à la recommandation suivante (« …du dialysat.La structure… ») est encore fusionné (cas observé une fois).
- **Accord manqué** quand la cotation est collée à un mot en gras suivi d'une minuscule.
- **Résidus de cosmétique OCR** : numéros de proposition sans espace (`14 –La …`), appels de note collés (`(2009)5`), « (NGP fort) » laissé dans l'énoncé.
- **Force `unknown` pour les RPP sans mention par unité** : quelques propositions de RPP (COVID 2022) ne portent que « Accord FORT » sans « les experts suggèrent ». Elles restent `unknown`, alors que le type de document (RPP) implique un avis d'experts. Aucune inférence au niveau du document n'est faite.
- **Tableaux de posologie de l'antibioprophylaxie** (« ●●● (GRADE 2) » par acte chirurgical) : ils ne sont pas extraits comme unités. Le document annonce 11 recommandations (R1.x), toutes extraites, mais les centaines de lignes acte × molécule cotées restent dans les chunks de tableau.
- **Doublons inter-éditions** : seuls les doublons de la même édition (famille et année) sont marqués. Une même recommandation reprise d'une édition à la suivante reste en deux unités, distinguées par `year` et `is_latest_edition`, ce qui est voulu.
- **Mesure** : le dernier tirage (D) ne porte pas exactement sur l'état final (3 correctifs après). Aucune mesure de rappel unité par unité n'a été faite : le rappel n'est approché que par le nombre annoncé (49 documents).

## Ce qui n'est pas couvert : documents narratifs et gradations anciennes

- **94 textes FR narratifs** (surtout 2000-2014 et documents « unknown ») : aucune cotation par énoncé, donc 5 documents seulement avec unités (13 unités, à traiter comme suspectes). Pour ces textes, le RAG doit continuer à s'appuyer sur les chunks.
- **Gradation A/B/C** (28 textes, ANAES / HAS / SFAR 1999-2012) : 9 seulement ont des unités, quand ils portent aussi un accord ou un AE. Une phrase suivie de « (grade B) » n'est pas extraite seule, car sans identifiant le risque de faux positif dans l'argumentaire est élevé. La force resterait de toute façon `unknown`.
- **Conférences de consensus avec jury** (2000-2008) : « le jury recommande » n'est pas une cotation ; 1 document sur 2 a des unités.
- **Annexes, algorithmes, fiches de synthèse** : les unités extraites sont souvent des doublons du texte principal, marqués `duplicate_of` quand la famille et l'année concordent.

## Pour la suite (indexation)

- Indexer de préférence les unités primaires (`duplicate_of is None`) avec un en-tête déterministe : titre, année, statut d'édition, champ, question, titre de section, identifiant, force et accord. Le `char_span` permet de revenir au passage source et de citer.
- Pour la sécurité clinique, la règle « force = cotation, formulation en repli » est préservée par `strength_source`. Une réponse générée ne devrait présenter une force que si `strength_source == "rating"`.
