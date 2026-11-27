# Lancer les benchmarks : guide pratique

Pour qui a le dépôt, le dossier `index/tas_v6` et un point d'accès compatible OpenAI (par exemple un Qwen servi par vLLM). Toutes les commandes se lancent à la racine du dépôt.

```bash
export HF_HUB_OFFLINE=1                       # modèles e5-small et mmarco déjà en cache
export RAG_SFAR_LLM_BASE_URL=https://…/v1     # point d'accès du modèle
export RAG_SFAR_LLM_MODEL=<modèle>
export RAG_SFAR_LLM_API_KEY=<clé>             # par variable d'environnement : la clé ne passe pas dans l'historique
```

Les options `--base-url`, `--model` et `--api-key` des commandes ci-dessous remplacent ces variables. Sans `--api-key`, la clé vient de `RAG_SFAR_LLM_API_KEY`.

Chaque commande porte une marque :
- **[exécutée]** : lancée par nous sur quelques questions de dev (`multirfe_synth`, 8 questions ; `abpe171`, 5 questions), avec un serveur de substitution à la place du vrai modèle (`scripts/standin_openai_server.py`). Ce serveur répond dans le bon format, mais ses réponses n'ont aucun sens.
- **[non exécutée]** : la raison est donnée à côté.

Aucune commande n'a été lancée avec un vrai modèle de langage.

## 0. Les jeux et les règles

| Suite | Contenu | Statut |
|---|---|---|
| `abpe171` | benchmark des experts (antibioprophylaxie V3.1), 102 dev / 69 test | validé par des médecins, **référence** |
| `abp171` | mêmes 171 questions, ancien format avec clés de réponse | validé par des médecins |
| `multirfe_synth` | 94 dev ; test sur 22 RFE jamais vues | synthétique (LLM), non validé |
| `genprobe`, `genprobe2` | sondes hors antibioprophylaxie | synthétiques, **tenues à l'écart** |

- **Dev** : on y fait toute la mise au point. C'est le split par défaut (`--split dev`).
- **Test scellé** : l'empreinte SHA-256 des fichiers `test.jsonl` est inscrite dans `eval/LOCKBOX.md` et vérifiée par `pytest`. On ne lance le test qu'une fois, sur la configuration finale (`--split test --allow-test`). Ne réglez rien sur ses résultats.
- **Jeux tenus à l'écart** (`genprobe`, `genprobe2`) : un seul passage par configuration finale. Ils ne servent pas à la mise au point.

## (a) Recherche seule : configuration gelée contre une variante

**Options de la recherche, sans modèle de langage** [exécutée, 10 questions de `multirfe_synth` dev] :

```bash
scripts/with_gpu_lock.sh MOI rag-sfar-eval --suite abpe171 --split dev --configs C10 \
    --index-map table_aware_sota=tas_v6 --retrieval-only \
    --ablate use_crag_multihop=true,use_subword=true --report-dir <dossier>
```

- La commande évalue la configuration gelée `C10_context_notes`, puis une variante par élément de `--ablate`, et imprime les comparaisons appariées (bootstrap).
- `--index-map table_aware_sota=tas_v6` est **obligatoire**. Sans elle, l'outil charge un autre index que celui qui a été évalué.
- `--report-dir` choisit le dossier des rapports (par défaut `reports/eval/`). `--output-dir` ne sert qu'à l'ancien chemin sans `--suite`.
- `--limit N` limite le nombre de questions.
- Les métriques portent sur les k = 8 premiers passages (`--k`). Ce n'est pas le contexte complet que lit le générateur.
- `scripts/with_gpu_lock.sh` sert à notre machine partagée. Ailleurs, lancez la commande sans ce préfixe.

**Avec les variantes servies par l'API (normalisation, décomposition) et mesure sur le contexte que lit le générateur** [exécutée, 8 questions `multirfe_synth` et 5 questions `abpe171`] :

```bash
# 1. capture de la recherche, une fois par variante (gelée, puis la variante)
python eval_internal/gen_replay.py capture --suite abpe171 --profile production --name gele
python eval_internal/gen_replay.py capture --suite abpe171 --profile production --name norm \
    --robustness normalize --backend openai --model $RAG_SFAR_LLM_MODEL
# 2. contexte du générateur, sans appel au modèle (backend record)
python eval_internal/gen_replay.py run --cache gele --suite abpe171 --profile production --backend record --tag gele_rec --out-dir <dossier>
python eval_internal/gen_replay.py run --cache norm --suite abpe171 --profile production --backend record --tag norm_rec --out-dir <dossier>
# 3. comparaison appariée
python eval_internal/gen_replay.py compare <dossier>/*_gele_rec.json <dossier>/*_norm_rec.json \
    --metrics sufficiency,evidence_recall,passage_hit,doc_hit,normalize_changed,decompose_fired,context_chars
```

Les caches vont dans `eval_internal/work/replay/<nom>/` (ou sous `--replay-dir`, à répéter à l'étape `run`). Les rapports vont dans `reports/eval/b3/` (ou sous `--out-dir`).

## (b) Benchmark complet avec votre modèle

Le profil évalué s'appelle `production`. Il fixe la recherche `C10_context_notes` sur `tas_v6`, le préréglage de génération `wide`, le mode `clinical_concise` et l'aiguillage des QCM. C'est exactement ce que sert l'API (le test `tests/test_generation_b3.py::test_api_prompt_identical_to_replay_prompt` vérifie que les prompts sont identiques à l'octet près).

**Profil évalué** [exécutée] :

```bash
python eval_internal/gen_replay.py capture --suite abpe171 --profile production --name gele
python eval_internal/gen_replay.py run --cache gele --suite abpe171 --profile production \
    --backend openai --model $RAG_SFAR_LLM_MODEL --tag qwen_gele
```

**Une option à la fois** : changez seulement l'étape `capture`. L'étape `run` reste identique, avec un autre `--cache` et un autre `--tag`.

| Cas | Options de `capture` | Appel au modèle avant la recherche | Statut |
|---|---|---|---|
| gelé (référence) | *(aucune)* | non | [exécutée] |
| lexicale | `--robustness lexical` | non | [exécutée] |
| normalisation | `--robustness normalize --backend openai --model M` | 1 par question (+1 par sous-question si la décomposition se déclenche) | [exécutée] |
| lexicale + normalisation | `--robustness both --backend openai --model M` | idem | [exécutée] |
| décomposition | `--decompose --backend openai --model M` | 1 par question | [exécutée] |
| normalisation + décomposition | `--robustness normalize --decompose --backend openai --model M` | 1 + 1 (+ sous-questions) | [exécutée] |
| ancien module CRAG | `--configs C10_context_notes --index-map table_aware_sota=tas_v6 --ablate use_crag_multihop=true` (à la place de `--profile`) | non | [exécutée] |

- Les appels de normalisation et de décomposition passent par le même client que l'API (`interfaces/generator_runtime.py`), avec `temperature=0`, 200 tokens au plus et la réflexion coupée (`enable_thinking=false`). Si votre serveur refuse ce champ, ajoutez `--no-thinking-flag`. Le modèle peut alors « réfléchir » dans ses 200 tokens et sortir du format. Dans ce cas, la sortie gelée est gardée et l'erreur est comptée.
- Un modèle local MLX s'utilise avec `--backend mlx --mlx-model-path <dossier>`.
- **Ce qui est enregistré** :
  - le `meta.json` du cache donne la variante (`robustness`, `decompose`), le modèle des appels préalables (`pre_retrieval_llm`), l'index (`index_map`, `index_dirs`), la configuration et le commit ;
  - chaque ligne du cache décrit ce qu'ont fait les étapes (`pre_retrieval` : question normalisée, sous-questions, erreurs de format) ;
  - le rapport de `run` reprend ces champs (`replay.cache_meta`, `generator`) et donne les taux `normalize_changed` et `decompose_fired` ;
  - `capture` imprime ces taux.
- Avec toutes les options par défaut, `capture` produit exactement le même cache qu'avant l'ajout de ces options. Nous l'avons vérifié sur 8 questions : passages et analyse identiques, seules les latences diffèrent.
- Pour comparer deux runs : `gen_replay.py compare A.json B.json` (bootstrap apparié).

## (c) Avec et sans l'ancien module CRAG, avec et sans décomposition

| | Ce que c'est | Appel au modèle | Activer | Désactiver |
|---|---|---|---|---|
| **Ancien module « CRAG »** (`retrieval/crag.py`, drapeau `use_crag_multihop`) | règles sans modèle : il repère des « facettes » cliniques de la question (porteur de BMR, obésité, insuffisance rénale, pédiatrie…), lance des sous-requêtes et une recherche de secours si une facette manque dans les passages | non | `--ablate use_crag_multihop=true` (`rag-sfar-eval`, ou `capture` avec `--configs/--index-map`) | défaut (désactivé dans `C10_context_notes`, mesuré sans effet) |
| **Décomposition** (`retrieval/multi_query.py`, mode `decompose`) | un appel court lit la question seule et répond `SIMPLE` ou `MULTIPLE` avec 2 ou 3 sous-questions. Chaque sous-question est cherchée, et chacune reçoit une part garantie du contexte | 1 par question | `capture --decompose --backend …` ; API : `"decompose": true` ou `RAG_SFAR_DECOMPOSE=1` | défaut |

Rappel des mesures (dev, générateur de substitution Claude) :
- CRAG : sans effet, donc désactivé.
- Décomposition : inerte sur les questions ordinaires (0/102 `abpe171`, 2/94 `multirfe`). Sur 16 questions à deux sources écrites pour le développement : +12,5 points de suffisance, IC [0 ; +31] (`reports/agents/X2_decomposition.md`).

Aucune de ces options n'a été mesurée avec un modèle d'environ 30B. Un tel modèle pourrait déclencher la décomposition plus souvent, d'où le taux `decompose_fired` dans les rapports.

L'ordre des étapes est fixe : décomposition (lit la question brute) → normalisation → développement des sigles → recherche gelée. Le générateur reçoit toujours la question d'origine.

## (d) Brancher un évaluateur externe sur l'API

```bash
scripts/with_gpu_lock.sh MOI rag-sfar-serve --host 127.0.0.1 --port 8000
```

[exécutée avec le serveur de substitution]

Le serveur lit le générateur dans `RAG_SFAR_LLM_*` et les défauts des options dans les variables suivantes :
- `RAG_SFAR_DEMO_ROBUSTNESS` (`none` | `lexical` | `normalize` | `both`, défaut `none`) ;
- `RAG_SFAR_DECOMPOSE` (`0` | `1`, défaut `0`).

Une valeur passée dans la requête l'emporte sur ces défauts. Sans rien préciser, le serveur sert le profil gelé évalué.

**Point d'accès compatible OpenAI** : `POST /v1/chat/completions`. Le dernier message `user` est la question.

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "rag-sfar-sota",
  "messages": [{"role": "user", "content": "Quelle antibioprophylaxie pour une cholécystectomie par coelioscopie ?"}],
  "robustness": "normalize", "decompose": false}'
```

Avec le SDK OpenAI, les champs `robustness` et `decompose` passent par `extra_body={"robustness": "normalize", "decompose": True}`.

Champs de la réponse :
- `choices[0].message.content` : la réponse, avec ses citations [S1]… ;
- `sfar_citations` : une entrée par passage du contexte, dans l'ordre des [Sn] (`citation_id`, `doc_id`, `doc_title`, `effective_year`, `version_label`, `section_path`, `grade_levels`, `is_latest_edition`, `superseded_by`, `excerpt`, `chunk_type`, `score`…) ;
- `sfar_verification` : contrôle automatique (citations invalides, molécules absentes des passages) ;
- `sfar_variant` : variante utilisée (`used`, `retrieval_config`, `decompose`, `normalization`, `decomposition`, `expansions`, `unavailable`) ;
- `usage`.

Le modèle `rag-sfar-benchmark-open` (ou `rag-sfar-benchmark-mcq`) choisit les modes `benchmark_open` et `benchmark_mcq`. Ces modes **ne sont pas** le profil évalué. Utilisez `rag-sfar-sota` pour mesurer ce qui a été évalué.

**API native** : `POST /api/query` avec `{"query": "...", "robustness": "none", "decompose": false, "retrieval_only": false}`. Elle renvoie `answer`, `citations`, `retrieved_chunks` (passages complets, avec leur texte), `verification`, `latency_ms`, `token_usage`, `config_name` et `extra.variant`. `"retrieval_only": true` renvoie les passages sans appeler le modèle. `POST /api/query/stream` donne les mêmes informations en flux d'évènements (SSE).

Le choix vaut par requête, mais les appels préalables utilisent le générateur configuré sur le serveur. Sans générateur, `normalize` retombe sur `none`, `both` sur `lexical` et la décomposition est coupée. Le champ `unavailable` le signale.

## (e) Importer le benchmark des experts et le format des jeux

Le benchmark des experts n'est pas redistribué dans ce dépôt. Une fois leur dépôt placé sous `data/benchmark_enrichi_alparagsfar/` :

```bash
python -m rag_sfar.evaluation.datasets convert-enriched          # -> eval/datasets/abpe171.jsonl, split repris d'abp171
python -m rag_sfar.evaluation.datasets coverage --suite abpe171  # part des preuves retrouvables dans l'index (dev)
```

- `coverage` : [exécutée] (102 questions dev, 341 des 348 passages de référence retrouvés dans l'index).
- `convert-enriched` : [exécutée] vers un nom de suite temporaire avec `--split-like ''` (171 questions), fichier supprimé ensuite. Nous ne l'avons pas relancée sur `abpe171` : elle réécrirait les fichiers en place, et le test scellé est protégé (`--force` exigé).

Un autre jeu (CSV, JSON ou JSONL) s'importe avec l'adaptateur [exécutée, sur un CSV de 2 lignes vers `--out-dir`] :

```bash
python -m rag_sfar.evaluation.datasets import --input <fichier> --suite <nom> --provenance physician_validated \
    --map question=<colonne> reference_answer=<colonne>
python -m rag_sfar.evaluation.datasets split --suite <nom> --test-fraction 0.4    # [non exécutée] : écrirait un split dans eval/
```

Le format des champs et les règles du split sont décrits dans `eval/README.md`. Ne réglez rien sur `test` ni sur `genprobe`/`genprobe2` (voir §0).

## (f) Juger les réponses

Notre juge (grille v4, deux passes à l'aveugle) tourne comme sous-agents Claude Code qui lisent des lots exportés. Vous ne l'aurez pas sur la plateforme. Trois possibilités :

1. **Clés déterministes**, sans juge [exécutée] :
   - `run` calcule `correct` quand la question a une `answer_key` (lettre de QCM pour les QCM `abpe171` à réponse unique, termes obligatoires ou étiquette pour `abp171`) ;
   - `run` calcule aussi `abstention_correct` / `false_abstention` sur les questions hors corpus, `sourced` (réponse citée) et `check_flag` (dose ou molécule absente des passages) ;
   - ces clés ne couvrent pas les questions ouvertes d'`abpe171` (`correct` y vaut « — »).
2. **L'évaluateur des experts** (`data/benchmark_enrichi_alparagsfar/benchmark_evaluator`, `python -m sfar_evaluator`, voir son README). Il prend des prédictions JSONL et un manifeste, et son juge se configure par un fichier TOML qui pointe vers le modèle de votre choix. Pour convertir un rapport de `run` en prédictions [exécutée] :
   ```bash
   python eval_internal/gen_replay.py export-predictions <rapport>.json --out predictions.jsonl
   ```
   Chaque ligne a la forme `{question_id, status, answer}`, et `question_id` reprend l'identifiant du benchmark (`ABP-LEG-Q01`). L'évaluation elle-même n'a pas été lancée : elle demande le manifeste de run et la configuration du juge de l'organisateur.
3. **Notre grille avec votre modèle** [non exécutée : il n'existe pas de script qui appelle un modèle juge] :
   - exporter : `python -m rag_sfar.evaluation.judge_io export-blind --run blind_<nom> --reports <rapports>` ;
   - pour chaque lot `eval_internal/judge/runs/blind_<nom>/judge_input_<P>.json`, envoyer `eval_internal/judge/JUDGE_INSTRUCTIONS.md` comme consigne et les cas du lot à votre modèle ;
   - écrire `pass_<J>/judge_out_<P>.json` au format défini dans ces instructions (voir aussi `JUDGE_TASK.md`) ;
   - fusionner : `judge_io merge-blind --run blind_<nom> --passes a,b`.

**Ce qui est validé et ce qui ne l'est pas** :
- Les questions et les références d'`abpe171`/`abp171` sont validées par des médecins.
- Notre juge LLM **ne l'est pas** : il n'a été calibré que contre des clés déterministes.
- `multirfe_synth`, `genprobe` et `genprobe2` sont synthétiques et non validés.
- Les résultats de référence ont été obtenus avec un générateur de substitution (Claude Sonnet), pas avec un modèle d'environ 30B (`reports/FINAL_REPORT.md`).

## Vérifier l'installation sans modèle

```bash
python scripts/standin_openai_server.py --port 8099 &     # faux point d'accès : formats corrects, contenu sans valeur
python eval_internal/gen_replay.py capture --suite multirfe_synth --profile production --robustness both --decompose \
    --backend openai --base-url http://127.0.0.1:8099/v1 --model standin --name essai --ids-file <ids.json>
```

`<ids.json>` vaut `{"ids": ["MR-…", …]}`. Le serveur compte les appels de chaque type sur `GET /stats`.
