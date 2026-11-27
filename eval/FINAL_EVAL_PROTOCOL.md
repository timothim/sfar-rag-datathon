# Protocole de l'évaluation finale (écrit et commité AVANT l'exécution)

Date de rédaction : 2026-11-27, 08:45. Rédigé par l'orchestrateur après la revue indépendante `reports/agents/R3_revue_finale.md`, dont il applique la section 6. Ce fichier ne doit plus être modifié après son commit ; toute déviation pendant l'exécution est consignée dans `JOURNAL.md` et dans le rapport final, section « Écarts au protocole ».

## 1. Ce qui est évalué (figé)

| Élément | Valeur |
|---|---|
| Code | commit `HEAD` au moment du commit de ce fichier (inscrit dans `JOURNAL.md` avec le hachage de ce fichier) |
| Retrieval | `C10_context_notes`, tag git `retrieval-freeze-20261127` |
| Index | `index/tas_v6`, sha256 du manifeste `829f9fa356380b3253c41ffdf59142ea24a3eac751e1310b2e2103b925e79a84` |
| Profil servi et évalué | `PRODUCTION` (`src/rag_sfar/generation/profile.py`, sha256 `177ff111d2056f3dd2aab8029dddf2c6b30c155a82738fe61b3fe19083912303`) : contexte structuré, préréglage `wide`, prompt `clinical_concise`, QCM routés vers `clinical_mcq`, aucune note de population ni de couverture, contrôle des réponses en avertissement |
| Prompts | `src/rag_sfar/generation/prompts.py`, sha256 `b3f80bf85cb38acb88b179e63aefcbe855784aa22b3b5184e6aaf435f219d3ca` |
| Générateur (substitut) | Claude Sonnet (sous-agents Claude Code, modèle `sonnet`), consignes `eval_internal/GENERATOR_INSTRUCTIONS.md` (sha256 `4b8ead91f469414d0286f21e38b8c8c00052b8ece232941f4ae6f1a4f0517bb5`), un agent par dossier `part_NN/` (≤ 8 cas, identifiants opaques, cas mélangés) |
| Juge | Claude Haiku (sous-agents, modèle `haiku`), grille v4 `eval_internal/judge/JUDGE_INSTRUCTIONS.md` (sha256 `69f08235b5b14fae9da8e0f166d4283ed61df9ca2cd3bb59f894aee050e1ce61`), tâche `JUDGE_TASK.md` (sha256 `0a5ba7884832075680362f9f2109c67c201bf82474e17e8440142415ccc96e4a`), lots de ~25 cas, identifiants opaques, deux passes indépendantes (a, b) par cas |
| Coffre-fort | `eval/LOCKBOX.md`, sha256 `e340c4d6d220e571f7a0d98787f63290d65bff6f5c23399296fb0bc89ee0d96a` |

Le générateur n'est pas le modèle déployé (cible : modèle ouvert de classe ~30B, jamais mesuré). Les résultats mesurent ce que l'étage de génération peut atteindre avec ce contexte et ce prompt ; ils ne sont pas un score du système servi.

## 2. Jeux exécutés, une seule fois

| Jeu | Split | Questions | Nature | Rôle |
|---|---|---:|---|---|
| `abpe171` | test (scellé) | 69 | benchmark enrichi, validé par des médecins, antibioprophylaxie V3.1 | résultat principal |
| `multirfe_synth` | test (scellé) | 57 | synthétique (LLM), 22 RFE jamais utilisées pendant la mise au point | généralisation hors documents vus |
| `genprobe` | unique (tenu à l'écart) | 48 | synthétique (LLM), 47 RFE hors antibioprophylaxie, questions conçues pour être difficiles | généralisation, génération jamais mesurée (retrieval déjà exécuté une fois le 27/11 à 07:52) |
| `abpe171` | dev | 102 | — | référence dev, rejugée dans le même passage |
| `multirfe_synth` | dev | 94 | — | référence dev, rejugée dans le même passage |

Non exécuté : `abp171` test. Mêmes 69 questions que `abpe171` test avec les références de l'édition précédente, et son fichier scellé désigne l'édition remplacée comme document de référence : ses chiffres n'auraient pas de sens. Il reste scellé.

Les réponses dev ne sont pas régénérées : ce sont les réponses Sonnet déjà produites avec la même configuration (`reports/eval/b3/*_b3_v6_c10n_iter_*` et `*_b3_v6_c10n_confirm_*`). Seul leur jugement est refait, à l'aveugle, mélangé au test.

## 3. Déroulement

1. Capture du retrieval des splits test et de `genprobe` avec `--profile production` (`gen_replay.py capture --split test --allow-test`, vérification du coffre-fort incluse).
2. Export à l'aveugle des prompts (`gen_replay.py run --backend record --export-frontier`), un dossier neuf.
3. Un agent Sonnet par `part_NN/`. Import par `gen_replay.py import-frontier` (refuse toute réponse manquante, vide, dupliquée ou mal rangée).
4. Export à l'aveugle unique mêlant les rapports test, `genprobe` et dev (`judge_io export-blind`), deux passes de juges Haiku, fusion `judge_io merge-blind --passes a,b`.
5. Calibration du juge sous la grille v4 (`eval_internal/judge/runs/blind_v4_calib`, `judge_io calibrate-blind`) : exécutée avant ou pendant, rapportée telle quelle.

## 4. Métriques principales (déclarées d'avance)

Retrieval, déterministe, sur le contexte montré au générateur :
- `abpe171` : suffisance des preuves (`sufficiency`), rappel des preuves ;
- `multirfe_synth` et `genprobe` : passage de référence dans le contexte (`passage_hit`), suffisance pour `genprobe`.

Génération, juge v4, combinaison stricte des deux passes (correct seulement si les deux juges disent correct ; erreur grave si l'un des deux en signale une ; comportement accepté seulement si les deux l'acceptent) :
- taux de réponses correctes ;
- taux de réponses correctes ou partielles ;
- taux d'erreurs graves, toutes catégories y compris `other` et `unjustified_assumption`, avec intervalle exact de Clopper-Pearson ;
- taux de faits obligatoires énoncés (`abpe171`) ;
- comportement accepté, lecture stricte (`abpe171`) ;
- abstention à tort ; abstention manquée sur les questions hors corpus (`multirfe_synth`) ;
- part des réponses signalées par le contrôle déterministe (`check_flag`).

Sont rapportés à côté, sans être des résultats principaux : les métriques de chaque juge, leur accord (kappa, accord brut), la lecture indulgente (`_any`), la fidélité aux extraits cités (`faithful`).

Intervalles : Clopper-Pearson pour les taux proches de 0 ou de 1, bootstrap pour les autres. Écart dev − test avec intervalle bootstrap non apparié ; le dev de référence est la confirmation (72 + 64 questions, non utilisées pour choisir), le sous-ensemble d'itération (30 + 30) est donné à part.

## 5. Sous-groupes déclarés d'avance

- `abpe171` test : QCM / questions ouvertes ; questions pédiatriques (tag `pediatric`) ; questions à clarification (5 : effectifs, pas de pourcentage).
- `abpe171` test, sensibilité à l'exposition antérieure : résultat sans Q58 et Q152 (utilisées pour un réglage par un autre agent avant le scellement), et sans toutes les questions de test ayant un résultat par question dans les rapports non versionnés `reports/benchmark_enrichi_eval*/` (16 questions au total selon la revue R3).
- `multirfe_synth` test : par type de question ; questions hors corpus.
- `genprobe` : par famille (QCM, ligne de tableau dépendant d'une note, contraste de population, deux sources).

Toute autre analyse est exploratoire et dite comme telle.

## 6. Règles d'échec

- Réponse manquante, vide ou illisible : comptée incorrecte, jamais exclue.
- Un dossier `part_NN/` dont l'import est refusé pour une raison technique (fichier absent, identifiants incohérents) est régénéré une seule fois, en entier, par un nouvel agent ; l'incident est consigné. S'il échoue encore, ses cas sont comptés incorrects.
- Verdict manquant ou invalide : le lot concerné est rejugé une seule fois ; s'il manque encore, le cas est compté incorrect (`--allow-missing`) et listé.
- Un seul passage. Aucune réexécution « pour voir », aucune modification du système, des prompts, de la grille ou de ce protocole après lecture d'un résultat de test.
- Après l'exécution, `abpe171` test, `multirfe_synth` test et `genprobe` ne sont plus des jeux vierges : ils ne servent plus à aucun réglage.

## 7. Formulation des résultats

Conformément à la revue R3 : « avec un générateur de substitution (Claude Sonnet) recevant exactement les prompts de notre configuration, X % [IC] des réponses sont jugées conformes à la référence par un juge LLM (Claude Haiku, grille v4, non validée médicalement) ». Ne seront pas écrits : « notre système atteint X % », « validé cliniquement », « 0 erreur grave » sans intervalle, ni une comparaison directe avec les scores de l'évaluateur officiel du benchmark (grille différente).
