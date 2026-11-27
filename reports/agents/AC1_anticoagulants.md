# AC1 — Benchmark anticoagulants : LLM seul, LLM + RAG, retrieval

Agent AC1, 2026-11-27. Une seule passe, exécutée selon le plan écrit avant tout résultat (`JOURNAL.md`, « Benchmark anticoagulants : réponses générées, plan écrit avant l'exécution », 14:39).

## Ce qu'il faut savoir avant de lire les chiffres

| Élément | Valeur |
|---|---|
| Jeu | `anticoag2026`, fourni par l'équipe : 13 cas cliniques × 5 questions types, soit **65 questions** (47 avec preuves annotées pour la mesure du retrieval). Une seule RFE : « Gestion des anticoagulants pour une procédure invasive programmée » (2026). |
| Confidentialité | Jeu **local, non versionné**. Ce rapport ne contient que des identifiants et des agrégats, sans texte de question ni de référence. |
| Mise au point | Aucune. Rien n'a été réglé sur ce jeu, ni avant ni après les résultats. |
| Générateur | **Substitut Claude Sonnet** : sous-agents, consignes `eval_internal/GENERATOR_INSTRUCTIONS.md`, un agent par lot de 8 cas au plus. Ce n'est pas le modèle de la plateforme. |
| Juges | **Claude Haiku** (sous-agents), grille v4 inchangée, à l'aveugle (195 réponses mélangées sous identifiants opaques, 8 lots). Deux passes indépendantes (a, b). |
| Combinaison des deux juges | Fixée d'avance : **correct seulement si les deux juges le disent ; erreur grave si l'un des deux en signale une**. |
| Passes | Génération et jugement exécutés une seule fois. |

### Les trois conditions

1. **LLM seul** : la question sans aucun passage. Consigne neutre : répondre brièvement d'après ses connaissances des recommandations françaises, dire s'il ne sait pas, ne citer aucune source.
2. **LLM + RAG évalué** : profil `production`, c'est-à-dire la retrieval figée `C10_context_notes` sur `index/tas_v6`, le contexte `wide`, le prompt `clinical_concise`. Les prompts ont été capturés par `gen_replay`.
3. **LLM + RAG, option lexicale** (secondaire) : la même chose avec `--robustness lexical`, c'est-à-dire n-grammes de caractères et sigles développés.

## 1. Tableau récapitulatif

Résultat principal : combinaison stricte des deux juges, n = 65 par condition.

| Condition | n | Correct [IC exact 95 %] | Partiel | Incorrect | Correct ou partiel | Abstentions à tort | Erreurs graves (n, IC) | Fidélité aux extraits | Longueur moyenne |
|---|---|---|---|---|---|---|---|---|---|
| LLM seul (Sonnet, sans contexte) | 65 | **36,9 %** (24) [25,3 ; 49,8] | 19 | 22 | 66,2 % (43) [53,4 ; 77,4] | 0 | **20** — 30,8 % [19,9 ; 43,4] | — | 85 mots |
| LLM + RAG évalué (C10, `tas_v6`) | 65 | **55,4 %** (36) [42,5 ; 67,7] | 11 | 18 | 72,3 % (47) [59,8 ; 82,7] | 16 (24,6 %) | **1** — 1,5 % [0,0 ; 8,3] | 51/51 | 77 mots |
| LLM + RAG option lexicale | 65 | **56,9 %** (37) [44,0 ; 69,2] | 16 | 12 | 81,5 % (53) [70,0 ; 90,1] | 11 (16,9 %) | **1** — 1,5 % [0,0 ; 8,3] | 55/55 | 86 mots |

Erreurs graves par catégorie (signalements de chaque juge, a / b) :

| Condition | Catégories (juge a / juge b) | Questions concernées |
|---|---|---|
| LLM seul | `wrong_dose` 10 / 8 ; `wrong_conduct` 6 / 4 ; `other` 3 / 2 | 20 questions, listées au § 5 |
| LLM + RAG évalué | `wrong_dose` 1 / 1 | B2-Q3 |
| LLM + RAG option lexicale | `wrong_dose` 1 / 1 | B2-Q3 |

Ce que mesure chaque colonne :
- **Fidélité aux extraits** : réponses dont les extraits cités sont retrouvés dans le prompt. La mesure n'est définie que pour les conditions RAG. Elle porte sur les réponses que le juge a pu vérifier : 51 sur 65 pour le RAG évalué, 55 sur 65 pour l'option lexicale.
- **Abstentions à tort** : réponses où le générateur s'abstient alors que la question est couverte par la RFE.

### Chaque juge seul

| Condition | Juge a : correct / partiel / incorrect / graves | Juge b : correct / partiel / incorrect / graves |
|---|---|---|
| LLM seul | 30 (46,2 % [33,7 ; 59,0]) / 17 / 18 / 19 | 27 (41,5 % [29,4 ; 54,4]) / 18 / 20 / 14 |
| LLM + RAG évalué | 40 (61,5 % [48,6 ; 73,3]) / 7 / 18 / 1 | 38 (58,5 % [45,6 ; 70,6]) / 10 / 17 / 1 |
| LLM + RAG option lexicale | 46 (70,8 % [58,2 ; 81,4]) / 7 / 12 / 1 | 39 (60,0 % [47,1 ; 72,0]) / 14 / 12 / 1 |

## 2. Différences appariées

Méthode :
- même question, bootstrap apparié (`harness.paired_bootstrap_diff`, 2 000 tirages), en points de pourcentage ;
- « gagnées » : questions passées à correct dans la seconde condition ; « perdues » : l'inverse.

| Comparaison | Correct | Gagnées / perdues | Correct ou partiel | Erreurs graves |
|---|---|---|---|---|
| **RAG évalué − LLM seul** | **+18,5 [+3,1 ; +35,4]** | 22 / 10 | +6,2 [−7,7 ; +20,0] | **−29,2 [−40,0 ; −18,5]** (19 en moins, 0 en plus) |
| Option lexicale − RAG évalué | +1,5 [−13,8 ; +16,9] | 13 / 12 | +9,2 [0,0 ; +20,0] | 0,0 (B2-Q3 dans les deux) |
| Option lexicale − LLM seul | +20,0 [+6,2 ; +33,8] | 20 / 7 | +15,4 [+3,1 ; +27,7] | −29,2 [−40,0 ; −18,5] |

### Par question type du cas

13 questions par type. Les colonnes LLM seul, RAG évalué et option lexicale donnent le nombre de réponses correctes, puis entre parenthèses le nombre d'erreurs graves et le nombre d'abstentions à tort.

| Question type | LLM seul | RAG évalué | Option lexicale | RAG − LLM seul | Lexicale − RAG |
|---|---|---|---|---|---|
| 1. Risque hémorragique de la procédure | 5 (4 graves, 0 abst.) | 3 (0, 7) | 3 (0, 9) | −15,4 [−53,8 ; +30,8], 3 / 5 | 0,0 [−30,8 ; +30,8], 2 / 2 |
| 2. Relais avant | 5 (4, 0) | 9 (0, 2) | 8 (0, 1) | +30,8 [0,0 ; +61,5], 5 / 1 | −7,7 [−38,5 ; +23,1], 2 / 3 |
| 3. Jour de la dernière prise | 8 (3, 0) | 7 (1, 0) | 9 (1, 1) | −7,7 [−30,8 ; +15,4], 1 / 2 | +15,4 [−23,1 ; +53,8], 4 / 2 |
| 4. Contrôle biologique avant | 2 (5, 0) | 8 (0, 5) | 9 (0, 0) | +46,2 [+7,7 ; +76,9], 7 / 1 | +7,7 [−23,1 ; +38,5], 3 / 2 |
| 5. Reprise et relais après | 4 (4, 0) | 9 (0, 2) | 8 (0, 0) | +38,5 [0,0 ; +69,2], 6 / 1 | −7,7 [−46,2 ; +23,1], 2 / 3 |

### Par famille d'anticoagulant

| Famille | n | LLM seul | RAG évalué | Option lexicale | RAG − LLM seul | Lexicale − RAG |
|---|---|---|---|---|---|---|
| AVK | 40 | 14 (13 graves) | 20 (0 grave, 13 abst.) | 23 (0, 8) | +15,0 [−5,0 ; +37,5], 13 / 7 | +7,5 [−12,5 ; +27,5], 10 / 7 |
| AOD | 25 | 10 (7 graves) | 16 (1, 3) | 14 (1, 3) | +24,0 [−4,0 ; +52,0], 9 / 3 | −8,0 [−32,0 ; +12,0], 3 / 5 |

## 3. Retrieval sur le contexte lu par le générateur

Les chiffres sont mesurés sur le contexte effectivement montré au générateur, et reproduisent ceux du journal.

| Condition | Document de référence dans le contexte (65) | Suffisance des preuves (47) | Rappel des preuves |
|---|---|---|---|
| RAG évalué | 65/65 | **36/47 = 76,6 %** [62,0 ; 87,7] | 76,6 % |
| Option lexicale | 65/65 | **41/47 = 87,2 %** [74,3 ; 95,2] | 88,3 % |

Exactitude selon que toutes les preuves étaient dans le contexte ou non (questions à preuves) :

| Condition | Preuves suffisantes : correct | Preuves insuffisantes : correct | Questions sans preuve annotée : correct | LLM seul sur les mêmes questions (suffisantes / insuffisantes) |
|---|---|---|---|---|
| RAG évalué | 26/36 = 72,2 % [54,8 ; 85,8] | 2/11 = 18,2 % [2,3 ; 51,8] | 8/18 = 44,4 % | 15/36 = 41,7 % ; 3/11 = 27,3 % |
| Option lexicale | 28/41 = 68,3 % [51,9 ; 81,9] | 2/6 = 33,3 % [4,3 ; 77,7] | 7/18 = 38,9 % | 15/41 = 36,6 % ; 3/6 = 50,0 % |

La seule erreur grave des conditions RAG (B2-Q3) survient alors que les preuves étaient dans le contexte.

## 4. Accord entre juges et lot 0

### Accord sur l'exactitude (3 classes)

| Périmètre | n | Accord brut | κ de Cohen | Accord sur « erreur grave » (brut, κ) |
|---|---|---|---|---|
| Tous les cas | 195 | 83,1 % | 0,71 | 96,4 %, 0,79 |
| **Lot 0 seul** | 25 | **40,0 %** | **0,26** | 88,0 %, 0,60 |
| Hors lot 0 | 170 | 89,4 % | 0,81 | 97,6 %, 0,84 |
| LLM seul | 65 | 76,9 % | 0,65 | 89,2 %, 0,72 |
| RAG évalué | 65 | 89,2 % | 0,81 | 100 %, 1,00 |
| Option lexicale | 65 | 83,1 % | 0,67 | 100 %, 1,00 |

### Lot 0

Sur les mêmes 25 cas :

| Juge | Correct | Partiel | Incorrect |
|---|---|---|---|
| a | 14 | 3 | 8 |
| b | 0 | 16 | 9 |

Le juge b du lot 0 a appliqué la phrase de la grille « plusieurs options dont une seule correcte sans trancher = partiel » à toutes les réponses conditionnelles, et à certaines réponses qui donnent une seule conduite. Les autres juges b ont noté correctes des réponses conditionnelles semblables.

Ce qui a été fait :
- Le lot n'a été ni rejugé ni retiré du résultat principal.
- Avec la combinaison stricte, le lot 0 n'apporte aucune réponse correcte, quelle que soit la condition.
- **Le lot ne pèse pas également sur les trois conditions** : il contient 8 réponses du LLM seul, 6 du RAG évalué et 11 de l'option lexicale.

### Sensibilité, lot 0 exclu

Analyse de sensibilité seulement : le résultat principal reste celui du § 1.

| Condition | n | Correct | Erreurs graves |
|---|---|---|---|
| LLM seul | 57 | 24 (42,1 % [29,1 ; 55,9]) | 15 |
| RAG évalué | 59 | 36 (61,0 % [47,4 ; 73,5]) | 0 |
| Option lexicale | 54 | 37 (68,5 % [54,4 ; 80,5]) | 1 |

Différences appariées, sur les questions dont aucune des deux réponses comparées n'est dans le lot 0 :

| Comparaison | n | Correct | Gagnées / perdues | Erreurs graves |
|---|---|---|---|---|
| RAG − LLM seul | 51 | +13,7 [−3,9 ; +31,4] | 15 / 8 | −25,5 [−37,3 ; −13,7] |
| Lexicale − RAG | 48 | +6,2 [−10,4 ; +22,9] | 10 / 7 | — |

### Sensibilité, troisième juge sur le lot 0

Analyse de sensibilité seulement, décidée avant de voir son résultat : le résultat principal reste celui du § 1. Un troisième juge Haiku, indépendant (mêmes consignes, sans accès aux deux premières passes), a rejugé les 25 réponses du lot 0. Sur ce lot, une réponse est alors comptée correcte si au moins deux juges sur trois le disent ; hors du lot 0, la combinaison stricte est inchangée.

| Condition | Combinaison stricte (§ 1) | Lot 0 tranché à la majorité de trois |
|---|---|---|
| LLM seul | 24/65 (36,9 %) | 26/65 (40,0 %) |
| RAG évalué | 36/65 (55,4 %) | 37/65 (56,9 %) |
| Option lexicale | 37/65 (56,9 %) | 43/65 (66,2 %) |

- Sur les 14 réponses du lot 0 jugées correctes par le juge a et partielles par le juge b, le troisième juge en note 9 correctes et 5 partielles.
- Les erreurs graves ne changent pas : le troisième juge n'en signale aucune nouvelle (20 / 1 / 1).
- Lecture : l'ordre des trois conditions ne change pas. L'écart entre l'option lexicale et le RAG évalué dépend du juge du lot 0 (de +1,5 à +9,2 points) et reste non démontré.

### Champs manquants dans les verdicts

Certains verdicts ne contiennent que les clés de base : `correctness`, `abstained`, `serious_error`, `faithful` et la justification. La fusion les a acceptés : aucun verdict n'a été compté comme manquant ou invalide.

| Lot | Passe | Clés manquantes |
|---|---|---|
| 0 | a et b | `behavior`, `claims_satisfied`, `forbidden_violated` |
| 2 | a et b | `behavior` |
| 6 | b | `behavior` |

Ce que cela change :
- **Seule la métrique de comportement (`judge_behavior_ok`) perd des cas.** Les lots 0 et 2 manquent entièrement ; le lot 6 est décidé par le juge a seul.
- Comportement accepté, sur les cas restants (hors métriques déclarées) :

  | Condition | Comportement accepté |
  |---|---|
  | LLM seul | 51/51 |
  | RAG évalué | 30/49 |
  | Option lexicale | 34/45 |

- Ce jeu n'a ni faits obligatoires ni interdits : les deux autres clés ne servent à aucune métrique.
- Les métriques déclarées (correct, partiel, erreurs graves, abstentions à tort) ne dépendent pas de ces clés.

## 5. Erreurs graves, pour vérification médicale

Une ligne par question et par condition, catégories des deux juges, puis description courte. Les justifications complètes des juges sont dans le fichier local `eval_internal/work/anticoag2026/analysis.json`.

| Question | Condition | Juge a | Juge b | Description |
|---|---|---|---|---|
| A2-Q2 | LLM seul | — | wrong_dose | seuil d'INR avant rachianesthésie plus permissif que la référence (**un seul juge**) |
| A2-Q4 | LLM seul | wrong_dose | wrong_dose | seuil d'INR avant rachianesthésie plus permissif que la référence |
| A3-Q2 | LLM seul | wrong_conduct | wrong_conduct | pas de relais préopératoire alors que la référence en impose un |
| A4-Q2 | LLM seul | wrong_conduct | wrong_conduct | pas de relais préopératoire alors que la référence en impose un |
| A4-Q4 | LLM seul | wrong_dose | wrong_dose | seuil d'INR avant rachianesthésie plus permissif que la référence |
| A4-Q5 | LLM seul | wrong_conduct | wrong_conduct | relais curatif postopératoire alors que la référence l'exclut |
| A5-Q1 | LLM seul | other | other | risque hémorragique sous-classé (valve mécanique) |
| A5-Q5 | LLM seul | wrong_dose | wrong_dose | délai de début du relais postopératoire et critère d'arrêt différents de la référence |
| A6-Q4 | LLM seul | wrong_dose | wrong_dose | seuil d'INR avant rachianesthésie plus permissif que la référence |
| A6-Q5 | LLM seul | wrong_dose | other | relais curatif postopératoire débuté plus tôt que la référence |
| A8-Q1 | LLM seul | other | — | risque hémorragique sous-classé d'un niveau (**un seul juge**) |
| A8-Q2 | LLM seul | wrong_dose | — | seuil d'INR plus permissif ; arrêt du traitement un jour plus tard que la référence (**un seul juge**) |
| A8-Q4 | LLM seul | wrong_dose | wrong_dose | seuil d'INR avant rachianesthésie plus permissif que la référence |
| B1-Q1 | LLM seul | wrong_conduct | — | risque hémorragique sous-classé (**un seul juge**) |
| B1-Q5 | LLM seul | wrong_dose | wrong_conduct | reprise de l'AOD beaucoup plus précoce que la référence |
| B2-Q1 | LLM seul | wrong_conduct | — | risque hémorragique sous-classé d'un niveau (**un seul juge**) |
| B2-Q3 | LLM seul | other | wrong_dose | dernière prise de l'AOD trop tardive d'un jour |
| B3-Q3 | LLM seul | wrong_dose | — | dernière prise de l'AOD un jour plus tôt que la référence (**un seul juge** ; le juge b n'y voit pas de préjudice) |
| B4-Q4 | LLM seul | wrong_conduct | — | contrôles biologiques demandés alors que la référence n'en requiert aucun (**un seul juge**) |
| B5-Q3 | LLM seul | wrong_dose | wrong_dose | dernière prise de l'AOD décalée d'un jour par rapport à la référence |
| **B2-Q3** | **RAG évalué** | wrong_dose | wrong_dose | dernière prise de l'AOD trop tardive de deux jours (délai du risque élevé appliqué au lieu de celui que donne la référence) ; preuves présentes dans le contexte |
| **B2-Q3** | **Option lexicale** | wrong_dose | wrong_dose | même erreur que le RAG évalué |

Bilan :
- **LLM seul** : 20 erreurs graves, dont **7 signalées par un seul juge** (A2-Q2, A8-Q1, A8-Q2, B1-Q1, B2-Q1, B3-Q3, B4-Q4) et 13 par les deux.
- **Conditions RAG** : une seule erreur, B2-Q3, signalée par les deux juges dans les deux conditions.
- **Erreur récurrente du LLM seul** : le seuil d'INR avant anesthésie neuraxiale, dans 6 cas sur 13.

## 6. Questions où le LLM seul a raison et le RAG non

| Condition | Le RAG est incorrect | Le RAG est partiel |
|---|---|---|
| RAG évalué (10) | A1-Q1, A7-Q2, A7-Q4, B3-Q1, B5-Q5 | A1-Q3, A3-Q1, A5-Q3, A7-Q1, B5-Q1 |
| Option lexicale (7) | A1-Q1, A2-Q3, A7-Q2, B3-Q1 | A1-Q5, B2-Q2, B5-Q1 |

Toutes les réponses RAG incorrectes de ce tableau sont des abstentions à tort : les 5 du RAG évalué et les 4 de l'option lexicale.

Abstentions à tort du RAG :

| Condition | Questions | Répartition |
|---|---|---|
| RAG évalué | A1-Q1, A2-Q1, A2-Q4, A4-Q1, A4-Q4, A5-Q1, A6-Q2, A6-Q4, A7-Q2, A7-Q4, A7-Q5, A8-Q1, A8-Q4, B3-Q1, B4-Q1, B5-Q5 | 7 sur la question 1 (classe de risque), 5 sur la question 4 (contrôle biologique) |
| Option lexicale | A1-Q1, A2-Q1, A2-Q3, A4-Q1, A5-Q1, A6-Q1, A7-Q2, A8-Q1, B2-Q1, B3-Q1, B4-Q1 | 9 sur la question 1 |

Lecture des abstentions (signalée par les générateurs, non mesurée) : les extraits ne classent pas toujours la procédure dans une classe de risque hémorragique. Le générateur s'abstient alors, ou répond de façon conditionnelle.

## 7. Lecture

1. **Le RAG apporte surtout de la sécurité.** Il fait passer les erreurs graves de 20 à 1 sur 65 : −29 points, avec un intervalle qui exclut 0. L'exactitude progresse aussi : +18,5 points [+3,1 ; +35,4].
2. **Ce gain est concentré** sur les questions 2, 4 et 5 : relais, contrôle biologique, reprise. Sur la question 1 (classe de risque de la procédure), le LLM seul fait aussi bien ou mieux : le RAG s'y abstient le plus souvent quand les extraits ne nomment pas la procédure.
3. **Le prix du RAG** est l'abstention à tort : 16 sur 65 pour le RAG évalué.
4. **L'option lexicale** :
   - améliore la suffisance des preuves (41/47 contre 36/47) ;
   - réduit les abstentions à tort (11 contre 16) ;
   - améliore « correct ou partiel » (+9,2 [0,0 ; +20,0]) ;
   - ne change pas l'exactitude stricte (+1,5 [−13,8 ; +16,9]).

   L'intervalle de « correct ou partiel » touche 0, ce qui reste cohérent avec les mesures précédentes. Elle n'est pas activée, et ce jeu ne sert pas à la régler.
5. **Les preuves comptent** : quand elles sont toutes dans le contexte, le RAG évalué répond juste dans 72 % des cas ; sinon, dans 18 % des cas (2 sur 11).

## 8. Limites

- **Questions non indépendantes** : 13 cas × 5 questions types. Les intervalles affichés, qui supposent l'indépendance, sont trop étroits.
- **Une seule RFE.**
- **Une seule exécution** pour la génération et pour chaque passe de juge.
- **Même famille de modèles** : le générateur (Claude Sonnet) et les juges (Claude Haiku) en font partie.
- **Juge non validé par un médecin** sur ce jeu. L'accord entre juges est faible sur le lot 0 (κ = 0,26), et ce lot pèse inégalement sur les conditions (§ 4).
- **Références courtes**, écrites par l'équipe. Ce sont des questions écrites par l'équipe, ni validées par un panel de médecins ni générées par un LLM.
- **Le « LLM seul » est Claude Sonnet**, pas le modèle de la plateforme (modèle ouvert d'environ 30 B, jamais mesuré). Un modèle récent et puissant peut connaître cette RFE de 2026 mieux ou moins bien qu'un modèle ouvert. Le résultat « LLM seul » ne se transpose pas.
- **Instruction différente pour le LLM seul** : `GENERATOR_INSTRUCTIONS.md` impose aux générateurs de n'utiliser que les extraits. Pour le LLM seul, le message de lancement, identique pour tous les agents, précisait que la consigne système du cas prévalait sur ce point.

## 9. Reproduction

Tous les dossiers ci-dessous sont locaux et ignorés par git.

| Étape | Commande ou fichier |
|---|---|
| Captures | `gen_replay.py capture --suite anticoag2026 --profile production` (`--name ac1_anticoag_c10n_v6`) et `--robustness lexical` (`--name ac1_anticoag_c10n_v6_lex`) |
| Prompts RAG | `gen_replay.py run --profile production --backend record --export-frontier` |
| LLM seul | consigne `eval_internal/work/anticoag2026/llm_alone_system.txt` ; export et import `eval_internal/work/anticoag2026/llm_alone.py` |
| Imports | vérifiés, sans aucun refus |
| Jugement | `judge_io export-blind --run blind_anticoag2026_ac1` (195 cas, 8 lots), puis `merge-blind --passes a,b` (0 verdict manquant ou invalide) |
| Tableau | `eval_internal/work/anticoag2026/analyze.py`, sortie `analysis.json` |
| Rapports fusionnés | `reports/eval/judge_v4/blind_anticoag2026_ac1/` |
