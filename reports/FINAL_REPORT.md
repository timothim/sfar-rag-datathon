# RAG-SFAR — Rapport final (2026-11-27)

> Rédigé à partir de `JOURNAL.md`, `eval/FINAL_EVAL_PROTOCOL.md`, `reports/eval/judge_v4/blind_final/summary.md`, `reports/eval/judge_v4/blind_v31grid2/combined_validated_grid.md` et des rapports d'agents (`reports/agents/*.md`, `reports/MCP_DEPLOIEMENT.md`, `reports/DEMO.md`). Aucun chiffre n'a été recalculé pour ce document.

## 0. À lire d'abord

- **Ce que mesurent nos chiffres principaux.** Avec un générateur de substitution (Claude Sonnet) recevant exactement les prompts de notre configuration, sur les 69 questions de test du benchmark des experts, les réponses jugées conformes à la référence par un juge LLM (Claude Haiku, grille v4, non validée médicalement) sont :
  - **53,6 % [41–66] (37/69)** sous les grilles du brouillon du benchmark (résultat pré-enregistré) ;
  - **62,3 % [50–74] (43/69)** sous les grilles validées par un médecin et publiées par les experts après notre exécution (analyse secondaire post hoc : mêmes réponses, même système).
- **Le modèle qui serait déployé (un modèle ouvert d'environ 30 milliards de paramètres) n'a jamais été mesuré.** Le juge n'a pas été validé par un médecin.
- **Le dev était optimiste.** Le retrieval atteint 95,7 % de suffisance des preuves sur le dev et 82,8 % sur le test ; les réponses correctes passent de 73,6 % à 53,6 % (grilles du brouillon) ou de 77,8 % à 62,3 % (grilles validées). Les correctifs du retrieval avaient été conçus en lisant les échecs du dev et n'ont pas transféré au test.
- **Erreurs graves sur le test** : 4 sur 69 sous les grilles du brouillon, 2 sur 69 (2,9 % [0–10]) sous les grilles validées, toutes du même type : une conduite unique imposée alors que la population ou la situation n'était pas précisée. Aucune mauvaise molécule, mauvaise dose, conduite opposée ou édition périmée n'a été relevée (0 sur 69, borne haute de l'intervalle exact 5,2 %).
- **Avec les formulations des cliniciens** (variante en langage courant publiée par les experts), la suffisance du retrieval gelé est de 81,2 % sur le dev comme sur le test. Les options lexicales (n-grammes, lexique) n'y montrent pas de gain démontré ; la normalisation de la question par le modèle y gagne 6,2 points côté dev (voir la décision ci-dessous et la section 5.5).
- **Décision** : la configuration évaluée et gelée est la solution. Les options explorées le 27/11 existent comme interrupteurs, désactivés par défaut ; aucune n'a montré d'effet sur la sonde tenue à l'écart. Une seule montre un effet sur des formulations réelles de cliniciens : la normalisation de la question par le modèle, en mode ajout (+6,2 points de suffisance [+2,1 ; +11,5] côté dev de la variante en langage courant, aucune question perdue ; +1,6 [0 ; +4,7] côté test, post hoc ; section 5.5). Elle est l'option recommandée à activer en premier, après vérification de sa fidélité avec le modèle réellement servi.
- **Rien n'est validé cliniquement.** Les questions du benchmark ont été validées par des médecins ; nos jeux internes sont synthétiques ; aucun médecin n'a relu nos réponses (section 12).

## 1. Ce que fait le système, et ce qu'il n'est pas

### 1.1 Ce qu'il fait

RAG signifie « génération augmentée par recherche » : le système cherche d'abord dans le corpus des recommandations SFAR les passages utiles à la question, puis les donne à un modèle de langue (LLM) avec la consigne de répondre uniquement à partir de ces passages et de les citer.

| Étape | Ce qui est fait | Où |
|---|---|---|
| Corpus | 265 documents SFAR convertis en Markdown (sorties OCR Chandra), dont la RFE antibioprophylaxie V3.1 (juillet 2026) intégrée comme surcouche et corrigée d'après le PDF officiel | `data/corpus_updates/` |
| Découpage (« chunking ») | Le texte est coupé en 36 872 morceaux (« chunks ») ; chaque ligne de tableau devient une fiche qui garde les en-têtes de son tableau ; bibliographies exclues ; 3 errata officiels appliqués de façon visible | index `index/tas_v6` |
| Éditions | Chaque document porte un statut (en vigueur / remplacé) ; les éditions remplacées sont filtrées par défaut | graphe de supersession |
| Recherche | Deux recherches en parallèle : lexicale (BM25, par mots) et sémantique (« dense » : vecteurs `multilingual-e5-small`), fusionnées par rang (RRF), puis reclassées par un modèle qui lit la question et le passage ensemble (« reranker » cross-encoder mmarco) | configuration `C9` |
| Construction du contexte | 16 meilleurs résultats ; autour des 8 premiers, le chunk voisin de chaque côté et le tableau parent (« fenêtres de contexte ») ; notes de bas de tableau appelées par la ligne retrouvée ; doublons retirés ; au plus 40 chunks / 30 000 caractères, présentés avec un en-tête (titre, année, version, statut d'édition, section, population, force de la recommandation) | configuration figée `C10_context_notes`, préréglage `wide` |
| Réponse | Prompt `clinical_concise` : réponse en 1 à 3 phrases citées [Sx], ligne « Source », phrase d'abstention fixe si les extraits ne traitent pas la question ; les QCM sont routés vers un prompt QCM dédié | `generation/profile.py::PRODUCTION` |
| Contrôle | Contrôle déterministe des doses, molécules et citations contre les extraits : avertissement seulement | `answer_check="flag"` |
| Signal de couverture | Meilleur score du reranker exposé à l'interface ; ne filtre rien (« calibré en échantillon, indicatif ») | `retriever.last_coverage` |

Le même profil `PRODUCTION` est servi par l'API, la page de démonstration, les deux serveurs MCP (MCP : protocole qui permet à un assistant IA d'appeler nos outils de recherche) et l'outil de rejeu utilisé pour l'évaluation ; un test vérifie que le prompt de l'API et celui du rejeu sont identiques à l'octet.

### 1.2 Ce qu'il n'est pas

- **Pas un dispositif médical** et pas un outil validé cliniquement.
- **Pas mesuré avec le modèle de déploiement.** Le générateur visé (modèle ouvert ~30B ; un Qwen 27B est servi sur LibreDataHub) n'a pas pu tourner sur la machine de développement (16 Go de RAM). Les chiffres de génération viennent d'un substitut (Claude Sonnet) et, pour le « petit modèle », de Qwen3.5-9B en 4 bits.
- **Pas un benchmark.** Les jeux de questions que nous avons créés (`eval_internal/`) sont des outils internes, synthétiques, non validés médicalement (principe 4 bis). Le benchmark de référence est celui des experts (`benchmark-enrichi`).
- **Pas couvert hors de son corpus** : la recherche renvoie toujours des passages, même hors sujet ; l'abstention repose sur le générateur.
- **Pas un service public** : ni authentification, ni quotas, droits sur les textes non réglés (section 11).

## 2. Ce qui a été mesuré : jeux, auteurs, protocole

### 2.1 Jeux d'évaluation

| Jeu | Questions | Qui les a écrites | Validées par des médecins ? | Rôle |
|---|---:|---|---|---|
| `abpe171` (benchmark des experts, antibioprophylaxie V3.1, brouillon du 26/11 08:36, commit `eabcefc`) | 171 : 102 dev / 69 test (scellé) | experts du projet `benchmark-enrichi` | **oui** (questions) ; grilles de correction en brouillon | résultat principal pré-enregistré |
| `abpv171` (même benchmark, version validée `sfar-abp-v31.1-valide`) | mêmes 171 questions, même découpage | experts | **oui** : 37 grilles révisées par un médecin | analyse secondaire post hoc |
| `abpvern` (variante en langage courant des experts ; `sfar-abp-v31.2-200` en contient 29 approuvées) | 171, dont 88 énoncés réécrits (57 dev / 31 test) | experts | variante publiée par les experts ; 29 reformulations approuvées | robustesse aux formulations réelles (post hoc) |
| `abp171` (benchmark historique) | mêmes 171 questions, références de l'édition précédente | benchmark existant | oui (édition antérieure) | dev seulement ; test non exécuté |
| `multirfe_synth` | 151 : 94 dev / 57 test ; 22 RFE uniquement en test | générées par un LLM (Claude Opus), vérifiées par d'autres sous-agents Claude | **non** | généralisation sur des RFE jamais vues |
| `genprobe` | 48 questions, 47 RFE hors antibioprophylaxie, conçues difficiles | générées par un LLM | **non** | sonde tenue à l'écart, exécutée une fois |
| `genprobe2` | 60 questions, 49 RFE | générées par un LLM (Claude Opus), scellées | **non** | sonde tenue à l'écart pour les explorations du 27/11, exécutée une fois |
| `x2_dev` | 16 questions à deux sources | écrites par un sous-agent pour le développement | **non** | outil de développement, pas une preuve |
| Jeux perturbés (robustesse) | copies déformées automatiquement des questions dev | générées par script (graine fixe) | sans objet | fautes, accents, sigles |

Coffre-fort : les fichiers de test sont scellés par empreinte SHA-256 dans `eval/LOCKBOX.md` ; un test pytest vérifie les empreintes. Limite déclarée : les 171 questions du benchmark avaient déjà été vues par les équipes précédentes et par un autre agent (Gemini Neon) qui a réglé le pipeline dessus ; le test n'est tenu à l'écart que de nos propres réglages. Les fichiers du benchmark des experts ne sont pas publiés dans ce dépôt (droits de redistribution non confirmés).

### 2.2 Protocole de l'évaluation finale

Le protocole a été écrit et commité avant l'exécution (`eval/FINAL_EVAL_PROTOCOL.md`, commit `9cb0c24`) : configuration figée, jeux exécutés une seule fois, métriques principales, sous-groupes, règles d'échec et formulation des résultats.

- **Générateur (substitut)** : Claude Sonnet, sous-agents Claude Code, lots de 8 cas au plus, identifiants opaques, cas mélangés.
- **Juge** : Claude Haiku, grille v4, à l'aveugle (dev et test mélangés, identifiants opaques), deux passes indépendantes par réponse. Combinaison stricte déclarée d'avance : une réponse est « correcte » si les deux juges le disent ; une erreur est « grave » si l'un des deux la signale.
- **Intervalles** : intervalles de confiance (IC) à 95 % ; exacts (Clopper-Pearson) pour les taux, bootstrap pour les écarts.
- **Accord entre les deux juges** (370 réponses) : correct / partiel / incorrect 94,3 % (κ = 0,83) ; erreur grave 98,9 % (κ = 0,74). Le kappa (κ) mesure l'accord au-delà du hasard (1 = parfait).
- **Calibration du juge sous la grille v4** : contre des clés déterministes sur 141 réponses courtes de l'antibioprophylaxie, accord 92,9 %, κ = 0,85 ; 0 verdict modifié sur 14 réponses rallongées (biais de longueur). Ce n'est pas une validation par un médecin.

**Grilles du benchmark.** Notre évaluation a été notée contre le brouillon du benchmark (26/11 08:36). La version validée `sfar-abp-v31.1-valide` (datée du 26/11 22:16, donc antérieure à notre exécution, mais signalée le 27/11 au matin) garde les mêmes 171 questions et les mêmes preuves, et révise 37 grilles de correction (20 dev, 17 test) : faits obligatoires, affirmations interdites, réponses de référence, et politique des questions à clarification (les 10 anciennes questions « à clarification » attendent désormais une réponse ; 6 acceptent aussi une réponse conditionnelle ou une clarification ciblée). Les 37 réponses concernées ont été rejugées à l'aveugle, même juge, même grille v4, deux passes, 0 verdict manquant (run `blind_v31grid2`) ; les 134 autres gardent leurs verdicts. Cette analyse est secondaire et post hoc.

### 2.3 Métriques de retrieval

- **Suffisance des preuves** (`sufficiency`, benchmark des experts et `genprobe*`) : toutes les preuves exigées sont dans le contexte montré au générateur.
- **Rappel des preuves** : part des preuves présentes.
- **Passage dans le contexte** (`passage_hit`, jeux synthétiques) : le passage de référence est dans le contexte.

Le retrieval n'est pas concerné par le changement de grilles : énoncés, fragments et ensembles de preuves sont identiques dans les deux versions (171/171), et la suffisance mesurée sur la version validée est identique (dev 95,8, test 82,8).

## 3. Résultats de l'évaluation finale

Formulation (protocole, section 7) : avec un générateur de substitution (Claude Sonnet) recevant exactement les prompts de notre configuration, X % [IC] des réponses sont jugées conformes à la référence par un juge LLM (Claude Haiku, grille v4, non validée médicalement).

### 3.1 Benchmark des experts : deux grilles côte à côte

| abpe171, réponses Sonnet | Grilles du brouillon (pré-enregistré) | Grilles validées (post hoc) |
|---|---|---|
| **Test (69) : correct (2 juges)** | **53,6 % [41–66] (37)** | **62,3 % [50–74] (43)** |
| Test : correct ou partiel | 97,1 % [90–100] (67) | 98,6 % [92–100] (68) |
| **Test : erreur grave (≥ 1 juge)** | **5,8 % [2–14] (4)** | **2,9 % [0–10] (2)** |
| Test : comportement accepté | 92,8 % [84–98] (64) | 97,1 % [90–100] (67) |
| Test : abstention à tort | 1,4 % [0–8] (1) | 1,4 % [0–8] (1) |
| Dev confirmation (72) : correct | 73,6 % [62–83] (53) | 77,8 % [66–87] (56) |
| Dev confirmation : erreur grave | 2,8 % [0–10] (2) | 0 % [0–5] (0) |
| Dev itération (30) : correct | 73,3 % [54–88] (22) | 86,7 % [69–96] (26) |
| Dev itération : erreur grave | 3,3 % [0–17] (1) | 0 % [0–12] (0) |
| Retrieval, test : suffisance | 82,8 % (53/64) ; rappel 92,7 % | identique |
| Retrieval, dev confirmation : suffisance | 95,7 % | identique |

Sur les 17 questions de test rejugées : correct 8 → 14 ; erreurs graves 2 → 0. Répartition du test sous grilles validées : 43 correctes, 23 partielles, 1 incorrecte, 2 erreurs graves. Faits obligatoires énoncés (grilles du brouillon) : 70,3 % au test, 85,0 % au dev.

### 3.2 Jeux internes (synthétiques)

| Jeu | Nature | n | Correct (2 juges) | Correct ou partiel | Erreur grave (≥ 1 juge) | Retrieval |
|---|---|---:|---|---|---|---|
| **multirfe_synth test** (22 RFE jamais vues) | synthétique (LLM) | 57 | **91,2 % [80,7–97,1]** (52) | 98,2 % (56) | **0 % [0–6,3]** | passage 97,9 % |
| multirfe_synth dev (confirmation) | synthétique (LLM) | 64 | 98,4 % [91,6–100] (63) | 100 % | 0 % [0–5,6] | passage 98,1 % |
| multirfe_synth dev (itération) | synthétique (LLM) | 30 | 86,7 % [69,3–96,2] (26) | 96,7 % | 0 % [0–11,6] | passage 91,7 % |
| **genprobe** (47 RFE hors antibioprophylaxie) | synthétique (LLM), difficile | 48 | **75,0 % [60,4–86,4]** (36) | 93,8 % [82,8–98,7] (45) | 6,2 % [1,3–17,2] (3) | suffisance 77,1 % ; passage 91,7 % |

Le jeu `multirfe_synth` a été écrit et vérifié par Claude, répondu par Claude et jugé par Claude. Sur les questions humaines, le gain de Sonnet sur le petit modèle était environ deux fois plus faible que sur ce jeu (section 6.3) : ses scores surestiment probablement Claude d'une dizaine de points.

Le contrôle déterministe a signalé 0 réponse sur 69 (abpe171 test), 3,5 % (multirfe test), 0 sur 48 (genprobe). Fidélité aux extraits cités (juge) : 95,6 % / 100 % / 97,7 %.

### 3.3 Écart dev → test sur le benchmark des experts

| Mesure | Dev (confirmation, 72) | Test (69) | Écart |
|---|---|---|---|
| Correct, grilles du brouillon | 73,6 % | 53,6 % | **−20,0 pts [−35,5 ; −4,4]** (bootstrap non apparié) |
| Correct, grilles validées (post hoc) | 77,8 % | 62,3 % | environ −15 pts |
| Correctes ou partielles (brouillon) | 97,2 % | 97,1 % | −0,1 [−5,8 ; +5,5] |
| Erreurs graves (brouillon) | 2,8 % | 5,8 % | +3,0 [−3,9 ; +10,2] |
| Suffisance des preuves | 95,7 % | 82,8 % | **−12,9 [−23,7 ; −3,4]** |
| Faits obligatoires (brouillon) | 85,0 % | 70,3 % | −14,7 [−28,5 ; −0,6] |

Sur `multirfe_synth` : correct −7,2 [−15,8 ; −0,2] ; passage −0,2 (non significatif).

**Ce que cela veut dire.** Le retrieval a été mis au point en lisant les échecs du dev ; il y atteint 96 % de suffisance et 83 % sur le test. La composition des jeux n'explique pas l'écart : les questions pédiatriques sont 34/102 en dev et 26/69 en test, mais leur suffisance passe de 94,1 % à **69,2 % (18/26)**, contre 96,8 % → 92,1 % pour les autres. Les formulations des cliniciens confirment la même optimisation du dev vue d'un autre angle : avec elles, dev et test se rejoignent à 81,2 % de suffisance (section 5.5).

**Gains de retrieval qui n'ont pas transféré** (analyse post hoc, retrieval seul, après lecture des résultats ; déclarée exploratoire) :

| Configuration | abpe171 dev, suffisance | abpe171 test, suffisance | multirfe test, passage |
|---|---|---|---|
| BM25 seul | 88,5 | 78,1 | 70,8 |
| C9 (hybride simple) | 88,5 | 82,8 | 85,4 |
| C9 + fenêtres | 92,7 | 82,8 | 97,9 |
| C10_context_notes (figée) | 95,8 [92–99] | 82,8 | 97,9 |

Les gains de C10 et des fenêtres mesurés sur le dev du benchmark (+3 à +10 points selon l'index) valent **0** sur son test. En revanche, les fenêtres de contexte généralisent hors antibioprophylaxie : +12,5 points [+4,2 ; +20,8] sur `multirfe_synth` test et +14,6 [+6,2 ; +25,0] de suffisance sur `genprobe`. C10 ne coûte rien de mesurable mais n'apporte rien de démontré par rapport à C9 + fenêtres.

### 3.4 Sous-groupes déclarés (abpe171 test, grilles du brouillon)

| Sous-groupe | Correct | Correct ou partiel |
|---|---|---|
| QCM (14) | 7 | 13 |
| Questions ouvertes (55) | 30 | 54 |
| Pédiatriques (26) | 12 | — |
| À clarification (5, définition du brouillon) | 1 | 4 (et 3 erreurs graves) |
| Suffisance = 1 (53) | 31 | 53 (1 grave) |
| Suffisance = 0 (11) | 5 | 10 |

Ces sous-groupes n'ont pas été recalculés sous les grilles validées. Sous ces grilles, les anciennes questions « à clarification » attendent une réponse, et 2 des 3 erreurs graves de ce sous-groupe disparaissent (Q17, Q167).

Sensibilité à l'exposition antérieure : sans Q58 et Q152, correct 52,2 % (35/67), graves 6,0 % (brouillon). L'analyse « sans aucune question exposée » est vide : les rapports non versionnés de l'autre agent mentionnent les 69 questions du test.

`multirfe_synth` test par type : ouvertes 21/22, cas cliniques 13/16, tableaux 9/9, hors corpus 9/9 abstentions correctes, comparaison d'éditions 0/1.

`genprobe` par famille (correct ; suffisance ; n = 12 chacune) : QCM 12/12 ; 12/12 — contraste de population 10/12 ; 12/12 — ligne de tableau dépendant d'une note 8/12 ; 6/12 — deux sources 6/12 ; 7/12.

### 3.5 Campagne des experts sur la version d'origine de notre pipeline

Pour mémoire, chiffres rapportés tels quels par les experts (`reports/agents/V1_benchmark_valide.md` §5) : 200 questions de la version v31.2, générateur Qwen3.5-9B, juge = le même Qwen, critère « réussite stricte ». LLM seule 56/200 (28 %) ; LLM + RAG « C8 » (copie de la version d'origine de notre pipeline) 133/200 (66,5 %) ; LLM + passages annotés « oracle » 153/200 (76,5 %). **Grille, juge et générateur différents des nôtres : non comparables directement** à nos chiffres.

## 4. Erreurs graves

Définition (grille v4) : mauvaise molécule (`wrong_drug`), mauvaise dose (`wrong_dose`), conduite opposée à la référence (`wrong_conduct`), recommandation périmée présentée comme en vigueur, affirmation non sourcée, abstention manquée hors corpus, autre erreur dangereuse (`other`), et conduite unique imposée alors qu'elle est fausse pour une population ou une situation non précisée (`unjustified_assumption`). Une abstention à tort n'est pas comptée grave ; elle a son propre taux.

### 4.1 Observées

| Jeu | Grilles du brouillon (≥ 1 juge) | Grilles validées (post hoc) | Catégories |
|---|---|---|---|
| abpe171 test (69) | 4 — 5,8 % [2–14] (Q15, Q17, Q126, Q167) | **2 — 2,9 % [0–10] (Q15, Q126)** | toutes `unjustified_assumption` ; Q126 : dose adulte donnée sans la restreindre à l'adulte ; Q17 et Q167 ne sont plus des erreurs sous la nouvelle politique de clarification |
| abpe171 dev confirmation (72) | 2 — 2,8 % (Q85, Q88) | 0 — 0 % [0–5] | `unjustified_assumption` |
| abpe171 dev itération (30) | 1 — 3,3 % (Q163) | 0 — 0 % [0–12] | `unjustified_assumption` |
| multirfe_synth test (57) | 0 — 0 % [0–6,3] | sans objet | — |
| genprobe (48) | 3 — 6,2 % [1,3–17,2] | sans objet | 2 `unjustified_assumption` (signalées par les deux juges) ; 1 `wrong_conduct` (un seul juge) ; 2 des 3 dans la famille « contraste de population » |

Toutes les erreurs graves relevées sur le benchmark des experts sont du même type : le système répond pour une population (le plus souvent l'adulte) quand la question ne la précise pas et que la conduite diffère selon la population.

### 4.2 Non observées

| Catégorie | abpe171 test | multirfe_synth test |
|---|---|---|
| Mauvaise molécule, mauvaise dose, conduite opposée, édition périmée | 0/69 (IC exact 0–5,2 %) | 0/57 (0–6,3 %) |
| Abstention manquée sur une question hors corpus | sans objet | 0/9 (0–33,6 %) |

« Non observé » n'est pas « absent » : avec 69 questions, un taux réel allant jusqu'à 5,2 % reste compatible avec zéro observation.

### 4.3 Ce que le contrôle déterministe ne voit pas

Sur 180 réponses du petit modèle jugées en développement, le contrôle déterministe (doses, molécules, citations présentes dans les extraits) a détecté 0 des 9 erreurs graves et signalé à tort 3 des 133 réponses correctes. Ces erreurs étaient des erreurs de raisonnement (mauvaise ligne du tableau, sens d'un changement inversé, tranche de score mal lue, abstention manquée) dont toutes les doses et molécules figuraient bien dans le contexte. Aucune dose ni molécule inventée n'a été trouvée sur ces 180 réponses. Le contrôle reste un avertissement à coût quasi nul ; il ne remplace pas une relecture.

## 5. Faiblesses connues

### 5.1 Lignes pédiatriques et contreparties de population

- Suffisance pédiatrique : 94,1 % en dev, **69,2 % (18/26) en test** ; 12/26 réponses pédiatriques correctes en test (grilles du brouillon).
- Échec dominant en dev (8 réponses partielles) : la réponse donne la conduite adulte seule alors que la référence attend aussi le volet pédiatrique, et la preuve pédiatrique était dans le contexte. C'est une faute de génération, pas de recherche.
- Sur `genprobe2`, famille « contrepartie de population » : suffisance 80,0 % (20 questions).
- Deux mécanismes ont été essayés et rejetés (section 7) : la règle de population du retrieval (ajoutait surtout des lignes d'un autre acte avec leurs doses) et les liens structurels adulte ↔ enfant (sûrs, mais sans effet). Les tableaux pédiatriques regroupent et nomment les actes autrement que les tableaux adultes ; il faudrait une table de correspondance des actes (codes CCAM ou annotation d'experts).

### 5.2 Questions à deux sources

C'est la faiblesse principale du retrieval gelé. Sur `genprobe2`, famille « deux sources » : **suffisance 40,0 % (8/20)**, rappel des preuves 63,3 %, alors que le passage de référence principal est dans le contexte pour 90 %. Sur `genprobe`, 7/12 en suffisance et 6/12 réponses correctes. La décomposition de la question par un LLM n'y a rien changé sur la sonde tenue à l'écart (section 8.2).

### 5.3 Lignes de tableau dépendant d'une note ou d'un en-tête

Sur `genprobe`, 6/12 en suffisance et 8/12 réponses correctes ; sur `genprobe2`, 75,0 % de suffisance (12 questions). Les notes appelées par la ligne sont lues (`called_scope`) ; les conditions portées ailleurs (en-tête éloigné, renvoi implicite) restent manquées.

### 5.4 Clarification

Sous les grilles du brouillon, le benchmark attendait pour 10 à 11 questions une demande de précision ou une réponse conditionnelle ; sur le test, 1 des 5 était correcte et 3 produisaient une erreur grave. Les experts ont changé cette politique dans la version validée : ces questions attendent désormais une réponse, l'information manquante servant à individualiser. Sous les grilles validées, 2 erreurs graves de ce type restent sur le test (Q15, Q126, dont les grilles n'ont pas été révisées). Le problème de fond demeure : la frontière « préciser / répondre » ne se lit pas dans le contexte (sur les 81 questions « réponse » du dev sans âge ni population, 38 ont aussi des tableaux adulte et pédiatrique dans le contexte), et aucune solution générique n'a été démontrée.

### 5.5 Robustesse aux fautes de frappe, aux sigles et aux formulations des cliniciens

**Perturbations synthétiques** (agent Q1, retrieval seul, dev, graine fixe) :

| Perturbation (configuration figée) | abpe171 dev, suffisance | Écart apparié vs propre | multirfe dev, passage |
|---|---|---|---|
| Propre | 95,8 [91,7–99,0] | — | 96,1 |
| 1 faute par question | 89,6 [83,3–95,8] | **−6,2 [−11,5 ; −2,1]** | 94,7 (−1,3) |
| 2 à 3 fautes | 84,4 [77,1–90,6] | **−11,5 [−18,8 ; −6,2]** | 93,4 (−2,6) |
| Accents retirés | 94,8 | −1,0 [−3,1 ; 0] | 98,7 |
| Style télégraphique | 95,8 | 0,0 | 96,1 |
| « antibioprophylaxie » → « ABP » et 6 autres sigles d'utilisateur (diagnostic) | 87,5 [80,2–93,8] | **−8,3 [−14,6 ; −3,1]** | 96,1 (2 questions modifiées) |

**Formulations réelles des cliniciens** (variante en langage courant publiée par les experts ; agent V1, retrieval seul ; côté test, une passe post hoc unique sur configurations fixes, rien de réglé) :

| Configuration | Standard, dev | Langage courant, dev | Standard, test | Langage courant, test |
|---|---|---|---|---|
| Figée | 95,8 [91,7–99,0] | **81,2 [72,9–88,5]** | 82,8 [73,4–92,2] | **81,2 [71,9–90,6]** |
| + n-grammes de caractères | 96,9 | 83,3 | 87,5 | 81,2 |
| + lexique médical | 95,8 | 82,3 | 82,8 | 81,2 |
| + les deux | 95,8 | 84,4 | 87,5 | 82,8 |

- Effet de formulation, langage courant − standard, configuration figée : sur les 88 énoncés réécrits, **−25,5 [−38,2 ; −12,7]** au dev (n = 55) et −3,6 [−17,9 ; +14,3] au test (n = 28) ; sur les 29 reformulations approuvées, −18,8 [−43,8 ; 0] (dev, n = 16) et −20,0 [−50,0 ; 0] (test, n = 10).
- Options contre figée, sur le langage courant (171 questions) : n-grammes +2,1 [−3,1 ; +8,3] dev, 0,0 test ; lexique +1,0 dev, 0,0 test ; les deux +3,1 [−3,1 ; +9,4] dev, +1,6 [−3,1 ; +6,2] test. **Aucun gain démontré** : tous les intervalles contiennent 0.
- Lecture : les gains vus sous fautes synthétiques (n-grammes) et sur un sigle synthétique (lexique, « ABP ») ne se retrouvent pas sur les formulations des experts, qui portent surtout sur des raccourcis opératoires et des synonymes. Le chiffre réaliste de suffisance avec des formulations de cliniciens est autour de 81–83 %.

**Normalisation de la question par le modèle, en mode ajout (NORM), sur les formulations de cliniciens** (`reports/agents/V1_benchmark_valide.md`, section 6 ; substitut Claude Haiku à la place du modèle servi ; retrieval seul ; prompt de normalisation inchangé, écrit avant que ce jeu existe chez nous ; côté test : une passe post hoc sur configuration fixe, ce test a déjà servi).

| Configuration − configuration figée, suffisance des preuves, variante en langage courant | dev | test (post hoc) |
|---|---|---|
| NORM, 171 questions | **+6,2 [+2,1 ; +11,5]** (6 gagnées, 0 perdue ; n = 96) | +1,6 [0 ; +4,7] (1 gagnée, 0 perdue ; n = 64) |
| NORM, 88 énoncés reformulés par les experts | **+9,1 [+1,8 ; +18,2]** (5 / 0 ; n = 55) | +3,6 [0 ; +10,7] (1 / 0 ; n = 28) |
| NORM, 29 reformulations publiées | +12,5 [0 ; +31,2] (n = 16) | +10,0 [0 ; +30,0] (n = 10) |
| Options lexicales + NORM, 171 questions | +8,3 [+2,1 ; +15,6] (10 / 2) | +6,2 [+1,6 ; +12,5] (4 / 0) |

Niveau de la configuration figée sur ce jeu : 81,2 % en dev et en test. Sur le dev, NORM récupère environ un tiers de la perte due à la formulation (−25,5 points sur les 88 énoncés reformulés) ; sur le test, le gain de NORM seule tient à une question et son intervalle touche 0. Une partie du gain « options lexicales + NORM » sur le test vient des n-grammes seuls, sur un test déjà utilisé : il indique une direction, il ne permet pas de choisir une configuration.

Fidélité : le modèle a modifié 59 des 171 questions (dont 55 des 88 reformulées par les experts). Sur 30 réécritures tirées au hasard et relues à la main, plus les cas signalés par les agents, **aucun contenu clinique perdu, ajouté ou altéré** ; chaque réécriture garde la forme d'origine et ajoute le développement entre parenthèses. Les sigles ambigus sont laissés tels quels (aucun apport sur ceux-là). Relecture faite par un agent, pas par un médecin.

Lecture : c'est la seule option de robustesse qui montre un effet sur des formulations réelles de cliniciens. Elle reste éteinte par défaut : l'effet est établi côté dev seulement, avec Haiku et non avec le modèle servi, et la fidélité doit être remesurée avec ce modèle avant activation.

### 5.6 Autres limites

- **Grilles du benchmark** : le résultat pré-enregistré porte sur les grilles du brouillon ; le résultat sur les grilles validées est post hoc (section 2.2).
- **Juge** : grille v4 non validée par un médecin ; les extraits cités sont transmis, pas le contexte entier ; le bruit de jugement (1 à 2 cas sur 30 entre deux jugements des mêmes réponses en développement) est de la taille de plusieurs écarts mesurés.
- **Générateur de substitution** : pas de contrôle de la température ni du plafond de tokens côté sous-agents ; leur isolation repose sur une consigne.
- **Routage QCM** : calé sur le format `A. …` ; une question ordinaire qui énumère des éléments lettrés serait traitée comme un QCM, et le mode QCM impose une lettre unique.
- **Liste de molécules du contrôle** : surtout antibiotiques et anticoagulants.
- **Corpus** : textes anciens toujours « en vigueur » contredits par des textes plus récents (section 12).
- **Latences** : celles mesurées le 27/11 à partir de 10:42 l'ont été avec un verrou GPU à trois places (plusieurs travaux simultanés) ; elles sont indicatives.

## 6. Choix retenus et pourquoi (résumé chronologique)

### 6.1 Nettoyage du système hérité

Le système de départ contenait des règles et des prompts écrits à partir de questions du benchmark (fuites) et un sourcing ajouté par le code. Retirés (« C8 générique »), avec un test anti-fuite automatique dans la suite pytest. Mesure : retrieval inchangé dans le bruit (abp171 doc hit 100 % = ; multirfe doc MRR +0,033 [+0,006 ; +0,071]) ; l'essentiel du sur-ajustement était dans les prompts de génération (ancien C8 avec le 7B : 86–100 % sur les jeux du README, 67,6 % hors prompts calqués, notation déterministe, abp171 dev).

### 6.2 Simplification par ablation (C9)

Ablation composant par composant (un composant retiré à la fois) de C8 générique, retrieval, dev : seuls le canal dense (multirfe passage hit −7,9 points [−14 ; −3] sans lui) et le reranker (passage MRR −0,085 [−0,15 ; −0,02] sans lui) ont un effet mesurable. Les 8 autres composants ont été retirés : C9 = BM25 + dense + RRF + reranker + filtre d'édition + routeur. En génération (7B, juge Haiku grille v1, multirfe dev) : correct −1,1 [−9,6 ; +7,4] (non significatif), **erreurs graves 16,0 % → 5,3 % (−10,6 [−18,1 ; −4,3])**.

### 6.3 Le générateur est le goulot

Mêmes contextes C9, juge Haiku (grille v1, ancien index) :

| Générateur | multirfe dev (94, synthétique) | abp171 dev (102, médecins) |
|---|---|---|
| Qwen2.5-7B, prompt concis | 69,1 % | 81,4 % |
| Sonnet, 6 passages | 90,4 % [84–96] (+21,3 [+12,8 ; +30,9]) | 91,2 % [85–96] (+9,8 [+2,0 ; +17,6]) |
| Sonnet, 12 passages | 96,8 % [93–100] | 95,1 % [90–99] |

Sur les 60 questions d'itération (grille v2), Sonnet − Qwen3.5-9B avec le même prompt : +6,7 points [0 ; +15,0], graves −5,0 [−11,7 ; 0].

### 6.4 Ingestion et index

Index successifs, mesurés sur dev (suffisance abpe171, C9 / C9 + fenêtres) : `tas_v3_errata` 83,3 / 88,5 ; `tas_v4` 90,6 / 93,8 ; `tas_v5` 88,5 / 92,7 ; `tas_v6` = `tas_v5` à ±1 point. `tas_v4` a été abandonné malgré ses scores : la revue indépendante R1 y a trouvé des défauts invisibles pour les métriques de retrieval mais graves pour la citation (1 472 tableaux aplatis sur une ligne, cellules décalées de colonne ; « µg » abîmé dans 45 chunks ; organigrammes perdant des doses ; ~700 chunks adultes étiquetés pédiatriques). `tas_v5`/`tas_v6` corrigent ces défauts (compteurs de fidélité permanents à 0) au prix de petits reculs de retrieval. Leçon : toute transformation de texte doit passer un contrôle de fidélité.

### 6.5 Gel du retrieval

Le 27/11 à 07:47, sur décision de l'utilisateur : `C10_context_notes` sur `index/tas_v6`, tag `retrieval-freeze-20261127`. Une revue indépendante (R2) a confirmé le gel avec cette réserve : le gain de C10 sur C9 + fenêtres n'est montré que sur l'antibioprophylaxie, et son IC touche 0 sur `tas_v6`. L'évaluation finale l'a confirmé (gain nul sur le test).

## 7. Résultats négatifs (essayé, mesuré, rejeté)

| Piste | Mesure | Décision |
|---|---|---|
| Embedder plus gros (Qwen3-Embedding-0.6B au lieu de e5-small) | C9, multirfe dev : doc hit −2,6 [−6,6 ; 0], passage hit +1,3 (n.s.), abp = | rejeté : pas de gain, le reranker corrige déjà le classement dense |
| Reranker plus gros (bge-reranker-v2-m3) | sur C9 : passage hit +3,9 [−1,3 ; +9,2] (n.s.) ; sur C10 : −1,0 [−3,1 ; 0], latence 1,8–3,9 s contre ~0,2 s | rejeté |
| Module correctif d'origine (CRAG : sous-requêtes par facette) | ablation un composant à la fois : effet nul ou non significatif sur les deux jeux dev ; son implémentation était spécifique au benchmark | retiré de C9 |
| Variantes de fusion des scores (DBSF en plus de RRF) | même ablation : sans effet mesurable | retiré ; poids et k de la RRF non balayés |
| Boosts (boost de métadonnées, encadrés allergie, expansion des voisins dans l'ancien pipeline) | même ablation : sans effet mesurable | retirés ; les voisins sont revenus sous forme de fenêtres de contexte, mesurées à part |
| Lexique médical, n-grammes de caractères, routeur | même ablation : sans effet sur questions propres ; lexique d'acronymes −1 question sur abp171 (C10) | retirés de C9 (le routeur reste pour les comparaisons d'éditions) ; robustesse remesurée le 27/11 (section 8.1) |
| Quota QCM (2 passages par option) | gain = 1 question (Q171), 14/19 ajouts hors sujet | retiré |
| Quota de population et recherche « contrepartie » | v3_errata : 7 déclenchements, 0 utile, 5 lignes d'un autre acte ; tas_v6 : 28 déclenchements, 2 utiles, 24 lignes d'un autre acte (avec leurs doses) | retiré (risque clinique) |
| Filtre d'édition désactivé | +3,1 (artefact), éditions remplacées dans le contexte | rejeté (sécurité) |
| Prompt de production v2 (prompt unique riche) | 9B : correct −13,3 pts [−25,0 ; −3,3], graves +6,7 [0 ; +15] ; Sonnet : 0,0 [−5 ; +5] | rejeté ; `clinical_concise` gardé |
| Note de dépendance à la population | ablation pré-enregistrée, abpe171 dev (102) : correct −2,0 [−7,8 ; +3,9], faits obligatoires +3,1 [−1,0 ; +7,3] ; règle de décision (IC excluant 0) non satisfaite | non activée ; prometteuse sur les omissions pédiatriques, non démontrée |
| Note de couverture | Sonnet : 11/11 correctes avec et sans | non activée |
| Contrôle déterministe des réponses en mode régénération | 0/9 erreurs graves détectées, 3/133 fausses alertes | gardé en avertissement seulement |
| Index `tas_v4` | meilleurs scores de retrieval, défauts de fidélité (section 6.4) | rejeté |
| Unités « recommandation » comme chunks ; en-tête sans domaines | neutre | rejetés |
| Liens structurels adulte ↔ enfant (X1) | 42/42 liens corrects à la lecture, mais tous dans l'antibioprophylaxie ; couverture 39/371 lignes ; effet sur dev 0 (1 déclenchement sur 102) | non retenu, code désactivé |
| Seconde passe corrective sans LLM (X2, option 2 : signal du cross-encoder par proposition) | AUC 0,43 sur x2_dev ; gain 0 sur les trois jeux ; abpe171 dev −1,0 [−3,1 ; 0] ; latence médiane 192 → 330–690 ms | écartée |
| Seconde passe corrective avec LLM (X2, option 3) | gain nul partout ; juge « complètes » les questions à deux sources ; ses 13 « incomplet » sur multirfe sont toutes des questions hors corpus ; ~1 900 tokens par question | écartée |
| Reformulation libre par LLM (Q2) | 9 réécritures sur 97 de questions propres altèrent le contenu clinique ; sous fautes, 4 inversions de sens (« sans » → « avec » deux fois, « hors » → « en », « avant » → « après ») et 1 acte remplacé par un autre | **rejetée : change le sens des questions** |
| Passage hypothétique écrit par le LLM (HyDE, Q2) | 190/196 passages inventent un grade ou un niveau de preuve, 47/196 une dose ou une durée ; en remplacement −8,7 [−14,0 ; −4,1] (17 questions perdues, 2 gagnées) | **rejeté** |
| Réécriture en mode remplacement (Q2) | perd des preuves même avec des réécritures fidèles (normalisation −1,2 [−3,5 ; +1,2] sur questions propres) | rejeté ; seul le mode ajout est gardé |
| Glossaire des sigles extrait du corpus (Q1) | ne rattrape pas « ABP » (absent du corpus) ; −1,2 [−2,9 ; 0] sur questions propres | gardé éteint (outil de vérification seulement) |
| Format de contexte historique (ordre en U, sans fusion) | structuré − historique : +3,3 [−6,7 ; +13,3] (n.s.), −18 % de tokens pour le structuré | format structuré gardé |

## 8. Explorations du 27 novembre

Après l'évaluation finale, quatre pistes ont été rouvertes sur deux objections de l'utilisateur : la robustesse aux saisies réelles n'avait jamais été mesurée, et le besoin couvert par l'ancien module correctif (questions à deux sources) n'est pas résolu. Règles : chaque mécanisme est un module séparé autour du retriever gelé, désactivé par défaut, avec un test d'identité ; mise au point sur dev ; les candidats retenus ont été exécutés **une seule fois** sur la sonde scellée `genprobe2`, selon un plan écrit avant l'exécution (`JOURNAL.md`, « Plan de l'exécution unique sur `genprobe2` »).

### 8.1 Robustesse sans LLM (Q1)

Sur dev (tableau de la section 5.5 pour la configuration figée), variantes contre figée, abpe171 dev, suffisance, apparié :

| Variante | 2 à 3 fautes | Sigles d'utilisateur | Propre | Latence médiane |
|---|---|---|---|---|
| n-grammes de caractères (`use_subword`) | +3,1 [−1,0 ; +7,3] | +2,1 [−2,1 ; +6,2] | +1,0 [−2,1 ; +5,2] | 198 ms (figée 190) |
| lexique médical | 0 | +7,3 [+2,1 ; +13,5] | 0 | 189 ms |
| n-grammes + lexique | +4,2 [0 ; +9,4] | +10,4 [+5,2 ; +16,7] | 0 | 197 ms |
| glossaire extrait du corpus | −1,0 [−3,1 ; 0] | −1,0 [−3,1 ; 0] | −1,0 [−3,1 ; 0] | 195 ms |
| BM25 seul | −14,6 [−22,9 ; −7,3] | −1,0 | −1,0 | 2 ms |
| dense seul | −6,2 [−12,5 ; −1,0] | −18,8 [−28,1 ; −10,4] | −19,8 [−28,1 ; −12,5] | 191 ms |

Ce que l'agent conclut :
- Les n-grammes vont dans le bon sens partout (aucune case négative sur 16) mais avec des IC qui touchent presque tous 0 ; protection modeste, pas un gain démontré.
- Le lexique ne fait que ses sigles : tout son gain mesuré vient de « ABP », que le corpus n'écrit jamais. Sur ses 73 sigles et 25 synonymes, **13 entrées ajoutent des termes au-delà de la forme longue, dont 7 des noms de molécules** (C1G → céfazoline, C2G, C3G, et des listes de molécules pour AOD, AVK, AAP, HBPM) ; ce sont précisément les molécules attendues par le benchmark d'antibioprophylaxie, donc une surface de surapprentissage. **18 des 73 sigles ne sont définis nulle part dans le corpus en vigueur.** La version réduite aux 60 sigles « purs » donne exactement le même gain. Recommandation de Q1 : ne pas réactiver le lexique complet tel quel, le remplacer par sa partie « sigles purs », à faire relire et étendre par un clinicien.
- Sur les formulations réelles des cliniciens, ni les n-grammes ni le lexique n'ont d'effet démontré (section 5.5).

### 8.2 Décomposition des questions et seconde passe corrective (X2)

Module `retrieval/multi_query.py`, modes `off` (défaut), `decompose`, `ce_gap`, `llm_correct`. Retrieval seul, dev, Sonnet comme substitut du modèle.

| Option | Déclenchements (dev) | Effet sur dev | Coût | Décision |
|---|---|---|---|---|
| 1. Décomposition par LLM avant la recherche | 0/102 abpe171, 2/94 multirfe, 9/16 x2_dev | abpe171 et multirfe : 0 ; **x2_dev : suffisance 37,5 → 50,0 (+12,5 [0 ; +31,2])**, 2 gagnées, 0 perdue ; rappel 65,6 → 71,9 ; ~35 des 66 passages ajoutés pertinents | un appel LLM par question (~400 tokens) ; latence de recherche médiane 192 → 583 ms quand elle se déclenche | candidate pour `genprobe2` |
| 2. Seconde passe sans LLM | — | gain 0 ; −1,0 sur abpe171 | latence médiane 192 → 330–690 ms | écartée |
| 3. Seconde passe corrective avec LLM | — | gain 0 ; détecte des questions hors corpus, pas des preuves manquantes | ~1 900 tokens par question | écartée |

`x2_dev` est un outil de développement (16 questions écrites par un sous-agent), pas une preuve de généralisation.

### 8.3 Réécriture de la question par un LLM (Q2)

Module `retrieval/query_rewrite.py`, désactivé par défaut. Retrieval seul, dev, Haiku comme substitut du modèle servi (1 804 réécritures importées sans rejet).

| Variante (deux jeux dev réunis, n = 172) | Propre | 1 faute | 3 fautes | Sigles d'utilisateur | Fidélité lue à la main |
|---|---|---|---|---|---|
| **Normalisation prudente, mode ajout** | +0,6 [0 ; +1,7] | +3,5 [+1,2 ; +6,4] | +8,1 [+4,1 ; +12,2] | +2,9 [+0,6 ; +5,8] | 0 altération sur les 23 questions propres modifiées (170/196 laissées inchangées) ; 1 mauvaise correction d'un qualificatif sur 40 questions perturbées lues ; aucune négation inversée, aucun nom de molécule ou d'acte mal corrigé |
| Reformulation libre, mode ajout | +0,6 | +3,5 | +8,1 | +2,9 | **9/97 altérations** sur questions propres ; 4 inversions de sens et 1 acte remplacé sous fautes |
| Passage hypothétique (HyDE), remplacement | −8,7 [−14,0 ; −4,1] | — | −5,2 | — | grade inventé 190/196, dose ou durée inventée 47/196 |

En mode ajout, le contexte gelé est conservé tel quel et la réécriture ne remplit que le budget restant : la suffisance ne peut pas baisser par construction. Coût : prompt ~460 tokens, sortie ~28 ; latence estimée (non mesurée) 0,3 à 2 s sur un modèle ouvert moyen, plus ~200 ms de seconde recherche. Condition posée par Q2 : remesurer la fidélité avec le modèle réellement servi avant toute activation.

### 8.4 Exécution unique sur la sonde tenue à l'écart `genprobe2`

60 questions synthétiques (Claude Opus), 49 RFE en vigueur, non validées médicalement, scellées (`76be3ccd…`), écrites à l'aveugle des méthodes. Exécutée le 27/11 à 10:43, une seule fois, retrieval seul, selon le plan écrit d'avance (agent G1, `reports/agents/G1_genprobe2_run.md`). Conditions : questions propres, et une faute de frappe par question (`typo1`, graine 20261127).

**Configuration gelée, première mesure sur ce jeu :**

| Famille | n | Suffisance (propre) | Rappel des preuves | Passage | Suffisance (1 faute) |
|---|---:|---:|---:|---:|---:|
| Toutes | 60 | 68,3 | 77,8 | 90,0 | 66,7 |
| Deux sources | 20 | **40,0** | 63,3 | 90,0 | 40,0 |
| Contrepartie de population | 20 | 80,0 | 85,0 | 90,0 | 75,0 |
| Note de tableau | 12 | 75,0 | 79,2 | 83,3 | 75,0 |
| Contrôles | 8 | 100,0 | 93,8 | 100,0 | 100,0 |

**Candidats contre configuration gelée, suffisance, en gras la cible déclarée d'avance :**

| Candidat | Condition | Toutes | Deux sources | Gagnées / perdues |
|---|---|---|---|---|
| LEX (n-grammes + lexique) | propre | +3,3 [−3,3 ; +10,0] | +10,0 [0 ; +25,0] | 3 / 1 |
| LEX | 1 faute | **+1,7 [−6,7 ; +8,3]** | +5,0 [−10,0 ; +25,0] | 3 / 2 |
| NORM (normalisation, mode ajout) | propre | 0 | 0 | 0 / 0 |
| NORM | 1 faute | **+1,7 [0 ; +5,0]** | 0 | 1 / 0 |
| DEC (décomposition) | propre | 0 | **0 [0 ; 0]** | 0 / 0 |
| TOUT (LEX + NORM + DEC) | propre | +3,3 [−3,3 ; +10,0] | +10,0 [0 ; +25,0] | 3 / 1 |
| TOUT | 1 faute | +3,3 [−5,0 ; +11,7] | +10,0 [−10,0 ; +30,0] | 4 / 2 |

- DEC ne s'est déclenché que sur 4/60 questions, toutes à deux sources, sans ajouter aucune preuve manquante.
- **Verdict selon les règles déclarées d'avance** : les quatre candidats sont « sélectionnables » (aucune question de contrôle perdue, au plus une perdue au total en condition propre), mais **aucun n'a d'intervalle excluant 0 sur sa cible : « pas d'effet démontré sur le jeu tenu à l'écart »**. Rien n'est activé par défaut ; la configuration gelée reste la référence.
- Limites : retrieval seul (réponses non générées ni jugées) ; 60 questions synthétiques ; à n = 20 par famille, une question vaut 5 points ; substituts Haiku et Sonnet ; latences indicatives (verrou GPU partagé).

### 8.5 Décision

| Option | État | Ce qu'elle a montré | Ce qu'elle n'a pas montré |
|---|---|---|---|
| **Configuration gelée `C10_context_notes`** | **solution retenue, active par défaut** | évaluée selon le protocole pré-enregistré (section 3) | — |
| Option lexicale (n-grammes + lexique) | interrupteur, désactivé par défaut. Les mesures ont été faites avec le lexique complet ; la démo (« lexicale ») sert les n-grammes et le lexique réduit aux 60 sigles de simple développement, sans ajout de molécules, mesuré équivalent sur dev seulement | gains sur dev sous fautes et sigles synthétiques (+4,2 et +10,4 points) | aucun gain démontré sur `genprobe2` ni sur les formulations des cliniciens ; lexique à relire par des médecins (13 entrées enrichies) |
| Normalisation par le modèle, mode ajout | interrupteur, désactivé par défaut (démo : « normalisation ») | +8,1 [+4,1 ; +12,2] sur dev avec 3 fautes ; **sur les formulations de cliniciens : +6,2 [+2,1 ; +11,5] côté dev, 0 question perdue** ; aucune perte possible par construction ; fidèle à la lecture avec Haiku (0 altération sur 30 réécritures relues) | effet sur `genprobe2` non démontré (+1,7 [0 ; +5,0]) ; côté test des formulations de cliniciens, intervalle touchant 0 (+1,6 [0 ; +4,7], post hoc) ; fidélité non mesurée avec le modèle servi ; un appel LLM de plus par question |
| Décomposition par LLM | interrupteur (`RAG_SFAR_MULTI_QUERY=decompose`), désactivé, non branché à l'API ni à la démo | +12,5 [0 ; +31,2] sur 16 questions de développement | aucun effet sur les questions à deux sources de `genprobe2` |
| Reformulation libre, passage hypothétique | rejetés | — | changent le sens des questions (section 8.3) |

## 9. Écarts au protocole

D'après `JOURNAL.md` :

1. Deux lots de `genprobe` ont été lancés quelques secondes après les autres (limite de 20 agents simultanés).
2. Une précision d'outillage (`--run blind_final` pour la commande `show`) a été ajoutée au message de tâche des juges, sans modifier le fichier de consignes figé.
3. L'analyse de sensibilité « sans les questions exposées » est vide de sens : toutes les questions du test sont mentionnées dans les rapports non versionnés de l'autre agent (le protocole, d'après la revue R3, en comptait 16).
4. L'analyse retrieval C9 / C9 + fenêtres / C10 / BM25 sur les splits test est post hoc, faite après lecture des résultats.
5. L'heure « 08:45 » écrite dans le protocole est une estimation ; le commit a été fait vers 08:38 (l'horodatage git fait foi).
6. Analyses ajoutées après coup, toutes déclarées post hoc : rejugement sous les grilles validées (un lot de la passe a rejugé une fois par un nouvel agent après un refus d'outil, conformément à la règle du protocole) ; retrieval sur la version validée et la variante en langage courant côté test.
7. `genprobe2` (plan distinct du protocole final) : TOUT a demandé une seconde série de 25 décompositions Sonnet (questions normalisées), exportée et répondue avant toute exécution.

Les jeux `abpe171` test, `multirfe_synth` test, `genprobe` et `genprobe2` ne sont plus vierges et ne servent plus à aucun réglage.

## 10. Démonstrateur

Page web unique servie par l'API FastAPI (`reports/DEMO.md`), hors ligne, sans ressource externe. Elle passe par le profil `PRODUCTION` : le prompt est celui de l'évaluation (test `test_api_prompt_identical_to_replay_prompt`).

- **Ce qui existe** : mode « Répondre » (réponse en continu, citations [Sx] cliquables qui déplient le passage, source avec titre, année, édition, section, niveau GRADE ; alertes du contrôle automatique) ; mode « Passages seuls » sans modèle de langage, qui est la partie entièrement mesurée ; repli automatique sur les passages si le générateur est injoignable ; générateur réglable (URL compatible OpenAI, modèle, clé gardée en mémoire seulement ; verrou `RAG_SFAR_DEMO_LOCK_SETTINGS=1` obligatoire pour une instance accessible à d'autres) ; sélecteur de robustesse par question (aucune / lexicale / normalisation / les deux), défaut « aucune ».
- **Ce qui a été vérifié** : démarrage local en 10 s ; tests automatiques (`tests/test_demo_chatbot.py` : les réglages du générateur changent le point d'accès et le modèle, pas le prompt) ; chemin de génération testé contre un serveur factice.
- **Ce qui n'a pas été vérifié** : **aucun vrai générateur n'a été testé avec la page** ; le branchement au Qwen 27B de LibreDataHub, l'acceptation de `chat_template_kwargs` par ce serveur et le temps de réponse sont à vérifier sur place ; la mémoire nécessaire (estimée 2 à 4 Go sans générateur) n'a pas été mesurée.

## 11. Serveur MCP

`reports/MCP_DEPLOIEMENT.md` (vérifications) et `reports/MCP_ARCHITECTURE.md` (conception). Le serveur est un moteur de recherche cité en lecture seule : il ne rédige pas de réponse.

- **Vérifié** (machine de développement, 27/11) : le client MCP officiel (SDK Python `mcp` 2.3.0) se connecte en HTTP et en stdio, liste les 5 outils et les appelle (smoke test 12/12 en HTTP, 6/6 en stdio, 13/13 avec 8 appels parallèles) ; profil `PRODUCTION` servi (265 documents, 36 872 passages) ; en-tête `Host` étranger refusé (protection contre le DNS rebinding) ; arguments invalides rejetés proprement ; le texte des requêtes n'apparaît pas dans le journal. Démarrage 9,9 s ; `sfar_search` 0,32–0,37 s à chaud ; environ 3 recherches par seconde par processus (appels sérialisés) ; mémoire 0,67–0,71 Go (macOS).
- **Non vérifié** : **l'image conteneur n'a jamais été construite** (Dockerfile écrit, démon Docker arrêté) ; taille d'image, latence et mémoire sur CPU ; **rien n'a été vérifié sur LibreDataHub** ; aucun agent LLM réel branché sur le serveur (seule la syntaxe `claude mcp add` a été vérifiée) ; charge soutenue au-delà de 8 appels.
- **Pas prêt pour un service public** : pas d'authentification, pas de limitation de débit ni de quotas, pas de limite de taille du corps HTTP, pas de TLS ; **droits de diffusion des extraits SFAR non réglés** (décision SFAR).

## 12. Ce que nous demandons aux médecins

1. **`reports/A_VALIDER_MEDECINS.md`** : liste consolidée des points de sécurité clinique (pour chacun : confirmé / à corriger / sans objet, et le nom du relecteur). Principaux groupes :
   - doses et valeurs chiffrées : adrénaline pédiatrique de l'arrêt cardiaque 2006 imprimée en mg/kg (erreur ×1 000) et corrigée par un erratum officiel dans le même PDF (correction appliquée de façon visible dans l'index, à contresigner) ; doutes sur des textes d'origine (morphine chez l'enfant ORL 2014, paracétamol < 10 kg, cible de diurèse du brûlé grave 2019, acide tranexamique 2001, cotation MTEV 2011) ; l'audit n'a trouvé aucune erreur de conversion OCR, mais les erreurs ×10 ne sont pas détectables par cette méthode ;
   - statut des éditions : textes anciens « en vigueur » contredits par des textes récents (arrêt cardiaque 2006, SDRA 2018 vs sepsis 2025, plasma 2012 vs 2020) ; remplacements partiels (AVK HAS 2008, urgences obstétricales 2010 vs RPP 2022) ; RPP COVID passée en « abrogée » ;
   - corrections déjà appliquées à la surcouche antibioprophylaxie V3.1, à contresigner ;
   - jeux internes à relire ; table de correspondance des actes adulte ↔ enfant à demander ; écarts entre deux sources (dose maximale de lidocaïne adrénalinée, intervalle de réinjection de la céfuroxime en urétéroscopie).
2. **`reports/lexique_a_valider_medecins.csv`** : les 98 entrées du lexique médical (73 sigles, 25 noms courants ou commerciaux) avec les termes que chacune ajoute à la recherche (colonnes : correct / autre sens possible / correction). Points d'attention relevés par Q1 : 13 entrées ajoutent des termes au-delà de la forme longue, dont 7 des noms de molécules ; 18 sigles ne sont définis nulle part dans le corpus en vigueur.
3. **Feuille locale de 20 réponses jugées** (`eval_internal/work/medecins/jugements_a_verifier.csv`, **non versionnée car elle contient le texte du benchmark**) : 20 réponses du test avec la grille validée, la réponse du système et les verdicts des deux juges (les 2 erreurs graves, la réponse incorrecte, 9 partielles, 8 correctes tirées au hasard), avec une colonne pour le verdict du médecin. C'est la seule façon de savoir si le juge LLM est fiable.

## 13. Ce qui reste inconnu

- **Le comportement du modèle de déploiement (~30B).** On l'attend entre le 9B et Sonnet ; ce n'est qu'une attente. À mesurer sur dev complet : exactitude, erreurs graves, abstentions à tort avec le contexte large, troncature des QCM, latence avec ~8 600 tokens de prompt, prise en compte de la désactivation de la réflexion sur vLLM, fidélité de la normalisation si elle est activée.
- **La validité du juge pour un médecin** : aucun médecin n'a relu les verdicts (section 12, point 3).
- **La qualité des réponses avec les formulations des cliniciens** : seul le retrieval a été mesuré sur la variante en langage courant.
- **Les pistes non mesurées** : modèles frontier sans RAG, document complet en contexte, approche hiérarchique, RAG agentique via MCP, fine-tuning (voir `COMPARAISON_SOLUTIONS.md`).
- **Le coût par requête en dollars** : toutes les générations et tous les jugements ont été faits par des sous-agents Claude Code sous abonnement ; aucune dépense API n'a été engagée (clé API refusée le 26/11 ; `reports/cost_ledger.csv` n'existe pas). Seul le volume est connu : ~20 000 caractères de contexte et ~8 600 tokens de prompt par question avec la configuration retenue.

## 14. Reproduire

- Retrieval figé : tag `retrieval-freeze-20261127`, configuration `C10_context_notes`, index `index/tas_v6` (manifeste sha256 `829f9fa3…`).
- Profil servi et évalué : `src/rag_sfar/generation/profile.py::PRODUCTION`.
- Commandes de capture, d'export à l'aveugle et d'import : `reports/agents/B3_generation.md` §1 et §6 bis ; jugement : `reports/agents/J1_juge_v4.md` §4.
- Protocole : `eval/FINAL_EVAL_PROTOCOL.md` ; résumé jugé : `reports/eval/judge_v4/blind_final/summary.md` ; grilles validées : `reports/eval/judge_v4/blind_v31grid2/combined_validated_grid.md`.
- Robustesse : `eval_internal/robustness/README.md` ; benchmark validé : `reports/agents/V1_benchmark_valide.md` ; `genprobe2` : `eval_internal/genprobe2_run.py` et `reports/agents/G1_genprobe2_run.md`.
