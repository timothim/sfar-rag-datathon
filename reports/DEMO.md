# Démonstrateur RAG-SFAR : guide d'utilisation

Page web unique servie par l'application FastAPI existante (`src/rag_sfar/interfaces/api.py`, page dans `src/rag_sfar/interfaces/demo_page.py`). HTML, CSS et JavaScript simples, aucune ressource chargée depuis Internet : la démonstration fonctionne hors ligne.

Ce que le jury teste est le système évalué : la page passe par `/api/query/stream`, qui construit le prompt avec le profil `PRODUCTION` (recherche `C10_context_notes` sur `index/tas_v6`, contexte structuré, prompt `clinical_concise`, QCM routés vers leur prompt). Le test `tests/test_generation_b3.py::test_api_prompt_identical_to_replay_prompt` vérifie que ce prompt est celui de l'évaluation. `tests/test_demo_chatbot.py` vérifie que les réglages du générateur changent le point d'accès et le modèle, mais pas le prompt.

## Démarrer (machine locale)

```bash
cd /Users/tim/Me/SFAR-datathon
HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-serve --host 127.0.0.1 --port 8000
```

Ouvrir ensuite http://127.0.0.1:8000/. Le démarrage a pris 10 s lors du test du 27/11 (chargement de l'index, de l'embedder et du reranker). La mémoire nécessaire sans générateur n'a pas été mesurée de façon fiable ; estimation : 2 à 4 Go. L'index servi par défaut est celui du profil (`index/tas_v6`). Le `--host 127.0.0.1` est obligatoire en local, car la valeur par défaut des réglages est `0.0.0.0`. Ports : le chatbot écoute par défaut sur 8000 (`RAG_SFAR_API_PORT`, aussi dans l'image Docker) ; le serveur MCP HTTP sur 8765 par défaut dans le code (`RAG_SFAR_MCP_PORT`), 8020 dans l'image Docker et dans `reports/MCP_DEPLOIEMENT.md`. Si le port 8000 est occupé, choisir un autre port avec `--port` (le test du 27/11 a utilisé 8010).

### Brancher un générateur

Trois possibilités :

1. **Depuis la page** : ouvrir « Réglages du générateur », saisir l'URL de base (terminée par `/v1`) et éventuellement la clé, cliquer sur « Tester la connexion » (la page liste alors les modèles servis), choisir le modèle, puis cliquer sur « Appliquer ». Le réglage vaut pour les questions suivantes.
2. **Au démarrage, par variables d'environnement** (aucun clic nécessaire) :
   `RAG_SFAR_LLM_BASE_URL=https://…/v1 RAG_SFAR_LLM_MODEL=<nom listé> RAG_SFAR_LLM_API_KEY=<clé> HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-serve --host 127.0.0.1 --port 8000`
3. **Modèle local Qwen3.5-9B MLX**. Ce petit modèle a seulement servi de substitut pendant le développement ; le générateur de substitution de l'évaluation pré-enregistrée était Claude Sonnet. Il demande environ 11 Go au pic : à lancer seulement quand aucune autre tâche n'utilise le GPU. Sur une machine de 16 Go, il ne peut pas tourner en même temps que des évaluations.
   - En processus : `HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-serve --host 127.0.0.1 --port 8000 --mlx-model /Users/tim/.cache/rag_sfar_models/Qwen3.5-9B-MLX-4bit-nothink`. Le panneau de réglages est alors en lecture seule.
   - Ou comme serveur compatible OpenAI : `.venv/bin/mlx_lm.server --model /Users/tim/.cache/rag_sfar_models/Qwen3.5-9B-MLX-4bit-nothink --host 127.0.0.1 --port 8080`, puis saisir `http://127.0.0.1:8080/v1` dans la page. Si ce serveur refuse le champ `chat_template_kwargs`, décocher « Envoyer enable_thinking=false » ; le dossier `-nothink` désactive déjà la réflexion dans son modèle de chat. **Non testé.**

Paramètres d'appel : par défaut, ceux du profil évalué (max_tokens 1024, température 0, `enable_thinking=false` transmis par `chat_template_kwargs`, comme pour Qwen servi par vLLM). Les champs « Tokens max » et « Température » permettent d'y déroger ; tout écart sort de la configuration évaluée.

### Clé d'API

La clé est envoyée par le navigateur au serveur, qui la garde **en mémoire uniquement**. Elle n'est écrite ni dans un fichier ni dans un journal, et aucun point d'accès ne la renvoie : la page indique seulement qu'une clé est enregistrée. Les messages d'erreur se limitent au type d'erreur et au code HTTP, car le corps d'erreur d'un fournisseur peut reprendre une partie de la clé.

### Verrouillage des réglages

`RAG_SFAR_DEMO_LOCK_SETTINGS=1` place le panneau en lecture seule. Le serveur refuse alors toute modification (HTTP 403), et « Tester la connexion » ne teste que le point d'accès configuré. Ce réglage est **obligatoire pour toute instance accessible à des visiteurs** : sans lui, n'importe qui pourrait faire appeler par le serveur une URL de son choix. Par défaut (démonstration locale), les réglages sont modifiables.

## Ce que voit le jury

- En tête de page, un bandeau permanent : prototype de recherche, ne remplace ni la recommandation ni le jugement clinique. Juste dessous, le générateur qui répond (modèle et URL) avec un témoin d'état : vert s'il a répondu, rouge s'il était injoignable au dernier essai, jaune s'il n'a pas encore été sollicité.
- Les boutons d'exemples, rédigés pour la démonstration (voies aériennes, diabète, obstétrique, pédiatrie, réanimation, allergie, plus une question hors périmètre pour montrer l'abstention). Aucun ne vient d'un jeu d'évaluation.
- Une conversation : les questions successives restent affichées, mais **chacune est traitée indépendamment**. Le système évalué fonctionne question par question, sans mémoire.

### Mode « Répondre »

La réponse s'affiche au fil de la génération. Ensuite :
- chaque citation [S1], [S2]… devient un lien qui déplie et surligne le passage correspondant. Une citation sans passage correspondant apparaît en rouge ;
- « Sources citées » : pour chaque source, le titre de la recommandation, le type et l'année, l'édition (en vigueur ou antérieure), la section, le niveau de preuve GRADE si présent, et le texte complet du passage à déplier. Les autres passages fournis au modèle sont repliés en dessous ;
- les alertes : celle du contrôle automatique (dose, molécule ou citation absente des passages), les citations invalides, une réponse sans citation, une abstention.

### Mode « Passages seuls »

Ce mode n'utilise aucun modèle de langage. Il affiche les passages retrouvés, dans l'ordre de classement, avec les mêmes métadonnées. C'est la partie du système entièrement mesurée.

**Repli automatique** : si le générateur est injoignable, ou s'il tombe en cours de session (mauvaise URL, mauvaise clé, serveur arrêté), la page l'indique en rouge et affiche les passages seuls au lieu d'échouer. Une réponse interrompue en cours de génération est signalée « à ne pas utiliser ».

### Robustesse aux fautes et abréviations (sélecteur par question)

On peut poser la même question avec chaque option et comparer. Chaque réponse indique la variante qui l'a produite.

- **aucune** (par défaut) : la configuration gelée, celle qui a été évaluée.
- **lexicale** : la recherche active en plus l'index de n-grammes de caractères (`use_subword`) et développe les sigles « purs » de la question (ABP → antibioprophylaxie), affichés sous la réponse. La recherche tolère ainsi mieux les fautes de frappe et les sigles, sans appel au modèle. Les candidats mesurés utilisaient le lexique complet ; la démonstration sert la version réduite aux 60 sigles purs (aucun nom de molécule ni mot de thème ajouté, `use_medical_lexicon` reste désactivé), que Q1 a mesurée équivalente sur dev.
- **normalisation par le modèle** : le générateur corrige l'orthographe et développe les abréviations de la question. Le système cherche ensuite avec la question d'origine **et** la question normalisée (mode `add`) : le contexte gelé est conservé, puis complété. La question normalisée est affichée à l'écran ; si le modèle l'a laissée inchangée ou s'il est injoignable, la page le dit. Option indisponible sans générateur.
- **les deux** : les deux options combinées.

Valeur par défaut côté serveur : `RAG_SFAR_DEMO_ROBUSTNESS=none|lexical|normalize|both`.

**Réserve à dire au jury** : ces deux options ont été mesurées sur les questions de développement seulement. Elles ne font pas partie de l'évaluation pré-enregistrée. La fidélité de la normalisation a été mesurée avec Claude Haiku et non avec le modèle servi (rapport `reports/agents/Q2_reformulation.md`). Coût en mémoire : nul. Aucune option ne charge de modèle ni d'index supplémentaire ; l'index de n-grammes est déjà chargé avec l'index principal.

## Limites à dire à voix haute

- Prototype de recherche, non validé pour l'usage clinique. Toujours relire le passage cité.
- Les chiffres de qualité publiés portent sur la recherche de passages et sur un générateur précis (rapports d'évaluation). Un autre générateur branché depuis la page n'a pas été évalué.
- Le système traite une question à la fois, sans mémoire de la conversation.
- Le corpus se limite aux documents SFAR indexés. Une question hors corpus doit conduire à une abstention, mais ce comportement n'est pas garanti.
- Les éditions antérieures peuvent apparaître dans les passages ; elles sont marquées « édition antérieure ».

### Dictionnaire des cliniciens (ajouté le 27/11, après les mesures)

Le choix « lexicale » développe désormais 461 sigles : les 60 sigles « purs » du lexique d'origine et 401 sigles d'un dictionnaire hospitalier fourni par l'équipe (`src/rag_sfar/retrieval/clinician_acronyms.py`, généré par `scripts/build_clinician_acronyms.py`). Chaque sigle est développé par sa seule forme longue : aucun nom de molécule ni autre terme n'est ajouté. 21 entrées du dictionnaire sont écartées par règle (mots grammaticaux en capitales comme PAS, ET, DE, LES ; sigles avec espace ou tiret ; deux sens dans la forme longue ; entrées identiques à leur forme longue), et 152 sont ajoutées mais signalées pour relecture (sigles de deux lettres, mots absents du corpus) dans `reports/lexique_cliniciens_a_verifier.csv`. **L'effet de cet ajout sur la recherche n'a pas été mesuré** ; la configuration évaluée (« aucune ») n'utilise pas le lexique et reste identique (vérifié sur 52 requêtes, mêmes passages et mêmes scores avant et après).

### Essai de bout en bout avec un vrai modèle Qwen (27/11, local)

Chaîne testée : page → API → point d'accès compatible OpenAI (`mlx_lm.server` avec Qwen3.5-9B 4 bits sur cette machine) ; réglages par variables d'environnement `RAG_SFAR_LLM_BASE_URL`, `RAG_SFAR_LLM_MODEL`, `RAG_SFAR_LLM_API_KEY` ; test de connexion réussi (liste des modèles) ; réponse reçue en flux. Une même question tapée en abrégé et sans accents (« ABP pour PTH chez un adulte sans allergie : quelle molecule et quand faire la reinjection ? ») sous les quatre choix :

| Choix | Ce qui s'est passé |
|---|---|
| aucune (configuration évaluée) | le modèle s'abstient : les passages retrouvés ne traitent pas la question |
| lexicale | sigles développés affichés (ABP, PTH) ; réponse citée [S5] tirée de la recommandation d'antibioprophylaxie |
| normalisation par le modèle | le Qwen 9B répond « inchangée » : aucune normalisation, donc même abstention que « aucune » |
| les deux | même résultat que « lexicale » |

À retenir : c'est un exemple, pas une mesure. Il montre que le branchement et les quatre choix fonctionnent avec un modèle Qwen réel, et que **la normalisation dépend du modèle servi** : mesurée utile avec Claude Haiku, elle n'a rien fait ici avec un Qwen de 9 milliards de paramètres. À revérifier avec le modèle de LibreDataHub. Temps jusqu'au premier mot sur ce Mac avec le 9B : 20 à 45 secondes (contexte large) ; ce n'est pas une estimation pour le modèle cible. L'exactitude clinique de la réponse n'a pas été vérifiée.


## Déploiement sur LibreDataHub

L'image Docker est écrite par ailleurs (agent M1) ; voici ce dont l'application a besoin pour servir aussi la page :

- **Code** : le paquet `rag_sfar` installé (`pip install -e .`), Python 3.11 ou plus récent.
- **Index** : le dossier `index/tas_v6` (environ 580 Mo : `bm25.pkl`, `embeddings.npy`, `subword.pkl`, `metadata.sqlite`, `manifest.json`), monté ou copié. Si son chemin n'est pas `index/tas_v6` sous le répertoire de travail : `RAG_SFAR_INDEX_DIR=/chemin/tas_v6`.
- **Modèles locaux, hors ligne** (cache Hugging Face, environ 1 Go chacun avec les fichiers du cache local, moins en ne copiant que les poids) : `intfloat/multilingual-e5-small` (embedder) et `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (reranker). Copier le cache (`HF_HOME`) dans l'image et lancer avec `HF_HUB_OFFLINE=1`. Les deux modèles tournent sur CPU.
- **Mémoire** : prévoir environ 4 Go pour l'application (estimation, non mesurée) (index, n-grammes, embedder, reranker). Le générateur Qwen 27B tourne à part, sur le service LibreDataHub.
- **Commande** : `rag-sfar-serve --host 0.0.0.0 --port 8000`. Dans un conteneur, `0.0.0.0` est nécessaire ; l'exposition réelle est décidée par la plateforme.
- **Variables d'environnement** :
  - `RAG_SFAR_LLM_BASE_URL` : URL de base du point d'accès compatible OpenAI, **terminée par `/v1`** ;
  - `RAG_SFAR_LLM_MODEL` : le nom du modèle **exactement tel que listé** par `GET <base>/models` (bouton « Tester la connexion ») ;
  - `RAG_SFAR_LLM_API_KEY` : la clé, si le service en demande une (secret de la plateforme, jamais dans l'image) ;
  - `RAG_SFAR_LLM_TIMEOUT_SECONDS` : 120 par défaut, à augmenter si le 27B est lent avec un contexte large (jusqu'à 30 000 caractères) ;
  - `RAG_SFAR_DEMO_LOCK_SETTINGS=1` si l'instance est accessible à d'autres personnes ;
  - `RAG_SFAR_DEMO_ROBUSTNESS` : facultatif, `none` par défaut.
- **À vérifier sur place (rien n'a pu être testé depuis cette machine)** : que « Tester la connexion » liste bien le modèle Qwen 27B ; qu'une question d'exemple obtient une réponse citée ; que le serveur accepte `chat_template_kwargs` (avec vLLM, c'est le cas ; sinon, décocher la case et vérifier qu'aucun texte de réflexion n'apparaît dans les réponses) ; le temps de réponse.
