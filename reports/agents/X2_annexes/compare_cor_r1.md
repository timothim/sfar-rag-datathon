# cor_r1 vs off (paired, b - a; contexte vu par le générateur : 40 extraits / 30 000 car.)

## abpe171 (n = 102, déclenchements 1 = 1.0 %)

| métrique | n | a | b | b − a [IC 95 %] | gagnés / perdus |
|---|---:|---:|---:|---|---|
| sufficiency | 96 | 95.8 | 95.8 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| evidence_recall | 96 | 98.2 | 98.2 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| passage_hit | 102 | 100.0 | 100.0 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| doc_hit | 102 | 100.0 | 100.0 | +0.0 [+0.0 ; +0.0] | 0 / 0 |

Latence médiane retrieval (hors appel LLM) : 192 → 192 ms (déclenchés : 343 ms) ; caractères moyens du contexte générateur : 20342 → 20465 ; requêtes supplémentaires : 1.
Erreurs de format : 0.

## multirfe_synth (n = 94, déclenchements 10 = 10.6 %)

| métrique | n | a | b | b − a [IC 95 %] | gagnés / perdus |
|---|---:|---:|---:|---|---|
| passage_hit | 76 | 96.1 | 96.1 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| doc_hit | 76 | 98.7 | 98.7 | +0.0 [+0.0 ; +0.0] | 0 / 0 |

Latence médiane retrieval (hors appel LLM) : 189 → 190 ms (déclenchés : 380 ms) ; caractères moyens du contexte générateur : 20549 → 21138 ; requêtes supplémentaires : 12.
Erreurs de format : 0.

## x2_dev (n = 16, déclenchements 1 = 6.2 %)

| métrique | n | a | b | b − a [IC 95 %] | gagnés / perdus |
|---|---:|---:|---:|---|---|
| sufficiency | 16 | 37.5 | 37.5 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| evidence_recall | 16 | 65.6 | 65.6 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| passage_hit | 16 | 93.8 | 93.8 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| doc_hit | 16 | 100.0 | 100.0 | +0.0 [+0.0 ; +0.0] | 0 / 0 |

Latence médiane retrieval (hors appel LLM) : 192 → 192 ms (déclenchés : 388 ms) ; caractères moyens du contexte générateur : 22676 → 22840 ; requêtes supplémentaires : 1.
Erreurs de format : 0.

