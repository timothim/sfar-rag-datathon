# K1 — Le découpage tient-il hors antibioprophylaxie ? Audit de structure de `index/tas_v6`

Date : 2026-11-27. Agent K1 (Opus). Audit seul : rien n'a été reconstruit ni modifié dans `index/`, `data/`, `src/`. Index audité : `index/tas_v6` (gelé, 36 872 chunks, 265 documents). Scripts et sorties : `reports/agents/K1_annexes/` (liste en fin de rapport). Aucun fichier de questions d'évaluation n'a été ouvert. Les sondes de retrieval sont construites à partir du corpus (questions PICO imprimées dans les RFE), pas des jeux d'évaluation.

## Réponse courte

Le découpage **n'est pas faux** pour les autres recommandations : le texte est là, propre (compteurs de fidélité de B2 à 0), les tableaux de scores et de seuils donnent des fiches de ligne lisibles, et un énoncé recherché par sa question PICO arrive dans le contexte 63 fois sur 64. Mais il a été réglé sur un document fait de tableaux, et il **ne connaît pas la structure « énoncé gradé → argumentaire → références »** qui fait l'essentiel des 264 autres textes. Conséquences mesurées : un énoncé sur quatre est servi sans sa cotation (dans la sonde : 15 sur 61), un sur trois n'est pas marqué comme recommandation (20 sur 63), la cotation de l'énoncé précédent devient parfois le titre de section de l'énoncé suivant, et environ 1 100 listes bibliographiques non signalées entrent dans le contexte (une requête sur deux en reçoit au moins une). **Il faut l'adapter**, avec quatre changements génériques ; le premier, le plus utile pour la sécurité, est démontré en mémoire sur 32 documents.

## 1. Défauts qui peuvent faire présenter quelque chose de faux comme une recommandation (en premier)

### D1. Lignes de cotation converties en titres de section (33 documents, 574 chunks, tous en vigueur)

Dans la conversion Markdown, la ligne de cotation (« GRADE 1 (recommandation forte) », « Avis d'experts (Accord Fort) ») est souvent un titre `###`. Le chunker la traite comme un titre : elle quitte le chunk de l'énoncé et devient le `section_path` de tout ce qui suit, jusqu'au titre suivant. La question suivante n'étant souvent pas un titre (gras seulement), **l'énoncé suivant et son argumentaire sont présentés sous la cotation de l'énoncé précédent**. Le générateur reçoit ce chemin (« Section : … » dans l'en-tête de la source).

- 574 chunks dans 33 documents ont une cotation dans leur chemin de section ; 56 d'entre eux contiennent un autre énoncé, dont **10 (5 documents) un énoncé de cotation différente** (`grade_heading_check.json`).
- Exemple : RFE pré-éclampsie 2020, chunk `2020_RFE_20pr_C3_A9-_C3_A9clampsie_finale_8989f8__c0070_b03284ce` : section « Champ 2 : PRISE EN CHARGE THERAPEUTIQUE > Avis d'experts (Accord FORT) », texte « R2.10 – Il n'est pas recommandé de réaliser un remplissage vasculaire systématique… GRADE 1- (Accord FORT) ». Un GRADE 1 est affiché sous un titre « Avis d'experts ».
- Exemple : RPP traumatisme crânien léger 2022, `…9c1d68__c0042_206c03f0` : la question 2.2 (biomarqueurs, R2.2.1, R2.2.2) a pour section « Question 2.1 Quels sont les éléments cliniques… > Avis d'experts (Accord Fort) ».
- Exemple : RFE ALR pédiatrique 2026, `…63f95f__c0054_9cb303dc` (type `prose`, `grade_levels` vide) contient R1.1.1 sans cotation ; la cotation « GRADE 1 (recommandation forte) » est le titre de section du chunk suivant, `c0055`, qui est l'argumentaire. Même schéma : LAT 2026 (`…a26946__c0156` / `c0157`), réactions d'hypersensibilité 2025, sédation procédurale 2026.
- **Correctif démontré** (`demo_grade_heading_fix.py`, en mémoire, code figé, 32 documents) : rendre une ligne de titre faite uniquement d'une cotation comme une ligne de texte en gras. Énoncés avec leur cotation dans le même chunk : **347/472 → 410/472** (73,5 % → 86,9 %) ; énoncés typés `recommendation_box` : 338 → 402 ; chunks sous un titre de cotation : 516 → 0. Règle générique (vocabulaire de cotation seulement), pas de lexique ni de cas particulier.

### D2. En-têtes de colonnes empruntés à un autre tableau (183 tableaux, 20 documents ; 87 hors ABP)

`table_parser.parse_html_table`, branche `elif previous_headers` : un tableau sans ligne d'en-tête reconnue reçoit les en-têtes du tableau précédent de la même grande section **dès que le nombre de colonnes est égal, sans exiger que les deux tableaux soient contigus** (la branche « bandeau » exige la contiguïté, celle-ci non). Mesure en mémoire avec le code figé (`header_inheritance_check.py`) : 488 héritages, dont 183 entre tableaux non contigus (ABP 96, tableaux dominants 34, gradés sans numéro 34, anciens 10, gradés numérotés 7, autres 2).
- Exemple grave : argumentaire ECBU 2026 (`2026_Reco_ECBU_Argumentaire_04_03_2026_MEL_901bcc`), **30 fiches de ligne** (ex. `__c0650_d5e268dc`) dont les « noms de colonnes » sont une ligne de données d'un autre tableau : « Uréthroplastie, Uréthrotomie / R5. Il est recommandé de réaliser un ECBU préopératoire… (Grade C). : Cystoscopie / R9. Il est fortement recommandé de ne pas réaliser… (Grade B). | 9 : 9 | [6-9] : [2-9] … ». Deux recommandations et leurs résultats de cotation sont juxtaposés sous la forme « colonne : valeur ».
- Exemple : HAS transfusion 2014, `…57ad8e__c0422_934d2d47` : la liste des organismes participants reçoit l'en-tête « Âge gestationnel (semaines d'aménorrhée + jours) ».
- Correctif : n'hériter qu'entre tableaux contigus (même règle que la branche bandeau), sinon fiche sans en-tête. Comme 96 cas sont dans l'ABP (suites de tableaux coupés par une page avec une légende entre les deux), il faut remesurer l'ABP avant de garder le changement.

### D3. Énoncés non reconnus comme recommandations, cotations non lues

Le chunker reconnaît une recommandation par `R\d+(\.\d+){1,2}` + une cotation de la liste `GRADE 1/2±, Avis d'experts, Accord fort/faible, Recommandation forte/faible`. Hors de ce format, l'énoncé est un chunk `prose` (« Nature : texte ») ou `callout_footnote` (« Nature : note ») et `grade_levels` est vide (pas de « Force/accord mentionnés » dans l'en-tête).
- **Numéros non reconnus** : « R 1.1 : », « R1 – », « Recommandation 3 », « P4.1 » : 262 énoncés dans 19 documents gradés (toute la RPP traumatisme crânio-encéphalique 2025, hypothermie 2018, SDRA 2018, trauma abdominal 2019, intubation hors bloc 2025, etc.).
- **Cotations non reconnues** : dans la classe G2, « grade A/B/C » (1 159 occurrences), « G1+ / G2- » (221), « (1+) » (55), « AE » (192), « accord professionnel/relatif » (121), surtout dans les textes 2001–2014 et HAS. 636 chunks de 61 documents G2 (et 214 chunks de 52 documents G1) contiennent une formule de recommandation (« il est recommandé », « les experts suggèrent », « il faut ») et une cotation, sans être typés recommandation.
- **Énoncés typés « note »** : un paragraphe commençant par « \*Experts : … » ou une puce « \* » est pris pour une note de bas de tableau (`FOOTNOTE_START_RE`). Exemple : trauma abdominal 2019, `…656ac9__c0052_62e3cd72`, R5 (damage control, « Grade 2+ (accord FORT) ») typé `callout_footnote`. 37 chunks d'énoncés dans les documents gradés numérotés, environ 90 au total.
- Sonde de retrieval (64 questions PICO, 33 documents) : l'énoncé visé est servi 43 fois comme « recommandation », 18 fois comme « texte », 2 fois comme « note ».
- Risque : ce n'est pas un texte faux, mais le modèle et le lecteur perdent l'indication qu'il s'agit de l'énoncé gradé et non d'un passage d'argumentaire ; la règle « citer la force de la recommandation » ne peut pas s'appliquer.

### D4. Un chunk, plusieurs énoncés ou énoncé + argumentaire

- 243 chunks contiennent au moins deux énoncés (555 énoncés) ; dans 143 d'entre eux les cotations diffèrent. `grade_levels` est l'union des cotations du chunk : l'en-tête affiche par exemple « Force/accord mentionnés : GRADE 2, Recommandation faible, AVIS D'EXPERTS » sans dire laquelle va avec quel énoncé (ALR pédiatrique 2026 `c0076`, `c0114` ; infections intra-abdominales 2026 `c0076`, `c0185`, `c0208`, `c0226`). Le texte, lu en entier, garde l'ordre énoncé → cotation ; c'est l'en-tête résumé qui est ambigu.
- 128 chunks `recommendation_box` contiennent plus de 300 caractères d'argumentaire après « Argumentaire » : ce texte (résultats d'études) est présenté comme « Nature : recommandation ».
- 929 chunks de méthodologie ou d'argumentaire ont un `grade_levels` non vide sans formule de recommandation (ex. « La formulation finale des recommandations sera … forte : il faut faire (GRADE 1+ ou 1-) », hypothermie 2018 `c0037`) : l'en-tête annonce une force sur un texte de méthode.
- Dans la sonde, un chunk du même document sans énoncé (argumentaire, méthode, question) est classé **avant** l'énoncé pour 25 questions sur 63 ; il est en tête 24 fois sur 64. L'énoncé est au rang 1 pour 37/63, dans les 3 premiers pour 50/63, présent dans le contexte pour 63/64.

Pas de cas trouvé d'édition obsolète présentée comme en vigueur du fait du découpage (les statuts d'édition ne dépendent pas du chunker ; voir B2 et R1 pour leurs limites).

## 2. Typologie du corpus (265 documents ; 217 éditions en vigueur et actives)

Classement automatique (`corpus_structure_audit.py`, `typology.tsv`), dans cet ordre : ABP ; anglais ; fiche/algorithme/annexe (rôle du loader ou < 15 000 caractères) ; tableaux dominants (≥ 35 % du texte hors bibliographie en tableaux) ; gradé numéroté (≥ 3 énoncés « R… », « Recommandation n ») ; gradé sans numéro (≥ 5 cotations, tous formats) ; ancien non gradé (≤ 2010) ; récent non gradé.

| Classe | Docs (en vigueur) | Chunks hors biblio | Exemples |
|---|---:|---:|---|
| 0. Antibioprophylaxie (exclue de l'audit) | 5 (1) | 2 264 | RFE ABP V3.1 2026 |
| G1. Gradée, énoncés numérotés (format RFE GRADE) | 60 (55) | 8 670 | anticoagulation en urgence 2024, infections intra-abdominales 2026, HSI 2025, ALR pédiatrique 2026, pré-éclampsie 2020, hypothermie 2018, TC léger 2022 |
| G2. Gradée sans numéro reconnu, ou autres formats de cotation | 67 (53) | 12 184 | blocs périmédullaires 2006 (grade A/B/C), traitements chroniques 2009, EER 2014 (« 1.1 Il faut … (Avis d'experts) »), sepsis HAS 2025, argumentaires voies aériennes 2026 et nutrition 2026 |
| O. Ancienne (≤ 2010), non gradée | 38 (28) | 3 941 | corticothérapie et choc septique 2000, SAUV 2003, candidoses 2004, profondeur d'anesthésie 2010 |
| X. Récente, non gradée (préconisations, propositions) | 18 (11) | 1 061 | bris dentaires 2012, ponction lombaire HAS 2019, GIHP COVID 2021, analgésie de césarienne 2021 |
| T. Tableaux dominants (hors ABP) | 7 (7) | 2 312 | voies aériennes 2026 (recommandations en tableau), argumentaire ECBU 2026, HAS transfusion 2014, tabac 2016 |
| F. Fiches, algorithmes, tableaux de synthèse, annexes | 47 (44) | 2 113 | arbre diagnostique anémie 2019, algorithmes anticoagulation 2024, algorithmes voies aériennes 2026, tableaux douleur 2016, tableaux ALR 2013 |
| E. Traductions anglaises | 23 (18) | 1 591 | TBI 2016, HAP 2017, intubation-extubation ICU 2016 |

Remarques. (1) Seuls 7 documents hors ABP sont dominés par les tableaux ; l'essentiel du corpus (127 documents gradés, 20 854 chunks) a la structure énoncé → cotation → argumentaire → références. (2) Les « textes longs » (`argumentaire`) et « textes courts » d'une même RFE sont des documents séparés : les énoncés existent en double. (3) 452 + 474 chunks en anglais dans les documents français gradés (résumés). (4) La part de tableaux mesurée inclut les tableaux de cotation, sommaires et listes d'abréviations.

## 3. Audit par contrôle

Contrôles automatiques sur tout l'index (`class_summary.json`, `extra_counters.json`) et lecture de chunks contre la source sur 35 documents en vigueur tirés par classe (graine 11 : 8 G1, 8 G2, 5 O, 4 E, 3 T, 4 F, 3 X ; `sample_review.txt`), plus les cas signalés par les compteurs. L'échantillon a été relu par l'agent, pas par un médecin.

### 3.1 Intégrité des recommandations (classe G1, 1 299 énoncés numérotés)

| Contrôle | Valeur |
|---|---:|
| Énoncés dont une cotation est dans le même chunk | 1 038 (79,9 %) |
| Cotation au début du chunk suivant | 25 |
| Aucune cotation trouvée près de l'énoncé (surtout D1 : cotation passée en titre) | 233 (17,9 %) |
| Chunks d'énoncé non typés `recommendation_box` | 291 / 981 |
| Chunks avec ≥ 2 énoncés (énoncés concernés) | 243 (555) |
| … dont cotations différentes mélangées dans `grade_levels` | 143 |
| `recommendation_box` avec > 300 car. d'argumentaire | 128 / 690 |
| Chunks d'énoncé commençant par la fin de la bibliographie de la question précédente | 57 |
| Chunks d'énoncé sous un titre « Argumentaire » resté ouvert (question précédente) | 47 (9 documents) |

Lecture : un énoncé coupé au milieu de sa phrase est rare (la découpe se fait sur les paragraphes, l'énoncé est un paragraphe) ; le problème est la séparation énoncé/cotation et le regroupement de plusieurs énoncés. Les recommandations rangées dans des tableaux (voies aériennes 2026, RAC cardiaque 2021, ECBU 2026 : 530 fiches hors ABP portent un identifiant R) sont bien formées : énoncé et « Niveau de preuve : 1 » ou « GRADE : 2+ | Accord : FORT » dans la même fiche ; seule la cotation n'entre pas dans `grade_levels` (format « colonne : valeur »).

### 3.2 Recommandation ou argumentaire

- L'argumentaire n'a pas de type propre : il est `prose`, comme les introductions et méthodes. Il ne se distingue d'un énoncé que si l'énoncé est un `recommendation_box`, ce qui échoue dans les cas D1, D3, D4.
- Le chemin de section ne sépare pas non plus : « Argumentaire » est presque toujours une ligne en gras, pas un titre ; quand c'est un titre, il reste ouvert sur la question suivante (47 chunks d'énoncé sous « Argumentaire »).
- Part de l'index : dans les classes G1 et G2, 13 589 chunks `prose` contre 724 `recommendation_box` (hors tableaux, hors bibliographie).
- Sonde de retrieval : voir D3, D4. Un chunk du même document sans énoncé passe avant l'énoncé pour 40 % des questions ; le contexte contient en moyenne 24,7 chunks, donc l'énoncé est presque toujours présent aussi, mais l'ordre et l'étiquette ne permettent pas au modèle de savoir lequel fait foi.

### 3.3 Bibliographies

- 2 736 chunks typés `references` et marqués `is_reference_section` : exclus de la recherche (`exclude_references=True`) et des fenêtres de voisinage.
- **≈ 1 107 chunks non marqués sont en fait des listes de références** (≥ 3 lignes de type « [n] Auteur X, … ; revue année;vol:pages » et au moins la moitié des lignes, sans contenu clinique) : G2 485, G1 475, E 62, T 25, ABP 19, F 19, O 18, X 4. Cause : la bibliographie est sous un titre en gras « **Références :** » (pas un titre Markdown), ou en fin de question sans titre, ou rendue en tableau (« Tableau : Références », RAC orthopédie 2019 `c0134` ; B2 garde volontairement les tableaux placés sous un titre Références).
- En contexte (sonde) : 69 chunks de ce type sur 1 582 (4,4 %), **au moins un pour 34 requêtes sur 64**. Aucun chunk marqué n'y entre. Risque clinique faible (le générateur cite rarement une liste d'auteurs), coût de contexte réel, et confusion possible « [12] » ↔ numéro de recommandation.

### 3.4 Tableaux hors antibioprophylaxie

- Fidélité du texte des cellules : bonne (contrôle B2 : 9 lignes sur 8 944 dont les jetons ne sont pas réunis, 4 jetons absents). Lus sur l'échantillon : échelles de score (AIS, MFI-5, score de COMFORT), seuils (bilirubine, argatroban selon APACHE/SOFA), tableaux comparatifs (solutés, équivalences d'opioïdes « Codéine | Ratio : 1/6 … ») donnent des fiches correctes.
- Tableaux sans ligne d'en-tête : 113 (G1), 158 (G2), 116 (T) ; leurs fiches s'écrivent « a — b — c » (1 043 fiches en G2), lisibles pour une liste, peu lisibles pour une grille à deux axes (échelles de douleur pédiatrique : « Pas de cris (éveillé ou endormi) — Pas de cris (éveillé ou endormi) — 0 », amygdalectomie 2014 `c0093`).
- Tableaux longs coupés en plusieurs chunks `table_markdown` : 101 (G1), 126 (G2), 78 (T) ; dans 64, 51, 32 d'entre eux un morceau n'a pas la ligne d'en-tête (les fiches de ligne, elles, l'ont toujours).
- Faux tableaux : sommaires et listes d'abréviations transformés en fiches (« Section : Sommaire / Question 1 : … ….. », anticoagulants programmés 2026 `c0017`), déjà signalé par R1 (m7).
- Tableaux de synthèse en fin de document rangés sous le dernier titre : la fiche d'une recommandation du Champ 1 porte « Section : CHAMP 4 … » (HSI 2025 `c0528`) ou « Champ 5 » pour le Champ 3 (ALR pédiatrique `c0222`) ; la sous-catégorie donne le bon champ.
- Tableaux en image dans la source : 4 descriptions d'image le désignent comme un tableau ; non mesurable plus finement sans les PDF (voir § 5).
- D2 (en-têtes empruntés) est le seul défaut de tableau qui change le sens.

### 3.5 Figures et arbres de décision

- 164 blocs Mermaid (organigrammes convertis par l'OCR) : réécrits sans perte de nombre ni de mot (contrôle B2), 9 gardés bruts.
- 134 descriptions d'image en anglais gardées et marquées ; logos supprimés.
- Algorithmes sans Mermaid : seul le texte des boîtes reste, sans les flèches. Exemples : algorithmes voies aériennes 2026 n° 1 et 2 (1 230 et 1 922 caractères ; « Échec et désaturation », « Appel à l'aide », « SMS Cricothyrotomie » sans l'ordre des branches) ; fiches tabac 2016 (le message est dans l'image, il reste une description et deux phrases). 17 documents citent une figure (« Figure n : ») sans image ni organigramme dans le Markdown.
- C'est une limite de la conversion source, pas de notre découpage. Les documents concernés ont presque tous un texte complet qui porte les mêmes recommandations (RFE voies aériennes 2026, anticoagulation 2024). À énoncer, pas à corriger aujourd'hui.

### 3.6 Chemins de section et longueurs

- Titres frères empilés : le chemin contient deux titres de même rang successifs (« QUESTION 2 > QUESTION 3 », « 2. CHAPITRE 2 … > 3. CHAPITRE 3 … », « Argumentaire R2.4.3 > Argumentaire R2.4.4 », « Patient 3 > Patient 4 »), parce que l'OCR donne des niveaux `#` différents à des titres de même rang. Documents touchés : O 31/38, G2 50/67, G1 19/60, E 17/23, X 9/18. Le dernier élément est juste ; le parent annoncé est faux. Exemples : blocs périmédullaires 2006, urgences obstétricales 2010.
- Aucun document « tout sous un seul titre » (0 document où un chemin couvre ≥ 80 % des chunks).
- Longueurs (hors bibliographie) : médiane 431 (T) à 789 (E) caractères ; P90 ≈ 1 130–1 190 partout ; < 100 caractères : 774 chunks en G2, 266 en T (titres de tableaux, lignes d'abréviations) ; > 2 000 caractères : 44 en G1, 17 en O. Pas d'anomalie de taille propre à une classe.

### 3.7 Documents anciens et atypiques

- Anciens (2000–2010) : prose bien découpée, cotations en lettres (« grade A/B/C », « (C3) », « niveau de preuve 1 ») non lues, énoncés non marqués, chemins empilés. Le contenu est intact.
- Fiches et aides cognitives : courtes, découpées en 2 à 40 chunks ; l'ordre de lecture d'une fiche en colonnes est celui de l'OCR.
- Traductions anglaises : même structure que le texte français, numérotation « R7.6 – … ([Grade 2+] strong agreement) » reconnue ; 52 chunks sous un énoncé devenu titre. Elles doublent le texte français et sont déclassées par `prefer_french`.
- Documents HAS 2025 (sepsis : recommandation, argumentaire, fiches) : « Recommandation n » en titre, cotations « AE / Grade B » non lues, annexes de bonnes pratiques bien découpées.

## 4. Verdict par classe

| Classe | Verdict | Ce qui coince | Documents / chunks touchés |
|---|---|---|---|
| G1 gradée numérotée (55 en vigueur) | **À adapter** | D1, D3 (numéros « R 1.1 », « R1 »), D4, bibliographies non marquées, « Argumentaire » ouvert | 60 docs ; ≈ 2 000 chunks d'énoncés et voisins |
| G2 gradée sans numéro (53) | **À adapter** | D3 (cotations en lettres, G1+, AE, « 1.1 Il faut »), bibliographies non marquées, chemins empilés | 67 docs ; 636 chunks d'énoncés non typés, 485 bibliographies |
| T tableaux dominants (7) | **Acceptable avec limite**, sauf D2 à corriger | en-têtes empruntés (ECBU argumentaire, HAS transfusion) | 4 docs, ≈ 60 fiches |
| O ancienne non gradée (28) | **Acceptable avec limite** | chemins empilés (31/38) ; pas de cotation à lire | 38 docs |
| X récente non gradée (11) | **Correcte** | « P4.1 » non reconnu (préconisations césarienne) | marginal |
| F fiches/algorithmes (44) | **Acceptable avec limite (source)** | flèches des algorithmes absentes, images sans texte | ≈ 20 docs |
| E anglais (18) | **Acceptable** | doublons du français, déclassés | — |

Ce qui relève de notre découpage : D1 (traitement des titres), D2 (règle d'héritage), D3 (expressions régulières de numéros et de cotations, règle des notes), D4 (découpe sans frontière d'énoncé), bibliographies sans titre Markdown, chemins empilés. Ce qui manque dans la source : flèches des algorithmes, images de tableaux et de figures, niveaux de titres incohérents (cause de D1 et des chemins empilés, mais c'est à nous de les absorber), cotations collées au texte dans les PDF anciens.

## 5. Adaptations proposées (risque clinique d'abord, puis bénéfice attendu)

1. **Ligne de cotation ≠ titre** (D1). Une ligne de titre faite uniquement d'une cotation devient une ligne de texte. 33 documents, ≈ 600 chunks. Démontré : énoncés avec cotation 73,5 % → 86,9 %, 0 chunk sous un titre de cotation. Une fonction de 3 lignes dans le chunker.
2. **Héritage d'en-tête seulement entre tableaux contigus** (D2). 183 tableaux, 20 documents, dont 96 dans l'ABP : remesurer abpe171/abp171 avant de garder.
3. **Frontières d'énoncé** (D3 + D4) : reconnaître « R 1.1 », « R1 », « Recommandation n », « Pn.n » et les cotations G1+/(1+)/grade A–C/AE/accord professionnel ; couper avant chaque énoncé et avant « Argumentaire » ; garder énoncé + cotation dans un chunk ; ne pas typer « note » un paragraphe qui contient une formule de recommandation et une cotation ; `grade_levels` par énoncé et non par chunk. Touche ≈ 127 documents gradés et ≈ 4 000 chunks. C'est ce qui permettrait au générateur de savoir « ceci est la recommandation, ceci est l'argumentaire ».
4. **Bibliographies sans titre** : marquer `is_reference_section` les paragraphes à forte densité bibliographique sans contenu clinique (même motif que `_is_truly_reference_text`, appliqué partout), et les tableaux dont toutes les lignes sont des références. ≈ 1 100 chunks, 34/64 requêtes nettoyées ; libère environ 4 % du contexte.
5. **Chemins de section** : quand un titre a la même forme numérotée que l'élément précédent du chemin (« QUESTION n », « CHAPITRE n », « Argumentaire Rn »), il le remplace au lieu de s'y ajouter ; fermer « Argumentaire » à la question suivante. ≈ 150 documents, plusieurs milliers de chunks (chemin seulement, texte inchangé).
6. Limites à énoncer sans corriger : algorithmes sans flèches, images, traductions en double.

Coût : toutes ces adaptations changent les chunks, donc **un nouvel index** (`tas_v7`, construction complète avec embeddings, comme B2), puis les contrôles de fidélité de B2, la ré-évaluation dev des trois jeux (abpe171, abp171, multirfe) et de la sonde `genprobe2`, et une revue indépendante ; le retrieval est gelé, donc c'est une décision de dégel. Ordre conseillé si on le fait : 1 et 2 (sécurité, petits, mesurables), puis 3 (le plus gros gain attendu sur le reste du corpus), puis 4 et 5. Aucune des règles n'est tirée d'une question d'évaluation.

## 6. Ce que je n'ai pas pu vérifier

- Pas de relecture médicale. La détection des énoncés et des cotations est faite par expressions régulières : rappel et précision non mesurés au-delà de l'échantillon de 35 documents et des exemples cités (le compteur « aucune cotation trouvée » est une borne haute : certains énoncés n'ont réellement pas de cotation, « absence de recommandation »).
- Pas de comparaison avec les PDF : ce que la conversion a perdu (tableaux en image, figures) n'est vu que par les légendes orphelines et les descriptions d'image.
- La sonde de retrieval utilise les questions PICO imprimées juste avant l'énoncé, donc des requêtes faciles et proches du texte (biais favorable) ; 64 requêtes, 33 documents, retrieval seul, configuration gelée `C10_context_notes`.
- Seul le correctif D1 a été démontré, en mémoire, sur des compteurs structurels ; aucun correctif n'a été mesuré en retrieval.
- Les traductions anglaises et les documents de classe F n'ont été lus que sur échantillon.

## Fichiers (`reports/agents/K1_annexes/`)

- `corpus_structure_audit.py` → `typology.tsv`, `doc_metrics.json`, `class_summary.json`, `examples.json` (typologie, intégrité des énoncés, bibliographies, tableaux, figures, chemins).
- `extra_counters.py` → `extra_counters.json` (cotations en titre, numéros non reconnus, énoncés non typés, longueurs).
- `grade_heading_check.py` → `grade_heading_check.json` (D1).
- `header_inheritance_check.py` → `header_inheritance_check.json` (D2, en mémoire).
- `retrieval_probe.py` → `retrieval_probe.json`, `retrieval_probe_summary.json` (sonde, verrou GPU `K1`).
- `demo_grade_heading_fix.py` → `demo_grade_heading_fix.json` (correctif D1 en mémoire).
- `sample_review.py` → `sample_review.txt` (échantillon relu ; contient des extraits de textes SFAR, donc régénéré à la demande et non commité).

Les textes des requêtes de la sonde (questions PICO imprimées dans les RFE) ont été retirés de `retrieval_probe.json` avant commit ; `retrieval_probe.py` les reconstruit.
