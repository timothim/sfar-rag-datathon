# C8 « générique » : changements appliqués

Date : 2026-11-26. Branche `rag-sfar-v2`, 7 commits de `b09c2f5` à `fb27ad5` (plus ce rapport), à partir de `fa0426a` ; des commits d’un autre processus (`2342361`, `d0cbc08`, `9788a23`, `0d0fd36`) sont intercalés et ne touchent pas `src/` ni `tests/`. Spécifications suivies : `reports/01_audit.md` (C1–C8, I3, I4), `reports/agents/audit_integrite_evaluation.md` §7, `reports/agents/audit_code_retrieval.md` et `reports/agents/audit_code_ingestion_generation.md` §5.

État à la fin :
- `pytest -q` : 42 tests passent (27 au départ, dont 1 xfail).
- `tests/test_no_benchmark_leakage.py` ne produit plus aucune sortie, et son marqueur `xfail` est retiré.
- Le même balayage appliqué à `tests/` ne trouve rien non plus.
- Aucun index n'a été reconstruit. Aucune évaluation n'a été lancée et aucune API payante n'a été appelée. Je n'ai fait que des requêtes ponctuelles en BM25 sur `index/table_aware_sota`.

Les numéros « avant » renvoient à `fa0426a`, les numéros « après » à `fb27ad5`. Le n° entre crochets est celui du tableau §7 de l'audit d'intégrité.

## 1. Liste des changements

### Prompts — commit `b09c2f5`

| Avant → après | Décision | Justification générique |
|---|---|---|
| `prompts.py:28-36` → `:34-42` (`SYSTEM_BENCHMARK_OPEN`) | **Supprimer** les exemples et **généraliser** les règles [1–4] | Retirés : PTH voie antérieure, épaule, ouverture articulaire, molécules d'exemple, « si/si » amoxicilline/céfazoline, « 1re intention (jamais la 2e) ». Restent trois règles de format et d'ancrage, valables pour toute RFE : (a) vérifier chaque situation si la question en associe plusieurs ; (b) n'appliquer une ligne conditionnelle (« en cas de… », « si… ») que si sa condition figure dans la question ; (c) pour un terrain cité, suivre la conduite de la même section, dans l'ordre de préférence des extraits. La réponse est « formulée comme dans les extraits ». « Pas d'antibioprophylaxie » ne figure plus comme réponse type ; l'absence d'indication reste possible si les extraits l'écrivent. |
| Règle « si 2 actes… retiens la molécule si au moins l'un… » [1] | **Supprimée** (voir §2) | C'est une règle clinique qu'il faut faire valider par un médecin. Seule subsiste la règle (a) ci-dessus. |
| `prompts.py:38-45` → `:44-51` (`SYSTEM_BENCHMARK_MCQ`) | **Supprimer** les exemples [5] | Retirés : « SANS antibioprophylaxie », « plaie de la main / hors main », « genou / hanche voie antérieure ». Restent le repérage de la polarité (exacte/inexacte, « sauf », « ne… pas ») et le respect des qualificatifs de la ligne (ordre de préférence, population, site, conditions). Le format de sortie `RÉPONSE : <Lettre> (SFAR <année> [Sx])` est inchangé. |
| `prompts.py:13` (« allergie aux bêtalactamines ») et `:23` (« pédiatrie, alternatives allergiques ») | **Généraliser** | Remplacés par « allergies, populations particulières » et « nouvelles populations, nouvelles alternatives ». |
| `prompts.py:59` (« Évalue A, B, C, D ») → `:65` | **Généraliser** | Devient « chaque choix ». Les QCM à 5 options existent. |
| `client.py:347` (réparation « réponds 'Pas d'antibioprophylaxie' ») → `client.py:399` | **Supprimer** | Ne garde que « Hors périmètre ». Pousser vers « pas de prophylaxie » après une hallucination peut transformer l'erreur en faux négatif clinique. |

### CRAG — commit `a3b3cf7` (`retrieval/crag.py`)

| Avant → après | Décision | Justification générique |
|---|---|---|
| `crag.py:31-43` → `:34-61` (`FACET_RULES`) | **Supprimer** identifiants et molécules ; **garder** les facettes [10, 11] | Retirés des sous-requêtes et des regex de preuve : R1.2, R1.2.x, R1.5–R1.7, ertapénème, carbapénème, céfazoline, amoxicilline, clindamycine, ainsi que dabigatran, apixaban et rivaroxaban dans la facette rénale. La sous-requête devient `<question d'origine> <termes du modificateur>` (« BLSE bêta-lactamase… », « obèse IMC poids… », « insuffisance rénale DFG… », « pédiatrie enfant mg/kg »). Le sujet vient de la question. La facette « identifiant de recommandation explicite » (R\d+…) est conservée : elle lit l'identifiant écrit par l'utilisateur. |
| `crag.py:89-112` → `:105-116` (`_extract_anchor_terms`) | **Généraliser** [12] | La liste fermée de 15 mots tirés de 2–3 RFE disparaît. Les ancres sont désormais les 6 premiers mots de contenu du stem de la question : stopwords et formulations interrogatives génériques sont retirés (`_QUESTION_WORDS` : parmi, laquelle, exacte, incorrecte…). |
| `crag.py:162-165` (`"orl"` → ajoute « antibioprophylaxie ») | **Supprimer** | Règle propre à une RFE. |
| `crag.py:129-138` (`_PURE_DRUG_OR_DOSAGE_RE`, liste d'antibiotiques) → `:130-162` | **Généraliser** [13] | Une option est reconnue comme « médicament ou dose » si tous ses mots sont des DCI repérées par les segments-clés OMS des DCI (‑cilline, ‑mycine, ‑oxacine, ‑pénème, céf‑, ‑xaban, ‑gatran, ‑parine, ‑curonium, ‑caïne, ‑azolam, ‑sétron, ‑fentanil…), des doses, des voies ou des connecteurs. Les options négatives (« Pas de… », « Aucun… ») comptent aussi. C'est un référentiel international et non une liste issue d'une RFE. Un nom non reconnu (propofol, par exemple) est traité comme une situation clinique, ce qui coûte une sous-requête de plus sans erreur. |
| `crag.py:139` (options A–D) → `:165` (A–E) ; `query.find("A.")` → position de la correspondance | **Corriger** | L'option E était ignorée, et un « A. » situé dans le stem pouvait tronquer celui-ci. |
| `crag.py:140-144` → `:167-170` (`_COMPOSITE_SPLIT_RE`) | **Généraliser** [16] | Le découpage ne se fait plus que sur une association explicite (« associée / combinée / concomitante à »). « et la pose d'un » (motif de Q16) et « et d'une » sont retirés : ce dernier découpait « hypotension et d'une bradycardie ». L'ancre préfixée aux sous-requêtes composites est retirée aussi : chaque partie est cherchée telle quelle. |
| Docstrings `crag.py:147-149, 183-187, 204-205` | **Supprimer** [14, 15, 16] | Elles citaient Q146, Q141/Q167 et Q16 mot pour mot. La méthode est gardée. |

### Pipeline — commit `d73072d` (`retrieval/pipeline.py`)

| Avant → après | Décision | Justification générique |
|---|---|---|
| `pipeline.py:559-560` (bonus `\bmain\b` +0.35) | **Supprimé** [17] | Règle anatomique ad hoc (Q09, Q15, Q143). |
| `pipeline.py:586-606` (`cond_triggers`) | **Supprimé** (voir §2) [19] | Ces déclencheurs visaient 5 lignes de tableau, toutes de la RFE ABP. |
| `pipeline.py:539` (`"v3.0"`) et `:542` (mot-clé `"pédiatri"`) → `:549-551` | **Supprimer** [20] | Il reste « historique des versions » (section de journal des modifications, structurelle) et les mots génériques de mise à jour. |
| `pipeline.py:548-558, 578-584` (« hors X » par sous-chaîne) → `:559`, `:563-567`, `:700-740` | **Généraliser** [18], I3 | (1) Seules les exclusions **entre parenthèses** `(hors X)` d'un intitulé de section sont lues, car c'est ainsi que les RFE restreignent la portée d'une section. Le « hors » d'un titre de document définit la portée du document et ne le pénalise plus : « Intubation… hors bloc » donne maintenant boost +0.30 et multiplicateur 1.0, contre −0.35 et 0.45 auparavant. (2) Tous les mots de contenu de X doivent figurer dans la question : « (hors fonction hépatique) » ne se déclenche plus sur « fonction rénale ». (3) « hors X », « hors du/de la X » et « en dehors de X » dans la question valent exclusion par la question elle-même. Les poids −0.65 et ×0.45 sont inchangés. |
| `pipeline.py:508-510` (pénalité `pediatrie` si population non précisée) | **Supprimé**, I3 | Plus d'a priori de population quand la question ne l'affirme pas. |
| `pipeline.py:340-343` (×0.72 post-rerank) → `:343-347` ; `:403` → `:407` ; `:467` → `:479` | **Corriger**, I3 | Le chunk pédiatrique n'est pénalisé ou exclu (rerank, injection 6b, rescue CRAG) que si `population == "adulte"`, et non plus dès que `population != "pediatrie"`. Exemple vérifié : « analgésie après amygdalectomie » met désormais la RFE pédiatrique en tête (BM25). |
| `pipeline.py:431` (sortie non bornée, non triée) → `:437-443` | **Corriger**, I4 | `retrieve()` renvoie au plus `final_top_k` chunks, triés par score décroissant. Les ajouts (injections 6b, rescues CRAG, encadrés, voisins) entrent en concurrence avec la sélection sur leur score au lieu de s'ajouter au-delà du budget. Exception : la comparaison d'éditions garde l'alternance « en vigueur / antérieure », pour que les deux éditions soient représentées ; elle est bornée elle aussi. Avant, `final_top_k=3` donnait 4 à 6 chunks : c'est vérifié sur `fa0426a` avec le test synthétique. |
| `import math` inutilisé | Supprimé | — |

### Lexique et routeur — commit `05362cf`

| Avant → après | Décision | Justification générique |
|---|---|---|
| `medical_lexicon.py:144-147` → `:139-149` | **Corriger** (C4) [25] | Les acronymes sont comparés **en respectant la casse**, sur des tokens entiers, tels qu'ils sont écrits dans le dictionnaire (« AOD », « ClCr »). « pas », « ira », « rac » et « iso » en minuscules ne sont plus développés. Les noms commerciaux et les synonymes de classe restent insensibles à la casse et aux accents. |
| `medical_lexicon.py:35` (`"PAS"`) | **Supprimé** | « PAS » entre en collision avec la négation écrite en capitales (« NE PAS », « PAS D'… »), et aucune règle déterministe ne sait les distinguer. « PAVM » reste. |
| `router.py:25-29` → `:22-41` (`PEDIATRIC_QUERY_RE`) | **Corriger** | Une durée nue (« 6 mois », « 3 ans ») n'est plus un âge. Un âge exige un contexte (« âgé de », « enfant de », « nourrisson de »…, < 18 ans) ou un mot de population (enfant, nourrisson, nouveau-né, adolescent…). |
| `router.py:30` (`ADULT_QUERY_RE`) | **Généraliser** | Seules les mentions explicites restent : adulte, sujet ou personne âgée, âge ≥ 18 ans. Grossesse, enceinte, césarienne et prostate sont retirées : c'était une liste ad hoc, et la population n'est plus déduite. |
| `router.py:45` → `:54-56` (modificateur `allergy`) | **Corriger** (C5) [24] | Seuls `allerg*` et `hypersensibilit*` déclenchent le modificateur. « alternative », « pénicilline », « bêtalactamine » et « intolérance » ne le font plus. |
| — → `router.py:128-157` (`detect_affirmed_allergy`) | **Nouveau** | Renvoie la phrase d'allergie *affirmée* dans la question (« allergique aux curares », « allergie à la chlorhexidine »). Il ignore les négations (« pas d'allergie », « non allergique ») et les mentions de sujet (« réaction allergique peranesthésique »). Aucun allergène n'est supposé. |
| `router.py:103-107` (domaines par sous-chaîne) → `:116` ; `loader.py:574-579` → `:562-609` (`infer_domains_from_text`) | **Corriger** (I2) | Le mot-clé doit commencer à une frontière de mot. Les sigles de ≤ 4 caractères (rac, usc, aod, alr…) doivent aussi s'y terminer. Les mots-clés plus longs restent des radicaux (« antibiothérapi », « pédiatr »). « rac » ne correspond plus à « fracture » ni à « orotrachéale », « usc » ne correspond plus à « muscle ». Le routeur en profite immédiatement. **Côté loader, la correction ne prendra effet qu'à la réindexation** : les domaines stockés dans `index/` et injectés dans le texte indexé restent faux d'ici là. |

### Sourcing et alerte allergie — commit `a5c46b3`

| Avant → après | Décision | Justification générique |
|---|---|---|
| `client.py:372-379` → `client.py:270-279` et `:424-428` | **Désactivable, désactivé par défaut** (C6) [8] | `SfarRagEngine(..., attach_provenance=False)` est la valeur par défaut, utilisée par le harnais (`cli.py:258`), par `run_e2e_eval.py` et par les scripts. Quand l'option est active, la réponse le dit : `RagResponse.extra["provenance_added_by_code"]` et `VerificationReport.provenance_added_by_code`. Ce nouveau champ optionnel remonte donc aussi dans `sfar_verification` (API OpenAI) et dans l'événement SSE `done` ; il vaut toujours `False` en streaming, qui n'ajoute rien. |
| `interfaces/api.py:362-366` → `:362-371` ; `config.py:59` | **Rétrocompatible** | L'API HTTP garde sa sortie actuelle via `Settings.api_attach_provenance=True` (variable `RAG_SFAR_API_ATTACH_PROVENANCE`). Le drapeau signale l'ajout dans `sfar_verification`. |
| `client.py:280-286` et `:436-442` (alerte « Patient ALLERGIQUE aux bêtalactamines… Ne donne PAS la molécule de 1re intention ») → `client.py:212-226` | **Généraliser** (C5) [7] | Une note neutre n'est ajoutée que si la question *affirme* une allergie : « NOTE : la question mentionne une allergie (« <phrase de la question> »). Recherche dans les extraits la conduite prévue pour ce terrain et applique-la ; si les extraits ne la précisent pas, signale-le. » Aucune classe d'allergène ni aucune consigne de molécule n'y figure. Comme avant, la note n'est active qu'avec `use_context_pruning`, pour garder la sémantique des ablations. |
| `client.py:261-286` dupliqué dans `stream_answer` → `client.py:229-267` (`generation_budget`, `build_generation_context`) | Factorisation | Un seul chemin construit le contexte de génération. Les budgets 7/5/6 chunks et 6500/5200 caractères sont inchangés et déclarés comme hyperparamètres réglés sur le jeu de développement [9]. |

### Adaptateur et interfaces — commit `1e1da9b`

| Avant → après | Décision | Justification générique |
|---|---|---|
| `benchmark_adapter.py:97-99` → `:98-102` | **Corriger** (I4) | `prune_prose=use_u_shape_ordering` était le mauvais drapeau, et aucune sélection n'était appliquée. L'adaptateur passe désormais par `build_generation_context()` : il reçoit le même contexte que `SfarRagEngine.answer` et que le harnais. La signature, `approach_id` et `build_prompt` sont inchangés. |
| `api.py:120, 144-149` (démo : Q04 et Q28 mot pour mot, réponses attendues dans les libellés) | **Supprimer** [36] | Les exemples 1 et 2 sont remplacés par des questions hors benchmark ABP (NVPO, anaphylaxie peranesthésique). Les indices de réponse disparaissent des libellés (« → Vanco/Teico », « → J-5 »…). |
| `tests/test_no_benchmark_leakage.py:111-112` (`xfail strict`) | **Retiré** | Le scan ne trouve plus rien. Le marqueur est retiré dans ce commit pour que la suite reste verte. |

### Tests — commit `fb27ad5`

| Avant → après | Décision | Justification |
|---|---|---|
| `tests/test_rag_sfar.py:567-588` (Q146 énoncé et choix, choix de Q143, énoncé de Q16) | **Remplacé** (C8) [35] | Exemples synthétiques de même structure : QCM à 5 gestes sur le bilan d'hémostase, QCM de curares (DCI + doses), association « cholécystectomie… associée à une cure de hernie », et un cas négatif « hypotension et d'une bradycardie ». |
| `test_mcq_choices_formatting_and_sourcing_scorer` (id `Q163` et ses choix) | **Remplacé** | Item synthétique `SYN-1`. |
| `test_section_allergy_box_linking_and_expansion` (fixture « hanche voie antérieure : préférer Vancomycine » = réponse de Q04) | **Retiré** de la fixture | Le test porte sur le lien encadré ↔ ligne, la phrase était inutile. |
| — → `tests/test_generic_safety.py` (15 tests) | **Ajouté** | Un test par défaut corrigé : lexique ; routeur (durée nue, âges, `alternative`/`pénicilline`/`intolérance`, négation d'allergie) ; note allergie (seulement si affirmée, neutre en classe, aussi via `build_generation_context`) ; domaines par mots ; a priori de population ; règle `(hors X)` ; borne `final_top_k` et tri (le test échoue sur `fa0426a`) ; sous-requêtes CRAG sans ID ni molécule ; sourcing ajouté seulement sur option, avec drapeau ; contexte de l'adaptateur = contexte du moteur. |

Aucun test figeant une règle ABP supprimée n'a dû être retiré. Les seuls tests concernés (CRAG composite et QCM) ont été réécrits. Le test de dé-fusion « PAS D'ANTIBIOPROPHYLAXIE » du parseur de tableaux (`test_rag_sfar.py`, partie 5) reste : il porte sur l'ingestion, hors périmètre ici (voir §3).

## 2. Supprimé faute de généralisation propre

- **`cond_triggers` / « En cas de X »** (`pipeline.py:586-606`, [19]). J'ai essayé d'extraire la condition d'une ligne « En cas de X » et de la comparer à la question, sans y arriver proprement. Une correspondance sur un seul mot de X donne un faux bonus : « hanche » suffit à promouvoir l'exception « voie antérieure » pour toute PTH, ce qui risque d'aboutir à une mauvaise molécule. Exiger tous les mots de X donne des faux malus, par exemple quand « chirurgie prothétique » est absent de la question. Les deux options sont non mesurées et risquées, j'ai donc supprimé. La règle générique de format reste dans le prompt.
- **Règle « si 2 actes associés, retiens la molécule si au moins l'un l'indique »** (`prompts.py:32`, [1]). C'est une règle de décision clinique, pas de format. Elle doit être validée par un médecin avant de revenir sous une forme générique.
- **Bonus `\bmain\b`** [17], **littéral `v3.0`** et **mot-clé « pédiatri » du bonus diff** [20] : aucune forme générique pertinente.
- **Ancre `orl` → « antibioprophylaxie »** et **ancre préfixée aux sous-requêtes composites** : pas de version générique utile. Les parties composites sont cherchées telles quelles.
- **Entrée lexique `PAS`** : la collision avec la négation française n'a pas de solution déterministe.
- **Contexte d'âge adulte** « grossesse / enceinte / césarienne / prostate » : supprimé plutôt que généralisé.

## 3. Ce qui reste à mesurer, et ce qui n'est pas traité

**À mesurer : C8-générique contre C8 (`fa0426a`)**, sur `abp171` dev et sur le jeu interne multi-RFE. Une baisse sur ABP est attendue (sur-ajustement retiré). Points d'attention :
1. **Exactitude ABP par type de question.** Questions allergie (prompt, note, CRAG), questions composites (split plus étroit, sans ancre) et QCM (ancres de stem génériques, détection DCI).
2. **Sourcing.** Il faut maintenant le mesurer sans ajout par le code : la valeur `extra.provenance_added_by_code` est disponible. Il faut aussi décider si le harnais compte comme « sourcée » une année ajoutée, comme le fait le `SourcingScorer` officiel.
3. **Retrieval.** Effets à mesurer :
   - la borne `final_top_k` (les ajouts CRAG et encadrés évincent maintenant les derniers chunks de base) ;
   - le tri de sortie, qui change l'ordre [Sx] et l'ordre en U ;
   - la suppression de la pénalité pédiatrique par défaut ;
   - la règle `(hors X)` restreinte ;
   - la fin de l'expansion « PAS ».

   Mesures utiles : Recall@k et MRR, avec un œil sur les requêtes pédiatriques sans mot « enfant ».
4. **Routeur.** Taux de faux positifs pédiatriques et allergie sur des questions adultes non allergiques, et précision des domaines inférés.
5. **Note allergie.** Effet sur les questions allergie, comparé à l'ancienne alerte, et absence d'effet sur les questions d'anaphylaxie.
6. **Domaines.** La correction `loader.py` ne s'applique qu'à la **réindexation**, à faire dans un nouveau dossier. Elle change aussi le texte indexé, puisque les domaines sont dans l'en-tête de chaque chunk.

**Non traité (hors du mandat, à décider) :**
- règles ABP de l'ingestion : `chunker.py` (`ALLERGY_BOX_RE`, « ANTIBIOPROPHYLAXIE EN », faux encadrés `**`) et `table_parser.py` (dé-fusion « pas d'antibioprophylaxie », anti-indices molécules/IVL) ; elles exigent une réindexation (I5) ;
- encadrés `callout_allergy` / `specialty_allergy_box` et `select_generation_context`, gardés et déclarés spécifiques ABP [21, 22] ;
- règle « juin-2026 / V3.0 » du loader [23] ;
- vérificateur limité à 70 molécules (C7, phase 3) ;
- stress-test `benchmarks.py` [30] ;
- démos de `scripts/` qui recopient Q03, Q04 et Q28 [36], ce répertoire n'étant pas scanné par le test anti-fuite.

**Décision à confirmer par l'équipe plateforme :** l'API HTTP garde l'ajout de la source par défaut (`RAG_SFAR_API_ATTACH_PROVENANCE=true`) pour ne pas changer sa sortie. Si la plateforme évalue via `/v1/chat/completions`, il faut soit mettre la variable à `false`, soit lire `sfar_verification.provenance_added_by_code`.
