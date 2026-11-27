# R3 — Revue adverse avant l'évaluation sur les jeux scellés (génération, harnais, juge)

Relecteur indépendant, 2026-11-27. Périmètre : étage de génération, outil de rejeu, juge, coffre-fort, plan d'évaluation finale. Ingestion et retrieval non revus (R1, R2) ; seul le gel a été vérifié.
Méthode : lecture du code et des consignes, du diff B3 (87c436a → HEAD), de `B3_generation.md` ; `pytest` complet (150 verts) ; scripts en lecture seule dans `reports/agents/R3_annexes/` ; relecture manuelle de 60 cas jugés (dont 40 détaillés ci-dessous). Aucun `test.jsonl` ni `genprobe.jsonl` ouvert : les identifiants de test ont été obtenus par différence « jeu complet − dev » (`R3_annexes/test_id_trace.py`).
Les extraits de cas (`R3_annexes/cases_*.txt`) contiennent du texte du benchmark enrichi : ils restent locaux, non versionnés (même règle que `eval_internal/judge/runs/*abpe*/`).

## 0. Verdicts

| Question | Verdict |
|---|---|
| 1. Code et prompts de génération | **Pas de surapprentissage détecté** dans les prompts, le format de contexte et le contrôle de réponse (aucun contenu clinique, aucune trace de question). Deux éléments limites : le routage QCM (calé sur le format `A. …` du harnais, et il envoie de vraies questions cliniques en mode QCM), et les correctifs typographiques du contrôle de réponse, réglés sur les sorties dev (déclaré). |
| 2. Évalué = déployé ? | **Non.** L'API (`/api/query`, `/v1/chat/completions`) ne sert ni `C10_context_notes`, ni `tas_v6` (sauf `.env`), ni le preset `wide`, ni `clinical_concise`. Le chiffre final mesurera « contexte figé + Sonnet », pas le système servi. **Bloquant pour toute phrase du type « notre système obtient X % ».** |
| 3. Juge | v2 défendable. v3 défendable **pour les 11 questions à clarification** (conforme à `acceptable_behaviors` du benchmark), **trop indulgente pour les questions « réponse »** (`answer → [answer, conditional]` n'est pas dans le benchmark). Biais résiduels vers « correct » (pas de sources fournies au juge, règle `reference_narrative`, consignes contradictoires). Désaccord relecteur/juge : 4 à 5 verdicts de correction sur 60 (3 trop indulgents, 1–2 trop sévères) et 5 incohérences internes sur les champs structurés (toutes dans le sens indulgent). La calibration κ = 0,88 **ne couvre pas** la grille actuelle. |
| 4. Intégrité | Coffre-fort intact (`test_lockbox` vert, aucune trace d'identifiant de test dans les rapports, caches de rejeu, entrées de juge). Le test anti-fuite couvre `src/rag_sfar/generation/` mais **pas** les consignes du générateur ni celles du juge. `genprobe` : une seule exécution, retrieval seul, après le gel ; aucune trace d'usage en réglage. Réserve : l'isolation des générateurs Sonnet repose sur une consigne, et les identifiants de cas leur révèlent la question. |
| 5. Plan final | Bon principe (une exécution, dev à côté de test, `abp171` test non exécuté). **Il manque** : l'outil de rejeu ne sait pas lire un split test ; la grille, les métriques primaires, le traitement des verdicts manquants et des échecs ne sont pas figés par écrit ; le dev et le test ne seront pas jugés dans les mêmes conditions ; les IC à zéro événement sont dégénérés ; `other` n'est compté nulle part. |

## 1. Constats classés par gravité

### Critique (à corriger avant le test, ou à déclarer en tête de rapport)

**C1. Le système servi n'est pas le système évalué.**
- `src/rag_sfar/interfaces/api.py:366-371` : le moteur est construit sans `gen_config` → génération **historique** (`LEGACY` : 6 chunks / 6 500 car., format legacy, élagage de prose, note allergie), pas `wide`.
- `api.py:41` : mode par défaut `clinical_detailed` ; `api.py:511-516` (`/v1/chat/completions`, l'interface OpenAI que la plateforme du datathon appellerait) : `clinical_detailed`, ou `benchmark_open`/`benchmark_mcq` selon le nom du modèle ; jamais `clinical_concise`.
- `api.py:425-433` et `458-466` : `RetrievalConfig` construite à la volée (`final_top_k=8`, lexique médical activé, voisins/callouts activés, défauts de `RetrievalConfig()` nommée `sota_full`) ; `/v1/chat/completions` utilise `RetrievalConfig()` par défaut. Aucune des fenêtres, tableaux parents, notes de tableau ni filtres de `C10_context_notes` (`evaluation/ablation.py:255-…`).
- `config.py:26` : index par défaut `index/sota_default` (sauf surcharge `.env`, non lue ici) ; `cli.py:451-470` (`serve`) n'offre ni `--gen-preset`, ni `--configs`, ni choix de mode.
- `config.py:59` : `api_attach_provenance=True` → en déploiement, les réponses QCM sans année reçoivent « (SFAR <année de [S1]> [S1]) » ajouté par le code (`client.py:627-628`) ; désactivé en évaluation.
→ Correction minimale : un point d'entrée de service qui charge `C10_context_notes`, `tas_v6`, `resolve_generation_config("wide")`, `clinical_concise` par défaut, `answer_check="flag"`, et un test qui vérifie que ce point d'entrée et `gen_replay` produisent **le même prompt** pour une question donnée. Sinon, toute communication doit dire « configuration d'évaluation », pas « système déployé ».

**C2. L'outil de rejeu ne sait évaluer que le dev.** `eval_internal/gen_replay.py:87, 285, 376, 414, 418, 427, 448` : `load_suite(…, "dev")` et `"split": "dev"` codés en dur. Pour lancer le test il faudra modifier l'outil ; cette modification doit être faite, relue et commitée **avant** l'exécution, avec un test (le même code sur dev reproduit à l'identique les prompts déjà capturés). Attention aussi : `PROXY_KEY_SUITE` (`:60`) chargerait `abp171` test pour le « proxy » → à désactiver hors dev. Et `--index-map` vaut par défaut `tas_v3_errata` (`:506`) : `tas_v6` doit être passé explicitement (et vérifié dans `meta.json` du cache).

**C3. Le juge n'est pas tenu dans les mêmes conditions sur dev et sur test, ni à l'aveugle.**
- `judge_io.py:73` : `case_id = "<config>::<id>"` → le juge voit le nom de la variante et du générateur (« c10notes_v6|wide+dependency_note=true|claude-sonnet-5-5 »). Le spec de l'évaluateur du benchmark exige que la requête du juge soit identique quel que soit le système.
- Variance inter-lots mesurée (§3.3) : mêmes contenus, verdicts différents d'un lot à l'autre (Q61 : partiel dans un lot, correct dans l'autre ; Q44 correct alors que Q81 est partiel pour la même omission d'alternative). Les chiffres dev ont été jugés en v1, v2 puis v3 par des agents différents.
→ Juger **dev et test ensemble**, mélangés, avec des identifiants opaques, la même grille figée, la même consigne, des lots de même taille ; puis désanonymiser. Sinon l'écart dev/test mélange effet du split et effet du lot de juges.

### Majeur

**M1. `other` n'est compté nulle part.** `judge_io.py:27` : `SERIOUS` exclut `other`, alors que la grille définit `other` comme « une erreur dangereuse qui n'entre dans aucune autre catégorie » (`JUDGE_INSTRUCTIONS.md:8`) ; `judge.py:7` dit « counted apart », mais `merge` ne le rapporte pas (`judge_io.py:156-158`). De plus `judge.py:63` met `other` par défaut quand la sortie du juge API est illisible : erreur dangereuse et échec technique sont confondus. Observé une fois (`b3_r1_c9_small_abpe`, 9B). → Compter `other` dans les erreurs graves, ou le rapporter en colonne séparée ; coder l'échec technique autrement.

**M2. Le juge ne voit pas les sources : « fidélité » et `unsupported_claim` sont inopérants.** `JUDGE_INSTRUCTIONS.md:22` (« Aucune source n'est fournie : `faithful` vaut donc toujours null »). Les ajouts non présents dans la référence passent (ex. multirfe confirm : posologie d'énoxaparine ajoutée, jugée « non vérifiable ici », verdict correct). Le contrôle déterministe (`answer_check`) est le seul garde-fou sur les doses et molécules hors contexte, et il **n'est pas calculé** sur les réponses Sonnet : `gen_replay.py:334-335` le retire à l'enregistrement, `import_frontier` (`:400-433`) ne le recalcule pas. Je l'ai recalculé en lecture seule (`R3_annexes/answer_check_sonnet.py`) : 0 dose ou molécule hors contexte sur 102 + 94 réponses dev de la configuration retenue, hors deux faux positifs (dose calculée à partir du poids de la question ; citations « [S1, 2016] » du mode comparatif lues comme S2016). → Lancer `gen_replay recheck` (ou équivalent) sur les rapports finaux et rapporter `check_flag` comme métrique de sécurité.

**M3. `answer → [answer, conditional]` est plus large que le benchmark.** `judge_io.py:47-50`. Dans le fichier source, les 160 questions « réponse » portent `answer_with_evidence` (explicite pour 22, implicite pour 138) ; `conditional_answer` n'est listé que pour les 11 questions à clarification. Le spec de l'évaluateur (§6.3) dit « accepter une stratégie alternative **effectivement recevable** » : c'est un jugement au cas par cas (la question omet-elle l'élément discriminant ?), pas une acceptation générale. Effet actuel faible (2 à 3 étiquettes `conditional` sur 30 questions « réponse »), mais `judge_behavior_ok` ne peut plus jamais échouer pour une réponse qui botte en touche. → Rapporter `behavior_ok` strict (comportements du benchmark seuls) comme métrique primaire, la version élargie en secondaire ; ou demander au juge si la condition est réellement absente de la question.

**M4. Consignes du juge contradictoires et biaisées vers « correct » sur les questions à clarification.** `JUDGE_INSTRUCTIONS.md:16-17` : la règle `reference_narrative` fixe `correctness` d'après le corrigé détaillé, puis la ligne suivante dit que ces clés « n'influencent pas `correctness` ». Une simple demande de précision est « correct » sans exiger qu'elle porte sur les `required_missing_information` (le benchmark donne exactitude N/A et complétude 2 seulement si **toutes** les données indispensables sont demandées). Enfin « Trancher sans demander une précision… pas par `serious_error`, sauf si la conduite donnée est elle-même fausse » (`:8`) est plus indulgent que le spec (§6.4 : « réponses affirmatives fondées sur une hypothèse clinique injustifiée » parmi les erreurs critiques possibles) : céfazoline « pour une œsophagectomie » sans âge est fausse pour l'enfant avec plastie colique (Q85). → Clarifier : (a) correction d'après le corrigé détaillé, assumée ; (b) clarification « correcte » seulement si elle demande les informations listées ; (c) laisser le juge qualifier de grave une conduite imposée qui est fausse pour une des populations non précisées.

**M5. Le routage QCM du moteur.** `client.py:368-386`, `prompts.py:72-79`, `client.py:771-772`.
- Une question clinique ordinaire qui énumère des éléments avec `A.`/`B.` ou `A)`/`B)` en début de ligne est routée en QCM ; vérifié : « Patient de 70 ans avec : A. insuffisance rénale B. allergie à la pénicilline … » → `clinical_mcq`, l'utilisateur ne reçoit que la dernière ligne « RÉPONSE : <lettre> ».
- Des QCM écrits autrement (`a.`, `1.`, `A :`, options en ligne) ne sont pas routés. Le motif correspond exactement à `EvalItem.formatted_query()` (`datasets.py:92-95`) : le routage dépend du format du harnais, pas d'une propriété générale des questions.
- Le prompt `clinical_mcq` impose une lettre unique : un QCM sans option unique (Q163 dans le dev, cas prévu par le benchmark : « ne pas imposer une lettre ») ne peut pas obtenir un comportement accepté. Effet sur le score : pénalisant, pas flatteur.
- `clinical_mcq` est dans `BENCHMARK_MODES` : pas de contrôle de réponse (`client.py:600`), plafond 320 tokens (`:399`).
Verdict : **limite**. À déclarer ; correction souhaitable mais pas avant le test (elle changerait la configuration figée).

**M6. Le générateur substitut n'est ni le modèle déployé, ni appelé comme lui.** `GENERATOR_INSTRUCTIONS.md` :
- isolation par consigne seulement (`:9` « do not open any other file ») alors que l'agent a accès au disque ; les `gen_input_*.json` contiennent `case_id` = identifiant de la question (`gen_replay.py:332`), donc la référence est retrouvable (`eval/datasets/abp171.jsonl`, `data/benchmark_enrichi…`, `eval_internal/datasets/multirfe_synth.jsonl`, rapports Gemini) ;
- 12 cas à la suite dans un même contexte (`:5`), plus une étape de relecture « re-read the question … confirm » (`:13`) que le modèle déployé ne fait pas ;
- pas de plafond de tokens (déploiement : 320 en QCM, 1 024 par défaut, 420 en MLX — `api.py:360`), température et « réflexion » non maîtrisées (déploiement : 0, réflexion coupée) ;
- la boucle de réparation du vérificateur (`client.py:573-595`, second appel LLM si une molécule suivie est absente des extraits) ne s'exécute jamais en rejeu (`RecordingLLM` répond par une abstention, `gen_replay.py:220-230`).
→ Pour le test : identifiants opaques dans `gen_input`, agents lancés dans un dossier ne contenant que leur fichier d'entrée, et contrôle a posteriori des transcriptions des agents (aucune lecture hors `<DIR>`), consigné.

### Modéré

**m1. Bootstrap percentile sur des taux nuls.** `harness.py:39-47` : 0 erreur grave sur 69 donne un IC [0 ; 0]. Utiliser Clopper-Pearson / Wilson (0/69 → borne haute 95 % ≈ 5,2 % ; 0/57 → ≈ 6,3 %).

**m2. Verdicts manquants silencieux.** `judge_io.py:138-145` : une réponse sans verdict sort du dénominateur ; seul un compteur `missing` est écrit. Pendant cette revue, `b3_v6_c10n_confirm_mult` avait 42/64 verdicts sur disque alors que le rapport fusionné affichait déjà 64/64 (fichiers écrits entre-temps) : vérifier `missing == 0` et le nombre de verdicts **au moment** de la fusion, et figer la règle (rejuger, ou compter comme échec).

**m3. Documentation de la configuration retenue inexacte.** `B3_generation.md` (§0, §1) annonce `answer_check="flag"`, mais le preset `wide` (`settings.py:101-114`) garde `answer_check="off"` (`:78`) et les commandes de B3 ne le surchargent pas. Sans effet sur les chiffres Sonnet (le contrôle n'y est pas calculé, cf. M2), mais la configuration « figée » n'est pas celle qui est écrite.

**m4. Le test anti-fuite ne couvre pas tout ce qui façonne la réponse évaluée.** `tests/test_no_benchmark_leakage.py:27, 99-104` : seulement `src/rag_sfar/**/*.py` hors `evaluation/`. Non couverts : `eval_internal/GENERATOR_INSTRUCTIONS.md` (partie du système évalué de fait), `eval_internal/judge/JUDGE_*.md` et `evaluation/judge.py` (un exemple tiré d'une question biaiserait le juge), `eval_internal/work/b3_prompts/*.txt` (non chargés par `src/`, variantes abandonnées). Vérifié à la main : aucun texte de question dans ces fichiers aujourd'hui. → Étendre le test à ces fichiers.

**m5. Liste de molécules du vérificateur centrée antibiotiques.** `verifier.py:11-…` (antérieur à B3) : antibiotiques et anticoagulants ; ni hypnotiques, curares, morphiniques, catécholamines… La boucle de réparation et `answer_check` (complété par les suffixes DCI, `answer_check.py:38-42`) sont donc plus sensibles sur l'ABP que sur les autres RFE. Pas un surapprentissage à une question, mais un biais de domaine à déclarer.

**m6. Calibration du juge hors champ.** `eval_internal/judge/CALIBRATION.md` : vérité = clé déterministe (lettre ou molécules), pas un médecin ; ancienne référence `abp171` ; réponses courtes ; correction binaire ; grille v1 ; ni erreurs graves, ni partiel, ni comportement, ni clarification, ni multirfe. Sous-groupe le plus proche des réponses actuelles (réponses longues C8) : κ = 0,63 (n = 38).

### Mineur
- `answer_check` : les citations du mode comparatif « [S1, 2016] » sont lues comme S2016 (faux positif de citation invalide, `answer_check.py:43`) ; un produit dose × poids de la question est signalé (Q28).
- `DEPENDENCY_NOTE` et `COVERAGE_NOTE` sont désactivées mais restent dans le chemin de code ; le jeu d'identifiants « piste clarification » (commit 1aab61b) est dans `eval_internal/`, pas dans `src/` : correct.
- Le streaming (`client.py:654-768`, utilisé par la page de démonstration) ne fait pas le contrôle de réponse.

## 2. Question 1 — éléments de génération

| Élément | Fichier | Verdict | Motif |
|---|---|---|---|
| `SYSTEM_CLINICAL_CONCISE` (prompt retenu) | `prompts.py:24-33` | générique | règles de format et d'ancrage ; aucun acte, molécule, exemple. Écrit le 26/11 par l'équipe qui voyait les 171 questions : historique à mentionner, contenu neutre. |
| `SYSTEM_BENCHMARK_MCQ` / `clinical_mcq` | `prompts.py:72-79` | générique (contenu), limite (comportement) | qualificatifs génériques (« ordre de préférence, population, site, conditions ») ; lettre unique imposée, incompatible avec un QCM sans option unique. |
| `SYSTEM_CLINICAL_PRODUCTION` (rejeté) | `prompts.py:37-47` | limite | « colonne des actes », « ligne voisine » : propriétés des tableaux de l'ABP plus que des RFE en général ; non utilisé. |
| Routage QCM (`has_lettered_options`, `route_mode`) | `client.py:368-386` | **limite** | calé sur `A. ` / `A) ` en début de ligne = format du harnais ; faux positifs sur des listes cliniques ; faux négatifs sur d'autres formats de QCM. |
| Extraction de la ligne finale | `client.py:771-784` | générique, risqué | en QCM l'utilisateur ne voit que la lettre ; si le modèle refuse de choisir, le texte complet est rendu. |
| Sélection budget 40 / 30 000 | `settings.py:101-114`, `context.py:39-52` | générique | hyperparamètres réglés sur dev (déclarés). |
| Fusion de chunks adjacents, ordre par rang, numérotation | `context.py:144-205, 323-347` | générique | structurel. |
| En-tête riche (édition, section, nature, force) | `context.py:245-274` | générique | métadonnées du corpus. |
| Population tirée des titres de section | `context.py:229-242, 263-269` | générique | 4 classes (adulte, enfant, nouveau-né, obstétrique), étiquetée « (titre de section) », utilisée seulement sans étiquette structurelle. Risque : un titre « adulte et enfant » ou une exception citée dans un titre donne une étiquette trompeuse ; pas de lien avec une question. |
| Note de dépendance de population | `context.py:352-389` | limite (inactive) | motivée par les questions à clarification de l'ABP ; désactivée après mesure. |
| Note de couverture | `client.py:388-391` | générique (inactive) | |
| `answer_check` : unités, suffixes DCI, citations | `answer_check.py:27-60` | générique | listes fermées de pharmacologie. |
| `answer_check` : normalisations typographiques (HTML sub/sup, « l-1 », Gauge, valeurs de la question) | `answer_check.py:87-93, 147-161` | limite | ajoutées pour supprimer des faux positifs observés sur dev ; génériques en contenu ; déclaré dans B3 §4. |
| `answer_check` : valeur remplacée d'un erratum | `answer_check.py:62-68` | générique | format du marqueur d'ingestion. |
| `allergy_context_note` | `client.py:281-294` | générique (inactif en `wide`) | |
| Liste `TRACKED_MOLECULES` | `verifier.py` | limite (biais de domaine) | voir m5. |

Le diff B3 sur `src/rag_sfar/generation/` (87c436a → HEAD, 1 898 lignes ajoutées) ne contient aucun nom d'acte, molécule ou identifiant de question (recherche par motifs) ; `test_no_benchmark_leakage.py` passe, y compris sur les 171 questions du benchmark enrichi.

## 3. Question 2 — chemin d'une question : API contre rejeu

| Élément | API servie (`create_app`) | Rejeu d'évaluation (`gen_replay` + Sonnet) |
|---|---|---|
| Index | `Settings.index_dir` = `index/sota_default` (sauf `.env`) | `tas_v6` via `--index-map` (défaut de l'outil : `tas_v3_errata`) |
| Retrieval | `RetrievalConfig` ad hoc, `final_top_k` = 8 (requête), lexique, voisins/callouts activés ; `/v1/…` : `RetrievalConfig()` | `C10_context_notes` (16 résultats, fenêtres ±1, tableaux parents, notes, filtres d'édition) |
| Génération | `gen_config=None` → `LEGACY` (6 chunks / 6 500 car., format legacy, élagage de prose, note allergie, ordre en U) | preset `wide` (40 / 30 000, format structuré, fusion, rang, en-tête riche) |
| Prompt | `clinical_detailed` (`/api/query`, `/v1/…`) ; `benchmark_*` selon le modèle `/v1` | `clinical_concise` ; QCM routés vers `clinical_mcq` (le routage existe aussi dans l'API) |
| Plafond de sortie | 1 024 tokens (OpenAI), 420 (MLX), 320 en QCM | aucun |
| Température / réflexion | 0 ; réflexion selon le serveur | non maîtrisées (agent Claude Code) |
| Boucle de réparation molécules | oui (2e appel) | jamais exécutée |
| Contrôle de réponse | `off` (pas de `gen_config`) | non calculé sur les réponses importées |
| Provenance ajoutée par le code | oui en QCM (`api_attach_provenance=True`) | non |
| Contexte d'appel | une question par appel | 12 questions par agent, relecture finale |
| Modèle | `Settings.llm_model` (défaut `qwen2.5:14b-instruct`) ou MLX | Claude Sonnet |

**Ce que le substitut Sonnet permet d'affirmer** : sur les contextes que construit le retrieval figé, un générateur fort qui suit exactement nos prompts produit des réponses jugées conformes aux références dans X % des cas (juge Haiku, grille v3), avec Y erreurs graves ; donc le contexte contient en général de quoi répondre et le prompt n'empêche pas une bonne réponse. C'est une **estimation haute de ce que l'étage de génération peut atteindre** avec ce contexte.

**Ce qu'il ne permet pas d'affirmer** : l'exactitude, la sécurité, la latence ou le coût du système déployé ; le comportement du modèle cible (~30B, jamais mesuré) ; l'ancrage strict des réponses (Sonnet connaît une partie des RFE ; le juge ne voit pas les sources ; seul le contrôle déterministe borne les doses et molécules) ; l'effet de la boucle de réparation et du contrôle de réponse ; un comportement sur des QCM ou des listes formatés autrement que le harnais.

## 4. Question 3 — le juge

### 4.1 Les deux changements
- **v2** (`wrong_conduct`, abstention à tort non grave) : défendable. `wrong_conduct` rend la grille plus sévère ; « abstention à tort non grave » suit le spec de l'évaluateur (§6.4 : ne pas pénaliser automatiquement l'absence de réponse comme critique). Il faut seulement rapporter à part le taux d'abstention à tort (`false_abstention` déterministe et `abstained=true` & `incorrect` du juge), puisqu'il sort des erreurs graves.
- **v3, questions à clarification** : vérifié dans `questions_enriched_draft.jsonl` : 11 questions `ask_clarification` avec `acceptable_behaviors = [ask_clarification, conditional_answer]`, 160 `answer_with_evidence`. Le changement est conforme au benchmark, et l'utilisation de `narrative_fr` est légitime (le corrigé court ne dit que quoi demander). Défendable, à condition de corriger M4.
- **v3, questions « réponse »** : non conforme (M3).
- **Effet mesuré de v3** sur les mêmes réponses : lots abpe171 de 0 à +2 correctes sur 18–30 ; 8 changements de `correctness` sur 96 cas rejugés (4 lots), dont 3 sur des questions « réponse » sans lien avec la clarification (Q44 et Q42 dans un sens, Q45 dans l'autre) : c'est du bruit de re-jugement, du même ordre que l'effet de la grille.

### 4.2 Relecture de cas (60 cas, dont 40 détaillés : 18 `clarif_base`, 8 changements v2→v3, 22 `confirm_abpe`, 12 `iter_mult` ; plus 14 `confirm_mult`)
- **Accord sur `correctness`** : 55–56/60.
- **Juge trop indulgent (3)** : Q44 (alternative céfuroxime et schéma pédiatrique omis, « correct » ; les mêmes omissions sont « partielles » ailleurs : Q81 pour l'alternative, Q132 pour l'alternative et l'enfant) ; Q61 dans `c9w_iter` (« correct » sans volet pédiatrique, « partiel » dans `c10n_iter` pour le même contenu) ; Q45 dans `clarif_base` (alternative omise, « correct » ; « partiel » dans `clarif_depnote`).
- **Juge trop sévère (1–2)** : Q85 dans `clarif_depnote` (`wrong_drug` pour une céfazoline exacte chez l'adulte, contraire à la consigne `:8` mais conforme au spec du benchmark, cf. M4) ; Q42 dans `c9w_iter` passe de correct (v2) à partiel (v3) sur la même réponse (2 350 mg « plafonnés à 2 g » : `wrong_dose` acceptable).
- **Incohérences internes** (5, sens indulgent) : Q19, Q61, Q88 (`clarif_base`) et Q99 (`c10n_iter`) : `behavior = "answer"` et en même temps aucune violation de « imposer une conduite unique ». Q88 omet le cas néonatal décrit par le corrigé : la non-violation est discutable.
- **Multirfe** : verdicts justes sur les 26 cas relus ; ajouts non vérifiables acceptés (M2). 64/64 correctes en confirmation : plausible au vu des cas (questions synthétiques proches du texte), mais circularité Claude–Claude–Claude (questions générées par Claude, réponses Sonnet, juge Haiku).
- Sens global : léger biais indulgent, et une variance inter-lots du même ordre que les écarts entre configurations comparées (2 changements dans chaque sens entre C9 + fenêtres et C10).

### 4.3 La calibration
κ = 0,88 (rubrique v1, correction binaire contre une clé déterministe, ABP, réponses courtes) ne soutient pas : le partiel, les erreurs graves (dont `wrong_conduct`), le comportement, les faits obligatoires/interdits, les questions à clarification, les réponses longues (κ = 0,63 sur ce sous-groupe), les questions multirfe.
À re-mesurer, sur des réponses Sonnet du dev, avant le test : (1) accord **test-retest** du juge (mêmes réponses, deux lots indépendants) sur correct/partiel/incorrect et sur `serious_error` ; (2) accord avec une relecture humaine en aveugle (idéalement un médecin, à défaut un relecteur de l'équipe, déclaré comme tel) sur ~40 cas stratifiés, enrichis en partiels, clarifications et erreurs graves ; (3) sonde de longueur rejouée en v3.

## 5. Question 4 — intégrité

- **Coffre-fort** : `tests/test_lockbox.py` vert ; hachages de `eval/LOCKBOX.md` respectés ; `git log` : `abp171` et `multirfe_synth` test inchangés depuis le scellement ; `abpe171` test non versionné (ignoré) — son seul garde-fou est le hachage.
- **Traces d'évaluation du test** : aucun rapport avec `split ≠ dev` ; aucun identifiant de test (69 + 57, obtenus par différence) dans `reports/eval/**`, `eval_internal/work/**` (caches de rejeu, `gen_input`), `eval_internal/judge/runs/**` (`R3_annexes/test_id_trace.py`).
- **Exposition antérieure du test abpe171** (connue, à rappeler) : les rapports Gemini non versionnés `reports/benchmark_enrichi_eval*/` (26/11, avant scellement) donnent des résultats par question pour 14 questions du test (cas critiques) et `retest_9_cases.json` en contient 2 (Q58, Q152), sur lesquelles le pipeline de l'époque a été réglé. Ces fichiers sont lisibles par tout agent. → Rapporter le test abpe171 aussi **sans ces 2 questions** (et sans les 16, en analyse de sensibilité).
- **Test anti-fuite** : couvre le code de génération et les prompts de `src/`. Ne couvre pas les consignes du générateur et du juge (m4). Les fichiers `eval_internal/work/b3_prompts/` ne sont pas chargés par `src/` (seulement par `gen_replay --system-file`) et ne servent pas à la configuration retenue.
- **`genprobe`** : créé à 05:00 (8b4c98f) ; exécuté une seule fois à 07:52–07:53, retrieval seul, après le gel (07:47) ; aucune trace dans les caches de rejeu, les lots de juge ou les rapports B3 ; B1 et R2 déclarent ne pas l'avoir ouvert. Il reste exploitable pour **une** mesure de génération (jamais faite) sur 47 RFE hors ABP, si ses fiches ont des réponses de référence.

## 6. Question 5 — plan d'évaluation finale

**D'accord** : ne pas exécuter `abp171` test (références de l'édition précédente, document gold périmé). Le laisser scellé et l'écrire dans le protocole.

**Manques, à régler avant l'exécution** :
1. Corriger C2 (split test dans `gen_replay`), commit + test, et **figer par écrit** (dans un fichier commité, avec son hachage, avant le lancement) : commit de code ; hachages de `JUDGE_INSTRUCTIONS.md`, `JUDGE_TASK.md`, `GENERATOR_INSTRUCTIONS.md` ; nom des caches ; commandes exactes ; modèles (Sonnet, Haiku, identifiants) ; taille des lots ; nombre d'agents.
2. **Métriques primaires** déclarées d'avance, avec leur définition : correct (juge), correct ou partiel, erreurs graves (y compris `other`), abstention correcte sur les questions hors corpus (multirfe : 9 en test), fausse abstention, `behavior_ok` strict, contrôle déterministe (`check_flag`), sourcé ; retrieval : suffisance des preuves dans le **contexte montré** et à k fixé. Tout le reste est secondaire.
3. **Règles d'échec** : réponse manquante ou illisible = incorrecte (pas exclue) ; verdict manquant = rejugé une fois puis compté incorrect ; aucune réexécution « pour voir » ; un seul passage.
4. **Juge** : dev et test jugés dans le même passage, mélangés, identifiants opaques, sans nom de variante ni de modèle (C3) ; grille v3 corrigée (M1, M3, M4) **avant** le passage, et le dev rejugé avec elle ; idéalement deux juges indépendants par réponse sur le test, désaccords rapportés.
5. **Générateur** : identifiants opaques dans `gen_input`, dossier isolé, transcriptions contrôlées (M6) ; au plus quelques cas par agent, ordre aléatoire.
6. **Statistiques** : IC exacts (Clopper-Pearson) pour les taux rares ; bootstrap pour les autres ; écart dev − test avec IC (bootstrap non apparié, populations différentes). Dev de référence = **la confirmation** (72 + 64 questions, non utilisées pour choisir), l'itération (30 + 30) à part.
7. **Sous-groupes déclarés d'avance** : clarification (5 en test abpe171 : à rapporter en effectifs, pas en %), QCM, hors corpus, et pour abpe171 la sensibilité aux questions déjà exposées (§5).
8. **Phrase de portée** dans le rapport : générateur substitut, pas le système servi (C1).
9. Optionnel : une mesure de génération sur `genprobe` dans le même passage (troisième jeu jamais vu en génération).

## 7. Formulations autorisées pour les chiffres principaux

- « Avec un générateur de substitution (Claude Sonnet) recevant exactement les prompts de notre configuration d'évaluation (retrieval `C10_context_notes`, index `tas_v6`), X % [IC] des réponses aux 69 questions tenues à l'écart du benchmark enrichi (validées par médecin) sont jugées conformes à la référence par un juge LLM (Claude Haiku, grille v3, accord non validé médicalement sur cette grille). »
- « Sur 57 questions synthétiques (générées par LLM, non validées médicalement) portant sur 22 RFE jamais utilisées pendant la mise au point : X % [IC]. »
- « Erreurs graves détectées par le juge : n/N (borne haute IC 95 % : …) ; le juge ne voit pas les sources : les affirmations hors référence ne sont pas vérifiées, seul un contrôle automatique des doses et molécules l'est. »
- « Ces chiffres mesurent ce que l'étage de génération peut atteindre avec ce contexte ; ils ne sont pas ceux du modèle déployé, qui n'a pas été évalué. »
- **Interdit** : « notre système / notre RAG atteint X % », « validé cliniquement », « 0 erreur grave » sans IC, « répond uniquement à partir des sources » (non mesuré), comparer directement à un chiffre obtenu avec l'évaluateur officiel du benchmark (autre grille : exactitude/complétude 0–2, réussite stricte).

## 8. Fichiers
- `reports/agents/R3_annexes/judge_stats.py` — distribution des verdicts par lot et par grille.
- `reports/agents/R3_annexes/dump_cases.py` — extraction des cas jugés (sorties locales `cases_*.txt`, non versionnées).
- `reports/agents/R3_annexes/test_id_trace.py` — recherche d'identifiants de test sans ouvrir les fichiers de test.
- `reports/agents/R3_annexes/answer_check_sonnet.py` — contrôle déterministe recalculé sur les réponses Sonnet, en lecture seule.
