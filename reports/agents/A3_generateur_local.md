# A3 — Substitut local au générateur ~30B (Mac M2 Pro 16 Go)

Date : 2026-11-27. Agent A3. Aucune modification du code du dépôt, aucun commit.

## 1. Recommandation

**Modèle retenu : Qwen3.5-9B (instruct, 4 bits MLX, `mlx-community/Qwen3.5-9B-MLX-4bit`, Apache-2.0, 5,95 Go), à utiliser avec le mode « réflexion » désactivé.**

| Élément | Valeur |
|---|---|
| Snapshot téléchargé (poids d'origine) | `/Users/tim/.cache/huggingface/hub/models--mlx-community--Qwen3.5-9B-MLX-4bit/snapshots/938d8919941c6e7efd3c7150eff7fe9d12afa631` |
| **Chemin à passer à `--mlx-model-path`** | **`/Users/tim/.cache/rag_sfar_models/Qwen3.5-9B-MLX-4bit-nothink`**. Ce dossier contient des liens symboliques vers les poids du snapshot et un `chat_template.jinja` modifié sur une ligne pour toujours désactiver la réflexion (voir §4.1). |
| Nom pour `--model` | `qwen3.5-9b-4bit-nothink` |
| Vitesse (machine peu chargée) | prefill ≈ 220–240 tokens/s, génération ≈ 35 tokens/s |
| Vitesse (avec les jobs de l'autre agent en parallèle) | prefill 150–220 tokens/s, génération 12–17 tokens/s |
| Latence par question, harnais C9 (≈ 2 200 tokens de prompt) | 13,7 s en moyenne (machine peu chargée) ; 20 s sous contention |
| Latence par question, contexte large (17 à 30 passages, 6 000–8 800 tokens) | ≈ 51 s en moyenne (sous contention) |
| Mémoire, modèle seul (pic MLX) | 6,7 Go à 2 k tokens ; 7,2 Go à 7,7 k ; 7,8 Go à 12,3 k ; 8,4 Go à 18,5 k |
| Mémoire, processus complet du harnais (embedder + reranker + index + LLM) | pic 10,2 Go (C9) ; **10,8 Go avec le contexte large** |
| **Contexte maximal validé** | **60 000 caractères ≈ 18 500 tokens** (test synthétique) ; **≈ 28 000 caractères / 8 800 tokens dans le harnais**, sans erreur Metal. Échec mémoire Metal à 100 000 caractères (≈ 31 k tokens). |

Pourquoi ce modèle :

1. **Il est de la même famille que la cible.** Qwen3.5-9B a la même architecture (`qwen3_5` : attention hybride gated-delta et attention complète) que Qwen3.6-35B-A3B, Qwen3.6-27B et Qwen3.8-27B, les modèles Qwen de classe ~30B qu'on déploiera probablement sur LibreDataHub. Il a aussi le même tokenizer et le même format de chat (ChatML avec `<think>`). J'ai comparé les templates : seule diffère la gestion de l'historique multi-tour, sans effet pour nos prompts à un tour. Un prompt mis au point sur ce 9B a donc les meilleures chances de se transposer au 30B.
2. **Ses scores multilingues sont les meilleurs des candidats < 10 Go.** Fiche officielle : MMMLU 81,2 ; MMLU-ProX 76,3 ; INCLUDE 75,6. Il dépasse Qwen3-30B-A3B-Thinking-2507 (78,4 / 69,1 / 74,4) et GPT-OSS-20B ([Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)). Attention, ces scores sont mesurés en mode réflexion : on ne dispose d'aucun score français isolé.
3. **Il garde de la marge en mémoire pour un long contexte.** Seules 8 couches sur 32 utilisent une attention complète (4 têtes KV × 256), d'où un cache KV d'environ 0,33 Go pour 10 k tokens, contre environ 1,6 Go pour un 14B dense. C'est **le seul candidat testé qui passe le contexte de ~25 000 caractères** sur cette machine.
4. **Sur les 12 questions de l'essai, ses réponses sont propres** : 92 à 100 % sont sourcées [Sx] et toutes respectent le format concis.

Second candidat testé : Ministral-3-14B-Instruct-2512 (4 bits). Il est **écarté** : plus lent d'un facteur 3 à 4, il dépasse la mémoire dès 18 000 caractères de prompt et ne cite ses sources que dans 42 % des réponses (§3).

## 2. Candidats recensés

Les tailles proviennent de l'API Hugging Face (somme des `.safetensors`, 2026-11-27). Tous les dépôts listés ne contiennent que des safetensors, sauf mention contraire.

Le cache KV est estimé en fp16 pour 10 k tokens, avec la formule 2 × couches à attention complète × têtes KV × dim tête × 2 octets × tokens (avec fenêtre glissante quand elle existe). La RAM estimée vaut poids + KV + environ 1 Go d'activations de prefill. Il faut y ajouter environ 2 à 3 Go pour le harnais (embedder, reranker, index). Sur cette machine, MLX recommande au plus 12,7 Go de « working set ». Par ailleurs, un `rag-sfar-serve` lancé par un tiers (Qwen2.5-3B, PID 65862) occupe déjà 4,2 Go de RAM résidente en permanence.

| Modèle (dépôt MLX) | Fichiers | Licence | Contexte natif | KV 10 k tok. | RAM estimée à 10 k | Qualité attendue en français (sources) | Verdict |
|---|---:|---|---:|---:|---:|---|---|
| **mlx-community/Qwen3.5-9B-MLX-4bit** | **5,95 Go** | Apache-2.0 | 262 k | 0,33 Go | **≈ 7,2 Go (mesuré)** | MMMLU 81,2, MMLU-ProX 76,3, INCLUDE 75,6 ([fiche Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)) | **Retenu** |
| mlx-community/Ministral-3-14B-Instruct-2512-4bit | 8,42 Go | Apache-2.0 | 256 k | 1,64 Go | ≈ 11 Go (mesuré : 9 Go à 3,8 k tok.) | Multilingual MMLU 74,2 (base) ; Arena Hard 0,551 contre 0,427 pour Qwen3-14B ; français cité parmi les langues principales ([fiche](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512), [rapport Ministral 3](https://arxiv.org/pdf/2601.08584)) | Testé, écarté (mémoire, vitesse, citations) |
| mlx-community/gemma-4-12B-it-4bit | 6,74 Go | Apache-2.0 | 256 k | ≈ 1,0 Go (8 couches complètes + 40 glissantes de 1 024) | ≈ 8,7 Go | MMMLU 83,4, au-dessus de Qwen3.5-9B ([fiche Gemma 4 12B](https://huggingface.co/google/gemma-4-12B-it)) | Non testé. Meilleur 3e choix, mais architecture et template différents de la cible Qwen |
| mlx-community/Qwen3-14B-4bit | 8,31 Go | Apache-2.0 | 40 k | 1,64 Go | ≈ 11 Go | Multilingual MMLU 75,4 (base, d'après la fiche Ministral 3) ; génération précédente | Dominé par Qwen3.5-9B |
| mlx-community/Qwen2.5-14B-Instruct-4bit | 8,31 Go | Apache-2.0 | 32 k | 1,97 Go | ≈ 11,3 Go | Génération 2024 | Dominé |
| mlx-community/phi-4-4bit | 8,25 Go | MIT | 16 k | 2,05 Go | ≈ 11,3 Go | Entraîné surtout en anglais ; multilinguisme faible d'après la fiche Microsoft | Écarté |
| mlx-community/gemma-3-12b-it-qat-4bit | 8,03 Go | Gemma | 128 k | ≈ 1,0 Go | ≈ 10 Go | Multilingual MMLU 69,0 (base, d'après la fiche Ministral 3) | Remplacé par Gemma 4 |
| mlx-community/Mistral-Nemo-Instruct-2407-4bit | 6,89 Go | Apache-2.0 | 128 k (annoncé 1 M) | 1,64 Go | ≈ 9,5 Go | Bon en français, mais date de 2024 | Dominé par Ministral 3 |
| mlx-community/Llama-3.1-8B-Instruct-4bit | 4,52 Go | Llama 3.1 | 128 k | 1,31 Go | ≈ 6,8 Go | Inférieur à Qwen2.5-7B en français médical (pas de score dédié) | Écarté |
| mlx-community/Mistral-Small-3.2-24B-Instruct-2506-4bit | 13,26 Go | Apache-2.0 | 128 k | 1,64 Go | ≈ 16 Go | Très bon en français | **Ne tient pas** |
| mlx-community/Mistral-Small-3.1-24B-Instruct-2503-3bit | 11,14 Go | Apache-2.0 | 128 k | 1,64 Go | ≈ 13,8 Go | Bon, dégradé par le 3 bits | Ne tient pas avec le harnais (voir §5) |
| mlx-community/EuroLLM-22B-Instruct-2512-mlx-4bit | 12,73 Go | Apache-2.0 | 32 k | 2,2 Go | ≈ 16 Go | Conçu pour les langues européennes | Ne tient pas |
| mlx-community/Qwen3-30B-A3B-3bit | 13,36 Go | Apache-2.0 | 40 k | 0,98 Go | ≈ 15,3 Go | Proche de la cible | Ne tient pas |
| mlx-community/Qwen3-30B-A3B-Instruct-2507-4bit | 17,18 Go | Apache-2.0 | 262 k | 0,98 Go | > 18 Go | Cible plausible | Ne tient pas |
| mlx-community/Qwen3.6-35B-A3B-4bit | 20,4 Go | Apache-2.0 | 262 k | 0,2 Go | > 21 Go | Cible plausible (MMLU-Pro 85,2) | Ne tient pas |
| mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit-REAP-19B | 13,22 Go | Apache-2.0 | 262 k | 0,2 Go | ≈ 14,5 Go | Variante élaguée (128 experts sur 256) de la cible | Au-delà du working set de 12,7 Go |
| mlx-community/Qwen3.6-27B-4bit, Qwen3.8-27B-4bit, Qwen3.8-27B-mxfp4 | 16,05 / 16,05 / 15,21 Go | Apache-2.0 | 262 k | 0,5 Go | > 16 Go | Cible plausible | Ne tient pas |
| mlx-community/gemma-4-26b-a4b-it-4bit | 15,34 Go | Apache-2.0 | 256 k | ≈ 0,6 Go | > 16 Go | MMMLU 86,3 | Ne tient pas |
| mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit-REAP-14B | 11,2 Go | Apache-2.0 | 256 k | ≈ 0,6 Go | ≈ 12,5 Go | Variante élaguée (64 experts sur 128), qualité non publiée | Option > 10 Go (§5) |
| mlx-community/Qwen3.5-9B-8bit | 10,43 Go | Apache-2.0 | 262 k | 0,33 Go | ≈ 11,5 Go | Même modèle, quantification moins destructive | Option > 10 Go (§5) |
| mlx-community/Qwen3.8-Flash-Next-4bit | 111,5 Go | — | 262 k | — | — | — | Hors sujet (MoE de 512 experts) |

Prise en charge par mlx-lm 0.32.2 : `qwen3_5`, `ministral3` et `gemma4` (y compris `gemma4_unified` par remappage) sont tous gérés. Les dépôts Qwen3.5 et Ministral 3 sont des conversions mlx-vlm qui incluent la vision ; `mlx_lm` ignore ces poids. Aucune comparaison directe en français entre ces trois modèles n'a été publiée (recherche web, 2026-11-27).

## 3. Résultats des essais (multirfe_synth dev, C9, `clinical_concise`, `--max-tokens 250`, `--limit 12`)

**Contexte de mesure.** Un autre agent a enchaîné en parallèle des évaluations retrieval et des constructions d'index (`b1eval.py`, `rag-sfar-eval --retrieval-only`, `build-index`). Le serveur `rag-sfar-serve` tiers (4,2 Go) tournait en permanence. J'ai attendu les créneaux libres quand c'était possible, mais plusieurs mesures ont été faites sous contention : leurs latences sont donc pessimistes. Le « correct » de ce tableau est la notation déterministe du harnais sur 12 questions. Elle est **non concluante** (IC à ±30 points) et ne doit pas servir à comparer la qualité des modèles : il faut un juge et le split complet.

| Run | Rapport | Passages (prompt) | Tokens de prompt (méd./max) | Latence/q (moy.) | Correct (dét.) | Sourcé | Fausse abstention | Pic mémoire du processus | Erreur Metal |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| Qwen3.5-9B, C9 | `reports/eval/20261127-013607_multirfe_synth_dev_smoke_qwen35_9b.*` | 2–6 | 2 208 / 2 501 | **13,7 s** | 7/12 | 11/12 | 1/12 | 10,2 Go | non |
| Qwen3.5-9B, `--ablate final_top_k=16+context_window=1+expand_table_parent=true` | `reports/eval/20261127-014352_multirfe_synth_dev_smoke_qwen35_9b_ctx16.*` | **toujours ≤ 6** | 2 264 / 2 610 | 19,5 s (base rejouée : 17,3 s) | 8/12 | 10/12 | 4/12 | 10,3 Go | non |
| Qwen3.5-9B, même ablation **+ `use_context_pruning=false+max_context_chars=30000`** | `reports/eval/20261127-035035_multirfe_synth_dev_smoke_qwen35_9b_ctxwide.*` | **17–30** | **7 373 / 8 835** | 50,9 s (sous contention) | 8/12 | **12/12** | 0/12 | **10,8 Go** | **non** |
| Ministral-3-14B, C9 | `reports/eval/20261127-015754_multirfe_synth_dev_smoke_ministral3_14b.*` | 2–6 | 2 208 / 2 467 | 45,3 s | 7/12 | **5/12** | 3/12 | 12,7 Go | non |
| Ministral-3-14B, ablation ctx16 (contexte toujours ≤ 6) | `reports/eval/20261127-022024_multirfe_synth_dev_smoke_ministral3_14b_ctx16.*` | ≤ 6 | 2 204 / 2 577 | 53,6 s | 6/12 | 5/12 | 4/12 | 12,4 Go | non |
| *Référence : Qwen2.5-7B, C9 concis v1 (mêmes 12 questions)* | `reports/eval/20261126-174431_multirfe_synth_dev_c9_concise.json` | ≤ 6 | ≈ 2 130 | 8,5 s | 7/12 | 7/12 | — | — | — |

**Point important pour la suite : la commande `--ablate "final_top_k=16+context_window=1+expand_table_parent=true"` n'élargit pas le contexte du générateur.** La fonction `build_generation_context` (`src/rag_sfar/generation/client.py`) applique `generation_budget()` : au plus 6 passages et 6 500 caractères en mode concis, tant que `use_context_pruning=True`. Le prompt reste alors à environ 2 200 tokens. Pour obtenir les ~25 000 caractères visés, il faut ajouter `use_context_pruning=false` et relever `max_context_chars` (16 000 par défaut dans `RetrievalConfig`). C'est ce que fait la 3e ligne, comparable au « ctx12 » de Sonnet dans `eval_internal/frontier_generator.py`.

Micro-banc mémoire et vitesse (`mlx_lm.stream_generate`, contexte synthétique en français, 250 tokens au plus, pic mesuré par `mx.get_peak_memory`, mémoire du processus par `/usr/bin/time -l`) :

| Modèle | Caractères | Tokens de prompt | Prefill (tok/s) | Génération (tok/s) | Pic MLX | Pic processus | Résultat |
|---|---:|---:|---:|---:|---:|---:|---|
| Qwen3.5-9B | 6 500 | 2 077 | 217 | 35,3 | 6,71 Go | 7,6 Go | OK |
| Qwen3.5-9B | 25 000 | 7 747 | 238 (147 sous contention) | 34,9 (15 sous contention) | 7,18 Go | 8,0–8,2 Go | OK |
| Qwen3.5-9B | 40 000 | 12 335 | 186–194 | 15–17 (contention) | 7,78 Go | 8,8–9,0 Go | OK |
| Qwen3.5-9B | 60 000 | 18 487 | 218 | 11,9 (contention) | 8,38 Go | 9,6 Go | OK (une première tentative, avec 3 jobs tiers actifs, a échoué faute de mémoire) |
| Qwen3.5-9B | 100 000 | ≈ 31 000 | — | — | — | 8,2 Go | **Insufficient Memory** |
| Ministral-3-14B | 6 500 | 2 065 | 73 | 11,7 | 8,56 Go | 9,0 Go | OK |
| Ministral-3-14B | 12 000 | 3 766 | 61 | 11,1 | 8,99 Go | 9,6 Go | OK (contexte maximal validé) |
| Ministral-3-14B | 18 000 et 25 000 | — | — | — | — | 10,1 Go | **Insufficient Memory** (deux fois à 25 k) |

Le prefill est l'étape qui sature la mémoire : à mesure que le contexte s'allonge, les blocs de 2 048 tokens produisent des scores d'attention de plus en plus gros. La limite dépend donc aussi de la RAM libre, que réduisent le serveur tiers de 4,2 Go et les autres jobs.

Observations qualitatives sur les 12 questions :
- **Qwen3.5-9B** respecte le format concis (réponse, puis [Sx], puis ligne « Source : »). Sur MR-g3b9708b3518cddf9bccf, il dit « Non, le patient ne peut pas rentrer » alors que la règle est « oui, s'il remplit les critères » : c'est une erreur de raisonnement typique d'un petit modèle. Avec le contexte large, il cite toutes ses réponses et ne fait aucune fausse abstention.
- **Ministral-3-14B** met beaucoup de markdown en gras, omet souvent les [Sx] (sourcé 5/12) et s'abstient à tort (MR-gd9a325c36650ee68a17f). Au chargement, transformers avertit d'une regex de pré-tokenisation Mistral incorrecte (`fix_mistral_regex=True` conseillé). Notre client ne passe pas cette option, ce qui peut dégrader légèrement la tokenisation.

## 4. Points d'attention pour l'utilisation dans le harnais

1. **Mode réflexion de Qwen3.5 et des autres modèles Qwen ≥ 3.5.** La réflexion est activée par défaut, et mlx-lm 0.32 injecte `enable_thinking=True` lorsque l'appelant ne précise rien (`TokenizerWrapper.apply_chat_template` dans `mlx_lm/tokenizer_utils.py`). Avec le snapshot d'origine, le modèle consacre ses 250 tokens à un « Thinking Process » en anglais, sans jamais donner de réponse. Je n'ai pas modifié le dépôt : le dossier `…/rag_sfar_models/Qwen3.5-9B-MLX-4bit-nothink` contient un template dont la ligne 149 est remplacée par `{%- if true %}`, ce qui produit toujours `<think>\n\n</think>`. **Correction recommandée dans le code** : passer `enable_thinking=False` à `apply_chat_template` dans `LocalMlxLLM._format_prompt`, et `chat_template_kwargs={"enable_thinking": False}` côté vLLM/OpenAI pour la cible LibreDataHub, car Qwen3.6 et Qwen3.8 réfléchissent aussi par défaut.
2. **Contexte large** : utiliser `final_top_k=16+context_window=1+expand_table_parent=true+use_context_pruning=false+max_context_chars=30000`. Validé jusqu'à environ 8 800 tokens dans le harnais (pic de 10,8 Go), sans erreur Metal.
3. **Rythme** : environ 14 s par question avec 6 passages, environ 50 s avec 17 à 30 passages (sous contention ; probablement 35 à 40 s sur machine libre). Une passe complète de multirfe dev (94 q.) prendrait donc environ 25 min en contexte étroit et 60 à 80 min en contexte large.
4. **Mémoire partagée** : arrêter le `rag-sfar-serve` tiers (PID 65862, Qwen2.5-3B, 4,2 Go résidents) libérerait de la marge, mais c'est à l'utilisateur d'en décider. Les erreurs « Insufficient Memory » relevées ici sont toutes survenues pendant que d'autres jobs tournaient.
5. Échantillonnage : le harnais génère en greedy (température 0). Pour le mode sans réflexion, Qwen recommande température 0,7, top_p 0,8 et presence_penalty 1,5. Je n'ai observé aucune répétition en greedy sur 36 réponses (une seule a atteint les 250 tokens).

## 5. Option > 10 Go (non téléchargée, décision de l'utilisateur)

Aucun modèle « nettement meilleur » entre 10 et 13 Go ne tient de façon fiable avec le harnais sur cette machine. Le working set recommandé est de 12,7 Go, et le harnais seul (embedder, reranker, index) consomme environ 3 Go. Les seules pistes réalistes sont :

- **mlx-community/Qwen3.5-9B-8bit (10,43 Go, Apache-2.0)** : c'est le même modèle avec moins de perte de quantification, sans doute quelques points de mieux en raisonnement. Pic estimé d'environ 13 Go pour le processus du harnais à 8 k tokens, soit à la limite : il faudrait arrêter le `rag-sfar-serve` tiers. Génération estimée à environ 20 tok/s.
- **mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit-REAP-14B (11,2 Go, Apache-2.0)** : un MoE à 4 B de paramètres actifs, issu du Gemma 4 26B (MMMLU 86,3), dont la moitié des experts a été élaguée (REAP). C'est le seul modèle de « classe ~25B » qui pourrait entrer. Mais sa qualité après élagage n'est pas publiée, il n'est pas de la famille Qwen de la cible, et il serait à la limite de la mémoire.
- Exclus : Mistral-Small-3.1-24B en 3 bits (11,1 Go poids + 1,6 Go KV + harnais, au-delà de 15 Go) et Qwen3.6-35B-A3B-REAP-19B (13,2 Go, au-delà du working set).

Le gain de ces options par rapport à Qwen3.5-9B en 4 bits est incertain, et elles nous priveraient de la marge pour le contexte large. Je ne recommande pas de les télécharger maintenant. Pour approcher le comportement du 30B, la voie la plus sûre reste un point de mesure ponctuel sur LibreDataHub, ou par API ouverte si l'utilisateur l'autorise.

## 6. Fichiers

- Rapports d'essai : `reports/eval/20261127-013607_…smoke_qwen35_9b.*`, `…014352_…smoke_qwen35_9b_ctx16.*`, `…035035_…smoke_qwen35_9b_ctxwide.*`, `…015754_…smoke_ministral3_14b.*`, `…022024_…smoke_ministral3_14b_ctx16.*`.
- Modèles téléchargés (cache HF, hors dépôt) : Qwen3.5-9B-MLX-4bit (5,95 Go), Ministral-3-14B-Instruct-2512-4bit (8,42 Go, snapshot `…/models--mlx-community--Ministral-3-14B-Instruct-2512-4bit/snapshots/95b6f345475c8c8c92b7959d02f4ad86d3ba8384`, supprimable s'il ne sert pas).
- Dossier dérivé sans réflexion : `/Users/tim/.cache/rag_sfar_models/Qwen3.5-9B-MLX-4bit-nothink`.
