# Audit de code — ingestion, génération, interfaces, CLI, scripts, tests

Audit en lecture seule, réalisé le 26/11/2026 sur le commit `943e0cd`, avec le venv `.venv` et `HF_HUB_OFFLINE=1`. Aucun fichier du dépôt n'a été modifié. Aucun index n'a été reconstruit et aucun appel API n'a été fait.

Périmètre : `src/rag_sfar/ingestion/`, `src/rag_sfar/generation/`, `src/rag_sfar/interfaces/`, `cli.py`, `schemas.py`, l'adaptateur `evaluation/benchmark_adapter.py::SfarRagApproach`, `scripts/*.py` (sauf `build_masterclass_pdf.py`) et `tests/`. Le dossier `retrieval/` et l'intégrité de l'évaluation sont audités par d'autres agents. Je ne cite ces parties que lorsqu'elles touchent directement mon périmètre.

---

## 1. Conclusions

### Critique

1. **Les prompts « benchmark » contiennent des indices tirés de questions précises du benchmark d'antibioprophylaxie, ce qui viole le principe n° 1 de CLAUDE.md.**
   - `prompts.py:28-36` (`SYSTEM_BENCHMARK_OPEN`) :
     - « PTH voie antérieure ou prothèse d'épaule » correspond à Q04 (réponse attendue : Vancomycine).
     - « si 2 actes chirurgicaux sont associés… retiens la molécule si au moins l'un… » correspond à Q15 et Q16.
     - L'exemple de réponse « Triméthoprime/Sulfaméthoxazole » est la réponse attendue de Q28.
   - `prompts.py:38-45` (`SYSTEM_BENCHMARK_MCQ`) :
     - « intervention SANS antibioprophylaxie » correspond à Q140, dont le titre est « Intervention sans ABP ».
     - « plaie de la main » vs « hors main » correspond à Q15 et Q143.
     - « genou » vs « hanche voie antérieure » correspond à Q139, Q141 et Q04.
   - Le chemin générique est contaminé aussi :
     - La réparation propose « réponds 'Pas d'antibioprophylaxie' » quel que soit le sujet (`client.py:347`).
     - Une alerte « Patient ALLERGIQUE aux bêtalactamines » est injectée dans le contexte (`client.py:280-286` et `436-442`), y compris en mode `clinical_detailed`.

2. **L'adaptateur `SfarRagApproach` est incompatible avec les scoreurs de la plateforme, et une partie du sourcing est fabriquée.**
   - **Sortie non extraite.** `build_prompt` demande une sortie sur 2 lignes (ANALYSE + RÉPONSE), mais la plateforme note la sortie brute :
     - `QCMScorer` retient la *première* lettre A-D isolée de la sortie. Une sortie verbeuse correcte est donc notée fausse (vérifié, §4.1).
     - `OpenScorer` fait une recherche de sous-chaîne. Une molécule citée dans la ligne ANALYSE est donc comptée juste, ce qui donne des faux positifs (vérifié).
   - **Mauvais paramètre.** `benchmark_adapter.py:98` passe `prune_prose=self._config.use_u_shape_ordering` au lieu de `use_context_pruning`.
   - **Classe non enregistrable.** `SfarRagApproach` n'hérite pas d'`ApproachPort` et ne peut pas être instanciée par `APPROACH_REGISTRY`, qui attend une classe sans argument.
   - **Sourcing ajouté artificiellement.** En modes benchmark, `client.py:372-379` ajoute « (SFAR <année> [S1]) » quand le LLM ne cite pas d'année. Le `SourcingScorer` (`\b\d{4}\b`) est donc satisfait par construction, et l'année ajoutée est celle de S1, pas forcément celle de la source réellement utilisée.

3. **Le vérificateur ne vérifie presque rien hors antibioprophylaxie et anticoagulants. Il ne doit pas être présenté comme un garde-fou clinique.**
   - **Liste fermée.** `verifier.py:11-81` contient une liste de 70 entrées, essentiellement des antibiotiques et des anticoagulants.
   - **Vérification par présence seulement.** Le contrôle porte sur la présence d'un mot n'importe où dans le contexte (`verifier.py:113-114`). Il ne vérifie ni l'association acte → molécule, ni la dose, ni les pluriels.
   - **Faux 100 %.** Le score de grounding vaut 1,0 pour « Propofol 2 mg/kg », « Kétamine », « HBPM », « Héparines » et même « Céfazoline 20 g » alors que la source dit 2 g (vérifié, §4.1).
   - **Contexte contrôlé ≠ contexte montré.** Le contrôle porte sur `indexed_text`, alors que le LLM a reçu un texte élagué par `prune_verbose_prose`.
   - L'interface affiche « Grounding: 100% » en vert (`api.py:232-233`).

### Important

4. **Le graphe de supersession des éditions est une liste curée de 25 règles regex, pas un mécanisme générique.**
   - **Règles nominatives.** Les règles de `loader.py:257-421` nomment des titres précis, par exemple `^recommandations\s+avk$` (`:266`).
   - **Couverture partielle.** 170 documents sur 264 n'ont aucune lignée et restent donc toujours « en vigueur ».
   - **Supersessions discutables, à faire valider par un clinicien :**
     - Le document HAS 2008 sur les surdosages en AVK est marqué remplacé par la RFE 2026 « procédure invasive programmée ».
     - La RFE 2011 « Prévention du risque allergique » est marquée remplacée par la RFE 2025 « Diagnostic et prise en charge des réactions d'hypersensibilité immédiate ».
   - **Mauvais document canonique.** La lignée nutrition 2026 a pour document canonique `Figures-RFE-Nutrition.pdf`.
   - **Identifiant instable.** Le `doc_id` contient l'année *inférée*. Tout changement de cette heuristique casse les `doc_id` exposés par MCP.

5. **L'imputation de domaines repose sur des sous-chaînes, ce qui produit beaucoup de faux positifs. Ces domaines sont ensuite injectés dans le texte indexé de chaque chunk.**
   - « rac » (`loader.py:233`) correspond à « fracture », « trachée » ou « pratique » : 59 documents sont étiquetés « Ambulatoire et Réhabilitation » par erreur.
   - Les autres cas sont « membre » (20), « neuro » (14), « usc » dans « muscle » (10) et « enfant » (9).
   - Au total, 114 documents ont au moins un domaine qui ne repose sur aucun mot entier.
   - Ces domaines sont écrits dans l'en-tête contextuel de *chaque* chunk (`chunker.py:123-130`), donc dans l'index BM25 et dans l'index dense.

6. **Le chunker `table_aware_sota` contient des règles codées pour la RFE d'antibioprophylaxie et se comporte mal ailleurs.**
   - **Règles propres à l'antibioprophylaxie :**
     - `ALLERGY_BOX_RE` (`chunker.py:37-43`) : les 29 chunks `callout_allergy` viennent tous de la RFE ABP 2026.
     - `ANTIBIOPROPHYLAXIE EN` (`:416`).
     - « actes chirurgicaux » et « nomenclature » (`:461-463`).
     - Côté tableaux : `table_parser.py:357-370` (« pas d'antibioprophylaxie »), `:223` (amoxicilline, céfazoline, IVL) et `:403` (nomenclature).
   - **Faux encadrés.** La regex de note de bas de page `^\s*[\*#…]` (`chunker.py:581`) capture le gras Markdown `**`. 1 551 des 1 883 `callout_footnote` sont du texte en gras. Ils sont liés comme « encadrés » à 15 168 chunks sur 32 591 (46,5 %).
   - **Perte de texte.** `_clean_cell_text` perd le texte hors `<li>` dans une cellule. Par exemple, « Si allergie : » disparaît (vérifié).
   - **Tableaux hors ABP.** 600 tableaux sans en-tête ne produisent pas de fiches de ligne.
   - **Chunks géants.** Des chunks de prose atteignent 21 454 caractères.

7. **Le modificateur « allergy » déclenche l'injection d'une alerte « allergie aux bêtalactamines » pour des questions qui n'en parlent pas.**
   - Le routeur l'active aussi pour « hypersensibilité », « intolérance » et « alternative » (`retrieval/router.py:45`).
   - Une question sur l'anaphylaxie aux curares ou sur une alternative thérapeutique quelconque reçoit donc « Ne donne PAS la molécule de 1re intention (bêtalactamine) ».
   - C'est un risque de sécurité clinique.

8. **Interfaces partagées : le contrat est fragile.**
   - **MCP :**
     - Le serveur répond à des notifications, alors que JSON-RPC l'interdit.
     - `ping` n'est pas implémenté.
     - Les erreurs de parsing sont avalées sans réponse `-32700`.
     - `protocolVersion` est figé.
   - **API OpenAI :**
     - `stream`, `temperature` et `max_tokens` sont ignorés.
     - `content` doit être une chaîne : le format « parts » en tableau est rejeté (422).
     - Aucune gestion d'erreur LLM : une panne remonte en HTTP 500.
   - **Valeur par défaut cassée.** `index_dir` vaut par défaut `index/sota_default` (`config.py:26`), dossier absent du dépôt. `rag-sfar-mcp` et `rag-sfar-serve` échouent sans la variable `RAG_SFAR_INDEX_DIR`, que je n'ai pas vérifiée car `.env` n'a pas été lu.

9. **Tests : les 19 tests passent en 3,3 s, mais ils couvrent surtout des cas d'exemple tirés de l'antibioprophylaxie.**
   - Le test anti-fuite exigé par CLAUDE.md (principe 3) est absent.
   - `SfarRagApproach`, les chunkers de référence, la supersession sur données synthétiques, l'API en mode benchmark, les erreurs LLM et MCP (hors cas nominal) ne sont pas testés.
   - Deux tests recopient des questions du benchmark : Q146 (`tests/test_rag_sfar.py:567`) et Q16 (`:582-585`).

### Mineur

10. **Dette de code.**
    - **Duplication :** `answer()` et `stream_answer()` dupliquent environ 120 lignes (`client.py:244-542`), avec deux prompts de réparation différents. La construction de `RetrievalConfig` est triplée dans `api.py`.
    - **Code mort :** la seconde regex de `clean_chandra_markdown` (`loader.py:447-451`) est entièrement couverte par la première. Le paramètre `header_context` de `to_markdown_chunks` n'est jamais passé.
    - **Champs jamais lus** hors ingestion : `reco_family_id`, `recommendation_ids`, `has_dosage_info`, `source_tabs`.
    - **Noms de fichiers en dur** dans `detect_language` (`loader.py:470` : `bja-2015`, `accpm-335`, etc.).

---

## 2. Méthode et commandes de vérification

- `HF_HUB_OFFLINE=1 .venv/bin/python -m pytest -q` : 19 tests passés en 3,26 s (le test sur le corpus réel n'est pas ignoré).
- Les scripts de vérification sont dans le dossier temporaire de session `/private/tmp/claude-501/-Users-tim--claude-spares-spare-xXtqK0/fdfce601-0588-4326-8d77-e9ea020e9a31/scratchpad/` (non versionné). Chacun s'exécute en moins de 10 s :
  - `lineages.py` : charge le corpus avec `load_sfar_corpus` et liste les lignées, les années et le statut `is_latest_edition`.
  - `dom.py` : mesure les faux positifs de l'imputation de domaines par sous-chaîne.
  - `idx.py` : lit `index/table_aware_sota/metadata.sqlite` en mode `?mode=ro` pour les tailles de chunks, la nature des `callout_footnote` et les liens d'encadrés.
  - `tables.py` : rejoue `_chunk_table_aware_sota` sur les 264 documents (7,4 s) en interceptant `parse_html_table` pour compter les tableaux avec en-tête, avec en-tête hérité et sans en-tête.
  - `checks.py` : reproductions unitaires (cellule `<li>`, vérificateur, scoreurs, langue, année, domaines, prose longue).
  - `mcp.py` : sonde JSON-RPC du serveur MCP.
  - `leak.py` : recherche des 9-grammes des questions et choix du benchmark dans `src/`, `tests/` et `scripts/`.
- Le recoupement des indices des prompts avec `data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json` a été fait en Python (171 questions : 138 ouvertes, 33 QCM).

---

## 3. Analyse par fichier

### 3.1 `ingestion/loader.py` (852 lignes)

**Graphe de supersession (`LINEAGE_RULES`, `:257-421` ; `_apply_temporal_supersession`, `:817-852`)**

- **Mécanisme.** Il y a 25 lignées définies à la main par des regex sur titre + nom de fichier. Dans chaque lignée, l'édition française de l'année maximale est la référence, et toute édition antérieure *ou non datée* est marquée `is_latest_edition=False` (`:844`).
- **Ce n'est pas générique.** 94 documents sont rattachés à une lignée, 170 ne le sont pas et ne seront jamais remplacés. Une nouvelle édition SFAR d'un thème non listé exige d'ajouter une règle.
- **Certaines règles sont nominatives :**
  - `r"^recommandations\s+avk$"` (`:266`) ;
  - `r"^intubation\s+difficile$"` (`:283`) ;
  - `r"^agents\s+antiplaquettaires\s+et\s+p[ée]riode\s+p[ée]riop[ée]ratoire$"` (`:380`).
- **D'autres sont trop larges.** `("antibioprophylaxie", [r"antibioprophylaxie"], [])` (`:259`) absorberait toute future recommandation d'antibioprophylaxie spécialisée, par exemple en obstétrique ou en pédiatrie, et la ferait remplacer par la RFE générale.
- **Résultats discutables observés sur le corpus réel (`lineages.py`) :**
  - `anticoagulants_procedure_programmee` : « Recommandations AVK » (HAS 2008, `2_HAS_Prise-en-charge-des-surdosages-en-antivitamines-K.pdf`) est marquée remplacée par la RFE 2026 « procédure invasive programmée ». Le périmètre (surdosage AVK, en partie en urgence) n'est pas le même.
  - `hypersensibilite_allergie_perioperatoire` : la RFE 2011 « Prévention du risque allergique peranesthésique » est remplacée par la RFE 2025 « Diagnostic et prise en charge des réactions d'HSI ». Le périmètre est partiellement différent, à valider par un clinicien.
  - `nutrition_clinique_adulte` : le document canonique est `Figures-RFE-Nutrition.pdf`. `classify_doc_role` classe « Version-longue » en argumentaire et « Version-courte » en texte court, et le tri `(role != "recommandation", -char_count)` (`:836-839`) retient le seul document « recommandation », qui est le PDF de figures. `superseded_by` pointe donc vers un PDF de figures.
- **Deux éditions de la même année ne sont pas départagées.** La comparaison se fait sur l'année seule, `version_label` est ignoré : deux versions V2 et V3 d'une même année seraient toutes deux « en vigueur ».
- **Supersession figée dans l'index.** L'étiquette « [ÉDITION ANTÉRIEURE — REMPLACÉE EN …] » est écrite dans `indexed_text` (`chunker.py:127`). Corriger une lignée impose de réindexer.

**Année effective (`infer_effective_year_and_version`, `:494-547`)**

- **Règle « 2026 » (`:517-519`).** `if "juin-2026" in fn_low or "2026" in fn_low` (la première condition est redondante) force l'année 2026 pour tout fichier dont le nom contient « 2026 ». Vérifié : `RFE-2019-mise-en-ligne-2026.pdf` avec `raw_year=2019` donne `(2026, 'Mise à jour 2026')`. Cela vaut aussi pour 2027 et au-delà : la règle n'est pas pérenne.
- **Règle préfixe d'année + « afar » (`:521-526`).** D'après la docstring (`:501`), elle vise un seul fichier : `2013 AFAR GIHP.pdf`.
- **Ce qui est générique.** La détection `V\d+\.\d+ du jj/mm/aaaa` (`:509`) et l'imputation depuis le nom de fichier, puis l'en-tête.
- **Fragilité.** La valeur la plus fréquente parmi les années de l'en-tête (`:543-545`) peut être l'année d'une référence bibliographique.

**Domaines (`DOMAIN_KEYWORDS`, `:27-252` ; `normalize_and_impute_domains`, `:562-588`)**

- **Mécanisme.** Test `kw in search_blob` sur titre + 1 500 premiers caractères, sans limite de mot (`:579`). L'enrichissement est appliqué *toujours*, même quand `raw_subdomain` existe déjà (`:574-585`).
- **Faux positifs mesurés (`dom.py`).** Domaine attribué uniquement via une sous-chaîne qui n'est pas un mot entier :

  | Mot-clé | Domaine attribué | Documents |
  |---|---|---:|
  | « rac » | Ambulatoire et Réhabilitation | 59 |
  | « membre » | Traumatologie | 20 |
  | « neuro » | Neuro-Réanimation | 14 |
  | « usc » | Organisation et Professionnel | 10 |
  | « enfant » | Pédiatrie | 9 |
  | « alr » | ALR et Douleur | 2 |

  Total : 114 documents. Exemple vérifié : `normalize_and_impute_domains(None, "Prise en charge de la fracture de l'extrémité supérieure du fémur", "pratique clinique")` donne `['Traumatologie', 'Ambulatoire et Réhabilitation']`.
- **Conséquences :**
  - La RFE ABP 2026 reçoit 6 domaines, dont Neuro-Réanimation, Obstétrique et Ambulatoire.
  - Le domaine « Général » n'est jamais utilisé.
  - Les domaines sont concaténés dans l'en-tête de chaque chunk, puis indexés en BM25 et en dense, et alimentent le filtre `domains` de l'API et de MCP.
- **Termes de molécules dans la liste.** Céfazoline, céfuroxime, etc. (`:50-61`) ne servent à rien pour classer les autres RFE.

**Langue (`detect_language`, `:463-491`)**

- **Points positifs.** L'échantillonnage du corps du document (20 à 80 %) et le comptage de mots-outils sont génériques et raisonnables.
- **Noms de fichiers en dur (`:470`).** La liste contient des préfixes génériques (`management-of-`, `-in-surgery-`) et des fichiers précis (`bja-2015`, `accpm-335`, `chest-trauma-`, `severe-pelvic-`, `eye-protection-`, `hospital-acquired-`). Ce filtre court-circuite le contenu. Vérifié : un texte 100 % français nommé `management-of-xyz-fr.pdf` est détecté `en`.
- **Effet de la catégorie « bilingual ».** 25 documents sont étiquetés `bilingual`, dont la RFE ABP 2026. Ils ne sont pas exclus, mais leur traitement en aval dépend du module retrieval.

**Rôle et populations (`:591-648`)**

- `classify_doc_role` : `"short"` (`:606`) est une sous-chaîne qui matche n'importe quel nom de fichier la contenant.
- `infer_population_scope` : le commentaire `:622` (« V3.0 antibioprophylaxie added pediatric Champ 3 ») montre une règle écrite pour un seul document. La RFE ABP 2026 obtient `non_specifie`.

**Nettoyage (`clean_chandra_markdown`, `:430-452`)**

- La seconde regex (`:447-451`) est morte. Le caractère qui précède le `#` est dans la classe autorisée par la première regex (`[^\n#\s/(\[]` inclut les chiffres, `.`, `)` et `*`), et après la première substitution il ne reste qu'un `\n`.

**Divers**

- `md_by_stem[stem][0]` (`:722`) renvoie un fichier arbitraire si un même stem existe dans plusieurs années.
- `doc_id = f"{eff_year}_{stem[:64]}_{sha[:6]}"` (`:759`) dépend de l'année inférée. L'identifiant est instable alors qu'il fait partie du contrat MCP.
- `reco_family_id`, MD5 du `landing_url` (`:798`), n'est lu nulle part.

### 3.2 `ingestion/chunker.py` (676 lignes)

**`naive_fixed` (`:193-222`)**

- Fenêtre glissante correcte (pas `max(200, size - overlap)`), sans en-tête contextuel. C'est une base de référence propre.
- Il indexe le HTML brut avec ses attributs `data-bbox`. C'est voulu, mais l'écart avec les autres configurations mélange alors plusieurs facteurs (chunking, en-tête contextuel, nettoyage HTML).

**`hierarchical_markdown` (`:320-372`)**

- Correct et générique : pile de titres, marquage de la bibliographie sur les deux derniers niveaux, suppression des attributs HTML.

**`table_aware_sota` (`:375-649`)**

- **Règles propres à l'antibioprophylaxie :**
  - `ALLERGY_BOX_RE` (`:37-43`) : « En cas d'allergie aux bêtalactamines, si antibioprophylaxie indiquée… ». Le type de chunk `callout_allergy` est figé dans `schemas.py:27`. Dans l'index réel, les 29 `callout_allergy` viennent tous de la RFE ABP (`idx.py`).
  - `_update_major_section` (`:416`) : regex `ANTIBIOPROPHYLAXIE\s+EN`.
  - `is_procedure_table` (`:461-463`) : « actes chirurgicaux », « interventionnels », « nomenclature ».
  - `_is_valid_heading` (`:232-235`) exclut les titres H1 commençant par « si allergie », « en cas d », « la demi-vie », « pas d'indication ». Ce sont des correctifs ponctuels pour des faux titres OCR.
- **Bug majeur sur les notes de bas de page.** `is_footnote = re.match(r"^\s*(?:[\*#†‡]|Note\s*:|NB\s*:)", sub) and len(sub) < 900` (`:581`) capture tout paragraphe commençant par `**`, c'est-à-dire du gras Markdown, très fréquent chez Chandra pour les recommandations.
  - Mesuré sur l'index : 1 551 des 1 883 `callout_footnote` commencent par `**`.
  - Ensuite, `:635-646` lie jusqu'à 2 encadrés d'allergie et 2 de ces « notes » à *chaque* chunk de la section majeure : 15 168 chunks sur 32 591 (46,5 %) ont des `linked_callout_ids`.
  - Pour toutes les RFE hors ABP, l'expansion d'encadrés injecte donc dans le contexte des paragraphes en gras arbitraires de la section. Leur effet sur la précision relève de l'audit retrieval, à mesurer.
- **Découpage de la prose (`_split_prose_paragraphs`, `:264-317`).** Une phrase plus longue que `max_chars` n'est jamais redécoupée.
  - Vérifié : 3 000 mots sans ponctuation donnent un seul chunk de 11 999 caractères.
  - Dans l'index, le plus gros chunk de prose fait 21 454 caractères (« Guide d'aide à la mise en place… »). Il y en a 4 au-delà de 6 000 caractères.
- **Tableaux sous un titre « Références ».** Ils sont ignorés silencieusement (`:443-445`) si le titre de bibliographie reste dans les deux derniers niveaux, même après dépilage.
- **Sortie de bibliographie.** `EXIT_REF_LINE_RE` (`:56-61`) contient « Facteurs de risque » et « Traitement probabiliste ». C'est plausible pour les RFE SFAR, mais calé sur la RFE IIA et la RFE ABP.
- **Détection des pédiatries (`_infer_chunk_population`).** Elle est générique et correcte.

### 3.3 `ingestion/table_parser.py` (448 lignes)

**Partie générique, à conserver**

- L'expansion rowspan/colspan avec bornes anti-OCR (rowspan ≤ 40, colspan ≤ 16) est correcte (`:276-346`).
- Le regroupement des lignes par ancre de rowspan sur les colonnes 0 et 1 et la détection des bandeaux en gras ou en colspan sont aussi corrects.

**Bugs et cas limites**

- **Texte hors liste perdu.** `_clean_cell_text` (`:155-177`) : si la cellule contient des `<li>`, tout texte hors liste est perdu. Le commentaire `:166` annonce une vérification qui n'existe pas. Vérifié : `<td><b>Si allergie :</b><ul><li>Clindamycine</li></ul></td>` donne `'Clindamycine'`.
- **Rowspan entre deux pages.** Une table de continuation dont la première colonne vient d'un rowspan de la page précédente a sa première cellule vide. 117 tables héritées hors ABP et 3 dans l'ABP sont dans ce cas (`tables.py`). Les fiches de ligne perdent alors leur clé (acte ou situation).
- **En-têtes hérités à tort.** L'héritage se fait sur le seul nombre de colonnes, dans la même section majeure (`:397-408`). Si une table d'une autre RFE a sa ligne d'en-tête en `<td>` sans les mots-clés d'en-tête, elle hérite des en-têtes de la table précédente de même largeur et sa propre ligne d'en-tête devient une ligne de données. 320 tables héritées hors ABP n'ont pas été vérifiées.
- **Volumes mesurés (`tables.py`) :**

  | Documents | Avec en-tête | En-tête hérité | Sans en-tête (pas de fiche) |
  |---|---:|---:|---:|
  | RFE ABP 2026 | 49 | 70 | 19 |
  | Autres documents | 993 | 320 | 600 |

  835 fiches de ligne portent des en-têtes génériques « Col N » ou « Colonne N », issus de `<th>` vides.
- **Taille non bornée.** `to_markdown_chunks` ne découpe jamais un groupe de rowspan, et un groupe plus grand que `max_chars` est émis tel quel : un tableau Markdown atteint 8 725 caractères.

**Règles propres à l'antibioprophylaxie**

- `_looks_like_header_row` (`:211-249`) : l'anti-indice `\bamoxicilline\b|\bc[ée]fazoline\b|\bivl\b` (`:223`) et des indices comme « actes chirurgicaux », « nomenclature », « réinjection ».
- La désagrégation des listes `<li>` parallèles (`:354-370`) ne se déclenche que sur la présence de « pas d'antibioprophylaxie ». Le commentaire cite « Septo-rhinoplastie sans vs avec greffe », c'est-à-dire les questions Q58, Q125 et Q152.
- L'héritage avec la colonne « Nomenclature » en moins (`:403`), qui correspond au code CCAM de la RFE ABP, et le cas « Catégorie » quand la première cellule fait au plus 16 caractères (`:406`).

### 3.4 `generation/prompts.py` (70 lignes)

- `SYSTEM_CLINICAL_DETAILED` (`:5-17`) : globalement générique. Les « Cas particuliers » citent l'« allergie aux bêtalactamines » en premier, mais le reste est neutre. Il définit une phrase d'abstention explicite (`:16`).
- `SYSTEM_TEMPORAL_DIFF` (`:19-26`) : générique.
- **`SYSTEM_BENCHMARK_OPEN` (`:28-36`) et `SYSTEM_BENCHMARK_MCQ` (`:38-45`) sont propres au benchmark.** Correspondances vérifiées avec `benchmark.json` :

  | Indice dans le prompt | Question(s) |
  |---|---|
  | « PTH voie antérieure ou prothèse d'épaule » (exception allergie) | Q04 (Vancomycine), Q140 (choix « Prothèse d'épaule ») |
  | « si 2 actes chirurgicaux sont associés… au moins l'un » | Q15, Q16 (actes combinés) |
  | « Triméthoprime/Sulfaméthoxazole », « Clindamycine + Gentamicine » (exemples) | Q28, Q12/Q43 (réponses attendues) |
  | « intervention SANS antibioprophylaxie » | Q140 (titre « Intervention sans ABP ») |
  | « plaie de la main » vs « hors main » | Q15, Q143 |
  | « genou » vs « hanche voie antérieure » | Q139, Q141, Q04 |
  | « ouverture articulaire », « geste difficile », « temps opératoire long » | Pièges de la RFE ABP (aucune question ne contient ces mots, mais ce sont des exceptions de tableaux ABP) |

  Ces prompts doivent être déplacés hors de `src/` (dans un adaptateur de benchmark) ou réécrits sans référence au domaine. Le principe 1 de CLAUDE.md les exclut en l'état.

### 3.5 `generation/verifier.py` (150 lignes)

- **Ce qui est vérifié réellement :**
  - les citations `[Sn]` hors de l'intervalle 1..k (`:106-108`) ;
  - les molécules de la liste `TRACKED_MOLECULES`, présentes dans la réponse mais absentes du contexte, par regex à limite de mot sur un texte sans accents (`:113-114`) ;
  - la présence d'une source non à jour *dans le contexte*, même si elle n'est pas citée (`:116-120`) ;
  - une abstention par 5 sous-chaînes (`:83-89`).
- **Ce qui n'est pas vérifié :**
  - les doses (vérifié : « Céfazoline 20 g » obtient 1,0) ;
  - le lien molécule ↔ acte ou situation ;
  - le fait que la source citée contienne l'affirmation ;
  - les molécules hors liste : propofol, kétamine, curares, corticoïdes, ondansétron… La liste couvre des antibiotiques, anticoagulants, antiagrégants et quelques antidotes ;
  - les formes plurielles et les sigles : « héparines » et « HBPM » ne sont pas détectés.
- **Contexte contrôlé ≠ contexte montré au LLM.** La vérification porte sur `indexed_text` (`:111`), alors que le LLM a reçu `c.text` éventuellement élagué par `prune_verbose_prose` (`retrieval/pipeline.py:770-773`). Une molécule retirée par l'élagage reste « ancrée ».
- **Abstention.** « Les extraits ne mentionnent pas cette situation » n'est pas détecté comme une abstention (vérifié).
- **Score non calibré.** `grounding_score` est une somme de pénalités ad hoc (−0,35, −0,25 par molécule, −0,20), pas une probabilité. L'afficher en pourcentage dans l'interface (`api.py:232-233`) est trompeur pour un clinicien.

### 3.6 `generation/client.py` (554 lignes)

- **`OpenAICompatibleLLM` (`:24-92`) :**
  - aucune relance, aucune gestion d'exception : les erreurs remontent ;
  - `stream_complete` renvoie un `usage` vide : en streaming, aucun comptage de tokens ;
  - le délai d'expiration de 120 s est configurable.
- **`LocalMlxLLM` (`:95-182`) :**
  - correct, avec échantillonnage glouton à température 0 ;
  - non sûr en multi-thread, alors que FastAPI exécute les endpoints synchrones dans un pool de threads (voir §3.7).
- **`SfarRagEngine.answer` (`:244-398`) :**
  - Les budgets de contexte sont codés en dur selon le mode (`:261-262`, 7/5/6 chunks).
  - **Alerte allergie bêtalactamines (`:280-286`)** injectée dès que `"allergy" in analysis.modifiers`. Ce modificateur s'active aussi pour « hypersensibilité », « intolérance » et « alternative » (`retrieval/router.py:45`). Une question sur l'anaphylaxie peranesthésique (RFE 2025) ou sur une « alternative » à un morphinique reçoit donc une instruction erronée. C'est un risque clinique, et ce n'est pas générique.
  - **Réparation (`:340-370`)** : un seul passage de réparation si une molécule n'est pas ancrée. Le prompt suggère « 'Pas d'antibioprophylaxie' / 'Hors périmètre' » (`:347`), y compris pour une question sur les anticoagulants. Pousser le modèle vers « pas de prophylaxie » après une hallucination peut transformer une erreur en faux négatif clinique.
  - **Ajout déterministe de provenance (`:372-379`)** : voir conclusion 2. À retirer, ou à rapporter séparément comme « sourcing ajouté par le système ».
  - **Pas d'abstention déterministe.** Aucun seuil sur le score de retrieval, aucun contexte vide détecté avant l'appel au LLM : l'abstention est entièrement déléguée au LLM (et au module CRAG du retrieval).
  - **Fallback d'extraction.** `_extract_benchmark_final_line` (`:545-554`) retourne la dernière ligne si « RÉPONSE : » est absent. Vérifié : « Céfazoline 2g\n\n(Source S1) » donne « (Source S1) ».
- **`stream_answer` (`:400-542`)** copie `answer` avec un prompt de réparation différent (`:503-508`). Les jetons de la première réponse, éventuellement hallucinée, sont déjà envoyés à l'interface avant la réparation.
- **Numérotation des citations.** `build_citations` et `format_context_for_llm` utilisent la même numérotation, même avec l'ordre en U (`retrieval/pipeline.py:751-756`). Cohérent.

### 3.7 `interfaces/api.py` (533 lignes)

- **Endpoints et modèles :** voir §5.
- **`/v1/chat/completions` (`:500-531`) :**
  - Le mode est choisi par sous-chaîne du nom de modèle (`:507-510`) : un modèle inconnu bascule silencieusement en `clinical_detailed`.
  - Seul le dernier message `user` est utilisé. Les messages `system` et l'historique sont ignorés.
  - `temperature` et `max_tokens` sont déclarés (`:53-54`) mais ignorés.
  - Un client qui envoie `stream=true` reçoit du JSON non streamé et casse.
  - `ChatMessage.content: str` (`:47`) rejette le format OpenAI « content parts » en tableau, ainsi que `content: null`, avec une erreur 422.
  - Aucune gestion d'erreur : une panne du LLM donne un HTTP 500, alors que `/api/query` a un repli (`:472-486`).
- **`/api/query/stream`.** Les erreurs sont envoyées comme un événement `token` contenant le message d'exception (`:441-447`), ce qui expose des détails internes.
- **Échec silencieux du reranker.** Le reranker est désactivé silencieusement si son chargement échoue (`:349-350`). Seul `/api/health` le montre.
- **Interface HTML.** `doc_title`, `section_path` et les avertissements sont injectés dans `innerHTML` sans échappement (`:210-213`, `:240`). Le risque est faible tant que le corpus est fiable.
- **Exemples de la démo.** Les exemples 1 et 2 de l'interface (`:144-145`) sont les questions Q04 et Q28 du benchmark : c'est acceptable pour une démonstration, mais ce sont aussi les cas qui ont servi au réglage.
- **Exposition réseau.** `api_host` vaut `0.0.0.0` par défaut (`config.py:54`), sans authentification.

### 3.8 `interfaces/mcp_server.py` (243 lignes)

Sonde `mcp.py`, vérifiée :

| Message | Réponse actuelle | Attendu |
|---|---|---|
| Notification `notifications/cancelled` (sans `id`) | Erreur `-32601` avec `id: null` | Aucune réponse : JSON-RPC interdit de répondre à une notification |
| `ping` | `-32601 Method not found` | `{}` (requis par la spécification MCP) |
| `initialize` avec `protocolVersion: "2025-06-18"` | Renvoie toujours `"2024-11-05"` | Acceptable par négociation, mais à documenter |
| Ligne non JSON | Rien sur stdout, log sur stderr | Réponse `-32700 Parse error`, `id: null` |
| Outil inconnu | `result.isError=true` | Acceptable ; la spécification recommande plutôt `-32602` |
| `query` absent | `isError`, « Error: 'query' » | Valider le schéma et renvoyer un message clair |
| `top_k: "abc"` | `isError` (message `int()`) | Idem |

- **Description figée.** Les descriptions annoncent « 267 recommandations » (`:30`), alors que le corpus réel en compte 264.
- **`latest_only` par défaut à `True`** dans `search_sfar_recommendations` (`:101`). Cela court-circuite le mode temporel automatique du routeur : une question « qu'est-ce qui a changé » passée à `search` ne verra que les éditions en vigueur.
- **Démarrage avec la valeur par défaut.** `main()` utilise `Settings().index_dir`, qui vaut `index/sota_default`, dossier absent.
- **Pollution possible de stdout.** Le chargement de `sentence-transformers` et du reranker peut écrire sur stdout et casser le protocole stdio. Aucune redirection n'est faite, et le comportement réel n'a pas été testé.

### 3.9 `evaluation/benchmark_adapter.py::SfarRagApproach` (`:59-99`)

- `build_prompt` :
  - appelle `retrieve` puis `format_context_for_llm(retrieved, query=full_q, prune_prose=self._config.use_u_shape_ordering)` (`:98`), avec le mauvais paramètre de configuration ;
  - n'applique pas `select_generation_context`, alors que `SfarRagEngine.answer` l'applique : le contexte diffère de celui qui a été évalué ;
  - laisse `reorder_u_shape` à `True`, quelle que soit la configuration.
- **Incompatible avec les scoreurs de la plateforme.** La plateforme envoie le `system_prompt` du jeu de données (« Aucune explication ») et note la sortie *brute*. Notre prompt utilisateur exige « exactement 2 lignes (ANALYSE puis RÉPONSE) » (`prompts.py:54`). Vérifié avec `score_antibioprophylaxie_answer`, qui reproduit exactement `QCMScorer` et `OpenScorer` :
  - QCM verbeux correct (« A : faux ; B : faux ; C : vrai… RÉPONSE : C ») : noté **faux**, car la première lettre isolée est A.
  - Question ouverte attendue « Céfazoline », sortie « ANALYSE : PTH = Céfazoline ; allergie → Vancomycine / RÉPONSE : Vancomycine » : noté **juste**.
- **Non enregistrable.** La classe ne dérive pas d'`ApproachPort` et son constructeur exige `retriever`. `APPROACH_REGISTRY: dict[str, type[ApproachPort]]` ne peut pas l'instancier sans fabrique.
- **Aucun test.**

### 3.10 `schemas.py` (205 lignes)

- **Types non stricts.** Dans `Chunk`, les champs `language`, `doc_role` et `setting_scope` sont des `str`, alors que ce sont des `Literal` dans `DocumentMetadata` : la validation est incohérente.
- **Remplacement mal affiché.** `superseded_by` contient un `doc_id`. `Chunk` et `Citation` n'ont ni `superseded_by_year` ni titre du document remplaçant, si bien que le contexte LLM affiche « REMPLACÉE (2018_xxx_abc123) » (`retrieval/pipeline.py:766`).
- **Types de chunk propres à l'ABP.** `ChunkType` contient `callout_allergy`. Un type générique `callout`, avec un sous-type facultatif, serait plus adapté.
- **Champs jamais lus hors ingestion :** `reco_family_id`, `recommendation_ids`, `has_dosage_info`, `source_tabs`. `disciplines` ne sert qu'à `setting_scope`.

### 3.11 `cli.py` (320 lignes)

Note : pendant l'audit, `cli.py` a été modifié hors de cet audit (+70 lignes non commitées, selon `git diff --stat`). Les références ci-dessous portent sur la version du commit `943e0cd`. Les lignes 1 à 177 sont inchangées.

- `build_and_save_index` : correct. Les chunks de bibliographie reçoivent un vecteur nul (`:83-87`), ce qui est voulu.
- `eval_cmd` lance l'ablation sur les 171 questions et le stress test multi-RFE, sans séparation dev/test (principe 2). Le détail relève de l'audit d'évaluation.
- `audit_cmd` écrit en dur « (dont les 3 RFE phares 2026 !) » (`:177`), un chiffre non calculé.

### 3.12 `scripts/`

- **`run_e2e_eval.py` :**
  - La ligne de base zero-shot utilise un prompt d'une ligne (`:50-59`), alors que le RAG utilise les prompts benchmark à 2 lignes avec indices. L'écart mesuré mélange donc retrieval et prompting.
  - `--max-tokens 48` est écrasé par 200 et 320 dans `answer()`.
  - Le sous-échantillon `--stratified` garde *toutes* les questions d'allergie.
  - Le sourcing est gonflé par `client.py:372-379`.
- **`run_clinical_showcase.py`, `quick_demo_queries.py` :** 6 requêtes vitrines, dont 2 sont les questions Q04 et Q28. Le reranker est codé en dur dans `quick_demo_queries.py:39`.
- **`audit_abp_v2_vs_v3.py` :** script ponctuel propre à l'ABP (`V3_CHANGED_TOPICS` écrit à la main). Utile comme note, mais pas comme code produit.
- **`export_pgvector.py` :** non testé, chemin d'index codé en dur.
- **`generate_slides_charts.py` :** purement présentationnel. Les SVG sont construits par chaînes sans échappement des libellés.

---

## 4. Tests (`tests/`, 19 tests)

### 4.1 Ce que couvrent réellement les tests

| Test | Couverture réelle |
|---|---|
| `test_clean_chandra_inline_headings` | 1 regex de nettoyage, 2 cas |
| `test_html_table_rowspan_and_continuation_headers` | Rowspan sur la colonne 0 et héritage d'en-tête à colonnes égales (fixture ABP) |
| `test_table_sub_banner_inheritance` | Bandeaux en gras AVK/AOD |
| `test_language_detection_handles_english_abstract` | 2 cas, dont 1 décidé par le *nom de fichier* « Guidelines-for- » |
| `test_effective_year_and_domain_imputation` | Le cas exact de la RFE ABP V3.0 et 1 imputation de domaine |
| `test_medical_lexicon_and_query_router` | Retrieval (hors périmètre) |
| `test_section_allergy_box_linking_and_expansion` | Liaison des encadrés d'allergie (fixture ABP) et BM25 |
| `test_citation_and_molecule_verifier` | Citation hors intervalle et méropénème non ancré |
| `test_antibioprophylaxie_scorer_parity` | Copie locale des scoreurs, pas comparée au code de la plateforme |
| `test_mcp_server_protocol` | `initialize`, `tools/list` (4 outils), 1 `tools/call` |
| `test_real_corpus_supersession_and_integrity` | Au moins 260 documents ; ABP 2026 à jour, 2018 remplacée ; anticoagulants 2026 et 2024 à jour |
| `test_frontier_2026_subword_crag_context_opt_and_rag_x` | Retrieval et évaluation, plus 1 cas de sortie de bibliographie du chunker |
| `test_mcq_choices_formatting_and_sourcing_scorer` | Formatage QCM et scoreurs |
| `test_self_medrag_active_verifier_repair` | Boucle de réparation avec un faux LLM |
| `test_noise_filtered_precision_context_selection` | Retrieval et `_extract_benchmark_final_line` (cas nominal) |
| `test_specialty_allergy_box_survives_child_chirurgie_subheading` | Liaison des encadrés d'allergie ABP |
| `test_balanced_temporal_diff_and_macrolide_guard` | Vérificateur (azithromycine) et retrieval temporel |
| `test_mcq_option_composite_and_scope_guard` | CRAG et désagrégation « PAS D'ANTIBIOPROPHYLAXIE » |
| `tests/test_api.py::test_fastapi_endpoints_and_openai_compat` | `/`, `/api/health`, `/api/search`, `/v1/models`, `/v1/chat/completions` (sans LLM), `/api/query/stream` en retrieval seul |

Les tests figent les règles propres à l'ABP comme comportement attendu. Par exemple, la désagrégation « PAS D'ANTIBIOPROPHYLAXIE » est spécifiée par `tests/test_rag_sfar.py:599-616`. Deux tests recopient des questions du benchmark : Q146 (`:567`) et Q16 (`:582-585`). Toujours dans `src/`, `retrieval/crag.py:204` contient un fragment de Q16 (relève de l'audit retrieval).

### 4.2 Ce qui manque

1. **Le test anti-fuite exigé par CLAUDE.md (principe 3)** : il doit échouer si une question ou une réponse de référence apparaît dans `src/`. Le prototype `leak.py`, à base de 9-grammes, trouve aujourd'hui Q04 et Q28 dans `api.py` et Q16 dans `crag.py`. Les indices de `prompts.py` sont paraphrasés, donc ce test ne les détecte pas : il faut le compléter par une revue manuelle.
2. **`SfarRagApproach`** : non testé. Il faudrait au minimum un test « sortie brute → scoreur de la plateforme ».
3. **Chunkers `naive_fixed` et `hierarchical_markdown`** : non testés.
4. **Supersession sur données synthétiques** : édition non datée, deux éditions la même année, traduction, document abrogé. Aujourd'hui, seul le corpus réel est testé, et le test est ignoré si on lance pytest depuis un autre répertoire (chemin relatif, `:265`).
5. **Imputation de domaines** : aucun test de faux positif (« fracture », « muscle »).
6. **API :**
   - `/api/query` avec un LLM simulé qui échoue (repli) ;
   - `/v1/chat/completions` en modes `benchmark-open` et `benchmark-mcq` ;
   - `content` en tableau ;
   - `stream=true` ;
   - erreur LLM.
7. **MCP :** notifications, `ping`, erreur de parsing, les 3 autres outils, `get_recommendation_sections` avec un `doc_id` inconnu.
8. **Génération :**
   - alerte allergie déclenchée sur une question « hypersensibilité » ;
   - fallback de `_extract_benchmark_final_line` ;
   - abstention sur contexte vide ;
   - mode `temporal_diff` sélectionné automatiquement.
9. **Parseur de tableaux :**
   - texte et `<li>` dans une même cellule ;
   - rowspan rompu entre deux pages ;
   - en-tête en `<td>` sans mot-clé ;
   - groupe plus grand que `max_chars`.
10. **Un test du cadenas dev/test** (principe 2) : rien n'existe.

---

## 5. Contrats d'interface à préserver (rétrocompatibilité)

### 5.1 API HTTP (`rag_sfar.interfaces.api:create_app`)

Fabrique : `create_app(index_dir: Path|None=None, settings: Settings|None=None, enable_llm: bool=True, mlx_model_path: str|None=None) -> FastAPI`. Lancement : `rag-sfar-serve [--index-dir] [--host] [--port] [--no-llm] [--mlx-model]`.

| Méthode et chemin | Requête | Réponse |
|---|---|---|
| `GET /` | — | HTML de l'interface de démonstration |
| `GET /api/health` | — | `{status, index_dir, num_documents, num_chunks, embedding_model, reranker_model, llm_model}` |
| `GET /api/catalog?latest_only=false` | Paramètre `latest_only: bool` | `{count, documents: [DocumentMetadata]}` |
| `POST /api/search` | `SearchRequest`, voir ci-dessous | `{query_analysis: QueryAnalysis, latency_ms: dict, retrieved_chunks: [RetrievedChunk]}` |
| `POST /api/query` | `QueryRequest` = `SearchRequest` + `mode: str="clinical_detailed"`, `retrieval_only: bool=false` | `RagResponse.model_dump()` |
| `POST /api/query/stream` | `QueryRequest` | SSE `data: <json>\n\n`, événements décrits ci-dessous |
| `GET /v1/models` | — | `{object:"list", data:[{id, object:"model", owned_by:"sfar-datathon"}]}` avec les identifiants `rag-sfar-sota`, `rag-sfar-benchmark-open`, `rag-sfar-benchmark-mcq` |
| `POST /v1/chat/completions` | `{model: str="rag-sfar-sota", messages:[{role, content: str}], temperature?, max_tokens?}` | `{id:"chatcmpl-…", object:"chat.completion", created, model, choices:[{index:0, message:{role:"assistant", content}, finish_reason:"stop"}], usage:{prompt_tokens, completion_tokens, total_tokens}, sfar_citations:[Citation], sfar_verification: VerificationReport}` |

**`SearchRequest`** : `query: str`, `top_k: int=8`, `latest_only: bool|None=None`, `use_reranker: bool=True`, `use_hybrid: bool=True`, `use_lexicon: bool=True`, `expand_callouts: bool=True`, `domains: list[str]|None`. Attention : `expand_callouts` pilote à la fois `expand_section_callouts` et `expand_neighbors`.

**Événements SSE de `/api/query/stream` :**
- `retrieval` : `{type:"retrieval", query_analysis, latency_ms, retrieved_chunks, citations, model_used}`
- `token` : `{type:"token", text}`
- `done` : `{type:"done", answer, full_generation, latency_ms, token_usage, verification, model_used, extra:{self_corrected, reasoning_trace}}`
- En mode retrieval seul ou en cas d'erreur, `done` est réduit à `{type, answer, latency_ms, verification:{}, extra:{}}`.

**Sémantique `/v1/chat/completions` :**
- Le mode se déduit d'une sous-chaîne du nom de modèle : `benchmark-open` → `benchmark_open` (réponse d'une ligne : molécule + « (SFAR <année> [Sx]) ») ; `benchmark-mcq` → `benchmark_mcq` (lettre + provenance) ; autre → `clinical_detailed`.
- Seul le dernier message `user` est utilisé.
- Les clés non standard `sfar_citations` et `sfar_verification` sont lues par la démo et peut-être par d'autres équipes.

**Pistes d'évolution rétrocompatibles :**
- accepter `content` en `str | list[part]` ;
- implémenter `stream=true` en SSE OpenAI ;
- honorer `temperature` et `max_tokens` ;
- renvoyer une erreur OpenAI `{error:{message,type}}` plutôt qu'un 500 nu ;
- ajouter des modèles sans renommer les 3 identifiants existants.

### 5.2 Serveur MCP `rag-sfar-mcp` (`rag_sfar.interfaces.mcp_server:main`, stdio, JSON-RPC 2.0 ligne par ligne)

- `initialize` → `{protocolVersion:"2024-11-05", capabilities:{tools:{}}, serverInfo:{name:"rag-sfar-mcp", version:"1.0.0"}}`.
- `tools/list` → 4 outils, verrouillés par `tests/test_rag_sfar.py:252` :

| Outil | Paramètres (`inputSchema`) | Sortie (`content[0].text`) |
|---|---|---|
| `search_sfar_recommendations` | `query: string` (requis), `top_k: integer=6`, `latest_only: boolean=true`, `domain: string` (un seul domaine, correspondance exacte) | Ligne « Analyse requête : mode=…, pop=…, contexte=…, acronymes={…} », puis les blocs `### [S{i}] {titre} — {type} SFAR {année} ({version}) [EN VIGUEUR \| ÉDITION ANTÉRIEURE — REMPLACÉE ({doc_id})]`, `Section : … \| Type : … \| Grades : …`, le texte, séparés par `\n\n---\n\n` |
| `compare_sfar_editions` | `topic_query: string` (requis), `top_k: integer=10` | Mêmes blocs, toutes éditions, au plus 3 chunks par document |
| `list_sfar_catalog` | `keyword: string`, `latest_only: boolean=true`, `limit: integer=25` | Lignes `- [{année}] ({doc_type}/{doc_role}) [EN VIGUEUR\|REMPLACÉE ({année})] \`{doc_id}\` — {titre} \| Domaines: …`, ou « Aucun document correspondant. » |
| `get_recommendation_sections` | `doc_id: string` (requis), `section_filter: string`, `limit: integer=10` | Blocs `### [{chunk_type}] {section_path}\n{texte}`, ou « Aucun passage trouvé pour doc_id=… » |

- **Erreurs d'outil** : `result.isError=true` avec le texte « Error: … ». **Méthode inconnue** : `error.code=-32601`.
- **Identifiants à stabiliser.** Le format du `doc_id`, `{année_effective}_{stem[:64]}_{sha256[:6]}` avec les caractères hors `[A-Za-z0-9_-]` remplacés par `_`, fait partie du contrat de fait, puisque `list_sfar_catalog` le fournit à `get_recommendation_sections`. Il dépend de l'heuristique d'année : il faut le figer, par exemple sans l'année, ou publier une table de correspondance avant toute modification du loader.

### 5.3 Adaptateur de benchmark (`rag_sfar.evaluation`)

- `SfarRagApproach(retriever: SfarRagRetriever, config: RetrievalConfig|None=None, approach_name: str="rag-sfar-sota")`, avec :
  - la propriété `approach_id`, qui renvoie `ApproachId(name)` si `llm_benchmark` est importable, sinon une chaîne ;
  - `prepare() -> None` ;
  - `build_prompt(question) -> str`, qui lit `question.question_text` (ou `.question`), `question.choices` (objet avec `.choices` ou dict A-D) et `question.question_type` (contenant « mcq »).
- `score_antibioprophylaxie_answer(question_type: str, expected_answer: str, actual_answer: str) -> bool` et `score_sourcing_present(actual_answer: str) -> bool`, des copies des scoreurs de la plateforme.

### 5.4 API Python et CLI

- **`SfarRagEngine`** :
  - `SfarRagEngine(retriever, llm=None, default_config=None)` ;
  - `.from_settings(settings, retriever, default_config=None, enable_llm=True)` ;
  - `.answer(query, mode="clinical_detailed", config=None, override_latest_only=None, override_domains=None, retrieval_only=False) -> RagResponse` ;
  - `.stream_answer(...)`, qui produit des dict avec les mêmes événements que le SSE.
  - Modes : `clinical_detailed`, `temporal_diff`, `benchmark_open`, `benchmark_mcq`.
  - Clés de `extra` : `context_chars`, `self_corrected`, `reasoning_trace`.
- **LLM** : `OpenAICompatibleLLM(base_url, api_key, model, temperature=0.0, max_tokens=1024, timeout=120.0)` et `LocalMlxLLM(model_path, model_label=None, temperature=0.0, max_tokens=450)`. Les deux exposent `complete(system_prompt, user_prompt, temperature=None, max_tokens=None) -> (str, usage_dict)` et `stream_complete(...)`, qui produit `("token", str)` puis `("usage", dict)`.
- **Ingestion** :
  - `load_sfar_corpus(corpus_dir, include_english=True, deduplicate_sha256=True) -> list[LoadedDocument]` ;
  - `chunk_document(doc, strategy, **kwargs)` et `chunk_corpus(docs, strategy, **kwargs)` avec `strategy ∈ {naive_fixed, hierarchical_markdown, table_aware_sota}` ;
  - `parse_html_table(table_html, previous_headers=None) -> ParsedTable`.
- **Schémas Pydantic** sérialisés par l'API, l'index SQLite (`payload_json`) et MCP : `DocumentMetadata`, `Chunk`, `QueryAnalysis`, `RetrievedChunk`, `Citation`, `VerificationReport`, `RagResponse`. On peut ajouter des champs facultatifs. Il ne faut ni renommer ni retirer un champ, et pas davantage restreindre un `str` en `Literal` sans migration de l'index.
- **CLI (`pyproject.toml`)** :
  - `rag-sfar-audit [--corpus-dir] [--output-dir]` ;
  - `rag-sfar-index [--corpus-dir] [--output-dir] [--strategy] [--embedding-provider] [--embedding-model] [--skip-embeddings] [--batch-size]` ;
  - `rag-sfar-eval [--index-root] [--benchmark-path] [--output-dir] [--reranker-provider] [--reranker-model]` ;
  - `rag-sfar-serve` ;
  - `rag-sfar-mcp`.
- **Variables d'environnement** : préfixe `RAG_SFAR_`, par exemple `RAG_SFAR_INDEX_DIR`, `RAG_SFAR_LLM_BASE_URL`, `RAG_SFAR_LLM_MODEL`, `RAG_SFAR_RERANKER_PROVIDER`.

---

## 6. Garder / simplifier / généraliser / supprimer

### Garder

- **Parseur de tableaux** (`table_parser.py:252-448`, sans les règles ABP) : expansion rowspan/colspan, groupes de rowspan, bandeaux, en-têtes multi-lignes, fiches de ligne. Le mécanisme est générique et utile partout.
- **`hierarchical_markdown`, `naive_fixed`** : des bases de référence claires.
- **`detect_language`** : échantillonnage du corps du document et comptage de mots-outils (sans la liste de noms de fichiers).
- **`infer_effective_year_and_version`** : détection `V\d+\.\d+ du jj/mm/aaaa` et imputation depuis le nom de fichier ou l'en-tête.
- **Marquage de la bibliographie** et garde-fou `_is_truly_reference_text`, ainsi que la sortie de bibliographie sur `R\d+\.\d+` et `GRADE`.
- **`SYSTEM_CLINICAL_DETAILED`, `SYSTEM_TEMPORAL_DIFF`** et le contrôle des citations hors intervalle.
- **Les contrats d'interface du §5**, en les élargissant sans les casser.

### Simplifier

- **`client.py`** : fusionner `answer` et `stream_answer` dans un `_prepare_context()` commun, avec un seul prompt de réparation. Sortir les budgets 7/5/6 et 200/320 dans `RetrievalConfig` ou une configuration de génération.
- **`api.py`** : une fonction `_build_rcfg(req)` au lieu de trois copies.
- **`verifier.py`** : renommer `grounding_score` en un indicateur explicite, par exemple « molécules connues non ancrées / citations invalides », et ne plus l'afficher en pourcentage.
- **`loader.py`** : supprimer la regex morte (`:447-451`) et la condition redondante `"juin-2026"`.

### Généraliser

- **Supersession** : remplacer `LINEAGE_RULES` par une lignée calculée, par exemple par similarité de titres normalisés, `landing_url` commun et recouvrement de domaines, puis validée par un fichier de correspondances *de données* (YAML relu par un clinicien), hors du code. Exiger aussi un départage par `version_label` à année égale.
- **Domaines** : correspondance par mot entier (`\b…`), suppression des sigles ambigus (« rac », « usc », « alr », « aod » seuls), pas d'enrichissement quand `raw_subdomain` existe, et retrait des domaines de l'en-tête indexé tant qu'ils ne sont pas fiables.
- **Encadrés (`callout_*`)** : un type `callout` générique, détecté par la structure (encadré, ligne courte en tête de tableau, notes `*`/`†` réelles, pas `**`), avec un sous-type facultatif. Plafonner les liens de section.
- **Tableaux** :
  - garder le texte hors `<li>` dans `_clean_cell_text` ;
  - propager un rowspan ouvert à la table de continuation ;
  - n'hériter des en-têtes que si la première ligne n'est *pas* elle-même un en-tête plausible et si les tables se suivent sans prose entre elles ;
  - découper les groupes plus grands que `max_chars`.
- **Découpage de la prose** : coupe forcée par caractères quand une phrase dépasse `max_chars`.
- **Alerte allergie** : ne l'injecter que si l'allergène est explicitement une bêtalactamine ou une pénicilline dans la *question*, et formuler un message neutre, par exemple « la question mentionne une allergie à X ».
- **Abstention** : ajouter un seuil déterministe (aucun chunk au-dessus du seuil → réponse « Hors périmètre » sans appel au LLM), mesuré sur des questions hors corpus.
- **MCP** : silence sur les notifications, `ping`, réponse `-32700`, validation des arguments, rediriger stdout vers stderr pendant le chargement, `latest_only` par défaut à `null` (routage automatique), nombre de documents calculé.
- **`SfarRagApproach`** : en faire une sous-classe d'`ApproachPort` avec fabrique sans argument, utiliser `select_generation_context`, corriger le paramètre `prune_prose`, et produire une sortie conforme au prompt système de la plateforme (une ligne) ou fournir un post-traitement documenté.

### Supprimer ou déplacer hors de `src/`

- **`SYSTEM_BENCHMARK_OPEN` et `SYSTEM_BENCHMARK_MCQ`** dans leur forme actuelle, à cause des indices Q04, Q15, Q28, Q139-Q143 et Q140. Si un mode concis est nécessaire, le réécrire sans aucun exemple de domaine et le mesurer sur dev uniquement.
- **L'ajout automatique « (SFAR <année> [S1]) »** (`client.py:372-379`).
- **Le texte de réparation « Pas d'antibioprophylaxie »** (`client.py:347`).
- **Les règles ABP du parseur et du chunker** : désagrégation « pas d'antibioprophylaxie » (`table_parser.py:354-370`), anti-indices molécules/IVL (`:223`), cas « nomenclature » (`:403`), `ANTIBIOPROPHYLAXIE EN` (`chunker.py:416`), `is_procedure_table` (`:461-463`) et la liste de faux titres (`:232-235`). À remplacer par des critères structurels ou à supprimer après ablation.
- **Les noms de fichiers en dur de `detect_language`** (`loader.py:470`) et la règle « afar » de `infer_effective_year_and_version` (`:521-526`).
- **Les questions du benchmark recopiées** dans `api.py` (exemples de la démo, à remplacer par des questions hors benchmark), `tests/test_rag_sfar.py` (Q146, Q16) et `retrieval/crag.py:204`.
- **Les champs jamais lus** (`reco_family_id`, `recommendation_ids`, `has_dosage_info`, `source_tabs`), sauf besoin documenté.
- **`scripts/audit_abp_v2_vs_v3.py`** : script ponctuel à archiver.
