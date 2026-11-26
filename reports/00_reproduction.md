# 00 — Reproduction des résultats annoncés dans le README

Date : 2026-11-26. Machine : Mac Apple Silicon, Python 3.14, index existants dans `index/` (non reconstruits).

## Conclusions

1. **Les chiffres de retrieval se reproduisent à l'identique** (même code, mêmes index, calcul déterministe). Ce n'est pas une validation : c'est la preuve que le code produit bien ces nombres.
2. **Ces métriques de retrieval sont trop permissives pour départager des systèmes.** Huit chunks **tirés au hasard** dans la RFE antibioprophylaxie en vigueur obtiennent **80,9 %** d'« evidence recall » (min 74,6 %, max 85,5 % sur 30 tirages), contre 92,0 % pour le BM25 naïf et 99,3 % pour C8. Raison : 59 des 138 questions notées n'exigent que la chaîne « pas d'antibioprophylaxie » et 42 la seule « céfazoline », présentes partout dans ce document.
3. **« Édition hit » et « intrusion obsolète » se résument à** : un chunk dont le titre contient « antibioprophylaxie » et dont l'année ≥ 2023 figure-t-il dans le top 8 ? Sur un benchmark mono-document, c'est presque gratuit dès que le filtre d'édition est actif.
4. **Le stress-test multi-RFE (30 questions)** est codé en dur dans `src/rag_sfar/evaluation/benchmarks.py`, écrit par la même équipe que le système, avec des termes de preuve choisis à la main. Il n'a pas valeur de test indépendant.
5. **End-to-end** : C8 (100 % sur le jeu « stratifié », 86 % sur les « inédites ») et zero-shot (52 %) se reproduisent exactement ; **le C0 naïf ne se reproduit pas (72 % mesurés contre 84 % annoncés)**. Une baseline constante fait 58 % sur les « inédites ». Section 3.
6. La suite de tests passe : **19/19** (`pytest -q`, 3 s).

## 1. Environnement et tests

```bash
.venv/bin/pip install -e ".[neural,dev]"
.venv/bin/python -m pytest -q        # 19 passed in 3.05s
```

Paquets clés : torch 2.15, sentence-transformers 6.3, transformers 5.24, mlx-lm 0.32. Modèles en cache : multilingual-e5-small, mmarco-mMiniLMv2 (cross-encoder), Qwen2.5-1.5B/3B/7B-Instruct-4bit (MLX).

## 2. Ablation de retrieval (README §1 et §2)

Commande (sortie dans un dossier séparé pour ne pas écraser les rapports d'origine) :

```bash
HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-eval --index-root index --output-dir reports/repro
```

Résultat : `reports/repro/ablation_results.json`, `reports/repro/ablation_report.md`.

| Jeu | Config | Annoncé (Ev. recall / MRR) | Mesuré | Écart |
|---|---|---|---|---|
| antibioprophylaxie_171 | C0 naïf BM25 | 92,0 % / 0,803 | 92,0 % / 0,803 | aucun |
| antibioprophylaxie_171 | C6 hybride + métadonnées | 97,8 % / 0,983 | 97,8 % / 0,983 | aucun |
| antibioprophylaxie_171 | C7 rerank + callouts | 99,3 % / 0,985 | 99,3 % / 0,985 | aucun |
| antibioprophylaxie_171 | C8 frontier | 99,3 % / 0,982 | 99,3 % / 0,982 | aucun |
| multi_rfe_stress_30 | C8 frontier | 96,7 % / 1,000 | 96,7 % / 1,000 | aucun |

Toutes les autres colonnes (édition hit, intrusion obsolète, allergie) sont identiques. Seuls changent les tokens estimés (±1 %, ordre de dédoublonnage) et la latence (C8 : 210 ms/requête mesurés contre 744 ms annoncés, cache chaud).

### Ligne de base aléatoire (ajoutée)

Pour chaque question, 8 chunks non bibliographiques tirés au hasard parmi les 787 chunks de la RFE antibioprophylaxie 2026 (V3.0), 30 tirages :

| Système | Evidence recall (138 questions) |
|---|---:|
| 8 chunks aléatoires du bon document | 80,9 % (74,6–85,5 %) |
| C0 naïf BM25 | 92,0 % |
| C8 frontier | 99,3 % |

Conclusion : l'écart utile entre systèmes se joue sur ~20 points dont une partie est du bruit (138 questions). Ces métriques ne mesurent pas si le **bon passage** (la bonne ligne de tableau, la bonne recommandation) est retrouvé. Il faut une vérité terrain au niveau du passage (phase 2).

## 3. End-to-end (README §3)

Le script `scripts/run_e2e_eval.py` ne permettait pas de rejouer l'échantillon « 50 inédites » (aucune option de sélection correspondante). J'ai ajouté une option rétrocompatible `--ids-file` et extrait les identifiants exacts des rapports d'origine (`reports/repro/*_ids.json`). Commande : `bash reports/repro/run_e2e_repro.sh`.

Notation utilisée par le script (`src/rag_sfar/evaluation/benchmark_adapter.py:22-43`) :
- question ouverte juste si **toutes** les molécules attendues apparaissent comme sous-chaînes de la réponse : une réponse qui énumère plusieurs molécules est comptée juste ;
- QCM juste si la **première lettre isolée A–D** de la réponse en majuscules est la bonne : le verbe « a » devient « A » ;
- « sourcing » = présence d'un nombre à 4 chiffres (une année) dans la réponse.

Résultats (Qwen2.5-7B-Instruct-4bit, MLX, Mac Apple Silicon ; scorer du script, identique au scorer officiel) :

| Jeu (50 q.) | Système | Annoncé | Mesuré | Écart | IC 95 % (Wilson) |
|---|---|---:|---:|---|---|
| « stratifié » | Zero-shot | 52 % | 52 % (26/50) | aucun | [38 ; 65] |
| « stratifié » | C0 RAG naïf | 84 % | **72 %** (36/50 ; open 28/40, QCM 8/10) | **−12 pts** | [58 ; 83] |
| « stratifié » | C8 | 100 % | 100 % (50/50) | aucun | [93 ; 100] |
| « inédites » | C8 | 86 % | 86 % (43/50 ; mêmes 7 erreurs) | aucun | [74 ; 93] |
| « inédites » | Baseline constante (« Pas d'antibioprophylaxie » / « C ») | — | **58 %** | ajouté | [44 ; 71] |

Lecture :
- Les chiffres C8 et zero-shot se reproduisent. Le C0 ne se reproduit pas (−12 points). Hypothèse la plus probable : le code commun (prompts, client) a été modifié après le run C0 d'origine. L'audit d'intégrité date ces modifications de 06:36–07:08, après les premiers runs. Le C0 annoncé n'a donc pas été mesuré avec le code actuel.
- Le « stratifié » est un **jeu de développement** : 13 des 50 questions sont visées par une règle ou un exemple écrit à partir d'elles (`reports/agents/audit_integrite_evaluation.md`). Le 100 % n'est pas une mesure de généralisation.
- Sur les « inédites », C8 dépasse la baseline constante de 28 points. Ces questions ont toutefois servi aux ablations du retrieval : ce n'est pas un test tenu à l'écart.
- Les réponses sont courtes (« Céfazoline SFAR 2026 [S1]. »). Une seule réponse ouverte sur 40 liste deux molécules (Q42), comptée juste par le scorer. Le « sourcing 100 % » est garanti par l'ajout automatique de l'année (`client.py:372-379`).

Ces chiffres sont remplacés par l'évaluation sur les jeux scellés (`abp171` test, `multirfe_synth` test) en fin de phase 3.

## 4. Ce qui reste à établir (phase 1 et 2)

- Qualité réelle de la notation end-to-end (audit d'intégrité en cours).
- Cohérence entre les réponses de référence du benchmark (RFE v2.0) et l'édition V3.0 2026 que le système considère en vigueur.
- Performance hors antibioprophylaxie, sur des questions et des documents jamais vus.
