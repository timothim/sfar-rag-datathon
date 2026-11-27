# R1 — Revue indépendante de l'ingestion B2 (`index/tas_v4`)

Date : 2026-11-27. Relecteur : R1 (Opus), indépendant de B2. Référentiel : `CLAUDE.md`, `<principes_non_negociables>`. Objet : commits 83abae1, 2c3ede3, 862a912, a092457, c18942e, a725f96, 7ec7ef7 (+ rapport ba19d63) et l'index `index/tas_v4`.

Tout ce qui suit a tourné sur CPU, sans construire d'index, sans embedding, sans modèle, en lecture seule sur `data/` et `index/`, sur les splits DEV seulement. Scripts et sorties : `reports/agents/R1_annexes/` (voir `README.md`). Je sépare **vérifié** (mesuré ou lu dans la source) et **déduit** (raisonnement non vérifié).

## Verdicts

| Question | Verdict |
|---|---|
| 1. Surapprentissage | **Pas de surapprentissage introduit par B2.** Aucun nom de molécule ou d'acte dans le code ajouté, tests synthétiques. Les règles B2 se déclenchent sur 25 à 183 documents, sauf deux : la note de périmètre (2 documents, les deux éditions ABP) et la règle d'édition « mention explicite » (1 lien). Je les classe **limites**. Les règles propres à l'ABP qui restent dans le code (en-tête `<td>` qui nomme des molécules, découpe « PAS D'ANTIBIOPROPHYLAXIE », encadré allergie) existaient avant B2. Le correctif des coquilles de l'overlay a été choisi à partir de questions DEV : la correction est vraie, mais la façon de la trouver est limite. |
| 2. Exactitude et sécurité du texte | **Non conforme en l'état.** Quatre défauts critiques sont vérifiés, tous génériques et faciles à corriger : (C1) 1 838 tableaux Markdown sur 2 638 sont aplatis sur une seule ligne, et les cellules vides sont supprimées, ce qui décale les colonnes ; (C2) la réécriture des organigrammes Mermaid perd des doses et des seuils ; (C3) µg devient « \mug » ou « mug » (135 occurrences, 42 documents) ; (C4) les négations placées après le terme sont ignorées (« (nouveau-né exclu) »), si bien qu'environ 700 chunks adultes reçoivent l'étiquette néonatal + pédiatrie. Les fiches de ligne (`table_row_card`) sont fidèles : les jetons cliniques perdus passent de 242 à 11 et les mots de cellule absents de 429 à 4 par rapport à `tas_v3_errata`. |
| 3. Éditions | Urgences obstétricales 2010 → remplacé : **justifié** (mise à jour explicite), mais le remplacement n'est que partiel. Copie COVID → abrogée : **justifié** (même texte, Jaccard 0,94, version 3.1 abrogée le 01/07/2023). AVK HAS 2008 → de nouveau en vigueur : **non justifié** (le chapitre 4 sur le relais par héparine pour un acte programmé est couvert par la RFE 2026, le chapitre 3 sur l'hémorragie par la RFE urgence 2024). Les deux règles génériques ne produisent aucun autre changement sur les 265 documents, et aucune paire n'a un Jaccard compris entre 0,8 et 0,9. La règle « mention explicite » se déclenche aussi sur des paragraphes de bibliographie : c'est un mécanisme de faux positif, sans effet aujourd'hui. |
| Reproductibilité des mesures DEV | **Reproduites** à la décimale près depuis `*_b2_base.*` et `*_b2_v4.*`, ainsi que les étapes intermédiaires et les 51 compteurs structurels. Trois imprécisions mineures (§ 5). |

**Point de méthode important.** Les trois régressions de texte C1 à C3 sont arrivées avec le nettoyage OCR (c18942e), mesuré à l'étape `tas_v4_c`. Les métriques de retrieval ne les voient pas : l'appariement des passages normalise les espaces et ignore la structure. Les compteurs structurels de B2 ne les voient pas non plus : ils mesurent la présence du texte, pas la ligne ou la colonne où il se trouve, et ils excluent Mermaid de la couverture. Un gain de retrieval ne garantit donc pas que le texte cité reste fidèle.

---

## Défauts, par gravité

### CRITIQUES (à corriger avant l'évaluation finale ; reconstruire l'index dans un nouveau dossier)

#### C1. Tableaux Markdown aplatis et colonnes décalées : `src/rag_sfar/ingestion/text_cleaning.py:187`
`strip_inline_tags` remplace `(?:\s*\|\s*){2,}` par `" | "`. Comme `\s` capture aussi `\n`, chaque fin de ligne `|\n|` devient un séparateur de cellule, et chaque cellule vide `|  |` disparaît. `clean_chunk_text` s'applique à tous les chunks, y compris `table_markdown` et `callout_allergy`.
- **Vérifié, reproduction minimale** : `clean_chunk_text("| Acte | Molécule | Dose |\n| --- | --- | --- |\n| A | PAS D'ANTIBIOPROPHYLAXIE |  |\n| B | Céfazoline | 2g IVL |")` renvoie `"| Acte | Molécule | Dose | --- | --- | --- | A | PAS D'ANTIBIOPROPHYLAXIE | B | Céfazoline | 2g IVL |"`.
- **Ampleur (vérifiée)** : `tas_v4_t` (avant nettoyage) contient 1 854 `table_markdown` d'au moins 2 lignes ; `tas_v4` contient 1 838 tableaux sur une seule ligne. 1 137 chunks de 117 documents ont au moins une cellule vide dans une ligne de données, donc un décalage de colonnes. Script : `R1_annexes/text_regressions.py`.
- **Exemples de valeurs attribuées à la mauvaise colonne (source, puis chunk `tas_v4`)** :
  - Solutés 2021 (`2021_RFE-SFAR-SFMU-Solute…`). Source : `K+ (mmol/l) | 4 |  | 4 | 5 | 4` (Plasma, NaCl, Ringer, Plasma-lyte, Isofundine). Dans `tas_v4` : `K+ (mmol/l) | 4 | 4 | 5 | 4`, si bien que NaCl 0,9 % semble contenir 4 mmol/l de K+ et Ringer 5. Même problème pour Ca2+ et Mg2+.
  - Sepsis HAS 2025, volumes d'hémoculture pédiatriques. Source : `≤ 1 | 0,5 à 2 |  |  |  |  |  | 0,5 à 2 | 1,5 à 3`. Dans `tas_v4` : `≤ 1 | 0,5 à 2 | 0,5 à 2 | 1,5 à 3 | 1,1-2 | …` : lignes fusionnées, et le « volume total sous-trait » tombe dans la colonne « Culture 1 anaérobie ».
  - Infections nosocomiales 2008. Dans la ligne « … chez l'enfant | 2,90–11,60 | 5,40 |  | 7,10–9,70 », la valeur 7,10–9,70 passe de la colonne CVC à la colonne Bactériémies.
  - ABP V3.1. Le tableau tête et cou devient une seule ligne : « … Frontoplastie | Céfazoline | 2g IVL | … | ●●● (GRADE 2) | ●●● (Avis d'experts) | Gênioplastie … ». On ne sait plus quelle cotation va avec quelle ligne.
- **Effet** : la configuration « C9 + fenêtres » (`expand_table_parent=true`) envoie au générateur ces tableaux parents aplatis. Les fiches de ligne ne sont pas touchées : leurs couples « colonne : valeur » sont corrects, par exemple `K+ … | Plasma : 4 | Ringer's Lactate : 4 | Plasma-lyte : 5 | Isofundine : 4`.
- **Correctif** : remplacer la regex par `(?:[ \t]*\|[ \t]*){2,}` et ne l'appliquer qu'aux fragments orphelins, c'est-à-dire seulement dans `_ORPHAN_*` et pas sur des lignes qui commencent par `|`. Ajouter un test : `clean_chunk_text` sur un tableau Markdown avec cellule vide doit garder le même nombre de lignes et de `|` par ligne.

#### C2. Organigrammes Mermaid : perte silencieuse de contenu clinique : `text_cleaning.py:233-350` (`_EDGE_AT_RE`, `_read_node`, `mermaid_to_text`)
- **Vérifié** (`R1_annexes/mermaid_check.txt`) : 13 blocs sur 164 perdent des arêtes, et la réécriture omet des libellés entiers. Pour les mêmes documents, `tas_v3_errata` conservait la syntaxe brute, où l'information restait lisible. Comptes faits dans les chunks des deux index (`text_regressions.py`, vérifications ad hoc) :
  - Algorithmes anticoagulation en urgence 2024 (`2024_Algorithmes_RFE-gestion-de-lanticoagulation…`) : « idarucizumab 5 g IVL » 1 → 0, « ≤50 ng/mL » 1 → 0, « 2ème dose d'idarucizumab » 1 → 0. La sortie répète trois fois « Mesure de la concentration en dabigatran → Résultat non disponible rapidement * » : les branches « [AOD] > seuil » et « ≤ seuil » ont disparu. Dans la RFE 2024 elle-même : « >600 ng/mL » 1 → 0, « 4-6h » 1 → 0.
  - Sédation-analgésie pédiatrique 2007 (`2007_2b_AFAR_aspet-pediatriques`) : l'algorithme s'arrête après trois flèches. Les seuils EVA > 30 et COMFORT > 26 / < 8, COMFORT-B > 22 / < 11 (« <11 », « >22 », « >26 », « >30 » : 1 → 0) et toutes les branches thérapeutiques sont perdus. Cause : `--  label -->` dont le libellé contient « > ».
  - Arrêt cardiaque 2006 : l'encadré « Pendant RCP … Adrénaline IV 0,01 mg/kg / 3-5 min … Envisager amiodarone, atropine » (relié par `<-->`) est absent de l'organigramme.
  - HAS infarctus 2006 : « >0,12 » (QRS larges) 2 → 0. Urologie ambulatoire 2013 : « >200 ml » 1 → 0.
- **Causes génériques** : libellés d'arête contenant `>` ; arêtes `<-->` ; crochets imbriqués dans les libellés (`[AOD]`) ; un nœud redéfini garde son premier libellé (`labels.setdefault`) ; une chaîne interrompue fait perdre tous les nœuds suivants, qui ne sont jamais lus.
- **Correctif** : après conversion, vérifier que tous les jetons numériques et tous les mots d'au moins 4 lettres des libellés sources se retrouvent dans la sortie ; sinon, garder le bloc brut ou ajouter « Libellés non reliés : … ». Accepter `<-->`, les libellés contenant `>` (lire jusqu'au `-->` suivant) et les crochets imbriqués. Ajouter des tests synthétiques pour chacune de ces formes.

#### C3. Unités micro corrompues (µg → « \mug » / « mug », µmol → « mumol ») : `table_parser.py:245-269` et `text_cleaning.py:86-88, 101-119`
- **Vérifié** : la source contient `<td>Morphine sans conservateur 3 à 5 <math>\mu</math>g/kg (max 250 <math>\mu</math>g)</td>` (ALR pédiatrique 2026). `tas_v3_errata` donne « 3 à 5 \mu g/kg (max 250 \mu g) » ; `tas_v4` donne « 3 à 5 \mug/kg (max 250 \mug) ». La nouvelle fonction `_node_text` colle le texte de `<math>` à la lettre qui suit, puis la règle `\mu(?![A-Za-z])` ne s'applique plus à cause du « g » qui suit. En prose, l'allergie 2011 donne « tryptase sérique ( > 25 mug L⁻¹ ) » : `latex_to_text` déroule `\text{}` avant de remplacer les symboles, puis le cas « commande inconnue » écrit « mug ». Reproduction : `clean_chunk_text("<math>\\leq 0,1 \\mu\\text{g/kg/min}</math>")` donne « ≤ 0,1 mug/kg/min ».
- **Ampleur** : 135 occurrences (« \mug » 36, « mug » 70, « mumol » 26…) dans 42 documents pour `tas_v4`, contre 0 pour `tas_v3_errata`. On y trouve clonidine, sufentanil et morphine (ALR pédiatrique 2026), sédation 2007, allergie 2011. **Risque** : lire mg au lieu de µg (facteur 1 000).
- **Correctif** : dans `_node_text`, traiter `<math>` par `latex_to_text` avant d'extraire le texte, et insérer un espace. Dans `latex_to_text`, remplacer les symboles avant de dérouler `\text{}`. Accepter `\mu`, `\Omega` et `\circ` même suivis d'une lettre. Test : `\mu\text{g}`, `<math>\mu</math>g/kg` et `\mu mol` doivent donner « µg » et « µmol ».

#### C4. Étiquettes de population : négation placée après le terme ignorée : `src/rag_sfar/ingestion/population.py:33-56`
- `_NEGATION_BEFORE_RE` ne regarde que les 40 caractères qui précèdent le terme. Un titre comme « Ventilation non invasive au cours de l'insuffisance respiratoire aiguë (nouveau-né exclu) » donne donc `{neonatal, pediatrie}`.
- **Vérifié** : environ 700 chunks dans 10 documents (VNI 2006 ×3, sédation-analgésie en réanimation 2007 ×3, hémodynamique du sepsis 2005 ×2, états de mal épileptiques 2008, infections nosocomiales 2008) portent `neonatal + pediatrie`, souvent sans `adulte`, alors que ces textes portent surtout sur l'adulte et excluent explicitement le nouveau-né.
- **Pourquoi c'est critique** : `retrieval/pipeline.py:74-86` (`_chunk_population`, B1) lit désormais `populations` en priorité. Ces chunks adultes sont donc classés « pediatrie » pour la pénalité et les quotas de population.
- **Correctif** : chercher aussi la négation dans une fenêtre après le terme (`exclus?`, `exclue?s?`, `non concerné`), y compris entre parenthèses. Ajouter un test.

### MAJEURS

#### M1. Lignes pleine largeur : des libellés sont classés comme « notes » : `table_parser.py:351-365`
Avec les règles actuelles (« se termine par . ou * », « italique seul », « commence par * »), environ 15 des 106 lignes classées « note » sont en réalité des libellés de sous-groupe (`R1_annexes/full_width_examples.txt`) : « Candida sp. », « Aspergillus sp. », « Chirurgie de la prostate. », « Chirurgie du tube digestif * », « Antiseptiques », « Colorants », « Faible risque [0–8] » … « Risque très élevé [> 24] », « CHAMP 1. … », etc. Ces libellés sont alors rattachés au groupe **précédent**.
- **Vérifié** : dans les candidoses et aspergilloses 2004, la fiche « fumigatus » porte « Note du tableau : Candida sp. », et la dernière ligne Candida (lusitaniae) porte « Note : Aspergillus sp. ». Dans ABP **V3.1**, partie néonatale, la fiche « Cure de laparoschisis/omphalocèle … Céfazoline 30 mg/kg » reçoit « Note : Chirurgie du tube digestif * » **et** la note (*) « La chirurgie de l'entérocolite … ne relève pas de l'antibioprophylaxie mais d'une antibiothérapie curative ». La note est donc attachée à la mauvaise ligne, et les lignes « tube digestif » perdent leur sous-catégorie.
- **Correctif** : une ligne courte (8 mots ou moins, sans verbe conjugué) est un libellé, même si elle finit par « . » ou par un appel de note. Il faut retirer l'appel avant de classer, mais le conserver pour lier la note au groupe qui **suit**. Une ligne courte en italique seul est aussi un libellé.

#### M2. AVK HAS 2008 remis « en vigueur » à tort : `loader.py:263-268`
- **Vérifié par lecture** : le chapitre 4 (« Conduite à tenir vis-à-vis du traitement par AVK en cas de chirurgie ou d'acte invasif », relais préopératoire par héparine) porte sur le même sujet que la RFE 2026 « Gestion des anticoagulants pour une procédure invasive programmée » (Q6 : relais AVK pour valve mécanique ; 194 chunks AVK + relais/INR). Le chapitre 3 (hémorragies) est couvert par « Gestion de l'anticoagulation dans un contexte d'urgence » 2024.
- **Déduit** : le chapitre 2 (surdosage asymptomatique) n'a peut-être pas d'équivalent plus récent dans le corpus. En revanche, présenter comme en vigueur des règles de relais de 2008, dépassées depuis 2018 et 2026, est une erreur grave au sens du principe 7.
- **Correctif** : revenir au statut « remplacé », avec `superseded_by` = RFE 2026 et une preuve qui cite aussi 2024. Sinon, créer un statut « partiellement remplacé » affiché dans l'en-tête et non masqué. À faire valider par un médecin.

#### M3. Étiquettes de population tirées de titres énumératifs ou de titres-phrases : `population.py:68-90`
- `obstetrique` s'ajoute dès qu'un titre parent la cite. Le titre « PARTIE 6 : CHIRURGIE GYNECOLOGIQUE, PROCREATION MEDICALEMENT ASSISTEE, OBSTETRIQUE ET RADIOLOGIE » étiquette donc obstétrique environ 35 chunks par édition ABP (sein, utérus, prolapsus, vulve, PMA). **Vérifié.**
- Des énoncés de recommandation transformés en titres propagent aussi leur population à l'argumentaire qui suit. **Vérifié** : 432 chunks de 36 documents tiennent leur étiquette d'un titre de plus de 15 mots. Exemple : dans HAP 2017, les chunks 37 à 40 (rationnel de la décontamination digestive sélective, adulte) sont étiquetés `pediatrie` parce qu'ils suivent la recommandation « Paediatrics – We suggest … ».
- **Correctif** : ignorer les termes de population dans les titres de plus d'environ 15 mots ou qui sont des phrases (« suggèrent », « recommandé », « we suggest »), et dans les énumérations de 3 domaines coordonnés ou plus.

**Échantillon relu (vérifié, `population_sample.txt`, graine 7, 2 chunks au plus par document)** :
- 55 chunks étiquetés (15 « table », 20 « section », 20 « document » ; les étiquettes « table » ne viennent que de 3 documents) : **3 erreurs strictes** (n° 24 obstétrique sur une exérèse d'endométriose ; n° 29 pédiatrie sur un argumentaire adulte ; n° 51 néonatal sur un document « nouveau-né exclu »), soit **5,5 % [IC 95 % Wilson 1,9 ; 14,8]**. S'y ajoutent 2 étiquettes « document » trop larges (n° 39 : tableau SSC adultes étiqueté adulte + pédiatrie + néonatal ; n° 40 : score adulte étiqueté adulte + pédiatrie).
- 30 chunks sans étiquette : aucun oubli net. « Sans étiquette » veut dire « non précisé », ce qui est voulu ; le n° 79, un schéma d'amygdalectomie, est douteux.
- Les erreurs systématiques C4 et M3 pèsent beaucoup plus que ce taux d'échantillon : environ 700 + 70 + plusieurs centaines de chunks.

### MINEURS (peuvent attendre)

- **m1. La règle « mention explicite » se déclenche sur la bibliographie** (`loader.py`, `_apply_explicit_update_mentions`). Vérifié en relâchant une condition : elle s'active sur « [1] Samama … Prévention de la MTEV postopératoire. Actualisation 2011 » et sur « (Source : SFAR SFPC … Actualisation 2016) ». Aucun effet aujourd'hui, car ces documents sont déjà remplacés par des lignées curées. Correctif : exclure les lignes `[n]` et `- [n]`, et exiger le mot de mise à jour et l'année dans la même phrase.
- **m2. Urgences obstétricales 2010** : le remplacement est justifié, mais la RPP 2022 (sept champs) ne traite plus les hémorragies du 2e et du 3e trimestre, les transferts in utero ni le recours au SAMU, chapitres 1, 3 et 8 de 2010. Masquer 2010 rend ces sujets introuvables : abstention possible. Indiquer « remplacement partiel » dans `supersession_evidence` et faire valider.
- **m3. Doublons actifs non traités (antérieurs à B2)** : AAP 2018 et « AAP en urgence » 2021 (Jaccard 0,974, tous deux en vigueur ; la copie datée de 2021 a l'air plus récente) ; TIH 2019, deux fichiers (Jaccard 0,999). Proposition : une règle « jumeaux » pour les documents actifs, qui ne garde qu'une copie avec la date de la plus ancienne.
- **m4. « Abord extra-oral ( ) »** : le texte en italique « sans contamination locale » est perdu dans la découpe des listes parallèles. Ce code ABP existait avant B2 (`table_parser.py:494-503`). Défaut vérifié en V3.0 et V3.1. La fiche de suite perd aussi son contexte parent « Chirurgie de la face avec reconstruction par lambeau ». Correctif : construire le préfixe avec `_li_text` au lieu des seules chaînes directes.
- **m5. Valeur et unité séparées par « / »** quand un `<br>` les coupe (`table_parser.py:285`), par exemple « Dopamine ≤ 5 / µg/kg/min » (IH 2018). Défaut antérieur à B2 : 13 chunks, 3 documents. Correctif : traiter comme une suite de phrase toute ligne qui commence par une unité ou par `\`.
- **m6. Réparation des octets NUL** : « Entraînement supervisé (à 3 fois par semaine) » (résection hépatique 2025). La docstring parle d'un « ≥ » de repli, mais il n'est jamais atteint, car `_WORD_RE` inclut `\x00` et une paire isolée passe donc par le vocabulaire (« à »). Déduit (le PDF est un pointeur LFS, invérifiable) : le caractère d'origine est probablement « ≥ ». Un seul cas.
- **m7. Fiches de ligne créées à partir de tables des matières** (seuil de 2 colonnes), par exemple « Section : Sommaire / Tableau 1 : … — 18 ». Ce sont des fiches parasites ; filtrer les lignes à points de conduite.
- **m8. Tableaux sans en-tête** : `_row_line` (`table_parser.py:82`) supprime les cellules vides, et la position des valeurs est perdue. L'effet est moindre puisqu'il n'y a pas de noms de colonnes.
- **m9. En-tête de colonne d'un premier sous-tableau réutilisé pour un autre** : brûlés, « Centres … Adultes Métropole : Nantes | CHU Nantes PTMC Réa Pédiatrique » sous « Sous-catégorie : Enfants ».

---

## 1. Surapprentissage : règle par règle

Comptes vérifiés en rechunkant le corpus en mémoire (`R1_annexes/rule_firing.py` → `rule_firing.json`), sur 265 documents dont 183 avec tableaux (2 190 tableaux).

| Règle (fichier) | Auteur | Documents / événements | Verdict |
|---|---|---|---|
| Lignes pleine largeur libellé / note (`table_parser.full_width_row_kind`) | B2 | 63 documents / 1 016 libellés ; 37 / 106 notes | **générique**, mais défaut M1 |
| Tableaux sans en-tête rendus sans « Col N », fiches dès 2 colonnes | B2 | 183 documents | **générique** (m7, m8) |
| Reprise de la clé de ligne après saut de page (`carry_first_cell`) | B2 | 25 / 105 tableaux ; 40 cas relus, tous des suites de cellule plausibles | **générique** |
| Note de périmètre « … de/dans/du ce tableau … » propagée tant que le titre reste ouvert (`chunker._scope_note_text`, `TABLE_NOTE_RE`) | B2 | **2 documents** (ABP V3.0 et V3.1) / 92 tableaux, tous dans le champ 3 pédiatrique ; aucun tableau adulte touché | **limite** : formule générique, effet propre à l'ABP. La limite de 400 caractères et 3 paragraphes vise à inclure « 2 g maximum ». À évaluer sur un autre guide ou à documenter comme convention de mise en page. |
| Liaison des notes à appel `*`, `**`, `†`, `#` (`chunker`) | B2 | 57 / 321 liaisons ; aucune confusion avec une multiplication (`2* âge`) | **générique** (un mauvais rattachement vient de M1) |
| Titre de tableau (« Tableau N », ligne en gras) | B2 | 79 / 266 | **générique** |
| Nettoyage LaTeX, entités HTML, balises, images | B2 | environ 219 documents | **générique**, mais défauts C1 et C3 |
| Réécriture Mermaid | B2 | 83 documents / 164 blocs | **générique**, mais défaut C2 |
| Réparation NUL (vocabulaire) | B2 | 2 documents | **générique** (m6) |
| Populations : liste de termes et de négations (`population.py`) | B2 | 141 documents | **générique**, sauf « se référer au tableau adulte » et « comme chez », tirés de la note ABP mais formulés comme un renvoi générique : **limite acceptable**. Défauts C4 et M3. |
| Mention explicite de mise à jour (`loader._apply_explicit_update_mentions`) | B2 | 1 changement (urgences obstétricales) | **limite**, n = 1 : impossible d'en mesurer la généralisation (m1) |
| Jumeau d'un document abrogé (`_apply_abrogated_twins`, Jaccard ≥ 0,9) | B2 | 1 changement (COVID) ; un seul document abrogé dans le corpus | **générique**, mais non testable au-delà de ce cas |
| Retrait manuel de « Recommandations AVK » de la lignée | B2 | 1 document | cas particulier **manuel** justifié par le périmètre, pas par une question ; **faux sur le fond** (M2) |
| Correctif des coquilles de l'overlay (« Lithotritie », « Amygdalectomie ») | B2 | 3 remplacements | correction vraie (PDF officiel), mais **choisie à partir des questions DEV Q115 et Q120** : **limite (méthode)**. Proposition : passer tout l'overlay au crible (mots hors vocabulaire du corpus et du PDF) pour que la correction ne dépende plus des questions. |
| En-tête `<td>` reconnu par une liste qui contient « amoxicilline », « céfazoline » (`table_parser.py:385-413`) | antérieur | 2 documents / 2 tableaux | **surappris (antérieur)** ; à remplacer par des marqueurs de dose génériques |
| Découpe des listes parallèles sur « PAS D'ANTIBIOPROPHYLAXIE » (`table_parser.py:526-542`) | antérieur | 4 documents (3 éditions ABP + ECBU) / 44 tableaux candidats | **surappris (antérieur)**, reconnu par B2 ; à généraliser (« contradiction entre lignes » sans mot-clé) |
| `ALLERGY_BOX_RE`, `ANTIBIOPROPHYLAXIE EN` dans `_update_major_section`, « historique des versions » | antérieur | `callout_allergy` : 2 documents (ABP) | **propre à l'ABP (antérieur)** |

Tests : `tests/test_ingestion_b2.py` n'utilise que des données synthétiques (« Acte gamma », « Chirurgie zeta », « moins de 40 kg ») et n'encode aucun cas du benchmark. La suite complète passe (`pytest`, 113 tests), anti-fuite compris. Il manque des tests de non-régression pour C1, C2 et C3.

## 2. Exactitude du texte transformé : méthode et constats complémentaires

- **Contrôle automatique sur tous les tableaux** (`table_fidelity.py`, `table_words.py`, vérifié). Jetons cliniques des 2 190 tableaux sources (nombres avec unité, comparateurs, intervalles, « pas d'antibioprophylaxie », négations), soit 8 935 jetons : 11 restent absents des chunks de tableau dans `tas_v4`, contre 242 dans `tas_v3_errata`. Les 11 viennent de m5 (valeur et unité séparées par « / », 7 cas) et de 4 faux positifs de l’extracteur (années de références bibliographiques, IMC). C3 n'apparaît pas ici, parce que la source et le chunk passent tous deux par `replace_math`. Mots des cellules (18 950 cellules) : 4 cellules ont des mots manquants dans `tas_v4`, contre 429 dans `tas_v3_errata` ; tous viennent de m4. Lignes avec dose : sur les 547 lignes dont la clé se retrouve dans une fiche, 1 seule n'a pas sa dose dans la fiche de sa clé dans `tas_v4`, contre 14 avant (ABP 2017, en anglais, ligne « or Cefamandole »). Sur la **complétude**, B2 améliore donc nettement l'index ; les défauts portent sur la **structure** (C1) et sur certaines **transformations** (C2, C3).
- **Relecture manuelle** (`table_sample.txt`) : 42 tableaux de 42 documents différents, de 1996 à 2026 et sans date. On y trouve des PDF anciens (2001, 2003, 2004), des cellules fusionnées (`rowspan`/`colspan` : AAP 2006, cardiopathies congénitales 2023, ABP 2017/2018, WSES 2026), des notes (pré-éclampsie 2020, β-lactamines 2018) et des scores (Lee, SOFA, MFI). Les fiches de ligne sont fidèles dans tous les cas relus, et ≥/≤/× sont bien convertis (urgences obstétricales « Terme ≤ 24 SA », PAS ≥ 180 mmHg, 10⁹/L). Tous les `table_markdown` de plus d'une ligne sont aplatis (C1), et 6 ont un décalage de colonnes visible (T4, T10, T12, T13, T32, T40).
- **Organigrammes** : C2. Les 151 autres blocs gardent leurs arêtes et leurs libellés OUI/NON. Les conditions comptées passent de 327 dans les sources à 331 dans les sorties, à cause de libellés répétés.
- **Populations** : voir C4, M3 et l'échantillon.

## 3. Éditions (détail)

- **Urgences obstétricales 2010 → RPP 2022** : vérifié dans le texte 2022, introduction l. 154 : « En 2010, la SFAR et la SFMU ont publié des recommandations formalisées d'experts sur les urgences obstétricales extrahospitalières [1] … une mise à jour de ces recommandations semblait nécessaire ». Mêmes sociétés (SFMU et SFAR, avec le CNGOF). **Justifié**, avec la réserve m2 (remplacement partiel).
- **COVID « finale sans marque » → abrogée** : vérifié. Même titre et même version (3.1, avril 2022), Jaccard des 5-grammes 0,936 avec le fichier marqué « **Abrogées le 01/07/2023** ». **Justifié.**
- **AVK HAS 2008 → en vigueur** : **non justifié** (M2).
- **Faux positifs possibles des règles génériques** (`editions_audit.txt`, vérifié) :
  - `_apply_explicit_update_mentions` ne change qu'un document (urgences obstétricales). Les autres déclenchements ou quasi-déclenchements visent tous des documents **déjà** remplacés par une lignée curée : IIA 2015, MTEV 2011, erreurs médicamenteuses 2016 (×2), TIH 2002. Faux négatifs de la règle, déjà couverts par les lignées : hyperthermie maligne 2013, intubation difficile 2006, pancréatite 2001, remplissage 2012, allergie 2011, sédation en urgence 2010. Quasi-faux positif sans effet : l'optimisation hémodynamique **pédiatrique** 2024 mentionne la « réactualisation » du remplissage 2012 adulte, mais le recouvrement de titre (0,25) est sous le seuil de 0,5. Mécanisme de faux positif : m1.
  - `_apply_abrogated_twins` : un seul document abrogé dans le corpus. Toutes les paires avec Jaccard ≥ 0,5 : ABP V3.0/V3.1 (0,996, déjà remplacé), AAP 2018/2021 (0,974, actifs, m3), COVID (0,936, la règle), TIH 2019 ×2 (0,999). **Aucune paire entre 0,8 et 0,9.**

## 4. Ce que je n'ai pas fait

- Je n'ai pas relancé le retrieval, ni la couverture du mapping abpe171 (341 → 347/348) : la commande `datasets coverage --suite abpe171` charge la suite entière, test compris.
- Je n'ai pas vérifié les coquilles dans le PDF, ni le caractère de m6 : les PDF de `data/` sont des pointeurs LFS.
- Je n'ai pas mesuré l'effet des correctifs proposés : cela demande une reconstruction de l'index, interdite dans ce mandat.

## 5. Reproductibilité du rapport B2 (`recompute_b2_diffs.tsv`)

Toutes les lignes du tableau « Avant / après » et du tableau « Mesure pas à pas » se reproduisent exactement avec `harness.paired_bootstrap_diff` (2 000 tirages, graine 0), y compris les IC. Exemples : abpe171 C9, suffisance +7,3 [+2,1 ; +13,5] ; multirfe, fenêtres, hit −2,6 [−6,6 ; 0,0] ; rejet de v4_h −3,9 [−9,2 ; 0]. Le sous-groupe pédiatrique (n = 9 : 44,4 → 77,8 en C9, 66,7 → 77,8 avec fenêtres), la liste des échecs restants et les 51 compteurs structurels (`scripts/ingestion_structural_checks.py --from-index index/tas_v4`) se reproduisent aussi : 0 écart avec `B2_annexes/structural_tas_v4.json`.

Imprécisions :
1. « multirfe_synth (94) » : les métriques de passage portent sur **n = 76** questions (celles qui ont un passage de référence).
2. Le doc hit de multirfe baisse aussi : 97,4 → 96,1 en C9 et 100 → 98,7 avec fenêtres. Le rapport ne cite le doc hit que pour abpe171 et abp171.
3. « Corrigés par v4 … (aucune régression) » n'est vrai qu'avec les fenêtres. En C9, Q91 régresse (1 → 0), avec en contrepartie 8 gains (Q28, Q40, Q52, Q74, Q120, Q139, Q157, Q158).

Rappel (déjà signalé par B2) : l'étape `tas_v4_c` regroupe trois variables (nettoyage OCR, plafond de taille, éditions), ce qui ne respecte pas strictement le principe 5. C'est précisément dans ce lot que C1 et C3 sont entrés sans être vus.

## 6. Ordre de correction proposé

1. Avant l'évaluation finale : C1, C2, C3, C4, puis M1, M2, M3. Ajouter des tests de non-régression synthétiques pour chacun. Reconstruire dans un nouveau dossier (par exemple `index/tas_v5`), sans écraser `tas_v4`.
2. Contrôles à ajouter à `scripts/ingestion_structural_checks.py` : nombre de lignes et de `|` par ligne des `table_markdown` comparés à la source ; jetons numériques des blocs Mermaid retrouvés dans la sortie ; résidus `\\[A-Za-z]+`, `mug` et `mumol` ; négations placées après le terme.
3. Ensuite : m1 à m9. Faire valider médicalement m2 et M2.
