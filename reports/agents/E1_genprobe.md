# E1 — Sonde de généralisation `genprobe` (2026-11-27)

**Statut : outil interne de développement. 48 questions synthétiques, écrites et vérifiées par un LLM (Claude Opus 5.5), non validées par un médecin. Ce n'est pas un benchmark.** Tenue à l'écart de la mise au point : à exécuter une seule fois sur les configurations gelées, chaque exécution étant consignée dans `JOURNAL.md`.

## Pourquoi

Plusieurs règles du retrieval n'ont pu être mesurées que sur l'antibioprophylaxie : tableaux adulte/pédiatrie, notes de tableau, QCM, questions à deux RFE. L'autre jeu interne (`multirfe_synth`) ne contient ni QCM ni presque aucune question à deux sources. `genprobe` exerce ces situations sur d'autres RFE.

Indépendance : les auteurs n'ont lu ni `src/rag_sfar/retrieval/`, ni les rapports B1/R2, ni aucun autre jeu de questions. Aucun modèle, retrieval ni calcul GPU n'a été lancé sur ces questions.

## Composition

| Famille (tag) | n | Contenu |
|---|---|---|
| `fam:mcq` | 12 | QCM à 4 ou 5 options, une seule étayée par le texte ; les distracteurs sont des valeurs de la même RFE valables dans une autre situation (`answer_key.mcq`) |
| `fam:table_note` | 12 | La réponse est une cellule de tableau, juste seulement si l'on lit la note, le champ, l'en-tête de colonne, l'unité ou la population du titre |
| `fam:population` | 12 | Conduite différente selon la population : enfant, femme enceinte, sujet âgé, obèse. 6 questions précisent la population ; 6 ne la précisent pas (`population_unspecified`, `meta.expected_behavior = conditional_or_clarification`) et leur référence donne chaque cas |
| `fam:two_source` | 12 | 7 `two_documents` (deux RFE) et 5 `two_sections` (deux sections éloignées d'une même RFE), avec deux preuves requises (ET) |

- **Types de questions** : `mcq` 12, `table` 12, `clinical_case` 16, `open` 6, `comparison` 2.
- **Tableaux** : 18 questions sur 48 portent sur un tableau (tag `table`).
- **Difficulté** : notée dans `meta.difficulty`.
- **Preuves** : `evidence` et `evidence_sets` sont remplis pour les 48 questions, donc la métrique `sufficiency` est calculable partout.
- **Affirmation interdite** : une question (`gp-pop-07`) porte un `forbidden_claims`, la conduite dépassée de 2006.

## Documents couverts

47 RFE en vigueur, soit 50 `doc_id`, de 2002 à 2026, aucune sur l'antibioprophylaxie. Réanimation, anesthésie, obstétrique, traumatologie, hémostase, nutrition, pédiatrie, urgence.

| Année | RFE | Questions |
|---|---|---|
| 2002 | Asthme aigu grave de l'adulte et de l'enfant | pop-01 |
| 2006 | Arrêt cardiaque | pop-06 |
| 2006 | Blocs périmédullaires chez l'adulte | two-05 |
| 2007 | Nausées et vomissements postopératoires | pop-05 |
| 2007 | Sédation et analgésie en réanimation (texte court, aspects pédiatriques) | pop-08 |
| 2008 | États de mal épileptiques | pop-02 |
| 2009 | Gestion périopératoire des traitements chroniques | two-10 |
| 2010 | Coronarien opéré en chirurgie non cardiaque | two-09 |
| 2012 | Examens pré-interventionnels systématiques | mcq-09 |
| 2012 | Transfusion de plasma thérapeutique | two-06 |
| 2013 | Chirurgie ambulatoire en urologie | tab-12 |
| 2014 | Réanimation du choc hémorragique | mcq-05 |
| 2014 | Transfusion de globules rouges homologues | tab-08 |
| 2014 | Antalgiques en chirurgie ORL | pop-12 |
| 2015 | Insuffisance rénale aiguë | mcq-08 |
| 2016 | Traumatisés crâniens graves | mcq-04, pop-09 |
| 2016 | Contrôle ciblé de la température | pop-09 |
| 2016 | Intubation et extubation en réanimation | two-04 |
| 2016 | ALR périnerveuse | two-05 |
| 2017 | Pneumonies associées aux soins | mcq-11 |
| 2017 | Anesthésie du sujet âgé | pop-10 |
| 2017 | Traumatisés pelviens graves | two-03 |
| 2018 | SDRA | mcq-03 |
| 2018 | Insuffisance hépatique en soins critiques | mcq-12 |
| 2018 | Antiplaquettaires, procédure programmée | two-01 |
| 2018 | Antiplaquettaires, procédure non programmée ou hémorragie | two-01 |
| 2019 | Hyperthermie maligne | mcq-01 |
| 2019 | Thrombopénie induite par l'héparine (GIHP/GFHT) | mcq-06 |
| 2019 | Brûlé grave adulte et enfant (texte et fiches) | pop-03, pop-04 |
| 2019 | Traumatisme abdominal grave | two-03 |
| 2019 | RAC en orthopédie lourde | two-11 |
| 2019 | Anémie en soins critiques | two-12 |
| 2020 | Pré-éclampsie sévère (fiches) | mcq-02 |
| 2020 | Traumatisme sévère de membre | tab-11, two-08 |
| 2020 | Plasmas lyophilisés (PLYO) | two-06 |
| 2021 | Pancréatite aiguë | mcq-07 |
| 2022 | Urgences obstétricales en médecine d'urgence | pop-07 |
| 2024 | Anticoagulation en contexte d'urgence | tab-10, two-02, two-07 |
| 2024 | Optimisation hémodynamique périopératoire, adulte | pop-10 |
| 2025 | Analgésie obstétricale | tab-05 |
| 2025 | Résection hépatique | tab-06 |
| 2025 | Intubation hors bloc et hors soins critiques | two-04 |
| 2026 | LAT en soins critiques | mcq-10 |
| 2026 | Anticoagulants pour procédure invasive programmée | tab-01, tab-02, two-02, two-07 |
| 2026 | Nutrition clinique (versions courte et longue) | pop-11, tab-03, tab-04 |
| 2026 | Sédation procédurale aux urgences | tab-07 |
| 2026 | Voies aériennes de l'adulte au bloc | tab-09 |

## Méthode

1. **Rédaction.** Quatre sous-agents, un par famille, ont chacun reçu une liste de RFE distincte. Ils ont lu les éditions en vigueur de `index/tas_v3_errata` dans le Markdown source et dans `data_derived/recommendations.jsonl`. La référence est tirée strictement du texte, doses et seuils verbatim. Les citations font 8 à 40 mots ; une ligne de tableau est citée cellule par cellule, séparée par « ‖ ».
2. **Contrôles programmatiques** (`eval_internal/build_genprobe_checks.py`).
   - Chaque citation est retrouvée verbatim dans le Markdown source, après retrait des balises et normalisation de la casse, des espaces et des apostrophes. Pour une citation « ‖ », chaque cellule est retrouvée, et toutes dans la même ligne `<tr>`.
   - Chaque document est une édition en vigueur, et aucun ne relève de l'antibioprophylaxie.
   - Le format est valide (`EvalItem`), les identifiants sont uniques et les clés de QCM valides.
   - Les ensembles de preuves sont cohérents.
   - Aucune question ne recopie 8 mots consécutifs d'une citation ni le titre d'un document.
   - Comptes par famille, par document et par année.
3. **Couverture du mapping.** Avec `--mapping`, le script vérifie pour chaque citation qu'au moins un chunk de `index/tas_v3_errata` la reconnaît avec `harness.passage_match`. Calcul sur CPU, sans modèle.
4. **Seconde relecture indépendante.** Deux sous-agents qui n'avaient pas écrit les questions ont relu les sources, ainsi que les autres RFE du corpus sur le même sujet. Ils ont vérifié que la référence est la seule lecture possible, qu'un QCM n'a qu'une option étayée et qu'aucune question ne donne sa réponse. Les corrections ont été appliquées puis les contrôles relancés.

## Résultats des contrôles (version finale)

- **Citations** : 94 sur 94 retrouvées verbatim dans la source. Toutes les lignes de tableau ont leurs cellules dans une même ligne `<tr>`. Le contrôle donne 0 erreur et 0 avertissement.
- **Couverture du mapping** : 93 sur 94 citations sont reconnues par au moins un chunk. La suffisance est atteignable dans l'index pour 47 questions sur 48.
- **Seule citation non reconnue : `gp-tab-06`** (résection hépatique 2025, algorithme de remplissage).
  - Le chunk tableau de cet algorithme (`…MEL_e8bdcf__c0086`) a perdu la partie de la cellule qui donne l'objectif de PAM : > 65 mmHg, et > 70 mmHg ou > 90 % de la valeur habituelle chez l'hypertendu. Il ne reste que « 12 % < VVE < 20 % ; PVC < 5 ».
  - La citation est la bonne : c'est l'ingestion de l'index qui a perdu le texte. La citation est donc conservée, et c'est un constat pour B2 (ingestion).
- **Bogue corrigé dans le script de contrôle pendant le travail.** La première version retirait les balises avec `<[^>]+>` après `html.unescape`. Un « < » littéral du texte (« < 30 ml/min », « &lt; 10 kg ») était alors pris pour une balise, et le retrait effaçait des paragraphes entiers. Résultat : de faux « citation introuvable ». La version committée retire les seules vraies balises, avant de décoder les entités.

## Corrections de la seconde relecture (16)

Le détail est dans `eval_internal/work/genprobe/second_pass_corrections.json`. Les plus importantes :

- **gp-mcq-03 (SDRA).** Le distracteur « manœuvres de recrutement » a été remplacé.
  - Une RFE en vigueur plus récente (sepsis 2025, R31) recommande de ne pas les utiliser dans le SDRA modéré à sévère.
  - Le QCM avait donc deux réponses défendables, et le distracteur présentait comme recommandée une pratique déconseillée.
- **gp-pop-07 (arrêt cardiaque chez la femme enceinte).** La référence a été réécrite d'après la RPP 2022 sur les urgences obstétricales.
  - Le texte de 2006, toujours « en vigueur » dans l'index, conseille d'incliner l'utérus de 15° et une extraction après la 25e semaine.
  - La RPP 2022 indique que la latéralisation réduit l'efficacité du massage. Elle demande un déplacement manuel continu de l'utérus et une césarienne envisagée à 4 minutes au-delà de 20 SA.
  - La latéralisation est désormais une affirmation interdite (tag `outdated_trap`).
- **gp-tab-10 et gp-two-07 (protamine sous énoxaparine).**
  - La note « anti-Xa ≤ 0,2 UI/ml et fonction rénale » venait de la branche « autre hémorragie grave » de l'algorithme. Elle est remplacée par R2.6.9 : pas de protamine si l'anti-Xa est < 0,2 UI/mL, quelle que soit l'hémorragie.
  - Dans gp-two-07, la question précise maintenant un choc hémorragique : pour une autre hémorragie grave, la protamine se discute au cas par cas.
- **gp-pop-09 (contrôle de la température, traumatisé crânien).** La partie enfant est complétée : CCT visant la normothermie (R12.5 de la RFE TC graves 2016), en plus de l'interdiction d'induire une hypothermie.
- **gp-pop-10 (sujet âgé, PAM).** La patiente est précisée non hypertendue, parce que la RFE 2024 d'optimisation hémodynamique fixe une autre cible chez l'hypertendu chronique. La cible générale de 2024 est ajoutée.
- **gp-tab-12 (rétention urinaire).** Un agent de courte durée d'action ne classe pas à lui seul le patient à risque faible. La lidocaïne est aujourd'hui contre-indiquée en rachianesthésie ; cette contre-indication est ajoutée.
- **gp-mcq-11.** L'énoncé exclut aussi la pneumonie nécrosante.
- **gp-mcq-10.** La formulation supposait un document connu ; elle est corrigée.
- **gp-pop-08.** Le tag `two_documents` est retiré, car le texte court suffit.
- **Citations ajoutées** à gp-pop-03, gp-tab-04, gp-two-10 et gp-two-11, pour que chaque élément de la référence soit porté par une citation.

## Constats sur le corpus (hors questions)

- **Doses pédiatriques d'adrénaline fausses dans le Markdown de la RFE arrêt cardiaque 2006.** Le texte donne « 10 mg/kg » IV et « 100 mg/kg » intratrachéal, très probablement des µg/kg perdus à la conversion du PDF, soit une erreur d'un facteur 1000.
  - Aucune question ne s'appuie sur ces passages.
  - Un RAG qui les cite donnerait une réponse dangereuse. Ce point est à signaler pour l'ingestion ou pour un garde-fou de dose.
- **Des RFE anciennes restent « en vigueur » dans l'index alors qu'un texte plus récent d'une autre lignée les contredit :** arrêt cardiaque 2006 contre RPP urgences obstétricales 2022 ; SDRA 2018 contre sepsis 2025 pour les manœuvres de recrutement ; plasma 2012 contre PLYO 2020, tension notée dans gp-two-06.
- **Brûlé grave 2019 : cible de diurèse de l'enfant différente** entre le texte long (0,5 à 1 mL/kg/h) et la fiche de synthèse (0,5 à 1,5). Aucune question ne porte dessus.
- **Paracétamol < 10 kg (ORL 2014)** : le tableau applique 7,5 mg/kg aux trois voies d'administration. La question suit le texte, mais l'écart avec la pratique habituelle, où la dose réduite vaut pour la voie IV, est à faire vérifier par un médecin.
- **Lignes de tableau trop courtes pour être citées.** Plusieurs lignes, idéales pour la famille « note de tableau », font moins de 8 mots, comme « Dexaméthasone ‖ 150 ‖ 5,00 » dans le tableau pédiatrique NVPO 2007, dont l'unité n'est que dans l'en-tête et la population que dans la légende. Elles n'ont pas pu servir.

## Branchement dans le harnais

- `load_suite("genprobe", "dev")` charge les 48 questions sans modification de `src/`.
- **À changer côté code** : `available_suites()` liste désormais `genprobe`, donc `rag-sfar-eval --suite full --split dev` l'inclurait dans les évaluations de mise au point. Il faudrait exclure les suites tenues à l'écart de `full`, par exemple avec une liste `HELD_OUT_SUITES` ou un fichier marqueur dans `splits/genprobe/`.
- **Autre effet** : `--suite full --split all` échoue désormais, faute de `splits/genprobe/test.jsonl`.
- **Test anti-fuite** : `tests/test_no_benchmark_leakage.py` lit déjà tous les `eval_internal/datasets/*.jsonl`, donc il protège `genprobe` sans modification. Il passe.
- **Coffre-fort** : il n'y a pas de split test, donc rien à sceller dans `LOCKBOX.md`. Le fichier entier devrait cependant être traité comme un test, c'est-à-dire ne pas être consulté pendant la mise au point.

## Limites

- **Validation** : questions synthétiques, non validées par un médecin. Le CSV `eval_internal/genprobe_a_valider_medecins.csv` est prêt pour une relecture.
- **Auto-préférence** : questions et vérification viennent de la même famille de modèles que certains générateurs évalués, d'où un risque d'auto-préférence.
- **Effectifs** : 12 questions par famille donnent des IC bootstrap très larges ; seuls des écarts importants seront interprétables.
- **Antériorité des références** : les références suivent le texte du corpus, y compris des RFE anciennes (2002 à 2010) encore marquées « en vigueur ». Sauf correction explicite (gp-pop-07), une question peut reposer sur une conduite que la pratique a dépassée.
- **Robustesse des réponses** : la seconde relecture a cherché les contradictions dans le corpus, sans garantie d'exhaustivité. Les preuves sont une borne basse : d'autres passages peuvent aussi répondre.
- **Dépendance aux notes de tableau** : plusieurs items `fam:table_note` dépendent d'une note placée dans la même cellule (tab-05, tab-06) ou répétée ailleurs dans le texte (tab-03), donc moins fortement qu'annoncé.
- **Équilibre des documents** : les RFE anticoagulants 2024 et 2026 et la RFE nutrition 2026 portent chacune 3 à 4 questions.
