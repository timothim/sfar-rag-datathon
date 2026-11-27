# K3 — En-têtes de tableaux hérités d'un tableau non adjacent

Date : 2026-11-27. Code : commit `261ffb2` (règle) + ce commit (mesures). Index mesuré : `index/tas_v6_tablefix` contre `index/tas_v6`. Conditions d'adoption : `JOURNAL.md`, section du 11:58 (écrites avant toute mesure). Retrieval seul, `C10_context_notes`, dev seulement ; aucun jeu de test, `genprobe` ni `genprobe2` ouvert.

## 1. Les 183 cas (lecture à la main)

Script : `K3_annexes/characterise_inheritance.py` (en mémoire, reproduit le compteur K1 : 183 = 96 ABP + 87 ailleurs, 20 documents). Étiquettes : `K3_annexes/inheritance_labels.json`.

| Groupe | Cas | Ce qui sépare le tableau de celui qui précède | Lus | Héritage juste | Héritage faux |
|---|---:|---|---:|---:|---:|
| Antibioprophylaxie (V3.0 + V3.1) | 96 | toujours un titre (`###` acte ou famille d'actes), < 100 caractères | 48 (V3.1, tous) ; V3.0 = même texte, non relu | 96 | 0 |
| Ailleurs | 87 | titre 41, texte court ≤ 300 car. 40 (titre courant de page, note, logo), paragraphe 6 ; plusieurs milliers de caractères dans les pires cas | 87 (tous) | 52 | 35 |

Dans l'ABP, il ne s'agit pas de suites de page : ce sont des sous-tableaux successifs (un par famille d'actes) qui partagent le même schéma « Actes / Molécules / Dose initiale / Réinjections / Force » ; l'héritage est juste partout, le nombre de colonnes concorde (92/96 ; 4 cas 6 → 5 par la colonne Nomenclature, déjà gérés). **Une règle de stricte contiguïté aurait retiré les en-têtes de ces 96 tableaux** (fiches « Molécules = Céfazoline » devenues « Céfazoline — 2g IVL »).

Faux ailleurs (exemples) : en-tête d'une seule cellule qui est un titre ou une cotation (« GRADE 2+ (Accord fort) » posé sur une autre recommandation, anticoagulation 2024 `…d0368c` ; « Déventilation », sécurisation 2008) ; titre de chapitre pris pour en-tête (résection hépatique 2025 `…e8bdcf`, 12 tableaux) ; ligne de données promue en-tête (« Uréthroplastie… | 9 | [6-9] », ECBU 2026 `…901bcc`) ; tableau sans rapport après un long texte (HAS transfusion 2014 `…57ad8e__c0422`, organismes sous « Âge gestationnel »).

## 2. Règle (générique, interrupteur éteint par défaut)

`RAG_SFAR_TABLE_ADJACENT_HEADERS=1` (`table_parser.ADJACENT_HEADERS`). Un tableau sans en-tête **non contigu** n'hérite que si :
1. le texte entre lui et le tableau qui le précède ne contient que des titres et **au plus 300 caractères** d'autre texte (titre courant, pied de page, note), **sans légende** « Tableau/Table/Figure/Annexe N » ;
2. le tableau qui précède n'est pas un tableau de même largeur à qui le même en-tête a été refusé (la chaîne de suites est rompue) ; un tableau d'une autre largeur ne rompt pas la chaîne ;
3. l'en-tête ressemble à des noms de colonnes : ≥ 2 cellules non vides, aucune n'étant une valeur nue (nombre, intervalle).
L'héritage entre tableaux contigus et la règle du bandeau sont inchangés. Aucune règle ne cite un document.

**Limite d'implémentation** : `chunker.py` (propriété de K2) ne transmet pas le texte entre deux tableaux. Le paramètre `continuation_gap` de `parse_html_table` est fourni, pour la construction, par `K3_annexes/gap_wrapper.py` (enveloppe en mémoire, même découpage que le chunker). Sans ce paramètre, l'interrupteur allumé retombe sur la stricte contiguïté (à ne pas utiliser : casse l'ABP). **Pour un usage en production, deux valeurs doivent être calculées au point d'appel du chunker** (texte depuis le tableau précédent, refus du précédent) : modification à faire par le propriétaire de `chunker.py`.

## 3. Construction

`index/tas_v6_tablefix` construit depuis un worktree propre du commit `261ffb2` (modifications non validées de K2 absentes), options par défaut, e5-small, surcouche du corpus ; `BUILD_NOTES.json` dans le dossier. Commande : `RAG_SFAR_TABLE_ADJACENT_HEADERS=1 HF_HUB_OFFLINE=1 scripts/with_gpu_lock.sh K3 .venv/bin/python -I <worktree>/reports/agents/K3_annexes/build_tablefix.py --corpus-dir data/sfar_recommendations/output --output-dir index/tas_v6_tablefix`. Durée : 350 s (dont 297 s d'embeddings, recalculés en entier, GPU partagé). Aucun index existant touché.

## 4. Conditions d'adoption

| # | Condition | Résultat | Verdict |
|---|---|---|---|
| 1 | Compteurs de fidélité (`ingestion_structural_checks.py`) | identiques à `tas_v6` : tableaux Markdown sur une ligne 0, unités micro 0, `\mu` 0, contradictions de population 0, blocs d'organigramme perdant des jetons 0, lignes pleine largeur perdues 0, erratums ok ; lignes non réunies 9 et jetons absents 4 (déjà 9 et 4 sur `tas_v6`) | **passe** |
| 2 | Fiches ABP modifiées : 0 dégradée | **0 fiche ABP modifiée** (0 chunk ABP changé, aucun héritage ABP retiré). Ailleurs : 172 chunks changés (118 fiches, 54 Markdown) + 4 supprimés, dans 14 documents ; 45 fiches tirées au hasard (graine 0) : **27 corrigées, 3 même sens, 15 dégradées** (`K3_annexes/changed_cards_labels_other.json`) | **passe** (ABP) ; dégradations ailleurs, voir §5 |
| 3 | Pas de régression (dev) | abpe171 suffisance 95,8 → 95,8 (Δ 0,0 [0,0 ; 0,0]), abpvern 81,2 → 81,2 (Δ 0,0 [0,0 ; 0,0]), multirfe_synth passage dans le contexte 96,1 → 96,1 (Δ 0,0 [0,0 ; 0,0], n = 76) ; 0 gagnée, 0 perdue par jeu. Contextes non identiques pour 11 / 14 / 11 questions (statistiques BM25 globales et embeddings recalculés) sans effet sur les métriques | **passe** |
| 4 | Compteur K1 « en-têtes hérités d'un tableau non adjacent » en baisse | 183 → 138 (ABP 96 → 96, ailleurs 87 → 42). Sur les 87 cas hors ABP : 33 faux corrigés sur 35, 40 justes gardés sur 52 ; dans l'ABP 96 justes gardés sur 96. Héritages contigus : 299 → 299 | **passe** |
| 5 | Tests, anti-fuite, gelé inchangé | 244 passés, 1 ignoré ; anti-fuite silencieux ; test `tests/test_k3_table_headers.py` : interrupteur éteint = sortie du parseur identique à l'octet à l'ancien code sur 12 documents (empreintes `tests/fixtures/k3_table_parser_baseline_digests.json`) ; fichiers du retrieval non modifiés | **passe** |

## 5. Ce qui empire

15 des 45 fiches échantillonnées perdent des noms de colonnes **justes** (aucune ne reçoit un nom faux) : tableaux de stratégie de recherche du sepsis 2025 (`…a5219e__c0531`, `c0534`… : « Type d'étude / Période / Nombre de références » séparés par plus de 300 caractères d'équations de recherche), tableau de cotation de la relecture ECBU (`…901bcc__c0774`–`c0782` : « Médiane / Distribution… »), tableau de références ECBU (`c0190`–`c0193`). Les valeurs restent, sans étiquette (« Méta analyses — 01/2010-07/2023 — 322 »). Restent faux : 2 tableaux (argumentaire résection hépatique `…2e42b6`, en-tête « Prise en charge… | GRADE | » à deux cellules non vides). Le correctif échange donc 33 étiquettes fausses contre 12 tableaux privés d'étiquettes justes ; l'échantillon et les étiquettes sont lus par un agent, pas par un médecin.

## 6. Recommandation

- **Antibioprophylaxie : rien ne change** (0 chunk, 0 fiche, mêmes métriques) ; la règle garde les 96 héritages, tous justes. Aucun risque à l'adopter pour ce document ; aucun bénéfice non plus.
- Hors ABP : corrige les cas cliniquement trompeurs (cotation d'une autre recommandation, titre pris pour en-tête, liste d'organismes sous « Âge gestationnel »), au prix d'étiquettes justes perdues dans des tableaux de méthodologie. Toutes les conditions pré-déclarées passent. Adoption = décision de l'orchestrateur ; elle suppose que le calcul de `continuation_gap` soit porté dans `chunker.py`, puis une reconstruction et une vérification que la sortie est identique à `tas_v6_tablefix`.

Fichiers : `K3_annexes/` (scripts, résumés JSON, étiquettes, `retrieval_summary.json`, `retrieval_rows.jsonl`, `compare_chunks.json`, `structural_*.json`). Les extraits de texte servant à la lecture (`*.local.json`) ne sont pas versionnés.
