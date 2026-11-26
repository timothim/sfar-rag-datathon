# Audit de Dérive Temporelle : Benchmark Antibioprophylaxie V2.0 (2024) vs RFE V3.0 (04/05/2026)

- **Questions totales dans le benchmark officiel** : 171
- **Questions touchant une zone modifiée ou ajoutée en V3.0** : **19**

## Changelog officiel extrait de la RFE V3.0 (04/05/2026)

> V3.0 du 04/05/2026 : ajout d'une recommandation R1.5.2 (avis d'experts) sur la dose de l'amoxicilline-clavulanate chez l'obèse (pages 25-28) ; modification d'une borne d'IMC pour l'adaptation de la clindamycine chez l'obèse (R1.6) pour une meilleure clarté (page 30) ; ajout de propositions de schémas thérapeutiques pour la prolongation postopératoire de l'antibioprophylaxie chez le patient allergique aux bêtalactamines dans les tableaux de neurochirurgie, chirurgie ORL et maxillo-faciale, chirurgie vasculaire, chirurgie thoracique, chirurgie plastique et reconstructrice ; modification de la posologie pourl'antibioprophylaxie de la pose de valve zéphyr (page 55) ; ajout de l'alternative en cas d'allergie aux bêtalactamines quand la céfoxitine est indiquée dans l'encadré allergie du tableau de chirurgie d'affirmation de genre (page 60) ; modification d'un intitulé chirurgical de la ligne « vaginoplastie » du tableau de chirurgie d'affirmation de genre (page 60) ; ajout de l'alternative en cas d'allergie aux bêtalactamines pour les traumatismes complexes de la main dans l'encadré allergie du tableau de traumatologie (page 75) ; modification des intitulés chirurgicaux sur la chirurgie des hernies de paroi (page 83) ; ajout du lien vers les recommandations 2026 de l'AFU concernant l'ECBU préopératoire dans le chapeau introductif du tableau 9 (page 87) ; ajout de précisions sur les délais d'administration de la fosfomycine en antibioprophylaxie des biopsies de prostate par voie transrectale (page 88) ; ajout du champ 3 et des 9 tableaux de recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnelle pédiatrique (à partir de la page 91).

## Questions du benchmark à revérifier en priorité avec les médecins SFAR

| ID | Titre | Type | Réponse V2.0 | Zone impactée en V3.0 |
|---|---|---|---|---|
| `Q03` | PTG allergie bêtalactamines | open | `Clindamycine` | Allergie bêtalactamines / prolongation postop (V3.0 tableaux) |
| `Q04` | PTH voie antérieure allergie | open | `Vancomycine` | Allergie bêtalactamines / prolongation postop (V3.0 tableaux) |
| `Q09` | Écrasement main > 2h | open | `Amoxicilline/Clavulanate` | Traumatismes complexes de la main (encadré allergie ajouté) (V3.0 p.75) |
| `Q12` | Fracture ouverte Gustilo 3 allergie | open | `Clindamycine + Gentamicine` | Allergie bêtalactamines / prolongation postop (V3.0 tableaux) |
| `Q15` | Polytrauma fémur radius plaie main | open | `Amoxicilline/Clavulanate` | Traumatismes complexes de la main (encadré allergie ajouté) (V3.0 p.75) |
| `Q27` | Craniotomie allergie bêtalactamines | open | `Clindamycine` | Allergie bêtalactamines / prolongation postop (V3.0 tableaux) |
| `Q28` | Plaie cranio-cérébrale allergie pénicillines | open | `Triméthoprime/Sulfaméthoxazole` | Allergie bêtalactamines / prolongation postop (V3.0 tableaux) |
| `Q43` | Carcinologique cervico-faciale allergie bêtalactamines | open | `Clindamycine + Gentamicine` | Allergie bêtalactamines / prolongation postop (V3.0 tableaux) |
| `Q63` | Vaginoplastie affirmation de genre | open | `Amoxicilline/Clavulanate` | Chirurgie d'affirmation de genre (vaginoplastie & encadré allergie céfoxitine) (V3.0 p.60) |
| `Q92` | Cholécystectomie coelioscopique haut risque | open | `Céfazoline` | Champ 3 : Pédiatrie & néonatalogie (9 nouveaux tableaux) (V3.0 p.91+) |
| `Q100` | Hernie inguinale avec prothèse | open | `Céfazoline` | Chirurgie des hernies de paroi (intitulés modifiés) (V3.0 p.83) |
| `Q101` | Hernie aine sans prothèse | open | `Pas d'antibioprophylaxie` | Chirurgie des hernies de paroi (intitulés modifiés) (V3.0 p.83) |
| `Q108` | Biopsie prostate transrectale | open | `Fosfomycine-trométamol` | Biopsie prostate transrectale (délais fosfomycine précisés) (V3.0 p.88) |
| `Q109` | Biopsie prostate transpérinéale | open | `Pas d'antibioprophylaxie` | Biopsie prostate transrectale (délais fosfomycine précisés) (V3.0 p.88) |
| `Q141` | PTG allergie alternative | mcq | `C` | Allergie bêtalactamines / prolongation postop (V3.0 tableaux) |
| `Q143` | Plaie jardinage main | mcq | `C` | Traumatismes complexes de la main (encadré allergie ajouté) (V3.0 p.75) |
| `Q160` | Biopsie prostate voie d'abord | mcq | `C` | Biopsie prostate transrectale (délais fosfomycine précisés) (V3.0 p.88) |
| `Q161` | Hernie inguinale avec vs sans prothèse | mcq | `C` | Chirurgie des hernies de paroi (intitulés modifiés) (V3.0 p.83) |
| `Q167` | Allergie bêtalactamines en chirurgie cardiaque | mcq | `B` | Allergie bêtalactamines / prolongation postop (V3.0 tableaux) |