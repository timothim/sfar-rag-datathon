# RAG-SFAR Frontier 2026 — Démonstration Clinique End-to-End (`Qwen2.5-7B-Instruct-4bit`)

> 6 cas cliniques couvrant les **3 RFE phares 2026**, la séparation **Urgence 2024 vs Programmé 2026**, les **allergies split-chunk** et le mode **comparaison longitudinale multi-éditions**.

## 1. Antibioprophylaxie 2026 — PTH voie antérieure + allergie (Exception + Encadré)

**Question** : *Quelle est la recommandation d'antibioprophylaxie pour une PTH par voie antérieure chez un patient allergique aux bêtalactamines ?*

- **Routeur** : `temporal=latest_only` | `setting=non_specifie` | `modifiers=['allergy']`
- **Vérificateur** : Grounding = **100%** | Citations = `['S1']` | Molécules hors-source = `[]` | Auto-corrigé = `False`
- **Tokens prompt** : `2752` | **Latence totale** : `23639 ms`

### Réponse clinique générée

**Réponse synthétique** : Préférer la vancomycine ou la teicoplanine à la clindamycine.

**Posologie, délais et modalités** :
- Vancomycine : 20 mg/kg IVL
- Teicoplanine : 12 mg/kg IVL
- Posologie initiale : Non précisé dans les extraits (doit être adaptée en fonction du poids du patient)
- Réinjections et durée : Non précisé dans les extraits (doit être adaptée en fonction de la durée de la chirurgie)

**Cas particuliers / Sécurité** : 
- Allergie aux bêtalactamines : Vancomycine ou teicoplanine sont préférées à la clindamycine.

**Niveau de preuve** : ●●● (Avis d'experts) [S1]

Note : Les délais et les modalités de réinjection ne sont pas précisés dans les extraits fournis. Il est recommandé de suivre les protocoles institutionnels ou les recommandations actuelles pour les réinjections.

### Sources SFAR citées

- **[S1]** `2026 | EN VIGUEUR | table_row_card` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 2. Recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnel*)
- **[S2]** `2026 | EN VIGUEUR | table_markdown` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 2. Recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnel*)
- **[S3]** `2026 | EN VIGUEUR | callout_allergy` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 2. Recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnel*)
- **[S4]** `2026 | EN VIGUEUR | prose` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 1. Recommandations générales sur l'antibioprophylaxie en chirurgie et médecine inter*)
- **[S5]** `2025 | EN VIGUEUR | prose` — **Diagnostic et prise en charge des réactions d’hypersensibilité immédiate périopératoires** (*CHAMP 1. Bilan diagnostique des réactions d'hypersensibilité immédiates (HSI) périopératoi*)

---

## 2. Antibioprophylaxie 2026 — Neurochirurgie + allergie pénicillines (Split-Chunk)

**Question** : *Quelle est la recommandation d'antibioprophylaxie pour une plaie cranio-cérébrale chez un patient allergique aux pénicillines ?*

- **Routeur** : `temporal=latest_only` | `setting=non_specifie` | `modifiers=['allergy']`
- **Vérificateur** : Grounding = **80%** | Citations = `[]` | Molécules hors-source = `[]` | Auto-corrigé = `False`
- **Tokens prompt** : `2235` | **Latence totale** : `14107 ms`

### Réponse clinique générée

**Réponse synthétique** : Clindamycine 900 mg IV.

**Posologie, délais et modalités** : Clindamycine 900 mg IV, puis réinjection toutes les 6 heures jusqu'à la fin de la chirurgie.

**Cas particuliers / Sécurité** : Non précisé dans les extraits.

**Niveau de preuve** : Avis d'experts (Édition 2026).

### Sources SFAR citées

- **[S1]** `2026 | EN VIGUEUR | callout_allergy` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 2. Recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnel*)
- **[S2]** `2026 | EN VIGUEUR | callout_allergy` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 2. Recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnel*)
- **[S3]** `2026 | EN VIGUEUR | prose` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 2. Recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnel*)
- **[S4]** `2026 | EN VIGUEUR | callout_footnote` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 2. Recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnel*)
- **[S5]** `2026 | EN VIGUEUR | table_row_card` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 2. Recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnel*)

---

## 3. Anticoagulants Programmés 2026 — Arrêt AOD neurochirurgie intracrânienne

**Question** : *Quel est le délai d'arrêt des AOD avant une neurochirurgie intracrânienne ou une procédure neuraxiale programmée ?*

- **Routeur** : `temporal=latest_only` | `setting=programme` | `modifiers=['dosage']`
- **Vérificateur** : Grounding = **100%** | Citations = `['S1', 'S3']` | Molécules hors-source = `[]` | Auto-corrigé = `False`
- **Tokens prompt** : `2420` | **Latence totale** : `18158 ms`

### Réponse clinique générée

**Réponse synthétique** : Les AOD doivent être arrêtés avec une dernière prise à J-5 avant une neurochirurgie intracrânienne ou une procédure neuraxiale programmée.

**Posologie, délais et modalités** : 
- Dernière prise d'AOD à J-5.
- Non précisé dans les extraits.

**Cas particuliers / Sécurité** : 
- Allergie aux bêtalactamines : Non précisé dans les extraits.
- Fonction rénale : Non précisé dans les extraits.
- Obésité : Non précisé dans les extraits.
- Pédiatrie : Non précisé dans les extraits.

**Niveau de preuve** : Avis d'experts (Grade : Avis d'experts, Accord : Fort) [S1], [S3].

### Sources SFAR citées

- **[S1]** `2026 | EN VIGUEUR | table_row_card` — **Gestion des anticoagulants pour une procédure invasive programmée** (*Argumentaire > Argumentaire*)
- **[S2]** `2026 | EN VIGUEUR | table_markdown` — **Gestion des anticoagulants pour une procédure invasive programmée** (*Argumentaire > Argumentaire*)
- **[S3]** `2026 | EN VIGUEUR | prose` — **Gestion des anticoagulants pour une procédure invasive programmée** (*Argumentaire*)
- **[S4]** `2026 | EN VIGUEUR | prose` — **Gestion des anticoagulants pour une procédure invasive programmée** (*les AVK se prescrivent chez les patients de poids extrêmes selon les mêmes modalités posol*)
- **[S5]** `2026 | EN VIGUEUR | table_row_card` — **Gestion des anticoagulants pour une procédure invasive programmée** (*Argumentaire > Argumentaire*)

---

## 4. Anticoagulation Urgence 2024 — Hémorragie intracrânienne (Séparation périmètre)

**Question** : *Chez un patient sous anticoagulant avec hémorragie intracrânienne grave en urgence, quelle est la conduite immédiate et faut-il attendre les dosages biologiques pour réverser ?*

- **Routeur** : `temporal=latest_only` | `setting=urgence` | `modifiers=['dosage']`
- **Vérificateur** : Grounding = **100%** | Citations = `['S1', 'S5']` | Molécules hors-source = `[]` | Auto-corrigé = `False`
- **Tokens prompt** : `2850` | **Latence totale** : `21090 ms`

### Réponse clinique générée

**Réponse synthétique** : Chez un patient sous anticoagulant avec hémorragie intracrânienne grave, la conduite immédiate consiste à administrer des CCP (50 UI/kg) sans attendre les dosages biologiques.

**Posologie, délais et modalités** : 
- Dose initiale : 50 UI/kg.
- Réinjections : Non précisé dans les extraits.
- Délai : Administration immédiate sans attendre les dosages biologiques.

**Cas particuliers / Sécurité** : 
- Allergie aux bêtalactamines : Non précisé dans les extraits.
- Fonction rénale : Non précisé dans les extraits.
- Obésité : Non précisé dans les extraits.
- Pédiatrie : Non précisé dans les extraits.

**Niveau de preuve** : GRADE 2+, Accord fort [S1], [S5].

### Sources SFAR citées

- **[S1]** `2024 | EN VIGUEUR | prose` — **Gestion de l’anticoagulation dans un contexte d’urgence** (*CHAMP 2 : Gestion d'une hémorragie sous anticoagulant*)
- **[S2]** `2022 | EN VIGUEUR | prose` — **Prise en charge des patients présentant un traumatisme crânien léger de l’adulte** (*Champ 2 : Prise en charge aux services des urgences. > Question 2.1 Quels sont les élément*)
- **[S3]** `2024 | EN VIGUEUR | callout_footnote` — **Gestion de l’anticoagulation dans un contexte d’urgence** (*CHAMP 2 : Gestion d'une hémorragie sous anticoagulant > Posologie du sulfate de protamine*)
- **[S4]** `2024 | EN VIGUEUR | table_markdown` — **Gestion de l’anticoagulation dans un contexte d’urgence** (*CHAMP 2 : Gestion d'une hémorragie sous anticoagulant*)
- **[S5]** `2024 | EN VIGUEUR | recommendation_box` — **Gestion de l’anticoagulation dans un contexte d’urgence** (*CHAMP 2 : Gestion d'une hémorragie sous anticoagulant*)

---

## 5. Infections Intra-Abdominales 2026 — IIA communautaire sans sepsis (R1.2.1)

**Question** : *Quelle antibiothérapie probabiliste recommander pour une infection intra-abdominale communautaire sans sepsis ni choc septique chez l'adulte (R1.2.1) ?*

- **Routeur** : `temporal=latest_only` | `setting=reanimation` | `modifiers=[]`
- **Vérificateur** : Grounding = **100%** | Citations = `['S1']` | Molécules hors-source = `[]` | Auto-corrigé = `True`
- **Tokens prompt** : `5833` | **Latence totale** : `48076 ms`

### Réponse clinique générée

**Réponse synthétique** : L'association d'une céphalosporine de 3ème génération (céfotaxime, ceftriaxone) au métronidazole est recommandée pour traiter une infection intra-abdominale communautaire sans sepsis ni choc septique.

**Posologie, délais et modalités** : 
- **Céphalosporine de 3ème génération** : Dose initiale de 2 g, puis 1 g toutes les 8 à 12 heures.
- **Métronidazole** : Dose initiale de 500 mg, puis 250 mg toutes les 8 à 12 heures.
- **Durée** : Non précisé dans les extraits.

**Cas particuliers / Sécurité** : 
- **Allergie aux bêtalactamines** : Alternatives possibles incluent le linezolid.
- **Fonction rénale** : Réduire la dose en fonction de la clairance rénale.
- **Obésité** : Posologie standard, mais surveillance de la toxicité.
- **Pédiatrie** : Posologie adaptée selon l'âge et le poids.

**Niveau de preuve** : GRADE 2, Recommandation faible [S1].

### Sources SFAR citées

- **[S1]** `2026 | EN VIGUEUR | recommendation_box` — **Prise en charge thérapeutique des Infections intra-abdominales de l’adulte** (*CHAMP 1 : Prise en charge initiale des infections intra-abdominales*)
- **[S2]** `2026 | EN VIGUEUR | recommendation_box` — **Prise en charge thérapeutique des Infections intra-abdominales de l’adulte** (*CHAMP 1 : Prise en charge initiale des infections intra-abdominales*)
- **[S3]** `2026 | EN VIGUEUR | table_row_card` — **Prise en charge thérapeutique des Infections intra-abdominales de l’adulte** (*CHAMP 3 : Prise en charge des complications évolutives des infections intra-abdominales*)
- **[S4]** `2026 | EN VIGUEUR | table_row_card` — **Prise en charge thérapeutique des Infections intra-abdominales de l’adulte** (*CHAMP 3 : Prise en charge des complications évolutives des infections intra-abdominales*)
- **[S5]** `2026 | EN VIGUEUR | table_markdown` — **Prise en charge thérapeutique des Infections intra-abdominales de l’adulte** (*CHAMP 3 : Prise en charge des complications évolutives des infections intra-abdominales*)

---

## 6. Veille Longitudinale — Comparaison Antibioprophylaxie 2018 vs 2026

**Question** : *Qu'est-ce qui a changé dans les recommandations d'antibioprophylaxie SFAR entre 2018 et 2026 ?*

- **Routeur** : `temporal=all_versions` | `setting=non_specifie` | `modifiers=['diff']`
- **Vérificateur** : Grounding = **100%** | Citations = `['S1', 'S2']` | Molécules hors-source = `[]` | Auto-corrigé = `False`
- **Tokens prompt** : `1860` | **Latence totale** : `27837 ms`

### Réponse clinique générée

### Comparaison des Éditions 2018 et 2026 des Recommandations SFAR sur l'Antibioprophylaxie

#### Éditions comparées :
- **[S2] Antibioprophylaxie en chirurgie et médecine interventionnelle (patients adultes) — RFE SFAR 2018**
- **[S1] Antibioprophylaxie en chirurgie et médecine interventionnelle — RFE SFAR 2026 (V3.0 (04/05/2026))**

#### Choses qui ont changé :
1. **Nouvelles molécules** :
   - **[S1]** : L'amoxicilline/clavulanate est mentionnée comme une option pour réduire l'incidence des infections postopératoires (ISO) chez les patients BPCO opérés de résection pulmonaire.

2. **Nouveaux délais** :
   - **[S1]** : Pour les fractures ouvertes, il est recommandé de réaliser le débridement de la plaie et le parage le plus rapidement possible, dans un délai inférieur à 24h. L'antibioprophylaxie doit être administrée dès la prise en charge du patient et au mieux moins de 3h après la fracture. Si le délai entre la 1<sup>ère</sup> injection d'antibiotique et la chirurgie est supérieur à 3h, une réinjection préopératoire doit être effectuée.

3. **Nouvelles populations** :
   - **[S1]** : Les recommandations incluent des détails spécifiques pour les patients atteints de bronchopneumopathie chronique obstructive (BPCO) opérés de résection pulmonaire.

4. **Modifications d'alternatives allergiques** :
   - **[S1]** : Il est mentionné que l'utilisation de l'amoxicilline/clavulanate pourrait réduire l'incidence des ISO, et une prolongation de l'antibioprophylaxie pour 24h à 48h postopératoires maximum pourrait également réduire l'incidence de POP lorsqu'elle

### Sources SFAR citées

- **[S1]** `2026 | EN VIGUEUR | prose` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 2. Recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnel*)
- **[S2]** `2018 | ANTÉRIEURE 2018 | table_row_card` — **Antibioprophylaxie en chirurgie et médecine interventionnelle (patients adultes)** (*Recommandations Formalisées d'Experts > Antibioprophylaxie en chirurgie thoracique*)
- **[S3]** `2026 | EN VIGUEUR | prose` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 2. Recommandations sur l'antibioprophylaxie en chirurgie et médecine interventionnel*)
- **[S4]** `2018 | ANTÉRIEURE 2018 | table_row_card` — **Antibioprophylaxie en chirurgie et médecine interventionnelle (patients adultes)** (*Recommandations Formalisées d'Experts > Antibioprophylaxie en chirurgie ORL*)
- **[S5]** `2026 | EN VIGUEUR | prose` — **Antibioprophylaxie en chirurgie et médecine interventionnelle** (*CHAMP 1. Recommandations générales sur l'antibioprophylaxie en chirurgie et médecine inter*)

---
