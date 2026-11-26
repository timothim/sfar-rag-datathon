# Audit des données : corpus SFAR (sorties OCR Chandra)

*Audit indépendant fait le 2026-11-26. Le corpus n'est lu qu'en lecture seule. Tous les chiffres ci-dessous ont été mesurés par les scripts de `reports/agents/data_audit_scripts/` (relance complète : `reports/agents/data_audit_scripts/run_all.sh`, environ 45 s de CPU, sans appel réseau ni API). Les sorties brutes sont dans `reports/agents/data_audit_scripts/out/`.*

---

## Conclusions

1. **Le corpus compte 267 fichiers, mais beaucoup moins de recommandations distinctes.** On a 267 fichiers Markdown, pour 272 entrées dans `discovery.json` (5 téléchargements ont échoué). Le loader en garde 264 après déduplication SHA. Ces fichiers ne correspondent qu'à **176 titres distincts**, soit 180 « familles » si l'on regroupe par landing_url ou par titre (56 familles comptent plusieurs fichiers). On y trouve **202 textes principaux en français** : textes principaux, courts ou longs, hors traductions, fiches, algorithmes et annexes. Le volume total est de 23,3 M caractères, soit environ **5,8 M tokens** (caractères/4). La médiane est de 57 k caractères (environ 14 k tokens) par fichier et le maximum de 479 k. Les années 2025 et 2026 pèsent 24 % des tokens. La formule « 264 recommandations » du README est donc trompeuse.

2. **Le texte OCR est fidèle, mais le balisage est bruité.** Je n'ai pu comparer au PDF original qu'**un seul document**. Les 267 fichiers de `pdfs/` sont en effet des **pointeurs Git LFS de 130 octets**, jamais tirés. Sur ce document (V2.0 de l'antibioprophylaxie, 91 pages, comparée à la sortie Chandra de la V3.0), le rappel lexical est de **99,6 %** par page (médiane) et le rappel des posologies (« 2 g », « 30 mg/kg »…) de **99,3 %** sur 881 occurrences. Les pages en écart correspondent aux modifications V2→V3. Les défauts sont systématiques mais réparables :
   - 4 133 formules LaTeX `$…$` et 586 balises `<math>` (`\geq` apparaît 541 fois, contre 362 fois `≥`) ;
   - 2 051 entités HTML (`&gt; 4h` dans les tableaux de posologie) ;
   - 1 707 titres collés au texte et 504 titres collés à `</table>` ;
   - 1 130 images remplacées par un texte alternatif **généré en anglais** (101 k caractères) ;
   - 161 organigrammes convertis en Mermaid (`graph TD`, 82 documents) ;
   - des octets NUL dans 2 documents (« R\x00\x00serve ») ;
   - aucune balise de page : impossible de citer une page à partir du Markdown.

3. **Il n'existe pas de « format RFE » unique.** Sur les 202 textes principaux français :
   - 57 (28 %) suivent le format GRADE SFAR complet (Rx.y + GRADE + accord) ;
   - 14 (7 %) ont un GRADE sans identifiants ;
   - 18 (9 %) sont des RPP ou avis d'experts numérotés ;
   - 22 (11 %) ne portent qu'une cotation d'accord (RAND/UCLA) ;
   - 26 (13 %) utilisent une gradation ancienne A/B/C ;
   - 2 sont des conférences de consensus avec jury ;
   - **62 (31 %) sont narratifs.**

   Le format structuré (GRADE, RPP numérotées) concerne **3 à 32 % des textes avant 2015, puis 71 % en 2015-2019, 70 % en 2020-2022 et 87 % en 2023-2026**.

4. **Une extraction générique par règles est faisable sur environ 90 documents.** Le prototype (`04_reco_markers.py`) extrait **2 355 recommandations** (après déduplication par identifiant) dans 89 documents, dont 1 897 avec leur grade et 1 439 avec leur niveau d'accord. Pour le valider, je l'ai comparé au nombre que le document déclare lui-même (« ont abouti à N recommandations », présent dans 45 documents) : l'écart est **inférieur à 10 % pour 25/45 documents et inférieur à 20 % pour 36/45**. Sur un échantillon de 30 unités, 27 sont correctes.

5. **La formulation ne suffit pas à déduire la force d'une recommandation.** Depuis le gabarit HAS adopté en 2024-2026, « Il est recommandé » peut correspondre à un **GRADE 2** (recommandation faible, preuves de qualité élevée). J'en ai compté 170 cas, notamment dans `2026/gestion_voies_aeriennes_recommandations_mel_vd.md:153-155`. Les cellules « AE » ou « 1 » / « 2 » des tableaux portent donc la vraie force. Les « ●●● (GRADE 2) » de l'antibioprophylaxie V3.0 sont un troisième codage.

6. **La supersession du loader est globalement plausible, mais elle a des erreurs et des oublis.** Le décompte de 44 éditions remplacées est confirmé. Parmi elles :
   - environ 38 sont plausibles, dont **10 seulement sont attestées par une mention explicite** dans le texte de la nouvelle édition ;
   - 6 sont douteuses : 4 documents sepsis 2004-2006 rattachés à la recommandation sepsis HAS 2025 (périmètre différent), l'AVK HAS 2008 rattaché à l'« acte programmé 2026 », et une recommandation britannique (DAS, BJA 2015) rattachée à la SFAR 2026.

   J'ai trouvé **au moins 2 oublis** :
   - *Urgences obstétricales extrahospitalières 2010* reste marquée « en vigueur » alors que la RPP de 2022 la remplace explicitement (`2022/rpp-urgences-obstetricales-en-medecine-durgence…md:154`) ;
   - la RPP COVID **abrogée** reste active à travers son quasi-doublon « finale sans marque » (similarité de Jaccard 0,94).

   Enfin, la similarité de titre seule produit des faux positifs (« traumatisés **crâniens** » ~ « traumatisés **pelviens** », J = 0,67).

7. **Les métadonnées sources sont peu fiables, et l'imputation de domaine du loader en ajoute de fausses.** Côté sources :
   - il manque l'année pour 22 fichiers (8 %), le sous-domaine pour 57 (21 %), la discipline pour 11 et la landing_url pour 28 ;
   - le champ `year` de discovery correspond parfois à la **date de mise en ligne** et non à la date de publication (dossier 2021 : tests viscoélastiques 2018, AAP en urgence 2018, AOD en urgence 2016, AOD programmé 2015) ;
   - le `type` vaut « RFE » pour 226/267 fichiers, y compris 17 documents HAS, ANAES, SPILF, AFU, BJA ou RPP.

   Côté loader, l'imputation par sous-chaîne attribue un domaine à tort à **102/264 documents**. Le cas le plus fréquent est le mot-clé « rac » trouvé dans « ca**rac**téristiques » ou « t**rac**héotomie », qui ajoute « Ambulatoire et Réhabilitation » à 59 documents.

8. **Les tableaux pèsent 12,5 % du texte, et un sur cinq est en fait un encadré de recommandation.** On compte 2 060 tableaux, **tous en HTML** (0 tableau Markdown à barres verticales), répartis dans 185 documents :
   - 452 sont des **encadrés de recommandation OCRisés en tableau** (44 documents), dont 55 tableaux à une seule cellule ;
   - 291 donnent des posologies ;
   - 162 décrivent la méthodologie ou la gradation ;
   - 149 présentent des scores ou des critères ;
   - 79 sont des formulaires ou check-lists.

   1 011 tableaux (49 %) n'ont pas d'en-tête, mais seuls **environ 325 (16 %) sont de vraies suites de tableau coupé** entre deux pages (contigus, même nombre de colonnes). Le README les compte toutes comme des suites. Enfin, 258 tableaux dépassent environ 500 tokens et 20,7 % des cellules sont vides (rowspan, mise en page).

9. **Il reste des quasi-doublons et des documents imbriqués après la déduplication SHA.** Les 3 doublons exacts (même PDF) sont éliminés par le loader. Restent pourtant :
   - 12 paires avec un Jaccard ≥ 0,5, dont TIH 2019 (deux fichiers, J = 1,00), AAP « 2021 » = RFE 2018 (0,98), COVID abrogée ou non (0,94) et AOD 2015 / « 2021 » (0,83) ;
   - 37 paires avec un taux d'inclusion ≥ 0,5 : texte court inclus dans le texte long, fiches de synthèse incluses dans le texte principal.

   Les références bibliographiques représentent **19 à 26 %** des caractères, ce qui confirme l'ordre de grandeur du README (25,4 %). En revanche, 153/267 documents n'ont pas de section « Références » titrée.

---

## 0. Méthode, périmètre et limites

| Script | Rôle | Sortie |
|---|---|---|
| `01_inventory.py` | inventaire, tailles, langues, formes, doublons, quasi-doublons (MinHash + Jaccard exact sur 5-grammes de mots), métadonnées manquantes | `out/inventory.json`, `out/inventory.tsv`, `out/near_duplicates.json` |
| `02_ocr_quality.py` | défauts OCR sur tout le corpus, échantillon de 20 documents, comparaison au PDF V2.0 | `out/ocr_quality.json` |
| `02b_dump_loader.py` | exécute `load_sfar_corpus` du projet et sauvegarde les métadonnées calculées | `out/loader_metadata.json` |
| `03_editions.py` | familles, mentions explicites d'éditions antérieures, paires de titres, évaluation des lignées du loader | `out/editions.json` |
| `03a_domain_check.py` | domaines imputés par sous-chaîne | stdout |
| `04_reco_markers.py` | marqueurs GRADE, force, accord, PICO, champ, argumentaire ; format par document et par période ; prototype d'extraction et validation | `out/reco_markers.json`, `out/reco_units.jsonl` |
| `05_tables.py` | typologie et défauts des tableaux | `out/tables.json` |
| `06_references_share.py` | part de la bibliographie (deux méthodes) | stdout |

Relance : `cd /Users/tim/Me/SFAR-datathon && reports/agents/data_audit_scripts/run_all.sh` (ordre requis : 01 → 02b → 03).

Limites :
- **PDF absents.** `data/sfar_recommendations/output/pdfs/**.pdf` sont des pointeurs LFS (`version https://git-lfs…`). Je n'ai pas lancé `git lfs pull`, qui aurait téléchargé les fichiers et modifié l'arbre de travail. La seule comparaison au PDF porte donc sur `data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/RFE-antibioprophylaxie-SFAR-v2.0.pdf`.
- Les classifications de forme et de format reposent sur des heuristiques fondées sur les noms de fichiers et des expressions régulières. Les faux positifs et faux négatifs sont discutés à chaque section.
- « Tokens » = caractères/4, comme demandé. Chandra compte lui-même 10,1 M tokens selon son tokenizer, balises HTML incluses.

---

## 1. Inventaire

Commande : `.venv/bin/python reports/agents/data_audit_scripts/01_inventory.py` (le résumé s'affiche sur stdout).

### 1.1 Fichiers et jointures

| Élément | Valeur |
|---|---:|
| Entrées `discovery.json` | 272 (227 RFE, 22 RPP, 18 Préconisation, 5 HAS) |
| … sans `filename` (échec de téléchargement : réponse HTML ou .docx) | 5 |
| Fichiers `.md` Chandra (+ `.html` et `_metadata.json` jumeaux) | 267 |
| `.md` joints à une entrée discovery (logique du loader : année + stem) | 267/267 |
| Fichiers `pdfs/` | 267, **tous des pointeurs LFS** |
| Empreinte LFS (oid) = `sha256` discovery | 266/267 (exception : `RFE-20.4.2026-deifinitif-et-validei.pdf`, dont le sha discovery est celui du pointeur ; `bytes` = 132) |
| Documents après déduplication par le loader | 264 |
| Titres distincts / landing_url distinctes / familles | 176 / 152 / 180 (56 familles multi-fichiers) |

### 1.2 Années (dossier = champ `year` de discovery)

2000: 2 · 2001: 10 · 2002: 4 · 2003: 4 · 2004: 6 · 2005: 5 · 2006: 11 · 2007: 5 · 2008: 8 · 2009: 7 · 2010: 9 · 2011: 4 · 2012: 6 · 2013: 4 · 2014: 8 · 2015: 8 · 2016: 22 · 2017: 11 · 2018: 12 · 2019: 18 · 2020: 6 · 2021: 15 · 2022: 8 · 2023: 5 · 2024: 8 · 2025: 14 · 2026: 25 · inconnue: 22.

Tokens (≈) par année : 2025 = 668 k et 2026 = 720 k (24 % du total), « inconnue » = 388 k (6,7 %).

**Attention, `year` ne donne pas toujours l'année de publication.** Le dossier 2021 contient des republications : `Tests%20viscoelastiques%202018` (article daté « © 2018 », ligne 56), `Gestion…AAP en urgence` (copie à J = 0,98 de la RFE 2018), `Gestion…AOD en urgence` (« Réactualisation … septembre 2016 », ligne 1) et `Gestion…AOD pour un acte programmé` (copie GIHP 2015, J = 0,83). Le loader ne corrige que `2013 AFAR GIHP` (2021 → 2013). Il impute par ailleurs **1996** à `unknown/2b_AFAR_Texte-Long_Intubation-difficile`, alors que son texte dit « La conférence d'experts publiée en 1996 vient d'être réactualisée » (ligne 7) : c'est l'édition de 2006.

### 1.3 Types et formes

- Le **`type` discovery** se répartit en 226 RFE, 21 RPP, 15 préconisations et 5 HAS (sur les 267 fichiers). Ce champ n'est pas fiable : 17 fichiers typés « RFE » sont des documents HAS, ANAES, SPILF, AFU ou BJA, ou des RPP (`2_HAS_*`, `2_ANAES_*`, `2_SPILF_*`, `2_PUROL_*`, `rpp-*`, `BJA-2015-*`). Par ailleurs, 130 fichiers typés RFE ne mentionnent pas « recommandations formalisées d'experts » dans leurs 5 000 premiers caractères.
- **Forme**, inférée du nom de fichier et de la langue :

  | Forme | n |
  |---|---:|
  | texte principal | 164 |
  | texte court | 19 |
  | texte long / argumentaire | 19 |
  | traduction anglaise | 22 |
  | fiche / aide cognitive / synthèse | 19 |
  | annexe (certificat, note de cadrage, livret…) | 14 |
  | algorithme / figure | 9 |
  | abrogée | 1 |

- **Nature déclarée en tête de document** (5 000 premiers caractères ; un fichier peut cumuler plusieurs marqueurs) :

  | Marqueur | Fichiers |
  |---|---:|
  | RFE (« recommandations formalisées d'experts ») | 83 |
  | HAS / RBP | 55 |
  | conférence de consensus | 25 |
  | conférence d'experts | 22 |
  | RPP | 21 |
  | propositions GIHP | 21 |
  | avis / recommandations d'experts | 26 |
  | préconisations | 7 |
  | référentiel / guide | 99 (marqueur peu spécifique) |
  | aucun marqueur | 69 |

- **Documents non SFAR présents dans le corpus** : HAS (infarctus 2006, AVC 2009, transfusion 2012/2014, AVK 2008, sepsis 2025…), ANAES (IVG), SPILF, AFU (ECBU 2026), DAS britannique (`unknown/BJA-2015-reco-ventilation-et-IOT1.md:80`, « The Difficult Airway Society commissioned… »).

### 1.4 Langues

Langue déterminée par les mots outils sur 20-80 % du corps : **fr 207, en 22, bilingue 12, indéterminée 26** (documents de moins de 30 mots outils : fiches, algorithmes). Le loader obtient fr 215, en 24, bilingual 25, avec une méthode proche. **1 050 des 1 130 textes alternatifs d'images sont en anglais** : ils ont été générés par Chandra, par exemple `2023/RFE-antibioprophylaxie-…md:1` (`![SFAR logo]…`).

### 1.5 Tailles

Médiane de 57 297 caractères (≈ 14 k tokens), p10 de 6 689, p90 de 191 819, maximum de 479 229 (`2026/Reco_ECBU_Argumentaire_04.03.2026_MEL`). Au total, 6 825 pages selon les sidecars Chandra.

### 1.6 Doublons

- **Exacts (même PDF, d'après l'oid LFS)** : 3 paires.
  - `2011/2_AFAR_echographie…` = `unknown/2_AFAR_echographie…` ;
  - `2010/2_AFAR_Urgences-Obstetricales…` = `unknown/Urgences-obstetricales-extrahospitalieres` ;
  - `2010/2a_HAS_texte-court_Delivrance…` = `unknown/recommandations_-_delivrance…`.

  Les sorties Markdown diffèrent uniquement par le nom haché des images (vérifié avec `diff` sur la paire échographie). Le loader les élimine.
- **Quasi-doublons non éliminés** (`out/near_duplicates.json`) : 12 paires avec J ≥ 0,5 :
  - `2019/diagnostic-et-prise-ne-charge-dune-TIH` ~ `2019/propositions-tih-gihp-gfht-sfar` (J = 1,00) ;
  - `2018/rfe-gestion-des-agents-antiplaquettaires` ~ `2021/Gestion…AAP en urgence` (0,98) ;
  - `2022/RPP SFAR COVID…finale sans marque` ~ `2022/RPP-SFAR-COVID…abrogee-010723` (0,94) ;
  - `2015/Reactualisation-GIHP_AOD…` ~ `2021/Gestion…AOD pour un acte programmé` (0,83) ;
  - `2017/Antibioprophylaxie-version-2017` ~ `2018/Antibioprophylaxie-RFE-mise-a-jour-2018` (0,77).
- **Documents imbriqués** (taux d'inclusion ≥ 0,5) : 37 paires. Exemples : nutrition 2026 `Version-courte` ⊂ `Version-longue` (0,95) ; `gestion_voies_aeriennes_recommandations` ⊂ `…argumentaire` (0,91) ; `Reco_ECBU_Synthese` ⊂ `Reco_ECBU_Argumentaire` (0,83) ; fiches de synthèse ⊂ texte (TSM 2020 : 0,91 ; hyperthermie : 0,93). Conséquence pour le RAG : la même recommandation est récupérée deux à trois fois.

### 1.7 Documents vides ou tronqués

- 24 fichiers font moins de 3 000 caractères. Ce sont tous des fiches, algorithmes ou annexes légitimes (téléconsultation CAMR, algorithmes voies aériennes 2026, thromboses post-vaccinales). Aucun n'est vide, sauf la page 1 de `2026/Aides-cognitives-Organisation…` (0 token).
- 21 pages ont moins de 60 tokens, dans 15 documents. Ce sont des pages blanches (48 tokens = gabarit vide).
- Fins de document : 234/267 se terminent par une ponctuation, un tableau, une figure ou une référence. Sur les 33 autres, la plupart se terminent par un glossaire ou une liste. Trois sont suspectes : `2004/2_SFAR_Traitement-des-urgences-transfusionnelles-obstetricales` (« …leur efficacité »), `2018/RPP_beta-lactamines…` et `2024/2024_RFE-optimisation-hemodynamique…`. Sans les PDF, impossible de confirmer une troncature (la comparaison du nombre de pages PDF/Chandra n'a pas pu être faite).

### 1.8 Métadonnées manquantes

| Champ (discovery, 272 entrées) | Manquant |
|---|---:|
| year | 22 |
| subdomain | 58 (57 parmi les fichiers chargés), dont les RFE 2026 voies aériennes, ALR pédiatrique et anticoagulants |
| discipline | 11 |
| landing_url | 29 |
| filename / sha256 | 5 |

Le sous-domaine est aussi **incohérent** : les variantes `Hématologie – Coagulation – Transfusion` et `…–Transfusion` (sans espace) coexistent, parfois dans la même cellule (`… | Hématologie – Coagulation –Transfusion`, 7 entrées).

---

## 2. Qualité OCR Chandra

Commande : `.venv/bin/python reports/agents/data_audit_scripts/02_ocr_quality.py`.

### 2.1 Comparaison au PDF (un seul PDF réel disponible)

J'ai comparé page à page le PDF V2.0 de l'antibioprophylaxie (extraction pypdf, 91 pages) avec `2023/RFE-antibioprophylaxie-2023_V3.0_…md`. Les pages 1 à 90 sont quasi identiques d'une version à l'autre, hors changelog.

| Mesure (90 pages) | Valeur |
|---|---:|
| Rappel des mots du PDF dans le Markdown (médiane) | **0,996** |
| Rappel des 5-grammes de mots (médiane) | 0,880 (ordre des cellules et coupures PDF) |
| Rappel des posologies « nombre + unité » (881 occurrences) | **0,993** |
| Pages avec un 5-gramme < 0,7 | p1, 6, 7, 15, 28, 31, 40 |

Les écarts correspondent aux zones modifiées en V3.0 : résumé et abstract p6-7, où la V2.0 contient des « XX » ; obésité p28-31, cf. changelog `…V3.0…md:19` (« V3.0 du 04/05/2026 ») ; liste des relecteurs p15. **Je n'ai trouvé aucune erreur de caractère sur les doses.** Le texte lui-même est d'excellente qualité, y compris pour les documents scannés de 2001-2002 (`2002/86-civdccons.md:20-40`, `2001/cc_pancreatiteaigue20010.md`).

### 2.2 Défauts systématiques (tout le corpus)

| Défaut | Occurrences | Documents | Exemple |
|---|---:|---:|---|
| Liste à puce doublée `- • `, `- ● `, `- ■ ` | 10 588 | 229 | `2018/2_RFE-CURARE-3.md:132` |
| Numérotation doublée `1. 1.` | 1 833 | 97 | `2018/2_Gestion-des-agents-antiplaquettaires…md:7` |
| LaTeX inline `$…$` (`$\geq 2$`, `$IC_{95}$`, `$n = 96$`) | 4 133 | 192 | `2026/Version-longue.md:1228` |
| Balise `<math>` (y compris dans les énoncés de recommandation) | 586 | 70 | `2018/2_RFE-CURARE-3.md:554` (« IMC \geq 40 kg/m^2 ») |
| Entités HTML (`&gt;`, `&lt;`) | 2 051 | 124 | `2025/RBP_…RESECTION…ARGUMENTAIRE…md:818` (« 1g si durée &gt; 4h ») |
| Titre collé à la phrase précédente (`…Decousser.## HISTORIQUE`) | 1 707 | 210 | `2023/RFE-antibioprophylaxie…md:59` |
| Texte collé après `</table>` | 504 tableaux | 119 | `2025/RBP_…RESECTION…ARGUMENTAIRE…md:60` (`</table>### Formulations…`) |
| Image et texte alternatif généré (en anglais 93 %) | 1 130 (101 k caractères) | 201 | `2023/RFE-antibioprophylaxie…md:1` |
| Organigrammes Mermaid (```` ``` ```` + `graph TD`) | 161 | 82 | `2006/2_AFAR_Prise-en-charge-de-larret-cardiaque-1.md:142` |
| Cases à cocher `<input type="checkbox">` | 549 | 13 | formulaires, certificat voies aériennes difficiles |
| `<sup>` / `<sub>` (appels de notes, SpO<sub>2</sub>) | 6 082 / 1 210 | 211 / 110 | — |
| Octets NUL | 266 | **2** | `2022/RFE-Programme-doptimisation…` (198), `2025/RESECTION…RECOMMANDATIONS_MEL` (68 : « R\x00\x00serve ») ; `grep` traite ce fichier comme binaire |
| Paragraphe coupé (fin sans ponctuation, suite en minuscule) | 505 | 106 | pire cas : `unknown/2b_AFAR_Texte-Long_Intubation-difficile` (24) |
| Césure `anesthé- sie` | 89 | 54 | rare |
| En-têtes ou pieds répétés (≥ 4 fois) | rares | — | Chandra supprime les en-têtes courants. Restent « © 2008 Elsevier Masson SAS » et « * Auteur correspondant » (12 fois chacun dans `2008/2b_AFAR_texte-long_Securisation…`) |
| Numéros de page isolés | 40 | 11 | négligeable |
| Caractère de remplacement U+FFFD, ligatures, zone privée Unicode, texte non NFC | 0 | 0 | — |
| **Marqueurs de page** | **0** | — | ni le `.md` ni le `.html` n'ont de séparateur de page. Le sidecar `_metadata.json` donne le nombre de tokens par page, sans position dans le texte |

**Unités et notations** :
- `µg` (signe micro U+00B5) 492 fois, `μg` grec 0, `mcg` 10 ;
- `mg/kg` 1 094 fois, contre 6 pour `mg.kg-1` / `mg·kg−1` ;
- **≥ écrit de trois façons** : `≥` 362, `\geq` 541, `>=` 33 ;
- décimale à virgule 1 077 fois, à point 163 fois (34 documents, surtout les traductions).

Un index lexical (BM25) ne fera pas correspondre « ≥ 2 » avec « $\geq 2$ » sans normalisation.

### 2.3 Échantillon stratifié (20 documents, 2000-2026, tous domaines)

Tableau imprimé par `02_ocr_quality.py`, section « Échantillon ». J'ai aussi inspecté manuellement : corticothérapie 2000, pancréatite 2001, CIVD 2002, HSA 2004, blocs périmédullaires 2006, état de mal 2008, ALR pédiatrique 2010, examens préinterventionnels 2012, épuration extrarénale 2014, douleur postopératoire 2016, curares 2018, traumatisme abdominal 2019, TSM 2020, traumatisme crânien léger 2022, antibioprophylaxie V3.0, MTEV 2024, hypersensibilité 2025, infections intra-abdominales 2026, ALR pédiatrique 2026 et intubation difficile (date inconnue).

Ce qu'il faut retenir :
- aucun document illisible ;
- les documents récents (2023-2026) concentrent LaTeX, `<math>`, entités et titres collés ; l'antibioprophylaxie V3.0 cumule 53 titres collés et 259 entités ;
- les documents anciens se caractérisent par des listes doublées et des paragraphes coupés ;
- les encadrés de recommandation sont tantôt des paragraphes en gras, tantôt des tableaux à une cellule (`2018/2_RFE-CURARE-3.md:188`) ;
- un tableau coupé par une page devient `</table><table border="1">` sans en-tête, avec un `rowspan` orphelin (`2023/RFE-antibioprophylaxie…md` autour des lignes 876-900).

---

## 3. Éditions et supersession

Commandes : `PYTHONPATH=src .venv/bin/python reports/agents/data_audit_scripts/02b_dump_loader.py`, puis `.venv/bin/python reports/agents/data_audit_scripts/03_editions.py`.

### 3.1 Ce que le loader calcule (vérifié)

264 documents, 26 lignées (94 documents) et **44 documents marqués « remplacés »**, conformément à `reports/corpus_audit.md`. Les lignées sont **définies à la main par des expressions régulières sur les titres** (`LINEAGE_RULES`). Ce n'est pas une méthode générique : un nouveau titre ou une nouvelle formulation échappe aux règles.

### 3.2 Exactitude sur les 44 supersessions (sortie « Supersessions du loader »)

| Verdict | n | Détail |
|---|---:|---|
| Attestée par une mention explicite dans la nouvelle édition | 10 | ALR pédiatrique 2010→2026 (`2026/TEXTE-RFE-ALR-PEDIA…md:119`), hypersensibilité 2011→2025 (`…md:143`), hyperthermie maligne 2013→2019 (`2019/rpp-hyperthermie-maligne.md:13`), infections intra-abdominales 2015→2026 ×2 (`…md:143`), prééclampsie 2009→2020 (`…md:71`), MTEV 2011→2024 (`2024/240516-Txt-definitif-.md:25`), sédation 2010→2026 (`…md:99`), TIH 2002→2019, vertébro-médullaire 2003→2019 (`…md:123`) |
| Plausible (même sujet, titre proche, pas de mention trouvée dans les 25 k premiers caractères) | ≈ 28 | antibioprophylaxie 2017/2018→V3.0, douleur postopératoire 2008→2016 (mention dans la version anglaise : « update of the 2008 guidelines »), erreurs médicamenteuses, pancréatite, voies aériennes, intubation difficile, AOD urgence ou programmé, AAP, nutrition, USC, organisation pédiatrique, blocs périphériques, remplissage |
| **Douteuse ou de périmètre partiel** | 6 | `sepsis_general` : antibiothérapie probabiliste 2004, sepsis hémodynamique 2005 ×2 et états septiques 2006, tous rattachés à la recommandation HAS sepsis 2025 (autre émetteur, périmètre différent). `anticoagulants_procedure_programmee` : « Recommandations AVK » HAS 2008 (surdosages et hémorragies sous AVK) remplacé par l'« acte **programmé** 2026 ». `BJA-2015` : guideline britannique (DAS) « remplacée » par la SFAR 2026 |

**Éditions manquées :**
1. `2010/2_AFAR_Urgences-Obstetricales-Extrahospitalieres` est marquée `is_latest_edition=True` alors que `2022/rpp-urgences-obstetricales-en-medecine-durgence.md:154` déclare « En 2010, la SFAR et la SFMU ont publié des recommandations… [sur les] urgences obstétricales extrahospitalières ». La règle `urgences\s+obstétricales\s+extrahospitali` ne reconnaît pas le titre de 2022.
2. RPP COVID : `RPP-SFAR-COVID…abrogee-010723` est bien `is_active=False`, mais son jumeau `RPP%20SFAR%20COVID_Version%20Avril%202022_finale%20sans%20marque` (J = 0,94) reste `is_active=True`, `is_latest_edition=True`. Le texte abrogé reste donc dans l'index.
3. Doublons de contenu dont les **deux** copies sont « en vigueur » : TIH 2019 ×2, AAP en urgence 2018 / « 2021 ».

### 3.3 Relier les éditions de façon générique : ce que le corpus permet

- **Mention explicite datée** : 47 documents citent une édition antérieure avec son année dans leurs 25 premiers k caractères. Mots-clés : actualisation, réactualisation, mise à jour, remplace, révision, update. Exemples : `2018/2_RFE-CURARE-3.md:17` (« Mettre à jour le référentiel français … qui datait de 1999 ») ; `2010/2_AFAR_Nutrition-artificielle-perioperatoire…md:3` (« Actualisation 2010 de la conférence de consensus de 1994 »). **Mais** beaucoup renvoient à des éditions absentes du corpus (1994, 1997, 1999), et certaines mentions sont parasites (citations d'autres sociétés, comme les « recommandations européennes actualisées en 2023 » dans la nutrition 2026).
- **Similarité de titre** : 59 paires inter-années (J ≥ 0,45 ou inclusion ≥ 0,75), dont 41 sont déjà dans une lignée du loader. Les 17 autres sont surtout des faux positifs : crâniens ~ pelviens 2016→2017, thoracique ~ abdominal 2014→2019, AAP ~ anticoagulants 2018→2026. Les trois livrets « formation IDE réanimation » (dates imputées 2002, 2003, 2008) sont trois parties d'un même document, pas trois éditions.
- **landing_url** : elle groupe les **parties d'une même édition** (texte court, long, fiches, traduction) : 56 familles multi-fichiers. Elle ne permet pas de relier deux éditions entre elles (URL différentes).
- **Version interne** : seule l'antibioprophylaxie porte un historique de versions (`…V3.0…md:19`, `:65` « V2.0 du 22/05/2024 »).

Recommandation : (a) grouper les parties d'une édition par landing_url ; (b) proposer les liens entre éditions à partir des mentions explicites et du recouvrement de titre ; (c) **faire valider à la main la table des liens**, qui reste petite (environ 30 lignées), et y noter le périmètre (adulte ou pédiatrique, programmé ou urgence) et le caractère total ou partiel du remplacement. Avec seulement 180 familles, une table curée bat toute heuristique.

### 3.4 Imputation des domaines (`03a_domain_check.py`)

Le loader **ajoute** des domaines par sous-chaîne à tous les documents, et pas seulement à ceux dont le sous-domaine manque. Résultat : 102/264 documents reçoivent au moins un domaine déclenché uniquement par une sous-chaîne :
- « rac » donne « Ambulatoire et Réhabilitation » dans 59 documents (« ca**rac**téristiques de GRADE », « t**rac**héotomie ») ;
- « membre » donne « Traumatologie » dans 20 documents ;
- « neuro » donne « Neuro-Réanimation » dans 13 documents (« neurologiques ») ;
- « usc » donne « Organisation » dans 10 documents (« m**usc**ulaire »).

En moyenne, un document reçoit 2,8 domaines, et jusqu'à 7. Tout filtre ou « boost » par domaine en est faussé.

---

## 4. Structure type d'une RFE SFAR et extraction générique

Commande : `.venv/bin/python reports/agents/data_audit_scripts/04_reco_markers.py` (unités extraites dans `out/reco_units.jsonl`).

### 4.1 Anatomie d'une RFE GRADE SFAR (2015-2026)

On trouve dans l'ordre : résumé et abstract avec le nombre de recommandations, puis la méthode (PICO, GRADE, vote Delphi, seuils d'accord). Viennent ensuite des **champs** (`Champ 1 …`), découpés en **questions** (`Question 1.2 : …`), chacune portant une ou plusieurs **recommandations** `R<champ>.<question>[.<n>]`. Chaque recommandation a un **énoncé**, une **cotation** (GRADE 1/2 et +/−, ou avis d'experts) et un **accord** (fort ou faible), puis un **argumentaire** et des **références** (par champ ou en fin de document).

Exemples réels :
- `2016/RFE-ANREA-Reactualisation…douleur…md:217-219` : « R3.1 – Il est recommandé d'associer un AINS… » puis « G1+, Accord fort. » ;
- `2018/2_RFE-CURARE-3.md:188` : encadré-tableau « R1.1 – Il n'est probablement pas recommandé… » / « (Grade 2-) Accord FORT » ; méthode aux lignes 153-154 (« Forte : Il faut faire… GRADE 1+ ; Faible : Il faut probablement… GRADE 2+ ») ; argumentaire à la ligne 229 ;
- `2014/2_AFAR_Nutrition-artificielle-en-reanimation.md:127` : « Encadré 4.1 – Il faut administrer… (Accord fort). » (cotation d'accord seule, identifiant « Encadré ») ;
- `2022/RPP-Trauma-cranien-leger…md:292-298` : « R2.5 - Les experts proposent… » / « Avis d'experts (Accord Fort) » ;
- `2025/2025_RFE-Intubation-adulte-hors-bloc-hors-rea-.md:378-380` : « R1.3.1 – … il est probablement recommandé… » / « GRADE 2 (Accord Fort) » ;
- `2026/RFE_sedationproceduraleUrgences_24juin2026.md:320` : « **R1.1.1** Chez les patients… les experts suggèrent… » (identifiant en gras, sans séparateur) ;
- `2026/Version-courte.md:672` et `2026/gestion_voies_aeriennes_recommandations_mel_vd.md:148-151` : **gabarit HAS**, tableau `<td>R1.1.1</td><td>énoncé</td><td>1|2|AE</td>`, avec des rangées « Champ » et « Question » en `colspan` ;
- `2023/RFE-antibioprophylaxie…md:637,736` : force dans une cellule « ●●● (GRADE 2) » / « ●●● (Avis d'experts) » des tableaux de posologie ;
- formats anciens : `2001/2_AFAR_Les-blocs-peripheriques…md:187` (« … ne sont pas recommandées (B). », gradation A/B/C) ; `2002/86-civdccons.md:22-36` (« QUESTION 1 » puis « Le jury retient : »).

### 4.2 Fréquence des marqueurs (267 fichiers / 202 textes principaux français)

| Marqueur | Occurrences | Fichiers | Textes principaux FR |
|---|---:|---:|---:|
| Force positive forte (« il faut », « il est recommandé », « nous recommandons ») | 3 943 | 189 | 182 |
| Force positive faible (« il faut probablement », « il est probablement recommandé », « nous suggérons ») | 950 | 82 | 81 |
| Force négative forte (« il ne faut pas », « il n'est pas recommandé ») | 620 | 123 | 121 |
| Force négative faible (« il ne faut probablement pas », « il n'est probablement pas recommandé ») | 249 | 57 | 57 |
| Avis d'experts (« les experts suggèrent/proposent », « avis d'experts ») | 3 241 | 124 | 116 |
| Étiquette GRADE (`GRADE 1+`, `G2-`…) | 2 175 | 103 | 81 |
| Accord (fort, faible, relatif, professionnel) | 3 180 | 113 | 109 |
| Gradation ancienne (grade A/B/C, niveau de preuve) | 1 373 | 82 | 74 |
| « le jury recommande » | 29 | 5 | 5 |
| PICO | 234 | 72 | 64 |
| Titre « Argumentaire » | 1 368 | 86 | 83 |
| Titre « Champ n » / « Question n » | 417 / 761 | 39 / 66 | 38 / 61 |
| Titre « Références » | 675 | 109 | 89 |

### 4.3 Part des documents au format structuré, par période (202 textes principaux FR)

| Période | n | GRADE SFAR (Rx + GRADE + accord) | GRADE sans identifiant | RPP / avis d'experts numérotés | Accord seul | Grades A/B/C | Jury | Narratif | **% structuré (3 premières colonnes)** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2000-2004 | 26 | 0 | 1 | 0 | 1 | 7 | 1 | 16 | 4 % |
| 2005-2009 | 35 | 0 | 5 | 0 | 6 | 6 | 1 | 17 | 14 % |
| 2010-2014 | 28 | 4 | 5 | 0* | 6 | 4 | 0 | 8 | 32 % |
| 2015-2019 | 45 | 27 | 1 | 4 | 6 | 1 | 0 | 6 | **71 %** |
| 2020-2022 | 20 | 7 | 0 | 7 | 1 | 0 | 0 | 5 | **70 %** |
| 2023-2026 | 31 | 19 | 1 | 7 | 1 | 3 | 0 | 0 | **87 %** |
| inconnue | 17 | 0 | 1 | 0 | 1 | 5 | 0 | 10 | 6 % |
| **Total** | 202 | 57 | 14 | 18 | 22 | 26 | 2 | 62 | **44 %** |

\* Plus 1 document avec identifiants « Rx » sans cotation (2010 nutrition).

Le format GRADE SFAR complet ne couvre donc **que 28 % des textes principaux**. Avant 2015, la structure prend d'autres formes (accord RAND/UCLA, A/B/C, jury) ou n'existe pas.

### 4.4 Règles d'extraction génériques (prototype `04_reco_markers.py`)

Prétraitement : découper chaque ligne en blocs (une cellule `<td>` = un bloc), supprimer les balises, normaliser les apostrophes et le signe −, et garder le n° de ligne source.

```text
# 1) Identifiant en début de bloc (paragraphe ou cellule), avec ou sans séparateur
RID_START = ^(?:\*\*|#+\s*|[-•●]\s*)*\s*(R\s?\d+(?:\s?\.\s?\d+){0,3})\.?\s*(?:\*\*)?\s*(?:[–\-:.)]\s*)?(?:\*\*)?\s*(?=[A-ZÀ-Ý«])
RID_ALONE = ^(?:\*\*)?\s*(R\s?\d+(?:\.\d+){0,3})\s*(?:\*\*)?$          # gabarit HAS : identifiant seul dans sa cellule
# 2) Cotation dans le bloc ou les 4 blocs suivants (jusqu'à l'identifiant suivant)
GRADE     = \bGRADE\s?[12]\s?[+\-]?(?![\d.]) | (?<![\w.])G[12]\s?[+\-]
GRADE_CELL= ^\(?\s*(?:GRADE|G)?\s*[12]\s*[+\-]?\s*\)?(…accord …)?$ | ^AE$ | ^\(?avis d'experts?\)?(…)?$
ACCORD    = accord (fort|faible|relatif|modéré) | consensus fort | accord professionnel
# 3) Ligne de tableau sans identifiant : cellule contenant une formule de force,
#    suivie d'une cellule de cotation (GRADE_CELL)
# 4) Formules de force (ordre de priorité)
faible_neg: il ne faut probablement pas | il n'est probablement pas recommandé | nous suggérons de ne pas
forte_neg : il ne faut pas | il n'est pas recommandé | il est recommandé de ne pas | nous recommandons de ne pas
faible_pos: il faut probablement | il est probablement recommandé | nous suggérons
forte_pos : il faut | il est recommandé | nous recommandons | (est|sont) recommandé(e)s
experts   : les experts (suggèrent|proposent|recommandent) | avis d'experts | AE
# 5) Contexte : dernier titre « Champ n » / « Question n » rencontré ; à défaut, champ = 1er chiffre de Rx.y
# 6) Édition : métadonnées du document (famille, année de publication corrigée, version_label)
```

Résultats sur tout le corpus :
- **2 976 blocs extraits** (2 722 ancrés sur un identifiant, 254 lignes de tableau), soit **2 355 recommandations après déduplication par identifiant**, dans 89 documents ;
- 1 897 avec un grade, 1 439 avec un accord, 1 383 avis d'experts.

Validation contre le nombre déclaré (« ont abouti à N recommandations », 45 documents) :
- concordance exacte pour 9, écart inférieur à 10 % pour 25, inférieur à 20 % pour 36 ;
- échecs : prééclampsie 2009 (76 déclarées, 0 extraite : format « affirmations » sans identifiant) ; sédation procédurale 2026 (33 déclarées, 14 extraites : identifiants collés au paragraphe précédent, `…md:927`) ; optimisation hémodynamique 2024 (24 / 14) ; hypersensibilité 2025 (70 / 100 : R1.10 est à la fois une question et une recommandation) ; anticoagulation en urgence 2024 (103 / 126).

Précision sur 30 unités tirées au hasard (graine 7) : 27/30 correctes. Erreurs : un bloc « AVIS D'EXPERTS (Accord fort) » pris comme énoncé (l'énoncé est dans le bloc précédent), et deux identifiants « R2 » et « R7 » de l'argumentaire ECBU (commentaires Delphi). Une unité correcte a en outre perdu son identifiant (format « R4.1 (pédiatrie) - »). Les **traductions anglaises** (« We suggest… ») sont bien découpées, mais leur force n'est pas reconnue : il faut ajouter les formules `we (do not )?(recommend|suggest)` et `experts suggest`.

### 4.5 Force : faire primer la cotation sur la formule

Croisement formule × cotation sur les unités extraites (`phrase_x_grade`) :
- les cas cohérents dominent : avis d'experts + AE (815), faible_pos + 2+ (284), forte_pos + 1+ (199), forte_neg + 1− (59), faible_neg + 2− (58) ;
- mais on compte **170 « forte_pos » avec GRADE 2** et 45 « forte_neg » avec GRADE 2, concentrés dans les gabarits HAS 2024-2026 (ordre de grandeur pour forte_pos : voies aériennes environ 52, résection hépatique environ 41, infections intra-abdominales environ 19, analgésie obstétricale environ 18, ALR pédiatrique environ 13).

Règle : **force = cotation si elle existe ; la formule ne sert que de repli**, et on stocke les deux. Le gabarit HAS change aussi la sémantique : « recommandation faible, qualité des preuves élevée » (`2025/RESECTION…RECOMMANDATIONS_MEL.md`, section « Formulations utilisées »).

---

## 5. Tableaux

Commande : `.venv/bin/python reports/agents/data_audit_scripts/05_tables.py`.

| Mesure | Valeur |
|---|---:|
| Tableaux HTML / Markdown à barres | **2 060** / 0 (185 documents ; 2 056 après déduplication par le loader) |
| Part des caractères du corpus dans des tableaux | 12,5 % |
| Avec en-tête `<th>` / sans en-tête | 1 049 / **1 011 (49,1 %)** |
| Contigus au tableau précédent | 467 |
| **Suite probable** (contigu, sans en-tête, même nombre de colonnes) | **325 (15,8 %)** |
| Avec `rowspan` / `colspan` | 240 / 540 |
| Cellules vides | 20,7 % (135 tableaux à plus de 50 % vides) |
| Tableaux à 1 cellule / à 1 colonne | 55 / 174 |
| Taille du texte : médiane / p90 | 607 / 2 243 caractères ; 258 tableaux > 2 000 caractères (≈ 500 tokens), aucun > 6 000 |
| Avec LaTeX ou `<math>` | 161 |
| Texte collé après `</table>` | 504 |

Typologie heuristique (`kinds`) :

| Type | Tableaux | Documents | Exemple |
|---|---:|---:|---|
| Encadré de recommandation (Rx ou formule de force + cotation) | 452 | 44 | `2018/2_RFE-CURARE-3.md:188` |
| Posologie / thérapeutique (≥ 2 doses + molécule ou « posologie, IVL, réinjection ») | 291 | 59 | `2004/2_AFAR_Antibiotherapie-probabiliste…md:281`, antibioprophylaxie V3.0 |
| Méthodologie / gradation | 162 | 54 | grilles GRADE en tête des RFE |
| Score / classification / critères | 149 | 64 | `2003/2b_AFAR_Texte-Long_.md:126` (score d'intubation difficile) |
| Formulaire / check-list | 79 | 28 | `2001/Dossier-AnesthRea-SFAR.md:322` |
| Synthèse d'études (RR, OR, n =) | 46 | 15 | `2006/2_AFAR_Prise-en-charge-initiale-des-etats-septiques…md:104` |
| Autres (descriptif, sommaires…) | 881 | 154 | sommaire en tableau : `2001/196-reco-anesth-chir-autres-2001.md:7` |

Les **algorithmes** ne sont pas des tableaux : ils apparaissent soit comme organigrammes Mermaid (161), soit comme images avec texte alternatif (1 130).

Problèmes à traiter :
1. Tableau coupé par une page : le second fragment n'a ni en-tête ni intitulé de section, et le `rowspan` est orphelin (antibioprophylaxie V3.0, lignes 876-900).
2. Encadrés de recommandation : 452 « tableaux » qui sont en réalité des énoncés. Les traiter comme des recommandations, pas comme des lignes de tableau.
3. Sommaires en tableau : bruit à exclure.
4. Entités `&gt;` / `&lt;` dans les cellules de posologie (« 1g si durée &gt; 4h », `…RESECTION…ARGUMENTAIRE…md:818`) : appliquer `html.unescape` avant toute regex.
5. Cellules de force codées « ●●● (GRADE 2) » et rangées d'intitulé en `colspan` (« Chirurgie rhino-sinusienne ») portant le contexte de la ligne.
6. Tableaux larges (258 de plus de 500 tokens) : les découper par lignes en répétant l'en-tête.

---

## 6. Recommandations

### 6.1 Normalisation avant découpage (chunking)

1. Supprimer les octets NUL (2 documents) et appliquer `html.unescape` (2 051 entités).
2. Convertir le LaTeX en Unicode pour l'index lexical (`\geq`→`≥`, `\leq`→`≤`, `_{95}`→`95`, `\text{}`), en gardant l'original pour l'affichage.
3. Unifier `µ`, la virgule décimale et `mg.kg-1`→`mg/kg`.
4. Réparer les puces et numérotations doublées (10 588 puces, 1 833 numérotations) et décoller les titres (1 707 titres collés au texte, 504 collés à `</table>`).
5. **Isoler les textes alternatifs d'images** (101 k caractères, 93 % en anglais) dans un champ `figure_alt` hors index principal, ou les marquer.
6. Garder chaque organigramme **Mermaid comme une unité atomique** (161) et en produire éventuellement une verbalisation (« si … alors … »).

### 6.2 Découpage

- **Unité « recommandation »** (89 documents, environ 2 355 unités) : énoncé + cotation + accord + champ + question + identifiant + métadonnées d'édition, sur une **ligne** propre. L'argumentaire est rattaché par l'identifiant ou la question, dans un découpage séparé (parent-enfant).
- **Documents non structurés** (environ 56 % des textes principaux) : découpage par titres Markdown, en fenêtres d'environ 400-800 tokens avec le chemin de titres en préfixe. Les documents font 14 k tokens en médiane et jusqu'à 120 k : pas de document entier dans le contexte.
- **Tableaux** :
  - fusionner les suites (contiguës, sans en-tête, même nombre de colonnes : environ 325) ;
  - propager les en-têtes et les rangées `colspan` d'intitulé ;
  - découper par groupes de lignes (Row-Group Cards) pour les 291 tableaux de posologie et les 258 grands tableaux ;
  - **reclasser les 452 encadrés** en unités de recommandation ;
  - exclure les sommaires.
- **Références** (19-26 %) : les sortir de l'index principal mais les garder dans un index secondaire. Comme 153 documents n'ont pas de titre « Références », il faut aussi un détecteur de lignes de citation (`06_references_share.py`, méthode B).
- **Doublons** : ne garder dans l'index principal qu'un seul exemplaire par famille et par contenu. Exclure les fiches et textes courts dont le contenu est inclus dans le texte long (inclusion ≥ 0,9), ou les marquer `is_derivative`. Les fiches restent utiles pour l'affichage.
- **Citations de page** : impossibles avec le Markdown actuel. Il faut tirer les PDF (`git lfs pull`) et aligner le texte page à page (pypdf), ou relancer Chandra avec séparateurs de page.

### 6.3 Métadonnées

| Champ | Source fiable | À éviter |
|---|---|---|
| `family_id` (une recommandation, toutes ses parties) | landing_url, sinon titre normalisé | sha256 |
| `publication_year` | texte : « © 20xx », « Disponible sur internet le », référence de revue, « V3.0 du … » ; puis nom de fichier | `year` de discovery seul (date de mise en ligne) |
| `doc_form` | nom de fichier + taille + langue (texte principal, court, long, fiche, algorithme, annexe, traduction) | `type` de discovery (« RFE » partout) |
| `issuer` | en-tête (SFAR, SFAR+X, HAS, ANAES, SPILF, AFU, DAS) | — |
| `grading_system` | format détecté (§ 4.3) : GRADE_SFAR, GRADE_HAS2024, A/B/C, accord seul, aucun | — |
| `status` + `supersedes[]` + `evidence` | table curée (§ 3.3), avec la ligne de la mention explicite | regex de titres non validées |
| `scope` | population (adulte, pédiatrie) et contexte (programmé, urgence, réanimation), depuis le titre | — |
| `domains` | sous-domaine discovery ; imputation **par mot entier et seulement s'il manque** | sous-chaînes (« rac », « usc », « neuro ») |
| Par unité : `rid`, `champ`, `question`, `strength` (1/2/AE, +/−), `accord`, `phrase_type` | § 4.4 | — |

### 6.4 Extraction structurée générique

1. **Règles** (§ 4.4) pour les 89 documents structurés (2015-2026 : environ 70-87 % des textes). Les valider automatiquement contre le nombre déclaré (45 documents) et signaler les documents dont l'écart dépasse 10 % (20/45) pour une reprise manuelle ou un LLM.
2. **LLM extracteur, contraint par un schéma JSON**, réservé aux formats anciens (accord seul, A/B/C, jury, narratif : environ 112 textes principaux). Il doit recevoir le texte normalisé et la grille du `grading_system` du document. Vérification : chaque énoncé extrait doit être une sous-chaîne (à normalisation près) du document source.
3. Fusionner les unités d'une même famille (texte court et texte long) par identifiant, et relier les éditions par la table de supersession curée.
4. Ajouter les formules anglaises (« we recommend/suggest », « experts suggest ») pour les 22 traductions, ou les exclure de l'extraction.

---

## 7. Écarts avec `reports/corpus_audit.md` et le README

| Affirmation | Mesuré | Verdict |
|---|---|---|
| « 264 recommandations cliniques » (README) | 264 **fichiers** après déduplication ; 176 titres, 180 familles, 202 textes principaux FR | **Trompeur** |
| « 264 documents uniques (dédupliqués SHA-256) » | Confirmé pour les doublons exacts (3) ; mais 12 quasi-doublons (J ≥ 0,5) et 37 inclusions subsistent, dont TIH ×2, AAP 2018/2021, COVID abrogée ou non | Incomplet |
| 23 185 552 caractères | 23 315 154 sur 267 fichiers (avant déduplication) ; cohérent | OK |
| 2 056 tableaux HTML, 0 tableau à barres | 2 060 avant déduplication, 2 056 après, 0 tableau à barres | OK |
| « 49,1 % (1 011/2 060) sont des continuations sans `<thead>` » | 1 011 sans en-tête : confirmé. Mais **environ 325 (16 %) seulement sont des suites** ; les autres sont des encadrés (452), des tableaux à une colonne, des formulaires | **Surinterprété** |
| 25,4 % de références | 26,4 % (sections titrées) / 19,3 % (lignes de citation) ; 153 documents sans section titrée | Ordre de grandeur OK |
| 57 sous-domaines manquants | 57 (58 dans discovery) | OK, mais l'imputation introduit des erreurs dans 102 documents |
| 18 années imputées | 18 : confirmé. Une imputation fausse (1996 au lieu de 2006), et des années discovery = date de mise en ligne non corrigées (tests viscoélastiques, AAP, AOD) | Incomplet |
| 44 éditions remplacées | 44 : confirmé ; environ 6 douteuses, au moins 2 manquées (urgences obstétricales 2010, jumeau COVID abrogé encore actif) | **Exactitude partielle** |
| Langues fr 215 / bilingual 25 / en 24 | Mesure indépendante : fr 207 / bilingue 12 / en 22 / indéterminée 26 ; plus 1 050 textes alternatifs anglais dans les documents FR | Cohérent, méthode-dépendant |
| « 1 document explicitement abrogé » | Vrai pour le nom de fichier, mais son jumeau (J = 0,94) reste actif | **Piège non traité** |
| Piège « encadré allergie séparé » | Spécifique à l'antibioprophylaxie ; non vérifié ici. Version générique : la rangée `colspan` d'intitulé et l'en-tête d'un tableau coupé sont séparés de leurs lignes | Hors périmètre |
| Non mentionné : PDF absents | `pdfs/` = 267 pointeurs LFS ; sha256 de discovery = oid LFS (266/267) | **Absent du README** |
| Non mentionné : pas de marqueurs de page | Aucun séparateur de page dans le `.md` ni le `.html` | **Absent** |
| Non mentionné : formule de force ≠ grade (gabarit HAS 2024+) | 170 « il est recommandé » cotés GRADE 2 | **Absent** |
