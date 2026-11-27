# V1 — retrieval seul, benchmark validé (abpv171) et vernaculaire (abpvern)

Index `tas_v6`, k = 64, configuration gelée `C10_context_notes` et variantes (n-grammes de caractères, lexique, les deux). IC 95 % bootstrap (moyenne ; différences appariées b − a, 2 000 tirages). n = questions où la métrique est définie. **Côté test : passe post hoc unique sur configurations fixes (test d'abpe171 déjà utilisé par l'évaluation finale), rien n'est réglé dessus.**

## sufficiency — niveaux

| config | jeu | dev | test (post hoc) |
|---|---|---|---|
| frozen | abpv171 | 95.8 [91.7–99.0] (n=96) | 82.8 [73.4–92.2] (n=64) |
| frozen | abpvern | 81.2 [72.9–88.5] (n=96) | 81.2 [71.9–90.6] (n=64) |
| subword | abpv171 | 96.9 [92.7–100.0] (n=96) | 87.5 [78.1–95.3] (n=64) |
| subword | abpvern | 83.3 [75.0–90.6] (n=96) | 81.2 [71.9–90.6] (n=64) |
| lexicon | abpv171 | 95.8 [91.7–99.0] (n=96) | 82.8 [73.4–92.2] (n=64) |
| lexicon | abpvern | 82.3 [74.0–89.6] (n=96) | 81.2 [71.9–90.6] (n=64) |
| subword_lexicon | abpv171 | 95.8 [91.7–99.0] (n=96) | 87.5 [78.1–95.3] (n=64) |
| subword_lexicon | abpvern | 84.4 [76.0–90.6] (n=96) | 82.8 [73.4–90.6] (n=64) |

## sufficiency — effet de formulation : vernaculaire − standard (apparié)

| config | sous-ensemble | dev | test (post hoc) |
|---|---|---|---|
| frozen | 88 énoncés modifiés | -25.5 [-38.2 ; -12.7] (n=55, 16 discordantes) | -3.6 [-17.9 ; +14.3] (n=28, 5 discordantes) |
| frozen | 149 appariés (experts) | -8.6 [-16.0 ; -1.2] (n=81, 9 discordantes) | -1.8 [-8.8 ; +3.5] (n=57, 3 discordantes) |
| frozen | 29 reformulations publiées | -18.8 [-43.8 ; +0.0] (n=16, 3 discordantes) | -20.0 [-50.0 ; +0.0] (n=10, 2 discordantes) |
| subword | 88 énoncés modifiés | -23.6 [-34.5 ; -12.7] (n=55, 13 discordantes) | -14.3 [-32.1 ; +3.6] (n=28, 8 discordantes) |
| subword | 149 appariés (experts) | -8.6 [-14.8 ; -2.5] (n=81, 7 discordantes) | -7.0 [-15.8 ; +0.0] (n=57, 6 discordantes) |
| subword | 29 reformulations publiées | -18.8 [-43.8 ; +0.0] (n=16, 3 discordantes) | -40.0 [-70.0 ; -10.0] (n=10, 4 discordantes) |
| lexicon | 88 énoncés modifiés | -23.6 [-34.5 ; -12.7] (n=55, 13 discordantes) | -3.6 [-17.9 ; +14.3] (n=28, 5 discordantes) |
| lexicon | 149 appariés (experts) | -7.4 [-13.6 ; -2.5] (n=81, 6 discordantes) | -1.8 [-8.8 ; +3.5] (n=57, 3 discordantes) |
| lexicon | 29 reformulations publiées | -6.2 [-18.8 ; +0.0] (n=16, 1 discordantes) | -20.0 [-50.0 ; +0.0] (n=10, 2 discordantes) |
| subword_lexicon | 88 énoncés modifiés | -20.0 [-30.9 ; -10.9] (n=55, 11 discordantes) | -10.7 [-28.6 ; +7.1] (n=28, 7 discordantes) |
| subword_lexicon | 149 appariés (experts) | -6.2 [-12.3 ; -1.2] (n=81, 5 discordantes) | -5.3 [-14.0 ; +1.8] (n=57, 5 discordantes) |
| subword_lexicon | 29 reformulations publiées | -6.2 [-18.8 ; +0.0] (n=16, 1 discordantes) | -40.0 [-70.0 ; -10.0] (n=10, 4 discordantes) |

## sufficiency — variante − gelée (apparié), par jeu

| variante | jeu / sous-ensemble | dev | test (post hoc) |
|---|---|---|---|
| subword | standard, 171 | +1.0 [-2.1 ; +5.2] (n=96, 3 discordantes) | +4.7 [+0.0 ; +10.9] (n=64, 3 discordantes) |
| subword | vernaculaire, 171 | +2.1 [-3.1 ; +8.3] (n=96, 8 discordantes) | +0.0 [-6.2 ; +6.2] (n=64, 4 discordantes) |
| subword | vernaculaire, 88 modifiés | +0.0 [-9.1 ; +9.1] (n=55, 6 discordantes) | -3.6 [-14.3 ; +7.1] (n=28, 3 discordantes) |
| lexicon | standard, 171 | +0.0 [+0.0 ; +0.0] (n=96, 0 discordantes) | +0.0 [+0.0 ; +0.0] (n=64, 0 discordantes) |
| lexicon | vernaculaire, 171 | +1.0 [-2.1 ; +4.2] (n=96, 3 discordantes) | +0.0 [+0.0 ; +0.0] (n=64, 0 discordantes) |
| lexicon | vernaculaire, 88 modifiés | +1.8 [-3.6 ; +7.3] (n=55, 3 discordantes) | +0.0 [+0.0 ; +0.0] (n=28, 0 discordantes) |
| subword_lexicon | standard, 171 | +0.0 [-3.1 ; +3.1] (n=96, 2 discordantes) | +4.7 [+0.0 ; +10.9] (n=64, 3 discordantes) |
| subword_lexicon | vernaculaire, 171 | +3.1 [-3.1 ; +9.4] (n=96, 9 discordantes) | +1.6 [-3.1 ; +6.2] (n=64, 3 discordantes) |
| subword_lexicon | vernaculaire, 88 modifiés | +3.6 [-7.3 ; +14.5] (n=55, 8 discordantes) | +0.0 [-10.7 ; +10.7] (n=28, 2 discordantes) |

## evidence_recall — niveaux

| config | jeu | dev | test (post hoc) |
|---|---|---|---|
| frozen | abpv171 | 98.2 [96.1–99.7] (n=96) | 92.7 [88.3–96.9] (n=64) |
| frozen | abpvern | 85.9 [79.4–91.8] (n=96) | 90.0 [83.7–95.3] (n=64) |
| subword | abpv171 | 99.0 [97.4–100.0] (n=96) | 94.9 [91.4–98.0] (n=64) |
| subword | abpvern | 87.2 [80.7–92.9] (n=96) | 88.7 [81.6–94.5] (n=64) |
| lexicon | abpv171 | 98.5 [96.8–99.8] (n=96) | 92.7 [88.3–96.9] (n=64) |
| lexicon | abpvern | 87.2 [80.7–92.8] (n=96) | 90.0 [83.7–95.3] (n=64) |
| subword_lexicon | abpv171 | 97.9 [95.3–99.8] (n=96) | 94.9 [91.4–98.0] (n=64) |
| subword_lexicon | abpvern | 88.2 [81.8–93.4] (n=96) | 90.2 [83.6–95.7] (n=64) |

## evidence_recall — effet de formulation : vernaculaire − standard (apparié)

| config | sous-ensemble | dev | test (post hoc) |
|---|---|---|---|
| frozen | 88 énoncés modifiés | -21.5 [-32.1 ; -11.5] (n=55, 16 discordantes) | -6.2 [-17.9 ; +3.6] (n=28, 5 discordantes) |
| frozen | 149 appariés (experts) | -8.0 [-14.8 ; -2.5] (n=81, 9 discordantes) | -1.8 [-6.1 ; +1.8] (n=57, 3 discordantes) |
| frozen | 29 reformulations publiées | -15.6 [-34.4 ; +0.0] (n=16, 3 discordantes) | -15.0 [-40.0 ; +0.0] (n=10, 2 discordantes) |
| subword | 88 énoncés modifiés | -20.6 [-30.9 ; -11.5] (n=55, 14 discordantes) | -14.3 [-29.5 ; -0.9] (n=28, 8 discordantes) |
| subword | 149 appariés (experts) | -7.4 [-13.0 ; -2.5] (n=81, 7 discordantes) | -5.7 [-12.7 ; +0.0] (n=57, 6 discordantes) |
| subword | 29 reformulations publiées | -12.5 [-28.1 ; +0.0] (n=16, 3 discordantes) | -27.5 [-55.0 ; -5.0] (n=10, 4 discordantes) |
| lexicon | 88 énoncés modifiés | -19.7 [-29.7 ; -10.0] (n=55, 13 discordantes) | -6.2 [-17.9 ; +3.6] (n=28, 5 discordantes) |
| lexicon | 149 appariés (experts) | -6.8 [-13.0 ; -1.9] (n=81, 6 discordantes) | -1.8 [-6.1 ; +1.8] (n=57, 3 discordantes) |
| lexicon | 29 reformulations publiées | -6.2 [-18.8 ; +0.0] (n=16, 1 discordantes) | -15.0 [-40.0 ; +0.0] (n=10, 2 discordantes) |
| subword_lexicon | 88 énoncés modifiés | -17.0 [-27.3 ; -7.3] (n=55, 13 discordantes) | -10.7 [-24.1 ; +0.9] (n=28, 7 discordantes) |
| subword_lexicon | 149 appariés (experts) | -4.9 [-10.5 ; -0.6] (n=81, 6 discordantes) | -3.9 [-10.1 ; +0.9] (n=57, 5 discordantes) |
| subword_lexicon | 29 reformulations publiées | -3.1 [-9.4 ; +0.0] (n=16, 1 discordantes) | -27.5 [-55.0 ; -5.0] (n=10, 4 discordantes) |

## evidence_recall — variante − gelée (apparié), par jeu

| variante | jeu / sous-ensemble | dev | test (post hoc) |
|---|---|---|---|
| subword | standard, 171 | +0.8 [-0.7 ; +2.3] (n=96, 4 discordantes) | +2.2 [+0.0 ; +4.9] (n=64, 3 discordantes) |
| subword | vernaculaire, 171 | +1.3 [-2.8 ; +5.8] (n=96, 10 discordantes) | -1.3 [-6.8 ; +3.1] (n=64, 4 discordantes) |
| subword | vernaculaire, 88 modifiés | +0.3 [-6.7 ; +7.3] (n=55, 7 discordantes) | -4.8 [-15.5 ; +4.8] (n=28, 3 discordantes) |
| lexicon | standard, 171 | +0.3 [+0.0 ; +1.0] (n=96, 1 discordantes) | +0.0 [+0.0 ; +0.0] (n=64, 0 discordantes) |
| lexicon | vernaculaire, 171 | +1.4 [-1.0 ; +4.2] (n=96, 4 discordantes) | +0.0 [+0.0 ; +0.0] (n=64, 0 discordantes) |
| lexicon | vernaculaire, 88 modifiés | +1.8 [-1.8 ; +6.4] (n=55, 3 discordantes) | +0.0 [+0.0 ; +0.0] (n=28, 0 discordantes) |
| subword_lexicon | standard, 171 | -0.3 [-1.9 ; +1.1] (n=96, 4 discordantes) | +2.2 [+0.0 ; +4.9] (n=64, 3 discordantes) |
| subword_lexicon | vernaculaire, 171 | +2.3 [-2.3 ; +7.3] (n=96, 11 discordantes) | +0.3 [-4.2 ; +3.9] (n=64, 3 discordantes) |
| subword_lexicon | vernaculaire, 88 modifiés | +3.0 [-4.8 ; +11.2] (n=55, 9 discordantes) | -1.2 [-10.7 ; +7.1] (n=28, 2 discordantes) |

## Questions sans suffisance (configuration gelée) — identifiants seulement

- abpv171 dev : Q07, Q44, Q158, Q171
- abpv171 test (post hoc) : Q12, Q14, Q16, Q24, Q33, Q35, Q49, Q60, Q93, Q146, Q152
- abpvern dev : Q01, Q03, Q07, Q18, Q25, Q27, Q46, Q48, Q74, Q89, Q100, Q102, Q115, Q120, Q122, Q158, Q168, Q171
- abpvern test (post hoc) : Q12, Q16, Q24, Q33, Q34, Q35, Q49, Q60, Q76, Q116, Q146, Q152

Latence moyenne de `retrieve` (ms) : frozen 198, subword 206, lexicon 196, subword_lexicon 205

## NORM sur les formulations des cliniciens (`abpvern`)

REF = gelée ; NORM = normalisation de la question par LLM (Q2, variante normalize, mode add) ; LEX+NORM = NORM avec n-grammes + lexique. « full » = tout le contexte retourné (k = 64, comme les tableaux précédents) ; « gen » = contexte lu par le générateur (40 extraits, 30 000 caractères, comme Q2/G1). Différences appariées setup − REF, IC 95 % bootstrap ; +g/−p = questions gagnées / perdues. Test : passe post hoc unique.

### sufficiency (full)

| setup | sous-ensemble | dev | test (post hoc) |
|---|---|---|---|
| REF (niveau) | 171 | 81.2 [74.0–88.5] (n=96) | 81.2 [71.9–90.6] (n=64) |
| REF (niveau) | 88 modifiés | 72.7 [60.0–83.6] (n=55) | 78.6 [64.3–92.9] (n=28) |
| REF (niveau) | 29 publiées | 81.2 [56.2–100.0] (n=16) | 70.0 [40.0–100.0] (n=10) |
| NORM − REF | 171 | +6.2 [+2.1 ; +11.5] (n=96, +6/−0) | +1.6 [+0.0 ; +4.7] (n=64, +1/−0) |
| NORM − REF | 88 modifiés | +9.1 [+1.8 ; +18.2] (n=55, +5/−0) | +3.6 [+0.0 ; +10.7] (n=28, +1/−0) |
| NORM − REF | 29 publiées | +12.5 [+0.0 ; +31.2] (n=16, +2/−0) | +10.0 [+0.0 ; +30.0] (n=10, +1/−0) |
| LEX_NORM − REF | 171 | +8.3 [+2.1 ; +15.6] (n=96, +10/−2) | +6.2 [+1.6 ; +12.5] (n=64, +4/−0) |
| LEX_NORM − REF | 88 modifiés | +10.9 [+0.0 ; +21.8] (n=55, +8/−2) | +10.7 [+0.0 ; +21.4] (n=28, +3/−0) |
| LEX_NORM − REF | 29 publiées | +12.5 [-12.5 ; +37.5] (n=16, +3/−1) | +20.0 [+0.0 ; +50.0] (n=10, +2/−0) |

### evidence_recall (full)

| setup | sous-ensemble | dev | test (post hoc) |
|---|---|---|---|
| REF (niveau) | 171 | 85.9 [79.3–91.8] (n=96) | 90.0 [84.0–95.3] (n=64) |
| REF (niveau) | 88 modifiés | 77.6 [67.0–87.0] (n=55) | 86.0 [74.7–96.4] (n=28) |
| REF (niveau) | 29 publiées | 84.4 [65.6–100.0] (n=16) | 82.5 [60.0–100.0] (n=10) |
| NORM − REF | 171 | +5.2 [+1.6 ; +9.9] (n=96, +6/−0) | +0.8 [+0.0 ; +2.3] (n=64, +1/−0) |
| NORM − REF | 88 modifiés | +8.2 [+1.8 ; +16.4] (n=55, +5/−0) | +1.8 [+0.0 ; +5.4] (n=28, +1/−0) |
| NORM − REF | 29 publiées | +12.5 [+0.0 ; +31.2] (n=16, +2/−0) | +5.0 [+0.0 ; +15.0] (n=10, +1/−0) |
| LEX_NORM − REF | 171 | +6.2 [+1.5 ; +11.6] (n=96, +10/−3) | +3.0 [+0.4 ; +6.4] (n=64, +4/−0) |
| LEX_NORM − REF | 88 modifiés | +9.4 [+1.8 ; +18.5] (n=55, +8/−3) | +5.1 [+0.0 ; +11.6] (n=28, +3/−0) |
| LEX_NORM − REF | 29 publiées | +12.5 [-3.1 ; +34.4] (n=16, +3/−1) | +7.5 [+0.0 ; +20.0] (n=10, +2/−0) |

### sufficiency (gen)

| setup | sous-ensemble | dev | test (post hoc) |
|---|---|---|---|
| REF (niveau) | 171 | 81.2 [74.0–88.5] (n=96) | 81.2 [71.9–90.6] (n=64) |
| REF (niveau) | 88 modifiés | 72.7 [60.0–83.6] (n=55) | 78.6 [64.3–92.9] (n=28) |
| REF (niveau) | 29 publiées | 81.2 [56.2–100.0] (n=16) | 70.0 [40.0–100.0] (n=10) |
| NORM − REF | 171 | +6.2 [+2.1 ; +11.5] (n=96, +6/−0) | +1.6 [+0.0 ; +4.7] (n=64, +1/−0) |
| NORM − REF | 88 modifiés | +9.1 [+1.8 ; +18.2] (n=55, +5/−0) | +3.6 [+0.0 ; +10.7] (n=28, +1/−0) |
| NORM − REF | 29 publiées | +12.5 [+0.0 ; +31.2] (n=16, +2/−0) | +10.0 [+0.0 ; +30.0] (n=10, +1/−0) |
| LEX_NORM − REF | 171 | +8.3 [+2.1 ; +15.6] (n=96, +10/−2) | +6.2 [+1.6 ; +12.5] (n=64, +4/−0) |
| LEX_NORM − REF | 88 modifiés | +10.9 [+0.0 ; +21.8] (n=55, +8/−2) | +10.7 [+0.0 ; +21.4] (n=28, +3/−0) |
| LEX_NORM − REF | 29 publiées | +12.5 [-12.5 ; +37.5] (n=16, +3/−1) | +20.0 [+0.0 ; +50.0] (n=10, +2/−0) |

### evidence_recall (gen)

| setup | sous-ensemble | dev | test (post hoc) |
|---|---|---|---|
| REF (niveau) | 171 | 85.9 [79.3–91.8] (n=96) | 90.0 [84.0–95.3] (n=64) |
| REF (niveau) | 88 modifiés | 77.6 [67.0–87.0] (n=55) | 86.0 [74.7–96.4] (n=28) |
| REF (niveau) | 29 publiées | 84.4 [65.6–100.0] (n=16) | 82.5 [60.0–100.0] (n=10) |
| NORM − REF | 171 | +5.2 [+1.6 ; +9.9] (n=96, +6/−0) | +0.8 [+0.0 ; +2.3] (n=64, +1/−0) |
| NORM − REF | 88 modifiés | +8.2 [+1.8 ; +16.4] (n=55, +5/−0) | +1.8 [+0.0 ; +5.4] (n=28, +1/−0) |
| NORM − REF | 29 publiées | +12.5 [+0.0 ; +31.2] (n=16, +2/−0) | +5.0 [+0.0 ; +15.0] (n=10, +1/−0) |
| LEX_NORM − REF | 171 | +6.2 [+1.5 ; +11.6] (n=96, +10/−3) | +3.0 [+0.4 ; +6.4] (n=64, +4/−0) |
| LEX_NORM − REF | 88 modifiés | +9.4 [+1.8 ; +18.5] (n=55, +8/−3) | +5.1 [+0.0 ; +11.6] (n=28, +3/−0) |
| LEX_NORM − REF | 29 publiées | +12.5 [-3.1 ; +34.4] (n=16, +3/−1) | +7.5 [+0.0 ; +20.0] (n=10, +2/−0) |

Normalisation utilisée (requête ajoutée) : dev 39/102, test 20/69.

Latence non rapportée (job concurrent sur le GPU). Les métriques « gen » sont identiques aux « full » : tout le contexte retourné tient dans le budget du générateur.
