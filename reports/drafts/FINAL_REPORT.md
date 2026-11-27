# RAG-SFAR — Rapport final (brouillon du 2026-11-27)

> Brouillon rédigé à partir de `JOURNAL.md`, `eval/FINAL_EVAL_PROTOCOL.md`, `reports/eval/judge_v4/blind_final/summary.md` et des rapports d'agents (`reports/agents/*.md`). Aucun chiffre n'a été recalculé pour ce document. Les lignes « À COMPLÉTER » signalent des résultats encore en cours de mesure.

## 0. À lire d'abord

- **Ce que mesurent nos chiffres principaux.** Avec un générateur de substitution (Claude Sonnet) recevant exactement les prompts de notre configuration, 53,6 % [41,2–65,7] des réponses (37 sur 69) aux questions de test du benchmark enrichi sont jugées conformes à la référence par un juge LLM (Claude Haiku, grille v4, non validée médicalement). Ce chiffre décrit ce que l'étage de génération peut atteindre avec ce contexte et ce prompt. **Le modèle qui serait déployé (un modèle ouvert d'environ 30 milliards de paramètres) n'a jamais été mesuré.**
- **Le dev était optimiste.** Sur les mêmes types de questions, le dev donnait 73,6 % de réponses correctes et 95,7 % de suffisance des preuves ; le test donne 53,6 % et 82,8 %. Les correctifs du retrieval avaient été conçus en lisant les échecs du dev ; ils n'ont pas transféré au test.
- **Erreurs graves.** Sur le test du benchmark enrichi, 4 réponses sur 69 (5,8 % [1,6–14,2]) sont signalées graves par au moins un des deux juges, toutes du même type : une conduite unique imposée alors que la population ou la situation n'était pas précisée. Aucune mauvaise molécule, mauvaise dose, conduite opposée ou édition périmée n'a été relevée (0 sur 69, borne haute de l'intervalle exact 5,2 %).
- **Rien n'est validé cliniquement.** Les questions du benchmark enrichi ont été validées par des médecins ; nos jeux internes sont synthétiques ; aucun médecin n'a relu nos réponses ni la grille du juge.

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

Le même profil `PRODUCTION` est servi par l'API, les deux serveurs MCP (MCP : protocole qui permet à un assistant IA d'appeler nos outils de recherche) et l'outil de rejeu utilisé pour l'évaluation ; un test vérifie que le prompt de l'API et celui du rejeu sont identiques à l'octet.

### 1.2 Ce qu'il n'est pas

- **Pas un dispositif médical** et pas un outil validé cliniquement.
- **Pas mesuré avec le modèle de déploiement.** Le générateur visé (modèle ouvert ~30B sur LibreDataHub) n'a pas pu tourner sur la machine de développement (16 Go de RAM). Les chiffres de génération viennent d'un substitut (Claude Sonnet) et, pour le « petit modèle », de Qwen3.5-9B en 4 bits.
- **Pas un benchmark.** Les jeux de questions que nous avons créés (`eval_internal/`) sont des outils internes, synthétiques, non validés médicalement (principe 4 bis). Le benchmark de référence est celui des experts (`benchmark-enrichi`).
- **Pas couvert hors de son corpus** : la recherche renvoie toujours des passages, même hors sujet ; l'abstention repose sur le générateur.

## 2. Ce qui a été mesuré : jeux, auteurs, protocole

### 2.1 Jeux d'évaluation

| Jeu | Questions | Qui les a écrites | Validées par des médecins ? | Rôle |
|---|---:|---|---|---|
| `abpe171` (benchmark enrichi, antibioprophylaxie V3.1) | 171 : 102 dev / 69 test (scellé) | experts du projet `benchmark-enrichi` | **oui** (référence V3.1 provisoire) | résultat principal |
| `abp171` (benchmark historique) | mêmes 171 questions, références de l'édition précédente | benchmark existant | oui (édition antérieure) | dev seulement ; test non exécuté (références périmées) |
| `multirfe_synth` | 151 : 94 dev / 57 test ; 22 RFE uniquement en test | générées par un LLM (Claude Opus), vérifiées par d'autres sous-agents Claude | **non** | généralisation sur des RFE jamais vues |
| `genprobe` | 48 questions, 47 RFE hors antibioprophylaxie, conçues difficiles | générées par un LLM | **non** | sonde tenue à l'écart, exécutée une fois |
| `genprobe2` | 60 questions, 49 RFE | générées par un LLM, scellées | **non** | sonde tenue à l'écart pour les explorations du 27/11 (non encore exécutée) |
| `x2_dev` | 16 questions à deux sources | écrites par un sous-agent pour le développement | **non** | outil de développement, pas une preuve |
| Jeux perturbés (robustesse) | copies déformées automatiquement des questions dev | générées par script | sans objet | robustesse aux fautes et abréviations |

Coffre-fort : les fichiers de test sont scellés par empreinte SHA-256 dans `eval/LOCKBOX.md` ; un test pytest vérifie les empreintes. Limite déclarée dans le coffre-fort : les 171 questions du benchmark avaient déjà été vues par les équipes précédentes et par un autre agent (Gemini Neon) qui a réglé le pipeline dessus ; le test `abpe171` n'est tenu à l'écart que de nos propres réglages.

### 2.2 Protocole de l'évaluation finale

Le protocole a été écrit et commité avant l'exécution (`eval/FINAL_EVAL_PROTOCOL.md`, commit `9cb0c24`) : configuration figée, jeux exécutés une seule fois, métriques principales, sous-groupes, règles d'échec et formulation des résultats.

- **Générateur (substitut)** : Claude Sonnet, sous-agents Claude Code, lots de 8 cas au plus, identifiants opaques, cas mélangés.
- **Juge** : Claude Haiku, grille v4, à l'aveugle (dev et test mélangés, identifiants opaques), deux passes indépendantes par réponse. Combinaison stricte déclarée d'avance : une réponse est « correcte » si les deux juges le disent ; une erreur est « grave » si l'un des deux la signale.
- **Intervalles** : intervalles de confiance (IC) à 95 % ; exacts (Clopper-Pearson) pour les taux rares, bootstrap pour les écarts.
- **Accord entre les deux juges** (370 réponses) : correct / partiel / incorrect 94,3 % (κ = 0,83) ; erreur grave 98,9 % (κ = 0,74). Le kappa (κ) mesure l'accord au-delà du hasard (1 = parfait).
- **Calibration du juge sous la grille v4** : contre des clés déterministes sur 141 réponses courtes de l'antibioprophylaxie, accord 92,9 %, κ = 0,85 ; 0 verdict modifié sur 14 réponses rallongées (biais de longueur). Ce n'est pas une validation par un médecin.

### 2.3 Métriques de retrieval

- **Suffisance des preuves** (`sufficiency`, benchmark enrichi) : toutes les preuves exigées par les experts sont dans le contexte montré au générateur.
- **Rappel des preuves** : part des preuves présentes.
- **Passage dans le contexte** (`passage_hit`, jeux synthétiques) : le passage de référence est dans le contexte.

## 3. Résultats de l'évaluation finale

Formulation (protocole, section 7) : avec un générateur de substitution (Claude Sonnet) recevant exactement les prompts de notre configuration, X % [IC] des réponses sont jugées conformes à la référence par un juge LLM (Claude Haiku, grille v4, non validée médicalement).

### 3.1 Tableau principal

| Jeu | Nature | n | Correct (2 juges) | Correct ou partiel | Erreur grave (≥ 1 juge) | Erreur grave (2 juges) | Retrieval |
|---|---|---:|---|---|---|---|---|
| **abpe171 test** | validé par des médecins | 69 | **53,6 % [41,2–65,7]** (37) | 97,1 % [89,9–99,6] (67) | **5,8 % [1,6–14,2]** (4) | 2,9 % [0,4–10,1] (2) | suffisance 82,8 % (53/64) ; rappel 92,7 % |
| abpe171 dev (confirmation) | validé par des médecins | 72 | 73,6 % [61,9–83,3] (53) | 97,2 % [90,3–99,7] (70) | 2,8 % [0,3–9,7] (2) | 2,8 % (2) | suffisance 95,7 % |
| abpe171 dev (itération) | validé par des médecins | 30 | 73,3 % [54,1–87,7] (22) | 93,3 % (28) | 3,3 % [0,1–17,2] (1) | 0 | suffisance 96,2 % |
| **multirfe_synth test** (22 RFE jamais vues) | synthétique (LLM) | 57 | **91,2 % [80,7–97,1]** (52) | 98,2 % (56) | **0 % [0–6,3]** (0) | 0 | passage 97,9 % |
| multirfe_synth dev (confirmation) | synthétique (LLM) | 64 | 98,4 % [91,6–100] (63) | 100 % | 0 % [0–5,6] | 0 | passage 98,1 % |
| multirfe_synth dev (itération) | synthétique (LLM) | 30 | 86,7 % [69,3–96,2] (26) | 96,7 % | 0 % [0–11,6] | 0 | passage 91,7 % |
| **genprobe** (47 RFE hors antibioprophylaxie) | synthétique (LLM), difficile | 48 | **75,0 % [60,4–86,4]** (36) | 93,8 % [82,8–98,7] (45) | 6,2 % [1,3–17,2] (3) | 4,2 % [0,5–14,3] (2) | suffisance 77,1 % ; passage 91,7 % |

Autres mesures sur abpe171 test : comportement accepté (réponse, demande de précision ou réponse conditionnelle, selon ce que la référence accepte, lecture stricte) 92,8 % [83,9–97,6] (64/69) ; abstention à tort 1,4 % [0,0–7,8] (1/69) ; faits obligatoires énoncés 70,3 % (dev 85,0 %). Le contrôle déterministe a signalé 0 réponse sur 69 (abpe171 test), 3,5 % (multirfe test), 0 sur 48 (genprobe). Fidélité aux extraits cités (juge) : 95,6 % / 100 % / 97,7 %.

Le jeu `multirfe_synth` a été écrit et vérifié par Claude, répondu par Claude et jugé par Claude. Sur les questions humaines, le gain de Sonnet sur le petit modèle était environ deux fois plus faible que sur ce jeu (section 6.3) : ses scores surestiment probablement Claude d'une dizaine de points.

**Grilles de référence utilisées.** Les résultats pré-enregistrés ci-dessus sont jugés contre le **brouillon** du benchmark enrichi daté du 26/11 à 08:36 (`questions_enriched_draft.jsonl`, commit `eabcefc`). Les experts ont publié depuis une version validée : `sfar-abp-v31.1-valide` garde les mêmes 171 questions mais 37 grilles de réponse ont été révisées par un médecin, dont la politique appliquée aux questions à clarification ; `sfar-abp-v31.2-200` ajoute 29 reformulations en langage courant approuvées (abréviations, raccourcis, synonymes de cliniciens), et une variante complète en langage courant des 171 questions existe (88 formulations diffèrent). L'intégration est en cours (agent V1, rapport attendu `reports/agents/V1_benchmark_valide.md`). Les chiffres de cette section ne sont donc pas des scores sur le standard validé.

À COMPLÉTER : retrieval (suffisance, rappel des preuves) de la configuration figée sur le standard validé `sfar-abp-v31.1-valide`, dev et test, d'après `reports/agents/V1_benchmark_valide.md`.

À COMPLÉTER : rejugement des réponses existantes (Sonnet, configuration figée) sous les grilles validées, présenté comme analyse secondaire post hoc : correct, correct ou partiel, erreurs graves avec IC, dev et test, et en particulier les 5 questions à clarification du test.

### 3.2 Écart dev → test sur le benchmark enrichi

| Mesure | Dev (confirmation, 72) | Test (69) | Écart [IC bootstrap non apparié] |
|---|---|---|---|
| Réponses correctes | 73,6 % | 53,6 % | **−20,0 pts [−35,5 ; −4,4]** |
| Correctes ou partielles | 97,2 % | 97,1 % | −0,1 [−5,8 ; +5,5] |
| Erreurs graves | 2,8 % | 5,8 % | +3,0 [−3,9 ; +10,2] |
| Suffisance des preuves | 95,7 % | 82,8 % | **−12,9 [−23,7 ; −3,4]** |
| Faits obligatoires | 85,0 % | 70,3 % | −14,7 [−28,5 ; −0,6] |

Sur `multirfe_synth` : correct −7,2 [−15,8 ; −0,2] ; passage −0,2 (non significatif).

**Ce que cela veut dire.** Le retrieval a été mis au point en lisant les échecs du dev ; il y atteint 96 % de suffisance et 83 % sur le test. La composition des jeux n'explique pas l'écart : les questions pédiatriques sont 34/102 en dev et 26/69 en test, mais leur suffisance passe de 94,1 % à **69,2 % (18/26)**, contre 96,8 % → 92,1 % pour les autres. Le dev réparé n'était plus représentatif.

**Gains de retrieval qui n'ont pas transféré** (analyse post hoc, retrieval seul, après lecture des résultats ; déclarée exploratoire) :

| Configuration | abpe171 dev, suffisance | abpe171 test, suffisance | multirfe test, passage |
|---|---|---|---|
| BM25 seul | 88,5 | 78,1 | 70,8 |
| C9 (hybride simple) | 88,5 | 82,8 | 85,4 |
| C9 + fenêtres | 92,7 | 82,8 | 97,9 |
| C10_context_notes (figée) | 95,8 [92–99] | 82,8 | 97,9 |

Les gains de C10 et des fenêtres mesurés sur le dev du benchmark enrichi (+3 à +10 points selon l'index) valent **0** sur son test. En revanche, les fenêtres de contexte généralisent hors antibioprophylaxie : +12,5 points [+4,2 ; +20,8] sur `multirfe_synth` test et +14,6 [+6,2 ; +25,0] de suffisance sur `genprobe`. C10 ne coûte rien de mesurable (même latence) mais n'apporte rien de démontré par rapport à C9 + fenêtres.

### 3.3 Sous-groupes déclarés (abpe171 test)

| Sous-groupe | Correct | Correct ou partiel |
|---|---|---|
| QCM (14) | 7 | 13 |
| Questions ouvertes (55) | 30 | 54 |
| Pédiatriques (26) | 12 | — |
| À clarification (5) | 1 | 4 (et 3 erreurs graves) |
| Suffisance = 1 (53) | 31 | 53 (1 grave) |
| Suffisance = 0 (11) | 5 | 10 |

Quand toutes les preuves sont dans le contexte, la réponse est presque toujours au moins partiellement juste (53/53) ; les réponses incomplètes viennent surtout d'omissions (volet pédiatrique, alternative) plutôt que d'erreurs de contenu.

Sensibilité à l'exposition antérieure : sans Q58 et Q152 (utilisées pour un réglage par un autre agent avant le scellement), correct 52,2 % (35/67), graves 6,0 %. L'analyse « sans aucune question exposée » est vide : les rapports non versionnés de l'autre agent mentionnent les 69 questions du test.

`multirfe_synth` test par type : ouvertes 21/22, cas cliniques 13/16, tableaux 9/9, hors corpus 9/9 abstentions correctes, comparaison d'éditions 0/1.

`genprobe` par famille (correct ; suffisance ; n = 12 chacune) : QCM 12/12 ; 12/12 — contraste de population 10/12 ; 12/12 — ligne de tableau dépendant d'une note 8/12 ; 6/12 — deux sources 6/12 ; 7/12.

## 4. Erreurs graves

Définition (grille v4) : mauvaise molécule (`wrong_drug`), mauvaise dose (`wrong_dose`), conduite opposée à la référence (`wrong_conduct`), recommandation périmée présentée comme en vigueur, affirmation non sourcée, abstention manquée hors corpus, autre erreur dangereuse (`other`), et conduite unique imposée alors qu'elle est fausse pour une population ou une situation non précisée (`unjustified_assumption`). Une abstention à tort n'est pas comptée grave ; elle a son propre taux.

### 4.1 Observées

| Jeu | Erreurs graves (≥ 1 juge) | Catégories |
|---|---|---|
| abpe171 test (69) | 4 — 5,8 % [1,6–14,2] | 4 `unjustified_assumption` : 3 questions à clarification (Q15, Q17, Q167), dont 2 signalées par les deux juges ; Q126 (dose adulte donnée sans la restreindre à l'adulte, un seul juge) |
| abpe171 dev confirmation (72) | 2 — 2,8 % [0,3–9,7] | 2 `unjustified_assumption` |
| abpe171 dev itération (30) | 1 — 3,3 % [0,1–17,2] | 1 `unjustified_assumption` |
| multirfe_synth test (57) | 0 — 0 % [0–6,3] | — |
| genprobe (48) | 3 — 6,2 % [1,3–17,2] | 2 `unjustified_assumption` (signalées par les deux juges) ; 1 `wrong_conduct` (un seul juge) ; 2 des erreurs dans la famille « contraste de population » |

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

- Suffisance pédiatrique : 94,1 % en dev, **69,2 % (18/26) en test** ; 12/26 réponses pédiatriques correctes en test.
- Échec dominant en dev (8 réponses partielles) : la réponse donne la conduite adulte seule alors que la référence attend aussi le volet pédiatrique, et la preuve pédiatrique était dans le contexte. C'est une faute de génération, pas de recherche.
- Deux mécanismes ont été essayés et rejetés (section 7) : la règle de population du retrieval (ajoutait surtout des lignes d'un autre acte avec leurs doses) et les liens structurels adulte ↔ enfant (sûrs, mais sans effet). Les tableaux pédiatriques regroupent et nomment les actes autrement que les tableaux adultes ; il faudrait une table de correspondance des actes (codes CCAM ou annotation d'experts).

### 5.2 Questions à deux sources

Sur `genprobe`, la famille « deux sources » obtient 7/12 en suffisance et 6/12 réponses correctes. Sur le jeu de développement `x2_dev`, la configuration figée n'a toutes les preuves que pour 6 questions sur 16 (37,5 %). Voir les explorations X2 (section 8).

### 5.3 Lignes de tableau dépendant d'une note ou d'un en-tête

Sur `genprobe`, 6/12 en suffisance et 8/12 réponses correctes. Les notes appelées par la ligne sont lues (`called_scope`) ; les conditions portées ailleurs (en-tête éloigné, renvoi implicite) restent manquées.

### 5.4 Clarification

Le benchmark attend, pour 11 de ses questions, une demande de précision ou une réponse conditionnelle étayée. Sur le test, 1 des 5 questions à clarification est correcte et 3 produisent une erreur grave. La frontière « clarification / réponse » ne se lit pas dans le contexte : sur les 81 questions « réponse » du dev sans âge ni population, 38 ont aussi des tableaux adulte et pédiatrique dans le contexte. Un signal déterministe « deux populations présentes, aucune nommée » se déclenche sur 3 des 6 questions à clarification du dev et sur 38 des 96 questions « réponse », et ne voit ni le site ni le grade. Aucune solution générique n'a été démontrée.

### 5.5 Robustesse aux fautes de frappe et aux abréviations

Les questions des benchmarks sont propres ; les cliniciens tapent vite. Mesure de robustesse du retrieval (agent Q1, retrieval seul, dev, perturbations synthétiques à graine fixe ; tableaux bruts `eval_internal/robustness/results/summary.md`) :

| Perturbation (configuration figée) | abpe171 dev, suffisance | Écart apparié vs propre | multirfe dev, passage |
|---|---|---|---|
| Propre | 95,8 [91,7–99,0] | — | 96,1 |
| 1 faute par question | 89,6 [83,3–95,8] | **−6,2 [−11,5 ; −2,1]** | 94,7 (−1,3 [−3,9 ; 0]) |
| 2 à 3 fautes | 84,4 [77,1–90,6] | **−11,5 [−18,8 ; −6,2]** | 93,4 (−2,6 [−9,2 ; +3,9]) |
| Accents retirés | 94,8 | −1,0 [−3,1 ; 0] | 98,7 |
| Style télégraphique | 95,8 | 0,0 [−3,1 ; +3,1] | 96,1 |
| Sigles d'utilisateur absents du corpus (ABP, ATB, IOT, ALR, RTUP, PTH, VNI ; diagnostic) | 87,5 [80,2–93,8] | **−8,3 [−14,6 ; −3,1]** | 96,1 (2 questions modifiées) |

La recherche lexicale seule s'effondre avec 2 à 3 fautes (69,8 %, −14,6 points par rapport à la configuration figée). Les variantes candidates (n-grammes de caractères `subword`, lexique médical, glossaire extrait du corpus) sont présentées en section 8.1. Ces perturbations sont synthétiques ; les formulations en langage courant approuvées par les experts (`sfar-abp-v31.2-200` et variante complète des 171 questions) permettent une mesure sur des formulations réelles.

À COMPLÉTER : effet de la formulation, langage courant − standard (variante complète des 171 questions, 88 formulations différentes, et les 29 reformulations approuvées), pour la configuration figée et pour les variantes n-grammes de caractères et lexique médical, avec IC appariés, d'après `reports/agents/V1_benchmark_valide.md`.

### 5.6 Autres limites

- **Grilles du benchmark** : les résultats pré-enregistrés sont jugés contre le brouillon du 26/11 (commit `eabcefc`), pas contre la version validée `sfar-abp-v31.1-valide` (37 grilles révisées par un médecin, politique des questions à clarification modifiée) ; voir section 3.1.
- **Juge** : grille v4 non validée par un médecin ; les extraits cités sont transmis, mais pas le contexte entier ; le bruit de jugement (1 à 2 cas sur 30 entre deux jugements des mêmes réponses en développement) est de la taille de plusieurs écarts mesurés.
- **Générateur de substitution** : pas de contrôle de la température ni du plafond de tokens côté sous-agents ; leur isolation repose sur une consigne.
- **Routage QCM** : calé sur le format `A. …` ; une question ordinaire qui énumère des éléments lettrés serait traitée comme un QCM, et le mode QCM impose une lettre unique.
- **Liste de molécules du contrôle** : surtout antibiotiques et anticoagulants.
- **Corpus** : textes anciens toujours « en vigueur » contredits par des textes plus récents (section 10).

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

Le 27/11 à 07:47, sur décision de l'utilisateur : `C10_context_notes` sur `index/tas_v6`, tag `retrieval-freeze-20261127`. Une revue indépendante (R2) a confirmé le gel en publiant cette réserve : le gain de C10 sur C9 + fenêtres n'est montré que sur l'antibioprophylaxie, et son IC touche 0 sur `tas_v6`. L'évaluation finale l'a confirmé (gain nul sur le test).

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
| Format de contexte historique (ordre en U, sans fusion) | structuré − historique : +3,3 [−6,7 ; +13,3] (n.s.), −18 % de tokens pour le structuré | format structuré gardé |

## 8. Explorations du 27 novembre

Après l'évaluation finale, quatre pistes ont été rouvertes sur deux objections de l'utilisateur : la robustesse aux saisies réelles n'avait jamais été mesurée, et le besoin couvert par l'ancien module correctif (questions à deux sources) n'est pas résolu. Règles : chaque mécanisme est un module séparé autour du retriever gelé, désactivé par défaut, avec un test d'identité ; mise au point sur dev ; les candidats retenus seront exécutés **une seule fois** sur la sonde scellée `genprobe2`. **Aucune de ces pistes n'est adoptée à ce jour.**

### 8.1 Robustesse (Q1)

Tableaux bruts disponibles (section 5.5 pour la configuration figée). Variantes contre la configuration figée, abpe171 dev, suffisance, apparié :

| Variante | 2 à 3 fautes | Sigles d'utilisateur | Propre | Latence médiane |
|---|---|---|---|---|
| n-grammes de caractères (`subword`) | +3,1 [−1,0 ; +7,3] | +2,1 [−2,1 ; +6,2] | +1,0 [−2,1 ; +5,2] | 198 ms (figée 190) |
| lexique médical | 0 | +7,3 [+2,1 ; +13,5] | 0 | 189 ms |
| n-grammes + lexique | +4,2 [0 ; +9,4] | +10,4 [+5,2 ; +16,7] | 0 | 197 ms |
| glossaire extrait du corpus | −1,0 [−3,1 ; 0] | −1,0 [−3,1 ; 0] | −1,0 [−3,1 ; 0] | 195 ms |
| BM25 seul | −14,6 [−22,9 ; −7,3] | −1,0 | −1,0 | 2 ms |
| dense seul | −6,2 [−12,5 ; −1,0] | −18,8 [−28,1 ; −10,4] | −19,8 [−28,1 ; −12,5] | 191 ms |

Sur `multirfe_synth` dev, n-grammes : +3,9 [0 ; +9,2] avec 1 faute, +14,3 [0 ; +35,7] sur les 14 questions mises en sigles. Réserve : la perturbation « sigles d'utilisateur » utilise 7 sigles choisis par l'utilisateur, hors de la règle « glossaire du corpus » ; un gain du lexique sur ces sigles doit être vérifié contre le principe 1 (pas d'entrée de lexique justifiée par une question).

À COMPLÉTER : conclusion et décision de l'agent Q1 (`reports/agents/Q1_robustesse.md`) : variante candidate pour `genprobe2` (n-grammes, lexique, les deux, ou aucune) et vérification que les entrées de lexique qui expliquent le gain sur les sigles sont génériques.

### 8.2 Décomposition des questions et seconde passe corrective (X2)

Module `retrieval/multi_query.py`, modes `off` (défaut), `decompose`, `ce_gap`, `llm_correct`. Jeu de développement `x2_dev` (16 questions à deux sources, écrit par un sous-agent) : la configuration figée y a une suffisance de 37,5 % (6/16).

- Option 2, seconde passe sans LLM : négative (section 7).
- Option 1, décomposition par un LLM avant la recherche (réponses du substitut Sonnet, 212 prompts) : le LLM a jugé « question multiple » 0 question sur 102 d'abpe171 dev, 2 sur 94 de multirfe dev, 9 sur 16 de x2_dev.

À COMPLÉTER : effet mesuré de la décomposition (option 1) sur la suffisance et le rappel des preuves (abpe171 dev, multirfe dev, x2_dev), avec IC et latence, d'après `reports/agents/X2_decomposition.md`.

À COMPLÉTER : effet mesuré de la seconde passe corrective avec LLM (option 3, 209 prompts, lot 06 refait après autorisation de l'utilisateur), avec IC et latence.

À COMPLÉTER : décision de X2 (option candidate pour `genprobe2` ou aucune).

### 8.3 Reformulation de la question par un LLM (Q2)

Module `retrieval/query_rewrite.py`, désactivé par défaut ; variantes : normalisation prudente, reformulation libre, passage hypothétique (HyDE : le LLM écrit une réponse supposée qui sert de requête) ; usage en remplacement ou en ajout du contexte gelé. 1 804 réformulations produites par des agents Haiku (substitut). Lecture d'un échantillon par l'orchestrateur : normalisation fidèle ; les passages hypothétiques contiennent des précisions inventées (seuil de pression, association de molécules), ce qui est un risque clinique si ces textes servent de requête.

À COMPLÉTER : résultats de Q2 (`reports/agents/Q2_reformulation.md`) : effet sur la suffisance en conditions propres et perturbées (1 faute, 3 fautes, sigles), fidélité des reformulations sur au moins 100 lectures (contenu clinique perdu, ajouté ou altéré), latence, et décision (variante candidate pour `genprobe2` ou aucune).

### 8.4 Sonde tenue à l'écart `genprobe2`

60 questions synthétiques (LLM), 49 RFE en vigueur : deux sources 20 ; contrepartie de population 20 (dont 6 sur l'antibioprophylaxie V3.1) ; note ou en-tête de tableau 12 ; contrôles 8. Scellée (SHA-256 `76be3ccd…a5ca255`), non validée médicalement, écrite à l'aveugle des méthodes. Aucune exécution à ce jour.

À COMPLÉTER : liste des candidats exécutés sur `genprobe2` (configuration figée comme référence + candidats issus de Q1, X2, Q2), heure de l'exécution unique consignée dans `JOURNAL.md`.

À COMPLÉTER : résultats `genprobe2` par famille (suffisance, rappel des preuves, passage), écarts appariés candidat − figée avec IC, latence, et décision d'adoption ou non pour chaque candidat.

## 9. Écarts au protocole

D'après `JOURNAL.md` :

1. Deux lots de `genprobe` ont été lancés quelques secondes après les autres (limite de 20 agents simultanés).
2. Une précision d'outillage (`--run blind_final` pour la commande `show`) a été ajoutée au message de tâche des juges, sans modifier le fichier de consignes figé.
3. L'analyse de sensibilité « sans les questions exposées » est vide de sens : toutes les questions du test sont mentionnées dans les rapports non versionnés de l'autre agent (le protocole, d'après la revue R3, en comptait 16).
4. L'analyse retrieval C9 / C9 + fenêtres / C10 / BM25 sur les splits test est post hoc, faite après lecture des résultats.
5. L'heure « 08:45 » écrite dans le protocole est une estimation ; le commit a été fait vers 08:38 (l'horodatage git fait foi).

Les jeux `abpe171` test, `multirfe_synth` test et `genprobe` ne sont plus vierges et ne servent plus à aucun réglage.

## 10. Sécurité clinique : points à faire relire par un médecin

La liste complète est dans **`reports/A_VALIDER_MEDECINS.md`** (réponse attendue pour chaque point : confirmé / à corriger / sans objet, avec le nom du relecteur). Principaux groupes :

- **Doses et valeurs chiffrées.** Adrénaline pédiatrique de l'arrêt cardiaque 2006 imprimée en mg/kg (erreur ×1 000) et corrigée par un erratum officiel dans le même PDF : correction appliquée de façon visible dans l'index, à contresigner. Doutes sur des textes d'origine : morphine chez l'enfant (ORL 2014), paracétamol < 10 kg, cible de diurèse du brûlé grave 2019, unité de temps de l'acide tranexamique (2001), cotation MTEV 2011. L'audit des doses n'a trouvé aucune erreur de conversion OCR ; les erreurs ×10 (virgule perdue) ne sont pas détectables par cette méthode.
- **Statut des éditions.** Textes anciens « en vigueur » contredits par des textes récents (arrêt cardiaque 2006, SDRA 2018 vs sepsis 2025, plasma 2012 vs 2020) ; remplacements partiels (AVK HAS 2008, urgences obstétricales 2010 vs RPP 2022) ; RPP COVID passée en « abrogée ».
- **Corrections déjà appliquées à la surcouche antibioprophylaxie V3.1** (lignes « faible risque → pas d'antibioprophylaxie », « céfoxitine », coquilles de noms d'actes et de molécules), vérifiées contre le PDF officiel par l'orchestrateur, à contresigner.
- **Jeux internes à relire** (`eval_internal/a_valider_medecins.csv`, CSV de `genprobe2`).
- **Points du 27/11** : table de correspondance des actes adulte ↔ enfant à demander ; écart de dose maximale de la lidocaïne adrénalinée entre deux sources ; écart d'intervalle de réinjection de la céfuroxime (urétéroscopie) entre deux sources.

## 11. Ce qui reste inconnu

- **Le comportement du modèle de déploiement (~30B).** On l'attend entre le 9B et Sonnet ; ce n'est qu'une attente. À mesurer sur dev complet : exactitude, erreurs graves, abstentions à tort avec le contexte large, troncature des QCM, latence avec ~8 600 tokens de prompt, prise en compte de la désactivation de la réflexion sur vLLM.
- **La validité du juge pour un médecin.** Aucun médecin n'a relu les verdicts.
- **La performance sur des questions réelles de cliniciens** (fautes, sigles, questions mal posées) : seule une simulation existe.
- **Les pistes non mesurées** : modèles frontier sans RAG, document complet en contexte, approche hiérarchique, RAG agentique via MCP, fine-tuning (voir `COMPARAISON_SOLUTIONS.md`).
- **Le coût par requête en dollars** : toutes les générations et tous les jugements ont été faits par des sous-agents Claude Code sous abonnement ; aucune dépense API n'a été engagée (clé API refusée le 26/11, ledger vide). Seul le volume est connu : ~20 000 caractères de contexte et ~8 600 tokens de prompt par question avec la configuration retenue.
- **Les résultats des explorations du 27/11** (section 8).
- **Les scores sur le standard validé des experts** et sur leurs formulations en langage courant (section 3.1 et 5.5), en cours d'intégration.

## 12. Reproduire

- Retrieval figé : tag `retrieval-freeze-20261127`, configuration `C10_context_notes`, index `index/tas_v6` (manifeste sha256 `829f9fa3…`).
- Profil servi et évalué : `src/rag_sfar/generation/profile.py::PRODUCTION`.
- Commandes de capture, d'export à l'aveugle et d'import : `reports/agents/B3_generation.md` §1 et §6 bis ; jugement : `reports/agents/J1_juge_v4.md` §4.
- Protocole : `eval/FINAL_EVAL_PROTOCOL.md` ; résumé jugé : `reports/eval/judge_v4/blind_final/summary.md`.
