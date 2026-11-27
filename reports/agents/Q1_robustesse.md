# Q1 — Robustesse du retrieval figé aux saisies réelles (fautes, accents, sigles)

Agent Q1, 2026-11-27. **Dev seulement** (`abpe171` dev, 102 questions ; `multirfe_synth` dev, 94), retrieval seul, `index/tas_v6`, k = 64. Aucun split test, `genprobe` non ouvert. Le retrieval figé (`C10_context_notes`, tag `retrieval-freeze-20261127`) n'a pas été modifié : toutes les variantes sont construites par `harness.ablation_variants` ou par une réécriture de la question avant l'appel à `retrieve`.

Tableaux bruts complets : `eval_internal/robustness/results/summary.md` (généré par `analyze.py`). Méthode et reproduction : `eval_internal/robustness/README.md`.

**Contrôle de reproduction** : sur les questions propres, la configuration figée redonne à l'identique, question par question, les métriques des rapports du gel (`reports/eval/20261127-075802_abpe171_dev_bm25cmp_v6_c10.json`, `…075834_multirfe_synth_dev_bm25cmp_v6_c10.json`) : 0 écart sur 102 + 94 questions (sufficiency 95,8 %, passage 96,1 %).

## En bref

1. **La configuration figée est fragile aux fautes de frappe sur l'antibioprophylaxie, robuste ailleurs.** Une faute par question coûte −6,2 pts de suffisance sur abpe171 [−11,5 ; −2,1] ; deux ou trois fautes, −11,5 [−18,8 ; −6,2]. Sur multirfe_synth : −1,3 et −2,6 (non significatifs). En regroupant les deux jeux : −4,1 [−7,0 ; −1,2] et −7,6 [−12,2 ; −2,9]. Accents manquants et style télégraphique : aucun coût mesurable.
2. **L'hypothèse « le dense absorbe les fautes » n'est que partiellement vraie.** Le canal dense seul est en effet insensible aux fautes (abpe171 : 76 % propre, 77 % / 78 % avec fautes), mais il est faible ; l'hybride dépend de BM25 pour le vocabulaire des actes, et BM25 seul s'effondre avec 2–3 fautes (94,8 → 69,8 %). L'hybride ne récupère qu'une partie de la perte.
3. **Les sigles coûtent cher quand l'utilisateur et le corpus ne les écrivent pas de la même façon.** Remplacer « antibioprophylaxie » par « ABP » (sigle que **aucun** chunk en vigueur n'écrit) coûte −8,3 pts [−14,6 ; −3,1] ; remplacer une forme longue par son sigle défini dans le corpus coûte 4 questions sur 18 modifiées (−22,2 [−44,4 ; −5,6], n petit). L'inverse (sigle → forme longue) ne coûte rien (0/15).
4. **Ce que chaque fonction rattrape** : le canal n-grammes (`use_subword`) va dans le bon sens partout (aucune case négative sur 16) mais avec des IC qui touchent presque tous 0 (+1 à +4 pts sous fautes) ; il ne coûte rien sur les questions propres (+1,2 [−1,2 ; +3,5]) et +8 ms. Le lexique ne fait **que** ses sigles : +7,3 pts [+2,1 ; +13,5] sur « ABP », rien sur les fautes ; **sa version réduite aux 60 expansions de sigles « pures » donne exactement le même gain, sans le léger coût de la version complète**. Le glossaire extrait du corpus (alternative générique) ne rattrape pas « ABP » (absent du corpus), rattrape 3 des 4 questions perdues par « forme longue → sigle », mais coûte 1 à 2 questions sur les questions propres.

## 1. Jeux perturbés

Générateur déterministe (graine 20261127, hachage de l'id) : `eval_internal/robustness/perturb.py`. Seule la question est modifiée ; choix de QCM, passages de référence, preuves et clés sont inchangés. Fichiers : `eval_internal/robustness/sets/<suite>/<perturbation>.jsonl` (format `EvalItem`, `meta.perturbation` décrit chaque modification). Les fichiers `abpe171` restent hors git.

| Perturbation | Définition | abpe171 modifiées | multirfe modifiées |
|---|---|---:|---:|
| `typo1` | 1 faute sur un mot de contenu (≥ 4 lettres, ni mot-outil, ni sigle, ni nombre) : suppression, inversion, touche voisine AZERTY, accent manquant | 102/102 | 94/94 |
| `typo3` | 2 ou 3 fautes sur des mots distincts | 102/102 | 94/94 |
| `noaccent` | tous les accents retirés | 74/102 | 93/94 |
| `telegraphic` | mots-outils et formules interrogatives supprimés (négations, « sans/avec » gardés) | 102/102 | 94/94 |
| `abbr` | forme longue → sigle (glossaire du corpus, entrées définies dans ≥ 2 documents) | **4/102** | **16/94** |
| `expand` | sigle → forme longue (même glossaire) | **6/102** | **9/94** |
| `abbr_user` | diagnostic **hors glossaire** : les 7 sigles cités dans la demande (ABP, ATB, IOT, ALR, RTUP, PTH, VNI) | 101/102 | 2/94 |

Fautes produites : abpe171 `typo1` 24 suppressions, 32 inversions, 40 touches voisines, 6 accents ; `typo3` 252 fautes au total (détail dans `sets/counts.json`).

**Limite importante** : avec le seul glossaire du corpus, les perturbations de sigles ne touchent que 20 questions (`abbr`) et 15 (`expand`) sur 196. Les écarts sur ces sous-ensembles ont des IC très larges : ils indiquent un sens, pas une taille. C'est pourquoi le diagnostic `abbr_user` a été ajouté : le sigle le plus fréquent du domaine, « ABP », n'est défini ni employé dans aucun chunk en vigueur ; un glossaire extrait du corpus ne peut donc pas le produire. Ce diagnostic utilise une liste donnée par l'utilisateur dans sa demande, pas tirée des questions ; il touche presque toutes les questions abpe171 (« antibioprophylaxie » → « ABP ») et presque aucune question multirfe.

## 2. Glossaire extrait du corpus

Module `src/rag_sfar/retrieval/corpus_glossary.py` (nouveau, importé par rien dans le pipeline), script `eval_internal/robustness/build_glossary.py`, sortie `eval_internal/robustness/glossary_tas_v6.json`.

- Source : 27 426 chunks des éditions en vigueur de `index/tas_v6` (masque par défaut du store : en vigueur, actif, références exclues).
- Motifs : « forme longue (SIGLE) » (4 395 occurrences), « SIGLE (forme longue) » (442), lignes de sections « Abréviations / Glossaire » « SIGLE : forme » (484), tableaux « Abréviation : X | Signification : Y » (362), listes « X, forme ; Y, forme » (73). Chaque paire est validée par un alignement de lettres à la Schwartz & Hearst (lettres du sigle dans l'ordre, la première en début de mot).
- **Taille** : 1 218 sigles, 1 683 couples sigle–forme (variantes graphiques et pluriels regroupés) ; **407 sigles** dont la forme principale est définie dans ≥ 2 documents (seuil utilisé pour les perturbations et l'expansion).
- **Précision** (étiquetage manuel par Q1, deux échantillons aléatoires de 50, `glossary_sample50.csv` et `glossary_sample50_usable.csv`) : **48/50 (96 %)** sur l'ensemble ; **48/50 (96 %)** parmi les 407 utilisés. Erreurs : formes tronquées ou altérées par l'OCR (SIZ, SPI « surgical ptelh index »), sens propre au document (HOLEP « hommes opérés d'une énucléation prostatique au laser »), forme illisible (PVE). Précision estimée par un non-médecin.
- Exemples : VNI = ventilation non invasive (12 documents), HBPM = héparine de bas poids moléculaire (12), ALR = anesthésie locorégionale (7), RTUP = résection transurétrale de prostate (5), PTH = prothèse totale de hanche, NVPO, SDRA, CEC, IMC, AMM. Ambiguïtés réelles conservées en second rang : EP (embolie pulmonaire 5 docs / estomac plein / échange plasmatique), AL (analgésie locale / anesthésiques locaux), AE (avis d'experts / autres sens).
- Absents : ABP, ATBP, C1G/C2G (jamais définis dans le corpus en vigueur), ATB (défini dans un seul document).

## 3. Résultats (retrieval seul, dev)

Configurations : `frozen` = `C10_context_notes` ; `subword` = `use_subword=true` ; `lexicon` = `use_medical_lexicon=true` ; `subword_lexicon` = les deux ; `lexicon_plain` = figée + expansion des 60 sigles « purs » du lexique (voir §4) appliquée à la question avant `retrieve` ; `glossary` = figée + expansion par le glossaire du corpus dans les deux sens, avant `retrieve` ; `glossary_a2l` = idem, sigle → forme longue seulement ; `bm25_only` = `use_dense=false+use_reranker=false` ; `dense_only` = `use_bm25=false`. Les variantes d'expansion avant `retrieve` reproduisent le format du lexique (termes ajoutés entre parenthèses, vus par BM25, le dense et le reranker).

### 3.1 abpe171 — sufficiency (%, IC 95 % bootstrap ; n = 96 questions avec preuves)

| config | propre | typo1 | typo3 | sans accents | télégraphique | abbr | expand | ABP (diag.) |
|---|---|---|---|---|---|---|---|---|
| **figée** | **95,8** [91,7–99,0] | **89,6** [83,3–95,8] | **84,4** [77,1–90,6] | 94,8 | 95,8 | 94,8 | 95,8 | **87,5** [80,2–93,8] |
| subword | 96,9 | 91,7 | 87,5 | 96,9 | 95,8 | 95,8 | 95,8 | 89,6 |
| lexique | 95,8 | 89,6 | 84,4 | 94,8 | 94,8 | 95,8 | 95,8 | 94,8 |
| subword + lexique | 95,8 | 90,6 | 88,5 | 95,8 | 95,8 | 95,8 | 95,8 | **97,9** |
| lexique « sigles purs » | 95,8 | 89,6 | 84,4 | 94,8 | 95,8 | 95,8 | 95,8 | 94,8 |
| glossaire (2 sens) | 94,8 | 88,5 | 83,3 | 95,8 | 95,8 | 94,8 | 95,8 | 86,5 |
| glossaire (sigle → forme) | 94,8 | 88,5 | 83,3 | 95,8 | 95,8 | 94,8 | 95,8 | 86,5 |
| BM25 seul | 94,8 | 88,5 | **69,8** | 94,8 | 93,8 | 92,7 | 94,8 | 86,5 |
| dense seul | 76,0 | 77,1 | 78,1 | 75,0 | 85,4 | 75,0 | 75,0 | 68,8 |

### 3.2 abpe171 — evidence_recall (%)

| config | propre | typo1 | typo3 | sans accents | télégraphique | abbr | expand | ABP (diag.) |
|---|---|---|---|---|---|---|---|---|
| **figée** | **98,2** | **93,3** | **89,5** | 97,8 | 97,7 | 97,1 | 97,7 | **91,9** |
| subword | 99,0 | 95,3 | 92,2 | 99,0 | 98,5 | 97,9 | 97,6 | 94,0 |
| lexique | 98,5 | 93,3 | 89,5 | 98,2 | 97,5 | 98,5 | 97,7 | 97,0 |
| subword + lexique | 97,9 | 94,3 | 92,4 | 97,9 | 98,2 | 98,4 | 97,6 | 98,4 |
| lexique « sigles purs » | 98,5 | 93,3 | 89,5 | 98,2 | 98,0 | 98,5 | 97,7 | 97,5 |
| glossaire (2 sens) | 98,0 | 92,8 | 89,0 | 98,4 | 98,0 | 98,0 | 98,2 | 91,4 |
| glossaire (sigle → forme) | 98,0 | 92,8 | 89,0 | 98,4 | 98,0 | 98,0 | 97,7 | 91,4 |
| BM25 seul | 95,7 | 91,3 | 74,7 | 95,7 | 95,3 | 94,1 | 95,7 | 90,0 |
| dense seul | 82,9 | 82,4 | 84,5 | 83,2 | 90,5 | 81,9 | 81,3 | 74,9 |

### 3.3 multirfe_synth — passage_hit (% ; n = 76 questions à passage de référence)

| config | propre | typo1 | typo3 | sans accents | télégraphique | abbr | expand | ABP (diag.) |
|---|---|---|---|---|---|---|---|---|
| **figée** | **96,1** | **94,7** | **93,4** | 98,7 | 96,1 | **92,1** | 96,1 | 96,1 |
| subword | 97,4 | 98,7 | 93,4 | 98,7 | 97,4 | 96,1 | 97,4 | 97,4 |
| lexique | 96,1 | 94,7 | 93,4 | 98,7 | 97,4 | 94,7 | 96,1 | 96,1 |
| subword + lexique | 97,4 | 98,7 | 93,4 | 98,7 | 97,4 | 96,1 | 97,4 | 97,4 |
| lexique « sigles purs » | 96,1 | 94,7 | 93,4 | 98,7 | 97,4 | 94,7 | 96,1 | 96,1 |
| glossaire (2 sens) | 94,7 | 94,7 | 92,1 | 97,4 | 96,1 | 94,7 | 94,7 | 94,7 |
| glossaire (sigle → forme) | 96,1 | 94,7 | 93,4 | 98,7 | 97,4 | 94,7 | 96,1 | 96,1 |
| BM25 seul | 86,8 | 82,9 | 78,9 | 86,8 | 86,8 | 84,2 | 84,2 | 86,8 |
| dense seul | 89,5 | 94,7 | 81,6 | 89,5 | 93,4 | 89,5 | 89,5 | 89,5 |

IC 95 % de chaque case dans `results/summary.md` (largeur typique ± 5 à 8 pts).

### 3.4 (i) Coût d'une saisie réelle pour la configuration figée — perturbé − propre, apparié

| Perturbation | abpe171 sufficiency | abpe171 evidence_recall | multirfe passage_hit | Deux jeux regroupés (suff. ∪ passage, n = 172) |
|---|---|---|---|---|
| typo1 | **−6,2 [−11,5 ; −2,1]** | −4,9 [−9,0 ; −1,6] | −1,3 [−3,9 ; 0] | **−4,1 [−7,0 ; −1,2]** |
| typo3 | **−11,5 [−18,8 ; −6,2]** | −8,7 [−14,1 ; −3,8] | −2,6 [−9,2 ; +3,9] | **−7,6 [−12,2 ; −2,9]** |
| sans accents | −1,0 [−3,1 ; 0] | −0,3 | +2,6 [0 ; +6,6] | +0,6 [−1,2 ; +2,9] |
| télégraphique | 0,0 [−3,1 ; +3,1] | −0,5 | 0,0 [−5,3 ; +5,3] | 0,0 [−2,9 ; +2,9] |
| abbr (questions modifiées) | −1 question sur 4 | −25 | −3 sur 14 (−21,4 [−42,9 ; 0]) | **−22,2 [−44,4 ; −5,6]** (n = 18 : 17 → 13) |
| expand (questions modifiées) | 0 sur 6 | −8,3 [−33 ; +17] | 0 sur 9 | 0 |
| ABP (diagnostic) | **−8,3 [−14,6 ; −3,1]** | −6,2 [−10,9 ; −2,4] | (2 questions, 0) | — |

Lecture des pertes (configuration figée, abpe171) : `typo1` fait perdre 6 questions, `typo3` 11, sans aucun gain ; une faute sur « antibioprophylaxie », « mandibule », « cardiaque » ou « dent » suffit. « ABP » fait perdre 8 questions. Sur multirfe, les fautes coûtent peu (1 et 4 pertes, 0 et 2 gains).

### 3.5 (ii) Ce que chaque fonction rattrape et ce qu'elle coûte — variante − figée, apparié

abpe171, sufficiency (toutes les questions du jeu ; pour abbr / expand / ABP, questions modifiées seulement) :

| Variante | propre | typo1 | typo3 | sans accents | télégr. | abbr (n=4) | expand (n=6) | ABP (n=96) |
|---|---|---|---|---|---|---|---|---|
| subword | +1,0 [−2,1 ; +5,2] | +2,1 [−3,1 ; +7,3] | +3,1 [−1,0 ; +7,3] | +2,1 [0 ; +5,2] | 0,0 | 0 | 0 | +2,1 [−2,1 ; +6,2] |
| lexique | 0,0 | 0,0 | 0,0 | 0,0 | −1,0 [−3,1 ; 0] | +25 [0 ; +75] | 0 | **+7,3 [+2,1 ; +13,5]** |
| subword + lexique | 0,0 [−3,1 ; +3,1] | +1,0 | +4,2 [0 ; +9,4] | +1,0 | 0,0 | +25 | 0 | **+10,4 [+5,2 ; +16,7]** |
| lexique « sigles purs » | 0,0 | 0,0 | 0,0 | 0,0 | 0,0 | +25 [0 ; +75] | 0 | **+7,3 [+2,1 ; +13,5]** |
| glossaire (2 sens) | −1,0 [−3,1 ; 0] | −1,0 | −1,0 | +1,0 | 0,0 | +25 [0 ; +75] | 0 | −1,0 |
| glossaire (sigle → forme) | −1,0 [−3,1 ; 0] | −1,0 | −1,0 | +1,0 | 0,0 | +25 | 0 | −1,0 |
| BM25 seul | −1,0 [−5,2 ; +2,1] | −1,0 | **−14,6 [−22,9 ; −7,3]** | 0,0 | −2,1 | −25 | 0 | −1,0 |
| dense seul | **−19,8 [−28,1 ; −12,5]** | −12,5 | −6,2 | −19,8 | −10,4 | 0 | −33 | −18,8 |

multirfe_synth, passage_hit :

| Variante | propre | typo1 | typo3 | sans accents | télégr. | abbr (n=14) | expand (n=9) |
|---|---|---|---|---|---|---|---|
| subword | +1,3 [0 ; +3,9] | +3,9 [0 ; +9,2] | 0,0 | 0,0 | +1,3 | +14,3 [0 ; +35,7] | 0 |
| lexique | 0,0 | 0,0 | 0,0 | 0,0 | +1,3 | +14,3 [0 ; +35,7] | 0 |
| subword + lexique | +1,3 | +3,9 [0 ; +9,2] | 0,0 | 0,0 | +1,3 | +14,3 | 0 |
| lexique « sigles purs » | 0,0 | 0,0 | 0,0 | 0,0 | +1,3 | +14,3 | 0 |
| glossaire (2 sens) | −1,3 [−3,9 ; 0] | 0,0 | −1,3 | −1,3 | 0,0 | +14,3 | 0 |
| glossaire (sigle → forme) | 0,0 | 0,0 | 0,0 | 0,0 | +1,3 | +14,3 | 0 |
| BM25 seul | **−9,2 [−15,8 ; −3,9]** | −11,8 | −14,5 | −11,8 | −9,2 | +7,1 | −33 |
| dense seul | −6,6 [−14,5 ; 0] | 0,0 | −11,8 | −9,2 | −2,6 | −7,1 | 0 |

Deux jeux regroupés (sufficiency abpe171 ∪ passage multirfe, n = 172, apparié) :

| Variante − figée | propre | typo1 | typo3 | sans accents |
|---|---|---|---|---|
| subword | +1,2 [−1,2 ; +3,5] | +2,9 [−0,6 ; +6,4] | +1,7 [−0,6 ; +4,1] | +1,2 [0 ; +2,9] |
| subword + lexique | +0,6 [−1,2 ; +2,9] | +2,3 [−0,6 ; +5,2] | +2,3 [0 ; +5,2] | +0,6 [0 ; +1,7] |
| glossaire (2 sens) | −1,2 [−2,9 ; 0] | −0,6 [−1,7 ; 0] | −1,2 [−2,9 ; 0] | 0,0 |

Sur les 18 questions « forme longue → sigle » (deux jeux) : figée 13/18 réussies (17 en propre), subword 15, lexique 16, glossaire 16.

### 3.6 Latence de `retrieve` et taille du contexte (1 568 requêtes par configuration, Mac 16 Go, MPS)

| Configuration | latence moyenne | médiane | p95 | contexte moyen (car.) | blocs |
|---|---:|---:|---:|---:|---:|
| figée | 190 ms | 190 | 204 | 20 777 | 27,7 |
| subword | 198 ms | 198 | 216 | 20 137 | 27,6 |
| lexique | 188 ms | 189 | 199 | 20 657 | 27,6 |
| subword + lexique | 197 ms | 197 | 214 | 20 012 | 27,5 |
| lexique « sigles purs » | 206 ms | 190 | 323* | 20 652 | 27,6 |
| glossaire (2 sens) | 194 ms | 195 | 211 | 20 727 | 27,7 |
| BM25 seul | 2 ms | 2 | 3 | 21 641 | 27,4 |
| dense seul | 188 ms | 191 | 206 | 19 870 | 28,1 |

\* p95 gonflé par une contention machine pendant ce passage (médiane identique à la figée).

Mémoire : l'index n-grammes (`subword.pkl`, 347 Mo sur disque contre 31 Mo pour BM25) est **déjà chargé** par `LocalVectorStore.load` quelle que soit la configuration ; l'activer ne coûte donc pas de mémoire supplémentaire au service, seulement ~8 ms par requête. Le glossaire pèse quelques centaines de Ko. Le temps de chargement de l'index au démarrage est inchangé.

## 4. Le lexique écrit à la main

`src/rag_sfar/retrieval/medical_lexicon.py` : 73 sigles (`MEDICAL_ACRONYMS`) et 25 synonymes (`CLINICAL_SYNONYMS`). Classement à la lecture :

- **60 sigles sont de simples expansions** (PTH, VNI, IOT, ALR, RTUP, HBPM sans molécules…, y compris ABP et ATBP).
- **13 ajoutent des termes au-delà de la forme longue** : 7 ajoutent des **noms de molécules** (C1G → céfazoline ; C2G → céfuroxime céfoxitine ; C3G → céfotaxime ceftriaxone ; AOD, AVK, AAP, HBPM → listes de molécules), 6 des mots de thème (ATB, IIA « péritonite », BLSE « entérobactérie », DFG, ClCr, IMC « obésité »). Les ajouts de C1G/C2G/C3G sont précisément les molécules attendues par le benchmark d'antibioprophylaxie : c'est la surface de surapprentissage.
- 25 synonymes : 21 noms commerciaux → DCI (générique), 4 synonymes de classe (bêtalactamines, pénicillines) orientés allergie.
- Biais de domaine : environ la moitié des sigles relèvent des actes et de l'infectiologie de l'antibioprophylaxie. 18 des 73 sigles ne sont définis nulle part dans le corpus en vigueur (dont ABP, ATBP, ATB, C1G, C2G, EBLSE, IIA) ; 49 des 55 présents dans le glossaire du corpus y ont la même forme longue.

**Mesure** : la version réduite aux 60 sigles purs (`lexicon_plain`, appliquée à la question) donne exactement le gain du lexique complet sur « ABP » (+7,3 [+2,1 ; +13,5]) et sur « forme longue → sigle », sans sa petite perte en style télégraphique (−1,0 → 0,0) ; les 13 entrées enrichies et les synonymes n'apportent rien de mesurable ici. Toute l'utilité mesurée du lexique vient des sigles que le corpus n'écrit pas (ABP) ou écrit autrement.

## 5. Ce que les données soutiennent (décision à l'utilisateur ; rien n'a été changé)

| Fonction | Gain sous saisie réelle | Coût sur questions propres | Risques | Recommandation |
|---|---|---|---|---|
| **`use_subword`** (n-grammes de caractères) | abpe171 sous fautes +2,1 / +3,1 pts (IC touchant 0) ; multirfe typo1 +3,9 [0 ; +9,2] ; regroupé typo1 +2,9 [−0,6 ; +6,4] ; sans accents +1,2 [0 ; +2,9] ; « forme longue → sigle » 15/18 contre 13/18. Aucune case négative sur 16. | +1,2 [−1,2 ; +3,5] (aucun coût) ; +8 ms ; contexte −3 % | Mémoire déjà payée (index chargé de toute façon) ; candidats bruités possibles mais non observés ; aucune surface de surapprentissage (canal générique). | **À activer si l'utilisateur dégèle**, en le présentant comme une protection modeste (≈ un quart à la moitié de la perte due aux fautes rattrapée), pas comme un gain démontré : aucun IC individuel n'exclut 0. À confirmer sur une nouvelle série (autre graine) avant de l'affirmer. |
| **`use_medical_lexicon`** (lexique complet) | « ABP » +7,3 [+2,1 ; +13,5] ; « forme longue → sigle » +3 questions sur 18 ; rien sur les fautes. | 0,0 sur propre ; −1,0 en télégraphique | 13 entrées enrichies dont 7 injectent des molécules (dont les réponses attendues de l'ABP) ; liste partiellement écrite à partir du benchmark. | **Ne pas réactiver tel quel. Remplacer** par sa partie « sigles purs » (60 entrées, aucune molécule, aucun mot de thème), qui donne le même gain mesuré sans le coût. La liste doit être relue (et étendue hors ABP) par un clinicien, hors de toute question d'évaluation. |
| **Expansion par le glossaire du corpus** (nouveau, générique) | « forme longue → sigle » 16/18 (+3) ; **rien sur « ABP »** (le corpus n'emploie pas ce sigle) ; rien sur les fautes. | −1,2 [−2,9 ; 0] regroupé (1 à 2 questions perdues) ; se déclenche sur 9 % (abpe) à 24 % (multirfe) des questions propres ; +4 ms | Ajoute du bruit sur des questions déjà correctes : les 2 pertes en propre viennent d'une forme longue anglaise ajoutée à « ECMO » (abpe171) et du sigle « AG » ajouté à « anesthésie générale » (multirfe) ; ambiguïtés (EP, AL, AE) ; précision 96 %. | **Garder éteint.** Il ne couvre pas le cas qui coûte le plus (sigle d'usage absent du corpus) et coûte un peu sur les questions propres. Utile comme outil : il a servi à construire les perturbations, et il permet de vérifier qu'un sigle d'une liste écrite à la main existe bien dans le corpus. |
| **`use_subword` + lexique « sigles purs »** | addition des deux (abpe171 « ABP » : +10,4 [+5,2 ; +16,7] pour subword + lexique complet) | ≈ 0 | ceux des deux | Combinaison la plus robuste mesurée ; à valider ensemble si dégel. |
| Correction orthographique, canal dense seul, BM25 seul | — | dense seul −19,8, BM25 seul −1 à −15 | — | Ne rien changer à l'architecture hybride : chaque canal seul est nettement moins bon ; le dense seul est insensible aux fautes mais trop faible sur l'ABP. |

**Ce qu'il faut retenir pour le jury** : sur des questions propres, le retrieval figé atteint 95,8 % de suffisance (abpe171 dev) ; avec une ou deux à trois fautes de frappe par question, il descend à **89,6 % et 84,4 %** ; avec « ABP » au lieu d'« antibioprophylaxie », à **87,5 %**. Les accents manquants et le style télégraphique ne coûtent rien. Ce sont des chiffres de dev, sur un jeu où le retrieval a été mis au point (le test abpe171 était déjà 13 pts plus bas sur questions propres) : la fragilité réelle est vraisemblablement au moins de cet ordre.

## 6. Limites

- Perturbations synthétiques, une seule graine ; fautes uniformes sur les mots de contenu (un clinicien se trompe plutôt sur les mots longs et les molécules). Pas de fautes sur les nombres ni sur les sigles.
- Dev seulement, dont le dev abpe171 qui a servi à la mise au point du retrieval : les niveaux absolus sont optimistes ; les écarts relatifs sont l'information utile.
- Les sous-ensembles « sigles » du glossaire sont petits (20 et 15 questions) ; le diagnostic « ABP » repose sur une seule substitution dominante.
- Expansions « glossaire » et « sigles purs » appliquées à la question avant `retrieve` (pas via le crochet du pipeline) : même format et mêmes canaux que le lexique, mais l'analyse de requête (population, période) voit le texte étendu.
- Précision du glossaire estimée par l'agent, pas par un médecin.

## 7. Fichiers

Créés : `src/rag_sfar/retrieval/corpus_glossary.py` (module isolé, importé par aucun module du pipeline ; un test le vérifie), `tests/test_corpus_glossary.py` (6 tests), `eval_internal/robustness/{README.md, build_glossary.py, perturb.py, run_retrieval.py, run_all.sh, analyze.py, glossary_tas_v6.json, glossary_sample50.csv, glossary_sample50_usable.csv}`, `eval_internal/robustness/sets/multirfe_synth/*.jsonl`, `sets/counts.json`, `results/summary.md`, `results/means.json`, ce rapport. Locaux (ignorés) : `sets/abpe171/`, `results/*.jsonl`, `logs/`. Règles `.gitignore` ajoutées par Q1 (3 lignes : `sets/abpe171/`, `results/*.jsonl`, `logs/`), versionnées dans le commit b1cb011 d'un autre agent qui a inclus .gitignore. **Aucune modification** de `pipeline.py`, `medical_lexicon.py`, `subword.py`, `config.py`, `ablation.py` ni de l'index. Suite de tests : 204 réussis, 1 ignoré (test anti-fuite inclus).
