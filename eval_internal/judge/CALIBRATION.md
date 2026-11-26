# Calibration du juge LLM (Claude Haiku, sous-agents Claude Code)

Date : 2026-11-26. Grille : `JUDGE_INSTRUCTIONS.md` (= `src/rag_sfar/evaluation/judge.py`). Commande : `python -m rag_sfar.evaluation.judge_io calibrate --dir eval_internal/judge`.

## Données
180 réponses réelles de 5 runs (réponses courtes du README et réponses longues en mode générique), sur le benchmark antibioprophylaxie. Vérité = clé déterministe : lettre du QCM, ou toutes les molécules attendues présentes. Les libellés ambigus (« pas d'antibioprophylaxie », « hors périmètre ») sont exclus. Sonde de biais de longueur : 20 réponses dupliquées avec une phrase neutre ajoutée.

## Résultats
| Mesure | Valeur |
|---|---|
| Accord juge / clé | 94,4 % (170/180) |
| Kappa de Cohen | **0,88** |
| Confusion (correct = positif) | VP 102, VN 68, FP 2, FN 8 |
| Verdicts changés par l'ajout de texte neutre | 0 / 20 |
| Kappa par source | de 0,63 (réponses longues C8) à 1,00 |

## Lecture des 10 désaccords
- 7 « faux négatifs » : la réponse cite **deux molécules sans trancher** (« Céfazoline ou Céfuroxime »). La clé par sous-chaîne la compte juste ; le juge la note « partielle », comme le demande la grille. Ici, le juge a raison.
- 2 « faux positifs » : « Pipéracilline + Tazobactam » contre la référence « Pipéracilline/Tazobactam ». C'est un faux négatif de format de la clé ; le juge a raison.
- 1 cas : « Clindamycine + Gentamicine » contre la référence « Clindamycine ». La clé le compte juste, le juge incorrect ; le juge a raison.

**Conclusion** : l'accord est suffisant (κ = 0,88), sans biais de longueur détecté. Les désaccords viennent surtout des défauts de la clé déterministe. Le juge Haiku peut servir aux conclusions, accompagné de son kappa. Limites : calibration sur une seule RFE, avec des réponses de type molécule ou QCM. L'accord sur des réponses ouvertes multi-RFE (posologies, conduites) reste à vérifier quand les médecins auront validé des questions.
