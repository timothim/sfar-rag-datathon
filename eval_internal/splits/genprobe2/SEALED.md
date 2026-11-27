# genprobe2 — scellé (2026-11-27, agent E2)

Jeu tenu à l'écart : 60 questions synthétiques (LLM, non validées par un médecin), à n'exécuter
qu'une seule fois, sur les configurations finales gelées. Chaque exécution est consignée dans `JOURNAL.md`.
Ne pas consulter ni modifier pendant la mise au point. Exclu de `--suite full` (`HELD_OUT_SUITES`).

| Fichier | SHA-256 |
|---|---|
| `eval_internal/splits/genprobe2/dev.jsonl` | `76be3ccd020efec13f0913c608ac24fb19f1e84cb9da76b3d20f6e641e5ca255` |

`eval_internal/datasets/genprobe2.jsonl` est identique octet pour octet (même hash).

Vérification : `shasum -a 256 eval_internal/splits/genprobe2/dev.jsonl`.
