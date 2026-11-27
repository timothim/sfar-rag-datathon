# A1 — Branchement du benchmark enrichi (suite `abpe171`)

Date : 2026-11-27. Agent : Claude Opus 5.5 (sous-agent). Périmètre : `src/rag_sfar/evaluation/*`, `eval/`, `eval_internal/judge/JUDGE_INSTRUCTIONS.md`, `tests/`, rapports. Le code du pipeline (retrieval, ingestion, génération), `index/` et `data/` n'ont pas été modifiés.

## Conclusions chiffrées (split DEV uniquement)

**Couverture du mapping preuves → chunks** (index `table_aware_sota`, document V3.1 en vigueur, 812 chunks) :

| Niveau | Couvert | Taux |
|---|---:|---:|
| Fragments de preuve bruts (`exact_fragments` tels quels, `passage_match` standard) | 230 / 294 | 78,2 % |
| `gold_passages` après normalisation (une citation par ligne de tableau) | **341 / 348** | **98,0 %** |
| Preuves (`evidence_id`) dont au moins un fragment est retrouvé | **217 / 222** | **97,7 %** |
| Questions dont un ensemble de preuves est entièrement mappable (plafond de la suffisance) | **94 / 96** | **97,9 %** |

Chaque `gold_passage` normalisé correspond en médiane à 2 chunks de l'index (contre plusieurs centaines avant le filtrage des n-grammes génériques, voir « Normalisation »).

**Baseline retrieval seul, `abpe171` dev** (96 questions avec ensemble de preuves ; 6 questions de clarification sans ensemble ; IC bootstrap 95 %) :

| Config | Contexte moyen | Doc hit | Passage hit | Preuve hit | Rappel preuves | **Suffisance** |
|---|---:|---:|---:|---:|---:|---:|
| C9 | 7,9 chunks | 100,0 | 96,1 [92–99] | 94,8 [90–99] | 89,7 [84–94] | **83,3 [76–91]** |
| C9 + fenêtres (`final_top_k=16+context_window=1+expand_table_parent=true`) | 24,1 chunks | 100,0 | 98,0 [95–100] | 95,8 [92–99] | 92,8 [88–97] | **88,5 [82–95]** |

Écart apparié fenêtres − C9 : suffisance **+5,2 pts [+1,0 ; +10,4]**, rappel des preuves +3,1 pts [+0,7 ; +6,2], passage hit +2,0 [0,0 ; +4,9]. Aucune intrusion d'édition obsolète (0/102).

Courbes (rang dans le contexte retourné) :

| Config | Courbe | k=1 | 3 | 5 | 8 | 12 | 16 | 20 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| C9 | Rappel preuves@k | 58,1 | 81,8 | 88,3 | 89,7 | 89,7 | 89,7 | 89,7 |
| C9 | Suffisance@k | 46,9 | 72,9 | 81,2 | 83,3 | 83,3 | 83,3 | 83,3 |
| C9 + fenêtres | Rappel preuves@k | 58,1 | 70,4 | 82,5 | 87,7 | 91,8 | 92,3 | 92,8 |
| C9 + fenêtres | Suffisance@k | 46,9 | 59,4 | 72,9 | 81,2 | 86,5 | 87,5 | 88,5 |

Les fenêtres intercalent les voisins après leur ancre : à budget de rangs égal (k ≤ 8) elles sont moins bonnes, le gain n'apparaît qu'en laissant passer tout le contexte (~24 chunks, coût en tokens ×3).

**Ventilation par tag (suffisance, C9 → C9 + fenêtres)** : adulte 92 → 94 (n=49) ; adulte et pédiatrique 88 → 88 (n=25) ; non précisé 69 → 85 (n=13) ; **pédiatrique 44 → 67 (n=9)** ; tag `pediatric` (pédiatrique ou mixte) 76 → 82 (n=34). Par catégorie : TABLE 80 → 86 (n=35), NEGATION 87 → 90 (n=31), CONDITION 87 → 91 (n=23), DIRECT 75 → 100 (n=4), MULTIHOP 0 → 0 (n=1). Par difficulté : facile 79 → 93 (n=14), moyenne 84 → 88 (n=73), difficile 89 → 89 (n=9). Les effectifs par tag sont petits : différences indicatives seulement.

**`multirfe_synth` dev** (pas d'ensembles de preuves, passages gold seulement) : passage hit C9 85,5 [78–93] → fenêtres 100,0 (+14,5 pts [+6,6 ; +22,4]) ; doc hit 97,4 → 100.

**Causes des échecs de suffisance** (11 échecs avec fenêtres, 16 sans ; détail plus bas) : la pédiatrie domine (6/11 : ligne ou note du tableau pédiatrique non retrouvée), puis l'ingestion (2/11 : tableaux sans en-tête « Col 1 | Col 2 » sans fiche ligne), une note de bas de tableau déportée, un QCM à quatre options exigeant six preuves, une requête au contexte nié qui attire les encadrés allergie. Les 5 échecs corrigés par les fenêtres sont tous des « chunks voisins » ou « tableau parent ».

**Anti-fuite** : à l'ajout du benchmark enrichi, le test a trouvé une fuite (voir plus bas), corrigée entre-temps par la relecture des modifications tierces (commit `5aa9d1a`). Le test passe aujourd'hui sans marqueur.

## Format et conversion

`convert_enriched_benchmark()` (`src/rag_sfar/evaluation/datasets.py`) lit le JSONL consolidé et produit des `EvalItem` (format commun, `eval/README.md`) :

- `id` = identifiant legacy (Q01…Q171), `question` / `choices` = `proposed` (ce qui est donné au système), `reference_answer` = `short_answer`, provenance `physician_validated` (171/171 approuvées).
- `gold_doc_ids` = édition en vigueur de la RFE antibioprophylaxie lue dans `index/table_aware_sota/metadata.sqlite` (`topic_lineage='antibioprophylaxie' AND is_latest_edition=1`) : `2026_RFE-antibioprophylaxie-2023_V3_1_pour-mise-sur-site-juillet-2026_642ad1` (la V3.0 y est marquée remplacée).
- `answer_key` : `{"mcq": lettre}` seulement si `mcq_option_status == "single_supported"` (18/19 QCM du dev) ; rien pour les questions ouvertes (notées par le juge sur les faits obligatoires) ni pour `invalid_choices` (tag `mcq:invalid_choices`).
- `expected_behavior` : `answer_with_evidence` → `answer`, `ask_clarification` → `clarification` (6 en dev, tag `behavior:clarification`), `abstain` → `abstention` (aucune) ; `should_abstain` vrai seulement pour l'abstention.
- Champs optionnels ajoutés à `EvalItem` (rétrocompatibles : vides par défaut, omis à l'écriture, les anciens fichiers se réécrivent à l'octet près — testé) : `mandatory_claims`, `forbidden_claims`, `expected_behavior`, `acceptable_alternatives`, `required_missing_information`, `evidence` ({evidence_id, doc_id, page, fragments, other_fragments, role, verification_status}), `evidence_sets` ({set_id, required_evidence_ids}).
- Tags : `cat:<primary_category>`, `difficulty:*`, `population:<adult_or_pediatric>`, `pediatric` (pédiatrique ou mixte), `challenge:<retrieval_challenges>`, `special:<special_population>`, `behavior:*`. `meta` garde question_id, narratif, statut QCM, catégories secondaires, famille de gabarit, décision de relecture.

### Normalisation des fragments (`normalize_layout_fragment`)

Les `exact_fragments` sont du texte `pdftotext -layout` : les colonnes du tableau sont entrelacées ligne à ligne (« § Prothèse de hanche … Céfazoline 2g IVL 1g si durée > 4h … ◉◎◎ »), ce qu'aucun chunk ne reproduit. Règles génériques (structure des tableaux RFE, aucune règle par question) :

1. Découpage de chaque ligne en segments de colonne (séparés par ≥ 2 espaces) ; suppression des segments composés uniquement de mots d'en-tête de tableau (« Actes chirurgicaux ou interventionnels », « Molécules », « Dose initiale », « Réinjections et durée », « Force de la recommandation », « Nomenclature ») et des puces (« § », « o », « ▪ »).
2. Découpage en lignes de tableau : ligne vide, puce « § », ou ligne commençant par une majuscule en première colonne (libellé de sous-catégorie) ; une ligne en minuscule ou « ( » en première colonne prolonge l'acte.
3. Dans une ligne de tableau, regroupement des segments par colonne (position ± 4 caractères) et lecture colonne par colonne ; colonnes séparées par « ‖ ».
4. Suppression des titres en capitales et des lignes trop génériques (< 6 mots, ou < 3 mots hors vocabulaire posologique/cotation : « PAS D'ANTIBIOPROPHYLAXIE (Avis d'experts) », « Céfazoline 2g IVL … ») ; si rien ne reste, le fragment entier est gardé s'il passe le même test.
5. Choix des fragments : quand l'annotation nomme la ligne (`table_coordinates.row`), seules les lignes portant ce libellé (≥ 60 % de ses mots) sont créditées (`fragments`), les autres lignes du même fragment vont dans `other_fragments` (contexte, pas de crédit). Sinon toutes les lignes sont créditées.

`passage_match` (harness) traite une citation contenant « ‖ » colonne par colonne : n-grammes jamais à cheval sur deux cellules, cellules de deux mots comparées en bigrammes, seuls les n-grammes contenant un mot de contenu comptent (sans cela, « 2g IVL ‖ Avis d'experts » suffisait à créditer 266 chunks). Les citations sans « ‖ » (abp171, multirfe_synth) gardent exactement l'ancien comportement.

Écart à la consigne : `gold_passages` = une citation par **ligne de tableau utile** d'un fragment, pas une par fragment brut, car un fragment couvre souvent plusieurs lignes de tableau alors qu'un chunk n'en contient qu'une ; une preuve est couverte quand l'un de ses fragments crédités l'est (règle « au moins un fragment »).

### Cas non mappables (DEV) — informations sur l'ingestion

| Question | Page | Ce qui manque | Cause |
|---|---|---|---|
| Q05, Q163 | 76 | Ligne pleine largeur « En cas de chirurgie pour fracture ouverte considérée comme Altemeier 3 ou 4, considérer une antibiothérapie curative… » | Présente dans l'overlay V3.1 (`<td colspan="5">`, ligne 3636 du Markdown) mais absente de tous les chunks : le parseur de tableaux perd les lignes `colspan` pleine largeur. |
| Q53 | 104 | Libellé « Chirurgies médiastinales, pleurales, pariétales (y compris par voie thoracoscopique/vidéo-assistée) » | Sous-catégorie convertie en titre Markdown (seulement dans `section_path`, pas dans le texte) ; en plus, libellé de l'overlay différent du PDF V3.1 (« voies thoracoscopiques vidéo-assistées »). |
| Q153 | 67 | Libellé « Chirurgie de l'utérus par voie laparotomique, coelioscopique ou robotique » | Titre Markdown (`###`) → `section_path` seulement. |
| Q61 | 59 | Abdominoplastie / abord extra-oral, deux sous-lignes (durée ≤ 2h / > 2h) | Sous-lignes entrelacées dans le même bloc layout : limite de la normalisation. |
| Q115 | 89 | « Lithotritie extra-corporelle » | Coquille de l'overlay V3.1 indexé (« Lithotrite ») absente du PDF. |
| Q120 | 41 | « Chirurgie amygdalienne et adénoïdectomie … Amygdalectomie, Adénoïdectomie » | Tableau sans en-tête converti en `Col 1 | Col 2 | Col 3`, sans fiche ligne (`table_row_card`), libellé en titre. Même famille de défaut pour l'hystéroscopie (Q74, mappable mais non retrouvée). La page 96 écrit « Amygdallectomie » dans l'overlay. |

Ces défauts relèvent de l'overlay V3.1 généré par un autre agent et du parseur de tableaux ; ils sont à transmettre à l'agent ingestion (non corrigés ici, hors périmètre).

## Métriques ajoutées (`harness.py`, rétrocompatibles)

`evidence_metrics()` (appelée par `retrieval_metrics`, uniquement pour les questions qui ont `evidence_sets`) calcule sur **tout le contexte retourné** :
- `evidence_hit` : au moins une preuve requise couverte ;
- `evidence_recall` : part des preuves requises (union des ensembles) dont un fragment est couvert ;
- `sufficiency` : un ensemble entièrement couvert (ET dans l'ensemble, OU entre ensembles) ; les questions sans ensemble (clarification) n'entrent pas au dénominateur ;
- `evidence_ranks`, `sufficiency_rank` → courbes `evidence_recall_curve` et `sufficiency_curve` à k ∈ {1, 3, 5, 8, 12, 16, 20}.

Ajoutées à `METRIC_KEYS` (donc ventilées par provenance, type et tag), aux tableaux Markdown, aux comparaisons appariées ; une section « Courbes » est ajoutée aux rapports.

## Juge

- `judge.py` : `JUDGE_SCHEMA` accepte en option `claims_satisfied`, `forbidden_violated`, `behavior` (answer | clarification | abstention) ; `format_expectations()` met en texte faits obligatoires, interdits, comportement attendu et informations manquantes ; les 5 champs historiques sont inchangés.
- `judge_io export` ajoute `mandatory_claims`, `forbidden_claims` ({id, text}), `expected_behavior`, `required_missing_information` quand l'item les porte.
- `judge_io merge` agrège `judge_claims_rate` (faits obligatoires satisfaits), `judge_no_omission` (réponses sans omission), `judge_forbidden_violation`, `judge_behavior_ok`, avec IC ; ces métriques n'existent que pour les verdicts qui portent les nouveaux champs (les rapports déjà jugés restent identiques).
- `eval_internal/judge/JUDGE_INSTRUCTIONS.md` décrit les nouveaux champs d'entrée et de sortie. Le juge n'a pas été recalibré sur ces nouveaux champs (aucun appel API).

## Anti-fuite

`tests/test_no_benchmark_leakage.py` charge aussi le benchmark enrichi (question proposée, choix, `short_answer`, textes des faits obligatoires et interdits ; les faits passent par la règle des 7-grammes) dans un test dédié, `test_no_enriched_benchmark_text_in_system_code`. Les classes de réponse partagées (« Pas d'antibioprophylaxie. ») sont calculées sur l'union avec les jeux historiques.

Fuite trouvée à l'ajout (2026-11-27, vers 00 h 50), dans les modifications **non commitées** de Gemini Neon :
- `src/rag_sfar/retrieval/router.py:66` et `src/rag_sfar/retrieval/router.py:93` (commentaires) : « sans portage connu d'entérobactérie productrice de BLSE », 7-grammes spécifiques de la question révisée **Q158** (dev).

Le test a d'abord été marqué `xfail(strict=True)` conditionnel. Pendant mon travail, la relecture des modifications tierces a été commitée (`5aa9d1a`) sans ces commentaires ; la fuite a disparu et le marqueur a été retiré. Le test passe sans marqueur.

## Reproduction

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.datasets convert-enriched          # dataset (split déjà scellé : non réécrit)
HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.datasets coverage --suite abpe171   # couverture du mapping (dev)
HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-eval --suite abpe171 --split dev --configs C9 --retrieval-only \
    --ablate "final_top_k=16+context_window=1+expand_table_parent=true" --k 64 --tag c9_evidence
HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-eval --suite multirfe_synth --split dev --configs C9 --retrieval-only \
    --ablate "final_top_k=16+context_window=1+expand_table_parent=true" --k 64 --tag c9_evidence
```

`--k 64` : toutes les métriques « @k » portent sur le contexte entier (≤ 8 chunks pour C9, ~24 avec fenêtres) ; les courbes donnent les coupures intermédiaires. Rapports : `reports/eval/20261127-010843_abpe171_dev_c9_evidence.{json,md}`, `reports/eval/20261127-011052_multirfe_synth_dev_c9_evidence.{json,md}`. Code du pipeline au moment des mesures : commit `0712f54`, sans modification locale de retrieval/ingestion/génération ; index `table_aware_sota` du 26/11 16:26 (non reconstruit après les commits d'ingestion `1f8d95e`). Une mesure précédente sur l'arbre de travail non commité donnait exactement les mêmes chiffres. Les latences ne sont pas comparables (machine chargée par d'autres agents).

## Analyse des échecs de suffisance (DEV)

| Question | C9 | Fenêtres | Preuve manquante (fenêtres) | Cause |
|---|:-:|:-:|---|---|
| Q05 | ✗ | ✗ | note posologique du tableau pédiatrique (p. 109) | Pédiatrie : question sans âge, l'ensemble exige aussi la preuve pédiatrique |
| Q07 | ✗ | ✗ | note posologique pédiatrique (p. 94) | Pédiatrie (même schéma) |
| Q44 | ✗ | ✗ | ligne « chirurgie cardiaque avec CEC » pédiatrique (p. 101) | Pédiatrie : seule la ligne adulte est retrouvée |
| Q28 | ✗ | ✗ | ligne « plaies cranio-cérébrales » pédiatrique (p. 95) | Pédiatrie / multipassage : encadré allergie et note trouvés, pas la ligne de l'acte |
| Q41 | ✗ | ✗ | traumatologie maxillo-faciale pédiatrique (p. 99) | Mauvaise section : tableaux de traumatologie orthopédique pédiatrique retrouvés à la place |
| Q131 | ✗ | ✗ | cathétérisme cardiaque pédiatrique (p. 102) | Mauvaise section : cardiologie structurelle adulte retrouvée |
| Q74 | ✗ | ✗ | hystéroscopie diagnostique (p. 67) | Ingestion : tableau sans en-tête (`Col 1 | Col 2 | Col 3`), pas de fiche ligne ; autre tableau de la même section retrouvé |
| Q120 | ✗ | ✗ | tableau ORL adulte (p. 41) | Ingestion : non mappable (voir plus haut) ; la preuve pédiatrique p. 96 est au rang 1 |
| Q149 | ✗ | ✗ | ligne « pneumonectomies ou lobectomies » (p. 53) | Requête au contexte nié (« sans allergie … ni BPCO ») : encadrés allergie en tête, tableau thoracique absent |
| Q157 | ✗ | ✗ | note « jusqu'à un IMC ≤ 50 kg/m² » (p. 80) | Note de bas de tableau déportée (QCM bariatrique) |
| Q171 | ✗ | ✗ | 3 des 6 preuves (pp. 41, 58, 106) | QCM à options réparties dans 4 tableaux ; la preuve p. 41 est aussi un artefact du texte layout (ligne de thyroïdectomie collée à la posologie de la ligne suivante) |
| Q27 | ✗ | ✓ | ligne craniotomie (p. 38) | Chunk voisin de l'encadré allergie |
| Q40 | ✗ | ✓ | lignes « dents incluses » (pp. 43, 98) | Tableau parent / voisins |
| Q52 | ✗ | ✓ | ligne « drainage thoracique » pédiatrique (p. 104) | Chunk voisin |
| Q139 | ✗ | ✓ | ligne prothèse de genou (p. 73) | Chunk voisin (QCM) |
| Q158 | ✗ | ✓ | ligne colectomie pédiatrique (p. 112) | Chunk voisin / tableau parent (QCM pédiatrique) |

Lecture : avec fenêtres, 6/11 échecs sont pédiatriques (tableaux du Champ 3 non atteints, ou ensembles qui exigent la variante pédiatrique pour une question sans âge), 2/11 viennent de l'ingestion, 3/11 de la formulation (contexte nié, note déportée, QCM multi-tableaux). Pistes à mesurer (une variable à la fois, sur dev) : diversification adulte/pédiatrique quand la population n'est pas précisée, rattachement des notes de bas de tableau à leurs lignes, fiches ligne pour les tableaux sans en-tête et lignes `colspan`.

## Coffre-fort

- `eval/splits/abpe171/{dev,test}.jsonl` reprennent exactement les identifiants de `eval/splits/abp171/{dev,test}.jsonl` (102 / 69, vérifié). Test scellé dans `eval/LOCKBOX.md` (SHA-256 `0408ba8c…`), historique conservé, fichiers `abp171` et `multirfe_synth` inchangés (`datasets verify` : OK).
- La normalisation a été mise au point sur le dev. Le fichier test a été régénéré puis scellé une seule fois, après stabilisation (un premier scellement non commité, fait avant la dernière correction, a été annulé avant tout usage ; aucune évaluation du test n'a eu lieu). Les questions test n'ont pas été lues.
- Limite (inscrite dans LOCKBOX) : les 171 questions ont été vues par les équipes précédentes et par Gemini Neon, qui a réglé le pipeline dessus sans jeu tenu à l'écart. Le test `abpe171` ne protège que contre nos propres réglages futurs ; il ne mesure pas la généralisation.

## Limites

- La V3.1 indexée est un overlay Markdown (V3.0 + amendements) généré par un autre agent, pas une extraction du PDF V3.1 : coquilles et libellés divergents (Q53, Q115, Q120) pénalisent le mapping. Une comparaison systématique overlay ↔ PDF reste à faire.
- La règle « au moins un fragment couvert » reste indulgente pour les preuves à plusieurs lignes sans libellé de ligne exploitable (dev : 146 preuves sur 222 couvrent plusieurs lignes ; 91 sont restreintes à la ligne annotée, 55 restent créditées sur toutes leurs lignes) : une ligne voisine du même bloc peut être créditée.
- Les fragments du benchmark viennent d'une autre version de `pdftotext` que la nôtre (mises en page différentes) ; certains entrelacements (Q171 p. 41) restent mal reconstitués.
- `evidence_sets` : une seule alternative annotée par question (pas d'OU réel) ; les ensembles n'ont pas de preuve d'exhaustivité (voir `docs/EVALUATION.md` du benchmark).
- Pas d'évaluation de génération ni de juge sur `abpe171` ici (aucun appel API) ; les nouveaux champs du juge ne sont pas calibrés.
- Droits : le README du benchmark indique que la redistribution du consolidé enrichi n'est pas autorisée en l'état. Le dépôt GitHub est **public** : le jeu converti (`eval/datasets/abpe171.jsonl`, `eval/splits/abpe171/`) et l'entrée LOCKBOX sont commités **localement mais pas poussés** ; à pousser seulement après accord de l'utilisateur.
