# B2 — Ingestion et indexation : chaque information du corpus retrouvable et lisible

Date : 2026-11-27. Agent B2 (Opus). Périmètre : `src/rag_sfar/ingestion/*`, `schemas.py` (ajouts rétrocompatibles), indexation de `cli.py`, erratum de l'overlay V3.1.

**Index recommandé : `index/tas_v4`** (265 documents, 36 862 chunks ; options du chunker : nettoyage OCR, plafond 2 400 car., en-tête historique, sans unités « recommandation »). Construit avec le code du commit final :

```bash
HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-index --strategy table_aware_sota --output-dir index/tas_v4
# (options par défaut = configuration retenue ; variante : --chunker-options "reco_units=1")
```

## Avant / après (DEV, retrieval seul, `tas_v3_errata` → `tas_v4`)

Même code de retrieval et d'évaluation pour tous les runs (copie figée de `src/` au commit `5823f5a`, `PYTHONPATH`), `--k 64` (métriques sur tout le contexte), IC = `harness.paired_bootstrap_diff` (2 000 tirages). Rapports : `reports/eval/*_b2_base.*` et `*_b2_v4.*` ; détail par question : `reports/agents/B2_annexes/cmp_tas_v3_errata_vs_tas_v4.md`.

| Jeu (n) | Config | Métrique | tas_v3_errata | **tas_v4** | Écart [IC 95 %] |
|---|---|---|---:|---:|---|
| abpe171 (102) | C9 | **Suffisance** | 83,3 | **90,6** | **+7,3 [+2,1 ; +13,5]** |
| | C9 | Rappel des preuves | 89,7 | 93,8 | +4,2 [+0,7 ; +8,3] |
| | C9 | Passage hit | 96,1 | 98,0 | +2,0 [−2,0 ; +5,9] |
| | C9 + fenêtres | **Suffisance** | 88,5 | **93,8** | **+5,2 [+1,0 ; +9,4]** |
| | C9 + fenêtres | Rappel des preuves | 92,8 | 95,9 | +3,1 [+0,2 ; +6,8] |
| | C9 + fenêtres | Passage hit | 98,0 | 98,0 | 0,0 [−2,9 ; +2,9] |
| multirfe_synth (94) | C9 | Passage hit | 85,5 | 84,2 | −1,3 [−6,6 ; +3,9] |
| | C9 + fenêtres | Passage hit | 100,0 | 97,4 (98,7 corrigé*) | −2,6 [−6,6 ; 0,0] |
| | C9 + fenêtres | Passage hit@8 | 88,2 | 84,2 | −3,9 [−9,2 ; 0,0] |
| abp171 (102) | C9 | Passage hit | 94,1 | 97,1 | +2,9 [−2,0 ; +7,8] |
| | C9 + fenêtres | Passage hit | 99,0 | **100,0** | +1,0 [0,0 ; +2,9] |
| | C9 + fenêtres | Passage hit@8 | 91,2 | 95,1 | +3,9 [−1,0 ; +9,8] |

Intrusion d'édition obsolète : 0 partout. Doc hit abpe171/abp171 : 100 partout.
\* multirfe : sur les 2 questions perdues, MR-g8f23… a un passage gold annoté sur la **syntaxe Mermaid brute** (« C{HÉMOPÉRITOINE ABONDANT … B --> D[SCANNER INITIAL] ») ; l'information est toujours là, réécrite en organigramme lisible, et la fiche est récupérée (rang 4) : artefact d'annotation. MR-gcb72… : le chunk gold est identique dans les deux index ; perte de classement (le top 5 est hors sujet dans les deux runs : problème de requête pour B1).

**Couverture du mapping abpe171** (`python -m rag_sfar.evaluation.datasets coverage --suite abpe171 --index index/<dir>`) : passages gold 341/348 → **347/348** ; preuves 217/222 → **221/222** ; questions dont un ensemble de preuves est entièrement mappable 94/96 → **96/96** (le plafond de suffisance passe à 100 %).

**Compteurs structurels** (`scripts/ingestion_structural_checks.py`, sorties `B2_annexes/structural_*.json`) :

| Compteur | tas_v3_errata | tas_v4 |
|---|---:|---:|
| Chunks / fiches de ligne (`table_row_card`) | 33 406 / 6 110 | 36 862 / **9 919** |
| Tableaux ≥ 2 colonnes sans fiche de ligne (dont sans en-tête) | 687 (492) | **51 (22)**¹ |
| Chunks avec en-têtes factices « Col N » / « Colonne N » (fiches / tableaux) | 1 897 / 1 326 | **0 / 0** |
| Lignes pleine largeur (colspan) perdues | 104 / 780 | **0 / 780** |
| Cellules du corpus absentes de tout chunk | 213 | **14** |
| Texte du corpus non couvert (hors bibliographie) | 0,56 % | 0,32 %² |
| Chunks > 4 000 car. (max) | 4 (21 454) | **1 (4 096)** |
| Résidus dans le texte : LaTeX `$…$` / commandes `\geq…` / octets NUL / balises HTML | 4 149 / 3 612 / 328 / 13 410 | **2 / 0 / 0 / 0** |
| Descriptions d'images générées (anglais) non marquées / Mermaid brut | 575 / 160 | 0 / 4 |
| Notes de bas de tableau liées aux lignes qui les appellent | 0 | 321 |
| Tableaux portant une note de périmètre / un titre | 0 / 0 | 92 / 266 |

¹ Tableaux d'allergie ou tableaux d'une seule ligne vide. ² Le reste : syntaxe Mermaid (réécrite, donc absente telle quelle), listes d'auteurs, sous-lignes « Durée ≤ 2h / > 2h » désagrégées (structure, pas perte).

## Mesure pas à pas (une variable à la fois)

Index intermédiaires (mêmes runs, mêmes réglages) :

| Étape | Index | abpe171 suff. C9 / fenêtres | multirfe passage hit fenêtres | abp171 passage hit@8 fenêtres | Décision |
|---|---|---:|---:|---:|---|
| Référence | tas_v3_errata | 83,3 / 88,5 | 100,0 | 91,2 | — |
| + tableaux (§1) + erratum coquilles | tas_v4_t | 88,5 / 92,7 | 98,7 | 94,1 | gardé (suff. +5,2 [0 ; +11,5] en C9) |
| + nettoyage OCR + plafond + éditions (§3, §4, §6) | tas_v4_c | 90,6 / 93,8 | 97,4 | 95,1 | gardé (abpe +2,1 [0 ; +5,2] ; multirfe −1,3 [−5,3 ; +2,6], 1 artefact) |
| + en-tête sans domaines, statut « en vigueur » (§4) | tas_v4_h | 88,5 / 92,7 | 93,4 | 93,1 | **rejeté** (multirfe −3,9 [−9,2 ; 0]) |
| + unités « recommandation » (§5) | tas_v4_r | 88,5 / 92,7 | 93,4 | 91,2 | **rejeté** (neutre, doublons) |
| Final (= v4_c + organigrammes compacts) | **tas_v4** | **90,6 / 93,8** | 97,4 | 95,1 | recommandé |

`tas_v4_t` ne contient pas les corrections d'éditions (code figé avant) ; à partir de `tas_v4_c` toutes les variantes les contiennent. L'erratum des coquilles (§3) est dans toutes les variantes v4 (appliqué dans `data/` avant la première construction).

Échecs de suffisance restants (abpe171, fenêtres) : Q05, Q07, Q41, Q44, Q131, Q171 — tous des preuves présentes dans l'index (mapping 100 %) mais non classées : lignes ou notes de tableaux pédiatriques et QCM multi-tableaux. Corrigés par v4 : Q28, Q74, Q120, Q149, Q157 (aucune régression). Sous-groupe `population:pediatric` (n=9) : 44,4 → 77,8 en C9, 66,7 → 77,8 avec fenêtres.

## 1. Tableaux

**Causes (lecture du code et de 18 documents).** `_clean_cell_text` ne gardait que les `<li>` (texte hors liste perdu, listes imbriquées écrites deux fois) ; une ligne pleine largeur était toujours un « bandeau » (sous-catégorie appliquée aux lignes suivantes, perdue si elle terminait le tableau, et les phrases « En cas de … considérer … » devenaient des sous-catégories) ; un tableau sans en-tête reconnu (`<td>` partout, ou largeur différente du tableau précédent, typiquement les tableaux de 3 colonnes « PAS D'ANTIBIOPROPHYLAXIE ») ne recevait ni fiche de ligne ni nom de colonne (« Col 1 | Col 2 ») ; le libellé de sous-catégorie n'existait qu'en titre Markdown (`section_path`) ; une ligne coupée par un saut de page perdait sa clé (rowspan orphelin) ; les tableaux placés sous un titre « Références » étaient ignorés ; les notes `*`, `**`, `#` sous les tableaux n'étaient liées à rien.

**Corrections (`ingestion/table_parser.py`, `ingestion/chunker.py`).**
- (e) Texte de cellule complet : tout nœud texte gardé une fois, listes imbriquées « parent : enfant ; enfant », sauts de ligne `<br>` recollés quand la ligne suivante continue la phrase (« 1g si durée > 4h, puis toutes les 4h jusqu'à fin de chirurgie »), sinon « / ».
- (b) Lignes pleine largeur classées `label` (titre de sous-groupe : court, sans verbe ni ponctuation finale, ou question « … ? ») ou `note` (italique, phrase, appel `*`, « En cas de / Si / NB », > 140 car.) ; une note est rattachée au groupe de lignes qui la précède (ou au tableau si elle est en tête) ; un label final est gardé comme ligne.
- (a) Tableaux sans en-tête : rendus en lignes « a | b | c » sans en-tête inventé, et fiches de ligne « a — b — c » (seuil 2 colonnes au lieu de 3) ; en-têtes vides = sans nom (plus de « Col N »).
- (c) Chaque fiche porte « Section : » (deux derniers titres, donc la sous-catégorie quand elle est un titre), « Sous-catégorie : » (bandeau), « Tableau : » (légende « Tableau N » ou ligne en gras juste avant), et les en-têtes de colonnes.
- (d) Continuation de page : si le tableau précédent est contigu, de même section, et que les premières lignes ont une première cellule vide, elles reprennent la clé de la dernière ligne (105 tableaux).
- (f) Note de périmètre (« Les posologies de ce tableau concernent l'enfant (hors néonatalogie) de moins de 50 kg… » + paragraphes courts suivants, ex. dose maximale) : ajoutée en « Périmètre : » à toutes les fiches et tableaux suivants tant que le chemin de titres reste ouvert (92 tableaux). Notes à appel (`*`, `**`, `***`, `†`, `#`) : ajoutées en « Note (*) : … » aux seules fiches dont une cellule porte l'appel (321 liaisons ; le gras Markdown `**Titre**` n'est pas un appel).
- Tableaux sous « Références » gardés ; tableaux d'en-têtes seuls (grilles vides) gardés.

**Mesure** : voir tableaux ci-dessus (étape tas_v4_t ; mapping 96/96). Exemple de fiche (structure, synthétique) : `Section : PARTIE 2 … > Chirurgie X` / `Périmètre : Les posologies de ce tableau concernent l'enfant…` / `Sous-catégorie : …` / `Actes … : … | Molécules : … | Dose initiale : …` / `Note (*) : …`.

## 2. Population par chunk (champ nouveau)

`Chunk.populations: list[str]` ⊂ {`adulte`, `pediatrie`, `neonatal`, `obstetrique`} et `Chunk.population_source` ∈ {`table`, `section`, `document`, ``} (`ingestion/population.py`). Règles, par priorité : (1) première phrase de la note de périmètre, titre ou bandeau du tableau ; (2) chemin de titres, de la racine vers la feuille (un titre plus profond qui nomme une tranche d'âge remplace la tranche héritée ; `obstetrique` s'ajoute) ; (3) titre du document. Rien n'est déduit de la prose libre. Négations ignorées : « hors néonatalogie », « sauf », « non obstétrical », « se référer au tableau adulte », « comme chez l'adulte ». `neonatal` implique `pediatrie`.

Couverture (34 145 chunks hors bibliographie) : `table` 476, `section` 4 419, `document` 10 126, aucune 19 124 (56 %) ; 141/265 documents ont au moins un chunk étiqueté. Étiquettes : adulte 8 556, pédiatrie seule 2 185, obstétrique seule 1 384, néonatal+pédiatrie 852, mixtes le reste. RFE ABP V3.1 : 429 chunks adulte, 285 pédiatrie, 42 néonatal, 60 obstétrique. Accord avec l'ancien `population_hint` : 93 % ; désaccords surtout `pediatrie` (ancien, déduit des 800 premiers caractères du texte) → non spécifié (nouveau).
`population_hint` (utilisé par la pénalité 0,72 du rerank) **n'a pas été modifié** : option `population_hint=structural` disponible (dérivée de `populations`), non mesurée ici (variable de B1).

## 3. Nettoyage OCR déterministe (`ingestion/text_cleaning.py`, option `clean_ocr`)

Octets NUL réparés par le vocabulaire du corpus (« R\x00\x00serve » → « Réserve » ; un seul candidat accentué connu, sinon « é ») ; entités HTML (y compris `&amp;gt;`) ; LaTeX inline, `$$…$$`, `<math>` et LaTeX nu des cellules → Unicode (≥, ≤, ×, µ, ², indices) ; `<sub>/<sup>`, `<br>`, balises de mise en forme et fragments `<td>/<tr>` orphelins ; puces et numéros doublés (« - • », « 1. 1. ») ; images : logos/icônes/photos supprimés, autres descriptions marquées « [Image, description automatique en anglais : …] » ; 164/166 organigrammes Mermaid réécrits en lignes « A → (OUI) B » (libellé complet à la première mention puis abrégé ; +12 % de caractères) et marqués « [Organigramme (converti depuis le schéma OCR)] ». Les titres collés au texte étaient déjà décollés par le loader (0 résidu).
Mesure : étape tas_v4_c (avec le plafond et les éditions) : abpe171 +2,1 pts de suffisance [0 ; +5,2] ; multirfe −1,3 [−5,3 ; +2,6] (deux questions, dont un artefact d'annotation Mermaid).

**Coquilles de l'overlay V3.1** vérifiées dans le PDF officiel (pypdf) : p. 89 « Lithotritie extra-corporelle », p. 96 « Amygdalectomie », « Adéno-amygdalectomie ». Erratum **appliqué** dans `data/corpus_updates/` (écriture autorisée) : script `reports/agents/B2_annexes/apply_errata_typos.py` (remplacements exacts, comptes vérifiés), entrée « Erratum 2 » dans `data/corpus_updates/ERRATA.md`, copie avant correction `data/corpus_updates_backup/RFE-V3.1_before_B2_typos.md` (rien de `data/` n'est commité). Effet : Q115 (Lithotritie) passe du rang 5 au rang 1 (fenêtres, abpe171), Q120 devient suffisante.

## 4. Taille, forme des chunks, en-tête

- Plafond dur (`hard_max_chars`, 2 400 ; 4 000 pour l'historique des versions) : découpe sur lignes puis mots les morceaux sans ponctuation. Plus grand chunk de prose 21 454 → 2 384 car. ; seul chunk > 4 000 : une fiche de ligne d'un formulaire de 2001 (4 096).
- En-tête existant dans `indexed_text` (vérifié) : `[<type> SFAR <année> <version> <statut si remplacé> | <titre> | Domaines : <3 domaines> | Section : <chemin> | Tableau structuré]`. Variante mesurée (tas_v4_h) : sans domaines + « [en vigueur] » systématique → **rejetée** (multirfe −3,9 pts [−9,2 ; 0], abpe −2,1 [−5,2 ; 0] en C9). L'en-tête historique est gardé ; option `header_domains=all|declared|none`, `header_status` pour B1. Je n'ai pas mesuré séparément chaque élément (titre, année, section) : faute de temps machine (file GPU partagée), un seul test d'en-tête.
- Domaines : la correction « mot entier » du loader était déjà dans `tas_v3_errata` (219 documents gardent au moins un domaine imputé par mot-clé, ex. ABP : Infectiologie, Neuro-Réanimation, Traumatologie, Obstétrique, Pédiatrie). Retirer les domaines de l'en-tête n'aide pas sur dev : ils restent, signalés comme bruités.

## 5. Unités « recommandation » (option `reco_units`)

`chunk_corpus` lance `reco_extractor` sur les documents chargés (overlay compris) et ajoute un chunk `recommendation_unit` par unité primaire : « Contexte : champ > question > titre / Recommandation : R… – énoncé / Cotation : GRADE… ; accord… ». Le chunk est hors de la chaîne de lecture : `prev_chunk_id` = chunk du flux qui contient l'énoncé (`source_chunk_id`), `next_chunk_id` = son successeur (une fenêtre ±1 ramène l'argumentaire). 3 578 unités (3 481 rattachées à un chunk source), 122 documents. Champs : `reco_strength`, `reco_strength_raw`, `reco_agreement`, `reco_label`.
Mesure (tas_v4_h → tas_v4_r) : neutre (abpe171 0,0 ; multirfe passage hit 0,0 [−3,9 ; +3,9] ; abp171 hit@8 −2,0 [−4,9 ; 0]). Les énoncés existent déjà dans les chunks de prose/encadrés ; les unités dupliquent. **Non retenues** dans l'index recommandé ; `index/tas_v4_r` est gardé pour B1 (utile si l'on veut filtrer par force, ou présenter la cotation à part).

## 6. Éditions

Corrections génériques dans `loader.py`, chacune avec sa preuve dans le nouveau champ `DocumentMetadata.supersession_evidence` :
- **Mention explicite** (`_apply_explicit_update_mentions`) : un paragraphe des 40 000 premiers caractères d'un document plus récent contient un mot de mise à jour (mise à jour, actualisation, remplace, révision, update) et une année Y ; un document actif de l'année Y a ≥ 3 mots de titre, tous présents dans le paragraphe, et au moins la moitié présents dans le titre du nouveau (même sujet) ; familles différentes. Toute l'édition (même famille, même année) est marquée.
- **Quasi-copie d'un document abrogé** (`_apply_abrogated_twins`) : Jaccard des 5-grammes ≥ 0,9 avec un document abrogé de même année ou postérieur → abrogé aussi.
- Lignées curées : inchangées, sauf retrait de « Recommandations AVK » (HAS 2008) de la lignée « procédure programmée ».

**Changements de statut à faire relire** (liste complète avec preuves : `reports/agents/B2_annexes/editions_review.md`) :

| Document | Avant → après | Preuve | Niveau |
|---|---|---|---|
| Urgences obstétricales extrahospitalières (2010, `2010_2_AFAR_Urgences-Obstetricales-Extrahospitalieres_47ad85`) | en vigueur → **remplacé** par la RPP 2022 urgences obstétricales | Texte 2022, introduction : « En 2010, la SFAR et la SFMU ont publié des recommandations … sur les urgences obstétricales extrahospitalières … une mise à jour de ces recommandations semblait nécessaire » | fort (mention explicite) |
| RPP COVID avril 2022 « finale sans marque » (`2022_RPP_20SFAR_20COVID_…_c5bf31`) | active → **abrogée** | Jaccard 5-grammes 0,94 avec `RPP-SFAR-COVID_Version-Avril-2022_abrogee-010723` | fort (même texte) |
| Recommandations AVK (HAS 2008, surdosage/hémorragie sous AVK) | remplacé par « procédure programmée 2026 » → **en vigueur** | Périmètre différent (audit données §3.2) ; plus probablement couvert par « anticoagulation en urgence 2024 », à confirmer | doute → visible |

Gardées en l'état mais douteuses (audit données) : 4 documents sepsis 2004–2006 remplacés par HAS sepsis 2025, guideline britannique DAS 2015 remplacée par la SFAR 2026. Extension des lignées : la règle « mention explicite » ne trouve qu'un seul lien nouveau ; la similarité de titres (Jaccard ≥ 0,4, sans mention) ne donne que des faux positifs (crâniens ~ pelviens, anémie ~ pancréatite, AAP ~ anticoagulants…) : non appliquée, listée pour relecture. Mesure : aucun effet sur les trois jeux (aucune question ne vise ces documents) ; intrusion obsolète 0.

## 7. Revue de 18 documents (2000–2026, formats variés)

Script `B2_annexes/survey_documents.py`, sortie `B2_annexes/survey_18_documents.txt` (avant/après : nombre et types de chunks, taille max, doublons de 8-grammes, résidus, populations). Constats :
- **Perdus avant** : texte hors `<li>` des cellules, lignes colspan finales, lignes de tableaux sous « Références » (grilles ECBU 2026), questions « Q1.7 … ? » des gabarits HAS 2026 (bandeaux), libellés « Champ 1 – … » en ligne de tableau (nutrition 2026).
- **Déformés avant** : LaTeX dans les posologies et seuils (HSA 2004 : 456 résidus ; MTEV 2024 : 52), octets NUL (résection hépatique 2025), organigrammes en syntaxe Mermaid (algorithmes 2024–2026, fiches 2019), descriptions d'images en anglais mêlées au texte, « Col 2 » comme nom de colonne (voies aériennes 2026), chunks de 7 752 et 21 454 car. (HAS 2010 information, guide réanimation éphémère).
- **Dupliqués** : listes imbriquées écrites deux fois dans les cellules (corrigé) ; les mêmes recommandations existent dans texte court / long / fiche (inchangé, structure du corpus) ; la note de périmètre est désormais répétée dans chaque fiche (voulu : autonomie de la fiche).
- **Reste à traiter** : ~1 000 chunks de prose ressemblent à de la bibliographie dans 80 documents sans titre « Références » ; 285 chunks de prose en anglais dans des documents FR/bilingues (résumés, traductions intégrées) ; la désagrégation des listes parallèles (`table_parser`, « PAS D'ANTIBIOPROPHYLAXIE ») reste une règle propre à l'ABP ; 210 commandes LaTeX restent dans les en-têtes (titres de section non nettoyés).

## Ce que le retrieval (B1) peut exploiter

- `Chunk.populations` / `population_source` : garantir dans le contexte au moins un chunk de la population demandée (ou des deux quand la question n'en précise pas) ; préférer `table`/`section` à `document`. Option d'index `population_hint=structural` pour remplacer l'ancienne heuristique (à mesurer).
- `Chunk.table_id` : regrouper fiches et tableau parent sans parcourir la chaîne `prev_chunk_id` ; ramener la fiche sœur pédiatrique/adulte d'une même ligne d'acte.
- Fiches de ligne autonomes (« Section », « Périmètre », « Note (*) ») : la règle `_own_table_notes` du pipeline devient en partie redondante.
- `chunk_type == "recommendation_unit"` (index `tas_v4_r`) avec `reco_strength`, `reco_agreement`, `source_chunk_id`.
- `DocumentMetadata.supersession_evidence` : afficher pourquoi une édition est masquée.
- Les questions perdues hors ABP sont des problèmes de classement, pas de texte (MR-gcb72… : top 5 hors sujet).

## Ce qui reste imparfait

- Le gain est net sur ABP (abpe171 suffisance +5 à +7 pts, IC > 0) mais **pas démontré hors ABP** : multirfe recule de 1 à 3 pts (IC incluant 0 ; une perte sur deux est un artefact d'annotation, l'autre une perte de classement). À recontrôler avec les fenêtres et le retrieval de B1.
- Les passages gold de multirfe/abp171 sont annotés sur l'ancienne forme des chunks : un passage gold en syntaxe Mermaid (g8f23) ne peut plus correspondre.
- La classification label/note des lignes pleine largeur est heuristique (106 notes détectées) ; aucune relecture humaine exhaustive.
- Le seuil de 2 colonnes ajoute ~3 800 fiches, dont des tableaux à une seule ligne (doublon partiel avec le tableau) : non ablaté séparément des autres corrections de tableaux.
- Un seul test d'en-tête (domaines + statut ensemble) ; l'apport de chaque élément (titre, année, section) n'est pas mesuré.
- Index intermédiaires `index/tas_v4_c` et `index/tas_v4_h` : suppression refusée par le système de permissions, à supprimer par l'orchestrateur (`tas_v4_t` = ablation tableaux seuls, `tas_v4_r` = variante avec unités : à garder ou supprimer).
- Les builds ont tourné en parallèle des évaluations MLX d'un autre agent (file d'attente GPU bloquée ~30 min) : latences non comparables.

## Fichiers

Code : `src/rag_sfar/ingestion/{table_parser,chunker,loader,text_cleaning,population}.py`, `src/rag_sfar/schemas.py`, `src/rag_sfar/cli.py` (`--chunker-options`). Tests : `tests/test_ingestion_b2.py` (15 tests synthétiques ; suite complète 113 verts ; anti-fuite muet). Scripts : `scripts/ingestion_structural_checks.py`, `scripts/compare_index_runs.py`. Annexes : `reports/agents/B2_annexes/`.
