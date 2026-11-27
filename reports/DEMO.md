# Démonstrateur RAG-SFAR : guide d'utilisation

Page web unique servie par l'application FastAPI existante (`src/rag_sfar/interfaces/api.py`, page dans `src/rag_sfar/interfaces/demo_page.py`). HTML, CSS et JavaScript simples, aucune ressource chargée depuis Internet : la démonstration fonctionne hors ligne.

Ce que le jury teste est le système évalué : la page passe par `/api/query/stream`, qui construit le prompt avec le profil `PRODUCTION` (recherche `C10_context_notes` sur `index/tas_v6`, contexte structuré, prompt `clinical_concise`, QCM routés vers leur prompt). Le test `tests/test_generation_b3.py::test_api_prompt_identical_to_replay_prompt` vérifie que ce prompt est celui de l'évaluation. `tests/test_demo_chatbot.py` vérifie que les réglages du générateur changent le point d'accès et le modèle, mais pas le prompt.

## Démarrer (machine locale)

```bash
cd /Users/tim/Me/SFAR-datathon
HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-serve --host 127.0.0.1 --port 8010
```

Ouvrir ensuite http://127.0.0.1:8010/. Le démarrage prend environ 30 à 60 s (chargement de l'index, de l'embedder et du reranker), pour environ 2 à 3 Go de mémoire sans générateur. L'index servi par défaut est celui du profil (`index/tas_v6`). Le `--host 127.0.0.1` est obligatoire en local, car la valeur par défaut des réglages est `0.0.0.0`.

### Brancher un générateur

Trois possibilités :

1. **Depuis la page** : ouvrir « Réglages du générateur », saisir l'URL de base (terminée par `/v1`) et éventuellement la clé, cliquer sur « Tester la connexion » (la page liste alors les modèles servis), choisir le modèle, puis cliquer sur « Appliquer ». Le réglage vaut pour les questions suivantes.
2. **Au démarrage, par variables d'environnement** (aucun clic nécessaire) :
   `RAG_SFAR_LLM_BASE_URL=https://…/v1 RAG_SFAR_LLM_MODEL=<nom listé> RAG_SFAR_LLM_API_KEY=<clé> HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-serve --host 127.0.0.1 --port 8010`
3. **Modèle local Qwen3.5-9B MLX** (le générateur de substitution de l'évaluation). Il demande environ 11 Go au pic : à lancer seulement quand aucune autre tâche n'utilise le GPU. Sur une machine de 16 Go, il ne peut pas tourner en même temps que des évaluations.
   - En processus : `HF_HUB_OFFLINE=1 .venv/bin/rag-sfar-serve --host 127.0.0.1 --port 8010 --mlx-model /Users/tim/.cache/rag_sfar_models/Qwen3.5-9B-MLX-4bit-nothink`. Le panneau de réglages est alors en lecture seule.
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
- **lexicale** : la recherche active en plus l'index de n-grammes de caractères et le lexique médical (`use_subword`, `use_medical_lexicon`). La recherche tolère ainsi mieux les fautes de frappe et les sigles. Aucun appel au modèle.
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

## Déploiement sur LibreDataHub

L'image Docker est écrite par ailleurs (agent M1) ; voici ce dont l'application a besoin pour servir aussi la page :

- **Code** : le paquet `rag_sfar` installé (`pip install -e .`), Python 3.11 ou plus récent.
- **Index** : le dossier `index/tas_v6` (environ 580 Mo : `bm25.pkl`, `embeddings.npy`, `subword.pkl`, `metadata.sqlite`, `manifest.json`), monté ou copié. Si son chemin n'est pas `index/tas_v6` sous le répertoire de travail : `RAG_SFAR_INDEX_DIR=/chemin/tas_v6`.
- **Modèles locaux, hors ligne** (cache Hugging Face, environ 1 Go chacun avec les fichiers du cache local, moins en ne copiant que les poids) : `intfloat/multilingual-e5-small` (embedder) et `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (reranker). Copier le cache (`HF_HOME`) dans l'image et lancer avec `HF_HUB_OFFLINE=1`. Les deux modèles tournent sur CPU.
- **Mémoire** : prévoir environ 3 à 4 Go pour l'application (index, n-grammes, embedder, reranker). Le générateur Qwen 27B tourne à part, sur le service LibreDataHub.
- **Commande** : `rag-sfar-serve --host 0.0.0.0 --port 8000`. Dans un conteneur, `0.0.0.0` est nécessaire ; l'exposition réelle est décidée par la plateforme.
- **Variables d'environnement** :
  - `RAG_SFAR_LLM_BASE_URL` : URL de base du point d'accès compatible OpenAI, **terminée par `/v1`** ;
  - `RAG_SFAR_LLM_MODEL` : le nom du modèle **exactement tel que listé** par `GET <base>/models` (bouton « Tester la connexion ») ;
  - `RAG_SFAR_LLM_API_KEY` : la clé, si le service en demande une (secret de la plateforme, jamais dans l'image) ;
  - `RAG_SFAR_LLM_TIMEOUT_SECONDS` : 120 par défaut, à augmenter si le 27B est lent avec un contexte large (jusqu'à 30 000 caractères) ;
  - `RAG_SFAR_DEMO_LOCK_SETTINGS=1` si l'instance est accessible à d'autres personnes ;
  - `RAG_SFAR_DEMO_ROBUSTNESS` : facultatif, `none` par défaut.
- **À vérifier sur place (rien n'a pu être testé depuis cette machine)** : que « Tester la connexion » liste bien le modèle Qwen 27B ; qu'une question d'exemple obtient une réponse citée ; que le serveur accepte `chat_template_kwargs` (avec vLLM, c'est le cas ; sinon, décocher la case et vérifier qu'aucun texte de réflexion n'apparaît dans les réponses) ; le temps de réponse.
