# B3 — Étage de génération (contexte, prompt, abstention, contrôle des réponses)

Agent B3, 2026-11-27. Brouillon : la section 6 (confirmation sur le reste de dev) sera complétée quand les réponses Sonnet de la confirmation seront jugées. Tous les chiffres sont sur les splits **dev**. Aucun `test.jsonl` n'a été ouvert ni évalué.

## 0. En bref

- **Configuration retenue** : retrieval figée `C10_context_notes` sur `index/tas_v6` ; contexte « structuré » (preset `wide`) ; prompt `clinical_concise` pour les questions ouvertes ; QCM routés **par le moteur** vers `clinical_mcq` ; ni note de dépendance de population, ni note de couverture ; contrôle déterministe des réponses en mode « avertissement ».
- **Générateur** : décision de l'utilisateur (2026-11-27 matin), on abandonne les petits modèles comme générateurs. Les mesures de prompt et de contexte qui comptent pour la configuration finale sont celles du substitut Sonnet. Les résultats du 9B restent la preuve « petit modèle ». **Le modèle cible (~30B) n'a jamais été mesuré** : on l'attend entre les deux substituts.
- **Ce qui a été rejeté après mesure** :
  - le prompt « production v2 » (−13,3 pts sur le 9B, effet nul sur Sonnet) ;
  - la note de dépendance de population (aucun gain avec Sonnet) ;
  - la note de couverture (aucun effet avec Sonnet) ;
  - la régénération guidée par le contrôle déterministe : elle n'a jamais été lancée, faute d'erreur que le contrôle puisse attraper (0 des 9 erreurs graves jugées).

## 1. Configuration retenue et commande

Code (branche `rag-sfar-v2`) : `src/rag_sfar/generation/{settings,context,client,prompts,answer_check}.py`.

| Élément | Valeur |
|---|---|
| Retrieval | `C10_context_notes` (B1, figée), `--index-map table_aware_sota=tas_v6` |
| Budget de contexte | preset `wide` : sélection « budget » (40 chunks / 30 000 caractères au plus), indépendante de `use_context_pruning` |
| Format du contexte | `structured` :<br>• chunks adjacents d'un même document fusionnés dans l'ordre du texte ;<br>• ordre par rang ;<br>• [Sx] numérotés dans l'ordre d'affichage ;<br>• en-tête riche (titre, année, version, statut d'édition, section, nature, population, force/accord) ;<br>• pas d'élagage de prose ;<br>• pas de note allergie. |
| Prompt, questions ouvertes | `clinical_concise` (inchangé par B3) |
| Prompt, QCM | `clinical_mcq` (= ancien `benchmark_mcq`). Le moteur y route toute question qui liste des options lettrées A., B., … (`client.route_mode`), en production comme en évaluation. |
| Réflexion (Qwen ≥ 3.5) | `enable_thinking=False` : MLX via le template ; vLLM/OpenAI via `extra_body.chat_template_kwargs` |
| Contrôle des réponses | `answer_check="flag"` (dans le preset `wide`) : avertissement ajouté à `verification.warnings`, pas de régénération ; aussi en streaming |
| Boucle de réparation des molécules | désactivée (`molecule_repair=False`, jamais mesurée) |
| Profil | `generation/profile.py::PRODUCTION`, utilisé par l'API, les deux serveurs MCP et le rejeu (`--profile production`) |
| Notes | `coverage_gate="off"`, `dependency_note=False` |

Commande de génération sur un cache de retrieval (outil de rejeu) :

```bash
# 1. retrieval une fois (sous le verrou GPU)
scripts/with_gpu_lock.sh b3-capture .venv/bin/python eval_internal/gen_replay.py capture --suite abpe171 \
    --configs C10_context_notes --index-map table_aware_sota=tas_v6 --name c10notes_v6
# 2a. générateur local ou serveur OpenAI-compatible (vLLM)
.venv/bin/python eval_internal/gen_replay.py run --cache c10notes_v6 --suite abpe171,multirfe_synth \
    --preset wide --gen-mode clinical_concise --mcq-mode route --backend openai --base-url <URL> --model <M> \
    --gen "enable_thinking=false" --tag final
# 2b. prompts capturés pour un générateur externe (substitut Sonnet), puis import
.venv/bin/python eval_internal/gen_replay.py run ... --backend record --export-frontier <DIR> --parts 12
.venv/bin/python eval_internal/gen_replay.py import-frontier --dir <DIR> --model-label claude-sonnet-5-5 --tag <tag>
```

Équivalent avec le harnais standard :

```bash
rag-sfar-eval --suite abpe171 --split dev --configs C10_context_notes \
    --index-map table_aware_sota=tas_v6 --gen-preset wide --gen-mode clinical_concise ...
```

## 2. Corrections de plomberie (piste 1)

- **Réflexion désactivable** : `LocalMlxLLM._format_prompt(enable_thinking=…)` et `OpenAICompatibleLLM._request_kwargs`, qui envoie `chat_template_kwargs` et `top_k` via `extra_body`, seulement quand ils sont définis. Les blocs `<think>` sont retirés de la sortie. Testé (`tests/test_generation_b3.py`).
- **Budget de contexte par classe de modèle** : `GenerationConfig` (`generation/settings.py`), avec trois presets :
  - `legacy` : comportement historique, par défaut ;
  - `small` : 6 chunks / 6 500 caractères ;
  - `wide`.

  On peut surcharger champ par champ (`--gen "field=value+…"`). Sans `gen_config`, le moteur garde exactement l'ancien comportement.
- **Moteur scindé** en `retrieve` + `generate` : la génération est rejouable sur un cache de retrieval.
- **Échantillonnage** : `top_p`, `top_k` et `presence_penalty` sont exposés (MLX : `make_sampler` / `make_logits_processors`). Ils n'ont pas été mesurés, tout a tourné en greedy.
- **Outil de rejeu** `eval_internal/gen_replay.py`, sous-commandes :
  - `subsets` : sous-ensembles d'itération stratifiés, graine fixe : 30 + 30 ;
  - `capture` : toute config, `--ablate`, `--index-map`, liste d'ids ;
  - `run` : MLX / OpenAI / `record` ;
  - `export-frontier` / `import-frontier` ;
  - `recheck` ;
  - `compare` : bootstrap apparié ;
  - `--system-file` / `--drop-rule` : variantes de prompt.

  Autres fichiers : file d'attente `eval_internal/b3_queue.sh`, tableau `eval_internal/b3_table.py`.

## 3. Variantes mesurées

Sous-ensembles d'itération dev (`eval_internal/work/b3_subsets/*_iter.json`) : 30 abpe171 + 30 multirfe_synth. Juge Haiku. Rubrique v2 sauf mention contraire. Valeurs abpe171 / multirfe. Deux jugements des mêmes réponses varient de 1 à 2 cas sur 30 : en dessous, c'est du bruit de juge.

### 3.1 Petit modèle (Qwen3.5-9B 4 bits MLX, sans réflexion), index `tas_v3_errata`

| Variante | Correct | Correct ou partiel | Graves | Faits oblig. | Tokens prompt | Latence | Décision |
|---|---|---|---|---|---|---|---|
| C9, budget `small` (6 chunks), concise | 73 / 73 | 83 / 90 | 3 / 3 | 88 | 2 300 / 1 800 | 13 / 10 s | référence petit contexte |
| C9 + fenêtres, `wide` structuré, concise | **77 / 83** | 83 / 93 | 3 / 7 | 88 | 6 600 / 6 700 | 30 / 30 s | **retenu (format)** |
| C9 + fenêtres, format historique (u-shape, sans fusion) | 67 / 87 | 80 / 93 | 3 / 7 | 77 | 8 600 / 7 900 | 38 / 34 s | rejeté : −18 % de tokens pour le structuré, sans perte (+3,3 pts [−6,7 ; +13,3], 60 q.) |
| `C10_context_population`, `wide` | 63 / 77 | 87 / 90 | 7 / 7 | 73 | 8 700 / 7 200 | 39 / 32 s | **périmé** : C10 a été corrigé depuis par B1. C9 + fenêtres − C10 = +10,0 pts [+1,7 ; +20,0] |
| C9 + fenêtres, production v2 (prompt unique, cap 700) | 57 / 77 | 83 / 83 | 10 / 13 | 81 | 7 300 / 6 900 | 34 / 32 s | **rejeté** : −13,3 pts [−25,0 ; −3,3], graves +6,7 [0 ; +15] |
| Variantes de formulation (v3a édition, v3c phrase d'abstention, cap 550), couverture sur concise | — | — | — | — | — | — | **non faites** : arrêt des runs 9B, abandonnées sans mesure |

La note de dépendance de population n'a jamais tourné sur le 9B ; elle n'a été mesurée qu'avec Sonnet (§ 3.2).

C9 + fenêtres contre C9 étroit : +6,7 pts [−3,3 ; +16,7], non significatif. Le 9B tire peu de bénéfice d'un contexte plus large, et sa latence est multipliée par 2,5.

### 3.2 Substitut fort (Claude Sonnet, prompts capturés), mêmes contextes

| Variante | Correct | Correct ou partiel | Graves | Remarque |
|---|---|---|---|---|
| C9 + fenêtres, concise + QCM routé (`tas_v3_errata`) | 83 / 90 | 100 / 100 | 0 / 0 | Sonnet − 9B (concise) : +6,7 pts [0 ; +15,0], graves −5,0 [−11,7 ; 0] |
| C9 + fenêtres, production v2 | 83 / 90 | 100 / 100 | 0 / 0 | v2 − concise : 0,0 [−5 ; +5] → prompt riche inutile même sur un modèle fort |
| `tas_v6`, C9 + fenêtres vs `C10_context_notes` (rubrique v3) | abpe171 : 86,7 / 86,7 ; multirfe : 27 correctes, 2 partielles, 1 incorrecte dans les deux cas | abpe171 : 100 / 100 | abpe171 : 1 (dose incohérente) / 0 ; multirfe : 0 / 0 | différence appariée sur 60 q. : 0,0 [−8,3 ; +8,3] → **C10_context_notes retenu** (retrieval figée) |
| Note de couverture (11 items signalés), off / note | 11 / 11 correctes dans les deux cas | | | **non activée** |
| Note de dépendance de population (18 items), off / note (rubrique v3) | 12 / 11 correctes, 6 / 7 partielles, 0 / 0 incorrectes | | 0 / 1 | Interdits violés : 2 / 4. **Non activée.** |

### 3.3 Taille du contexte (abpe171 iter, enregistrement sans LLM, tokenizer Qwen)

| Variante | Caractères | Tokens | Suffisance des preuves dans le contexte montré |
|---|---|---|---|
| C9, `small` | 5 900 | 2 300 | 84,6 % |
| C9 + fenêtres, format historique | 25 900 | 8 500 | 88,5 % |
| C9 + fenêtres, structuré (fusion) | 20 200 | 6 600 | 88,5 % |
| idem sans fusion | 26 300 | 8 500 | 88,5 % |
| idem + suppression des fiches-lignes déjà présentes dans leur tableau | 18 100 | 5 900 | 88,5 % |
| `C10_context_population`, structuré | 26 600 | 8 700 | 100 % |
| `tas_v6`, C9 + fenêtres | 24 400* | 7 350 | 96,2 % |
| `tas_v6`, `C10_context_notes` | 26 400* | 8 600 | 96,2 % |

\* Prompt complet, prompt système compris.

La fusion des chunks adjacents réduit le contexte de 23 % sans perdre de preuve. La suppression des fiches-lignes redondantes enlève encore 10 %. Cette dernière n'a pas été mesurée en génération : elle reste disponible (`table_rendering=drop_covered_cards`) mais n'est pas activée.

## 4. Contrôle déterministe des réponses (piste 5)

`generation/answer_check.py` vérifie :
- chaque dose (nombre + unité, liste fermée d'unités cliniques) ;
- chaque molécule (liste suivie + suffixes DCI) ;
- chaque citation [Sx].

Toutes doivent se retrouver dans les extraits montrés. Les valeurs données dans la question sont acceptées. Les mentions d'erratum de `tas_v6` (« texte initial : « 10 mg/kg » ») ne valent pas soutien.

Résultat sur les 180 réponses 9B jugées au tour 1 :
- **0 des 9 erreurs graves détectées**. Toutes étaient des erreurs de raisonnement : mauvaise ligne, sens d'un changement inversé, tranche de score mal lue, une abstention manquée. Toutes leurs doses et molécules figurent dans le contexte.
- 3 des 133 réponses correctes signalées à tort.
- Aucune dose ni molécule inventée sur ces 180 réponses.
- Le signal faible (« dose présente dans le contexte mais pas dans l'extrait cité ») attrape 2 des 9 erreurs graves (un seul item) et 1 réponse correcte sur 133 : trop peu pour décider.

Décision : mode `flag` (avertissement, coût quasi nul) ; pas de régénération. Les faux positifs ont été corrigés sur les sorties dev par des règles purement typographiques (indices HTML, « l-1 », Gauge, valeurs de la question) ; c'est déclaré ici comme réglage dev.

## 5. Abstention et clarification (pistes 3 et 4)

### Signal de couverture (B1)

Hors ligne, sur tout dev : refuser sous le seuil attrape 9 des 18 questions hors corpus de multirfe, mais refuse à tort Q28 et Q52, qui sont couvertes.

Avec Sonnet, la note de couverture ne change rien : les 11 réponses sont correctes avec ou sans elle. On ne refuse donc rien avant l'appel au LLM. Le seuil reste utile pour l'affichage, ou pour refuser des requêtes clairement hors domaine dans un déploiement grand public.

### Pourquoi la clarification échoue

Les 6 items « clarification » de abpe171 dev, examinés sur le contexte `tas_v6` :

| Item | Ce que montre le contexte | Ce qui manque | Classement |
|---|---|---|---|
| Q19 biopsie cérébrale | adulte « PAS D'ANTIBIOPROPHYLAXIE » ; enfant (biopsie stéréotaxique) « PAS D'ANTIBIOPROPHYLAXIE » | technique de biopsie (non visible) | la distinction demandée **n'est pas visible** dans les extraits : même conduite pour les deux populations |
| Q61 lambeau libre | lignes distinctes selon le site (carcinologie cervico-faciale → amoxicilline/clavulanate ; autres → céfazoline) | site receveur | visible et décisive (**site**) |
| Q85 œsophagectomie | ligne adulte seule (« avec ou sans plastie colique », même conduite) | ligne pédiatrique non retrouvée | non visible / non décisive |
| Q88 résection du grêle | adulte céfoxitine 2 g ; enfant céfoxitine 40 mg/kg | âge | visible et décisive (**population** → dose) |
| Q99 transplantation hépatique | adulte céfoxitine ; enfant « pas de recommandation consensuelle » ; texte sur la colonisation | âge, colonisation | visible et décisive (**population**, colonisation) |
| Q163 QCM fracture ouverte | ligne « Gustilo 2 ou 3 » | grade, âge | visible (**grade**) |

Constat : la frontière « clarification / réponse » du benchmark ne se lit pas dans le contexte. Sur les 81 items « réponse » sans population ni âge dans la question, 38 ont aussi des tableaux adulte et pédiatrique dans le contexte. C'est le cas de Q25, dont la référence couvre aussi l'enfant.

Le signal déterministe « deux populations présentes, aucune nommée » déclenche sur 3 des 6 items de clarification et sur 38 des 96 items « réponse ». Il ne voit ni le site (Q61) ni le grade (Q163).

Avec Sonnet, la note ajoutée sur ce signal n'apporte rien : Sonnet répond déjà cas par cas quand les extraits montrent les deux populations. Elle n'est pas activée.

**Réserve sur les métriques de clarification** : avant la rubrique v3 (commit 54e4346), le juge ne recevait pas les comportements acceptables du benchmark. Une réponse conditionnelle qui ne choisit pas était donc comptée comme violation. Les métriques de clarification jugées en rubriques v1 et v2 (tous les tours 9B) étaient trop sévères sur ces items, et on n'en tire aucune conclusion.

## 6. Confirmation sur le reste de dev

Configuration finale :
- substitut Sonnet ;
- retrieval `C10_context_notes` sur `tas_v6` ;
- prompt concise, QCM routés ;
- aucune note.

Questions : 136, soit tout dev hors sous-ensembles d'itération, exécuté une seule fois. Rubrique v3.

| Jeu | n | Correct | Correct ou partiel | Graves | Faits oblig. | Comportement accepté | Interdits violés |
|---|---|---|---|---|---|---|---|
| abpe171, confirmation | 72 | 83,3 % [75–92] | 98,6 % | 0 | 89,3 % | 95,8 % | 2 / 12 |
| multirfe, confirmation | 64 | 100 % | — | 0 | — | — | — (12 / 12 hors corpus refusées) |
| abpe171, itération (même rubrique) | 30 | 86,7 % | 100 % | 0 | | | |
| multirfe, itération | 30 | 90,0 % | | | | | |
| **abpe171, tout dev** | 102 | **84,3 % [76–91]** | 99,0 % | **0** | | | |
| **multirfe, tout dev** | 94 | **96,8 % [93–100]** | 98,9 % | **0** | | | |

Les choix faits sur les 60 questions d'itération tiennent sur les 136 autres.

Réponses abpe171 non correctes de la confirmation :
- **8 partielles** (Q27, Q40, Q46, Q102, Q114, Q118, Q119, Q132) : la réponse donne la conduite adulte seule alors que la référence attend aussi la branche pédiatrique. Pour les huit, la suffisance des preuves vaut 1,0 : la preuve pédiatrique était dans le contexte et le générateur l'a laissée de côté.
- **Q81** omet une alternative.
- **Q85 et Q88** sont des items de clarification auxquels le modèle répond pour l'adulte seulement.
- **Q131** est une abstention à tort alors que la preuve est dans le contexte.

L'omission de la branche pédiatrique est donc l'échec dominant restant sur le benchmark de référence. C'est ce que vise la note de dépendance de population. Sur le parcours de 18 items, la note n'avait rien apporté, mais la référence sans note n'y comptait qu'une seule omission de ce type.

L'ablation est **pré-enregistrée** par l'orchestrateur, sur abpe171 tout dev (n = 102, apparié).

Règle de décision fixée d'avance : activer la note seulement si :
- l'exactitude ou le taux de faits obligatoires progresse avec un IC apparié qui exclut 0 ;
- et les erreurs graves n'augmentent pas.

La note se pose sur 33 des 102 prompts abpe171. Aucune de ces 33 questions ne nomme une population ; les 15 questions qui en nomment une ne la reçoivent pas. Sur multirfe dev, la note ne se pose que sur une question (MR-g7efa49eea406c3678a28, traumatisé thoracique), exportée à part pour vérifier qu'elle n'est pas dégradée. Sur les 12 réponses non correctes listées ci-dessus, la note porterait sur 7 (Q27, Q40, Q102, Q118, Q119, Q132, Q88) ; Q46, Q114, Q81, Q85 et Q131 ne la reçoivent pas.

**Résultat (abpe171 dev)** : les 33 prompts concernés ont été régénérés avec Sonnet et jugés en rubrique v3 ; les 69 autres gardent leur verdict.

| Mesure (33 questions concernées) | Sans note | Avec note |
|---|---|---|
| Correct | 75,8 % | 69,7 % |
| Correct ou partiel | 100 % | 100 % |
| Graves | 0 | 0 |
| Faits obligatoires | 85,0 % | 95,0 % |
| Interdits violés (n = 8) | 25 % | 12,5 % |
| Comportement accepté | 90,9 % | 97,0 % |

Différences appariées sur tout dev (n = 102) :
- exactitude : −2,0 pts [−7,8 ; +3,9] ;
- faits obligatoires : +3,1 [−1,0 ; +7,3].

La règle pré-enregistrée exige un gain d'exactitude ou de faits obligatoires avec un intervalle qui exclut 0 : elle n'est pas remplie, donc **la note reste désactivée**.

Au cas par cas :
- là où elle se pose, la note corrige la branche pédiatrique omise (Q102, Q118, Q119, Q138 gagnent) ;
- cinq réponses régénérées perdent un point ailleurs, le plus souvent une molécule alternative qui n'est plus citée (Q05, Q45, Q95, Q100, Q128). C'est de l'ordre du bruit générateur et juge déjà mesuré.

La seule question multirfe qui reçoit la note reste correcte.

Lecture : prometteuse sur les faits obligatoires, non démontrée. À re-mesurer sur le modèle cible avec davantage de questions.

## 6 bis. Système servi = système évalué (suite de la revue R3)

### Profil de service unique

`generation/profile.py` définit `PRODUCTION`, seule définition de ce que le système déployé exécute :
- retrieval `C10_context_notes` (définition inchangée, figée) ;
- index `index/tas_v6` ;
- preset `wide` ;
- `clinical_concise` + routage QCM ;
- pas de provenance ajoutée par le code ;
- notes de dépendance et de couverture désactivées.

Ce profil est utilisé par :
- l'API HTTP (`create_app`, qui charge `PRODUCTION` par défaut) ;
- le serveur MCP HTTP et le serveur MCP stdio, qui renvoient exactement les passages et le bloc de contexte que lit le générateur évalué ;
- l'outil de rejeu (`--profile production`).

### Changements apportés au preset `wide`

L'incohérence relevée par la revue est corrigée : le preset passe à `answer_check="flag"`, `molecule_repair=False` (la boucle de réparation par un second appel au LLM n'a jamais été mesurée) et `max_tokens=1024`. Les prompts ne changent pas. Le chemin en streaming calcule maintenant aussi le contrôle (avertissement, pas de régénération).

### Ce qui a changé dans l'API

| Avant | Maintenant |
|---|---|
| Index `index/sota_default` | `index/tas_v6`, sauf argument explicite ou variable `RAG_SFAR_INDEX_DIR`. Le réglage `Settings.index_dir` n'est **pas** modifié : il sert aussi de dossier de sortie par défaut de `rag-sfar-index`. |
| `RetrievalConfig` ad hoc construit à chaque requête | Configuration du profil. Les champs de requête `top_k`, `use_reranker`, `use_hybrid`, `use_lexicon` et `expand_callouts` sont acceptés mais ignorés. |
| Mode `clinical_detailed` | Mode `clinical_concise` |
| Provenance ajoutée en QCM | Supprimée. `Settings.api_attach_provenance` n'est plus lu par l'API. |
| Second appel de réparation des molécules | Supprimé |
| Plafond MLX de 420 tokens | Plafond du profil (1 024) |

### Preuves

- `tests/test_generation_b3.py::test_api_prompt_identical_to_replay_prompt` : pour une question ouverte et un QCM synthétiques, avec un LLM enregistreur, le prompt système et le prompt utilisateur envoyés par `/api/query` et par `/v1/chat/completions` sont identiques octet pour octet à ceux du rejeu (cache de retrieval sérialisé puis `replay_generate`). Les plafonds et options d'appel sont identiques aussi.
- `tests/test_generation_b3.py::test_replay_reproduces_existing_dev_prompts` : le rejeu `--profile production` reconstruit octet pour octet les prompts de l'export de confirmation. Testé aussi sur les 136 prompts.

### Ce qui reste différent entre servi et évalué

- **Le modèle** : substitut Sonnet contre LLM servi. Température et réflexion ne sont pas maîtrisées chez les agents. Plafond de 1 024 tokens côté servi, aucun côté agents. Les agents répondent à jusqu'à 8 cas par session.
- **Paramètres de requête** : l'API honore encore `latest_only` et `domains` (par défaut `None`, donc identique à l'évalué).
- **Modes non évalués** : les modèles `/v1` `rag-sfar-benchmark-open` et `-mcq` restent disponibles.
- **Repli** : si le LLM est indisponible, l'API se replie sur le mode retrieval seul.
- **MCP** : l'outil `compare_sfar_editions` garde sa propre configuration (toutes éditions). Le `top_k` du MCP HTTP tronque la liste des passages.

### Outil de rejeu

- **Split** : `--split dev|test`, avec la même garde que `rag-sfar-eval` (`--allow-test` et vérification du coffre-fort avant toute lecture).
- **Arguments explicites** : retrieval et index sont obligatoires (`--profile` ou `--configs` + `--index-map`), le preset aussi (`--profile` ou `--preset`). Plus aucun défaut silencieux.
- **Clés proxy** : celles qui ne valent que sur dev sont désactivées hors dev.
- **Exports aveugles** : identifiants opaques aléatoires, cas mélangés, un sous-dossier `part_NN/` d'au plus 8 cas par agent. La correspondance est rangée hors de l'export (`work/replay/frontier_keys/`).
- **Import** : il refuse toute réponse manquante, mal rangée ou en double, et les réponses longues identiques sur deux cas. Il revérifie que chaque prompt contient sa question et calcule `check_flag` sur chaque réponse importée.
- **Consignes aux agents** : `eval_internal/GENERATOR_INSTRUCTIONS.md`.

### Limites signalées par la revue, non corrigées

- Le routage QCM reconnaît le format du harnais (`A. ` / `A) ` en début de ligne). Une question ordinaire qui énumère des éléments lettrés serait routée en QCM. Un QCM présenté autrement ne serait pas reconnu.
- Le mode QCM impose une lettre unique : un QCM sans réponse unique ne peut pas être réussi.
- La liste de molécules du vérificateur (`verifier.TRACKED_MOLECULES`, reprise par le contrôle) couvre surtout les antibiotiques et les anticoagulants. Les suffixes DCI élargissent un peu, sans couvrir toute la pharmacopée.

## 7. Analyse des échecs (9B et Sonnet)

- **Raisonnement du petit modèle** (la cause dominante) :
  - mauvaise ligne d'un tableau alors que la bonne est dans le contexte (Q69 : la ligne « Annexectomie … Céfazoline » est au rang 10, le 9B prend la ligne voisine « pas d'ABP ») ;
  - sens d'un changement entre éditions inversé ;
  - tranche de score mal lue ;
  - limite de dose d'une autre molécule rattachée à la mauvaise.
- **Abstentions à tort du 9B** alors que la preuve est montrée : Q83, Q128, Q44. Elles se multiplient quand le contexte s'élargit (C10). Pour Q83, une partie de la cause vient de l'ingestion : tableau sans en-têtes (« Col 1 ») dans `tas_v3_errata`, corrigé dans `tas_v6`.
- **Recopie du prompt** : la mention « édition antérieure » sur Q42 et Q95 n'est **pas** un bug d'en-tête. L'en-tête affiche « V3.1 — en vigueur » ; le 9B recopie la formulation de la règle 4 du prompt concise.
- **Troncature** : QCM coupés à 320 tokens (Q149) et comparaisons à 400. C'est un problème du 9B verbeux en contexte large ; non mesuré avec Sonnet.
- **Retrieval** : la seule erreur multirfe de Sonnet sur `tas_v6` est une abstention sur la question que la retrieval manque.
- **Ambiguïté du benchmark** : la frontière entre items de clarification et items de réponse (§ 5).

## 8. Attendus pour un modèle ~30B, à re-mesurer

- Le prompt concise et le contexte structuré large devraient convenir. Sonnet ne gagne rien avec un prompt plus riche ; le 9B y perd.
- À re-mesurer sur la cible, réflexion désactivée :
  - exactitude et erreurs graves sur dev complet ;
  - abstentions à tort avec C10 (le 9B s'abstient davantage quand le contexte grandit) ;
  - troncature des QCM ;
  - latence avec environ 8 600 tokens de prompt.
- Vérifier sur vLLM que `chat_template_kwargs={"enable_thinking": false}` est bien pris en compte : sinon la réponse part dans le bloc de réflexion.
- Paramètres d'échantillonnage Qwen (température 0,7, top_p 0,8, presence_penalty 1,5, recommandés par Qwen sans réflexion) : non mesurés. Tout a été évalué en greedy.

## 9. Questions ouvertes

- La clarification ne peut pas s'obtenir de façon générique tant que la frontière du benchmark n'est pas structurelle. Un signal « site / grade / niveau de risque » demanderait que l'ingestion structure ces conditions par ligne de tableau.
- La suppression des fiches-lignes redondantes (−10 % de tokens) n'a pas été mesurée en génération.
- Le 30B n'a jamais été mesuré.
- Les mesures multirfe portent sur des questions synthétiques écrites par Claude, qui avantagent Claude d'environ 10 points.

## 10. Fichiers

| Quoi | Où |
|---|---|
| Code | `src/rag_sfar/generation/*`, `cli.py` (options `--gen-preset` / `--gen`), `evaluation/harness.py` (métrique « sourcé » avec [S1, S2]) |
| Tests | `tests/test_generation_b3.py`. Suite complète : 150 verts, test anti-fuite muet. |
| Rapports | `reports/eval/b3/` |
| Lots du juge | `eval_internal/judge/runs/b3_*` |
| Prompts capturés | `eval_internal/work/replay/frontier/` (ignoré par git : contient le texte des questions abpe171) |
