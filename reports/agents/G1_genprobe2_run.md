# G1 — exécution unique sur `genprobe2` (2026-11-27, 10:43)

Plan exécuté : `JOURNAL.md`, « Plan de l'exécution unique sur `genprobe2` », écrit et commité avant toute exécution. Une seule exécution ; aucun candidat, prompt, paramètre ou règle modifié après lecture. Sceau vérifié (`76be3ccd…`).

- Jeu : 60 questions **synthétiques (Claude Opus, agent E2), non validées médicalement** ; familles : deux sources 20, contrepartie de population 20, note de tableau 12, contrôles 8 ; 10 marquées `meta.weak`.
- Retrieval seul, `index/tas_v6`, métriques `harness.retrieval_metrics` (k = 64) sur le contexte lu par le générateur (40 extraits / 30 000 caractères), comme Q2 et X2. Différences appariées b − a contre la référence gelée dans la même condition, IC 95 % bootstrap.
- Pilote : `eval_internal/genprobe2_run.py` (modules existants inchangés). `typo1` : `perturb.apply_typos`, graine 20261127, 60/60 questions modifiées.
- Substituts : normalisation Haiku (120 réponses), décomposition Sonnet (120 + 25 pour les questions normalisées, nécessaires à TOUT). 0 réponse manquante pendant l'exécution, 0 erreur de format.
- TOUT = NORM (mode ajout) ⊃ DEC ⊃ retriever avec la configuration LEX : composition sans modifier aucun fichier.

## 1. Référence gelée (`C10_context_notes`) : première mesure sur ce jeu

| sous-groupe | n | suffisance (propre) | rappel des preuves | passage | suffisance (typo1) | rappel | passage |
|---|---:|---:|---:|---:|---:|---:|---:|
| toutes | 60 | 68,3 | 77,8 | 90,0 | 66,7 | 76,9 | 90,0 |
| deux sources | 20 | **40,0** | 63,3 | 90,0 | 40,0 | 65,8 | 100,0 |
| population | 20 | 80,0 | 85,0 | 90,0 | 75,0 | 80,0 | 80,0 |
| note de tableau | 12 | 75,0 | 79,2 | 83,3 | 75,0 | 79,2 | 83,3 |
| contrôles | 8 | 100,0 | 93,8 | 100,0 | 100,0 | 93,8 | 100,0 |
| sans `weak` | 50 | 70,0 | 79,0 | 90,0 | 68,0 | 78,0 | 90,0 |

Les questions à deux sources sont la faiblesse principale du retrieval gelé : 12 sur 20 n'ont pas toutes leurs preuves dans le contexte.

## 2. Suffisance (métrique principale), candidat − référence

| condition | candidat | toutes | deux sources | population | note de tableau | contrôles | sans `weak` | gagnées / perdues (toutes) |
|---|---|---|---|---|---|---|---|---|
| propre | LEX | +3,3 [−3,3 ; +10,0] | +10,0 [0 ; +25,0] | +5,0 [0 ; +15,0] | −8,3 [−25,0 ; 0] | 0 | +4,0 [0 ; +10,0] | 3 / 1 (perdue : gp2-tab-12) |
| propre | NORM | 0 [0 ; 0] | 0 | 0 | 0 | 0 | 0 | 0 / 0 |
| propre | DEC | 0 [0 ; 0] | **0 [0 ; 0]** | 0 | 0 | 0 | 0 | 0 / 0 |
| propre | TOUT | +3,3 [−3,3 ; +10,0] | +10,0 [0 ; +25,0] | +5,0 [0 ; +15,0] | −8,3 [−25,0 ; 0] | 0 | +4,0 [0 ; +10,0] | 3 / 1 (gp2-tab-12) |
| typo1 | LEX | **+1,7 [−6,7 ; +8,3]** | +5,0 [−10,0 ; +25,0] | +5,0 [0 ; +15,0] | −8,3 [−25,0 ; 0] | 0 | 0 [−6,0 ; +6,0] | 3 / 2 (gp2-two-07, gp2-tab-12) |
| typo1 | NORM | **+1,7 [0 ; +5,0]** | 0 | +5,0 [0 ; +15,0] | 0 | 0 | +2,0 [0 ; +6,0] | 1 / 0 |
| typo1 | TOUT | +3,3 [−5,0 ; +11,7] | +10,0 [−10,0 ; +30,0] | +5,0 [0 ; +15,0] | −8,3 [−25,0 ; 0] | 0 | +2,0 [−4,0 ; +10,0] | 4 / 2 (gp2-two-07, gp2-tab-12) |

En gras : la cible pré-déclarée de chaque candidat.

## 3. Rappel des preuves et passage dans le contexte (toutes familles)

| condition | candidat | rappel des preuves | g / p | passage | g / p |
|---|---|---|---|---|---|
| propre | LEX | +2,8 [−2,5 ; +8,3] | 4 / 1 | 0 [−5,0 ; +5,0] | 1 / 1 |
| propre | NORM | 0 | 0 / 0 | 0 | 0 / 0 |
| propre | DEC | 0 | 0 / 0 | 0 | 0 / 0 |
| propre | TOUT | +2,8 [−2,5 ; +8,3] | 4 / 1 | 0 [−5,0 ; +5,0] | 1 / 1 |
| typo1 | LEX | +1,4 [−3,1 ; +5,6] | 5 / 3 | 0 [−6,7 ; +6,7] | 2 / 2 |
| typo1 | NORM | +1,7 [0 ; +4,2] | 2 / 0 | +1,7 [0 ; +5,0] | 1 / 0 |
| typo1 | TOUT | +3,9 [−1,1 ; +9,2] | 7 / 3 | +1,7 [−5,0 ; +8,3] | 3 / 2 |

En typo1, LEX et TOUT perdent le passage de deux questions à deux sources (gp2-two-01 et gp2-two-09 ; deux sources : 100 → 90).

## 4. Déclenchements et coût

- **DEC** se déclenche sur **4/60** questions propres, **toutes dans la famille deux sources (4/20)** : gp2-two-01, 02, 05, 07. Les sous-questions n'apportent aucune preuve manquante : suffisance et rappel inchangés sur les 4.
- **NORM** réécrit 18/60 questions propres et 55/60 questions typo1 ; le gain en typo1 tient à une question (gp2-pop-06).
- TOUT = la somme de ses parties : sur les questions propres, résultats identiques à LEX ; en typo1, LEX et NORM s'additionnent.

| condition | config | latence médiane retrieval (ms) | p90 | contexte moyen (car.) | extraits |
|---|---|---:|---:|---:|---:|
| propre | REF / LEX / NORM / DEC / TOUT | 321 / 306 / 323 / 310 / 345 | 354 / 361 / 638 / 352 / 712 | 21 484 / 20 882 / 22 643 / 21 735 / 22 252 | 26,8 / 26,3 / 28,3 / 27,2 / 28,3 |
| typo1 | REF / LEX / NORM / TOUT | 198 / 212 / 386 / 414 | 224 / 237 / 433 / 519 | 21 537 / 20 869 / 24 571 / 23 710 | 26,8 / 26,2 / 30,6 / 30,0 |

Les latences sont **indicatives seulement** : le job a tourné sous un verrou GPU à 3 places, avec d'autres jobs (la référence passe de 321 ms en propre à 198 ms en typo1 à cause de la seule contention). Elles excluent l'appel LLM de NORM et DEC (réponses lues dans une table), qui est le vrai coût de ces options sur le modèle servi. Pas de seconde passe à `GPU_LOCK_SLOTS=1` : le verrou était occupé.

## 5. Verdicts selon les règles pré-déclarées

| candidat | règle 1 : sélectionnable ? (propre : 0 contrôle perdu, ≤ 1 perdue au total) | règle 2 : cible, IC exclut 0 ? | verdict |
|---|---|---|---|
| LEX | oui (0 contrôle perdu, 1 perdue : gp2-tab-12) | typo1, toutes familles : +1,7 [−6,7 ; +8,3], non | sélectionnable ; **pas d'effet démontré sur le jeu tenu à l'écart** |
| NORM | oui (0 perdue ; ne peut pas baisser en propre, par construction) | typo1 : +1,7 [0 ; +5,0], borne basse = 0, non | sélectionnable ; **pas d'effet démontré sur le jeu tenu à l'écart** |
| DEC | oui (0 perdue) | deux sources : 0 [0 ; 0], non | sélectionnable ; **pas d'effet démontré sur le jeu tenu à l'écart** |
| TOUT | oui (0 contrôle perdu, 1 perdue) | pas de cible propre dans le plan ; typo1 +3,3 [−5,0 ; +11,7], deux sources propres +10,0 [0 ; +25,0] | sélectionnable ; **pas d'effet démontré** |

Aucun candidat n'est recommandé par défaut. La configuration gelée reste la référence.

## 6. Écarts au plan et limites

- **Écart d'exécution (pas de règle).** TOUT a demandé une seconde série de substituts Sonnet (25 décompositions de questions normalisées), parce que NORM en mode ajout passe aussi la question normalisée à DEC. Cette série a été exportée et répondue avant toute exécution.
- La règle 1 est appliquée sur la suffisance. Sur le rappel des preuves et sur le passage, LEX et TOUT perdent aussi la même seule question en condition propre.
- Les limites dites d'avance s'appliquent :
  - retrieval seul, les réponses générées ne sont pas jugées ;
  - 60 questions synthétiques non validées médicalement ;
  - substituts Haiku et Sonnet à la place du modèle servi ;
  - à n = 20 par famille, une question vaut 5 points.
- Sans les 10 questions `weak`, les conclusions ne changent pas (§ 2).
