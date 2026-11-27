# Évaluation RAG-SFAR — format commun et coffre-fort de test

Guide pratique pour lancer les benchmarks (avec votre modèle, chaque option, API pour un évaluateur externe, jugement) : [`BENCHMARKS.md`](BENCHMARKS.md).

Ce dossier contient les jeux d'évaluation **normalisés** et leur découpage dev/test. Les jeux internes synthétiques vivent à part dans `eval_internal/` (voir son README) ; le benchmark officiel antibioprophylaxie reste dans son submodule et n'est ici que converti.

## Règles

1. Toute la mise au point se fait sur `dev`. Les fichiers `test.jsonl` sont sous coffre-fort : leur SHA-256 est inscrit dans `LOCKBOX.md` et vérifié par `pytest` (`tests/test_lockbox.py`). On ne les modifie pas et on ne les évalue qu'en fin de phase, sur les configurations finales.
2. Le split est déterministe (graine fixe), stratifié par type de question et par document source, et garde ensemble les questions d'un même `group` (quasi-doublons).
3. Chaque question porte sa **provenance** : `physician_validated`, `external_benchmark`, `llm_synthetic`, `team_written`. Les rapports ventilent les résultats par provenance.

## Format d'une question (`*.jsonl`, une question par ligne)

| Champ | Type | Obligatoire | Sens |
|---|---|---|---|
| `id` | str | oui | identifiant unique dans le jeu |
| `suite` | str | oui | nom du jeu (ex. `abp171`, `multirfe_synth`) |
| `question` | str | oui | texte posé au système |
| `question_type` | str | oui | `open`, `mcq`, `clinical_case`, `comparison`, `table`, `abstention` |
| `choices` | dict | QCM | `{"A": "...", "B": "..."}` |
| `reference_answer` | str | oui* | réponse attendue (*vide autorisé pour `abstention`) |
| `answer_key` | dict | non | clé de notation déterministe : `{"mcq": "C"}` ou `{"all_of": ["céfazoline"]}` ou `{"any_of": [...]}` ou `{"label": "pas d'antibioprophylaxie"}` |
| `should_abstain` | bool | non | vrai si le corpus ne couvre pas la question |
| `gold_doc_ids` | list[str] | non | documents qui contiennent la réponse (`doc_id` du loader) |
| `gold_passages` | list[obj] | non | `{"doc_id": ..., "quote": "..."}` : extrait verbatim (≥ 8 mots) qui porte la réponse, indépendant du chunking |
| `current_edition_required` | bool | non | la réponse doit venir de l'édition en vigueur (défaut vrai) |
| `source_doc_ids` | list[str] | non | documents dont la question est issue (pour le split « documents jamais vus ») |
| `group` | str | non | questions à garder du même côté du split |
| `provenance` | str | oui | voir règle 3 |
| `tags` | list[str] | non | ex. `allergy`, `pediatric`, `dosage`, `edition_diff` |
| `meta` | dict | non | libre (auteur, date, identifiant d'origine) |

Seuls `id`, `suite`, `question`, `question_type` et `provenance` sont strictement requis : une question sans `gold_*` n'est notée qu'en génération, une question sans `reference_answer` qu'en retrieval.

## Importer un benchmark externe (équipe `benchmark-enrichi` ou autre)

```bash
.venv/bin/python -m rag_sfar.evaluation.datasets import --input <fichier .json|.jsonl|.csv> --suite <nom> \
    --provenance physician_validated [--map question=Question reference_answer=Réponse ...]
```

`--map` relie les colonnes du fichier source aux champs ci-dessus. Le fichier normalisé est écrit dans `eval/datasets/<suite>.jsonl`, puis :

```bash
.venv/bin/python -m rag_sfar.evaluation.datasets split --suite <nom> --test-fraction 0.4
rag-sfar-eval --suite <nom> --split dev
```

## Benchmark enrichi (`abpe171`, référence)

Le benchmark des experts (`data/benchmark_enrichi_alparagsfar/benchmark_enrichi_phase1/questions_enriched_draft.jsonl`, mêmes 171 questions que `abp171`, validées par médecin, référence V3.1 provisoire) est converti par :

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.datasets convert-enriched        # -> eval/datasets/abpe171.jsonl + split
HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.datasets coverage --suite abpe171 # couverture du mapping (dev)
```

- Split : celui d'`abp171` repris par identifiant (102 dev / 69 test), test scellé dans `LOCKBOX.md`.
- Champs optionnels ajoutés au format commun (absents des anciens fichiers) : `mandatory_claims`, `forbidden_claims` ({claim_id, text, …}), `expected_behavior` (`answer` | `clarification` | `abstention`), `acceptable_alternatives`, `required_missing_information`, `evidence` ({evidence_id, doc_id, page, fragments, other_fragments}), `evidence_sets` ({set_id, required_evidence_ids}).
- `fragments` : fragments `pdftotext -layout` du benchmark normalisés (colonnes ré-assemblées et séparées par « ‖ », en-têtes de tableau retirés, une citation par ligne de tableau, lignes trop génériques écartées) ; `gold_passages` = ces fragments. `passage_match` compare une citation à colonnes cellule par cellule, sur les n-grammes porteurs d'un mot de contenu.
- `gold_doc_ids` : édition en vigueur de la RFE antibioprophylaxie dans l'index (`topic_lineage='antibioprophylaxie'`, `is_latest_edition=1`).
- `answer_key` : lettre seulement pour les QCM `single_supported` ; les questions ouvertes sont notées par le juge sur les faits obligatoires.
- Métriques supplémentaires (sur tout le contexte retourné) : `evidence_hit`, `evidence_recall` (preuves requises dont un fragment est couvert), `sufficiency` (un ensemble de preuves entièrement couvert ; ET dans l'ensemble, OU entre ensembles), avec courbes @k. Tags : `cat:*`, `difficulty:*`, `population:*`, `pediatric`, `challenge:*`, `behavior:*`.
- Juge : les cas transmettent faits obligatoires / interdits / comportement attendu / informations manquantes requises / corrigé détaillé (questions à clarification) ; la fusion agrège taux de faits satisfaits, réponses sans omission, violations d'interdits et comportement (voir « Juge LLM » ci-dessous).

## Juge LLM (grille v4, à l'aveugle, en double)

Grille : `eval_internal/judge/JUDGE_INSTRUCTIONS.md` (historique v1 → v4 à la fin) ; consigne des agents juges : `eval_internal/judge/JUDGE_TASK.md`. Le juge ne voit ni le système, ni la configuration, ni le modèle, ni le jeu, ni le split.

```bash
# 1. export à l'aveugle : réponses de plusieurs rapports (dev et test, toutes variantes) mélangées,
#    identifiants opaques, lots d'environ 25 cas ; la clé va dans eval_internal/judge/blind_keys/<run>/
HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.judge_io export-blind --run blind_<nom> \
    --reports reports/eval/b3/<A>.json reports/eval/b3/<B>.json ...
# 2. deux passes indépendantes (a, b) : un agent juge par lot et par passe, consigne JUDGE_TASK.md
#    avec <RUN> = blind_<nom>, <P> = numéro de lot, <J> = a ou b -> <RUN>/pass_<J>/judge_out_<P>.json
# 3. fusion (échoue s'il manque un verdict ; --allow-missing le compte incorrect et le liste)
HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.judge_io merge-blind --run blind_<nom> --passes a,b
```

- Les dossiers `eval_internal/judge/runs/blind_*/` et `blind_keys/` restent locaux (texte du benchmark) ; l'export refuse un dossier suivi par git.
- Sorties : `reports/eval/judge_v4/<run>/<rapport>.json|.md` (copie de chaque rapport avec les verdicts ; les rapports d'origine ne sont pas modifiés, sauf `--in-place`) et `summary.json|.md` (tous les rapports, accord entre juges).
- Combinaison déclarée d'avance (chiffres principaux) : **correct** et **comportement accepté** seulement si tous les juges l'accordent ; **erreur grave** si un juge en signale une (toutes catégories sauf `none`, `other` compris). Écart rapporté : `_any` (un juge suffit) pour les issues favorables, `_all` (tous les juges) pour les erreurs.
- Comportement : `judge_behavior_ok` strict (liste du benchmark : clarification ou réponse conditionnelle pour les questions à clarification, réponse sinon) ; secondaires : `judge_behavior_ok_lenient` (lecture v3 : réponse au cas par cas acceptée partout) et `judge_behavior_ok_case_by_case` (stratégie alternative jugée recevable par le juge, spécification de l'évaluateur §6.3).
- Abstention à tort (`judge_false_abstention`, questions couvertes) et abstention manquante (`judge_missing_abstention`, questions hors corpus) : taux à part ; l'abstention à tort n'est pas une erreur grave.
- Fidélité (`judge_faithful`) : les extraits que la réponse cite ([S1]…) sont retrouvés dans les prompts capturés par `gen_replay` et transmis au juge (4 000 caractères par extrait, 9 000 par cas) ; seulement pour `faithful` et `unsupported_claim`.
- Intervalles : Clopper-Pearson (exact) pour tous les taux 0/1 de la fusion ; bootstrap pour le taux de faits satisfaits.
- Calibration sous v4 (clé déterministe, `abp171` dev seulement, sonde de longueur) : `judge_io export-calibration --run blind_<nom>` puis `judge_io calibrate-blind --run blind_<nom> --passes a,b`.

## Lancer l'évaluation

```bash
rag-sfar-eval --suite full --split dev            # tous les jeux, split dev
rag-sfar-eval --suite abp171 --split dev --configs C0,C8 --retrieval-only
```

Sorties : `reports/eval/<horodatage>_<suite>_<split>.json` et `.md` (métriques par configuration, IC bootstrap à 95 %, ventilation par provenance et par tag, coûts API du ledger).
