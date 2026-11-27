# D1 — Audit des unités et des ordres de grandeur des doses dans le corpus (2026-11-27)

Pourquoi : principe 7 (sécurité clinique). La RFE arrêt cardiaque 2006 donne, chez l'enfant, l'adrénaline à « 10 mg/kg » IV et « 100 mg/kg » intratrachéale, soit 1 000 fois la dose usuelle. Ce rapport cherche systématiquement ce type de corruption dans les 268 fichiers du corpus (267 Markdown Chandra et l'overlay ABP V3.1), puis vérifie les candidats dans les PDF.

Annexes : `reports/agents/D1_annexes/`. Liste consolidée pour les médecins : `reports/A_VALIDER_MEDECINS.md`.

## Résumé

- **Aucune erreur de conversion OCR n'a été trouvée** parmi les candidats vérifiés. Chandra lit l'image des pages et reproduit fidèlement le PDF, y compris les µ que la couche texte des PDF perd.
- **Le cas de l'adrénaline pédiatrique est une erreur de l'article publié.** On lit bien « 10 mg/kg » et « 100 mg/kg » sur la page 11 du PDF. Un erratum officiel (AFAR 2008;27:273), page 13 du même PDF, rétablit les µg. Chandra a converti les deux pages fidèlement, mais dans deux chunks différents : dans `index/tas_v5`, les chunks 30399 et 30400 (document « en vigueur ») portent toujours les mg.
- **3 erreurs confirmées dans le PDF, toutes du même type : texte d'origine corrigé par un erratum officiel inclus dans le même PDF.** Il s'agit de deux doses (adrénaline pédiatrique IV/IO et intratrachéale, facteur 1 000) et d'une cotation (MTEV 2011, « (2−) » au lieu de « (2+) »). Elles sont proposées dans `errata_proposed.json` et ne sont pas appliquées.
- **4 doutes sur le texte d'origine**, à faire trancher par un médecin. Il n'y a là aucune erreur de conversion :
  - concentration de morphine « 20 µg/mL » (ORL 2014), alors que la littérature parle plutôt de ng/mL ;
  - acide tranexamique « 1 mg/kg pendant 10 heures » (AAP 2001), sans « /h » ;
  - et deux points déjà signalés par E1 : le paracétamol avant 10 kg et la diurèse du brûlé.
- **Constat systémique.** La couche texte des PDF Elsevier (AFAR 2003-2011) rend « µ » par « m » : 18 doses en µg/kg deviennent des mg dans le seul PDF sédation pédiatrique 2007. D'autres PDF codent µ dans la police Symbol (U+F06D). Le Markdown Chandra est juste dans tous les cas vérifiés. Toute extraction future par pypdf ou pdftotext réintroduirait donc des erreurs d'un facteur 1 000 sans bruit.

## 1. Méthode

Le script `D1_annexes/detect_doses.py` est en lecture seule et déterministe (sorties `candidates.tsv`, `candidates_summary.json`, `doses_extracted.tsv`).

- **Normalisation.**
  - Le LaTeX inline (`$\mu\text{g}$`) et les balises `<math>` sont aplatis : `\mu` → µ, `\geq` → ≥, `kg^{-1}` → `kg^-1`.
  - Les entités HTML sont décodées.
  - Chaque ligne `<tr>` de tableau devient une ligne de texte, cellules séparées par « | ».
- **Extraction des doses.** On retient un nombre (ou une fourchette) suivi de g, mg, µg, mcg ou ng, avec « /kg » et une unité de temps facultatifs. Toutes les graphies sont reconnues : `/kg`, `kg-1`, `·kg^-1`, `par kg`, `/min`, `min-1`, `par heure`.
  - Les concentrations sont exclues (masse suivie de /mL, /L, mL⁻¹).
  - Les doses par jour sont exclues.
- **Rattachement au médicament.**
  - Si le médicament est nommé juste après la dose (« 2 µg/kg de rémifentanil », « (sufentanil) »), c'est lui qui est retenu.
  - Sinon, on prend le médicament le plus proche qui précède la dose, dans les 160 caractères de la même ligne ou de la même ligne de tableau.
  - Au total, 1 175 doses sont rattachées, dans 106 documents : 302 pour des médicaments dosés en µg, 873 pour des médicaments dosés en mg.
- **Lexique de 59 médicaments** (`DRUGS`), dont 27 habituellement dosés en microgrammes : adrénaline, noradrénaline, fentanyl, sufentanil, rémifentanil, alfentanil, clonidine, dexmédétomidine, atropine, isoprénaline, dobutamine, dopamine, phényléphrine, glycopyrronium, naloxone, desmopressine, flumazénil, carbétocine, sulprostone, misoprostol, milrinone, lévosimendan, salbutamol, néostigmine, dropéridol, buprénorphine, trinitrine.
  - Les plages plausibles sont larges : elles couvrent adulte, enfant et nouveau-né, ainsi que toutes les voies, y compris intrathécale et intratrachéale. Elles sont données par type de dose : absolue, /kg, /kg/min, /kg/h, /min, /h.
  - **Ces plages viennent de mes connaissances pharmacologiques, pas du corpus**, et doivent être relues par un médecin avant tout usage en production.
  - Aucune règle ne dépend d'une question d'évaluation (principe 1).

### Détecteurs et nombre de candidats

| Détecteur | Ce qu'il cherche | Candidats | Documents |
|---|---|---:|---:|
| D1 plausibilité | dose hors de la plage plausible d'un facteur ≥ 10 (connaissances) | 17 | 14 |
| D2 écart au corpus | dose à ≥ 100× de la médiane du corpus pour le même médicament et le même type de dose (groupes ≥ 5 mentions) | 15 | 9 |
| D3 même nombre ×1000 | dans un même document, même médicament, même nombre écrit une fois en mg et une fois en µg (ou g/mg) | 4 | 1 |
| D4 µ absent | document qui posologie un médicament « µg » sans contenir aucun µ / mcg / microgramme | 5 | 5 |
| D5 zéro initial | « 05 mg », « 005 mg/kg » (virgule perdue) | 0 | 0 |
| D6 virgule → espace | « 0 5 mg » | 0 | 0 |
| D7 tiret perdu | « 5 10 mg » (deux nombres croissants avant une unité, hors séparateur de milliers) | 1 | 1 |
| D8 unité dans la cellule suivante | « 10 \| mg/kg » | 0 | 0 |
| D9 signe de police Symbol / comparateur cassé | « ³ 5 », « £ 5 », « > = 5 », caractère de remplacement | 2 | 1 |
| D10 débit sans unité de temps | médicament perfusé (noradrénaline, dobutamine, dopamine, isoprénaline) dosé en µg/kg sans /min ni /h | 0 | 0 |
| D11 graphie non standard du µg (informatif) | mcg, gamma, ng/kg | 21 | 12 |
| D12 mg/kg/min | unité exceptionnelle en anesthésie, souvent un µ perdu | 0 | 0 |
| D13 unité en en-tête de tableau | cellules sans unité dont l'en-tête porte « (µg/kg) » ; 17 doses testées | 0 | 0 |

La répartition par document est dans `candidates_summary.json` (`per_detector_doc`). On ne trouve aucun résidu de police Symbol (U+F0xx), aucun « ³ » ou « £ » devant un chiffre et aucun µ grec U+03BC dans les Markdown. Seul µ U+00B5 apparaît, dans 87 documents.

### Rappel synthétique (`recall_test.py`, `recall_test.txt`)

Méthode : sur les doses réelles du corpus, on simule l'erreur, puis on vérifie si D1 l'aurait signalée.

| Erreur simulée | Doses testables | Détectées |
|---|---:|---:|
| µg → mg (×1 000) | 238 | 203 (85 %) |
| mg → µg (÷1 000) | 775 | 685 (88 %) |
| mg → g (×1 000) | 775 | 738 (95 %) |
| virgule perdue 0,5 → 5 (×10) | 202 | **0 (0 %)** |

Les erreurs d'un facteur 1 000 sont bien couvertes, mais seulement pour les doses rattachées à un médicament du lexique. Les erreurs d'un facteur 10 ne sont pas détectables avec ces plages larges, et c'est voulu : un seuil à 3× donne 13 signalements, tous des faux positifs à la relecture (doses cumulées, doses totales d'études, posologies quotidiennes).

## 2. Vérification dans les PDF

- **Accès.** `git lfs` 3.7.1 est disponible. Chaque PDF a été obtenu par `git -C data/sfar_recommendations show HEAD:<pointeur> | git lfs smudge`, dans un dossier neuf du répertoire temporaire de session. Rien n'a été écrit dans `data/` hors du cache LFS interne de git. Les fichiers sont lus avec `.venv/bin/python -I` (pypdf) et rendus par `pdftoppm` à 250-300 dpi pour la lecture visuelle.
- **Correspondance.** `output/chandra/<année>/<nom>/<nom>.md` correspond à `output/pdfs/<année>/<nom>.pdf`. Le hash est le suffixe du `doc_id` de l'index.
- **15 PDF ont été téléchargés, uniquement des candidats** :
  - arrêt cardiaque 2006 ;
  - AAP 2001 FR et EN ;
  - ORL 2014 ;
  - blessé vertébro-médullaire 2003 ;
  - sédation pédiatrique 2007 ;
  - brûlé 2019, texte long et fiches ;
  - NVPO 2007 ;
  - PUROL 2013 ;
  - voies aériennes de l'enfant 2018 ;
  - TSM 2020 et ses fiches ;
  - MTEV 2011 ;
  - tableaux douleur postopératoire 2016.
- **Contrôle complémentaire** (`tokdiff.py`, sortie `verif/tokdiff_md_vs_pdf_textlayer.txt`) : les jetons « nombre + unité » du Markdown absents de la couche texte du PDF. Résultat :
  - 0 écart pour 9 documents ;
  - les écarts restants s'expliquent tous par un µ que la couche texte rend « m » (arrêt cardiaque p. 13, sédation pédiatrique 2007) ou par une figure : sugammadex 16 mg/kg (voies aériennes 2018) ;
  - exception : 16 jetons des tableaux de la douleur postopératoire 2016, absents de la couche texte (pages de tableaux mal extraites par pypdf). Leurs valeurs sont plausibles, mais **ils ne sont pas vérifiés**.

## 3. Constats, classés par danger clinique

Les catégories :
- **E-orig+erratum** : erreur du texte publié, corrigée par un erratum officiel ;
- **doute-orig** : le PDF dit la même chose que le Markdown, mais le texte d'origine est douteux ;
- **non-erreur** ;
- **FP** : faux positif du détecteur.

| # | Document (index `tas_v5`) | Passage (court) | Détecteurs | Vérification | Classement |
|---|---|---|---|---|---|
| 1 | Arrêt cardiaque 2006 (`2006_2_AFAR_Prise-en-charge-de-larret-cardiaque-1_c70196`, en vigueur), l. 637, chunk 30400 | adrénaline enfant « 10 mg/kg en intraveineux et intraosseux » | D1, D2, D3 | PDF p. 11 visuel : « 10 mg/kg » imprimé ; figure 5, même page : « 0,01 mg/kg » ; erratum p. 13 : « 10 µg/kg » | **E-orig+erratum**, ×1 000, enfant, vasopresseur. Proposé D1-E2 |
| 2 | idem, l. 629, chunk 30399 | « adrénaline intratrachéale est de 100 mg/kg » | D1, D2, D3 | PDF p. 11 visuel « 100 mg/kg » ; erratum p. 13 « 100 µg/kg » | **E-orig+erratum**, ×1 000. Proposé D1-E1 |
| 3 | ORL 2014 (`2014_Recommandation_antalgique_post_amygdalectomie_2014_TC2_9ae464`), l. 1131 | dépression respiratoire de l'enfant « pour des concentrations sanguines supérieures à 20 µg/mL » (morphine) | relecture des écarts PDF | PDF p. 26 : µ en police Symbol (U+F06D), donc bien « µg/mL » | **doute-orig** : les seuils publiés sont plutôt de l'ordre de 20 ng/mL (×1 000). C'est une concentration, pas une dose : risque modéré |
| 4 | AAP 2001 FR et EN (`2001_2a_SFAR-Francais_9076ff`, `…2b_SFAR-Anglais_7075ff`, remplacés), l. 228 | acide tranexamique « 10 mg·kg⁻¹, suivi d'une perfusion continue de 1 mg·kg⁻¹ pendant 10 heures » | recherche d'unité de temps manquante | PDF p. 16 FR et EN identiques (pas de « /h ») | **doute-orig** : le schéma habituel est 1 mg/kg/h. Lu littéralement, c'est 10 fois moins. Document remplacé : risque faible |
| 5 | MTEV 2011 (`2011_…thromboembolique-veineuse-postop_da2bda`, remplacé), l. 212 | prophylaxie prolongée « jusqu'à l'appui plantaire (2–) » | recherche des erratums inclus | PDF p. 4 visuel « (2−) » ; erratum p. 6 « (2+) » | **E-orig+erratum** (cotation, pas une dose). Proposé D1-E3 |
| 6 | ORL 2014, tableau l. 852 (signalé par E1) | paracétamol « Enfants < 10 kg : 7,5 mg/kg x 4 / j » pour IV, IR et per os | — | PDF p. 19 identique | **doute-orig** (E1) : la réduction à 7,5 mg/kg vaut d'habitude pour la voie IV |
| 7 | Brûlé 2019, texte long l. 208 et fiches l. 344 (signalé par E1) | diurèse « 0,5 et 1 mL/kg/h » (adulte, texte long) contre « 0,5 et 1,5 mL/Kg/h » (fiche) | — | PDF texte long p. 14, fiches p. 4 et p. 5 : identiques au Markdown | **doute-orig** (cohérence interne) |
| 8 | Blessé vertébro-médullaire 2003, l. 112 | naloxone « 5,4 mg/kg … puis 4 mg/kg par heure » | D1, D4 | PDF p. 4, couche texte identique | **non-erreur** : protocole NASCIS II, réellement en mg/kg |
| 9 | Sédation pédiatrique 2007, l. 314 | dose cumulée « midazolam supérieure à 60 mg/kg », « fentanyl supérieure à 1,5 mg/kg » | D1, D2 | PDF p. 6 visuel : mg/kg | **non-erreur** : seuils de doses cumulées de sevrage, cohérents avec la littérature |
| 10 | Allergie 2011 l. 944 ; anaphylaxie 2025 l. 1667 et 3498 ; optimisation hémodynamique 2024 l. 775 et 906 | titration d'adrénaline 10 à 20 µg ; bolus de noradrénaline 5 à 10 µg | D2 | lecture | **non-erreur** : la médiane du corpus est tirée vers le haut par les doses absolues de 1 mg |
| 11 | Aides cognitives 2026 l. 282 ; urgence vitale 2026 l. 1497 | « NORADRENALINE (8 mg=4 ml) » | D1 | lecture | **non-erreur** (contenu d'ampoule) |
| 12 | 5 documents D4 : blessé 2003, PUROL 2013, voies aériennes enfant 2018, TSM 2020 et ses fiches | pas de µ ; dropéridol 0,625-1,25 mg, salbutamol nébulisé 2,5 et 5 mg, noradrénaline < 2 mg/h | D4 | `tokdiff` : 0 écart avec le PDF (sauf la figure sugammadex) | **non-erreur** : doses réellement en mg |
| 13 | Douleur postopératoire 2016, tableaux l. 3058 | « 1 ou 2 20 ml bolus » | D7 | lecture | **non-erreur** (« 1 ou 2 bolus de 20 ml ») |
| 14 | Résection hépatique 2025, l. 965 | « >= 1 » | D9 | lecture | **non-erreur** (comparateur ASCII) |
| 15 | 10 passages | blocs périmédullaires 2006 l. 893 (fentanyl IT 10 µg rattaché à la ropivacaïne) ; allergie 2011 l. 956 (terlipressine) ; annexe DCALR 2013 l. 5391 ; intubation réanimation 2016 l. 345 (sugammadex) ; prééclampsie 2020 l. 365 (poids de naissance 2500 g) ; programme 2022 l. 532 ; RPP-FHS 2022 l. 506 (amoxicilline 2 g) ; sepsis 2025 l. 455 ; blocs moteurs (tube de 5 g) | D1, D2 | lecture | **FP** de rattachement ou de contexte |
| 16 | Annexe DCALR 2013 l. 4838 | clonidine « 0.06 gamma/kg/h à 0.86 gamma/kg/h » | D11 | lecture | **non-erreur** (gamma = µg, usage ancien). Un LLM pourrait le mal interpréter ; sans gravité ici, car tableau de littérature |

Bilan :

- **Confirmées dans le PDF** :
  - 3 erreurs, toutes « E-orig+erratum » : 2 doses et 1 cotation ;
  - 0 erreur de conversion Chandra, 0 erreur seulement dans la couche texte, 0 candidat non vérifiable parmi ceux qui comptent cliniquement.
- **Doutes sur le texte d'origine** : 4, à trancher par un médecin.
- **Non vérifiés** : les 16 jetons de tableau de la douleur postopératoire 2016 (plausibles).

## 4. Constat systémique : la couche texte des PDF n'est pas fiable pour µ

- **PDF Elsevier AFAR** (police GillSans/Times). Les µ s'affichent correctement à l'écran, mais pypdf et pdftotext les extraient comme « m ». C'est le cas de la sédation pédiatrique 2007 (p. 3 : « 100 à 330 µg/kg par heure » affiché, `mg/kg` extrait) et de l'erratum de l'arrêt cardiaque (p. 13).
- **Autres PDF** (ORL 2014) : µ est codé U+F06D (police Symbol), que pypdf rend tel quel.
- **Conséquence 1** : Chandra (OCR visuel) est la bonne source. Une recherche du type « le PDF dit mg » n'est valable qu'après examen visuel de la page.
- **Conséquence 2** : ne jamais remplacer le Markdown Chandra par une extraction de couche texte, ni s'en servir comme référence automatique de fidélité, sans traitement des µ (U+F06D → µ ; « m » devant g/kg à confirmer visuellement).
- **Le pipeline peut aussi corrompre µ.** R1 (C3) l'a montré : `tas_v4` transformait µg en « mug » (131 occurrences). C'est corrigé dans `tas_v5` et surveillé par le compteur `fidelity` de `scripts/ingestion_structural_checks.py`. Ce compteur doit rester dans les contrôles permanents.

## 5. Mécanisme de correction proposé (non appliqué)

- **Erreurs confirmées** (`errata_proposed.json`, 3 entrées) : passer par l'overlay existant. `loader.py` lit déjà `data/corpus_updates/`, et `ERRATA.md` journalise chaque correction avec la page PDF.
  - Chaque entrée donne :
    - le chemin du document et son SHA-256 au moment de la vérification ;
    - une chaîne d'origine unique (vérifiée) et la chaîne corrigée ;
    - la preuve, le PDF, son SHA-256 et ses pages ;
    - le statut de vérification.
  - Il faut une copie corrigée du Markdown dans l'overlay, comme pour l'ABP, puisque l'overlay remplace aujourd'hui des documents entiers. À défaut, un mécanisme « patch » appliquerait des remplacements exacts au chargement. Ce second choix est plus léger et garde la traçabilité, mais il touche à `src/rag_sfar/ingestion/` : décision à prendre avec l'agent d'ingestion.
  - Dans les deux cas, garder l'ancienne chaîne dans les métadonnées du chunk (« corrigé d'après l'erratum AFAR 2008;27:273 ») pour que la citation reste honnête vis-à-vis du PDF.
- **Mécanisme générique complémentaire.** 2 documents du corpus contiennent un erratum officiel à la fin de leur PDF : arrêt cardiaque 2006 et MTEV 2011. Ces sections commencent par « Erratum » ou « Une erreur s'est glissée ». Le loader pourrait les détecter de façon générique (structure des publications AFAR, pas une question du benchmark) et rattacher le chunk d'erratum à tous les chunks du document. Ainsi, quand le passage fautif est retrouvé, la correction l'accompagne.

## 6. Passages dangereux non vérifiés : options (décision à vous)

Aujourd'hui, il ne reste aucun passage de dose dangereux non vérifié. La question se reposera à chaque nouveau signalement : nouveau corpus, nouveaux détecteurs, doutes « d'origine » comme la morphine 20 µg/mL. Options :

1. **Avertissement visible dans le chunk** (préfixe ou champ d'en-tête : « ⚠ dose signalée, en attente de vérification médicale ; voir … »).
   - Pour : le passage reste retrouvable, le LLM et le lecteur voient le doute, et c'est transparent pour le jury.
   - Contre : un LLM peut ignorer l'avertissement ou recopier la dose. Il faut un test qui le vérifie.
2. **Exclusion de la citation** : le chunk reste indexé, mais la génération ne peut pas le citer ni en reprendre la dose.
   - Pour : c'est le plus sûr.
   - Contre : on perd du contenu. Cela peut provoquer des abstentions ou pousser vers une source plus ancienne ou moins pertinente, et le masquage est invisible pour l'utilisateur.
3. **Correction provisoire sans preuve PDF** : à proscrire, car un chiffre non vérifié deviendrait une source.
4. **Garde-fou de dose à la sortie.** Les plages de `DRUGS`, une fois validées par un médecin, servent à vérifier les doses de la réponse générée. Un écart ≥ 10× déclenche un avertissement ou une abstention.
   - Pour : c'est générique et cela attrape aussi les erreurs du LLM.
   - Contre : il faut valider et maintenir un lexique, et les plages larges ratent les erreurs ×10.

**Ma recommandation** :
- pour les erreurs confirmées, l'overlay (§5) ;
- pour les signalements non vérifiés, l'option 1 combinée au rattachement générique des erratums (§5) ;
- l'option 4 comme couche de sécurité ensuite, une fois le lexique validé.

Je déconseille l'exclusion (option 2) sauf pour un écart ≥ 100× sur un médicament à marge étroite (catécholamines, opioïdes, curares) chez l'enfant, le temps que le médecin tranche.

## 7. Limites

- Seules les doses **rattachées à l'un des 59 médicaments** sont testées par D1 et D2 (1 175 doses). Les médicaments absents du lexique (antibiotiques autres que céfazoline, gentamicine et vancomycine ; HBPM en UI ; insuline ; produits sanguins) ne sont couverts que par les détecteurs génériques D5 à D12.
- Les erreurs **×10** (virgule perdue) ne sont pas détectées par les plages (rappel synthétique 0 %). Les détecteurs typographiques D5 et D6 ne trouvent rien, mais ils ne voient pas une virgule disparue sans trace.
- La perte de **≥/≤/</>** n'est détectable que par ses résidus typographiques (D9). Un signe disparu sans trace reste invisible sans comparaison au PDF, faite ici seulement pour les 15 PDF téléchargés.
- Le rattachement au médicament par proximité produit des faux positifs (§3, ligne 15) et peut rater une dose dont le médicament est loin (tableau dont le nom n'est que dans le titre).
- Les **figures** (algorithmes en image) ne sont vérifiées que par leur texte alternatif ou leur Mermaid Chandra.
- Une **erreur de l'article d'origine sans erratum** n'apparaît que si elle sort des plages. C'est le cas de la morphine 20 µg/mL (repérée à la relecture), pas d'une erreur ×2 ou ×5.
- Les plages de doses sont **mes connaissances, non validées par un médecin**.
