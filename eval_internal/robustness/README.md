# eval_internal/robustness — robustesse du retrieval aux saisies réelles (agent Q1, 2026-11-27)

**Perturbations synthétiques, outil de développement uniquement.** Les jeux de ce dossier sont des copies déformées de façon automatique (graine fixe) des questions **dev** de `abpe171` et `multirfe_synth`. Ce ne sont ni des questions validées médicalement, ni un benchmark : elles servent seulement à mesurer ce que coûtent au retrieval des fautes de frappe, des accents manquants, des abréviations ou un style télégraphique, toutes choses que les questions d'évaluation (propres, rédigées par des experts) ne contiennent pas. Aucun split test, aucune question de `genprobe`.

Rapport : `reports/agents/Q1_robustesse.md`.

## Fichiers

| Fichier | Rôle |
|---|---|
| `build_glossary.py` | Extrait le glossaire des abréviations des chunks des éditions en vigueur de `index/tas_v6` (module `rag_sfar.retrieval.corpus_glossary`) → `glossary_tas_v6.json` ; échantillons d'audit de 50 entrées étiquetés à la main (`glossary_sample50*.csv`, colonne `correct`), conservés sauf `--resample`. |
| `perturb.py` | Génère `sets/<suite>/<perturbation>.jsonl` (format `EvalItem`, seule la question change ; `meta.perturbation` décrit la modification) et `sets/counts.json`. |
| `run_retrieval.py` | Retrieval seul, une configuration par appel (sous `scripts/with_gpu_lock.sh`), mêmes métriques que `rag-sfar-eval --retrieval-only --k 64` → `results/<config>.jsonl`. |
| `run_all.sh` | Enchaîne les 7 configurations, un verrou GPU par configuration. |
| `analyze.py` | Tableaux, différences appariées (bootstrap), latence, taille du contexte → `results/summary.md`. |

## Perturbations (question seule ; choix de QCM, passages de référence et preuves inchangés)

- `typo1` : une faute sur un mot de contenu (≥ 4 lettres, pas un mot-outil, pas un sigle, jamais un nombre) : suppression, inversion de deux lettres, touche voisine (AZERTY) ou accent manquant.
- `typo3` : deux ou trois fautes, sur des mots distincts.
- `noaccent` : tous les accents retirés.
- `telegraphic` : mots-outils et formules interrogatives supprimés (négations et « sans/avec » gardées).
- `abbr` : forme longue → sigle, avec le seul glossaire du corpus (entrées définies dans ≥ 2 documents).
- `expand` : sigle → forme longue principale, même glossaire.
- `abbr_user` (diagnostic, **hors règle « glossaire du corpus »**) : les 7 sigles cités par l'utilisateur dans sa demande (ABP, ATB, IOT, ALR, RTUP, PTH, VNI). Sert à mesurer le cas que le glossaire ne peut pas produire : un sigle que les recommandations n'écrivent jamais (« ABP » n'apparaît dans aucun chunk en vigueur).

## Reproduire

```bash
.venv/bin/python eval_internal/robustness/build_glossary.py
.venv/bin/python eval_internal/robustness/perturb.py
eval_internal/robustness/run_all.sh          # ~35 min, sous verrou GPU
.venv/bin/python eval_internal/robustness/analyze.py > eval_internal/robustness/results/summary.md
```

## Git

`sets/abpe171/` (texte du benchmark des experts) et `results/*.jsonl` (lignes brutes) restent locaux (`.gitignore`). Les jeux `multirfe_synth`, le glossaire, les scripts et `results/summary.md` sont versionnés.
