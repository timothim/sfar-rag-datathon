# dec_r1_s4 vs off (paired, b - a; contexte vu par le générateur : 40 extraits / 30 000 car.)

## abpe171 (n = 102, déclenchements 0 = 0.0 %)

| métrique | n | a | b | b − a [IC 95 %] | gagnés / perdus |
|---|---:|---:|---:|---|---|
| sufficiency | 96 | 95.8 | 95.8 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| evidence_recall | 96 | 98.2 | 98.2 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| passage_hit | 102 | 100.0 | 100.0 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| doc_hit | 102 | 100.0 | 100.0 | +0.0 [+0.0 ; +0.0] | 0 / 0 |

Latence médiane retrieval (hors appel LLM) : 192 → 193 ms (déclenchés : nan ms) ; caractères moyens du contexte générateur : 20342 → 20342 ; requêtes supplémentaires : 0.
Erreurs de format : 0.

## multirfe_synth (n = 94, déclenchements 2 = 2.1 %)

| métrique | n | a | b | b − a [IC 95 %] | gagnés / perdus |
|---|---:|---:|---:|---|---|
| passage_hit | 76 | 96.1 | 96.1 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| doc_hit | 76 | 98.7 | 98.7 | +0.0 [+0.0 ; +0.0] | 0 / 0 |

Latence médiane retrieval (hors appel LLM) : 189 → 190 ms (déclenchés : 579 ms) ; caractères moyens du contexte générateur : 20549 → 20710 ; requêtes supplémentaires : 4.
Erreurs de format : 0.

## x2_dev (n = 16, déclenchements 9 = 56.2 %)

| métrique | n | a | b | b − a [IC 95 %] | gagnés / perdus |
|---|---:|---:|---:|---|---|
| sufficiency | 16 | 37.5 | 50.0 | +12.5 [+0.0 ; +31.2] | 2 / 0 |
| evidence_recall | 16 | 65.6 | 71.9 | +6.2 [+0.0 ; +15.6] | 2 / 0 |
| passage_hit | 16 | 93.8 | 93.8 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| doc_hit | 16 | 100.0 | 100.0 | +0.0 [+0.0 ; +0.0] | 0 / 0 |

Latence médiane retrieval (hors appel LLM) : 192 → 562 ms (déclenchés : 587 ms) ; caractères moyens du contexte générateur : 22676 → 26707 ; requêtes supplémentaires : 18.
Erreurs de format : 0.

