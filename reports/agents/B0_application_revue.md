# B0 — Application de la revue A2 aux modifications « Neon »

Date : 2026-11-27. Agent B0 (Opus). Spécification : `reports/agents/A2_revue_neon_v31.md`.
Commits : `5aa9d1a` (retrieval), `1f8d95e` (ingestion, CLI), `0712f54` (`.gitignore`). Tests : `pytest -q` 86 passés ; `tests/test_no_benchmark_leakage.py` (version étendue de A1) n'affiche plus rien.

## 1. Bilan des 22 changements

Numérotation = tableau §1 de A2. Lignes = état après les commits.

| # | Changement | Verdict A2 | Appliqué | Fichier:ligne |
|---|---|---|---|---|
| 1 | Version la plus haute « Vx.y du … » sur 30 000 caractères | Garder | Gardé | `ingestion/loader.py:512` |
| 2 | Overlay `data/corpus_updates/` | Modifier | Résolution explicite (`resolve_corpus_updates_dir`), options CLI `--corpus-updates-dir` / `--no-corpus-updates`, chemin et SHA-256 (manifeste + chaque fichier) écrits dans `manifest.json` de l'index (`corpus_updates`) | `loader.py:712,722` ; `cli.py:112,219` |
| 3 | Remplacement de version mineure la même année | Garder | Gardé | `loader.py:910,938` |
| 4 | En-têtes hérités par un tableau à bandeau | Modifier | Héritage seulement si le tableau précédent est **contigu** (aucun texte entre les deux), dans la **même section**, avec le **même nombre de colonnes**, et si le bandeau n'est pas suivi d'une ligne `<th>` | `ingestion/table_parser.py:255,388` ; `chunker.py:445-470` |
| 5 | « HISTORIQUE DES VERSIONS » niveau 1, 3 500 car. | Garder | Gardé | `chunker.py:253,585` |
| 6 | « INTRODUCTION » niveau 1 | Modifier ou retirer selon ablation | **Gardé** après ablation (index `tas_v3_nointro`, §3.3) : le retirer dégrade légèrement multirfe (MRR −0,013 / −0,021, 2 à 4 questions moins bien classées, aucune gagnée de façon nette), neutre sur ABP | `chunker.py:255` |
| 7 | Classement des notes de bas de tableau | Modifier | L'encadré de recommandation (R-id + GRADE) est testé **avant** la note ; le gras Markdown (`**R1.1`, `**Céfazoline**`) n'est plus un appel de note ; limite ramenée à 900 ; le bandeau propre à l'ABP est remplacé par une règle générique (« … de ce tableau » en tête d'un court paragraphe) ; « au-delà, se référer au tableau adulte » (texte ABP) retiré | `chunker.py:39,41,604` |
| 8 | `v[123]\.\d+` | Garder | Gardé | `retrieval/router.py:22` |
| 9 | `adolescente` | Garder (consigne : seulement si accord systématique) | Accord en genre et en nombre traité pour **tous** les termes de population (âgé·e·s, enfant·s, nourrisson·s, garçon·s, fille·s, fillette·s, adolescent·e·s, patient·e·s, nouveau-né·e·s, sujet·s âgé·e·s, personne·s âgée·s) + test sur 28 formes | `router.py:30,34` |
| 10 | Garde de négation (modificateurs) | Modifier | Portée réécrite : la négation porte sur le terme qui la suit **immédiatement** ; entre l'indice et le terme, seuls des mots-outils (articles, prépositions élidées ou non) et « antécédent(s) de / notion de / signe(s) de / histoire de ». « non diabétique allergique », « sans antécédent particulier allergique », « non fumeuse allergique » déclenchent `allergy` ; « sans allergie », « non allergique », « pas d'allergie », « sans diabète ni allergie », « non-allergique » non. Les expansions d'acronymes niés ne comptent pas (« sans IRC »). `detect_affirmed_allergy` (générateur) utilise la même fonction | `router.py:83,89,102,159,198` |
| 11 | Retrait des clauses niées de la requête | **Retirer** | Retiré (fonction, regex, appel dans `pipeline.py`) + test qui vérifie l'absence de l'appel | — |
| 12 | Facette CRAG pédiatrique | Garder | Gardé (déjà systématique en genre) | `crag.py:56` |
| 13 | Garde de négation CRAG | Modifier | Même correction que 10 (fonction partagée) | `crag.py:85` |
| 14 | FOP / CPRE | Modifier | Développement du sigle seul (« foramen ovale perméable », « cholangiopancréatographie rétrograde endoscopique ») : acronymes médicaux standard non ambigus en français ; termes de titres de section ABP retirés | `medical_lexicon.py:65-66` |
| 15 | `colectomie`, `mandibule` | **Retirer** | Retirés | — |
| 16 | Sous-population nouveau-né / enfant | Modifier | Seulement si `population == pediatrie` ; âge en jours/semaines **avec contexte d'âge** (« âgé de 10 jours », « J3 de vie », « 5 jours de vie ») et < 28 jours ; « 3 jours avant », « antibiothérapie de 5 jours », « diabétique depuis 5 ans » ne déclenchent plus rien | `pipeline.py:51-85` |
| 17 | Pénalité des encadrés allergie | **Retirer** | Retirée (×0,65 au rerank et −0,25 au boost) | — |
| 18 | Pénalité de population 0,72 → 0,68 | **Retirer** | Revenu à 0,72 | `pipeline.py:390,392` |
| 19 | Ajout de notes en contexte | Modifier | Regex d'appel de note isolé `(?<![\*\w.])\*{1,3}(?![\*\w])` (plus de gras/italique) ; hors cas `wants_callout` (règle d'origine, ≤ 550 car.), on n'ajoute que les notes **du tableau du résultat** (`_own_table_notes`) | `pipeline.py:62,716,758` |
| 20 | Règle 5 « clarification » du prompt | Modifier (ablation jugée) | **Non traité ici** (écart, §2) | `generation/prompts.py:20` |
| 21 | Tests de Neon | Modifier | Réécrits avec des entrées synthétiques ; ajout de 14 tournures de négation, 28 formes de population, sous-population, regex de note, classement encadré/note, héritage d'en-têtes (4 cas) | `tests/test_rag_sfar.py:624-772` |
| 22 | `.gitignore` `ag_edits.md` | Garder | Gardé | `.gitignore` |

Fuites : la docstring/les commentaires de `router.py` (Q149, Q158) ont disparu avec la fonction 11 ; les énoncés de Q58, Q149, Q152 dans les tests sont remplacés par des exemples synthétiques. Le test anti-fuite étendu de A1 (abpe171) passe.

## 2. Chiffres avant / après (dev, retrieval seul, C9 et C9 + fenêtres)

Méthode : A1 modifiait `evaluation/harness.py` pendant la tâche, ce qui a faussé une première série (rapports `*_b0_before` / `*_b0_codeonly` : les rangs de preuves de abpe171 changeaient sans que la liste récupérée change). Toutes les mesures ci-dessous utilisent donc **le même code d'évaluation figé** (copie de `src/rag_sfar/evaluation/` à 01:13) : avant = code de Neon + `index/table_aware_sota` (tag `b0fz_before`) ; après = code B0 + `index/tas_v3` (`b0fz_after`). Différences appariées : `harness.paired_bootstrap_diff` (2 000 tirages). Détail par question et courbes : `reports/agents/B0_annexes/cmp_*.md`.

| Suite (n) | Config | Passage dans le contexte | Passage hit@8 | MRR passage | Rappel preuves (ctx) | Suffisance (ctx) |
|---|---|---|---|---|---|---|
| multirfe_synth (94) | C9 | 85,5 → 85,5 (+0,0) | 85,5 → 85,5 | 0,678 → 0,688 (+0,010 [0 ; +0,030]) | — | — |
| | C9 + fenêtres | 100 → 100 | 88,2 → 88,2 | 0,658 → 0,670 (+0,012 [0 ; +0,035]) | — | — |
| abp171 (102) | C9 | 94,1 → 94,1 | 94,1 → 94,1 | 0,740 → 0,740 | — | — |
| | C9 + fenêtres | 98,0 → 99,0 (+1,0 [0 ; +2,9]) | 90,2 → 91,2 | 0,712 → 0,714 | — | — |
| abpe171 (102) | C9 | 96,1 → 96,1 | 96,1 → 96,1 | 0,806 → 0,804 (−0,002 [−0,020 ; +0,013]) | 90,2 → 89,7 (−0,5 [−3,1 ; +1,6]) | 84,4 → 83,3 (−1,0 [−3,1 ; 0]) |
| | C9 + fenêtres | 98,0 → 98,0 | 93,1 → 94,1 | 0,775 → 0,770 | 92,8 → 92,8 | 87,5 → 88,5 (+1,0 [−2,1 ; +4,2]) |

Rang médian du passage : 1 partout, avant comme après. Courbes passage hit@k (C9 + fenêtres, abpe171) : @1 70,6 → 69,6 ; @5 89,2 → 90,2 ; @8 93,1 → 94,1 ; @16 98,0 → 98,0.

Décomposition : les mêmes runs avec le code B0 sur l'**ancien** index (`b0fz_codeonly`) donnent exactement les mêmes chiffres que `b0fz_after` : la reconstruction de l'index (types de fragments, en-têtes) est neutre pour C9 en retrieval seul (C9 n'utilise pas le bonus par type de fragment), tout l'écart vient du code de requête.

Aucune différence n'est significative. Les seules questions qui reculent sont **Q149** (preuve rang 6 → hors top 8 en C9 ; 2 → 8 avec fenêtres) et **Q158** (1 → 3 ; 1 → 2), deux cas de `retest_9_cases`. Analyse : la cause est le retrait de la fonction 11. Sans elle, la clause niée « sans allergie aux bêtalactamines » reste dans la requête et les encadrés « En cas d'allergie aux bêtalactamines » (ABP, Champs 2 et 3) remontent en tête par correspondance lexicale. La fonction 11 « aidait » ces deux questions en effaçant la clause, mais elle efface aussi l'acte dans d'autres formulations (A2 §1 ligne 11) : c'est une heuristique réglée sur le benchmark, pas une perte. Piste générique à tester par B1, sur un jeu hors benchmark : quand une allergie est **explicitement niée** (la nouvelle `is_negated_at` le sait), ne pas laisser les encadrés allergie occuper le top k (par exemple via le plafond `max_allergy_callouts`), plutôt que réécrire la requête. Je ne l'ai pas introduite : elle ne serait motivée que par Q149.

## 3. Nouvel index `index/tas_v3`

Commande : `HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-index --strategy table_aware_sota --output-dir index/tas_v3` (e5-small, 357 s). Aucun index existant touché.

- **265 documents, 33 405 fragments** (ancien `table_aware_sota` : 265 / 33 300).
- **V3.1 en vigueur** (`is_latest_edition=1`, `version_label="V3.1 (10/07/2026)"`) ; **V3.0 remplacée** (`is_latest_edition=0`, `superseded_by=…V3_1…_642ad1`).
- Manifeste : `corpus_updates` = `data/corpus_updates`, SHA-256 du manifeste `fff18405…`, du Markdown V3.1 `a05f2f9f…`, PDF source `642ad1f1…`.

### 3.1 Types de fragments (ancien `table_aware_sota` → `tas_v3` ; avant Neon : `tas_qwen3emb06`)

| Type | Avant Neon | Neon | B0 |
|---|---:|---:|---:|
| `recommendation_box` | 553 | 443 | **851** |
| `callout_footnote` | 1 883 | 2 828 | **491** |
| dont encadrés de recommandation classés en note | 288 (A2) | **408** | **0** |
| `prose` | 19 255 | 18 643 | 20 566 |
| `table_row_card` | 5 722 | 6 003 | 6 109 |
| `callout_allergy` | 29 | 58 | 58 |

La chute des notes vient surtout du gras Markdown : 1 939 paragraphes que l'ancienne règle `^[\*#†‡]` prenait pour des notes commencent par `**` (argumentaires, questions PICO, recommandations non numérotées R…, listes de liens d'intérêts). Échantillon de 12 vérifié à la main : aucun n'est une note de tableau.

### 3.2 Héritage d'en-têtes (2 189 tableaux, 171 commencent par une ligne-bandeau)

| | Neon | B0 |
|---|---:|---:|
| Tableaux qui héritent d'en-têtes (toutes causes) | 497 | 482 |
| dont via une ligne-bandeau | 43 | **22** |

Note : A2 comptait « 78 tableaux de cette forme » (forme exposée au risque, pas héritages effectifs). Les 22 héritages restants sont tous contigus, même section, même largeur, sans ligne `<th>` propre (cas « Chirurgie des gonades » p. 121 conservé).

### 3.3 Ablation INTRODUCTION (`index/tas_v3_nointro`, construit avec la règle 6 neutralisée, sans modifier le code)
multirfe C9 : MRR 0,688 → 0,674 (−0,013 [−0,033 ; 0]) ; C9 + fenêtres : 0,670 → 0,648 (−0,021 [−0,053 ; 0]) ; passage dans le contexte inchangé. abp171 inchangé ; abpe171 : une question 2 → 3. Décision : garder la règle (aucun indice de dégradation, léger avantage hors ABP).

## 4. Erreurs de l'overlay V3.1 (p. 81, 87, 113)

Consigne d'origine : ne pas corriger `data/`. En cours de tâche, l'orchestrateur a transmis l'accord de l'utilisateur pour corriger. **La modification de `data/corpus_updates/` a été refusée par le système de permissions** ; je ne l'ai pas contournée. Ce qui est prêt :

- `reports/agents/B0_annexes/apply_errata.py` : 3 remplacements exacts, recopiés du PDF officiel (pypdf), chacun vérifié unique. p. 81 : nouvelle ligne « Cholécystectomie élective par laparoscopie ○ Patients à faible risque : aucun des critères ci-dessus → PAS D'ANTIBIOPROPHYLAXIE, ◉◉◎ (GRADE 2) », la ligne céfazoline/céfuroxime ne garde que le haut risque ; p. 87 : « Si céfoxitine » ; p. 113 (pédiatrie) : la ligne « PAS D'ANTIBIOPROPHYLAXIE » reçoit l'acte et la puce « faible risque » (première cellule vide auparavant). Diff : `B0_annexes/overlay_errata.diff`.
- `reports/agents/B0_annexes/ERRATA.md` : brouillon de `data/corpus_updates/ERRATA.md` (date, page, avant, après, texte du PDF, accord). `updates_manifest.json` ne contient que le SHA du PDF source, inchangé : pas de mise à jour nécessaire.
- Pour appliquer : `.venv/bin/python reports/agents/B0_annexes/apply_errata.py data/corpus_updates/RFE-antibioprophylaxie-2023_V3.1_pour-mise-sur-site-juillet-2026_sans-code-CCAM.md`, copier `ERRATA.md`, puis reconstruire l'index (nouveau dossier). `data/corpus_updates/` est ignoré par git.

Mesure de l'effet (index `index/tas_v3_errata`, construit depuis une copie corrigée de l'overlay dans le dossier de travail, sans toucher `data/`) :
- `check_errata.py` : dans `tas_v3`, les 2 fiches-lignes « faible risque » (adulte p. 81, pédiatrie p. 113) portent **céfazoline** et pas « PAS D'ABP », et « Si céfotaxime » est présent ; dans `tas_v3_errata`, les 2 fiches « faible risque » portent **PAS D'ANTIBIOPROPHYLAXIE** sans céfazoline (GRADE 2 en adulte), « Si céfotaxime » a disparu, « Si céfoxitine : gentamicine » est présent.
- Retrieval : aucun changement sur multirfe et abpe171 ; abp171 : Q159 passage rang 1 → 2 (la citation gold de Q159 avait été annotée sur la cellule fusionnée, voir `eval/annotations/abp171_dev_gold_passages.md`). L'effet réel est sur le **contenu** remonté (risque clinique : céfazoline associée aux patients à faible risque), que les métriques de passage ne voient pas. Petit défaut résiduel, préexistant : le parseur répète le texte des listes imbriquées dans la colonne Acte (« ○ Patients à faible risque … ; ○ Patients à faible risque … »).
- `index/tas_v3_errata` dépend d'un overlay hors dépôt (manifeste : chemin du dossier de travail) : à reconstruire depuis `data/` une fois l'erratum appliqué.

## 5. Écarts avec A2 et justification

1. **#20 (règle 5 du prompt)** : non traité. L'ablation demandée est une évaluation **générée et jugée** (exactitude, taux de clarification, abstention), hors du périmètre retrieval de cette tâche et du ressort de B3. Le prompt reste inchangé.
2. **#2** : l'overlay reste appliqué **par défaut** quand `data/corpus_updates/updates_manifest.json` existe (la commande de reconstruction imposée repose dessus) ; il est désormais affiché au build, désactivable, et tracé avec SHA-256 dans le manifeste de l'index.
3. **#7** : au lieu de garder la phrase propre à l'ABP (« Les posologies de ce tableau concernent… ») comme le laissait A2, je l'ai remplacée par une règle structurelle (« de/dans/du ce tableau » dans les 160 premiers caractères d'un paragraphe de moins de 900 caractères), et j'ai retiré « au-delà, se référer au tableau adulte ».
4. **#19** : A2 proposait la regex `(?<![\*\w])…` ; j'exclus aussi un `*` précédé d'un point (fin d'italique « *i.e.* »).
5. **#16** : la règle « nouveau-né » accepte aussi « prématuré(e)(s) » (terme déjà présent chez Neon) mais seulement si la requête est routée en pédiatrie.
6. **#10** : « portage » n'est pas dans les mots de liaison de la négation (lien un à un avec Q158) ; « sans portage de BLSE » active donc la facette CRAG BLSE (faux positif sans danger, CRAG n'est pas dans C9).
7. Mesures : la première série `b0_before`/`b0_codeonly` (rapports gardés dans `reports/eval/`) est **invalide** pour abpe171 (code d'évaluation modifié par A1 entre les runs) ; seuls les rapports `b0fz_*` font foi.

## 6. Fichiers

- Rapports d'évaluation : `reports/eval/20261127-01*_{multirfe_synth,abp171,abpe171}_dev_b0fz_{before,codeonly,after,errata,nointro}.{json,md}`.
- Annexes : `reports/agents/B0_annexes/` (scripts `compare.py`, `chunk_stats.py`, `check_errata.py`, `apply_errata.py`, `build_variant.py` ; comparaisons `cmp_*.md` ; statistiques `stats_*.json` ; `ERRATA.md`, `overlay_errata.diff`).
- Index créés : `index/tas_v3` (référence), `index/tas_v3_errata` et `index/tas_v3_nointro` (ablations, supprimables).
