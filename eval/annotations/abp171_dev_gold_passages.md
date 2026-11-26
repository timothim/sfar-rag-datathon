# abp171 dev : annotation des passages gold

Document de référence : RFE antibioprophylaxie V3.0 (doc_id `2026_RFE-antibioprophylaxie-2023_V3_0_pour-mise-sur-site-juin-2026_sa_9ff419`).

## Méthode
- Lecture des chunks indexés du document (table `chunks` de `index/table_aware_sota/metadata.sqlite`, 811 chunks) et repérage, pour chaque question, de la ligne de tableau (acte, molécule) ou de l'encadré allergie qui justifie la réponse de référence.
- Chaque `quote` est recopiée depuis le texte d'un chunk (tableaux de la partie adulte, doses « 2g IVL »), sans balises HTML, 8 à 60 mots.
- QCM comparatives : ajout du passage de l'option correcte et, quand la question oppose plusieurs actes, de celui des options fausses (Q144, Q154, Q157, Q158, Q160, Q161, Q164, Q165, Q166, Q168). Questions allergie : ligne de l'acte + encadré allergie (Q3, Q27, Q28, Q141).
- Validation : `passage_match(quote, chunk_text)` (seuil 0,5) satisfaite par au moins un chunk du document pour les 121 quotes ; recouvrement de trigrammes mesuré >= 0,8 pour toutes.

## Résultat
- 102 questions annotées sur 102 (121 passages), aucune sans passage.

## Cas à signaler (passage trouvé mais partiel ou ambigu)
- Q163 : seules les lignes « fracture ouverte Gustilo 2 ou 3 » (amoxicilline/clavulanate) et l'alternative céfazoline + gentamicine sont citées ; le document n'aborde pas le cas d'un patient déjà sous ceftriaxone, donc l'option C (« incorrecte ») n'est pas justifiée explicitement par un passage.
- Q42 : le document contient deux lignes contradictoires pour la chirurgie orthognatique (céfazoline avec amoxicilline/clavulanate en alternative, et amoxicilline/clavulanate seule dans le tableau de chirurgie plastique) ; la quote retenue suit la réponse de référence (céfazoline).
- Q159 : la ligne de la cholécystectomie par coelioscopie est fusionnée à l'extraction OCR (haut risque et faible risque dans la même cellule) ; la quote couvre ictère/calcul de la VBP.
- Q3, Q141 : la réponse « clindamycine » repose sur l'encadré allergie du tableau orthopédique (clindamycine en première intention), distinct de la ligne prothèse.
- Q28 : le TMP/SMX provient de l'encadré allergie du tableau de neurochirurgie (amoxicilline/clavulanate remplacé par triméthoprime/sulfaméthoxazole).
