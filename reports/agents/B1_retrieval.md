# B1 — Retrieval : viser 100 % des preuves dans le contexte

Date : 2026-11-27. Agent B1 (Opus). Périmètre : `src/rag_sfar/retrieval/*`, `src/rag_sfar/config.py`, `src/rag_sfar/evaluation/ablation.py` (config `C10_context_population`), tests `tests/test_b1_retrieval.py`. Split **dev uniquement** (aucun test évalué). Retrieval seul, mesuré sur tout le contexte retourné (équivalent `--k 64`). Index principal des mesures : `index/tas_v3_errata` ; reprise finale sur `index/tas_v4` (B2) en §0.2.

Commits : `482a678` (fonctions de retrieval, toutes désactivées par défaut : C9 inchangé), `2a5525b` (config C10). `pytest -q` : 113 verts ; `tests/test_no_benchmark_leakage.py` muet.

## 0. Avant / après

### 0.1 Index `tas_v3_errata` (toutes les ablations ont été faites sur cet index)

| Config | abpe171 suffisance | abpe171 rappel des preuves | abp171 passage dans le contexte | multirfe_synth passage dans le contexte | Contexte moyen (car.) | Chunks moyens | Latence médiane (ms)* | Contexte max (car.) |
|---|---|---|---|---|---:|---:|---:|---:|
| C9 | 83,3 [76–91] | 89,7 [84–94] | 94,1 [89–98] | 85,5 [78–93] | 5 663 | 7,9 | 219 | 10 636 |
| C9 + fenêtres | 88,5 [82–95] | 92,8 [88–97] | 99,0 [97–100] | 100,0 [100–100] | 17 021 | 24,6 | 290 | 29 967 |
| **C10** | **99,0 [97–100]** | **99,5 [98–100]** | **100,0 [100–100]** | 98,7 [96–100] | 20 139 | 32,3 | 478 | 29 996 |

IC bootstrap 95 % (2 000 tirages). n = 96 questions avec ensemble de preuves (abpe171), 102 (abp171), 76 avec passage gold (multirfe_synth, sur 94). Contexte et latence : moyenne / médiane sur les trois jeux.
\* Latences mesurées sur une machine partagée (construction d'index de B2 et évaluations MLX d'un autre agent en parallèle) : ordres de grandeur seulement ; voir §7 (« Latence mesurée seule ») : C9 + fenêtres 186 ms, C10 314 ms en médiane.

Différences appariées C10 − (C9 + fenêtres) : abpe171 suffisance **+10,4 pts [+4,2 ; +16,7]** (10 questions gagnées, 0 perdue), rappel des preuves +6,7 [+2,7 ; +11,3] ; abp171 +1,0 [0 ; +2,9] (Q74 gagnée) ; multirfe −1,3 [−3,9 ; 0] (MR-ga95d perdue, cause §9 : annotation). Contexte +3 100 caractères (+18 %).

Ventilation abpe171 (suffisance, C9 → C9 + fenêtres → C10) : pédiatrique 44 → 67 → **100** (n = 9) ; adulte 92 → 94 → 100 (n = 49) ; population non précisée 69 → 85 → 100 (n = 13) ; adulte et pédiatrique 88 → 88 → 96 (n = 25) ; TABLE 80 → 86 → 100 (n = 35) ; NEGATION 87 → 90 → 97 (n = 31). Effectifs faibles.

Remarque : le « plafond de mapping » de A1 (97,9 %, mesuré sur l'ancien index) est dépassé (99,0 %) car le mapping sur `tas_v3_errata` couvre une question de plus ; la seule question restante (Q120) est non mappable (§9).

### 0.2 Index `tas_v4` (B2)

Mêmes configurations, sans aucun réglage sur `tas_v4` (C10 a été figé sur `tas_v3_errata` avant la première mesure sur `tas_v4`).

**Chiffres provisoires** : une revue indépendante a trouvé dans `tas_v4` des étiquettes `populations` fausses (~700 chunks de documents adultes étiquetés néonatal + pédiatrique, étiquettes obstétricales issues de titres énumérés) et des tableaux aplatis ; B2 corrige dans `tas_v5`. Sur `tas_v4`, la garantie de population de C10 lit `populations` en priorité : les gains Q07/Q44/Q131 sur cet index sont donc à remesurer sur `tas_v5`. Par construction, une étiquette fausse ou absente ne peut qu'**ajouter** des candidats : les résultats classés sans quota restent en tête, dans le même ordre (test `test_population_quota_only_adds_and_survives_wrong_labels`) ; le pire cas est un passage inutile de plus dans le contexte.


| Config | abpe171 suffisance | abpe171 rappel des preuves | abp171 passage dans le contexte | multirfe_synth passage dans le contexte | Contexte moyen (car.) | Chunks moyens | Latence médiane (ms)* | Contexte max (car.) |
|---|---|---|---|---|---:|---:|---:|---:|
| C9 | 90,6 [84–96] | 93,8 [89–98] | 97,1 [93–100] | 84,2 [76–92] | 6 333 | 7,9 | 457 | 12 937 |
| C9 + fenêtres | 93,8 [89–98] | 95,9 [92–99] | 100,0 [100–100] | 97,4 [93–100] | 18 909 | 24,6 | 294 | 28 725 |
| **C10** | **99,0 [97–100]** | **99,8 [99–100]** | **100,0 [100–100]** | 97,4 [93–100] | 23 075 | 32,3 | 954 | 29 990 |

C10 − (C9 + fenêtres), appariés : abpe171 suffisance **+5,2 [+1,0 ; +9,4]** (Q05, Q07, Q41, Q44, Q131 gagnées, 0 perdue), rappel des preuves +3,9 [+1,0 ; +7,4] ; abp171 0 ; multirfe 0 [0 ; 0] (mêmes deux échecs). Contexte +4 200 caractères (`tas_v4` a plus de fiches ligne et de notes liées : les fenêtres et les notes ramènent davantage). La latence médiane mesurée pendant cette série (954 ms) est gonflée par la charge de la machine ; mesure isolée en §7 (« Latence mesurée seule »).

Échecs restants sur `tas_v4` (C10) :

| Jeu | Question | Ce qui manque | Cause | Relève de |
|---|---|---|---|---|
| abpe171 | Q171 (QCM ORL, 6 preuves dans 4 tableaux) | ligne pédiatrique « Pose d'implants cochléaires » (p. 96) | les 2 passages garantis pour l'option D sont d'autres lignes (adulte et tableau parent) ; la ligne pédiatrique n'est pas dans le top 2 de la sous-requête | retrieval (classement ; quota par option) |
| multirfe | MR-g8f23 | passage gold en syntaxe Mermaid | la forme du chunk a changé dans `tas_v4` (B2) : la citation ne peut plus correspondre | annotation (passage gold à réannoter) |
| multirfe | MR-gcb72 (fluoroquinolones en réanimation) | paragraphe gold (RFE antibiotiques en réanimation) | rang dense 21, rang BM25 445 : hors des 24 candidats reclassés alors que son score cross-encoder (0,37) dépasse celui du premier résultat (0,33) ; tout le top 5 est hors sujet. Cause générique : un passage vu par un seul canal n'atteint pas le reclassement. `rerank_top_k=48` le récupérerait mais a coûté une autre question sur `tas_v3_errata` (§7) | retrieval (profondeur de reclassement) |

Q120 (échec sur `tas_v3_errata`) passe sur `tas_v4` : le libellé de sous-catégorie est désormais dans le texte des fiches (B2). MR-ga95d passe aussi sur `tas_v4`.

## 1. Ce que contient C10

`C10_context_population` = C9 (BM25 + e5-small + RRF + cross-encoder mmarco + filtre d'édition + routeur) avec :

| Élément | Champ | Pourquoi (structure générale) |
|---|---|---|
| 16 résultats classés, ±1 voisin et tableau parent pour les 8 premiers | `final_top_k=16`, `context_window=1`, `expand_table_parent=True` | « fenêtres » de A1 ; voisins de prose indispensables hors ABP (§5) |
| Pas de plafond par document sous le budget | `max_chunks_per_doc=16` (au lieu de 7) | une question porte en général sur **une** RFE : le plafond 7 remplissait les places 8–16 avec des documents hors sujet |
| Notes des tableaux retrouvés | `attach_table_notes=True` | notes de périmètre (« Les posologies de ce tableau concernent… ») et appels de note (*, **, #) liés aux lignes à l'ingestion, plus le bloc de notes imprimé sous le tableau |
| Équilibre de population | `population_quota=1`, `population_counterpart=True` | les RFE ont des tableaux adulte et pédiatrique parallèles ; quand la question n'exclut pas une population, une recherche restreinte à cette population (métadonnées, documents des 3 premiers résultats, chunks de tableau) garantit un passage ; la requête est complétée par le libellé de la ligne de l'autre population déjà retrouvée (« contrepartie ») |
| QCM : une recherche par option | `mcq_option_quota=2` | format « A. … B. … » détecté ; chaque option (énoncé + option) garde 2 passages (version adulte et pédiatrique d'une même ligne) |
| Signal de couverture | champs `coverage_*` | exposé, ne filtre rien (§8) |

Tout le reste de C9 est inchangé. Les nouveaux champs de `RetrievalConfig` sont désactivés par défaut : `RetrievalConfig()`, l'API, le MCP, l'adaptateur et la CLI se comportent comme avant.

## 2. Piste 1 — QCM et questions composites

Hypothèse : les options « distractrices » polluent la requête ; une recherche par option apporte la preuve de chaque option.
Implémentation : `query_tools.split_mcq` (lettres consécutives à partir de A, ≥ 2 options) ; `_guaranteed_extras` lance `_focused_search(énoncé + option)` (BM25 + dense + RRF + cross-encoder sur 16 candidats) et garantit `mcq_option_quota` passages par option (ceux déjà présents comptent).

| Variante (base) | abpe171 suff. | abp171 | multirfe | Contexte | Décision |
|---|---|---|---|---|---|
| quota 1, énoncé + option (C9 + fenêtres + notes) | +0,0 | +0,0 | +0,0 | +0,2 k | — |
| quota 1 + requête principale = énoncé seul (`mcq_stem_only`) | −1,0 (Q158) | −1,0 (Q158) | 0 | +0,8 k | rejeté : retirer les options fait perdre l'information portée par elles |
| quota 2, énoncé + option (sur C10 sans QCM) | **+1,0** [0 ; +3,1] (Q171) | 0 | n/a | +0,3 k | **gardé** |
| quota 2, option seule (`mcq_option_with_stem=False`) | +1,0 (Q171) | 0 | n/a | +1,3 k | rejeté (même gain, plus long) |

Conclusion : l'effet est réel mais repose sur **une** question (Q171, 6 preuves dans 4 tableaux adulte + pédiatrique). multirfe n'a pas de QCM. Les questions composites « X associée à Y » (code CRAG existant) n'ont pas été remesurées : aucune en dev.

## 3. Piste 2 — Population

Hypothèse : quand la question affirme une population, il faut des passages de cette population ; quand elle n'en affirme aucune, il faut les deux (les ensembles de preuves des experts exigent souvent la variante pédiatrique pour une question sans âge).

| Variante (base C9 + fenêtres + notes, plafond 7) | abpe171 suff. | abp171 | multirfe | Contexte | Latence |
|---|---|---|---|---|---|
| quota 1, requête = question | +1,0 [0 ; +3,1] (Q44) | 0 | 0 | +1,0 k | +270 ms |
| quota 1 + contrepartie | **+3,1 [0 ; +7,3]** (Q07, Q44, Q131) | 0 | 0 | +1,5 k | +300 ms |
| quota 1 + contrepartie, sur base plafond 16 | **+3,1 [0 ; +7,3]** (Q07, Q28, Q44) | 0 | 0 | +1,3 k | |

Pourquoi la contrepartie : la ligne pédiatrique emploie souvent un autre libellé que la question (« arthrodèse lombaire instrumentée » → « chirurgie du rachis avec mise en place de matériel ») alors que la ligne adulte, déjà retrouvée, porte ce libellé. Règle structurelle (tableaux parallèles), aucune liste de termes. Décision : **gardé**.
Métadonnées : sur `tas_v3_errata`, `population_hint` est bruité (les pages d'auteurs du Champ 1 de l'ABP sont « pédiatrie ») ; la restriction aux chunks de tableau (`population_tables_only=True`) le compense. Sur `tas_v4`, le code lit d'abord `Chunk.populations` (structurel, B2) quand il existe (`_chunk_population`).

## 4. Piste 3 — Contexte nié

Implémentation générique (`query_tools.patient_negated_spans`) : une négation est « d'arrière-plan » seulement si elle suit **directement** la description du patient (« chez un adulte sans X ni Y », « enfant de 8 ans, 25 kg, sans X ») ; portée = la négation et son groupe nominal (≤ 6 mots, arrêt sur ponctuation, « ni », verbe/participe), coupée avant tout terme d'état affirmé (« non diabétique allergique à X » garde « allergique à X », règle NegEx du routeur). Les lignes d'options de QCM ne sont jamais touchées, ni les négations qui définissent l'acte (« sans prothèse », « sans mise en place de matériel »). Deux usages : poids réduit dans BM25 (`negated_term_weight`), retrait de la requête dense + cross-encoder (`negation_strip_semantic`). La question posée au générateur n'est jamais modifiée.

| Variante (base C9 + fenêtres + notes) | abpe171 | abp171 | multirfe | Décision |
|---|---|---|---|---|
| poids lexical 0,2 | 0 | 0 | 0 | rejeté (sans effet) |
| retrait sémantique | +1,0 [0 ; +3,1] (Q149) | 0 | 0 | gain annulé par le plafond 16 (Q149 déjà gagnée) : **non gardé** (simplicité) |

Seules 8 questions dev ont une négation attachée au patient (Q42, Q149, Q158, Q166 n'en a pas après exclusion des options ; 4 multirfe). Risque relevé : hors ABP, la négation porte souvent la condition même de la recommandation (« sans antécédent hémorragique » → pas de bilan d'hémostase) ; la retirer pourrait nuire. Le code reste disponible, désactivé.

## 5. Piste 4 — Notes de tableau

`_table_notes` : pour chaque chunk de tableau parmi les 8 premiers résultats, (a) les `callout_footnote` liés à l'ingestion (`linked_callout_ids`, médiane 246 car., max 890 ; 59 documents en ont), (b) jusqu'à 2 paragraphes qui suivent le tableau et commencent par un appel de note (`*`, `\*`, `#`, `†`, pas le gras Markdown). Les encadrés allergie n'en font pas partie.

| Base | abpe171 suff. | abp171 | multirfe | Contexte |
|---|---|---|---|---|
| C9 → C9 + notes | 83,3 → 86,5 (+3,1 [0 ; +7,3] ; Q05, Q157, Q158) | 0 | 0 | +1,8 k |
| C9 + fenêtres → + notes | 88,5 → 90,6 (+2,1 [0 ; +5,2] ; Q05, Q157) | 0 | 0 | +1,5 k |

Décision : **gardé** (aucune perte, structure générique des tableaux RFE).

## 6. Piste 5 — Fenêtres de contexte et budget

Courbe sur la base « C10 sans QCM » (fenêtres + notes + population, plafond = k) :

| Variante | abpe171 suff. | abp171 | multirfe | Contexte moyen |
|---|---|---|---|---|
| k = 8 | 94,8 (−3,1) | 100 | 94,7 (−3,9) | 15,5–16,5 k |
| k = 12 | 95,8 (−2,1) | 100 | 94,7 (−3,9) | 17,2–19,0 k |
| **k = 16** | **97,9** | **100** | **98,7** | 19,0–21,6 k |
| k = 20 | 97,9 | 100 | 100 (+1,3 ; MR-ga95d) | 20,9–24,0 k |
| k = 16, fenêtres sur les 16 premiers | 97,9 | 100 | 98,7 | 26,8–27,6 k |
| k = 16, ±2 voisins | 97,9 | 100 | 98,7 | 23,6–26,6 k |

Sur la base C9 + fenêtres : voisins seulement autour des tableaux → multirfe −2,6 (2 pertes), abp −1 ; sans voisins (tableau parent seul) → abpe −3,1, multirfe −2,6 ; k = 16 sans fenêtres → abpe −4,2, abp −4,9, multirfe −7,9 ; k = 12 avec fenêtres → multirfe −2,6.
Décision : **k = 16, ±1 voisin, tableau parent, fenêtres sur les 8 premiers** = plus petit contexte qui garde le maximum. k = 20 récupère MR-ga95d pour +2,4 k caractères : non retenu (passage gold douteux, §9). Le contexte reste sous ~25 k en moyenne, plafonné à 30 k (`context_char_budget`).
Ordre de lecture : `context_order="document"` (regroupement par document, ordre du texte) est implémenté mais n'a **aucun effet** sur ces métriques (calculées sur tout le contexte) ; à mesurer en génération (B3). La déduplication existante (`dedup_by_content`) n'a pas été modifiée. « Section complète pour les petites sections » : non implémenté (les ±1 voisins couvrent déjà les petites sections ; ±2 n'apporte rien).

## 7. Piste 6 — Profondeur et classement

| Variante (base C9 + fenêtres + notes) | abpe171 | abp171 | multirfe | Contexte | Latence | Décision |
|---|---|---|---|---|---|---|
| `max_chunks_per_doc` 7 → 16 | **+4,2 [+1,0 ; +8,3]** (Q41, Q74, Q131, Q149) | +1,0 (Q74) | −1,3 (MR-ga95d) | +0,6 k | = | **gardé** |
| `max_chunks_per_doc` 12 (sur C10) | −1,0 vs 16 | 0 | 0 | | | rejeté |
| `rerank_top_k` 24 → 48 | +1,0 (Q44) | 0 | −1,3 (MR-gb887) | +2,9 k | +150 ms | rejeté |
| `initial_candidates` 100 + `rerank_top_k` 48 | +1,0 (Q44) | 0 | −1,3 | +2,7 k | +475 ms | rejeté |
| filtre d'édition désactivé | +3,1 (artefact : la V3.0 obtient 7 places de plus sous le plafond 7) | −1,0 | −2,6 | +2,6 k | | **rejeté** (sécurité : éditions remplacées dans le contexte) |
| lexique d'acronymes (sur C10) | 0 | −1,0 (Q171) | 0 | | | rejeté |
| `BAAI/bge-reranker-v2-m3` à la place de mmarco (sur C10, y compris sous-requêtes) | −1,0 [−3,1 ; 0] (Q149 perdue) | n.m. | 0 | +0,3 k | ×4 à ×9 (médiane 1,8–3,9 s en charge) | **rejeté** |

Le reranker `bge-reranker-v2-m3` (568 M paramètres) a été mesuré sur C10 : aucun gain, une perte, latence multipliée ; mmarco reste. Le gain du plafond par document est structurel : sur une question d'une RFE donnée, les places 8–16 allaient à d'autres documents (ex. tableaux de risque hémorragique ORL avec un score cross-encoder < 0,01). Poids/k de la RRF : non balayés (C9 utilise les poids par défaut ; les gains restants ne dépendaient pas de la fusion, toutes les preuves manquantes étaient déjà dans les candidats).

### Latence mesurée seule (verrou GPU, `tas_v4`, 40 questions dev : 20 abpe171 + 20 multirfe, après préchauffage)

| Reranker | C9 | C9 + fenêtres | C10 |
|---|---|---|---|
| mmarco (retenu) | 187 ms (p90 197) | 186 ms (p90 195) | **314 ms (p90 455)** |
| bge-reranker-v2-m3 | 1 757 ms (p90 1 803) | 1 657 ms (p90 1 730) | 2 765 ms (p90 3 918) |

Le surcoût de C10 (+130 ms médiane) vient des recherches ciblées (une par population non exclue, une par option de QCM), chacune avec 16 paires cross-encoder.

## 8. Piste 8 — Signal de couverture (abstention côté retrieval)

Exposé dans le dictionnaire `timings` renvoyé par `retrieve()` (rétrocompatible, valeurs `float`, `-1.0` = non disponible) et dans `retriever.last_coverage` : `coverage_score` (meilleur score cross-encoder de la requête principale), `coverage_supported` (1.0 si ≥ `coverage_threshold`, défaut 0,2), `channel_agreement` (part du top 10 BM25 dans le top 10 dense), `dense_top_score`. **Aucun filtrage.**

Calibration (dev, config C10 sans QCM) : positifs = 280 questions couvertes des trois jeux ; négatifs = 30 requêtes hors domaine écrites pour l'occasion (`reports/agents/B1_annexes/ood_queries.txt`) et 18 questions `abstention` de multirfe (anesthésie, non couvertes par le corpus).

| Règle « non couvert » | Couvertes signalées à tort | Hors domaine détectées | Abstentions multirfe détectées |
|---|---|---|---|
| CE < 0,05 | 2 / 280 (0,7 %) | 24 / 30 | 4 / 18 |
| **CE < 0,2 (seuil retenu)** | **2 / 280 (0,7 %)** | **28 / 30 (93 %)** | 9 / 18 (50 %) |
| CE < 0,3 | 4 / 280 | 30 / 30 | 11 / 18 |
| CE < 0,5 | 13 / 280 | 30 / 30 | 16 / 18 |
| CE < 0,2 ou dense < 0,86 | 2 / 280 | 29 / 30 | 9 / 18 |
| accord des canaux < 0,1 | 26 / 280 | 17 / 30 | 9 / 18 |

Lecture : le signal sépare bien le **hors domaine** ; il ne sépare pas les questions d'anesthésie non couvertes (le corpus contient toujours un passage voisin). Les deux faux « non couvert » sont Q28 (0,005) et Q52 (0,04), questions pédiatriques ABP pour lesquelles mmarco note mal le bon tableau. D'où un seuil prudent (0,2) et un usage indicatif : le générateur doit garder sa propre règle d'abstention. Le seuil dense (0,86) dépend du modèle d'embedding ; il n'est pas utilisé par `coverage_supported`.

## 9. Piste 7 — Requêtes

- Requêtes multiples déterministes : la « contrepartie de population » (§3) et les sous-requêtes d'options (§2) sont les deux formes gardées. « Acte seul » (retrait des descripteurs du patient) n'a pas été testé séparément ; le retrait de la négation (§4) en est un cas particulier, sans gain sur C10.
- Acronymes : lexique (`use_medical_lexicon`) −1 sur abp171 : rejeté (cohérent avec l'ablation C9).
- Repli lexical quand le dense échoue : déjà assuré par la RRF (BM25 + dense) et la garantie top-2 par canal ; pas de variante supplémentaire.
- Pas de LLM dans la boucle.

## 10. Piste 9 — Échecs restants (C10, `tas_v3_errata`)

| Jeu | Question | Ce qui manque | Cause | Relève de |
|---|---|---|---|---|
| abpe171 | Q120 | preuve p. 41 (tableau ORL adulte « Chirurgie amygdalienne et adénoïdectomie ») | le tableau est **dans le contexte** (`Col 1 | Col 2 | Col 3`, « Amygdalectomie ; Adénoïdectomie | PAS D'ANTIBIOPROPHYLAXIE ») mais le libellé de sous-catégorie n'existe que dans le titre (`section_path`) : fragment non mappable | ingestion (libellé de sous-catégorie à porter dans le texte ; corrigé par B2 dans `tas_v4`) / mapping |
| multirfe | MR-ga95d (nourrisson, bilan d'hémostase) | passage gold « Les services de laboratoire et de radiologie doivent pouvoir répondre… » (organisation des soins pédiatriques) | le contexte contient la recommandation qui répond (« Il est recommandé d'évaluer le risque hémorragique d'après l'anamnèse… », RFE examens préopératoires) ; le passage gold est faiblement lié à la question et ne revient qu'avec k = 20 | annotation (passage gold synthétique discutable) |

Questions corrigées par C10 et cause d'origine : Q05 (note de périmètre pédiatrique → notes), Q157 (note « IMC ≤ 50 » → notes), Q07 / Q44 / Q28 (ligne pédiatrique absente → population + contrepartie), Q41 / Q74 / Q131 / Q149 (bonne ligne au-delà de la 7e place du même document → plafond 16), Q171 (QCM sur 4 tableaux → quota par option). abp171 : Q74 (plafond).

## 11. Ce que j'attends de l'ingestion (B2)

1. Libellés de sous-catégorie et lignes `colspan` pleine largeur **dans le texte** des fiches ligne (Q120, Q05/Q163 p. 76) ; en-têtes réels au lieu de `Col N`. (Annoncé fait dans `tas_v4`.)
2. `populations` structurel par chunk (tableau > section > document), pour remplacer `population_hint` bruité ; `table_id` commun aux fiches et au tableau parent (remplacerait la remontée par `prev_chunk_id`).
3. Notes : chaque appel de note (*, **, #) d'une ligne relié au chunk de note correspondant, et les paragraphes de notes trop longs (> 900 car., classés `prose`) découpés en une note par appel.
4. Un identifiant de « ligne d'acte » commun aux versions adulte et pédiatrique (même acte, deux tableaux) : la contrepartie (§3) passerait d'une recherche à une jointure.

## 12. Risques de surapprentissage dans mes choix

- **abpe171 dev a guidé le diagnostic** : j'ai lu les 11 échecs puis conçu notes, population et plafond. Chaque règle est structurelle (tableaux, notes, populations parallèles, format QCM) et aucune ne contient de terme d'acte, de molécule ou de question ; mais l'effet n'est démontré que sur ABP : multirfe est saturé avec les fenêtres (100 %) et ne peut que détecter des pertes, abp171 est le même document qu'abpe171.
- **QCM quota 2** : choisi après avoir examiné Q171 (une seule question gagnée). Le quota 2 a une justification structurelle (adulte + pédiatrique), mais c'est le choix le plus fragile ; à vérifier sur le test scellé et sur d'autres QCM.
- **Plafond par document 16** : favorise la RFE dominante ; une question qui croise deux RFE peut perdre des passages du second document (une perte multirfe, jugée d'annotation, va dans ce sens). La garantie top-2 par canal et le quota population en limitent l'effet.
- **Contrepartie de population** : suppose des tableaux adulte/pédiatrique parallèles dans la même RFE ; sans effet ailleurs (aucune perte multirfe), utile seulement là où cette structure existe.
- Le seuil de couverture est calibré sur 48 négatifs dont 30 écrits par moi : estimation grossière.
- Les mesures du jeu multirfe portent sur des questions synthétiques non validées médicalement.

## 13. Reproduction

Pilote d'évaluation (scratchpad de session, copie dans `reports/agents/B1_annexes/`) : `b1eval.py` charge l'index une fois et appelle `harness.retrieval_metrics` sur tout le contexte ; `cmp.py` (différences appariées, `harness.paired_bootstrap_diff`) ; `coverage.py`. Équivalent CLI :

```bash
HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-eval --suite abpe171 --split dev --configs C9,C10 --retrieval-only --k 64 \
    --index-map table_aware_sota=tas_v3_errata --tag b1_c10
```
