# Audit de code : module retrieval (RAG-SFAR)

Périmètre : `src/rag_sfar/retrieval/*.py`, `src/rag_sfar/config.py` (RetrievalConfig), lecture de `schemas.py` et des appelants (`generation/client.py`, `interfaces/api.py`, `interfaces/mcp_server.py`, `evaluation/benchmark_adapter.py`, `evaluation/ablation.py`).
Index utilisé pour les vérifications : `index/table_aware_sota` (264 documents, 32 591 chunks, e5-small, subword activé), commit `943e0cd`.
Toutes les commandes se lancent depuis la racine du dépôt avec `HF_HUB_OFFLINE=1 .venv/bin/python`. Aucun fichier source n'a été modifié, aucun index reconstruit.

---

## Conclusions (par gravité)

### Critique

1. **Le lexique développe des mots français courants comme des acronymes : « pas » devient « pneumonie associée aux soins ».** `expand_medical_query` compare `tok.upper()` au dictionnaire d'acronymes, avec une liste d'exclusion incomplète (`medical_lexicon.py:144-147`). Sur « Faut-il **ne pas** arrêter l'aspirine avant une chirurgie ? », la requête étendue reçoit « pneumonie associée aux soins » et le routeur ajoute le domaine Infectiologie. Sans reranker, **7 des 8 chunks** viennent de la RFE « Pneumonies associées aux soins de réanimation ». Avec le reranker, il en reste **3 sur les 6 premiers** (preuve en §medical_lexicon). Comme « ne pas » est très fréquent dans les questions cliniques, ce défaut touche une grande partie des requêtes réelles.

2. **Le routeur produit des faux positifs, et ces faux positifs déclenchent des pénalités lourdes ainsi qu'une alerte « patient allergique » dans le prompt.**
   - `PEDIATRIC_QUERY_RE` contient `\d+\s*mois` et `[1-9]\s*ans` (`router.py:25-29`). « stent posé il y a 6 mois » donne `population=pediatrie`, ce qui pénalise les chunks adultes.
   - Le modificateur `allergy` se déclenche sur `alternative\w*`, `pénicilline\w*` et `bêtalactamine\w*` (`router.py:45`). « Quelle **alternative** à l'intubation orotrachéale ? » ou « place des **pénicillines** dans la pneumonie » donnent `modifiers=['allergy']`. Or `generation/client.py:280-286` place alors en tête du contexte « ⚠️ ALERTE CLINIQUE : Patient ALLERGIQUE aux bêtalactamines/pénicillines… ». C'est un risque de sécurité dans les réponses.
   - Les domaines sont inférés par sous-chaîne (`router.py:105-107`). Le mot-clé `rac` de « Ambulatoire et Réhabilitation » correspond à « f**rac**ture », « orot**rac**héale » et « **rac**hianesthésie ». Ce domaine couvre 11 242 chunks (34 % du corpus), qui reçoivent donc un bonus de domaine à tort.

### Important

3. **Des heuristiques propres à la RFE antibioprophylaxie sont codées en dur dans le pipeline générique, et plusieurs reprennent des questions du benchmark** (signal de fuite à transmettre à l'audit d'évaluation) :
   - Bonus `+0.35` si la requête et la section contiennent « main » (`pipeline.py:559-560`). Le benchmark contient « plaie de la main », « écrasement complexe de la main ».
   - `cond_triggers` « voie antérieure / épaule / ouverture articulaire / dure-mère » (`pipeline.py:586-606`). Les lignes ciblées appartiennent toutes à la RFE antibioprophylaxie (5 lignes). Le benchmark contient « prothèse de hanche par voie antérieure ».
   - Le bonus « diff » vise `"v3.0"` et `"historique des versions"` (`pipeline.py:536-546`). Seuls 6 chunks du corpus sont concernés, tous dans l'antibioprophylaxie.
   - L'exemple de la docstring de `extract_composite_procedure_subqueries` (`crag.py:204-205`) est **mot pour mot** une question du benchmark (« splénectomie d'hémostase associée à la pose d'un fixateur externe sur fracture fermée du fémur »).
   - `FACET_RULES` (`crag.py:31-58`) écrivent en dur des identifiants de recommandation (`R1.2`, `R1.5`, `R1.6`, `R1.7`) et des molécules. Or chaque RFE numérote ses recommandations à partir de R1.1.
   - L'ancre `"orl"` ajoute « antibioprophylaxie » à la requête (`crag.py:162-165`).
   - La regex « options QCM = médicaments » (`crag.py:129-138`) ne contient que des antibiotiques.
   - `callout_allergy` et `select_generation_context` reposent sur un type de chunk qui n'existe que dans 29 chunks, tous issus de la même RFE.

4. **La pénalité pédiatrique s'applique aussi aux requêtes sans population précisée, et le premier flag d'ablation ne la désactive pas.** `pipeline.py:340-343` multiplie par 0.72 les chunks `pediatrie` dès que `population != "pediatrie"`, ce qui inclut `non_specifie` et `mixte`. Ce code n'est conditionné par aucun flag. `pipeline.py:508-510` ajoute une pénalité de −0.23 au stade de la fusion, que `use_soft_metadata_boost` désactive, mais la pénalité post-rerank reste. Exemple sur « Quelle analgésie postopératoire après amygdalectomie ? » : le chunk au meilleur score cross-encoder (0.99995, RFE amygdalectomie chez l'enfant) se classe 3e, derrière un chunk à 0.81. Sans le bonus de métadonnées, ce chunk revient 1er. 13 % du corpus (4 359 chunks) porte `population_hint=pediatrie`.

5. **L'exclusion « (hors X) » se déclenche sur les titres de documents et pénalise le bon document.** Le `section_path` contient le titre, par exemple « Intubation en urgence d'un adulte **hors bloc** opératoire… ». Pour la requête « Intubation en urgence **hors du bloc** opératoire », ce document reçoit `boost=-0.35` et `scope_mult=0.45`, contre `+0.30` et `1.0` si la requête dit « hors bloc ». La règle fonctionne par simple sous-chaîne (`pipeline.py:549-558` et `578-584`).

6. **Contrats de sortie non tenus et chemins d'évaluation différents de la démo.**
   - `final_top_k` n'est pas une borne : avec `final_top_k=3`, `retrieve()` renvoie 5 ou 6 chunks. Les ajouts 6b, la phase CRAG et l'expansion se font *après* la sélection, sans plafond global (`pipeline.py:379-431`).
   - La liste renvoyée n'est pas triée par score, alors que `format_context_for_llm` applique l'ordre en U en supposant un ordre de pertinence décroissant (`pipeline.py:751-756`).
   - `benchmark_adapter.py:98` passe `prune_prose=self._config.use_u_shape_ordering` (le mauvais flag). Il n'appelle ni `select_generation_context` ni l'alerte allergie, contrairement à `client.py:263-286`. Le benchmark mesure donc un contexte différent de celui que reçoit l'API.

7. **Pile de scores difficile à justifier.** On compte environ 40 constantes sans justification ni mesure individuelle : poids RRF 1.0/0.65/1.0, `dbsf_blend` 0.35, bonus de 0.10 à 0.55, plancher 0.25, mélange 0.68 CE / 0.32 a priori, ×0.72, ×0.45, ×0.68/×1.12, seuils 0.65/0.7/0.82/0.90. Les a priori multiplicatifs peuvent dépasser +100 % alors que l'écart RRF entre les rangs 1 et 10 est d'environ 13 %. L'ablation `C7 → C8` active 5 options à la fois (subword, DBSF, CRAG, U-shape, pruning, voir `ablation.py`), ce qui ne permet d'attribuer aucun gain.

### Mineur

8. **Code mort et duplication.**
   - `reorder_lost_in_the_middle` est importé (`pipeline.py:29`) mais réimplémenté en ligne (`pipeline.py:751-756`). `import math` n'est pas utilisé (`pipeline.py:22`).
   - `PgVectorStore` n'est branché nulle part : `Settings.vector_backend` n'est lu par aucun code. Son CTE `sparse` fait un `LIMIT 40` sans `ORDER BY` (`vector_store.py:357-365`).
   - `Settings.index_dir` vaut `index/sota_default` par défaut (`config.py:26`), un dossier absent du dépôt (le dossier réel est `index/table_aware_sota`). Le `.env` le redéfinit peut-être, mais je ne l'ai pas lu.

9. **Tokenisation et identifiants de recommandation.** `tokenize_medical_french("R1.2.1")` donne `['r1.2', '1']` (`medical_lexicon.py:164`), donc BM25 ne distingue pas R1.2.1 de R1.2.3. La regex de preuve `\bR1\.2\b` accepte « R1.2.1 ». Les identifiants ne sont pas uniques entre les 264 documents.

10. **Échecs silencieux.** L'échec d'initialisation du reranker est avalé par `except Exception: reranker = None` (`api.py`, `mcp_server.py:235`) : la démo tourne alors sans reranker, sans alerte. Le constructeur du modèle retente par le réseau en cas d'échec local (`embedder.py:61-64`, `reranker.py:40-45`). Le cross-encoder applique sa propre sigmoïde (`reranker.py:52-60`) : c'est correct avec sentence-transformers 6.3.0, où l'activation par défaut est `Identity()` (vérifié), mais `pyproject.toml` accepte `>=3.0`. Je n'ai pas vérifié les anciennes versions, où une double sigmoïde est possible (voir §reranker).

**Performance : rien de bloquant pour la démo.** La récupération prend 250 à 540 ms par requête sur MPS, dont 225 à 490 ms pour le reranking de 24 paires. Le chargement prend 3 s pour l'index et 11 s pour les modèles. La mémoire résidente maximale est d'environ 1,0 à 1,25 Go, dont `subword.pkl` (321 Mo sur disque, matrices CSR et CSC toutes deux en mémoire). Le CRAG ajoute quelques ms.

**Points vérifiés et corrects.** La formule BM25+ et le masquage sont justes. La normalisation DBSF (μ ± 3σ, bornée) est correcte. Le masque de filtrage dur est cohérent. Il n'y a pas de double sigmoïde dans l'environnement actuel. Sur 4 requêtes génériques hors antibioprophylaxie (obèse/intubation, IRA, amygdalectomie, intubation hors bloc), le CRAG n'a **pas** injecté de chunks d'antibioprophylaxie dans le top-8 : la contamination redoutée ne s'est pas produite sur ces cas.

---

## Preuves par fichier

### `config.py` (RetrievalConfig, Settings)

| Constat | Preuve |
|---|---|
| `index_dir` par défaut inexistant | `config.py:26` `index_dir: Path = Path("index/sota_default")` ; `ls index/` → `hierarchical_markdown naive_fixed table_aware_sota` |
| `vector_backend` et `pgvector_dsn` jamais lus par le retrieval | `grep -rn "vector_backend" src scripts` → uniquement `config.py:50` ; `pgvector_dsn` lu seulement dans `scripts/export_pgvector.py:21` |
| `use_context_pruning` regroupe 3 comportements (sélection `select_generation_context`, pruning de prose, alerte allergie) | `client.py:263-286` |
| `use_u_shape_ordering` est détourné en flag de pruning dans l'adaptateur benchmark | `benchmark_adapter.py:98` `prune_prose=self._config.use_u_shape_ordering` |
| `max_context_chars=16000` ne limite que les ajouts (CRAG et expansion), pas la sélection de base | `pipeline.py:469`, `694`, `724` |
| `max_chunks_per_doc=7` avec `final_top_k=8` : la contrainte de diversité est quasi inactive | `config.py:97-100` |
| `chunking_strategy` n'est pas lu par le retriever, seulement par l'ablation pour choisir l'index | `ablation.py:232` |
| `use_bm25=False` n'empêche pas BM25 dans le CRAG (facettes, sous-requêtes QCM, rescue) | `pipeline.py:198`, `205`, `456` (`self.store.bm25.search` sans test de `cfg.use_bm25`) |

### `pipeline.py`

**Fusion (l.174-283)**
- La formule RRF pondérée est correcte. Pour le DBSF, chaque canal est normalisé sur ses top-k hits et les absents valent 0 : c'est acceptable.
- La normalisation `rrf_norm = rrf / max_rrf_unit` (l.238, 261) ne borne pas le score à [0, 1] comme l'affirme le commentaire l.232. `facet_rank_bonus` ajoute jusqu'à `(0.60+0.40)/(k+1)` **par sous-requête QCM ou composite** (l.213-217), alors que `max_rrf_unit = 2.65/(k+1)`. Avec 4 options, un chunk classé 1er partout atteint `rrf_norm ≈ (4 + 2.65)/2.65 ≈ 2.5` : le bonus des sous-requêtes domine les trois canaux principaux.
- Le bonus multiplicatif `fused_score = base_score * max(0.25, meta_mult)` (l.268) peut combiner domaine +0.18, population +0.25, rôle +0.15, type de chunk +0.14, année +0.25, allergie +0.14, diff +0.55, main +0.35 et hors −0.65. Ces a priori ont un ordre de grandeur supérieur aux écarts RRF.

**Reranking (l.285-347)**
- Le mélange `0.68*ce + 0.32*norm_prior` (l.339) est une constante sans justification.
- La pénalité ×0.72 pour la population (l.340-343) n'est pas conditionnée par un flag et s'applique aux requêtes `non_specifie` et `mixte`.
- Avec `use_reranker=False`, les chunks « garantis » sont ajoutés **après** le pool trié (l.326-328) sans nouveau tri. `_select_diverse` s'arrête à `final_top_k` et ne les atteint donc jamais : la garantie n'existe qu'avec le reranker.
- Les scores de `fused` sont modifiés en place par le rerank (même objet), puis réutilisés en 6b via `fused_by_id` (l.385, 393, 408). On compare alors des échelles différentes : score fusionné non borné et score post-rerank dans [0, 1].

**Sélection et injections (l.349-434)**
- `_select_diverse` déduplique sur les 180 premiers caractères alphanumériques (l.637). Mesure sur l'index (chunks actifs, dernière édition, hors références) : 568 groupes de textes distincts partagent la même signature, dont 142 ont une similarité inférieure à 0.8. Exemples : fragments de prose qui ont le même préfixe mais une suite différente, ou la note « 3 » et « **3** ». Ces collisions viennent surtout de la fragmentation à l'ingestion ; l'impact est mineur.
- Constantes magiques en 6b : 4 injections au maximum, seuil `rerank_score < 0.65`, `scope < 0.7`, score `base_top*0.82`, types autorisés limités aux tableaux et encadrés.
- La liste finale n'est pas triée : les injections, les rescues et l'expansion sont ajoutés à la fin (l.405, 471, 695, 726).

**Heuristiques spécifiques**

| Ligne | Heuristique | Portée réelle dans le corpus |
|---|---|---|
| 536-546 | `diff` : `"historique des versions"` ou `"v3.0"`, mot-clé `"pédiatri"` | 6 chunks, tous dans « Antibioprophylaxie en chirurgie et médecine interventionnelle » |
| 549-558, 578-584 | `(hors X)` dans `section_path` | 157 chunks « hors fracture » (RAAC), 31 « hors bloc », « hors nouveau-nés »… Le titre fait partie de `section_path`, donc la règle porte sur tout le document |
| 559-560 | `\bmain\b` dans la requête et la section : +0.35 | Le benchmark contient « plaie de la main » et « écrasement complexe de la main » (`benchmark.json` l.68, 110, 1030) |
| 586-606 | `cond_triggers` (voie antérieure, épaule, ouverture articulaire, dure-mère) | 5 lignes de tableau, toutes dans la RFE antibioprophylaxie |
| 664-683 | Encadré allergie « En cas d'allergie » | `callout_allergy` : 29 chunks sur 32 591, tous dans la RFE antibioprophylaxie |

Reproduction de la portée réelle :
```bash
sqlite3 index/table_aware_sota/metadata.sqlite "select json_extract(payload_json,'$.doc_title'), count(*) from chunks where chunk_type='callout_allergy' group by 1;"
```

Reproduction du problème « hors du bloc » :
```bash
HF_HUB_OFFLINE=1 .venv/bin/python -c "
from pathlib import Path; from rag_sfar.retrieval.vector_store import LocalVectorStore as S
from rag_sfar.retrieval.pipeline import SfarRagRetriever as R; from rag_sfar.retrieval.router import analyze_query as A
from rag_sfar.config import RetrievalConfig as C
s=S.load(Path('index/table_aware_sota')); r=R(s); c=next(c for c in s.chunks if 'hors bloc' in c.section_path.lower())
for q in ['Intubation en urgence hors du bloc opératoire : quelle sédation ?','Intubation en urgence hors bloc opératoire : quelle sédation ?']:
    a=A(q); print(round(r._compute_soft_metadata_boost(c,a,C()),3), r._compute_clinical_scope_multiplier(c,a), q)"
# -> -0.35 0.45 (hors du bloc) / 0.3 1.0 (hors bloc)
```

**Contrat `final_top_k`.** Avec `final_top_k=3`, la requête « PTH … obèse allergique … BLSE, R1.6 » renvoie 5 chunks (`specialty_allergy_box`, `next_neighbor`) et la requête composite « splénectomie … fixateur externe … enfant » en renvoie 6 (3 `crag_rescue:multi_act_or_mcq_option`). Mesuré avec `SfarRagRetriever(store)` sans modèles.

**`format_context_for_llm` (l.741-780).** L'ordre en U est dupliqué avec `context_optimizer.reorder_lost_in_the_middle`. Les numéros `[S{orig_idx}]` restent cohérents avec les citations, ce qui est correct. En revanche, la position d'entrée n'est pas un rang de pertinence (voir plus haut).

### `bm25.py`
- BM25+ (k1=1.5, b=0.65, δ=0.5) et l'IDF Lucene sont corrects. Le masque passe les chunks exclus à −1 et la sélection garde `scores > 0` : correct. Le poids de requête sous-linéaire est correct (l.99).
- Il n'y a pas de racinisation ; la tolérance morphologique est déléguée au canal subword.
- Latence mesurée : 0.3 à 0.8 ms par recherche (à chaud). Aucun problème.

### `subword.py`
- TF-IDF sur n-grammes de caractères 3 à 5, `max_features=120000`. Le fichier `subword.pkl` fait **321 Mo**, et `load` garde CSR **et** CSC en mémoire (l.98-99), alors que seule la CSC sert à la recherche.
- Latence mesurée : 4 à 11 ms à chaud, 26 ms à froid. Le gain n'a pas été mesuré isolément (l'ablation C8 active subword en même temps que 4 autres options).
- Le seuil `min_df` dépend de la taille du corpus (l.42) : c'est raisonnable.

### `embedder.py`
- e5 : les préfixes `query:` et `passage:` sont corrects. `local_files_only=True` est suivi d'un `except Exception` qui retente sans ce paramètre (l.61-64) : hors mode offline, la démo peut tenter un téléchargement.
- `OpenAICompatibleEmbedder.dim = 0` tant qu'aucun appel n'a eu lieu, donc `embed_documents([])` renvoie un tableau de forme `(0, 0)`. C'est mineur.
- `TfidfSvdEmbedder.embed_documents` réajuste le modèle à chaque appel : il ne sert donc qu'à l'indexation. C'est correct pour cet usage mais piégeux.
- Latence de `embed_query` sur MPS : 12 à 67 ms.

### `reranker.py`
- Vérification : `CrossEncoder.activation_fn` vaut `Identity()` (sentence-transformers 6.3.0). `predict` renvoie bien des logits (7.22 / −6.31) et `score_pairs` les passe en sigmoïde (0.9993 / 0.0018). **Pas de double sigmoïde ici.** Avec sentence-transformers 3.x, l'activation par défaut d'un modèle à 1 label était, à ma connaissance, `Sigmoid` : je ne l'ai pas vérifié, mais il faut épingler la version ou passer `activation_fn=Identity()` explicitement.
- Le passage est tronqué à `indexed_text[:2400]` caractères puis à `max_length=512` tokens.
- Le reranker note la requête **étendue** (`pipeline.py:332`). Il hérite donc des erreurs du lexique : l'ajout « (pneumonie associée aux soins) » change la pertinence évaluée.
- Coût mesuré : 225 à 493 ms pour 24 paires sur MPS. C'est le poste dominant de la latence.

### `router.py`
Reproduction des faux positifs :
```bash
HF_HUB_OFFLINE=1 .venv/bin/python -c "
from rag_sfar.retrieval.router import analyze_query as A
for q in ['Chez un patient sous AOD, quel délai d\'arrêt 6 mois après un stent ?','Quelle alternative à l\'intubation orotrachéale en cas d\'échec ?','Quelle est la place des pénicillines dans le traitement de la pneumonie ?','Prise en charge d\'une fracture du col du fémur chez le sujet âgé']:
    a=A(q); print(a.population, a.modifiers, a.inferred_domains)"
```
Résultats :
- `pediatrie ['dosage'] [...]` : « 6 mois » est pris pour un âge.
- `non_specifie ['allergy'] ['Voies Aériennes','Ambulatoire et Réhabilitation']` : « alternative » déclenche l'allergie et « rac » le domaine ambulatoire.
- `['allergy']` pour la question sur les pénicillines.
- `['Traumatologie','Ambulatoire et Réhabilitation']` pour la fracture.

Autres points :
- `ADULT_QUERY_RE` contient « prostate », « césarienne », « grossesse » (l.30) : liste ad hoc.
- La détection d'années (`20[0-2]\d`, l.66) passe en `specific_year` dès qu'une année est citée, et `build_filter_mask` retombe sur toutes les éditions (y compris remplacées) si l'année n'existe pas. En effet `latest_only` est déjà à False (`pipeline.py:115-116`) et le filtre d'année est ignoré quand il viderait le masque (`vector_store.py:78-81`).
- La même correspondance par sous-chaîne existe à l'ingestion (`loader.py:576-579`), ce qui explique sans doute pourquoi « Ambulatoire et Réhabilitation » couvre 34 % des chunks. Ce point relève de l'audit ingestion.

### `medical_lexicon.py`
- l.144-147 : un token en minuscules est développé si son équivalent en majuscules est un acronyme non exclu. L'exclusion ne couvre que `ID, FA, MI, MS, TC, EP, AG, HM`. **« pas » → PAS** a été vérifié. D'autres collisions sont possibles (« ira » → IRA, « iso » → ISO) mais je ne les ai pas mesurées.
- Effet mesuré, sans modèles :
  - « Faut-il arrêter l'aspirine avant une chirurgie ? » : 7 des 8 premiers chunks viennent des RFE AAP et coronarien, c'est correct.
  - « Faut-il **ne pas** arrêter… » : 7 des 8 viennent de « Pneumonies associées aux soins de réanimation ».
  - Avec e5 et le cross-encoder : 3 des 6 premiers chunks restent des pneumonies.
- `tokenize_medical_french` : un seul séparateur est conservé (`[./-]`), donc `R1.2.1 → r1.2, 1` et `1,5 g → 1, 5`.
- Le contenu des dictionnaires (acronymes et noms commerciaux) est générique au domaine anesthésie-réanimation : c'est raisonnable.

### `crag.py`
- Facettes : les sous-requêtes et regex sont écrites pour l'antibioprophylaxie et l'anticoagulation (l.31-58). Exemples : facette obésité « … antibioprophylaxie R1.5 R1.6 céfazoline amoxicilline clindamycine » ; facette rénale « … AOD dabigatran apixaban rivaroxaban » ; la regex de preuve de la facette obésité accepte `r1.5` ou `r1.6` de n'importe quelle RFE.
- Effet mesuré sur 4 requêtes génériques : avec ou sans `use_crag_multihop`, le top-8 est identique ou quasi identique et ne contient **aucun** chunk d'antibioprophylaxie. Sur ces cas, le CRAG est inerte : il ne fait pas de mal mais n'apporte rien de démontré.
- `_extract_anchor_terms` (l.89-112) : liste fermée de 15 mots tirés de 2 ou 3 RFE.
- `extract_mcq_option_subqueries` (l.147-177) :
  - seules les options A à D sont lues (`_MCQ_OPTION_LINE_RE`, l.139), les options E sont ignorées ;
  - `query.find("A.")` peut tomber sur un « A. » du stem (l.159) ;
  - la regex « options = médicaments » ne contient que des antibiotiques. Un QCM sur les curares (Rocuronium, Succinylcholine…) est donc traité comme 4 « actes cliniques » et lance 4 × (BM25 + subword) supplémentaires. Vérifié : `[('A','Rocuronium'),…]`.
- `extract_composite_procedure_subqueries` : la séparation sur « et d'une » se déclenche sur des requêtes banales. Vérifié : « hypotension **et d'une** bradycardie lors d'une rachianesthésie » donne 2 sous-requêtes.
- L'exemple de la docstring (l.204-205) est une question du benchmark mot pour mot (`grep -o "splénectomie d'hémostase.\{40\}" data/.../benchmark.json`).

### `context_optimizer.py`
- `reorder_lost_in_the_middle` n'est utilisé que par les tests. Le pipeline a sa propre copie.
- `prune_verbose_prose` ne s'applique qu'aux chunks `prose` de plus de 1 100 caractères, soit 19,5 % des chunks prose (médiane 828 caractères). Il est bien protégé (tableaux, encadrés, GRADE, posologies) ; son gain n'a pas été mesuré.
- `select_generation_context` (l.89-193) est essentiellement de la logique « encadré allergie de la même spécialité » (`callout_allergy` + `parent_section_id`). Sur le reste du corpus, il se réduit à : garder les 2 premiers, les rescues CRAG, puis les autres au-dessus de 0.62 × top1. Le seuil `final_score >= 0.80` (l.120) dépend de l'échelle du mélange post-rerank.

### `vector_store.py`
- `LocalVectorStore` : les masques sont précalculés et corrects. `prefer_french` est en réalité un filtre dur (`language != "en"`, qui exclut 2 049 chunks `traduction_en`). Les filtres `allowed_years` et `required_domains` sont ignorés **silencieusement** s'ils videraient le masque (l.78-90), alors que `doc_ids` n'a pas ce garde-fou (l.91-98). Le masque de domaine est recalculé en Python sur les 32 000 chunks à chaque requête qui en demande un.
- `dense_search` : produit scalaire exact, sentinelle −2 et seuil −1.5, correct.
- `PgVectorStore` : il n'est appelé par aucun chemin de requête (seulement `scripts/export_pgvector.py`). Le CTE `sparse` (l.357-365) fait `LIMIT 40` sans `ORDER BY`, donc Postgres ne garantit pas que ce soient les 40 meilleurs. Il n'applique ni subword, ni a priori, ni rerank. Le présenter comme « backend production » est trompeur tant qu'il n'est pas relié au pipeline.

### Interfaces (signalement seul, sans modification)
- `SfarRagRetriever.retrieve(query, config, override_latest_only, override_domains, override_doc_ids)` renvoie `(list[RetrievedChunk], QueryAnalysis, dict)`. Les appelants (`api.py:406`, `client.py:255/411`, `mcp_server.py:98/116`, `benchmark_adapter.py:97`, `retrieval_metrics.py:89`) sont cohérents avec cette signature. `override_doc_ids` n'est utilisé par aucun appelant.
- `mcp_server.py:101` force `override_latest_only=args.get("latest_only", True)`, ce qui contourne la détection temporelle du routeur pour l'outil `search`. C'est acceptable puisque `compare_sfar_editions` existe.
- `api.py` : `SearchRequest.latest_only=None` laisse le routeur décider, c'est correct. `top_k` est passé à `final_top_k`, mais l'API renvoie plus de chunks que demandé (voir conclusion 6).

### Performance (mesurée, machine partagée, MPS)

| Étape | Mesure |
|---|---|
| Chargement de `LocalVectorStore` | 3.0 s ; mémoire résidente max ≈ 1,24 Go (sans modèles) |
| Chargement e5-small et mMiniLM-L12 | 10.9 s |
| BM25 | 0.3 à 0.8 ms |
| Subword | 4 à 11 ms à chaud (26 ms au premier appel) |
| Embedding dense de la requête | 12 à 67 ms |
| Fusion | 2 à 6 ms |
| Rerank (24 paires) | 225 à 493 ms |
| **Total `retrieve`** | **250 à 540 ms** |

Il n'y a pas de goulot pour une démo en direct. Les optimisations possibles sont `rerank_top_k` de 24 à 16 et la libération de la matrice CSR du canal subword.

---

## Garder / simplifier / généraliser / supprimer

| Composant | Verdict | Mesure qui tranche |
|---|---|---|
| BM25+ (`bm25.py`) | **Garder** | — (correct, rapide) |
| Tokenizer | **Généraliser** : conserver les identifiants à plusieurs points (`r1.2.1`) | Recall@k sur des questions citant un identifiant de recommandation |
| Subword n-grammes | **Garder sous condition** : 321 Mo, ne garder que la CSC | Ablation isolée (C7 + subword seul) : ΔRecall@8 et ΔMRR. Supprimer si < +1 point |
| Dense e5 (`embedder.py`) | **Garder** | — |
| Fusion RRF | **Garder, simplifier** : poids égaux par défaut | Comparer poids 1/0.65/1 et 1/1/1 |
| DBSF | **Simplifier ou supprimer** | Ablation isolée `use_dbsf_fusion` ; supprimer si Δ ≈ 0 |
| Bonus de métadonnées (rôle, type, année, setting) | **Simplifier** : moins de termes, plafond global | Ablation terme par terme sur un jeu de questions multi-RFE |
| Pénalité pédiatrique (fusion et ×0.72 post-rerank) | **Corriger** : seulement si `population == "adulte"` explicite ; mettre le ×0.72 derrière un flag | Requêtes pédiatriques sans mot « enfant » (amygdalectomie, etc.) : rang du meilleur chunk |
| `(hors X)` | **Généraliser** : n'utiliser que les titres de section, pas le titre du document, et traiter « hors du/de la » | Requêtes « hors bloc », « hors fracture » : rang du document attendu |
| `main` +0.35, `cond_triggers`, `diff v3.0` | **Supprimer** (spécifiques à une RFE, liés au benchmark) | Score multi-RFE avant/après (attendu ≈ 0) ; score antibioprophylaxie avant/après pour chiffrer la dépendance au benchmark |
| Routeur : population | **Corriger** : retirer `\d+ mois` / `N ans` nus, exiger un contexte d'âge (« enfant de 6 mois ») | Jeu de 50 requêtes adultes contenant une durée : taux de faux positifs pédiatriques |
| Routeur : modificateur allergie | **Corriger** : retirer `alternative`, exiger `allerg\w*` ou `hypersensibilité` | Taux de faux positifs sur requêtes non allergiques ; c'est ce flag qui déclenche l'alerte dans le prompt |
| Routeur : domaines | **Généraliser** : correspondance sur mots entiers et non sous-chaînes (`rac`, `usc`, `aod`) | Précision du domaine inféré sur un jeu étiqueté |
| Lexique : acronymes | **Corriger** : correspondance sensible à la casse pour les acronymes de 2 à 3 lettres, ou liste d'exclusion des mots français | « ne pas », « il ira »… : contamination du top-8 |
| Reranker | **Garder** ; épingler sentence-transformers ou passer `activation_fn` ; reranker la requête *non étendue* | Comparer requête étendue et originale pour le CE |
| Mélange CE/a priori 0.68/0.32 | **Simplifier** : CE seul, ou a priori faible | Ablation : CE seul contre mélange |
| CRAG facettes (`FACET_RULES`) | **Généraliser ou supprimer** : sous-requête = requête + modificateur, sans identifiant ni molécule codés en dur | Ablation isolée `use_crag_multihop` sur un jeu multi-RFE (inerte sur les 4 requêtes testées ici) |
| Sous-requêtes QCM et composites | **Simplifier** : options A à E, détection de médicaments non limitée aux antibiotiques, garder la séparation composite seulement sur « associée à » | Ablation sur QCM hors antibioprophylaxie |
| Injection 6b et rescue CRAG | **Simplifier** : respecter `final_top_k` (plafond global), trier la sortie | Vérifier `len(retrieve()) <= final_top_k + budget d'expansion déclaré` |
| Expansion voisins et notes (`_expand_context`) | **Garder** (générique) | — |
| Expansion encadré allergie | **Généraliser** (relier tout encadré de section) ou supprimer | 29 chunks concernés ; mesurer hors antibioprophylaxie |
| `select_generation_context` | **Simplifier** : seuil relatif générique, retirer la logique d'encadré allergie | Ablation génération sur un jeu multi-RFE |
| Ordre en U | **Supprimer le doublon** ; ne l'appliquer qu'à une liste triée | Ablation génération (`use_u_shape_ordering`) seule |
| `prune_verbose_prose` | **Garder sous condition** | Ablation génération seule |
| `PgVectorStore` | **Supprimer du chemin « produit »** ou le relier vraiment ; corriger l'`ORDER BY` | — |
| `benchmark_adapter.py:98` | **Corriger le flag** et aligner sur `engine.answer` | Écart de score entre l'adaptateur et l'API sur les mêmes questions |
| Protocole d'ablation | **Découper C7 → C8** en 5 étapes à une option chacune ; ajouter un jeu multi-RFE | Seule façon d'attribuer les gains annoncés |
