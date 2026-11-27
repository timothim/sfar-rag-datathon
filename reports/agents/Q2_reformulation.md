# Q2 — Réécrire la question par un modèle de langage avant le retrieval ? (2026-11-27)

**Dev seulement** (`abpe171` dev, 102 q. ; `multirfe_synth` dev, 94 q.) et copies perturbées de ces questions par Q1 (`eval_internal/robustness/sets/`, lecture seule). Aucun split test, ni `genprobe`, ni `genprobe2` n'a été ouvert. Le modèle de langage est un **remplaçant** : des agents Claude Haiku ont répondu aux prompts exacts du module (46 lots à l'aveugle, ids opaques, 1 804 réponses, import strict sans aucun refus). Le modèle déployé (open source de taille moyenne) n'a pas été mesuré. Les métriques portent sur le retrieval seul. L'effet sur la réponse générée n'a pas été mesuré.

Types de questions : `abpe171` = questions validées par des médecins (benchmark des experts) ; `multirfe_synth` = questions synthétiques écrites par LLM, non validées ; les perturbations (fautes, abréviations) sont automatiques (graine fixe, Q1).

## 1. Ce qui a été construit

- `src/rag_sfar/retrieval/query_rewrite.py` : enveloppe `QueryRewriteRetriever` autour du retriever gelé (`C10_context_notes`, `index/tas_v6`). Elle a la même interface `retrieve(...)` et reste **désactivée par défaut**. `wrap_retriever(base)` renvoie `base` lui-même quand la réécriture est désactivée. `pipeline.py`, `config.py` et `ablation.py` ne sont pas modifiés (diff vide depuis `retrieval-freeze-20261127`).
- Un appel court qui ne voit **que l'énoncé**. Pour un QCM, les options ne sont pas montrées au modèle et sont recollées telles quelles après la réécriture : le modèle ne peut pas recopier une option (un candidat-réponse) dans la question et orienter la recherche vers elle. La sortie tient sur une ligne, au format strict. Toute réponse hors format, toute erreur du modèle, `INCHANGEE`, ou une réécriture identique à la casse, aux accents et à la ponctuation près rendent la sortie gelée.
- Trois prompts, en français, neutres (aucun nom de médicament, d'acte ou de recommandation, aucun chiffre, aucun exemple ; testé) :
  1. `normalize` (normalisation conservatrice) : corriger l'orthographe et les accents ; développer une abréviation dont le sens est certain, en écrivant « forme longue (SIGLE) » ; écrire une phrase complète. Il est interdit d'ajouter, de retirer ou de remplacer une information clinique, et de « corriger » un nom dont le modèle n'est pas sûr. Réponse `INCHANGEE` si la question est déjà propre.
  2. `reformulate` (reformulation libre dans le vocabulaire des recommandations, en gardant le sens).
  3. `hyde` (passage hypothétique : le modèle écrit le passage de recommandation qu'il s'attend à trouver, utilisé seulement comme requête).
- Deux usages :
  - `replace` : on cherche avec la réécriture à la place de la question.
  - `add` : on cherche avec la question **et** la réécriture, puis on fusionne (`merge_add`). **Garantie** : le contexte gelé est conservé en entier, dans le même ordre et aux mêmes rangs. Les blocs de la réécriture (extrait classé + sa fenêtre) viennent ensuite, dans leur ordre, sans doublon (même id ou même texte), tant que le budget du générateur le permet (préréglage `wide` : 40 extraits, 30 000 caractères). Un bloc dont l'extrait classé ne tient pas est écarté. Par construction, sufficiency, evidence_recall et passage_hit ne peuvent donc **pas baisser** question par question. La contrepartie : la réécriture n'a que la place laissée par le contexte gelé (médiane ~10 000 caractères, environ 6 extraits ajoutés en moyenne).
- Garde-fou déterministe optionnel (`guard=True`, mesuré comme variante à part) : la réécriture est rejetée si elle perd un nombre, une négation ou un mot de population, ou si elle ajoute un nombre.
- `tests/test_query_rewrite.py` (14 tests) :
  - réécriture désactivée = mêmes extraits et mêmes scores que la configuration gelée ;
  - chaque repli (INCHANGEE, réponse mal formée, réécriture identique, modèle indisponible) dans les deux usages ;
  - options de QCM masquées au modèle et recollées à l'identique ;
  - `add` = sur-ensemble ordonné du contexte gelé, dans le budget ;
  - analyseur strict, garde-fou, interrupteur, neutralité des prompts.

  Suite complète verte, test anti-fuite silencieux. Pendant la mesure, le cache du retriever gelé a été revérifié sans cache : 25/25 requêtes identiques.
- Évaluation : `eval_internal/q2_rewrite_eval.py` (export à l'aveugle → import strict → run → analyse) ; consignes des remplaçants `reports/agents/Q2_annexes/STANDIN_INSTRUCTIONS.md`. Tout ce qui contient le texte des questions (lots, clés, réponses, lignes brutes, feuilles de lecture) reste dans `eval_internal/work/q2/`, ignoré par git.

### Conditions mesurées (une réécriture par question distincte et par variante)
- `normalize` et `reformulate` : propre, 1 faute, 3 fautes (deux suites) ; abréviations « utilisateur » (`abbr_user`, deux suites, dont seulement 2 questions modifiées sur `multirfe_synth`) ; abréviations du glossaire du corpus (`abbr`, `multirfe_synth`, 16 questions modifiées). 706 appels chacune.
- `hyde` : propre et 3 fautes, 392 appels.

## 2. Effet sur le retrieval (contexte vu par le générateur, k = 64, apparié contre le gelé sur la même condition, IC 95 % bootstrap)

### Deux suites regroupées : sufficiency (abpe171) / passage_hit (multirfe_synth), n = 172

| condition | gelé | normalize replace | normalize **add** | reformulate replace | reformulate add | hyde replace | hyde add |
|---|---:|---|---|---|---|---|---|
| propre | 95,9 | −1,2 [−3,5 ; +1,2] (1 gagnée / 3 perdues) | **+0,6 [0 ; +1,7]** (1 / 0) | −1,7 [−4,1 ; +0,6] (1 / 4) | +0,6 [0 ; +1,7] (1 / 0) | **−8,7 [−14,0 ; −4,1]** (2 / 17) | +0,6 [0 ; +1,7] (1 / 0) |
| 1 faute | 91,9 | +3,5 [+0,6 ; +6,4] (7 / 1) | **+3,5 [+1,2 ; +6,4]** (6 / 0) | +4,1 [+0,6 ; +7,6] (8 / 1) | +3,5 [+1,2 ; +6,4] (6 / 0) | — | — |
| 3 fautes | 88,4 | +6,4 [+1,7 ; +11,0] (14 / 3) | **+8,1 [+4,1 ; +12,2]** (14 / 0) | +8,1 [+4,1 ; +12,8] (15 / 1) | +8,1 [+4,1 ; +12,2] (14 / 0) | −5,2 [−11,0 ; +0,6] (9 / 18) | +4,7 [+1,7 ; +8,1] (8 / 0) |
| abréviations utilisateur | 91,3 | +4,1 [+1,2 ; +7,6] (8 / 1) | **+2,9 [+0,6 ; +5,8]** (5 / 0) | +3,5 [+0,6 ; +7,0] (7 / 1) | +2,9 [+0,6 ; +5,8] (5 / 0) | — | — |

Avec la normalisation en mode `add`, la sufficiency perturbée remonte au niveau des questions propres : 95,3 / 96,5 / 94,2 contre 95,9.

### Par suite

**abpe171, sufficiency (n = 96)** — gelé : propre 95,8 ; 1 faute 89,6 ; 3 fautes 84,4 ; abréviations 87,5.

| condition | normalize replace | normalize add | reformulate replace | reformulate add | hyde replace | hyde add |
|---|---|---|---|---|---|---|
| propre | −1,0 [−5,2 ; +2,1] | +1,0 [0 ; +3,1] | −3,1 [−7,3 ; 0] | 0 | −11,5 [−17,7 ; −5,2] | 0 |
| 1 faute | +5,2 [0 ; +10,4] | +5,2 [+1,0 ; +10,4] | +5,2 [0 ; +10,4] | +5,2 [+1,0 ; +10,4] | — | — |
| 3 fautes | +9,4 [+3,1 ; +16,7] | +11,5 [+5,2 ; +18,8] | +11,5 [+6,2 ; +18,8] | +11,5 [+6,2 ; +18,8] | −4,2 [−11,5 ; +4,2] | +5,2 [+1,0 ; +10,4] |
| abréviations utilisateur | +8,3 [+3,1 ; +14,6] | +5,2 [+1,0 ; +10,4] | +6,2 [+2,1 ; +11,5] | +4,2 [+1,0 ; +8,3] | — | — |

evidence_recall abpe171 (même ordre ; gelé 98,2 / 93,3 / 89,5 / 91,9) : normalize add +0,5 [0 ; +1,6] / +4,5 [+1,6 ; +8,5] / +8,5 [+3,8 ; +13,9] / +4,3 [+1,0 ; +8,2] ; normalize replace −0,5 / +4,5 / +7,6 / +5,7 ; hyde replace propre −9,2 [−14,1 ; −4,3].

**multirfe_synth, passage_hit (n = 76)** — gelé : propre 96,1 ; 1 faute 94,7 ; 3 fautes 93,4 ; abréviations du glossaire 92,1. Les effets vont dans le même sens mais sont petits et leurs IC touchent 0 :
- normalize add : 0 / +1,3 [0 ; +3,9] / +3,9 [0 ; +9,2] / +2,6 [0 ; +6,6] ;
- normalize replace : −1,3 [−3,9 ; 0] sur les questions propres ;
- reformulate replace : +5,3 [+1,3 ; +10,5] sur les abréviations du glossaire ;
- hyde replace : −5,3 (propre) et −6,6 (3 fautes).

Tableaux complets (toutes les variantes, garde-fou compris) : `eval_internal/work/q2/results/summary_r1.md` (local).

### Ce que montrent les pertes en mode `replace` sur les questions propres
Les 3 questions perdues par `normalize replace` ont toutes été réécrites **fidèlement** :
- « bêtalactamines » → « bêta-lactamines » ;
- « ECMO » → « oxygénation extracorporelle par membrane (ECMO) » ;
- « COVID-19 » → « maladie à coronavirus 2019 (COVID-19) ».

Le retrieval gelé est sensible à la graphie exacte : un tiret ou un sigle développé suffit à faire sortir la preuve du contexte. C'est l'argument principal pour le mode `add`. Il garantit que ce que la question d'origine trouvait reste dans le contexte.

## 3. Fidélité des réécritures

### Comptes automatiques (une ligne par question distincte et variante ; comparaison à la question reçue)

| variante | condition | n | INCHANGEE | modifiée | nombre perdu/ajouté | négation perdue | population perdue | population ajoutée |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| normalize | propre | 196 | 170 | 23 | 1 (« 2019 » de COVID-19) | 0 | 0 | 1 (« grossesse » de IVG) |
| normalize | 1 faute / 3 fautes | 196 / 196 | 5 / 0 | 179 / 194 | 0 / 0 | 0 / 0 | 0 / 0 | 3 / 10 (mot rétabli d'une faute) |
| reformulate | propre | 196 | — | 97 | 1 | 0 | 0 | 1 |
| hyde | propre | 196 | — | 196 | 73 | 6 | 9 | 32 |

Le garde-fou n'a rejeté qu'**une** réécriture de `normalize` sur question propre (le développement de COVID-19, inoffensif). Il ne détecte aucune des altérations réelles listées ci-dessous. Il n'apporte rien : je ne le retiens pas.

**Correction des perturbations** (chaque modification de Q1, forme d'origine rétablie / faute laissée / autre forme) :

| variante | 1 faute | 3 fautes | abréviations utilisateur | abréviations du glossaire |
|---|---|---|---|---|
| normalize | 190 / 5 / 1 | 474 / 7 / 4 | 104 / 0 / 0 | 14 / 4 / 0 |
| reformulate | 187 / 0 / 9 | 465 / 1 / 19 | 104 / 0 / 0 | 15 / 2 / 1 |
| hyde | — | 391 / 3 / 91 | — | — |

**Retour exact à la question propre** (même texte à la casse et aux accents près) : normalize 168/196 (1 faute), 165/196 (3 fautes) ; reformulate 110/196 et 108/196.

**Mots de relation par rapport à la question propre** (`sans`, `hors`, `avant`, `après`, `avec`, `non`) : normalize ne présente aucune inversion. Ses seules différences sont une faute laissée (« sane » pour « sans ») et le « non » de « ventilation non invasive ». Reformulate présente **4 inversions de sens**, listées ci-dessous.

### Lecture à la main (toutes les altérations trouvées)
Lu : les 23 réécritures `normalize` modifiées de questions propres (les 170 `INCHANGEE` sont fidèles par construction) ; les **97** réécritures `reformulate` modifiées de questions propres ; 40 réécritures `normalize` de questions perturbées tirées au hasard ; toutes les modifications classées « autre forme » ou « laissée » des deux variantes ; 12 passages `hyde`.

**normalize, questions propres (23 lues)** : **0 altération**. Seulement des développements de sigles avec le sigle gardé (ECMO, CPRE, BPCO, BLSE, ORL, PIC, COVID-19, SDRA, PEP, VNI, CAM, IVG, CRP, PaO2/FiO2, SpO2, FiO2, AVK, TAVI, CPAP) et deux graphies (« bêta-lactamines », « sus-trigonale »).

**normalize, questions perturbées (40 lues au hasard + 6 cas « autre forme » + 15 « laissée »)** :
- **1 mauvaise correction** : « complee » (pour « complexe ») → « complet » (« écrasement complexe » devient « écrasement complet » ; qualificatif, ni médicament ni acte). Même erreur avec reformulate.
- **0 mauvaise correction de nom de médicament ou d'acte.** En contrepartie, la variante est trop prudente sur les noms très déformés, qu'elle laisse tels quels (comme le prompt l'exige quand elle n'est pas sûre) : « dexmsdétomidine », « coledtomie », « myringoplasie », « urétéroscope », « oculocardique », et aussi « sane » (négation abîmée, non corrigée) et « ranimation ».
- 4 sigles du glossaire non développés (« CCT », « RT ») : le sens n'est pas certain, abstention conforme au prompt. « RT » a été développé en « radiographie thoracique (RT) » dans un autre lot, quand le contexte le rendait clair.
- Choix jugés acceptables : « ascès » → « accès » (c'est bien « accès de dialyse » dans l'original) ; « Candida sp. » → « Candida espèce indéterminée (sp.) » (sigle gardé, sans conséquence).

**reformulate, questions propres (97 lues)**, **9 altérations du contenu clinique** :
- **retrait** : « Un homme intubé » → « Chez un patient intubé » (le sexe compte dans le calcul du poids idéal demandé par la question) ;
- **ajouts** : « option préventive » → « option de prévention thromboembolique » (restreint la question) ; « en chirurgie prothétique » ajouté ;
- **remplacements par un terme voisin** : « hernie de l'aine » → « hernie inguinale » (plus étroit) ; « bris dentaire » → « traumatisme dentaire » ; « pneumonies » → « pneumopathies » (2 questions) ; « bicarbonates » → « bicarbonatémie » ;
- **question changée** : « que penser des posologies habituelles » → « quelles sont les posologies habituelles à considérer ou à adapter » ; « conseillée » → « recommandée » (force de la recommandation).

Le reste (≈ 85) est fidèle : ordre des mots, « grade de recommandation », sigles développés.

**reformulate, questions perturbées**, **altérations graves** (lecture des 30 cas « autre forme » et des inversions) :
- **4 inversions de sens** :
  - « sane mise en place » → « saine **avec** mise en place » (l'original dit « sans ») ;
  - « sanq hypertension intracrânienne » → « **avec** hypertension intracrânienne » ;
  - « horz contexte septique » → « **en** contexte septique » (l'original dit « hors ») ;
  - « Avatn une surrénalectomie » → « **Après** une surrénalectomie ».
- **1 acte remplacé par un autre** (le cas le plus grave pour la sécurité) : « coledtomie » (colectomie) → « **cholécystectomie** ».
- **1 population perdue** : « données adjltes » (adultes) → « données **additionnelles** ».
- **1 geste remplacé** : « aobrd chirurgical » (abord) → « **ablation** chirurgicale ».
- En contrepartie, reformulate corrige des noms que normalize laisse (« dexmsdétomidine » → « dexmédétomidine »).

**hyde** : sur 196 passages écrits pour des questions propres, 190 inventent un grade ou un niveau de preuve, et 47 contiennent une quantité absente de la question (doses comme « 2 g », durées comme « 24 heures »). Les passages nomment des molécules et des schémas que la question ne contient pas, parfois contradictoires : par exemple une antibioprophylaxie « avant l'incision » et « après le clampage du cordon » dans la même phrase. Comme requête seule, en mode `replace`, elle fait **perdre 8,7 points** de suffisance ou de passage sur les questions propres (17 questions perdues pour 2 gagnées). En mode `add`, elle est sans danger pour le retrieval mais apporte moins que la normalisation (+4,7 contre +8,1 sur 3 fautes). Comme attendu : à écarter.

### Le cas `part_34` signalé par l'orchestrateur
Deux cas ont la même réponse parce que leurs énoncés sont presque identiques : deux questions distinctes du benchmark portent sur la même chirurgie de la cataracte, l'une ouverte, l'autre en QCM dont les options ne sont pas montrées. La réponse identique est légitime.

## 4. Coût

| variante | prompt système | message | sortie moyenne (p90 / max) | jetons, tokenizer Qwen |
|---|---:|---:|---|---|
| normalize | 460 | 38 | 28 (52 / 78) ; `INCHANGEE` ≈ 4 | |
| reformulate | 212 | 38 | 42 (56 / 77) | |
| hyde | 198 | 39 | 103 (126 / 181) | |

- **Latence ajoutée, estimation** (non mesurée sur le modèle cible) : pour un modèle ouvert de taille moyenne servi sur un GPU (préremplissage ~1 000–3 000 jetons/s, décodage ~30–60 jetons/s), l'appel `normalize` coûte environ 0,2–0,5 s de préremplissage (moins avec le cache de préfixe du prompt système, identique à chaque appel) et 0,1 s (`INCHANGEE`) à 1,5 s de décodage. Soit **~0,3 à 2 s par question**, en série avant le retrieval.
- Le mode `add` ajoute une seconde recherche quand la réécriture diffère (~200 ms ; médiane mesurée 197 ms, p90 205 ms). Elle peut être lancée en parallèle de la première.
- Le contexte du générateur grossit en `add` : 20 766 → 23 461 caractères en moyenne (normalize), ~6 extraits de plus quand la réécriture sert, ce qui alourdit un peu la génération.
- Sur des questions propres, `normalize` répond `INCHANGEE` dans 87 % des cas (170/196) : pas de seconde recherche, peu de décodage.

## 5. Comparaison avec les alternatives sans LLM (Q1)
**En attente** : `reports/agents/Q1_robustesse.md` n'existe pas au moment de la rédaction. Les résultats bruts de Q1 (n-grammes de caractères, lexique, glossaire du corpus) ne sont ni rapportés ni relus, je ne les compare pas.

## 6. Limites
- **Modèle de remplacement** : Claude Haiku, plus fiable qu'un modèle ouvert de taille moyenne sur l'orthographe médicale française et sur le respect d'un interdit. La fidélité mesurée ici est un plafond plausible, pas celle du modèle déployé. **Avant toute activation, remesurer la fidélité (mêmes contrôles automatiques + lecture) avec le modèle servi.** Le mode `add` protège le retrieval contre une mauvaise réécriture, mais il ne protège pas la génération d'extraits ajoutés hors sujet.
- Les fautes et abréviations sont **synthétiques** (Q1 : une ou trois fautes par question, sept sigles cités par l'utilisateur, glossaire du corpus). De vraies saisies de médecins (style télégraphique combiné à des abréviations locales) n'ont pas été mesurées. Le style télégraphique n'a pas été inclus, parce que le retrieval gelé n'y perd rien (Q1).
- Le dev est petit (96 + 76 questions avec métrique) et s'est montré optimiste sur le test (−13 points de suffisance sur abpe171). Les gains sur 1 faute ont des IC qui touchent ou frôlent 0.
- Seul le retrieval est mesuré, pas l'exactitude des réponses ni les erreurs graves de génération.
- Le dev de `multirfe_synth` est synthétique (écrit par LLM, non validé).
- Pas de règle de décision pré-enregistrée pour cette piste : la recommandation ci-dessous a été formée après lecture des résultats.

## 7. Activer chaque variante
```bash
export RAG_SFAR_QUERY_REWRITE=normalize     # off (défaut) | normalize | reformulate | hyde
export RAG_SFAR_QUERY_REWRITE_USE=add       # add (défaut quand activé) | replace
```
```python
from rag_sfar.retrieval.query_rewrite import wrap_retriever
retriever = wrap_retriever(base_retriever, llm=served_llm)            # lit les variables ci-dessus
retriever = wrap_retriever(base_retriever, llm=served_llm, variant="normalize", use="add")  # explicite
# garde-fou (non recommandé) : wrap_retriever(..., guard=True)
```
`served_llm` = le client existant (`complete(system, user, temperature=, max_tokens=)`), appelé à température 0, 200 jetons maximum (400 pour `hyde`). Une variante activée sans modèle lève une erreur au lieu de se taire. L'API (`interfaces/api.py`) n'est pas branchée, parce que ce fichier est partagé. Il suffit d'envelopper le retriever à l'endroit où le profil de production le construit.

## 8. Recommandation
**Proposer la normalisation conservatrice en mode `add` comme candidate pour l'exécution tenue à l'écart, sous deux conditions.** Ne retenir ni la reformulation libre, ni le passage hypothétique, ni le mode `replace`, ni le garde-fou.

Pourquoi :
- **Retrieval** :
  - questions propres, la majorité : par construction aucune perte, +0,6 [0 ; +1,7] mesuré ;
  - 3 fautes : +8,1 [+4,1 ; +12,2] ;
  - 1 faute : +3,5 [+1,2 ; +6,4] ;
  - abréviations utilisateur : +2,9 [+0,6 ; +5,8] ;
  - 0 question perdue dans toutes les conditions.
- **Sécurité** : en lisant toutes ses réécritures de questions propres et 40 de questions perturbées, je n'ai trouvé aucune altération de contenu clinique sur les questions propres et une seule mauvaise correction sur les questions perturbées (un qualificatif, pas un médicament ni un acte). Aucun mot de relation n'est inversé, aucune population n'est ajoutée ni perdue.
- La reformulation libre gagne autant mais altère le sens : sur 97 réécritures de questions propres lues, 9 changent le contenu clinique ; sur les questions perturbées, elle inverse 4 négations ou relations temporelles et remplace un acte mal orthographié par un autre acte. C'est exactement le risque de changement de sens silencieux.
- Le passage hypothétique invente doses, molécules et grades, et fait perdre 8,7 points en `replace`.
- Le mode `replace` perd des preuves même avec des réécritures fidèles (graphies).

Conditions :
1. **Remesurer la fidélité avec le modèle réellement servi** (mêmes 706 prompts, même lecture). Ne pas l'activer si une inversion de négation ou une mauvaise correction de médicament ou d'acte apparaît.
2. Sur le jeu tenu à l'écart (`genprobe2`, questions propres), l'effet attendu sur le retrieval est nul par construction (0 ou +). Cette exécution ne vérifie donc que l'absence de régression, pas le bénéfice sur les saisies bruitées. Le bénéfice ne pourra être confirmé que sur de vraies saisies de médecins.

Le gain de la piste est entièrement dans la robustesse aux fautes. Si les alternatives sans LLM de Q1 (en attente) récupèrent l'essentiel de ces points sans appel supplémentaire, elles sont préférables : elles sont gratuites et ne changent jamais le sens.
