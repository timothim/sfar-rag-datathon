# À valider par un médecin : liste consolidée (2026-11-27)

Ce document rassemble tous les points que les rapports des agents ont laissés « à vérifier par un médecin ». Ils sont groupés par nature et classés par importance dans chaque groupe. Chaque point donne le document, le passage (cité au plus court), ce qui est douteux et le rapport d'origine.

**Comment répondre** : pour chaque point, indiquer *confirmé* / *à corriger* (avec la bonne valeur) / *sans objet*, puis le nom du relecteur. Aucune correction n'est appliquée au corpus sans cette validation, sauf les corrections déjà faites dans l'overlay antibioprophylaxie (section D), qui sont à contresigner.

Abréviations :
- « l. » : ligne du Markdown `data/sfar_recommendations/output/chandra/<année>/<nom>/<nom>.md` ;
- « p. » : page du PDF source ;
- « en vigueur » : `is_latest_edition = 1` dans l'index `tas_v5`.

---

## A. Doses et valeurs chiffrées (risque immédiat)

### A1. Adrénaline pédiatrique, arrêt cardiaque 2006 : facteur 1 000 (priorité maximale)

- **Document** : *Prise en charge de l'arrêt cardiaque* (SFAR/SRLF, AFAR 2007;26:1008-19), dossier `2006/2_AFAR_Prise-en-charge-de-larret-cardiaque-1`. Il est **en vigueur** dans l'index.
- **Passages** :
  - l. 637 : « L'adrénaline doit être administrée chez l'enfant à la dose de 10 mg/kg en intraveineux et intraosseux » ;
  - l. 629 : « adrénaline intratrachéale est de 100 mg/kg ».
- **Ce qui est douteux** :
  - L'article publié porte bien « mg/kg » (PDF p. 11). La figure 5 de la même page donne « 0,01 mg/kg ».
  - L'**erratum officiel** (AFAR 2008;27:273), reproduit p. 13 du même PDF, demande de lire « µg » et non mg : 10 µg/kg IV/IO, 100 µg/kg intratrachéal.
  - Dans l'index, l'erratum est dans un autre chunk que les passages fautifs. Un RAG peut donc citer « 10 mg/kg » avec sa source.
- **Proposition** : corriger les deux passages en µg/kg via l'overlay (`reports/agents/D1_annexes/errata_proposed.json`, D1-E1 et D1-E2).
- **À valider** : la correction, et la question de savoir si ce texte de 2006 doit rester « en vigueur » (voir B1).
- **Origine** : E1 (`reports/agents/E1_genprobe.md`, « Constats sur le corpus »), vérifié par D1 (`reports/agents/D1_audit_doses.md`).

### A2. Morphine chez l'enfant : seuil de concentration « 20 µg/mL » (ORL 2014)

- **Document** : *Recommandations antalgiques en chirurgie ORL* (2014), `unknown/Recommandation_antalgique_post_amygdalectomie_2014_TC2`, l. 1131 (PDF p. 26).
- **Passage** : la dépression respiratoire du jeune enfant « survient pour des concentrations sanguines supérieures à 20 µg/mL ».
- **Ce qui est douteux** : le PDF dit bien µg/mL, donc le texte est fidèle. Mais les seuils publiés pour la morphine sont plutôt de l'ordre de 20 **ng**/mL, soit 1 000 fois moins. Il s'agit peut-être d'une erreur du texte d'origine. C'est une concentration et non une dose : risque modéré.
- **Origine** : D1.

### A3. Paracétamol chez l'enfant de moins de 10 kg (ORL 2014)

- **Document** : même document qu'A2, tableau des antalgiques, l. 852 (PDF p. 19).
- **Passage** : « Enfants < 10 kg : 7,5 mg/kg x 4 / j », sur une ligne qui couvre les voies IV, IR et per os.
- **Ce qui est douteux** : en pratique, la dose réduite de 7,5 mg/kg vaut pour la voie IV ; le tableau l'applique aux trois voies. Le PDF dit la même chose : ce n'est pas une erreur de conversion.
- **Origine** : E1, vérifié dans le PDF par D1.

### A4. Brûlé grave 2019 : cible de diurèse

- **Documents** : *RPP prise en charge du brûlé grave* 2019, texte long, l. 208 (PDF p. 14) ; *fiches de synthèse*, l. 344 (PDF p. 5).
- **Passages** :
  - texte long : « entre 0,5 et 1 mL/kg/h » (brûlures thermiques de l'adulte) ;
  - fiche : « Diurèse horaire : entre 0,5 et 1,5 mL/Kg/h ».
- **Ce qui est douteux** : la cible diffère entre le texte long et la fiche. Il faut savoir si la fiche vise l'enfant et laquelle fait foi. Les deux PDF sont fidèlement convertis.
- **Origine** : E1, vérifié par D1.

### A5. Acide tranexamique, AAP 2001 : unité de temps absente

- **Document** : conférence d'experts *Agents antiplaquettaires et période périopératoire* 2001, FR (`unknown/2a_SFAR-Francais`, l. 228) et EN (`unknown/2b_SFAR-Anglais`). PDF p. 16 des deux versions. Le document est **remplacé** par la RFE 2018.
- **Passage** : « 10 mg·kg⁻¹, suivi d'une perfusion continue de 1 mg·kg⁻¹ pendant 10 heures ».
- **Ce qui est douteux** : le schéma habituel est 1 mg/kg/**h**. Lu littéralement, le texte donne une dose dix fois plus faible. Le défaut est dans le texte d'origine, pas dans la conversion. Risque faible, car le document n'est plus en vigueur.
- **Origine** : D1.

### A6. Cotation d'une recommandation, MTEV 2011 (erratum officiel)

- **Document** : *Prévention de la maladie thromboembolique veineuse postopératoire* 2011 (texte court), l. 212 (PDF p. 4). Le document est **remplacé** par la RFE 2024.
- **Passage** : prophylaxie prolongée « jusqu'à l'appui plantaire (2–) ».
- **Ce qui est douteux** : l'erratum officiel, reproduit p. 6 du même PDF, donne « (2+) ». Le sens est inversé : suggestion de ne pas faire au lieu de suggestion de faire.
- **Proposition** : D1-E3 dans `errata_proposed.json`.
- **Origine** : D1.

### A7. Plages de doses plausibles utilisées par l'audit

- **Fichier** : `reports/agents/D1_annexes/detect_doses.py`, dictionnaire `DRUGS` : 59 médicaments, plages par type de dose.
- **Ce qui est à valider** : ces plages viennent des connaissances de l'agent, pas du corpus. Elles ne doivent servir de garde-fou dans le RAG (vérification des doses d'une réponse) qu'après relecture médicale.
- **Origine** : D1.

---

## B. Statut des éditions : texte ancien présenté comme en vigueur, ou remplacement partiel

### B1. Arrêt cardiaque 2006, en vigueur alors que des textes plus récents le contredisent

- **Constat** : le texte de 2006, en vigueur dans l'index, recommande pour la femme enceinte d'incliner l'utérus de 15° et une extraction après la 25e semaine. La RPP *Urgences obstétricales en médecine d'urgence* 2022 indique que la latéralisation réduit l'efficacité du massage. Elle demande un déplacement manuel continu de l'utérus et une césarienne envisagée à 4 minutes au-delà de 20 SA.
- **À décider** :
  - le texte de 2006 doit-il rester « en vigueur » ?
  - sinon, faut-il le marquer comme partiellement remplacé, chapitre par chapitre ?
- **Origine** : E1 (« Corrections de la seconde relecture », gp-pop-07 ; « Constats sur le corpus »).

### B2. SDRA 2018 et sepsis 2025 : manœuvres de recrutement

- **Constat** : la RFE sepsis 2025 (R31) recommande de ne pas utiliser les manœuvres de recrutement dans le SDRA modéré à sévère. La RFE SDRA 2018, toujours en vigueur, est d'une autre lignée et ne le dit pas.
- **À décider** : faut-il un remplacement partiel, ou une note visible sur les chunks concernés ?
- **Origine** : E1.

### B3. Transfusion de plasma 2012 et plasmas lyophilisés (PLYO) 2020

- **Constat** : il y a une tension entre les deux textes, tous deux en vigueur (question gp-two-06).
- **Origine** : E1.

### B4. Recommandations AVK (HAS 2008) : remplacement partiel

- **Constat** :
  - le chapitre 4 (relais pour chirurgie programmée) est couvert par la RFE 2026 *Gestion des anticoagulants pour une procédure invasive programmée* ;
  - le chapitre 3 (hémorragies sous AVK) est couvert par la RFE 2024 *Anticoagulation en contexte d'urgence* ;
  - le chapitre 2 (surdosage asymptomatique) n'a **peut-être pas d'équivalent plus récent** dans le corpus.
- **Statut actuel** : remplacé, avec une note « à valider par un médecin » (`loader.SUPERSESSION_REVIEW_NOTES`).
- **Origine** : R1 (`reports/agents/R1_revue_ingestion.md`, M2), B2 (`reports/agents/B2_ingestion.md`, § 6 et corrections M2), audit des données (`reports/agents/audit_donnees.md`, § 3.2).

### B5. Urgences obstétricales extrahospitalières 2010 et RPP 2022 : remplacement partiel

- **Constat** : la RPP 2022 cite explicitement la mise à jour du texte de 2010, mais ne reprend pas les hémorragies des 2e et 3e trimestres, les transferts in utero ni le recours au SAMU (chapitres 1, 3 et 8 de 2010).
- **Statut actuel** : 2010 est marqué remplacé, avec une note.
- **À décider** : faut-il garder ces chapitres « en vigueur » ?
- **Origine** : R1 (§ 3), B2 (§ 6), audit des données (§ 3.2).

### B6. Quatre documents sepsis 2004-2006 rattachés à la recommandation HAS sepsis 2025

- **Documents** : antibiothérapie probabiliste 2004, sepsis hémodynamique 2005 (×2), états septiques graves 2006.
- **Constat** : ils sont marqués remplacés, alors que l'émetteur et le périmètre diffèrent. L'audit les juge douteux ; B2 les a laissés en l'état.
- **Origine** : audit des données (§ 3.2, conclusion 6), B2 (§ 6).

### B7. Guideline britannique DAS (BJA 2015) « remplacée » par la RFE SFAR 2026 voies aériennes

- **Constat** : l'émetteur diffère ; le remplacement est douteux.
- **Origine** : audit des données (§ 3.2), B2 (§ 6).

### B8. RPP COVID avril 2022 « finale sans marque », passée en « abrogée »

- **Constat** : c'est une quasi-copie (Jaccard 0,94) du fichier marqué « Abrogées le 01/07/2023 ». Il faut confirmer que tout le contenu est bien abrogé.
- **Origine** : B2 (§ 6), audit des données (§ 3.2), R1 (§ 3).

### B9. Doublons dont les deux copies sont « en vigueur » (faible)

- **Documents** : TIH 2019 (deux fichiers identiques) ; AAP en urgence 2018 et sa copie datée « 2021 ».
- **Constat** : il n'y a pas d'enjeu clinique, seulement de la redondance. Il faut confirmer qu'il s'agit bien du même texte.
- **Origine** : R1 (m3), audit des données (§ 3.2).

---

## C. Corrections proposées, non appliquées

Fichier : `reports/agents/D1_annexes/errata_proposed.json`. Les trois entrées ont été vérifiées dans le PDF ; chacune corrige un texte publié d'après un erratum officiel inclus dans le même PDF.

| Id | Document | Avant → après | Voir |
|---|---|---|---|
| D1-E1 | Arrêt cardiaque 2006, l. 629 | 100 mg/kg → 100 µg/kg (adrénaline intratrachéale, enfant) | A1 |
| D1-E2 | Arrêt cardiaque 2006, l. 637 | 10 mg/kg → 10 µg/kg (adrénaline IV/IO, enfant) | A1 |
| D1-E3 | MTEV 2011, l. 212 | (2–) → (2+) | A6 |

Toujours non validées par un médecin : en attente d'une décision de l'utilisateur sur leur application.

---

## D. Corrections déjà appliquées dans l'overlay antibioprophylaxie V3.1 (à contresigner)

Journal complet : `data/corpus_updates/ERRATA.md`. Source : PDF officiel V3.1 (122 p.).

1. **p. 81, vésicule biliaire (adulte)** : la cholécystectomie élective par laparoscopie chez les patients à faible risque est placée sur sa propre ligne, avec « PAS D'ANTIBIOPROPHYLAXIE » et « (GRADE 2) ». Elle était fusionnée avec la ligne haut risque céfazoline / céfuroxime.
2. **p. 87, encadré allergie (urologie, adulte)** : « Si céfotaxime » → « Si **céfoxitine** : gentamicine 6 à 7 mg/kg IVL + métronidazole 1 g IVL ». C'est une molécule qui change.
3. **p. 113, vésicule biliaire (pédiatrie)** : même séparation de ligne qu'en 1.
   - **Point à vérifier** : le journal donne « ●●● (Avis d'experts) » pour la ligne corrigée, alors que le texte du PDF cité dans le même journal donne « ◉◎◎ (Avis d'experts) ». Il faut confirmer le niveau de cotation affiché.
4. **Coquilles (erratum 2)** : « Lithotritie » (p. 89) ; « Amygdalectomie », « Adéno-amygdalectomie » (p. 96).
5. **Passe systématique (erratum 3)** : 23 formes corrigées (51 occurrences), dont **« céfuoxime » → « céfuroxime » (19 occurrences)**. Deux formulations de l'overlay sont absentes du PDF et restent à relire : « discutée collectivement » et « conformité ».

Origine : A2 (`reports/agents/A2_revue_neon_v31.md`, § 2.4), A1 et B2 (`reports/agents/B2_ingestion.md`, « Coquilles de l'overlay »).

---

## E. Jeux de questions internes à relire

Ce sont des outils de développement, synthétiques et non validés médicalement. Ils ne constituent pas un benchmark : le benchmark de référence est celui des experts. Les relire avec les colonnes prévues dans chaque fichier.

- `eval_internal/a_valider_medecins.csv` : 40 questions (séparateur « ; »), colonnes « question_valide », « reponse_correcte », « reponse_corrigee », « commentaire », « relecteur ».
- `eval_internal/genprobe_a_valider_medecins.csv` : 48 questions de la sonde de généralisation (séparateur « , »), colonnes « avis_medecin » et « commentaire ».
- `eval_internal/genprobe2_a_valider_medecins.csv` : 60 questions de la seconde sonde (`genprobe2`, tenue à l'écart) : deux sources, contrepartie de population, note ou en-tête de tableau, contrôles.

## F. Points relevés le 27/11 pendant l'exploration (non vérifiés cliniquement)

- **Correspondance des actes adulte ↔ enfant (antibioprophylaxie V3.1).** Les tableaux pédiatriques ne reprennent pas les lignes des tableaux adultes : ils regroupent et nomment les actes autrement. Seules 39 lignes sur 371 ont un équivalent de même libellé dans l'autre population (`reports/agents/X1_liens_structurels.md`). Une table de correspondance des actes, ou la version du document avec codes CCAM, permettrait de présenter côte à côte la ligne adulte et la ligne pédiatrique d'un même acte. À demander aux auteurs.
- **Lidocaïne adrénalinée, dose maximale.** L'agent qui a écrit `genprobe2` signale un document où un tableau donne 500 mg et le texte 300 mg (`reports/agents/E2_genprobe2.md`, correction de l'item tab-10, retiré du jeu). Le document n'est pas nommé dans le rapport : à retrouver et à vérifier dans la source.

---

## Ce qui a été vérifié, et comment

- **Points A1 à A6** : comparés au PDF source (rendu de la page et couche texte) par l'agent D1. La méthode est décrite dans `reports/agents/D1_audit_doses.md`.
- **Points B** : ils reposent sur la lecture des textes par les agents R1, B2, E1 et l'audit des données. Aucun n'a été validé cliniquement.
- **Points D** : vérifiés contre le PDF officiel V3.1 par A2 et B2.
