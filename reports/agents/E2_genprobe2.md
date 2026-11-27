# E2 — Sonde tenue à l'écart `genprobe2` (2026-11-27)

**Statut : outil interne de développement. 60 questions synthétiques, écrites et relues par un LLM (Claude Opus 5.5), non validées par un médecin. Ce n'est pas un benchmark.** Scellée (`eval_internal/splits/genprobe2/SEALED.md`, SHA-256 `76be3ccd020efec13f0913c608ac24fb19f1e84cb9da76b3d20f6e641e5ca255`). À exécuter une seule fois, sur les configurations finales ; chaque exécution est consignée dans `JOURNAL.md`. Exclue de `--suite full` (`HELD_OUT_SUITES`).

## Pourquoi

L'évaluation finale a épuisé les jeux tenus à l'écart et a montré trois faiblesses du retrieval : réponses qui exigent deux passages éloignés ; ligne propre à une population (enfant, nouveau-né, femme enceinte) supplantée par la ligne adulte, ou l'inverse ; lignes de tableau dont le sens dépend d'une note, d'une portée ou d'un en-tête. `genprobe2` mesure ces trois cas, plus des contrôles, avant que les nouveaux mécanismes soient évalués.

**Indépendance.** Ni moi ni les sous-agents n'avons lu `src/rag_sfar/retrieval/`, les rapports B1, R2, Q1, X1 ou X2, ni aucun fichier de questions existant (`genprobe` compris). Aucun retrieval, aucun modèle, aucun calcul GPU n'a été lancé sur ces questions.

## Composition

| Famille | Sous-type | n |
|---|---|---|
| `fam:two_source` | `two_documents` (deux RFE) | 10 |
| | `two_sections` (deux sections éloignées d'une RFE longue) | 10 |
| `fam:population` | `population_specific` (enfant, nouveau-né ou femme enceinte nommé) | 8 |
| | `population_adult` (adulte nommé ; ligne pédiatrique interdite) | 6 |
| | `population_unspecified` (aucune population ; les deux lignes requises, `conditional_or_clarification`) | 6 |
| `fam:table_note` | `note_footnote` | 5 |
| | `note_scope` | 4 |
| | `note_header` | 3 |
| `fam:control` | `control` | 8 |

- **RFE** : 49 titres distincts en vigueur (`is_latest_edition = 1` dans `index/tas_v6`), de 2002 à 2026. Au plus 3 questions par RFE, sauf l'antibioprophylaxie (7 : 6 en famille population, 1 en deux sources).
- **Famille population** : 11 RFE. Population visée : `pediatric` 12, `neonate` 4, `pregnancy` 3, `adult` 14 (tags cumulés). La ligne de l'autre population est dans `meta.counterpart_quotes`, vérifiée verbatim. Quand elle serait une erreur, elle figure aussi dans `forbidden_claims`.
- **Tableaux** : 25 questions ont au moins une preuve qui est une ligne de tableau.
- **Format** : chaque question a `gold_doc_ids`, `gold_passages` (citations de 8 à 40 mots ; lignes de tableau cellule par cellule, séparées par « ‖ »), `evidence`, `evidence_sets`, `mandatory_claims` et, le cas échéant, `forbidden_claims`. On y trouve aussi `provenance = llm_synthetic`, `suite = genprobe2` et `meta.author = "claude-opus (agent E2)"`. Les questions sans population ont `expected_behavior = "clarification"` et `meta.expected_behavior = "conditional_or_clarification"`.
- **Ensembles alternatifs** : certaines questions ont un second ensemble de preuves quand un autre passage suffit aussi. Exemples : version longue et version courte d'une même RFE, fiche de synthèse.

## Méthode

1. **Rédaction.** Trois sous-agents ont rédigé, chacun sur une liste de RFE disjointe. Le premier a écrit les 20 questions à deux sources, le deuxième les 20 questions population, le troisième les 12 questions note de tableau et les 8 contrôles. La consigne commune est dans `eval_internal/work/genprobe2/AUTHOR_BRIEF.md`. Pour chaque question à deux sources, `meta.necessity_note` dit ce qu'apporte chaque pièce. Pour chaque question note de tableau, `meta.note_dependency` dit ce que répondrait un lecteur qui manque la note.
2. **Remplacements avant relecture.** J'ai fait remplacer cinq questions :
   - pop-16 et pop-17 : la ligne adulte et la ligne enfant étaient dans la même phrase, donc dans le même chunk ;
   - tab-02 : la note est absente de tous les chunks de l'index, l'item n'était donc pas mesurable ;
   - tab-06 : la note ne changeait pas la réponse ;
   - tab-10 : les en-têtes étaient déjà résolus par le chunking, et l'item n'était pas mappable.
3. **Contrôles programmatiques** : `eval_internal/build_genprobe2_checks.py`, adapté du script d'E1. Il vérifie :
   - les citations verbatim, cellule par cellule et dans la même ligne `<tr>` ;
   - la longueur des citations, de 8 à 40 mots ;
   - que chaque document est une édition en vigueur ;
   - les identifiants, les sous-types et la cohérence des preuves ;
   - qu'une question à deux sources a au moins deux preuves requises : deux RFE pour `two_documents`, une seule pour `two_sections` ;
   - que les deux lignes sont requises dans les questions sans population ;
   - les cibles de composition ;
   - qu'aucune question ne recopie 8 mots d'une citation ni un titre.
   Avec `--mapping`, il calcule la couverture par `harness.passage_match` sur `tas_v6`, sur CPU et sans modèle.
4. **Seconde relecture indépendante.** Trois sous-agents qui n'avaient pas écrit les questions ont relu les sources, une famille chacun, ainsi que les autres RFE en vigueur sur le même point. Ils ont vérifié pour chaque question :
   - la justesse de la référence et qu'elle est la seule lecture possible ;
   - la nécessité de chaque pièce (famille 1) ;
   - que la note n'est pas répétée dans le corps du texte (famille 3) ;
   - la bonne ligne de population (famille 2).
   Ils ont corrigé en place, puis relancé les contrôles. Les détails sont dans `eval_internal/work/genprobe2/second_pass_*.json`.

## Résultats des contrôles (version scellée)

- `build_genprobe2_checks.py --mapping` : **0 erreur, 0 avertissement**. Les 114 citations sont verbatim dans le Markdown source, ainsi que les lignes de contre-partie.
- **Couverture du mapping** : 113 citations sur 114 et 142 fragments de preuve sur 143 sont reconnus par au moins un chunk. La suffisance est atteignable dans l'index pour **60 questions sur 60**.
- **Seule citation non reconnue** : gp2-tab-07, la ligne `TURP ‖ 6–70% ‖ 5–10% ‖ 0–4% ‖ [46, 47]` du tableau EAU de l'argumentaire ECBU 2026. Ses cellules sont purement numériques, et `passage_match` ne compte que les n-grammes qui contiennent un mot de contenu. Le fragment d'en-tête de la même preuve est reconnu, donc la question reste créditable.
- **Format** : `load_suite("genprobe2", "dev")` charge les 60 questions, et `available_suites()` n'inclut plus `genprobe2`.
- **Tests** : `pytest` donne 204 réussis et 1 ignoré. Le test anti-fuite lit `eval_internal/datasets/*.jsonl` et couvre donc `genprobe2`.

## Corrections de la seconde relecture (29 questions)

**Deux sources (14 questions corrigées).**
- **two-10** : la nécessité était fausse. La fiche de synthèse du traumatisme abdominal 2019 donnait déjà la cible de pression artérielle. La seconde pièce porte maintenant sur le fibrinogène (choc hémorragique 2014), absent du texte de 2019.
- **two-07** : le scénario contredisait l'argumentaire de résection hépatique, qui limite la péridurale. La question porte désormais sur une rachianesthésie en injection unique sous HBPM préventive.
- **two-11** : avec un DFG de 40, la seconde pièce était inutile. Le DFG passe à 25, ce qui donne J-5.
- **two-03** : la RFE intubation en réanimation 2016 donne > 0,9 mg/kg de rocuronium. Cette dose est maintenant acceptée et un ensemble alternatif est ajouté.
- **two-08** : la cible postopératoire était ambiguë (mise à jour 2009). La question est réduite à la cible peropératoire.
- **two-09** : la situation « molécule inconnue » est reformulée selon R1.1.1.
- **two-12** : la référence est complétée.
- **Ensembles alternatifs ajoutés** : two-01, 02, 04, 15 et 17.
- **Notes ajoutées** : two-14 et two-20.

**Population (5 questions corrigées).** Aucune erreur de dose ni de ligne n'a été trouvée.
- **pop-07** : la référence disait à tort que le schéma enfant « ne s'applique pas » au nouveau-né. Elle est reformulée.
- **pop-17** : le plafond de 10 mg de dexaméthasone est ajouté et la formulation est alignée sur R1.2.1.
- **pop-19** : la contre-partie adulte est précisée (IMC > 28).
- **pop-08 et pop-16** : contraste faible, noté.

**Notes de tableau et contrôles (10 questions corrigées).**
- **tab-10 remplacée de nouveau.** La ligne lidocaïne adrénalinée (500 mg) se heurtait aux 300 mg du texte du même document. Elle est remplacée par l'en-tête de colonne « intervention urgente » pour la metformine, dans les fiches diabète 2025.
- **tab-07** : la question était ambiguë, deux sources de chiffres étant citées. Elle est réécrite.
- **tab-09** : la question est recentrée sur ce que seule la note donne.
- **tab-08** : la portée est aussi dans le titre de section. Ce passage est ajouté comme ensemble alternatif.
- **tab-02 et tab-12** : dépendance surestimée, corrigée dans les métadonnées.
- **tab-06** : signalée faible.
- **ctl-01 et ctl-03** : un ensemble alternatif est ajouté (fiche et rappel dans le texte).
- **ctl-07** : la référence est réduite au passage cité.

**Items faibles.** 10 questions portent `meta.weak`, avec la raison. La propriété visée y est affaiblie, et on peut les exclure en analyse de sensibilité :
- deux sources : two-03, two-11, two-14 ;
- population : pop-08, pop-16, pop-17 ;
- notes de tableau : tab-02, tab-06, tab-08, tab-12.

## Limites

- **Synthétique et non validé.** Questions écrites et relues par la même famille de modèles, d'où un risque d'auto-préférence avec les générateurs Claude. Le CSV `eval_internal/genprobe2_a_valider_medecins.csv` est prêt pour une relecture médicale.
- **Effectifs.** Les familles comptent 20, 20, 12 et 8 questions, et les sous-types 3 à 10. Les intervalles de confiance seront larges : seuls de gros écarts entre configurations seront interprétables. Ventiler par sous-type n'est qu'indicatif.
- **Nécessité des deux pièces.** Elle a été vérifiée par relecture, sans garantie d'exhaustivité. Une fiche, un résumé ou une autre RFE peut réunir les deux informations. Les ensembles alternatifs connus sont déclarés, mais la suffisance reste une borne basse.
- **Population.** Trois contrastes reposent sur deux RFE distinctes d'années différentes (pop-08, 16, 17). Une part de la différence y est chronologique. Plusieurs RFE sont anciennes mais encore « en vigueur » : asthme 2002, état de mal épileptique 2008, sédation 2007. Les références suivent le texte.
- **Notes de tableau.** La dépendance est réelle mais d'intensité variable (voir les items faibles). tab-08 recoupe la famille population (nouveau-né).
- **Langue.** Deux preuves sont en anglais dans la source : two-09 (texte GIHP sur les tests viscoélastiques) et tab-07 (tableau EAU).
- **Antibioprophylaxie.** Elle fournit 7 questions, toutes sur l'édition 2026 V3.1 (`data/corpus_updates/`). Le jury connaît bien cette RFE, et le système y a été mis au point sur d'autres questions : ces items risquent d'être plus faciles que les autres.
- **Index.** La couverture du mapping est calculée sur `tas_v6`. Un autre index peut couper autrement : relancer `--mapping` avec l'index évalué avant de lire la suffisance.

## Fichiers

- `eval_internal/datasets/genprobe2.jsonl` et `eval_internal/splits/genprobe2/dev.jsonl`, identiques.
- `eval_internal/splits/genprobe2/SEALED.md` (hash).
- `eval_internal/genprobe2_a_valider_medecins.csv`.
- `eval_internal/build_genprobe2_checks.py`.
- `eval_internal/work/genprobe2/` (local, ignoré par `.gitignore`) :
  - consigne des auteurs ;
  - catalogue des documents en vigueur ;
  - brouillons par famille, après relecture ;
  - corrections de la seconde relecture ;
  - `checks_report.json`.
- `src/rag_sfar/evaluation/datasets.py` : `"genprobe2"` ajouté à `HELD_OUT_SUITES`. C'est la seule modification de `src/`.
