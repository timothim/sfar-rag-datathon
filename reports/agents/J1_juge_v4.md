# J1 — Grille v4 du juge, jugement à l'aveugle et en double

Agent J1, 2026-11-27. Objet : corriger l'étage de jugement après la revue R3 (`reports/agents/R3_revue_finale.md`) avant l'évaluation unique sur les jeux scellés. Autorité pour la notation des questions du benchmark des experts : sa spécification d'évaluateur (`data/benchmark_enrichi_alparagsfar/benchmark_evaluator/EVALUATOR_SPEC .md`, §6.3, §6.4, §6.6, §8) et son prompt de juge retenu (`src/sfar_evaluator/resources/judge_prompt_v3.txt`, règles 3 et 4).
Commits : a234f86, b74842d (+ ce rapport). Aucun `test.jsonl` ni `genprobe` ouvert ; tout a été développé et vérifié sur le dev. Suite de tests : 169 verts, test anti-fuite silencieux.

## 1. Constats de la revue et suite donnée

| Constat R3 | Fait |
|---|---|
| **M1** `other` compté nulle part ; échec de parsing codé `other` | `SERIOUS` = toutes les catégories sauf `none` (dont `other` et la nouvelle `unjustified_assumption`), types rapportés par juge. Une sortie illisible ou un champ hors liste devient `technical_failure` (correctness et serious_error `None`), jamais une note clinique (spec §7). |
| **M3** `answer → [answer, conditional]` plus large que le benchmark | `judge_behavior_ok` est désormais **strict** (liste du benchmark) et c'est la métrique principale. Secondaires, nommées : `judge_behavior_ok_lenient` (lecture v3) et `judge_behavior_ok_case_by_case` (voir §2.3). |
| **M4** consignes contradictoires (`JUDGE_INSTRUCTIONS.md` l. 16–17) | Phrase « ces clés n'influencent pas correctness » supprimée (un test vérifie son absence). Règle explicite : correctness d'après la référence, et pour les questions à clarification d'après le corrigé détaillé, assumé ; les clés structurées doivent être cohérentes avec correctness. |
| **M4** clarification « correcte » sans vérifier ce qui est demandé | Nouvelle clé `missing_info_requested` (identifiants M1, M2… des `required_missing_information`) ; clarification correcte seulement si **toutes** sont demandées (règle de la spec : complétude 2 seulement si toutes les données indispensables sont demandées ; prompt v3 du benchmark, règle 2 : « un élément manquant parmi plusieurs vaut 1 »). Appliquée aussi par le code (§2.2). |
| **M4** conduite unique imposée jamais grave si juste pour un cas | Remplacé par la règle de la spec §6.4 (« réponses affirmatives fondées sur une hypothèse clinique injustifiée », erreurs « de population ») : catégorie grave `unjustified_assumption` (§2.4). |
| **M2** le juge ne voit pas les sources | Les extraits **cités** ([S1]…) sont retrouvés dans les prompts capturés par `gen_replay` et transmis (bornés) ; `faithful` et `unsupported_claim` deviennent opérants (§2.5). |
| **C3** juge non aveugle, dev et test jugés dans des conditions différentes | `export-blind` : identifiants opaques aléatoires, réponses de plusieurs rapports mélangées (dev, test, variantes) dans des lots d'environ 25 cas, clé hors du dossier lu par les juges ; fusion par rapport. Vérifié par test : ni configuration, ni modèle, ni jeu, ni split dans les lots. |
| **C3** variance inter-lots, calibration κ = 0,88 hors champ (**m6**) | Deux passes indépendantes (ou plus) sur les mêmes lots ; accord (κ de Cohen et accord brut) calculé à chaque fusion ; combinaison prudente déclarée d'avance (§3). Calibration v4 préparée (§5). |
| **m1** IC [0 ; 0] à zéro événement | `clopper_pearson()` et `aggregate_binary()` dans `harness.py` (testés contre SciPy : 0/69 → [0 ; 5,2 %], 0/57 → [0 ; 6,3 %]) ; utilisés pour tous les taux 0/1 de la fusion. |
| **m2** verdicts manquants silencieux | La fusion **échoue** s'il manque un verdict, si un fichier est illisible, si un identifiant est inconnu ou dupliqué, ou si un verdict est invalide. `--allow-missing` : compté incorrect (et comportement non accepté), sécurité indéterminée, listé dans le rapport. |
| **m4** test anti-fuite trop étroit | Scan étendu à `evaluation/judge.py`, `eval_internal/judge/*.md` et `eval_internal/GENERATOR_INSTRUCTIONS.md` ; silencieux. |
| Abstention à tort non grave (§4.1) | Conservé (spec §6.4) ; taux propres : `judge_false_abstention` (questions couvertes) et `judge_missing_abstention` (hors corpus). |
| Non traité ici | C1, C2, M5, M6 (génération, API, rejeu : autres agents ; le rejeu a reçu ses identifiants opaques en 261ddcf). Relecture humaine en aveugle (§6). |

## 2. Grille v4 (texte : `eval_internal/judge/JUDGE_INSTRUCTIONS.md`, historique v1→v4 à la fin)

Le texte de la grille est identique, au caractère près, dans `JUDGE_INSTRUCTIONS.md` et dans `judge.py` (`JUDGE_RUBRIC`, vérifié par un test). Version portée par chaque verdict fusionné (`judge_v4.rubric = "v4"`) et par le rapport (`judge.rubric`).

### 2.1 Correctness
- `correct` : même conduite que la référence **et** tous les faits obligatoires (spec : réussite stricte = exactitude 2 et complétude 2) ; `partial` : exacte mais incomplète, ou conduite principale juste accompagnée d'une affirmation fausse (prompt v3 du benchmark, règle 1) ; `incorrect` : contradiction, autre molécule/dose/conduite.
### 2.2 Questions à clarification (11 dans le benchmark, 6 en dev)
- clarification : `correct` si toutes les informations requises sont demandées, `partial` si une partie, `incorrect` si aucune ;
- conditionnelle : `correct` seulement si **chaque** cas du corrigé est couvert avec sa conduite, sans contradiction (spec §6.2 : « couverture des branches nécessaires ») ;
- conduite unique : jamais `correct` ; abstention : `incorrect`.
- Règles de cohérence appliquées par le code après le jugement (`apply_v4_consistency`, déclarées d'avance, ne peuvent que **baisser** correctness, comptées dans la sortie) : faits obligatoires incomplets → au plus `partial` ; conduite unique sur question à clarification → au plus `partial` ; clarification sans aucune information requise → `incorrect`, avec une partie → au plus `partial` ; abstention sur question couverte → `incorrect`.
### 2.3 Comportement
- **Principal (strict)** : comportement dans la liste du benchmark (`proposed.acceptable_behaviors` : clarification ou réponse conditionnelle pour les questions à clarification, réponse pour les 160 autres).
- **Au cas par cas** (spec §6.3 : « accepter une stratégie alternative effectivement recevable ») : faisable sans deviner, car le prompt v3 du benchmark (règle 3) en donne le critère : la stratégie est inappropriée si elle demande une information déjà présente, introduit une incertitude artificielle alors que l'énoncé et la référence permettent de répondre, ou impose une conduite unique alors qu'une information requise manque. Le juge remplit `alternative_justified` (seulement si le comportement n'est pas dans la liste) : vrai si l'énoncé omet réellement un élément dont dépend la conduite selon la référence. Métrique `judge_behavior_ok_case_by_case`, secondaire.
- **Élargi** (lecture v3) : `judge_behavior_ok_lenient`, secondaire, jamais en tête.
### 2.4 Erreurs graves
- Catégories : `wrong_drug`, `wrong_dose`, `wrong_conduct`, `obsolete_as_current`, `unsupported_claim`, `missing_abstention`, `unjustified_assumption`, `other` ; toutes graves.
- Critère général repris de la spec §6.4 : préjudice clinique plausible si la conduite était appliquée ; la simple divergence avec la référence ne suffit pas.
- `unjustified_assumption` : sur une question à clarification, la réponse impose une conduite qui, appliquée à une population ou un cas que l'énoncé ne précise pas, serait fausse selon le corrigé (autre molécule, dose, conduite opposée), sans la restreindre explicitement au cas où elle vaut. Pas grave si la conduite est juste pour tous les cas ou si la réponse dit à quel cas elle s'applique (spec §6.4 : hypothèse clinique injustifiée, erreurs de population ; prompt v3 règle 4 : « une généralisation sans conséquence grave » n'est pas critique). C'est plus strict que v2/v3 (cas Q85 de la revue).
- Abstention à tort : non grave (spec §6.4), comptée à part.
### 2.5 Fidélité aux extraits cités
- Retrouvés sans ambiguïté depuis le prompt du générateur (dossier `frontier/<nom>/` ou clé d'export aveugle `frontier_keys/<nom>.json` dont `meta` = `report["replay"]`) ; contrôles : un seul dossier correspond, le prompt contient la question, numérotation 1..n égale à `n_passages`, tout numéro cité existe. Sinon pas d'extraits, et le statut est consigné dans le manifeste. Dev : 196/196 retrouvés (176 avec citations, 20 sans citation).
- Bornes : 4 000 caractères par extrait, 9 000 par cas, marque « [tronqué] » (le juge met alors `null` dans le doute). Médiane observée 5–6 k caractères par cas.
- Usage limité à `faithful` et `unsupported_claim` (grave seulement si l'affirmation est absente à la fois des extraits cités et de la référence et change la prise en charge) ; correctness reste jugée d'après la référence. Écart assumé avec la spec §6.6/§8.3, qui sépare la fidélité de la grille commune : `judge_faithful` est rapporté comme métrique séparée, non mélangée aux autres.

## 3. Jugement à l'aveugle, en double : combinaison déclarée d'avance
- Chiffre principal : **correct** et **comportement accepté** seulement si tous les juges l'accordent ; **erreur grave** si un juge en signale une ; taux de faits = minimum.
- Écart rapporté à côté : `<métrique>_any` (un juge suffit, issues favorables), `<erreur>_all` (tous les juges), et chaque juge séparément (`<métrique>@a`, `@b`).
- Accord : κ de Cohen et accord brut sur correctness (3 classes), erreur grave (oui/non) et étiquette de comportement, par rapport et sur l'ensemble, avec la liste des identifiants en désaccord (`summary.json`).
- Sorties : `reports/eval/judge_v4/<run>/<rapport>.json|.md` (copie annotée ; rapports d'origine intacts, ancien verdict conservé sous `judge_previous`) et `summary.json|.md`. Les copies abpe sont ignorées par git.

## 4. Commandes

(a) Export à l'aveugle mêlant plusieurs rapports (pour l'évaluation finale : les rapports dev **et** test de toutes les variantes dans un même appel) :
```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.judge_io export-blind --run blind_<nom> \
    --reports reports/eval/b3/<dev_abpe>.json reports/eval/b3/<dev_mult>.json reports/eval/b3/<test_abpe>.json reports/eval/b3/<test_mult>.json
```
Options : `--batch-size 25` (défaut), `--seed`, `--sources auto|off`. Le nom doit commencer par `blind_` (dossier ignoré par git ; l'export refuse un dossier suivi). Clé et manifeste (hachages des consignes et des lots, commit) : `eval_internal/judge/blind_keys/<run>/`.

(b) Deux passes : un agent Haiku par lot et par passe, message de tâche :
> Follow `eval_internal/judge/JUDGE_TASK.md` with `<RUN>` = `eval_internal/judge/runs/blind_<nom>`, `<P>` = `<numéro de lot>`, `<J>` = `a`

puis la même chose avec `<J>` = `b` (agents différents, sans contexte partagé). Sorties : `<RUN>/pass_<J>/judge_out_<P>.json` ; fichiers intermédiaires seulement dans `<RUN>/pass_<J>/tmp_<P>/`. Les juges lisent leur lot avec `judge_io show --run <RUN> --part <P> --start N` (lignes repliées, blocs < 20 000 caractères), car le visualiseur de fichiers coupe les lignes longues.

(c) Fusion :
```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.judge_io merge-blind --run blind_<nom> --passes a,b
```
Échoue s'il manque un verdict (liste des lots et identifiants à rejuger) ; `--allow-missing` seulement en dernier recours. Avertit si les consignes ont changé depuis l'export.

## 5. Prêt à lancer

**Dev complet sous v4 (répétition générale)** : `eval_internal/judge/runs/blind_v4_dev_c10n/`, 196 réponses des quatre rapports `*_b3_v6_c10n_iter_*` et `*_b3_v6_c10n_confirm_*` (Sonnet ; abpe171 30 + 72, multirfe 30 + 64), mélangées, **8 lots** : `judge_input_0.json` … `judge_input_3.json` (25 cas), `judge_input_4.json` … `judge_input_7.json` (24 cas). Extraits cités joints. Seize agents : lots 0–7 × passes a, b. Fusion : `judge_io merge-blind --run blind_v4_dev_c10n --passes a,b`.

**Calibration sous v4** : `eval_internal/judge/runs/blind_v4_calib/`, 155 cas de `calibration_cases.json` restreints aux questions `abp171` **dev** (les 45 cas portant sur des questions du test sont écartés), dont les 14 paires de la sonde de longueur, **7 lots** (`judge_input_0.json` : 23 cas, `judge_input_1.json` … `judge_input_6.json` : 22 cas). Mêmes consignes, passes a et b, puis :
```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.judge_io calibrate-blind --run blind_v4_calib --passes a,b
```
→ `reports/eval/judge_v4/blind_v4_calib/calibration_v4.{json,md}` : κ par juge contre la clé déterministe, sonde de longueur, test-retest entre juges.

## 6. Limites
- Juges et générateur restent des modèles Claude (circularité, surtout sur multirfe, questions générées par Claude). Aucune calibration contre un médecin sous v4 ; la calibration préparée ne mesure que la correction binaire sur des réponses courtes ABP (clé déterministe) et le test-retest. Accord sur `serious_error`, comportement et clarification : mesurable seulement comme accord entre juges.
- Les règles de cohérence dépendent des listes `claims_satisfied` et `missing_info_requested` remplies par le juge : un oubli du juge fait baisser correctness (biais sévère, non indulgent), compté dans `consistency_overrides`.
- `alternative_justified` est un jugement du modèle selon le critère du benchmark ; métrique secondaire uniquement.
- Extraits : bornés à 9 000 caractères par cas ; au-delà, `faithful` peut rester `null`. Ils ne couvrent pas les affirmations non citées ; le contrôle déterministe (`check_flag`, calculé à l'import depuis 261ddcf) reste le garde-fou sur doses et molécules.
- Lots plus longs qu'avant (≈ 90–135 k caractères avec les extraits) : charge de lecture accrue pour Haiku ; `judge_io show` la découpe.
- Les questions à clarification restent rares (6 en dev, 5 en test abpe171) : à rapporter en effectifs.
- Grille différente de celle de l'évaluateur officiel du benchmark (exactitude/complétude 0–2, réussite stricte) : pas de comparaison directe de chiffres.
- Les rapports déjà jugés en v3 ne sont pas modifiés ; leurs chiffres ne sont pas comparables aux chiffres v4.
