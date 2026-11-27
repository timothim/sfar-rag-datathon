# K2 — Découpage adapté aux recommandations gradées : `index/tas_v7`

Date : 2026-11-27. Agent K2 (Opus). Fichier modifié : `src/rag_sfar/ingestion/chunker.py` (seul). Index construit : `index/tas_v7` (nouveau dossier ; aucun autre index touché). Scripts et sorties : `reports/agents/K2_annexes/`. Conditions d'adoption : celles écrites avant toute mesure dans `JOURNAL.md` (11:58). Aucun split test, ni `genprobe`/`genprobe2`, n'a été ouvert.

## Correctifs (chacun derrière son interrupteur, éteint par défaut)

| Interrupteur (variable d'environnement) | Défaut K1 | Règle (forme du texte seulement) | Fait |
|---|---|---|---|
| `RAG_SFAR_CHUNK_GRADE_HEADINGS=1` (`grade_heading_as_text`) | D1 | Un titre Markdown dont tout le contenu est une ligne de cotation (vocabulaire de cotation, chiffres, signes, ponctuation ; ≤ 90 car.) reste dans le texte, en gras, au lieu de devenir un titre de section | oui |
| `RAG_SFAR_CHUNK_GRADES=1` (`extended_grades`) | D3 (cotations) | Formats G1+/G2−, (1+), grade A/B/C, accord relatif/professionnel, (AE) lus dans `grade_levels` ; un paragraphe contenant une formule de recommandation (« il est (probablement) recommandé », « il n'est pas recommandé », « les experts suggèrent/recommandent/proposent ») **suivie** d'une cotation, hors guillemets, est typé `recommendation_box` (donc jamais « note ») | oui |
| `RAG_SFAR_CHUNK_REC_IDS=1` (`extended_rec_ids`) | D3 (numéros) | Identifiants « R 1.1 », « R1 – », « Recommandation 3 » en début de ligne | oui |
| `RAG_SFAR_CHUNK_BIBLIO=1` (`unheaded_biblio`) | bibliographies | Un morceau de prose fait d'au moins 3 lignes de citation (référence de revue « 2015;12:45 », DOI, ou entrée « [n] Auteur AB, … ») formant au moins la moitié des lignes, sans contenu clinique, est marqué `references` | oui, **avec un défaut (voir plus bas)** |
| — | D4 (plusieurs énoncés par passage) | — | **non fait** |

Les interrupteurs sont aussi des champs de `ChunkOptions` (donc écrits dans `manifest.json` → `chunker_options`). Aucun fichier partagé modifié.

## Construction

```bash
env -u RAG_SFAR_TABLE_ADJACENT_HEADERS HF_HUB_OFFLINE=1 RAG_SFAR_CHUNK_GRADE_HEADINGS=1 RAG_SFAR_CHUNK_GRADES=1 \
  RAG_SFAR_CHUNK_REC_IDS=1 RAG_SFAR_CHUNK_BIBLIO=1 \
  scripts/with_gpu_lock.sh K2 .venv/bin/rag-sfar-index --strategy table_aware_sota --output-dir index/tas_v7
```

Construction complète (sans réutilisation des embeddings : 4 min 35 s, dont ~3 min 45 d'embeddings), même commande que `tas_v6` hormis les interrupteurs ; correctif de K3 éteint. `index/tas_v7/BUILD_NOTES.json` décrit la construction. 36 837 passages (`tas_v6` : 36 872).

## Conditions d'adoption

| # | Condition | Résultat | Verdict |
|---|---|---|---|
| 1 | Compteurs de fidélité de `ingestion_structural_checks.py` à 0 | Tous à 0 et identiques à `tas_v6` (tokens de tableaux manquants 4 = 4, texte non couvert 0,17 % = 0,17 %, résidus identiques) | **passe** |
| 2 | ABP en vigueur (`…V3_1…642ad1`) identique sauf passages visés | 824 identiques, **1 changé** (type), 0 ajouté, 0 retiré, 0 chemin de section changé. Le changé, lu : `…642ad1__c0417_c3f5971b`, énoncé « il est recommandé d'administrer une antibioprophylaxie… [Recommandation forte / …] » (césarienne), `prose` → `recommendation_box` : visé par la règle `extended_grades` | **passe** |
| 3 | Pas de régression (dev, C10_context_notes, k = 64) | voir tableau ci-dessous : 0 question perdue, bornes basses à 0 | **passe** |
| 4 | Compteurs de structure K1 en hausse | voir tableau ci-dessous | **passe** (sauf D4, inchangé) |
| 5 | Tests verts, anti-fuite silencieux, gelés inchangés | `pytest -q` : 244 passés, 1 ignoré (dont `test_no_benchmark_leakage`) ; nouveau `tests/test_k2_graded_chunking.py` : interrupteurs éteints → sortie **identique à l'octet** au chunker d'avant sur les **265 documents** (empreintes dans `tests/fixtures/`), plus règles sur texte synthétique. Aucun fichier du retrieval, de la génération, de `config.py`, `cli.py` ou `table_parser.py` modifié par K2 | **passe** |

### Retrieval (condition 3) — `analyze_retrieval.py`, `retrieval_summary.json`

| Jeu (dev) | Métrique | n | tas_v6 | tas_v7 | Écart [IC 95 % apparié] | Gagnées / perdues |
|---|---|---:|---:|---:|---|---|
| abpe171 | suffisance | 96 | 95,8 | 96,9 | +1,0 [0,0 ; +3,1] | Q07 / aucune |
| abpvern (formulation des cliniciens) | suffisance | 96 | 81,2 | 82,3 | +1,0 [0,0 ; +3,1] | Q07 / aucune |
| multirfe_synth | passage dans le contexte | 76 | 96,1 | 96,1 | 0,0 [0,0 ; 0,0] | aucune / aucune |

Un gain d'une question n'est pas une amélioration démontrée (bruit) ; la condition demandait l'absence de perte.

### Structure (condition 4) — `structure_counters.py` (expressions de K1), tout le corpus

| Compteur | tas_v6 | tas_v7 |
|---|---:|---:|
| Énoncés numérotés avec leur cotation dans le même passage (tous) | 1 350 / 1 698 | **1 409 / 1 698** |
| … classe G1 (RFE gradées numérotées) | 1 038 / 1 299 (79,9 %) | **1 097 / 1 299 (84,4 %)** |
| Passages sous un titre de cotation | 574 | **34** |
| Énoncés typés recommandation (tous / G1) | 1 080 / 906 | **1 432 / 1 131** |
| Énoncés typés « note » | 29 | **3** |
| Passages de bibliographie non signalés | 1 107 | **457** |
| Passages à ≥ 2 énoncés (dont cotations différentes) | 324 (114) | 324 (115) |

Sonde de 64 requêtes de K1 (mêmes requêtes, relancée sur les deux index avec le même code) :

| | tas_v6 | tas_v7 |
|---|---:|---:|
| Énoncé dans le contexte | 63 | 63 |
| … servi comme recommandation / texte / note | 43 / 18 / 2 | **58 / 5 / 0** |
| … sans sa cotation | 19 | **12** |
| Rang 1 / rang ≤ 3 | 37 / 50 | 36 / 51 |
| Requêtes avec ≥ 1 passage surtout bibliographique dans le contexte | 34 | **26** |

(K1 avait rapporté 15 énoncés sans cotation ; la relance du même script sur `tas_v6` donne 19 ; les autres chiffres de K1 sont reproduits.)

## Exemples (énoncé qui porte désormais sa propre cotation)

| Document, passage | tas_v6 | tas_v7 |
|---|---|---|
| ALR pédiatrique 2026, `…63f95f__c0054_9cb303dc` (R1.1.1) | `prose`, `grade_levels` vide ; la cotation était le titre de section du passage suivant | `recommendation_box`, « GRADE 1 (recommandation forte) » dans le passage, juste après l'énoncé |
| Pré-éclampsie 2020, R2.10 (`…8989f8__c0070` → `__c0069_5146fde6`) | section « … > Avis d'experts (Accord FORT) » au-dessus d'un énoncé GRADE 1− | section « Champ 2 : PRISE EN CHARGE THERAPEUTIQUE », cotation GRADE 1− dans le texte |
| TC léger 2022, `…9c1d68__c0042_206c03f0` (R2.2.1) | section « Question 2.1 … > Avis d'experts (Accord Fort) » | la cotation sort du chemin ; **mais le chemin reste « Question 2.1 »** (la question 2.2 n'est pas un titre dans la source : défaut non traité) |

## Ce qui s'est dégradé ou reste faux

- **Règle bibliographie : 105 passages mixtes cachés.** Sur les 639 passages nouvellement marqués `references` (donc exclus de la recherche), 105 contiennent aussi une ligne de prose ≥ 120 caractères (25 239 caractères au total ; ids dans `K2_annexes/biblio_mixed_chunks.json`). Exemple : `2024_RPP-RH-AR-validee-CA-SFAR-191224-_994758__c0022_6db0903b`, une phrase d'organisation suivie de 4 références. Correctif nommé, non appliqué faute de temps : exiger que toute ligne non-citation soit courte. **Tant qu'il n'est pas fait, ne pas adopter `RAG_SFAR_CHUNK_BIBLIO`** ; les trois autres interrupteurs sont indépendants.
- **Une référence unique servie comme prose** : `rpp-urgences-obstetricales-en-medecine-durgence` (`…32dd15`, passage 66) : un titre de cotation qui fermait auparavant la section « Référence » ne la ferme plus. 1 cas.
- 34 passages restent sous un titre de cotation (titres que la règle ne reconnaît pas comme cotation seule).
- Les chemins de section restent faux quand la question suivante n'est pas un titre (exemple TC léger ci-dessus).
- La règle « formule + cotation » a été resserrée **avant la construction et avant toute mesure de dev** après lecture des passages modifiés de l'ABP (des paragraphes de méthode citant « GRADE 1 « il est recommandé… » » et des argumentaires avec « et al. » étaient retypés) : formule hors guillemets, cotation après la formule ; lignes de citation au lieu de marqueurs de citation.

## Non fait

- D4 : couper aux frontières d'énoncés (passages à plusieurs énoncés de cotations différentes, en-tête qui liste toutes les cotations).
- Réutilisation des embeddings des passages inchangés (construction complète, 4 min 35).
- Correctif des passages bibliographiques mixtes ; relecture par un médecin ; lecture de tous les passages modifiés hors ABP (échantillons seulement).

## Fichiers

`src/rag_sfar/ingestion/chunker.py` ; `tests/test_k2_graded_chunking.py`, `tests/fixtures/k2_chunker_baseline_hashes.json` ; `reports/agents/K2_annexes/` : `diff_chunks.py` (+ `diff_v6_v7.json`), `structure_counters.py` (+ `.json`), `run_retrieval_v7.py`, `analyze_retrieval.py` (+ `retrieval_rows.jsonl`, ids et métriques seulement, `retrieval_summary.json`), `probe_v7.py` (+ résumés `probe_tas_v6/`, `probe_tas_v7/`), `structural_checks_tas_v6.json`, `structural_checks_tas_v7.json`, `snapshot_baseline.py`, `gpu_jobs.sh`, journaux. `index/tas_v7/BUILD_NOTES.json` (non versionné, comme l'index).
