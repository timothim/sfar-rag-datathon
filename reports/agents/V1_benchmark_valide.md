# V1 — Benchmark enrichi validé (sfar-abp-v31.1 / v31.2) : différences, nouvelles suites, retrieval

Agent V1, 2026-11-27. Source : dépôt des experts AlpaRagSfar, commit `7d1e7fc`, extrait dans `data/benchmark_alparagsfar_20261127/` (l'ancien clone `data/benchmark_enrichi_alparagsfar/`, commit `eabcefc`, n'est pas touché). Aucun texte du benchmark dans ce rapport ni dans les fichiers commités : identifiants et agrégats seulement.

## 1. Brouillon → version validée (171 identifiants)

- `revision_v31/data/standard.jsonl` et les 171 lignes standard de `questions_validated.jsonl` (release `sfar-abp-v31.2-200`) ont un contenu clinique identique : seules les métadonnées d'approbation (`status`, `review.*`, `review_required`) diffèrent.
- Script : `eval_internal/benchmark_valide/build.py` ; identifiants par champ : `eval_internal/benchmark_valide/diff_ids.json`.

| Champ | Total | dev (102) | test (69) |
|---|---:|---:|---:|
| Énoncé de la question | 0 | 0 | 0 |
| Choix QCM | 0 | 0 | 0 |
| Comportement attendu (`expected_behavior`) | 10 | 6 | 4 |
| Comportements acceptables (`acceptable_behaviors`) | 28 | 15 | 13 |
| Clé / politique QCM | 2 | 1 | 1 |
| Faits obligatoires | 37 | 20 | 17 |
| Faits optionnels | 37 | 20 | 17 |
| Affirmations interdites | 37 | 20 | 17 |
| Informations manquantes requises | 10 | 6 | 4 |
| Informations d'individualisation (nouveau champ) | 37 | 20 | 17 |
| Fragments de preuve | 0 | 0 | 0 |
| Ensembles de preuves | 0 | 0 | 0 |
| Réponse de référence courte | 34 | 18 | 16 |
| Réponse de référence détaillée | 37 | 20 | 17 |
| **Au moins un champ** | **37** | **20** | **17** |

- Les 37 sont exactement la liste `clinical` du manifeste des experts : Q08, Q14, Q16, Q17, Q19, Q22, Q28, Q33, Q37, Q38, Q40, Q41, Q42, Q43, Q55, Q61, Q62, Q63, Q67, Q75, Q85, Q86, Q88, Q90, Q91, Q99, Q102, Q125, Q138, Q141, Q152, Q155, Q158, Q162, Q163, Q167, Q169.
- Les 10 anciennes questions « à clarification » (Q17, Q19, Q38, Q61, Q85, Q88, Q90, Q99, Q163, Q167) passent toutes en `expected_behavior = answer` ; leurs informations manquantes ne sont plus un prérequis (déplacées en `individualization_information`). Six d'entre elles acceptent aussi une réponse conditionnelle ou une clarification ciblée (« politiques mixtes »).
- **Le retrieval n'est pas concerné** : énoncés, fragments et ensembles de preuves inchangés ; après conversion, 171/171 questions d'`abpv171` ont la même requête et les mêmes preuves qu'`abpe171`.

## 2. Nouvelles suites (locales, non commitées)

- `abpv171` : release validée (`questions_validated.jsonl`, lignes `-V` écartées), 171 questions ; tag `v31:grid_revised` sur les 37.
- `abpvern` : variante vernaculaire (`revision_v31/data/vernaculaire.jsonl`), 171 questions, même grille ; `meta` et tags `vern:wording_changed` (88 : 57 dev / 31 test), `vern:paired_149` (149 : 87 / 62), `vern:in_release_200` (29 : 17 / 12). 66 énoncés modifiés appartiennent aux 149 appariés. Mêmes preuves que le standard (171/171) ; 83 requêtes identiques au standard.
- Conversion : `convert_enriched_benchmark` inchangé sur le fond, étendu de deux paramètres (`source`, `skip_reformulations`) et de champs `meta` de la release (comportements acceptables, politique QCM, faits optionnels, individualisation). `LOCAL_ONLY_SUITES` complété ; `.gitignore` : `eval/datasets/abpv*.jsonl`, `eval/splits/abpv*/`, `reports/eval/judge_v4/**/*abpv*` (vérifié par `git check-ignore`).
- Split repris d'`abpe171` par identifiant : dev = identifiants de `eval/splits/abpe171/dev.jsonl`, test = complément (le fichier test n'a pas été ouvert). **La partie test est écrite `test_posthoc.jsonl`, pas `test.jsonl`** : un `test.jsonl` non enregistré ferait échouer `verify_lockbox`, et `LOCKBOX.md` ne doit pas être modifié. Ces questions sont celles du test d'`abpe171`, déjà utilisé ; aucune nouvelle mise sous scellé n'aurait de sens.
- Couverture du mapping des preuves sur `index/tas_v6` (`mapping_coverage`, comme la commande `coverage`) — identique pour les deux suites : dev 347/348 passages, 221/222 preuves, 96/96 questions à ensembles atteignables ; test 325/325 passages, 174/175 preuves (1 sans fragment utile), 64/64.
- Test anti-fuite étendu aux fichiers de la release (standard, vernaculaire, 200) ; il reste silencieux.

## 3. Retrieval seul

Index `tas_v6`, k = 64, `C10_context_notes` gelée (tag `retrieval-freeze-20261127`) et trois variantes construites comme dans `eval_internal/robustness/run_retrieval.py` (importé en lecture seule) ; un seul job sous verrou GPU, ~5 min. Scripts : `eval_internal/benchmark_valide/run_retrieval.py`, `analyze.py` ; tableaux complets (rappel des preuves, variante − gelée, identifiants en échec) : `reports/agents/V1_annexes/retrieval_tables.md`. IC 95 % bootstrap ; différences appariées. **Côté test : une passe post hoc unique sur configurations fixes ; le test d'`abpe171` a déjà servi à l'évaluation finale ; rien n'a été réglé dessus et aucun échec individuel n'a été examiné.**

### 3a. Standard validé, configuration gelée

| | dev (n=96) | test post hoc (n=64) |
|---|---|---|
| sufficiency | 95,8 [91,7–99,0] | 82,8 [73,4–92,2] |
| rappel des preuves | 98,2 [96,1–99,7] | 92,7 [88,3–96,9] |

Identique au brouillon (95,8 / 82,8 publiés), comme attendu : preuves et énoncés inchangés. Le chiffre de retrieval de l'évaluation finale tient sous la version validée.

### 3b. Effet de formulation : vernaculaire − standard, sufficiency (apparié)

| config | sous-ensemble | dev | test (post hoc) |
|---|---|---|---|
| gelée | 88 énoncés modifiés | **−25,5 [−38,2 ; −12,7]** (n=55) | −3,6 [−17,9 ; +14,3] (n=28) |
| gelée | 149 appariés (experts) | **−8,6 [−16,0 ; −1,2]** (n=81) | −1,8 [−8,8 ; +3,5] (n=57) |
| gelée | 29 reformulations publiées | −18,8 [−43,8 ; 0] (n=16) | −20,0 [−50,0 ; 0] (n=10) |
| + n-grammes | 88 modifiés | −23,6 [−34,5 ; −12,7] | −14,3 [−32,1 ; +3,6] |
| + n-grammes | 149 appariés | −8,6 [−14,8 ; −2,5] | −7,0 [−15,8 ; 0] |
| + n-grammes | 29 publiées | −18,8 [−43,8 ; 0] | −40,0 [−70,0 ; −10,0] |
| + lexique | 88 modifiés | −23,6 [−34,5 ; −12,7] | −3,6 [−17,9 ; +14,3] |
| + lexique | 149 appariés | −7,4 [−13,6 ; −2,5] | −1,8 [−8,8 ; +3,5] |
| + lexique | 29 publiées | −6,2 [−18,8 ; 0] | −20,0 [−50,0 ; 0] |
| + les deux | 88 modifiés | −20,0 [−30,9 ; −10,9] | −10,7 [−28,6 ; +7,1] |
| + les deux | 149 appariés | −6,2 [−12,3 ; −1,2] | −5,3 [−14,0 ; +1,8] |
| + les deux | 29 publiées | −6,2 [−18,8 ; 0] | −40,0 [−70,0 ; −10,0] |

Niveaux absolus, sufficiency (dev / test post hoc) : gelée standard 95,8 / 82,8, vernaculaire 81,2 / 81,2 ; + n-grammes 96,9 / 87,5 et 83,3 / 81,2 ; + lexique 95,8 / 82,8 et 82,3 / 81,2 ; + les deux 95,8 / 87,5 et 84,4 / 82,8. Variante − gelée sur le vernaculaire (171) : n-grammes +2,1 [−3,1 ; +8,3] dev, 0,0 test ; lexique +1,0 dev, 0,0 test ; les deux +3,1 [−3,1 ; +9,4] dev, +1,6 [−3,1 ; +6,2] test. Latence : 198 ms (gelée) contre 196–206 ms.

### Lecture

1. **La formulation des cliniciens coûte cher au retrieval sur le dev** (−25 points sur les 88 énoncés réécrits, −9 sur les 149 appariés), **peu sur le test** (−4 et −2, non significatif). Sur le vernaculaire, dev et test se rejoignent (81,2 / 81,2) : l'avantage du dev standard (95,8) tient aux formulations sur lesquelles le retrieval a été mis au point. C'est la même optimisation du dev que celle constatée dans l'évaluation finale (écart dev → test de −13 points), vue d'un autre angle, et le meilleur chiffre « réaliste » est autour de 81–83 % de suffisance.
2. **Les n-grammes et le lexique ne compensent pas l'effet de formulation des experts.** Sur le vernaculaire, aucune variante n'a d'effet significatif contre la configuration gelée (tous les IC contiennent 0) ; la combinaison réduit l'écart au dev (−20 contre −25,5 sur les 88) sans le combler. Le gain de Q1 sous sigles synthétiques (+10 points) ne se retrouve pas sur les formulations réelles : les réécritures des experts portent surtout sur des raccourcis opératoires et des synonymes, pas sur des fautes ni sur l'unique sigle que le lexique connaît.
3. Sur le standard, n-grammes +4,7 [0 ; +10,9] au test post hoc (3 questions discordantes) : à ne pas utiliser pour choisir, c'est le test déjà vu.
4. Les 29 reformulations publiées : n = 16 et 10 questions avec métrique, IC très larges ; le −40 du test avec n-grammes repose sur 4 questions.


## 4. Re-jugement sous les grilles validées (préparé, non lancé)

- `eval_internal/benchmark_valide/prepare_rejudge.py` crée des copies dérivées (locales, `eval_internal/work/v1/reports/`) des trois rapports `abpe171` de l'évaluation finale, réduites aux 37 identifiants révisés, avec `suite = abpv171` (grille validée) et `split = test_posthoc` côté test ; réponses, lignes de retrieval et métadonnées `replay` inchangées. Rapports d'origine non modifiés ; aucune modification de `judge_io`.
- Export à l'aveugle fait : run **`blind_v31grid2`**, **37 cas en 2 lots** (8 dev itération, 12 dev confirmation, 17 test), extraits cités retrouvés pour 37/37 (`ok` 36, `ok_no_citation` 1). Un premier export `blind_v31grid` est sans extraits cités (clé de prompt manquée) : à ignorer (sa suppression m'a été refusée).
- Pour les 134 autres identifiants, la grille est identique : les verdicts `blind_final` restent valables.
- Lancement : deux passes (a, b) de juges Haiku selon `eval_internal/judge/JUDGE_TASK.md`, `<RUN> = blind_v31grid2`, lots 0 et 1 ; puis `HF_HUB_OFFLINE=1 .venv/bin/python -m rag_sfar.evaluation.judge_io merge-blind --run blind_v31grid2 --passes a,b`.

## 5. Campagne des experts (`Full pipeline/README.md`)

Protocole : 200 questions de la release v31.2, générateur local Qwen3.5-9B (LM Studio), trois conditions (LLM seule ; LLM + RAG « C8 », copie de la version d'origine de notre pipeline sur le PDF V3.1 ; LLM + passages annotés « oracle »), 600 réponses. Juge automatique = le même Qwen, prompt clinique distinct, grille à quatre axes, critère « réussite stricte ». Chiffres rapportés tels quels, grille et juge différents des nôtres : **non comparables directement**.

| Condition | Réussites strictes (juge Qwen) | Alertes critiques (juge Qwen) |
|---|---:|---:|
| LLM seule | 56/200 (28 %) | 119/200 |
| LLM + RAG C8 | 133/200 (66,5 %) | 36/200 |
| LLM + oracle | 153/200 (76,5 %) | 28/200 |

Ils rapportent aussi un ensemble complet de passages annotés retrouvé pour 114/186 questions avant sélection et 82/186 dans le contexte transmis (leur mesure, pas la nôtre).
