# X2 — Recherche multi-requêtes pour les questions à deux sources

Agent X2, 2026-11-27. Code : `src/rag_sfar/retrieval/multi_query.py` (module nouveau, désactivé par défaut), `eval_internal/multi_query_eval.py` (évaluation), `tests/test_multi_query.py` (8 tests). Retrieval figé intact : `pipeline.py`, `crag.py`, `config.py` non modifiés ; avec le mode `off`, le module renvoie exactement les chunks figés (test unitaire, et contrôle sur les 212 questions de dev : 0 différence pour toute question où l’étape ne se déclenche pas, dans les cinq runs).

**Résumé.** Trois options ont été construites et mesurées sur dev contre `C10_context_notes` (`index/tas_v6`) :

| Option | Appel LLM | Déclenchement (abpe171 / multirfe / x2_dev*) | Effet sur x2_dev* (suffisance) | Effet sur les questions ordinaires |
|---|---|---|---|---|
| 1. Décomposition avant recherche | 1 court (≈ 400 tokens) par question | 0 % / 2,1 % / 56 % | **37,5 → 50,0 %** (+12,5 [0 ; +31,2], 2 gagnées / 0 perdue) | aucune régression (0 déclenchement sur abpe171) |
| 2. Correction sans LLM (cross-encoder par clause) | aucun | 22 % / 47 % / 62 % (τ = 0,05) | 0 | −1 question sur abpe171 (éviction par le budget) |
| 3. Correction avec LLM (titres + premières lignes) | 1 (≈ 1 900 tokens) par question | 1 % / 10,6 % / 6 % | 0 | aucune régression ; se déclenche surtout sur les questions hors corpus |

\* `x2_dev` : 16 questions à deux sources **écrites pour ce développement** (synthétiques, non validées médicalement, voir §4) ; ce n'est pas une preuve de généralisation. Tous les chiffres ci-dessous sur x2_dev portent la même réserve.

**Recommandation** : n'envoyer au passage tenu à l'écart (`genprobe2`) que l'**option 1 (décomposition)**, telle quelle (mode `decompose`, part garantie 2), contre le retrieval figé. Elle est inerte sur les questions ordinaires (0/102 abpe171, 2/94 multirfe) et c'est la seule qui ait apporté une preuve manquante sur x2_dev. Le gain attendu est modeste : sur les 6 questions en échec où elle se déclenche, 4 ne sont pas réparées, parce que chaque sous-question garde le contexte dominant de la question (§5). Les options 2 et 3 ne sont pas à envoyer.

## 1. Le problème et ce qu'en dit la littérature

Une question qui combine deux sujets éloignés (un traitement du patient et la conduite propre à un acte ; deux chapitres d'une longue RFE) est cherchée par une seule requête dont le sujet dominant capte le top-k. Sur `genprobe`, famille « deux sources », la suffisance était de 7/12. Sur x2_dev (§4), le retrieval figé atteint 6/16 (37,5 %) de suffisance pour 65,6 % de rappel des preuves : presque toujours la moitié des preuves, celle du sujet dominant.

Ce que j'ai retenu de la littérature (recherche courte) :
- **Décomposition / multi-requêtes.** *Question Decomposition for RAG* (arXiv 2507.00355, 2025) : décomposition par LLM + recherche par sous-question + reranking ; +4,4 pts de Hits@4 dû à la décomposition seule, +7,6 au reranking, mais un coût élevé (≈ 19 s/requête) et un lien faible entre les sous-questions générées et la structure réelle des preuves. RAG-Fusion (arXiv 2402.03367) : plusieurs reformulations, fusion des listes. *Transforming Questions and Documents* (arXiv 2508.09755) : décomposition zéro-shot en sous-questions simples. → Retenu : sous-questions **autonomes** (chacune nomme son sujet et son contexte), fusion avec **part garantie** par sous-question, recherche principale conservée.
- **Adaptativité.** Adaptive-RAG (Jeong et al., arXiv 2403.14403) : un classifieur de complexité choisit entre aucune, une ou plusieurs recherches. → Retenu : la même décision « SIMPLE / MULTIPLE » est prise par l'appel de décomposition lui-même, avec une consigne explicite que SIMPLE est le cas général ; sans décision, rien ne change.
- **Correction.** CRAG (Yan et al., arXiv 2401.15884) : un évaluateur léger note la qualité des documents retrouvés et déclenche une action corrective (affiner, rechercher ailleurs). Self-RAG (Asai et al., arXiv 2310.11511) : jetons de réflexion appris. i-MedRAG (Xiong et al., arXiv 2408.00727) : questions de suivi itératives en médecine (gains sur MedQA). EfficientRAG (arXiv 2408.04259) : petites têtes d'étiquetage pour éviter un appel LLM par itération. → Retenu : une version sans LLM (option 2, notre « évaluateur léger » est le cross-encoder existant) et une version avec un seul appel court sur un résumé du contexte (option 3), sans itération (coût).

## 2. Ce que fait chaque option

Commun aux trois : enveloppe `MultiQueryRetriever(base, MultiQueryConfig(mode=...), responder)` avec la même interface `retrieve(...)`. Fusion `merge_results` : un bloc = un passage classé + sa fenêtre de contexte ; tour à tour, chaque source (requête principale puis sous-requêtes) reçoit ses 2 premiers blocs, puis le reste de la requête principale, puis le reste des sous-requêtes ; doublons (id ou texte) écartés ; plafonds du contexte générateur (`wide` : 30 000 caractères, 40 extraits). Les comparaisons d'éditions (`all_versions`) ne sont jamais touchées. Toute réponse LLM hors format, ou une panne du modèle, rend la sortie figée.

1. **`decompose`** : un appel lit **seulement la question** et répond `SIMPLE` ou `MULTIPLE` + 2–3 sous-questions numérotées. Prompt `DECOMPOSE_SYSTEM` : neutre (aucun médicament, acte, RFE ou exemple tiré d'une question d'évaluation), « reprends les termes de la question, n'ajoute aucune information médicale, ne donne aucune réponse ».
2. **`ce_gap`** : la question (tronc, sans les options de QCM) est coupée en clauses à la ponctuation et aux mots grammaticaux (et, ou, chez, avec, sous, lors de, en cas de, après, avant, pour, qui, dont…) ; chaque clause est notée par le cross-encoder contre les 8 premiers passages ; une clause sous le seuil τ est cherchée seule (≤ 3).
3. **`llm_correct`** : un appel voit la question et, pour les 16 passages classés, `[n] titre (année) — section — 160 premiers caractères` (pas le contexte entier) ; il répond `COMPLET` ou `INCOMPLET` + 1–2 lignes `REQUETE: …`. Une requête identique à la question est ignorée (relancer la même recherche ne sert à rien : 3 cas).

## 3. Protocole de mesure

- Dev seulement : `abpe171` dev (102, références des experts), `multirfe_synth` dev (94, synthétique LLM, dont 18 hors corpus) et `x2_dev` (16, écrit pour ce développement). Ni test, ni `genprobe`, ni `genprobe2` (non ouvert).
- Métriques `harness.retrieval_metrics` sur **le contexte que lit le générateur** (`select_within_budget(40, 30 000)`), appariées contre le run figé (`harness.paired_bootstrap_diff`, b − a, 2 000 rééchantillonnages). Latence = appel `retrieve` seul (sans l'appel LLM, dont la latence dépend du modèle servi).
- Appels LLM : générateur de substitution **Claude Sonnet** (sous-agents, consignes `reports/agents/X2_annexes/STANDIN_INSTRUCTIONS.md`), exports à l'aveugle (ids opaques, lots ≤ 20), import strict (refus global si une réponse manque ou sort du format) ; les réponses sont retrouvées par empreinte du prompt, donc les prompts évalués sont ceux du produit. Décomposition : 212 réponses, 0 erreur de format. Correction : 209 réponses, 0 erreur de format. Pour `cor_r1/part_06`, un premier agent a vu son fichier signalé par le système de permissions et ce fichier a été écarté sans usage ; un deuxième n'a rien écrit ; le troisième, autorisé par l'utilisateur, a répondu `COMPLET` aux 20 cas (les trois avaient jugé indépendamment les 20 cas complets).
- Base figée reproduite : abpe171 dev suffisance 95,8 %, rappel des preuves 98,2 % (= journal) ; multirfe dev passage 96,1 %.
- Le contexte figé n'utilise en moyenne que ≈ 20 300 des 30 000 caractères : les ajouts occupent d'abord la place libre et n'évincent la fin du contexte figé que lorsqu'il est déjà presque plein.

## 4. Le jeu `x2_dev` (outil de développement)

16 questions à deux sources (8 deux RFE, 8 deux sections d'une même RFE éloignées de 31 à 410 chunks ; 21 RFE en vigueur, hors antibioprophylaxie), citations verbatim vérifiées dans `tas_v6`, écrites par un sous-agent de X2 qui n'a vu ni le code ni les prompts. **Synthétique, non validé médicalement, écrit pour ce travail** ; les prompts ont été écrits avant que je lise les questions, mais j'ai vu les questions avant de mesurer. Fichier : `eval_internal/work/x2_dev/x2_dev.jsonl` (+ `README.md`, `build_x2_dev.py`). Doutes de l'auteur : X2D-01 (le délai d'imagerie est dans un autre chunk que la citation), X2D-02 (lien inféré), X2D-05, X2D-06 (les deux parties donnent la même valeur), X2D-07 (la RFE coronarien de 2010 couvre aussi en partie les antiplaquettaires).

## 5. Résultats

Tableaux complets : `reports/agents/X2_annexes/compare_{dec_r1,dec_r1_s4,cor_r1,ce_gap_002,ce_gap_005}.md`.

### Option 1 — décomposition (`dec_r1`, part garantie 2)

| Jeu | n | Déclenchements | Suffisance | Rappel des preuves | Passage | Document |
|---|---:|---|---|---|---|---|
| abpe171 dev | 102 | 0 (0 %) | 95,8 → 95,8 (0 [0 ; 0]) | 98,2 → 98,2 | 100 → 100 | 100 → 100 |
| multirfe dev | 94 | 2 (2,1 %) | — | — | 96,1 → 96,1 (0) | 98,7 → 98,7 |
| x2_dev* | 16 | 9 (56 %) | **37,5 → 50,0 (+12,5 [0 ; +31,2])**, 2 / 0 | 65,6 → 71,9 (+6,2 [0 ; +15,6]) | 93,8 → 93,8 | 100 → 100 |

- **Quand il se déclenche** : 9 des 16 questions x2_dev (dont 6 des 10 en échec ; X2D-02, 10, 13 et 16 jugées SIMPLE) ; sur les questions ordinaires, 2/196. Les deux déclenchements multirfe sont une question d'imagerie à deux lésions (passage conservé) et une question **hors corpus** (deux sous-questions, 4 passages hors sujet ajoutés ; l'abstention n'a pas été mesurée en génération).
- **Ce qu'il apporte** : X2D-04 (préoxygénation + décubitus ventral, deux RFE) et X2D-09 (deux sections éloignées d'une RFE de nutrition) passent à suffisance 1. Rien n'est perdu.
- **Pourquoi 4 échecs déclenchés restent** (diagnostic : rang de chaque preuve dans la sortie propre de chaque sous-question, `eval_internal/work/x2/diag_dec_r1.json`) :
  - X2D-01, X2D-06, X2D-07 : la preuve manquante n'est **dans aucune** des sorties des sous-questions. Chaque sous-question reprend tout le contexte de la question (comme le prompt le demande) et la recherche retombe sur le document dominant : la sous-question « antagoniser l'AVK après traumatisme crânien » retrouve la RFE traumatisme crânien, pas celle de l'anticoagulation ; « dernière dose de l'iSGLT2 avant une colectomie à risque hémorragique » retrouve la RFE anticoagulants.
  - X2D-05 : la preuve est bien retrouvée par la sous-question, mais au rang 27 de sa sortie, au-delà des blocs garantis ; une part de 4 blocs (`dec_r1_s4`) ne change rien (mêmes chiffres exactement).
- **Pertinence des ajouts lue à la main** (un lecteur, X2, non aveugle ; passages classés ajoutés hors fenêtres) : 66 passages ajoutés sur les 11 déclenchements ; ≈ 35 traitent du sujet de leur sous-question (dont les 2 preuves gagnées), ≈ 31 sont du bruit (références bibliographiques, sommaire, résumé en anglais, autre population ou autre acte de la même RFE, autre RFE sans rapport). Sur la question hors corpus : 0/4 pertinent.
- **Coût** : un appel par question (prompt ≈ 1 460 caractères, ≈ 400 tokens ; réponse `SIMPLE` de 6 caractères dans 95 % des cas, ≤ 410 caractères sinon). Quand il se déclenche : 2–3 recherches de plus, latence retrieval médiane 192 → 583 ms, contexte 22 700 → 26 700 caractères en moyenne (x2_dev), toujours ≤ 30 000. Le prix réel est l'appel LLM **avant** la recherche, à chaque question, y compris les 98 % de questions simples : sur le modèle servi (≈ 30B) c'est une latence ajoutée de l'ordre d'une génération courte (non mesurée ici ; le générateur de substitution n'est pas le modèle servi).

### Option 2 — correction sans LLM (`ce_gap`)

- **Signal** (balayage `clause_scan` : support minimal par clause contre les 8 premiers passages, prédiction d'un rappel des preuves < 1) : AUC 0,73 sur les trois jeux réunis (17 échecs / 176 questions à ≥ 2 clauses), **0,43 sur x2_dev**, c'est-à-dire aucun signal là où il servirait. Les clauses grammaticales sont des fragments sans sujet (« pour quelle durée quotidienne », « et à quelle posologie l'administrer ») : le cross-encoder les note bas qu'elles soient couvertes ou non, et cherchées seules elles ne retrouvent rien d'utile.
- **Effet** (τ = 0,02 et 0,05) : déclenchement 16–22 % abpe171, 33–47 % multirfe, 50–62 % x2_dev ; gain 0 partout ; **abpe171 perd une question** (Q41, suffisance −1,0 [−3,1 ; 0] : 9 extraits de la fin du contexte figé évincés par le budget). Latence médiane 192 → 330–690 ms, coût cross-encoder ≈ 170 ms par question (clauses × 8 paires).
- **Conclusion** : pas de signal exploitable sans compréhension de la question. Abandonné.

### Option 3 — correction avec LLM (`cor_r1`)

| Jeu | n | INCOMPLET (déclenchés) | Suffisance / passage |
|---|---:|---|---|
| abpe171 dev | 102 | 1 (1) | 95,8 → 95,8 ; passage 100 → 100 |
| multirfe dev | 94 | 13 (10) | passage 96,1 → 96,1 |
| x2_dev* | 16 | 1 (1) | 37,5 → 37,5 ; rappel 65,6 → 65,6 |

- Le correcteur juge presque tout `COMPLET` : il ne voit que les titres et premières lignes, et sur une question à deux sources le document du sujet dominant « couvre » visiblement la question. Sur x2_dev, il ne signale que X2D-06 (la sous-requête iSGLT2 retrouve encore la RFE anticoagulants : 0 preuve ajoutée).
- **13 des 13 INCOMPLET de multirfe sont des questions hors corpus** (13/18 hors corpus signalées, 0 question couverte signalée). Comme détecteur de non-couverture, il est précis ; comme moyen de retrouver une preuve, il n'apporte rien : les ≈ 38 passages ajoutés sur ces questions sont tous hors sujet (par construction), et ils rendent le contexte plus long sur des questions où la bonne réponse est l'abstention.
- **Coût** : prompt ≈ 6 850 caractères (≈ 1 900 tokens) à chaque question, après la recherche ; recherche supplémentaire seulement dans 6 % des cas (latence 190 → 380 ms quand elle a lieu).
- **Conclusion** : aucune preuve gagnée, coût en tokens 4 à 5 fois celui de la décomposition. Abandonné pour la recherche. L'usage comme signal d'abstention n'est pas à reprendre ici (la génération refuse déjà 12/12 questions hors corpus sur multirfe test) ; noté pour mémoire.

## 6. Limites

- Peu de vraies questions à deux sources en dev : l'effet utile n'est mesuré que sur x2_dev, 16 questions écrites pour ce travail ; l'IC de +12,5 pts touche 0. Le résultat qui compte est le passage unique sur `genprobe2`.
- Retrieval seul ; l'effet sur la réponse (et sur l'abstention quand une décomposition se déclenche sur une question hors corpus) n'est pas mesuré.
- Décisions et sous-questions produites par Sonnet, pas par le modèle servi : un modèle de 30B déclenchera peut-être plus souvent (risque d'ajouts bruités sur les questions simples) ; le format strict et le repli sur la sortie figée limitent le risque de casse, pas celui de bruit.
- La pertinence des ajouts est lue par un seul lecteur, non médecin et non aveugle.
- Une piste non testée, faute de temps et pour ne pas régler sur x2_dev : des sous-questions qui **ne répètent pas** le contexte dominant (sujet de la partie seul + population), puisque c'est la cause principale des échecs restants. Ce serait un changement de prompt à mesurer sur un autre jeu que x2_dev.

## 7. Activer chaque option

Par défaut, rien n'est actif : `wrap_retriever(retriever)` renvoie l'objet figé lui-même si `RAG_SFAR_MULTI_QUERY` n'est pas défini.

```python
from rag_sfar.retrieval.multi_query import wrap_retriever, MultiQueryRetriever, MultiQueryConfig, llm_responder
retriever = wrap_retriever(base_retriever, llm=served_llm)            # mode lu dans RAG_SFAR_MULTI_QUERY
retriever = MultiQueryRetriever(base_retriever, MultiQueryConfig(mode="decompose"), llm_responder(served_llm))
engine = build_engine(retriever, served_llm)                         # même interface retrieve(...)
```

- `RAG_SFAR_MULTI_QUERY=decompose` (option 1, recommandée pour le passage tenu à l'écart) ; `=llm_correct` (option 3) ; `=ce_gap` (option 2, sans LLM). `llm_responder` appelle `llm.complete(system, user, temperature=0, max_tokens=200)` du client existant.
- L'API et les serveurs MCP ne sont pas branchés sur ce module (profil `PRODUCTION` inchangé) : l'activer en production demande d'envelopper le retriever dans `build_engine`, décision à prendre après `genprobe2`.
- Évaluation (même chemin de code) : `export` → réponses des agents de substitution → `import` → `run` → `compare` (en-tête de `eval_internal/multi_query_eval.py`). Pour `genprobe2` : ajouter la suite à `SUITES`/`items()` puis exporter les prompts de décomposition ; un seul passage, `decompose` contre `off`.
