# X1 — Liens structurels entre chunks (contreparties de population, notes de tableau)

Agent X1, 2026-11-27. Retrieval figé inchangé (`C10_context_notes`, `index/tas_v6`, tag `retrieval-freeze-20261127`) : aucun fichier de `retrieval/pipeline.py`, `config.py`, `ingestion/` ni de l'index n'a été modifié. Tout ce qui suit est une étape de post-traitement, **désactivée par défaut**. Aucun appel API (coût 0 $). Mesures : dev seulement (`abpe171`, `multirfe_synth`) ; aucun jeu test, ni `genprobe`, ni `genprobe2` n'a été ouvert.

## 0. Résumé

- **Contreparties de population** : avec une règle stricte (même document, tableaux de populations différentes étiquetées au niveau du tableau ou de la section, même en-tête de colonne d'acte, **tous les actes de la ligne source présents dans la ligne cible**), on obtient **42 liens, tous dans la RFE antibioprophylaxie 2026**, **42/42 corrects à la lecture** (même acte, autre population). **Couverture : 39 lignes sources sur 371 lignes « liables » (10,5 %)** ; adulte 18/202, pédiatrie 21/140, néonatal 0/13, obstétrique 0/8.
- La structure « un tableau par population, mêmes lignes » **n'existe, dans l'index, que dans l'ABP** : hors ABP, aucune paire de lignes de même libellé dans deux tableaux de populations différentes (vérifié aussi sans étiquette de population : les seuls libellés répétés hors ABP sont des citations d'études ou des tableaux de même population présentés selon deux axes). L'échantillon demandé (≥ 60 liens, ≥ 5 RFE) est donc impossible ; j'ai lu les 42 liens stricts **et** les 34 liens qu'ajouterait une règle lâche (≥ 1 acte commun), soit **76 liens lus**.
- **Effet sur dev : nul.** Version retenue (lien suivi seulement depuis une ligne classée dans les 8 premiers dont la question nomme l'acte) : se déclenche sur **1/102** questions abpe171 et **0/94** multirfe, ajoute 1 ligne (bonne procédure, bonne population, utile), **sufficiency 95,8 → 95,8 (Δ 0 [0 ; 0])**, rappel des preuves 98,2 → 98,2, passage hit multirfe 96,1 → 96,1. Même résultat nul sur des bases plus faibles (C9, C9 + fenêtres) où des contreparties manquent : les preuves pédiatriques manquantes **ne sont pas des cibles de liens**, parce que les tableaux pédiatriques regroupent et nomment les actes autrement que les tableaux adultes.
- **Notes de tableau** : la lecture figée (`called_scope`) des 8 premiers résultats est déjà complète sur dev (le lien supplémentaire « note en italique » ne se déclenche sur aucune question). 10 liens de note manquants trouvés dans le corpus, 1 RFE, 10/10 corrects. Étendre les notes aux rangs 9–16 : 36 questions, 52 notes, surtout la note de périmètre pédiatrique déjà imprimée dans la fiche, +246 caractères par question, aucun gain.
- **Recommandation : ne pas retenir ces étapes comme candidates pour l'exécution unique sur `genprobe2`.** Elles sont sûres (précision lue 100 % en version stricte) mais n'atteignent pas l'échec observé au test : il faudrait relier des lignes dont les libellés diffèrent (« chirurgie colorectale » pédiatrique vs actes coliques adultes), ce qu'aucune règle d'égalité de libellé ne fait sans une table de correspondance d'actes. Le code reste disponible, désactivé.

## 1. Construction des liens (`scripts/build_chunk_links.py` → `index/tas_v6_links/`)

Lecture seule de `index/tas_v6/metadata.sqlite` ; écriture de `links.json` et `manifest.json` (hachages de l'index source : `metadata.sqlite` `3bb49ae9…`, `manifest.json` `829f9fa3…` = manifeste figé ; commit, date, paramètres, effectifs). Ni LLM, ni embedding, ni recherche.

### 1.1 Contreparties

| Règle | Raison (structure générale des RFE) |
|---|---|
| même `doc_id`, édition en vigueur, active | une contrepartie appartient à la même recommandation |
| population de chaque ligne = une seule classe (adulte / pédiatrie / néonatal / obstétrique) **issue du tableau ou de la section** (`population_source` ∈ {table, section}) | une étiquette au niveau du document ne distingue pas deux tableaux du même document |
| `table_id` différent, classe différente | sinon ce n'est pas un tableau parallèle |
| même en-tête de la colonne d'acte (premier segment normalisé) | deux tableaux sont parallèles quand leur colonne de libellé est la même |
| libellé découpé en actes (« ; ») ; **tous les actes de la source se retrouvent, normalisés, dans la cible** | la ligne ajoutée couvre chaque acte nommé par la ligne retrouvée : elle ne peut pas apporter la dose d'un acte que la ligne source ne nomme pas |
| au plus 2 cibles par (source, population) ; au-delà, lien ambigu abandonné ; doublons de fiches (même ligne imprimée deux fois) liés une seule fois | préférer manquer un lien |
| libellé informatif (un acte de ≥ 6 caractères avec un mot de ≥ 4 lettres) | pas de lien sur un libellé vide ou numérique |

Effectifs (`manifest.json`) : 8 368 fiches ligne en vigueur ; 886 avec une population unique de tableau ou de section ; 542 liables ; **39 sources, 42 liens** (adulte → pédiatrie 16 exacts + 3 inclusions ; pédiatrie → adulte 16 + 7) ; 0 lien néonatal ou obstétrical (les libellés néonataux diffèrent : « DVE ; DVI » vs « DVI ; DVP »).

Par RFE : antibioprophylaxie 2026 (V3.1) : 42 ; toutes les autres : 0. Documents qui ont au moins deux classes de population au niveau des tableaux ou des sections : ABP, transfusion de globules rouges (HAS 2014), antalgie post-amygdalectomie (2014), tableaux douleur postopératoire (2016), voies aériennes 2026 (3 lignes obstétricales), RPP cardiopathies congénitales, sepsis 2025 — aucun n'a de lignes de même acte d'un tableau à l'autre (scores, échelles, études, sommaires).

### 1.2 Précision lue (`reports/agents/X1_annexes/counterpart_links_read.txt`, `loose_links_read.txt`)

- **Règle stricte, 42 liens : 42 corrects** (même acte, population différente, ligne complète avec molécule et dose de l'autre population). Un cas à signaler sans être une erreur de lien : la ligne adulte « Ponction de lésion kystique pancréatique sans facteur de risque ; … avec facteur(s) de risque ; … » porte une seule molécule pour six actes dans le tableau source lui-même ; le lien depuis la ligne pédiatrique « sans facteur de risque — pas d'antibioprophylaxie » la ramène telle qu'imprimée.
- **Règle lâche (≥ 1 acte commun), 34 liens de plus** : 6 copies de liens stricts (ligne imprimée deux fois), 6 jeux d'actes quasi identiques à une formulation près (« chirurgie de paroi thoracique (avec ou sans pose de matériel) » vs « chirurgie de la paroi thoracique »), **22 partiels** : la cible ne couvre qu'un acte d'une ligne qui en nomme plusieurs, ou deux listes différentes partagent un seul acte (ex. dérivations ventriculaires pédiatriques ↔ néonatales ; ostéosynthèse/plaie articulaire ↔ plaie articulaire seule). Pour une question portant sur un autre acte de la ligne, ces liens apporteraient la dose d'un autre acte : **précision 12/34 (35 %)** → règle lâche rejetée.
- **Couverture** : sur les 371 lignes liables des documents à plusieurs populations, 39 ont un lien (10,5 %). La faiblesse vient du corpus : les tableaux pédiatriques ne reprennent pas ligne à ligne les tableaux adultes (regroupements et intitulés différents, actes propres à l'enfant). La version distribuée de l'ABP est « sans code CCAM » : un code d'acte commun aurait été l'identifiant structurel naturel.

### 1.3 Notes et en-têtes

Audit des 284 fiches ligne en vigueur qui contiennent une marque d'appel (`notes_audit.py`) :
- 196 impriment déjà leur note dans la fiche (« Note (*) : … », ingestion `tas_v6`) ; l'en-tête de colonne est dans chaque cellule (« En-tête : valeur ») ; la note de périmètre est dans la ligne « Périmètre : » des fiches ABP pédiatriques ; le titre du tableau dans « Tableau : ». Rien à ajouter pour ces cas.
- 96 gardent au moins une marque sans note trouvée par la lecture figée (98 marques). Causes : 50 marques sans note de même marque dans les 40 chunks suivants (fausses marques comme « 2*âge », marques changées à la conversion) ; 17 dont la note candidate est après un autre tableau (non suivi : ambigu) ; 31 dont un chunk de note suit le tableau mais n'est pas reconnu : note **en italique** (« *\*en cas d'insuffisance rénale … » ), que `_note_marks` ne lit pas, ou référence bibliographique.
- Le constructeur ajoute ces notes (lecteur de marques échappées, même parcours que la lecture figée, mêmes exclusions + exclusion des notes qui sont des références bibliographiques « volume(numéro) : pages », ajoutée après lecture de 10 liens vers une référence « *Maisels … J Perinatol » dans la RBP transfusion). **10 liens, 1 RFE (anticoagulants et procédures programmées 2026), 10/10 corrects** (note « en cas d'insuffisance rénale, se référer au chapitre dédié » appelée par les recommandations d'arrêt ou de relais des AOD/AVK).
- Utilisation par le retrieval figé : `called_scope` n'attache les notes qu'aux 8 premiers résultats classés (`context_window_top`). Sur dev, les liens « italique » ne se déclenchent jamais dans ces 8 premiers ; la complétion aux rangs 9–16 est mesurée au §3.

## 2. Suivi des liens (`src/rag_sfar/retrieval/links.py`)

`LinkedRetriever(base, Path("index/tas_v6_links"), LinkPolicy(...))` a la même interface `retrieve(query, config, ...)` ; `apply_links(...)` s'applique aussi directement à la sortie de `retrieve`. `LinkPolicy()` par défaut : tout désactivé, sortie inchangée (vérifié §4). La sidecar est refusée si elle a été construite depuis un autre index (hachage du manifeste).

Politique (option `counterparts=True`) et justification :
- **Ancres** : résultats classés (pas les fenêtres), fiches ligne, dans les **8 premiers** (même profondeur que les fenêtres de la configuration figée).
- **La question doit nommer l'acte de l'ancre** (`anchor_must_match_query`) : au moins min(2, n) des n mots discriminants du libellé de l'ancre (mots rares parmi les libellés d'actes de la même RFE, fréquence ≤ 5 %, racines de 5 lettres, calculés hors ligne). Raison : sans ce filtre, sur dev, 4 des 7 ajouts étaient la contrepartie d'une ligne classée **hors sujet** (neurochirurgie trans-sphénoïdale pour une question de PMA, glandes salivaires pour une prothèse de genou, escarrotomie pour une brachioplastie) : une deuxième dose hors sujet. Ce filtre a été ajouté après avoir lu ces ajouts sur dev ; il ne contient aucun terme d'acte (il est calculé sur le corpus), mais sa nécessité a été vue sur dev : à noter.
- **Population** : question sans population (ou « mixte ») → toutes les populations ; question adulte → adulte/obstétrique ; question pédiatrique → pédiatrie/néonatal, affiné par l'âge (`_query_subpopulation` du retrieval : « 8 ans » exclut le néonatal, « J5 de vie » exclut l'enfant). Une question qui nomme une population ne reçoit jamais la ligne d'une autre.
- **Quantité** : au plus 1 ligne par population cible et par ancre, 2 par ancre, 4 par question ; rien si la ligne est déjà lisible (même chunk, même texte, ou son tableau Markdown contenant le libellé déjà dans le contexte) ; seulement la ligne (ni voisins, ni tableau) ; dans le budget de caractères de la configuration (30 000).
- **Placement et marquage** : juste après le bloc de l'ancre (ancre + ses fenêtres), `expansion_reason = "counterpart:<population>"`. Dans le contexte structuré, la ligne n'est pas contiguë à l'ancre et forme sa propre source, avec son en-tête « Population : pediatrie » et sa section (« … PEDIATRIQUE »), et la ligne « Périmètre » de la fiche.
- Option `notes=True` : notes appelées (lecture figée + liens « italique ») des 16 résultats classés de type tableau et des lignes ajoutées.

## 3. Mesures sur dev (retrieval seul, `tas_v6`)

Base : `C10_context_notes` rejouée par X1 (`res/base__*.json.gz`) : **102/102 et 94/94 contextes identiques** aux lignes figées de B1 (`tas_v6_F0`) ; sufficiency 95,8, passage hit 96,1 (reproduits). L'étape est une fonction pure (sortie du retriever, question, index) : mesure hors ligne exacte (`offline_eval.py`), confirmée en ligne (§4). IC : bootstrap apparié (2 000), b − a.

| Variante (contre C10 figé) | abpe171 sufficiency | rappel des preuves | multirfe passage hit | Questions où ça se déclenche (abpe / multirfe) | Ajouts | Ajouts bonne procédure et population | Ajouts hors sujet | Car. ajoutés / question déclenchée |
|---|---|---|---|---|---|---|---|---|
| C10 figé | 95,8 | 98,2 | 96,1 | — | — | — | — | — |
| **contreparties (retenue)** | 95,8 (Δ 0 [0 ; 0]) | 98,2 (0 [0 ; 0]) | 96,1 (0) | **1 / 0** | 1 | 1 (Q42, ligne pédiatrique d'une question pédiatrique) | 0 | 920 |
| contreparties sans filtre d'ancre | 95,8 (0 [0 ; 0]) | 98,2 (0) | 96,1 (0) | 7 / 0 | 7 | 3 (Q42, Q62, Q138 : la ligne pédiatrique de l'acte demandé) | **4** (contrepartie d'une ligne hors sujet) | 792 |
| notes rangs 1–16 | 95,8 (0 [0 ; 0]) | 98,2 (0) | 96,1 (0) | 36 / 1 | 52 + 1 notes | — | surtout la note de périmètre pédiatrique déjà imprimée dans la fiche (redondante) | 697 |
| notes rangs 1–8 (liens « italique » seuls) | 95,8 | 98,2 | 96,1 | 0 / 0 | 0 | — | — | 0 |
| contreparties + notes | 95,8 (0) | 98,2 (0) | 96,1 (0) | 36 / 1 | 1 + 52 | — | — | 722 |

Par sous-groupe (contreparties retenues) : tag `pediatric` (n = 34) 94,1 → 94,1 ; non pédiatrique (n = 62) 96,8 → 96,8 ; question sans population (n = 84) 96,4 → 96,4 ; population nommée (n = 12) 91,7 → 91,7 (Δ = 0 partout). Contexte moyen : 20 342 → 20 351 caractères (abpe171), inchangé sur multirfe.

**Bases plus faibles (analyse de sensibilité)** : appliquée aux sorties figées de B1 pour C9 (sufficiency 88,5 ; pédiatrique 82,4) et C9 + fenêtres (92,7 ; 85,3) : se déclenche sur 1 question (9 sans filtre d'ancre), **Δ = 0** partout. Explication (`reach.py`) : sur les 16 preuves manquantes de C9 dans les questions insuffisantes, **12 ne sont la cible d'aucun lien** (la ligne pédiatrique a un autre libellé que toute ligne adulte : « chirurgie cardiaque avec CEC (…) ; transplantation cardiaque … » vs les actes cardiaques adultes ; « chirurgie colorectale, incluant les plasties coliques » ; « traumatologie maxillo-faciale avec abord endobuccal … ») et 4 sont des cibles dont aucune source n'est dans le contexte. Sur C10 : 5 non-cibles, 1 sans source. Ce mécanisme ne peut donc pas corriger l'échec du test (69 % de suffisance pédiatrique), dont la forme typique est justement celle-là.

Latence : +1,6 ms médiane pour l'étape (§4) ; pas de recherche, pas de modèle.

## 4. Reproductibilité et non-régression

- `tests/test_x1_links.py` (dans la suite standard, 193 tests verts, test anti-fuite silencieux) : règles du constructeur sur des chunks synthétiques (inclusion, en-tête, population de document refusée, ambiguïté abandonnée, marques en italique) ; politique (désactivée = même liste ; ajout après le bloc de l'ancre ; population nommée respectée ; ancre non nommée par la question ignorée ; déjà visible / budget dépassé → rien) ; **sur les 40 premières sorties figées de dev (`tas_v6_F0`) : étape désactivée = mêmes chunks ; activée = tous les chunks figés conservés dans leur ordre**.
- Test lent (`RAG_SFAR_SLOW_TESTS=1`, sous verrou GPU) : retriever figé réel enveloppé, étape désactivée → mêmes chunks que les sorties figées sur 12 questions dev. Résultat : **1 passed** (12/12 identiques).
- Exécution en ligne sous verrou (`online_job.sh`) : enveloppe désactivée → **102/102 et 94/94 contextes identiques** au C10 figé ; contreparties activées → 1 contexte modifié (abpe171), 0 (multirfe), exactement les questions prévues hors ligne ; contreparties + notes → 36 et 1 contextes modifiés, idem hors ligne ; métriques identiques au calcul hors ligne. Latence médiane de bout en bout : 190 ms (figé) → 193 ms (contreparties) / 192 ms (contreparties + notes), dans le bruit de la machine partagée ; coût propre de l'étape 1,6 ms médiane (max 4,8 ms).

## 5. Ce que ça ne peut pas faire

- Relier deux lignes d'un même acte formulées différemment selon la population (cas majoritaire dans l'ABP et cause des échecs pédiatriques) : il faudrait une table de correspondance d'actes (code CCAM ou annotation experte), pas une règle de libellé.
- Agir hors ABP : aucune autre RFE de l'index n'a de tableaux parallèles par population.
- Relier des notes placées après un autre tableau, ou dont la marque a été modifiée à la conversion PDF → Markdown.
- Le filtre « la question nomme l'acte » repose sur des mots du libellé : une question formulée avec un synonyme (« greffe » pour « autogreffe ») ne déclenche pas le lien. C'est voulu (préférer manquer), mais limite encore la portée.

## 6. Activer

```bash
.venv/bin/python scripts/build_chunk_links.py --index index/tas_v6 --out index/tas_v6_links   # déjà fait
```
```python
from pathlib import Path
from rag_sfar.retrieval.links import LinkedRetriever, LinkPolicy
retriever = LinkedRetriever(base_retriever, Path("index/tas_v6_links"), LinkPolicy(counterparts=True))
# notes rangs 1–16 en plus : LinkPolicy(counterparts=True, notes=True)
```
Rien n'est branché dans le profil de production, l'API ou `ablation.py`.

## 7. Fichiers

- `scripts/build_chunk_links.py` ; `index/tas_v6_links/{links.json, manifest.json}` (non versionnés, comme `index/`) ;
- `src/rag_sfar/retrieval/links.py` ; `tests/test_x1_links.py` ;
- `reports/agents/X1_annexes/` : `capture.py` (rejeu en ligne), `offline_eval.py` (mesures, IC), `reach.py` (atteignabilité des preuves manquantes), `notes_audit.py`, `hidden_parallel.py`, `loose_links.py`, `dump_links.py`, lectures `counterpart_links_read.txt`, `loose_links_read.txt`, `note_links_read.txt`, résultats `res/`.
