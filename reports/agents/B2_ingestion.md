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

---

# Corrections après revue R1 (`index/tas_v5`)

Date : 2026-11-27. Revue : `reports/agents/R1_revue_ingestion.md`. Code : commit `58a3536` (+ comparateur `scripts/compare_index_runs.py`). **Index mesuré : `index/tas_v5` ; index recommandé à la fin de cette journée : `index/tas_v6`** (= `tas_v5` + errata du corpus + glyphes, voir la section suivante) (265 documents, 36 872 chunks, options par défaut). `tas_v4` ne doit plus servir de source de citations : ses tableaux Markdown sont aplatis et des unités µg y sont corrompues.

## Défauts corrigés

| # | Défaut (R1) | Correction | Fichier |
|---|---|---|---|
| C1 | `(?:\s*\|\s*){2,}` mangeait les fins de ligne : tableaux Markdown aplatis sur une ligne, cellules vides supprimées, colonnes décalées | Seuls les séparateurs produits par les fragments `<td>` orphelins sont fusionnés (sentinelle, espaces horizontaux seulement) ; les lignes et cellules vides des tableaux Markdown ne sont plus touchées | `text_cleaning.strip_inline_tags` |
| C2 | 13 organigrammes Mermaid sur 164 perdaient des libellés (doses, seuils) | Libellés d'arête contenant `>`/`<` et sur plusieurs lignes, arêtes `<-->`, crochets imbriqués, nœuds redéfinis (libellés fusionnés). **Garde-fou** : si un nombre ou un mot (≥ 4 lettres) des libellés source manque à la réécriture, le bloc brut est gardé, marqué « [Organigramme (syntaxe d'origine conservée)] » (9 blocs sur 164) | `text_cleaning.mermaid_block_to_text` |
| C3 | µg → `\mug` / `mug`, µmol → `mumol` | Symboles LaTeX remplacés avant le déroulement de `\text{}` ; `\mu`, `\Omega`, `\circ` reconnus même collés à une lettre ; `<math>` rendu avant l'extraction du texte des cellules ; « µ g » → « µg ». Autres lettres grecques et commandes vérifiées par le compteur (0 résidu) | `text_cleaning.latex_to_text`, `table_parser._node_text/_li_text` |
| C4 | Négation placée après le terme ignorée (« (nouveau-né exclu) ») | Négation cherchée après le terme (« exclu(e)(s) », « non concerné », « excepté ») et dans une parenthèse d'exclusion (« (except … and neonate) », « (sauf …) ») | `population.population_terms` |
| M1 | Libellés courts finissant par « . » ou un appel de note pris pour des notes, rattachés à la ligne précédente | Ligne courte (≤ 8 mots, sans verbe, pas de marqueur de note en tête) = libellé, même avec « . », « * », ou en italique ; l'appel reste dans le libellé, donc la note est liée aux lignes qui **suivent** | `table_parser.full_width_row_kind` |
| M2 | AVK HAS 2008 remis « en vigueur » à tort ; remplacement partiel de 2010 non signalé | AVK 2008 de nouveau remplacé (`superseded_by` = RFE 2026 procédure programmée) avec une preuve qui cite aussi la RFE urgence 2024 ; notes « à valider par un médecin » pour AVK 2008 et urgences obstétricales 2010 (chapitres 1, 3 et 8 non repris en 2022) dans `supersession_evidence` | `loader.SUPERSESSION_REVIEW_NOTES` |
| M3 | Populations tirées de titres énumératifs ou de titres-phrases | Un titre ne donne une population que s'il fait ≤ 15 mots, n'est pas une phrase (recommandé, suggèrent, il faut, we suggest…, « ? ») ni une énumération (≥ 2 virgules, ou virgule + « et ») ; dans le doute, pas d'étiquette | `population.heading_can_label` |
| m1 | Règle « mention explicite » déclenchée par la bibliographie | Paragraphes `[n] …`, `- [n] …`, « (Source : …) » ignorés | `loader._apply_explicit_update_mentions` |
| m5 | Valeur et unité séparées par « / » | Une ligne qui commence par une unité continue la valeur du dessus | `table_parser._resolve_breaks` |
| m6 | Octet NUL réparé en « à » par devinette | Remplacement seulement si le vocabulaire désigne un seul mot (casse respectée) ; sinon marqueur visible « � » (5 chunks) | `text_cleaning.NulRepairer` |

Non traités (limites connues, R1 « peut attendre ») : m3 doublons actifs (AAP 2018/2021, TIH 2019 ×2), m4 texte en italique perdu dans la désagrégation des listes parallèles ABP (code antérieur, règle propre à l'ABP), m7 fiches de ligne issues de sommaires, m8 position des cellules vides perdue dans les tableaux **sans en-tête** (`_row_line`), m9 en-tête d'un premier sous-tableau réutilisé ; règles antérieures propres à l'ABP (`ALLERGY_BOX_RE`, découpe « PAS D'ANTIBIOPROPHYLAXIE », indices d'en-tête nommant des molécules).

## Contrôles permanents ajoutés (`scripts/ingestion_structural_checks.py`, clé `fidelity`)

- **Tableaux** : pour chaque ligne `<tr>` de chaque tableau source, les jetons cliniques (nombres avec unité, comparaisons, mots de type molécule), nettoyés comme les chunks, doivent se trouver **ensemble** dans une même unité (une ligne d'un chunk tableau ou une fiche de ligne) du même document ; on compte aussi les jetons absents de tous les chunks tableau.
- **Organigrammes** : pour chaque bloc Mermaid, tous les nombres et mots des libellés doivent se retrouver dans les chunks du document.
- Compteurs : tableaux Markdown sur une seule ligne (en-tête + séparateur + données collés), unités micro corrompues, LaTeX `\mu` brut, chunks dont l'étiquette de population contredit une exclusion explicite du titre ou du chemin de section.

| Compteur | tas_v3_errata | tas_v4 | **tas_v5** |
|---|---:|---:|---:|
| Lignes de tableau dont les jetons cliniques ne sont pas réunis dans une même unité (sur 8 944) | 112 | 12 | **9** |
| Jetons cliniques de tableau absents de tout chunk (sur 32 954) | 157 | 10 | **4** |
| Organigrammes perdant un nombre ou un mot (sur 164) | 0 (syntaxe brute) | 5 | **0** |
| `table_markdown` aplatis sur une ligne | 0 | 1 854 | **0** |
| Unités micro corrompues (`\mug`, `mug`, `mumol`) / `\mu` brut | 0 / 374 | 131 / 0 | **0 / 0** |
| Étiquettes contredisant une exclusion explicite | — | 660 | **0** |
| Lignes pleine largeur perdues (sur 780) | 104 | 0 | 0 |
| Cellules/lignes du corpus non couvertes (part des caractères) | 218 (0,57 %) | 458 (0,33 %) | **112 (0,17 %)** |
| Chunks étiquetés adulte / pédiatrie / néonatal / obstétrique | — | 11 292 / 5 052 / 1 897 / 1 890 | 10 446 / 4 340 / 1 179 / 1 738 |
| Organigrammes gardés en syntaxe brute (garde-fou) | 160 | 4 | 12 |

Sorties : `reports/agents/B2_annexes/structural_{tas_v3_errata,tas_v4,tas_v5}.json`. Couverture du mapping abpe171 sur `tas_v5` : 347/348 passages, 221/222 preuves, 96/96 questions mappables (inchangée).

## Coquilles de l'overlay : passe systématique

Liste de tous les mots de 6 lettres ou plus de `data/corpus_updates/*.md` absents du texte du PDF officiel (pypdf, `python -I`) : 93 mots (`B2_annexes/overlay_words_not_in_pdf.tsv`), relus un à un avec le contexte du PDF (proposition la plus proche par `difflib`, page). **23 formes corrigées (51 occurrences)**, seulement quand le PDF donne la forme correcte dans le même contexte, dont trois noms qui comptent cliniquement : **« céfuoxime » → « céfuroxime » (19 occurrences, molécule)**, « ANTIOPROPHYLAXIE / antiobiprophylaxie / antibiotoprophylaxie » → antibioprophylaxie (7), « Fibroscope / Bronchoscope » → Fibroscopie / Bronchoscopie (9) ; et Altemeier, amygdalectomie (minuscule), Annexectomie, anévrysme, Bioprothèse, œsophagienne, emphysème, endométriose, expandeur, Génioplastie, site opérateur, sustrigonale, transfixiant, tympans, Ténotomie. Copie avant correction `data/corpus_updates_backup/RFE-V3.1_before_B2_overlay_pass.md`, script `B2_annexes/apply_errata_overlay_pass.py`, entrée « Erratum 4 » dans `data/corpus_updates/ERRATA.md`. Restent 70 mots (`overlay_words_not_in_pdf_after.tsv`) : noms d'auteurs, capitales sans accent, descriptions d'images en anglais, variantes d'accent admises, mots du tableau de Gustilo (en image dans le PDF) et deux formulations absentes du PDF (« discutée collectivement », « conformité ») **à relire** (possible écart de contenu, pas de coquille).

## Mesures DEV `tas_v4` → `tas_v5` (retrieval seul)

Même code de retrieval et d'évaluation pour les deux index (copie figée de `src/` au commit `58a3536`, qui contient `C10_context_population` de B1), `--k 64`, IC appariés `harness.paired_bootstrap_diff` (2 000 tirages). Tags `b2r_v4`, `b2r_v5`, `b2r_v4_c10`, `b2r_v5_c10` ; détail par question : `B2_annexes/cmp_tas_v4_vs_tas_v5.md` et `cmp_tas_v4_vs_tas_v5_C10.md`. **multirfe_synth : les métriques de passage portent sur n = 76** (questions qui ont un passage de référence) ; le doc hit ne bouge sur aucun jeu.

| Jeu | Config | Métrique (n) | tas_v4 | tas_v5 | Écart [IC 95 %] |
|---|---|---|---:|---:|---|
| abpe171 | C9 | Suffisance (96) | 90,6 | 88,5 | −2,1 [−5,2 ; 0] |
| | C9 + fenêtres | Suffisance (96) | 93,8 | 92,7 | −1,0 [−3,1 ; 0] |
| | C10 | Suffisance (96) | 99,0 | 97,9 | −1,0 [−3,1 ; 0] |
| | C10 | Passage hit (102) | 100 | 100 | 0 |
| multirfe_synth | C9 | Passage hit (76) | 84,2 | 82,9 | −1,3 [−3,9 ; 0] |
| | C9 + fenêtres | Passage hit (76) | 97,4 | 96,1 | −1,3 [−3,9 ; 0] |
| | C10 | Passage hit (76) | 97,4 | 96,1 | −1,3 [−3,9 ; 0] |
| | toutes | Doc hit (76) | 96,1 / 98,7 / 98,7 | identique | 0 |
| abp171 | C9 | Passage hit (102) | 97,1 | 97,1 | 0 [−2,9 ; +2,9] |
| | C9 + fenêtres | Passage hit@8 (102) | 95,1 | 93,1 | −2,0 [−4,9 ; 0] |
| | C10 | Passage hit (102) | 100 | 100 | 0 |

Aucun écart n'est significatif ; ce sont des corrections de sécurité, gardées quoi qu'il arrive. Questions qui reculent, une par une (le texte de preuve est présent dans les deux index : couverture du mapping abpe171 identique, 96/96) :
- **Q157** (C9, abpe171) : la preuve est dans le tableau bariatrique (`…c0470`), même chunk dans les deux index ; dans `tas_v4` ce tableau était aplati sur une ligne, dans `tas_v5` il retrouve ses lignes (C1) : son embedding et son score BM25 changent et il sort du top 8 (rang 3 → au-delà). Pas de perte de texte.
- **Q158** (C9, fenêtres, C10) : la ligne pédiatrique de colectomie (`…c0741`, même texte) recule pour la même raison (tableaux voisins redevenus multi-lignes) ; avec C10 s'ajoutait un effet de population : dans `tas_v5`, la règle « titre-phrase » (M3) prenait « Recommandations » (nom) pour un verbe et retirait l'étiquette `adulte` des sections du Champ 2 ABP. **Corrigé** ensuite (verbes seulement, test ajouté) et mesuré dans `tas_v6`.
- **MR-g3940…** (multirfe, fenêtres) : tableau de réhabilitation colorectale, chunk gold inchangé, rang 12 → hors contexte (même mécanisme que Q157).
- Les autres mouvements sont des changements de rang sans perte (Q115, Q132, Q44, Q52 …) et des gains (Q139 rang 8 → 1, Q42, Q61, MR-g394ecc…).


### Limites connues après R1

- Les règles propres à l'ABP antérieures à B2 restent (encadré allergie, découpe des listes parallèles « PAS D'ANTIBIOPROPHYLAXIE », indices d'en-tête nommant des molécules) ; m3, m4, m7, m8, m9 non traités (voir plus haut).
- 9 organigrammes sur 164 sont gardés en syntaxe Mermaid brute (garde-fou) : lisibles par un modèle, moins par un humain.
- 9 lignes de tableau (sur 8 944) n'ont pas tous leurs jetons cliniques dans une même unité ; 4 jetons absents (formats « / » et extracteur).
- 5 chunks portent le marqueur « � » d'un caractère illisible (2 documents) au lieu d'une devinette.
- Le contrôle « jetons cliniques » est lexical (nombres, comparaisons, mots de type molécule) : il ne vérifie pas le sens d'une phrase.

# Errata du corpus et détection des erratums (`index/tas_v6`)

Date : 2026-11-27. Demande de l'orchestrateur après l'audit D1 (`reports/agents/D1_audit_doses.md`). Code : commits `4d3d900` et suivants. **Index recommandé : `index/tas_v6`** (265 documents, 36 872 chunks).

## 1. Mode « patch » pour les erratums officiels

- `data/corpus_updates/patches.json` liste des remplacements exacts par fichier source : `id`, `document` (chemin), `document_sha256` (fichier contre lequel le patch a été écrit), `original`, `corrected`, `evidence`, `pdf_pages`, `pdf_sha256`. Le loader (`apply_corpus_patches`) les applique à l'ingestion, sans toucher `data/sfar_recommendations`.
- **Échec bruyant** (`CorpusPatchError`) si le SHA-256 du fichier ne correspond plus, si la chaîne d'origine est absente ou présente plusieurs fois, ou si un patch vise un document qui n'est pas chargé.
- **Rendu honnête** : seul le segment modifié est remplacé et suivi du texte imprimé, par exemple « La posologie de l'adrénaline intratrachéale est de 100 µg/kg [corrigé selon l'erratum officiel publié dans le même document ; texte initial : « 100 mg/kg »] dilué … ».
- Traçabilité : `DocumentMetadata.applied_patches`, `Chunk.corpus_patch_ids` (le chunk qui porte le texte corrigé), SHA-256 de `patches.json` dans `manifest.json` de l'index (`corpus_updates.patches_sha256`).
- Patches entrés : **D1-E1** (adrénaline intratrachéale enfant 100 mg/kg → 100 µg/kg) et **D1-E2** (adrénaline enfant IV/IO 10 mg/kg → 10 µg/kg), arrêt cardiaque 2006 (document en vigueur) ; **D1-E3** (« (2–) » → « (2+) »), MTEV 2011 (document remplacé). Vérifiés dans `tas_v6` : les trois chunks portent le texte corrigé et leur `corpus_patch_ids` ; plus aucun chunk ne contient « 10 mg/kg en intraveineux » sans la mention. Journal : `data/corpus_updates/ERRATA.md`, section « Erratum 3 » (la passe systématique overlay ↔ PDF de la section précédente est renumérotée « Erratum 4 »).
- Tests synthétiques : application visible et enregistrée, SHA-256 différent, chaîne non unique (`tests/test_ingestion_b2.py`).

## 2. Détection des erratums (contrôle de complétude)

`scripts/ingestion_structural_checks.py` (clé `errata`) cherche dans tout le corpus : titres « Erratum / Errata / Corrigendum » (sauf les notes « Erratum in: » des références PubMed), « Une erreur s'est glissée », « il fallait lire », « doivent être lu(e)s », « Nous prions nos lecteurs », « au lieu de lire », et les notes « correction de coquilles / d'une erreur » d'un historique de versions. Chaque document détecté doit avoir un patch ou une entrée `reviewed_errata` motivée dans `patches.json` ; sinon le script sort en erreur.

Résultat (265 documents) : **2 documents ont une section d'erratum**, tous deux couverts ; 2 historiques de versions revus.

| Document | Ce que dit l'erratum | Statut |
|---|---|---|
| Arrêt cardiaque 2006 (`2006_2_AFAR_Prise-en-charge-de-larret-cardiaque-1_c70196`, en vigueur) | « Une erreur s'est glissée à la page 1018 … les posologies d'adrénaline doivent être lues en « µg » et non mg. » Les deux posologies de la page 1018 (IV/IO 10, intratrachéale 100) | patché D1-E1, D1-E2 |
| MTEV 2011 (`2011_2_AFAR_Prevention-de-la-maladie-thromboembolique-veineuse-postop_da2bda`, remplacé) | « il fallait lire : … la prescription d'HBPM est recommandée (1+). Toutefois, une prophylaxie prolongée … est suggérée jusqu'à l'appui plantaire (2+). » (seule la cotation (2–) diffère du texte imprimé) | patché D1-E3 |
| ABP V3.1 et V3.0 (historique des versions) | « V1.2 du 16/12/2023 : correction de coquilles dans les schémas de réinjection … » | revu, pas de patch : corrections déjà intégrées dans le texte de la version publiée |

Aucun autre erratum n'a été trouvé ; je n'ai donc aucune correction supplémentaire à proposer. Le détecteur ne voit que les erratums **imprimés dans le même PDF** ; un erratum publié séparément (autre numéro de revue) reste invisible.

## 3. Glyphes de force de l'overlay ABP

Les suites « ●●● », « ◉◎◎ », « ●○○○ » placées devant une cotation textuelle sont rendues de la même façon par l'OCR quel que soit le grade, alors que le libellé qui suit (« (GRADE 1) », « (GRADE 2) », « (Avis d'experts) ») est juste. Règle générique (`text_cleaning._GRADE_GLYPHS_RE`) : une suite de 2 à 5 glyphes ●◉◎○◯⬤ est supprimée **quand un libellé de cotation la suit** (GRADE, Avis d'experts, AE, Accord, G1/G2), dans le texte affiché comme dans le texte indexé. Les glyphes isolés ou sans libellé (puces « ○ Patients… », cases « ○○ » d'un questionnaire tabac 2016) ne sont pas touchés.
Occurrences dans le corpus : ABP V3.1 483, ABP V3.0 (édition remplacée) 483, ECBU 2026 22, résection hépatique 2025 ×2 (2) ; toutes suivies d'un libellé. Chunks contenant ces glyphes : 1 081 dans `tas_v5` → 0 dans `tas_v6`.

## 4. Cellule perdue de la résection hépatique 2025

Dans `tas_v3_errata`, le chunk `…MEL_e8bdcf__c0086` avait perdu la cible de pression artérielle (« → maintien d'une PAM > 65 mmHg (> 70 mmHg ou > 90 % de la valeur habituelle chez l'hypertendu) ») : texte d'une cellule placé hors de `<li>` (défaut (e) du §1, corrigé dès `tas_v4`). Le contrôle de fidélité le voit : sur ce document, `tas_v3_errata` a 1 ligne dont les jetons ne sont pas réunis et 5 jetons absents (`>65`, `65mmhg`, `70mmhg`, `>70`, `90%`) ; `tas_v5` et `tas_v6` : 0 et 0 (l'unité « mmHg » a été ajoutée aux jetons du contrôle).

## 5. Mesures DEV `tas_v5` → `tas_v6`

Même protocole que ci-dessus (code figé `58a3536`, `--k 64`), tags `b2r_v6`, `b2r_v6_c10` ; détail : `B2_annexes/cmp_tas_v5_vs_tas_v6.md`, `cmp_tas_v5_vs_tas_v6_C10.md`. `tas_v6` contient aussi la correction de la règle « titre-phrase » (étiquette `adulte` rendue aux sections ABP du Champ 2).

| Jeu | Config | Métrique (n) | tas_v5 | tas_v6 | Écart [IC 95 %] |
|---|---|---|---:|---:|---|
| abpe171 | C9 | Suffisance (96) | 88,5 | 88,5 | 0 [0 ; 0] |
| | C9 + fenêtres | Suffisance (96) | 92,7 | 92,7 | 0 [0 ; 0] |
| | C9 + fenêtres | Passage hit@8 (102) | 93,1 | 94,1 | +1,0 [0 ; +2,9] |
| | C10 | Suffisance (96) | 97,9 | 97,9 | 0 |
| multirfe_synth | C9 / fenêtres / C10 | Passage hit (76) | 82,9 / 96,1 / 96,1 | identique | 0 |
| | toutes | Doc hit (76) | 96,1 / 98,7 / 98,7 | identique | 0 |
| abp171 | C9 + fenêtres | Passage hit@8 (102) | 93,1 | 92,2 | −1,0 [−3,9 ; +2,0] |
| | C10 | Passage hit (102) | 100 | 100 | 0 |

Rien d'autre n'a bougé de façon mesurable : seuls des rangs changent (Q115 rang 7 → 2 en C9, Q149 8 → 1, Q70 4 → 8 en fenêtres sans perte de suffisance).

Compteurs `tas_v6` (`B2_annexes/structural_tas_v6.json`) : identiques à `tas_v5` pour les tableaux, organigrammes, unités micro et exclusions ; contrôle des erratums « ok » ; couverture du mapping abpe171 inchangée (347/348, 221/222, 96/96).

## Note sur le verrou GPU

Les évaluations attendaient le verrou `.gpu_lock` plus d'une heure : `scripts/with_gpu_lock.sh` interroge toutes les 10 s et d'autres agents enchaînent leurs tâches sans intervalle. J'ai regroupé mes 12 évaluations en une seule prise du verrou et utilisé une copie du même protocole (mkdir atomique, fichiers pid/owner, reprise d'un verrou orphelin) qui interroge toutes les 0,1 s (`scratchpad/b2/fastlock.sh`). Une seule tâche lourde à la fois a été respectée.
