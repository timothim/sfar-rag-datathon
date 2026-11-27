# ce_gap_005 vs off (paired, b - a; contexte vu par le générateur : 40 extraits / 30 000 car.)

## abpe171 (n = 102, déclenchements 22 = 21.6 %)

| métrique | n | a | b | b − a [IC 95 %] | gagnés / perdus |
|---|---:|---:|---:|---|---|
| sufficiency | 96 | 95.8 | 94.8 | -1.0 [-3.1 ; +0.0] | 0 / 1 |
| evidence_recall | 96 | 98.2 | 97.1 | -1.0 [-3.1 ; +0.0] | 0 / 1 |
| passage_hit | 102 | 100.0 | 100.0 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| doc_hit | 102 | 100.0 | 100.0 | +0.0 [+0.0 ; +0.0] | 0 / 0 |

Latence médiane retrieval (hors appel LLM) : 192 → 332 ms (déclenchés : 577 ms) ; caractères moyens du contexte générateur : 20342 → 21774 ; requêtes supplémentaires : 28.
Erreurs de format : 0.

## multirfe_synth (n = 94, déclenchements 44 = 46.8 %)

| métrique | n | a | b | b − a [IC 95 %] | gagnés / perdus |
|---|---:|---:|---:|---|---|
| passage_hit | 76 | 96.1 | 96.1 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| doc_hit | 76 | 98.7 | 98.7 | +0.0 [+0.0 ; +0.0] | 0 / 0 |

Latence médiane retrieval (hors appel LLM) : 189 → 394 ms (déclenchés : 574 ms) ; caractères moyens du contexte générateur : 20549 → 24374 ; requêtes supplémentaires : 57.
Erreurs de format : 0.

## x2_dev (n = 16, déclenchements 10 = 62.5 %)

| métrique | n | a | b | b − a [IC 95 %] | gagnés / perdus |
|---|---:|---:|---:|---|---|
| sufficiency | 16 | 37.5 | 37.5 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| evidence_recall | 16 | 65.6 | 65.6 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| passage_hit | 16 | 93.8 | 93.8 | +0.0 [+0.0 ; +0.0] | 0 / 0 |
| doc_hit | 16 | 100.0 | 100.0 | +0.0 [+0.0 ; +0.0] | 0 / 0 |

Latence médiane retrieval (hors appel LLM) : 192 → 687 ms (déclenchés : 919 ms) ; caractères moyens du contexte générateur : 22676 → 27720 ; requêtes supplémentaires : 18.
Erreurs de format : 0.

