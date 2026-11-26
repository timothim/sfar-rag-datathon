# Veille état de l'art — RAG médical FR sur les recommandations SFAR

Date de la veille : 26 novembre 2026. Méthode : recherche web, sources primaires en priorité (arXiv/ACL/ICLR, docs officielles, cartes de modèles). Aucun appel API payant.

Conventions :
- **[vérifié]** : chiffre lu dans la source primaire (abstract, tableau ou page officielle) pendant cette veille.
- **[secondaire]** : chiffre lu dans un résumé tiers ou une source non primaire.
- **[non vérifié]** : chiffre de mémoire ou estimation de l'auteur, à confirmer avant de le citer.
- Les gains sur benchmarks généraux (MMTEB, BEIR, MIRACL) **ne se transfèrent pas mécaniquement** au français médical d'anesthésie. Chaque hypothèse doit être mesurée sur le jeu de dev interne, jamais sur le lockbox.

Point de départ supposé (d'après la demande et le README) : BM25 + n-grammes de caractères + dense `multilingual-e5-small`, fusion RRF/DBSF, cross-encoder `mmarco-mMiniLMv2`, CRAG maison, ordre « U-shape », Row-Group Cards pour les tableaux, graphe de supersession des éditions, élagage de type Provence.

---

## 0. Prérequis à toutes les hypothèses : une mesure fiable

Sans cela, aucune des hypothèses ci-dessous n'est arbitrable. Coût faible, gain indirect mais décisif.

1. **Gold set au niveau de la recommandation** : pour chaque question, l'identifiant de la ou des recommandations attendues (document, édition, numéro R, cotation GRADE), pas seulement le document. On peut alors calculer recall@k et nDCG@10 au niveau de la recommandation, séparément de la génération.
2. **Métriques séparées** : retrieval (recall@k, MRR, couverture des recommandations attendues), génération (exactitude clinique, fidélité au contexte, citation correcte, abstention correcte), système (latence p50 et p95, tokens).
3. **Juge LLM calibré** : 50 à 100 réponses annotées par un clinicien, accord rapporté en κ de Cohen. Permuter l'ordre des réponses en comparaison par paires (biais de position). Ne pas juger avec un modèle de la même famille que le générateur (biais d'auto-préférence). Rubrique explicite plutôt que note globale.
4. **Intervalles de confiance** (bootstrap) : avec environ 200 questions, une différence de 2 à 3 points est souvent du bruit.

---

## Top 10 des hypothèses classées

Échelles : gain attendu (élevé, moyen, faible), coût d'implémentation (heures de dev), coût d'exécution (latence et GPU à l'usage). Le classement pondère le gain attendu par le coût et le risque.

| # | Hypothèse | Gain attendu | Coût d'implémentation | Coût d'exécution | Risque | Mesure |
|---|---|---|---|---|---|---|
| 1 | **Remplacer l'embedder dense** `multilingual-e5-small` (118M) par `Qwen3-Embedding-0.6B` (Apache 2.0), avec `BGE-M3` (MIT) et `EmbeddingGemma-300m` comme alternatives | **Élevé**. MMTEB Retrieval : 49,3 (mE5-small) contre 64,65 (Qwen3-Emb-0.6B), 62,49 (EmbeddingGemma), 54,60 (BGE-M3) | Faible (environ 0,5 j) : réindexation, préfixe d'instruction côté requête, nouvelle dimension pgvector | Faible : environ 5 fois les FLOPs de mE5-small par token, négligeable sur GPU pour une requête ; réindexation unique en quelques minutes sur GPU [non vérifié] | Transfert au français médical non garanti. Le canal dense peut écraser BM25 dans la fusion, donc il faut réajuster les poids | Recall@20 et nDCG@10 au niveau de la recommandation, par canal et après fusion ; ablation avec et sans n-grammes |
| 2 | **Remplacer le reranker** `mmarco-mMiniLMv2` par `bge-reranker-v2-m3` (déjà prévu dans le script LibreDataHub) puis `Qwen3-Reranker-0.6B` ou `4B` (Apache 2.0) ; régler la profondeur (top-50 à 100 puis top-k) | **Élevé**. MMTEB-R : 58,36 (bge-v2-m3), 66,36 (Qwen3-R-0.6B), 72,74 (Qwen3-R-4B), chiffres de Qwen | Faible (environ 0,5 j) : vLLM `--runner pooling` avec `/rerank` | Moyen : 0,6B sur 50 paires d'environ 512 tokens, de l'ordre de 0,1 à 0,5 s sur GPU [non vérifié] ; plusieurs secondes sur Mac | Les chiffres viennent de l'éditeur, et l'ancien MiniLM n'est pas dans leurs tableaux | nDCG@10 après rerank, latence p95 ; courbe gain en fonction de la profondeur de rerank |
| 3 | **Unité de retrieval = recommandation GRADE structurée** : extraire chaque recommandation (R-id, texte, force GRADE 1+/2+/2−/1−, accord fort ou relatif, population, édition, statut en vigueur) dans une table PostgreSQL, indexer ces unités, puis « small-to-big » vers l'argumentaire ou la section parente | **Élevé** sur la précision des citations et sur les questions « que recommande la SFAR pour X » ; moyen sur le reste | Moyen (2 à 4 j) : regex sur les motifs « R1.1 », « GRADE », « Accord FORT », LLM en secours, validation sur un échantillon | Faible : requêtes SQL et filtres exacts | Formats hétérogènes entre 2000 et 2026 (avant GRADE : grades A/B/C, ou « accord professionnel ») et bruit OCR | Taux d'extraction contrôlé à la main sur 30 documents ; recall@k au niveau R ; exactitude de la force GRADE citée |
| 4 | **En-têtes contextuels de chunks**, d'abord déterministes (titre de la RFE, année, édition, chemin de sections, en-tête de tableau, spécialité), puis contextual retrieval par LLM si le gain persiste | **Moyen à élevé**. Anthropic : −35 % d'échecs de retrieval en dense, −49 % avec BM25 contextuel, −67 % avec rerank | Faible pour la version déterministe (0,5 j) ; moyen pour la version LLM | Nul à l'usage. Indexation LLM : de quelques heures sur GPU à plus d'une nuit sur Mac [non vérifié] | Recoupement avec ce qui existe déjà (Row-Group Cards, boost de métadonnées). La version LLM peut halluciner un contexte | Échecs@20 (1 − recall@20) avec et sans en-tête, par canal |
| 5 | **Générateur plus fort en production** sur GPU LibreDataHub : `Qwen3.5-27B` ou `Qwen3.5-35B-A3B` (MoE), `Gemma 4 31B` ou `26B-A4B` (Apache 2.0), `Mistral Small 3.2 24B` (Apache 2.0, éditeur français). Garder le 7B en dev Mac | **Élevé** sur la fidélité, l'abstention et l'usage des tableaux | Faible : API compatible OpenAI | Moyen : 24 à 31B denses tiennent sur un GPU de 48 à 80 Go en FP8 ou en 4 bits [non vérifié] ; les MoE A3B/A4B sont rapides | Pas de résultat publié en QA médicale française pour ces modèles. Le mode « thinking » augmente la latence | Bout en bout sur le dev : exactitude, fidélité, abstention, latence ; même retrieval figé |
| 6 | **Abstention calibrée « sufficient context »** : un classifieur (LLM) juge si le contexte suffit, combiné à la confiance du modèle ; remplace ou simplifie le CRAG maison | **Moyen** sur la sécurité : +2 à 10 points de réponses correctes parmi les réponses données (Google, ICLR 2025) | Moyen (1 à 2 j) | Un appel LLM court de plus par requête | Le seuil sur-abstient si mal calibré | Courbe couverture / exactitude sélective ; taux de fausses abstentions sur les questions répondables |
| 7 | **Citations au niveau de la phrase ou de la recommandation et vérification post-génération** : chaque phrase porte son [R-id] ; vérification par NLI ou LLM ; préférer la citation verbatim de la recommandation (extraction) à la paraphrase | **Moyen** sur la fiabilité perçue et la traçabilité | Moyen (1 à 2 j) | Un appel de vérification (petit modèle) | Juge NLI imparfait (ALCE : 85 % d'exactitude en rappel, 78 % en précision face à l'humain) | Citation recall et precision style ALCE sur le dev ; audit humain de 50 réponses |
| 8 | **Régler k et la longueur du contexte ; élaguer plutôt que réordonner** : tester k ∈ {3, 5, 8, 12} après rerank, XProvence (multilingue, base bge-reranker-v2-m3) pour le pruning ; garder ou retirer le « U-shape » selon la mesure | **Faible à moyen**. L'effet de position est marginal en RAG réaliste (EMNLP 2025) mais réel quand k est grand | Faible | Négatif (moins de tokens) | Faible | Exactitude bout en bout en fonction de k et de l'ordre (original, U-shape, inverse, aléatoire) |
| 9 | **Conflits d'éditions explicites** : filtre « en vigueur » dur par défaut, mode comparatif qui injecte les deux éditions étiquetées (année, statut) avec consigne de raisonner sur le conflit ; reranking qui combine pertinence et récence | **Moyen** sur les questions sensibles aux versions, faible ailleurs | Faible à moyen (le graphe de supersession existe déjà) | Nul | Périmètres cliniques qui se recouvrent sans se remplacer (urgence contre programmé) | Sous-ensemble de questions « version-sensibles » ; taux de citation d'une édition périmée |
| 10 | **Décomposition de requête ciblée** (multi-query) pour les seules questions multi-facettes ou multi-RFE, avec un routeur ; **pas de HyDE** sur le canal dense | **Faible à moyen** | Moyen | Un appel LLM de plus pour les questions routées | Les expansions dégradent les retrievers forts (corrélation négative entre force du retriever et gain) | Recall@k sur le sous-ensemble multi-facettes contre le reste |

Hors top 10, à considérer si le temps le permet : sortie sparse et multi-vecteurs de BGE-M3 (+1 à 3 points MIRACL), fine-tuning RAFT/LoRA du générateur, late chunking (exige un embedder à long contexte).

---

## 1. Chunking et représentation

### Constats
- **Contextual retrieval (Anthropic, 19 sept. 2024)** — https://www.anthropic.com/engineering/contextual-retrieval — échec top-20 (1 − recall@20) : 5,7 % en base, 3,7 % avec contextual embeddings (−35 %), 2,9 % avec BM25 contextuel en plus (−49 %), 1,9 % avec rerank Cohere en plus (−67 %). Contexte de 50 à 100 tokens par chunk ; environ 1,02 $ par million de tokens de document avec cache de prompt. Recommande de passer les 20 meilleurs chunks (top-150 → rerank → top-20). [vérifié] Limite : les gains sont cumulatifs ; si hybride et rerank sont déjà en place, l'apport marginal est plus proche de −35 % [secondaire].
- **Merola & Singh, « Reconstructing Context » (avril 2025, atelier ECIR)** — https://arxiv.org/abs/2504.19754 — contextual retrieval avec fusion et rerank : meilleure précision mais coût élevé ; late chunking plus efficace mais très dépendant de l'embedder et du jeu de données. [vérifié, abstract]
- **Late chunking (Jina, sept. 2024)** — https://arxiv.org/abs/2409.04701 — meilleur que le découpage naïf sur les jeux BEIR testés. Exemple SciFact nDCG@10 : 66,10 contre 64,20 [secondaire, README GitHub]. Gain moyen relatif de 2,7 à 3,6 % [non vérifié]. Exige un embedder à long contexte : **inapplicable avec mE5-small (512 tokens)**, possible avec Qwen3-Embedding (32k) ou BGE-M3 (8k).
- **Chunking sémantique : « Is Semantic Chunking Worth the Computational Cost? » (NAACL Findings 2025)** — https://aclanthology.org/2025.findings-naacl.114 — gains incohérents et trop faibles pour justifier le coût face au découpage de taille fixe. [vérifié, abstract]
- **Caspari et al., « When Is Complex Chunking Worth It? » (17 août 2026, v2 4 nov. 2026)** — https://arxiv.org/abs/2608.16586 — 8 stratégies, 3 embedders : les méthodes coûteuses apportent rarement des gains cohérents ; le meilleur choix dépend de l'embedder, du corpus et de la métrique. [vérifié, abstract ; pas de chiffres dans l'abstract]
- **Propositions, « Dense X Retrieval » (EMNLP 2024)** — https://arxiv.org/abs/2312.06648 — Recall@20 +10,1 points pour les retrievers non supervisés, mais seulement +2,2 à +2,7 pour les retrievers supervisés [vérifié ; le chiffre supervisé varie selon la version]. Avec un embedder moderne supervisé, le gain attendu est faible et le coût LLM d'indexation élevé.
- **Structure du document, GraLC-RAG (23 mars 2026)** — https://arxiv.org/abs/2603.22633 — sur 2 359 articles PMC : les méthodes par similarité ont le meilleur MRR (0,517) mais ne récupèrent qu'une section ; les méthodes structurelles couvrent jusqu'à 15,6 fois plus de sections ; ΔF1 de génération de 0,009 seulement. [vérifié, abstract] Pertinent ici : une recommandation et son encadré ou sa contre-indication sont souvent dans des sections différentes (cas de l'encadré allergie déjà traité).
- **Tableaux** : les résultats se contredisent selon le modèle et la tâche.
  - OCR et RAG (déc. 2024) — https://arxiv.org/abs/2412.02592 — les tableaux HTML se retrouvent moins bien que Markdown ou LaTeX au retrieval ; en génération, Markdown perd sur les cellules fusionnées. [secondaire]
  - TQA-Bench — https://arxiv.org/abs/2411.19504 — Markdown est meilleur en QA multi-tables. [secondaire]
  - OfficeQA Pro (2026) — https://arxiv.org/abs/2603.08655 — HTML gagne légèrement (7 agents sur 11). [secondaire]

### Implications pour SFAR
- Les Row-Group Cards linéarisées (« en-tête : valeur ») sont le bon choix pour l'index. Pour la génération, on peut garder un rendu du tableau parent (HTML ou Markdown) en « small-to-big ». La version à préférer se tranche sur le dev, aucune règle générale ne s'impose.
- **H3 et H4** sont les leviers de représentation les plus rentables : l'unité « recommandation » est naturelle dans ce corpus, et les en-têtes déterministes ne coûtent rien.
- À ne pas faire : chunking sémantique, chunking par propositions généré par LLM sur tout le corpus.

---

## 2. Recherche (retrieval)

### Embedders multilingues ouverts (MMTEB, Mean(Task) / Retrieval)
Source principale : tableaux des rapports Qwen3-Embedding (https://arxiv.org/abs/2506.05176, juin 2025) et EmbeddingGemma (https://arxiv.org/abs/2509.20354, sept. 2025). [vérifié]

| Modèle | Params | MMTEB moyen | MMTEB Retrieval | Licence |
|---|---|---|---|---|
| multilingual-e5-small (actuel) | 118M | 55,8 | 49,3 | MIT |
| granite-embedding-278m-multilingual | 278M | 53,7 | 52,2 | Apache 2.0 |
| gte-multilingual-base | 305M | 58,24 | 56,50 | Apache 2.0 |
| EmbeddingGemma | 308M | 61,15 | 62,49 | Gemma Terms [non vérifié] |
| BGE-M3 (dense) | 568M | 59,56 | 54,60 | MIT |
| multilingual-e5-large-instruct | 560M | 63,22 | 57,12 | MIT |
| Qwen3-Embedding-0.6B | 595M | 64,33 | 64,64 | Apache 2.0 |
| Qwen3-Embedding-4B | 4B | 69,45 | 69,60 | Apache 2.0 |
| Qwen3-Embedding-8B | 8B | 70,58 | 70,88 | Apache 2.0 |

Autres repères :
- EmbeddingGemma est 8e au classement global MMTEB(Multilingual, v2) et premier modèle de moins de 500M. [vérifié, abstract]
- NVIDIA annonce `Llama-Embed-Nemotron-8B` premier modèle ouvert sur MMTEB. Il s'agit d'une annonce de l'éditeur, non datée dans le résultat ; la licence est à vérifier. https://forums.developer.nvidia.com/t/llama-embed-nemotron-8b-model-tops-the-multilingual-text-retrieval-leaderboard/348440 [secondaire]
- `jina-embeddings-v4` (3,8B, juin 2025, https://arxiv.org/abs/2506.18902) est multimodal, avec sortie mono- et multi-vecteurs. Licence non commerciale probable [non vérifié]. Peu adapté à la contrainte de souveraineté et de licence.
- Mise en garde : un audit AACL 2026 (https://aclanthology.org/2026.aacl-short.28.pdf) montre que des modèles bien classés en moyenne MMTEB peuvent être faibles sur des langues précises. **Regarder la vue française et Retrieval**, pas la moyenne.
- Domaine médical : MMed-Bench-IR (23 juin 2026, https://arxiv.org/abs/2606.24200) montre des encodeurs biomédicaux à 0,818 nDCG@10 en anglais et 0,056 en japonais. **Ne pas prendre d'embedder biomédical anglais.** Une étude JMIR 2026 en allemand et anglais place mE5-large (mAP@100 0,14) devant BGE-M3 (0,11) sur du clinique [secondaire]. Le classement général n'est donc pas garanti en domaine médical : **mesurer**.

### Late interaction et sparse appris
- **BGE-M3 (fév. 2024)** — https://arxiv.org/abs/2402.03216 — MIRACL nDCG@10 moyen : BM25 31,9 ; mE5-large 66,6 ; M3 dense 69,2 ; sparse 53,9 ; multi-vecteurs 70,5 ; dense+sparse 70,4 ; tout combiné 71,5. **Français** : M3 dense 58,3, M3 combiné 61,2 (+2,9), mE5-large 54,5. [vérifié]
- Coût du multi-vecteurs : pgvector ne fait pas de MaxSim natif. L'usage réaliste est de **reranker le top-100 avec les vecteurs multi-tokens de M3**, sans les stocker pour tout le corpus.
- **Sparse** : pgvector ≥ 0.7.0 (30 avril 2024) offre `sparsevec` (jusqu'à 1 000 dimensions non nulles indexées) et `halfvec` (index HNSW deux fois plus léger) — https://www.postgresql.org/about/news/pgvector-070-released-2852 [vérifié]. Comme BM25 et les n-grammes de caractères existent déjà, l'apport du sparse de M3 est probablement marginal [non vérifié].
- **Jina-ColBERT-v2** (août 2024, https://arxiv.org/abs/2408.16672) : ColBERT multilingue, stockage −50 %. Licence non commerciale probable [non vérifié]. Gain attendu inférieur à celui d'un bon cross-encoder.

### Fusion hybride
- **MedRAG / MIRAGE (ACL Findings 2024)** — https://arxiv.org/abs/2402.13178 — BM25 reste un retriever fort en médical ; RRF aide souvent mais pas toujours ; RAG +18 % d'exactitude au maximum par rapport au CoT seul. [vérifié, abstract et résumé]
- RAG sur les guidelines NICE (oct.–déc. 2025) — https://arxiv.org/abs/2510.02967 — embedding hybride sur 10 195 chunks et 300 guidelines : MRR 0,814, recall@1 81 %, recall@10 99,1 %. [vérifié, abstract] C'est un ordre de grandeur réaliste pour un corpus de guidelines bien découpé.
- Après H1, **re-régler les poids de fusion** et tester le retrait du canal n-grammes (utile contre l'OCR, mais peut-être redondant).

### Réécriture de requête, HyDE, multi-query
- **Expansions génératives (2023)** — https://arxiv.org/abs/2309.08541 — sur 24 retrievers, forte corrélation négative entre la force du retriever et le gain de l'expansion : elle aide les faibles et nuit aux forts. [vérifié, abstract]
- **« Not All Queries Need Rewriting » (mars 2026)** — https://arxiv.org/abs/2603.13301 — la réécriture fait −9,0 % nDCG@10 sur FiQA et améliore TREC-COVID : effet dépendant du domaine. [secondaire]
- **HyDE et rétroaction (Jedidi & Lin, nov. 2025, SIGIR 2026)** — https://arxiv.org/abs/2511.19349 — HyDE est surtout utile côté BM25, avec extraction de termes de type Rocchio. [vérifié, abstract]
- Conclusion : conserver le lexique d'acronymes et le routeur (bon marché, ciblé) ; décomposition seulement pour les questions multi-facettes (H10) ; pas de HyDE systématique.

### Filtrage temporel et métadonnées
- Voir thème 5 (conflits d'éditions). Le piège des 57 documents sans `subdomain` relevé dans le README confirme qu'il vaut mieux un **boost doux** qu'un filtre strict sur des métadonnées imputées. Le filtre strict reste approprié sur le statut « en vigueur » issu du graphe de supersession.

---

## 3. Reranking

| Reranker | Params | MTEB-R | MMTEB-R | MLDR | Licence |
|---|---|---|---|---|---|
| bge-reranker-v2-m3 | 568M | 57,03 | 58,36 | 59,51 | Apache 2.0 |
| gte-multilingual-reranker-base | 306M | 59,51 | 59,44 | 66,33 | Apache 2.0 |
| jina-reranker-v2-base-multilingual | 278M | 58,22 | 63,73 | 39,66 | CC-BY-NC [non vérifié] |
| Qwen3-Reranker-0.6B | 0,6B | 65,80 | 66,36 | 67,28 | Apache 2.0 |
| Qwen3-Reranker-4B | 4B | 69,76 | 72,74 | 69,97 | Apache 2.0 |
| Qwen3-Reranker-8B | 8B | 69,02 | 72,94 | 70,19 | Apache 2.0 |

Source : rapport Qwen3-Embedding, tableau des rerankers. Tous les modèles reclassent le top-100 de Qwen3-Embedding-0.6B : **chiffres de l'éditeur** (https://arxiv.org/abs/2506.05176). [vérifié] `mmarco-mMiniLMv2` (≈118M, 2022) n'y figure pas. L'écart avec lui n'est pas chiffré, mais il est probablement important [non vérifié].

Autres sources :
- **jina-reranker-v3 (sept.–oct. 2025)** — https://arxiv.org/abs/2509.25085 — reranker listwise de 0,6B (base Qwen3-0.6B) : BEIR 61,94 contre 61,16 pour Qwen3-Reranker-4B ; MIRACL 66,50 à 66,83 selon la version. [secondaire ; chiffres de l'éditeur] Licence probablement non commerciale [non vérifié] : **à exclure si la contrainte de licence est stricte**.
- **XProvence (janv. 2026)** — https://arxiv.org/abs/2601.18886 — reranker et élagueur de phrases multilingue (base bge-reranker-v2-m3), « coût d'élagage quasi nul » parce qu'il fusionne avec l'étape de rerank. Provence original : ICLR 2025, anglais seulement, https://arxiv.org/abs/2501.16214. [vérifié, abstract] Le README mentionne un « élagage Provence » : vérifier que la version multilingue est bien utilisée.
- **Rerank listwise par LLM** :
  - FIRST (juin 2024, https://arxiv.org/abs/2406.15657) annonce −50 % de latence par rapport à RankZephyr ; la reproduction de Waterloo (2025, https://arxiv.org/abs/2411.05508) mesure −21 à −42 %. [vérifié]
  - RankZephyr (7B) est environ 23 fois plus lent que SCaLR et dépasse 5 min pour 1 000 candidats sans vLLM (https://arxiv.org/abs/2411.04602). [secondaire]
  - Sur un corpus de 264 documents avec un cross-encoder de 0,6 à 4B, le listwise LLM n'est pas rentable.
- **Service** : vLLM sert Qwen3-Reranker via `--runner pooling` avec `hf_overrides` (`Qwen3ForSequenceClassification`, jetons yes/no) et expose `/score` et `/rerank` (compatible Cohere) — https://docs.vllm.ai/en/latest/examples/pooling/score/ [vérifié]. Ollama : pas de support de rerank documenté trouvé [non vérifié]. **Sur LibreDataHub, servir le reranker avec vLLM, pas Ollama.**

---

## 4. Structure : extraction, graphes, versions

- **Extraction structurée des recommandations (H3)** :
  - Benchmark de guidelines sur dix ans (26 mars 2026) — https://arxiv.org/abs/2603.25196 — 32 155 recommandations extraites (avec force et niveau de preuve) de 3 418 guidelines. Les LLM détectent 71,1 à 89,6 % des recommandations, mais **ne citent le bon titre de guideline que dans 3,6 à 29,7 % des cas**, et l'adhésion n'est que de 21,8 à 63,2 %. [vérifié, abstract] Cela justifie que l'attribution (R-id, édition) vienne du système et non du modèle.
  - SafeLLM (11 juin 2026) — https://arxiv.org/abs/2606.12897 — l'extraction (sélection de lignes sources par numéro) résiste mieux aux hallucinations que la réécriture : rappel de termes jusqu'à 95 %. [vérifié, abstract] Argument pour **citer verbatim** la recommandation et sa cotation GRADE.
  - Extraction de la force des recommandations AHA par LLM (sept. 2025) — https://arxiv.org/abs/2509.10843 — [secondaire, pas de chiffre relevé].
- **GraphRAG** :
  - Han et al., « RAG vs. GraphRAG » (fév. 2025, v4 nov. 2026) — https://arxiv.org/abs/2502.11371 — forces distinctes selon la tâche ; les hybrides aident. [vérifié, abstract]
  - GraphRAG-Bench (ICLR 2026) — https://arxiv.org/abs/2506.02404 — le graphe gagne sur le raisonnement complexe et la synthèse ; la recherche vectorielle gagne ou fait jeu égal en factuel simple (F1 64,8 contre 63,0) [secondaire]. Indexation GraphRAG complète d'environ 1 797 s contre environ 204 s pour KGP [secondaire].
  - Ici, les questions sont surtout factuelles et ponctuelles (« quelle antibioprophylaxie pour X »). **Le graphe utile existe déjà : la supersession des éditions et le lien vers l'encadré allergie.** Un GraphRAG d'entités extraites par LLM n'est pas prioritaire.
- **RAPTOR (ICLR 2024)** — https://arxiv.org/abs/2401.18059 — +20 points d'exactitude absolue sur QuALITY avec GPT-4. [vérifié, abstract] Conçu pour des questions de synthèse sur des textes longs (romans), alors que les questions SFAR sont localisées. Faible priorité.
- **Versions** : voir thème 5.

---

## 5. Génération et contexte

### Lost-in-the-middle : l'effet est-il encore présent en 2025–2026 ?
- Original : Liu et al. (TACL 2024, https://arxiv.org/abs/2307.03172), courbe en U. [non revérifié dans cette veille]
- **Veseli et al. (COLM 2025)** — https://arxiv.org/abs/2508.07479 — l'effet est maximal quand l'entrée occupe jusqu'à 50 % de la fenêtre ; au-delà, le biais de primauté s'affaiblit et il reste un biais de distance (récence). [vérifié, résumé]
- **Cao et al., « Do RAG Systems Really Suffer From Positional Bias? » (mai 2025, EMNLP 2025)** — https://arxiv.org/abs/2505.15561 — plus de 60 % des requêtes ont au moins un passage très distrayant dans le top-10 ; l'effet de position est marginal en RAG réaliste ; **les réordonnancements selon les préférences de position ne font pas mieux qu'un mélange aléatoire**. [vérifié, abstract]
- **Reproduction SIGIR 2026** — https://arxiv.org/abs/2605.27105 — Llama-3.1-8B et 70B, Mistral-NeMo-12B, Gemma-3-4B et 27B : **pas de courbe en U reproduite** sur AmbigQA, NQ et HotpotQA (presque plate). En revanche, sensibilité réelle à l'ordre et à la taille de contexte sur HotpotQA (l'ordre inverse gagne quand le contexte grandit). Le rerank réduit la sensibilité à l'ordre. [vérifié, page HF]
- **Jin et al. (ICLR 2025)** — https://arxiv.org/abs/2410.05983 — la performance culmine puis baisse quand le nombre de passages augmente, à cause des « hard negatives ». Le réordonnancement (meilleurs passages au début et à la fin) n'aide que quand le nombre de passages est grand. [vérifié, abstract]
- **Conclusion** : avec k ≤ 8 après un bon rerank, l'ordre U-shape apportera probablement peu ; **le nombre et la qualité des passages comptent davantage** (H8). À mesurer sur Qwen2.5 et 3.5 : aucune étude spécifique à Qwen trouvée.

### Fenêtre effective des modèles ouverts
- **NoLiMa (ICML 2025)** — https://arxiv.org/abs/2502.05167 — 13 modèles revendiquant au moins 128K : à 32K, **10 descendent sous 50 % de leur score en contexte court** ; GPT-4o passe de 99,3 à 69,7. Longueur effective (≥ 85 % du score de base) bien inférieure à celle annoncée. [vérifié, abstract]
- **RULER (NVIDIA)** — https://github.com/NVIDIA/RULER — presque tous les modèles passent sous le seuil avant leur longueur annoncée. Llama-3.1-70B : moyenne 89,6, 66,6 à 128K (tableau 16 du rapport Qwen2.5, https://arxiv.org/abs/2412.15115). [secondaire] OneRuler (multilingue, https://arxiv.org/abs/2503.01996) couvre Qwen2.5 7B et 72B, sans chiffre relevé ici.
- Pour un 7B en 4 bits sur Mac, viser un contexte de moins de 8K tokens. La quantification dégrade aussi le long contexte (https://arxiv.org/abs/2505.20276, sans chiffre relevé).

### Contexte long contre RAG
- **Li et al., Self-Route (EMNLP 2024 Industry)** — https://arxiv.org/abs/2407.16833 — le contexte long bat le RAG « quand il a assez de ressources », mais le routage auto-réflexif réduit le coût de 65 % (Gemini-1.5-Pro) et 39 % (GPT-4o) à performance comparable. [vérifié]
- **LaRA (ICML 2025)** — https://arxiv.org/abs/2502.09977 — pas de solution miracle. Plus le modèle est faible, plus le RAG l'aide. Contexte long +2,4 % à 32K, RAG +3,68 % à 128K. Le RAG est meilleur pour détecter les hallucinations, le contexte long pour le raisonnement et la comparaison. [secondaire, chiffres variables selon la version]
- Cas anesthésie : PEACH (déc. 2024, https://arxiv.org/abs/2412.18096) utilise du « context stuffing » de protocoles avec Claude 3.5 Sonnet. [vérifié, abstract]
- **Ici** : le corpus fait environ 23M de caractères (≈ 6M tokens) [estimation tirée du README : 5,89M de caractères = 25,4 %], donc le contexte long intégral est hors de portée. Seule piste : « document long par routage » (une RFE entière, 20 à 80K tokens) pour les questions comparatives, au-delà de la fenêtre effective des modèles de 7 à 30B (NoLiMa). Faible priorité.

### Abstention, auto-correction, Self-RAG et CRAG
- **Sufficient Context (Google, ICLR 2025)** — https://arxiv.org/abs/2411.06037 — autorater de « contexte suffisant » à 93 % d'exactitude. Les petits modèles ouverts (Llama 3.1, Mistral, Gemma 2) hallucinent ou s'abstiennent souvent même quand le contexte suffit. La génération sélective améliore de 2 à 10 % la part de réponses correctes parmi les réponses données. Code disponible. [vérifié, résumé et blog]
- **CRAG** : reproduction ouverte (mars 2026, https://arxiv.org/abs/2603.16169) avec Phi-3-mini. Tiny-Critic RAG (https://arxiv.org/abs/2603.00846) remplace l'évaluateur T5-large par un petit modèle LoRA. [secondaire]
- Self-RAG (https://arxiv.org/abs/2310.11511) demande un modèle entraîné avec des tokens de réflexion. **Pas pertinent** avec des modèles génériques servis par Ollama ou vLLM. [non revérifié]

### Citations et vérification
- **ALCE (2023)** — https://arxiv.org/abs/2305.14627 — citation recall et precision par NLI (TRUE). Face à l'humain : exactitude de 85,1 % en rappel et 77,6 % en précision ; pas de détection du « support partiel ». [secondaire, cité dans la littérature]
- **ALiiCE (NAACL 2025)** — https://arxiv.org/abs/2406.13375 — évaluation de citations positionnelles à granularité fine. [secondaire]
- Un NLI multilingue anglais (TRUE est en anglais) est un point faible en français. Préférer un juge LLM local avec rubrique « la phrase est-elle entièrement soutenue par [R-id] ? », calibré sur 50 cas annotés.

### Contradictions entre éditions
- **HOH (ACL 2025)** — https://preview.aclanthology.org/ingestion-acl-25/2025.acl-long.301.pdf — les passages périmés nuisent au RAG. [secondaire]
- **CONFLICTS (juin 2025)** — https://arxiv.org/abs/2506.08500 — demander explicitement au modèle de raisonner sur les conflits du contexte améliore les réponses. [secondaire]
- **Re3 (ACL 2026)** — https://aclanthology.org/2026.acl-long.1180.pdf — modélise conjointement pertinence et récence au retrieval. [secondaire]
- Traduction ici (H9) : étiqueter chaque passage avec l'édition, l'année et le statut (en vigueur, remplacée, périmètre différent), et donner une consigne explicite de conflit.

---

## 6. Générateurs ouverts pour le français médical

### Résultats publiés en QA médicale française
- **MediQAl (juillet 2025)** — https://arxiv.org/abs/2507.20917 — 32 603 questions d'ECN, 41 spécialités. [vérifié, tableaux]
  - Exactitude MCQU : o3 73,15 ; DeepSeek-V3 63,32 ; GPT-4o 60,95 ; **Qwen2.5-72B 45,94** ; Llama-3.3-70B 43,36 ; Llama-3-70B-UltraMedical 38,31 ; HuatuoGPT-o1-8B 23,49 ; **BioMistral-7B 12,20**.
  - Questions ouvertes (juge LLM) : Qwen2.5-72B 59,49 ; BioMistral-7B 13,38.
  - **Aucun avantage net des modèles spécialisés médicaux** ; les distillations R1 de 7–8B s'effondrent en français.
- **MedGemma (juillet 2025, v4 avril 2026)** — https://arxiv.org/abs/2507.05201 — MedQA (anglais) : 4B 64,4 contre 50,7 pour Gemma 3 4B ; 27B 87,7 contre 74,9. [vérifié] Pas de résultat français trouvé. Licence HAI-DEF, pas Apache [non vérifié] : vérifier la compatibilité avec la contrainte de souveraineté et de licence.
- 2026 : synthèse SHTI sur les LLM open source en français médical (doi 10.3233/SHTI260298) [contenu non consulté] ; MedInjection-FR (mars 2026, jeu d'instructions biomédicales FR) [secondaire].

### Modèles candidats (sorties 2025–2026, poids ouverts)
- **Qwen3.5** (février 2026, Apache 2.0) : 397B-A17B, 122B-A10B, 35B-A3B, 27B, petits modèles dont 9B. Contexte natif de 262K. [secondaire : VentureBeat, Simon Willison, https://simonwillison.net/2026/Feb/17/qwen35/]
- **Gemma 4** (2 avril 2026, Apache 2.0) : E2B, E4B, (12B), 26B-A4B MoE, 31B dense. 128K à 256K de contexte. https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/ [vérifié, blog et model card]
- **Mistral Small 4** (16 mars 2026, Apache 2.0) : 119B, dont 6,5B actifs (MoE), 256K. Demande plusieurs GPU (environ 119 Go en FP8). https://docs.mistral.ai/models/mistral-small-4-0-26-03.md [vérifié]
- **Mistral Small 3.2 24B** (2025, Apache 2.0) : tient sur un seul GPU, éditeur français. [non revérifié dans cette veille]

**Recommandation H5** : sur LibreDataHub, A/B sur le dev entre `Qwen3.5-27B` (ou `35B-A3B` pour la latence), `Gemma-4-31B` (ou `26B-A4B`) et `Mistral-Small-3.2-24B`, à retrieval figé. Désactiver le mode « thinking » ou le budgéter. En dev Mac, `Qwen3.5-9B` ou `Gemma-4-E4B` en MLX 4 bits pourraient remplacer Qwen2.5-7B (disponibilité MLX non vérifiée). Note de souveraineté : les poids ouverts exécutés localement garantissent la souveraineté des données quelle que soit l'origine du modèle. Mistral reste l'option à privilégier si l'origine européenne est un critère.

---

## 7. Fine-tuning pour l'usage du contexte

- **RAFT (mars 2024)** — https://arxiv.org/abs/2403.10131 — entraînement avec documents oracle et distracteurs, et réponses CoT qui citent verbatim le passage utile. Gains sur PubMed, HotpotQA et Gorilla. [vérifié, abstract ; chiffres non relevés]
- **CRAFT (sept. 2024)** — https://arxiv.org/abs/2409.17648 — RAFT avec LoRA pour environnements contraints, performance comparable à coût réduit. [vérifié, abstract]
- **Jin et al. (ICLR 2025)** — https://arxiv.org/abs/2410.05983 — fine-tuning implicite de robustesse aux « hard negatives » et fine-tuning explicite avec raisonnement intermédiaire. [vérifié, abstract]
- MediQAl : SFT de BioMistral-7B sur MediQAl, MCQU de 12,2 à 27,84. Gros gain relatif, mais niveau absolu toujours bas. [vérifié]
- **Données nécessaires** : aucun chiffre fiable trouvé pour un RAFT médical. De l'ordre de quelques milliers de triplets (question, contexte avec distracteurs, réponse citée) [non vérifié]. On peut les synthétiser depuis les recommandations extraites (H3) avec un modèle plus grand.
- **Verdict datathon** : coût de mise en œuvre élevé (génération de données, validation clinique, LoRA, risque de sur-apprentissage, MLX-LM ou PEFT), alors que changer de générateur (H5) apporte probablement plus pour moins. À reconsidérer seulement si le 7B local est imposé en production.

---

## 8. Évaluation RAG

- **RAGAS (sept. 2023)** — https://arxiv.org/abs/2309.15217 — accord avec l'humain sur WikiEval : fidélité 0,95, pertinence de réponse 0,78, pertinence du contexte 0,70. [secondaire]
- **ARES (nov. 2023)** — https://arxiv.org/abs/2311.09476 — τ de Kendall 0,91 (pertinence du contexte) et 0,97 (pertinence de la réponse) en domaine. [secondaire]
- **RAGChecker (août 2024)** — https://arxiv.org/abs/2408.08067 — dans sa méta-évaluation, la fidélité RAGAS corrèle faiblement avec le jugement humain. [secondaire]
- **GroUSE (sept. 2024)** — https://arxiv.org/abs/2409.06595 — une bonne corrélation ne garantit pas la calibration sur les cas limites ; RAGAS et DeepEval divergent à définition égale, à cause du prompt. [secondaire] → **Ne pas comparer des scores RAGAS entre outils ou entre prompts de juge.**
- **Biais des juges** :
  - MT-Bench (https://arxiv.org/abs/2306.05685) : plus de 80 % d'accord avec l'humain ; biais de verbosité ; auto-préférence non concluante. [secondaire]
  - Position bias (https://arxiv.org/abs/2406.07791) : varie selon le juge et la tâche ; une partie s'explique par l'écart de qualité. [secondaire]
  - Atténuations sans réentraînement (avril 2026, https://arxiv.org/abs/2604.23178). [secondaire]
- **Juges en médecine** : accords LLM–médecin de κ ≈ 0,7 à 0,8 sur de petits échantillons ; un juge par mots-clés tombe à κ 0,18 ; des juges fermés plus forts peuvent être moins bien calibrés. [secondaire, préprints 2025–2026 hétérogènes] → **calibrer localement**.
- **Benchmarks français** et pertinence pour l'anesthésie :
  - **MediQAl** (ECN, 41 spécialités) : utile pour pré-sélectionner un générateur en français médical, pas pour le RAG SFAR (connaissance générale, sans contexte).
  - **FrenchMedMCQA** (2023, https://arxiv.org/abs/2304.04280) : questions de pharmacie, environ 3 105 [non vérifié]. Pertinence faible pour l'anesthésie.
  - **DrBenchmark** (LREC-COLING 2024, https://aclanthology.org/2024.lrec-main.478) : 20 tâches de compréhension (NER, POS, STS, classification) pour encodeurs. Hors sujet pour la génération ; éventuellement pour choisir un encodeur.
  - CareMedEval (lecture critique) et MedFrenchmark (114 exemples) : marginaux.
  - Côté anesthésie : RAG sur des questions de type board ABA (JMIR Formative Research 2026, https://formative.jmir.org/2026/1/e97902) — les gains dépendent fortement des embeddings et du chunking [secondaire, page non lisible].
  - **Aucun benchmark public ne couvre les RFE SFAR** : le gold set interne et le lockbox restent la référence.

---

## Ce qui ne vaut probablement pas le coup ici, et pourquoi

1. **Chunking sémantique ou par propositions générées par LLM sur tout le corpus** : gains incohérents ou faibles avec des retrievers supervisés (NAACL Findings 2025 ; Caspari et al. 2026 ; Dense X : +2,2 à 2,7 points seulement en supervisé), pour un coût d'indexation LLM élevé. La structure native (recommandations, tableaux, sections) est un meilleur découpage.
2. **GraphRAG d'entités, LightRAG, RAPTOR** : conçus pour la synthèse globale et le multi-sauts sur de longs textes. Les questions SFAR sont surtout ponctuelles, et le graphe utile (supersession, encadrés) existe déjà. Indexation coûteuse, gain non démontré sur ce type de question.
3. **HyDE systématique et réécriture générique** : les expansions nuisent aux retrievers forts (arXiv 2309.08541) ; elles ajoutent un appel LLM et un risque d'hallucination dans la requête. Le lexique d'acronymes suffit.
4. **Rerank listwise par LLM (RankZephyr, RankGPT)** : latence d'un ordre de grandeur au-dessus d'un cross-encoder, pour un gain incertain face à Qwen3-Reranker-4B.
5. **Contexte long intégral à la place du RAG** : environ 6M de tokens de corpus, fenêtre effective bien plus courte que la fenêtre annoncée (NoLiMa), et le RAG reste meilleur pour la détection d'hallucinations et la traçabilité (LaRA). Le « document entier » par routage reste une option de niche.
6. **Optimiser finement l'ordre U-shape** : l'effet de position est marginal en RAG réaliste (EMNLP 2025 : pas mieux qu'aléatoire) et non reproduit sur des modèles 2024–2025 (SIGIR 2026). Mieux vaut régler k et la qualité du rerank.
7. **Modèles médicaux spécialisés de 7–8B (BioMistral, Meditron, UltraMedical-8B, HuatuoGPT-o1-8B)** : très faibles en français (MediQAl : BioMistral-7B 12,2 % en MCQU) et peu fidèles au contexte (NICE : Meditron3-8B à 43 % de fidélité). Un modèle généraliste récent de 24 à 31B est préférable.
8. **Self-RAG** : exige un modèle entraîné avec des tokens de réflexion, incompatible avec un générateur interchangeable servi par Ollama ou vLLM.
9. **ColBERT ou multi-vecteurs stockés dans pgvector** : pas de MaxSim natif, stockage multiplié. Si on en veut, l'utiliser comme reranker du top-100.
10. **Fine-tuning RAFT/LoRA pendant le datathon** : données à synthétiser et à valider cliniquement, risque élevé. Changer de générateur et durcir les citations rapportent davantage pour moins.
11. **Modèles sous licence non commerciale (Jina v3/v4, Jina-ColBERT, jina-reranker-v3, probablement Nemotron-embed)** : à écarter tant que la licence n'est pas vérifiée compatible avec LibreDataHub, puisque des équivalents Apache 2.0 ou MIT existent (Qwen3, BGE).
12. **Benchmarks français génériques (FrenchMedMCQA, DrBenchmark) comme critère de succès** : hors périmètre anesthésie et sans contexte. Ils servent au mieux à pré-sélectionner un générateur.
