# Serveur MCP RAG-SFAR — déploiement et tests

Date : 2026-11-27. Agent M1, branche `rag-sfar-v2`. Complète `reports/MCP_ARCHITECTURE.md` (conception) : ici, uniquement ce qui a été exécuté et vérifié.

## 1. Verdict

- **Testable : oui.** Un client MCP réel (client officiel du SDK Python `mcp` 2.3.0) se connecte aux deux serveurs, liste les outils et les appelle ; un smoke test réutilisable et 8 tests pytest sans GPU le prouvent.
- **Déployable : oui en local / sur une machine de l'équipe (Python nu)** ; **pas encore prouvé en conteneur** : le `Dockerfile` est écrit mais le démon Docker ne tournait pas sur la machine de développement, l'image n'a donc pas été construite ni testée (§5).
- **Pas prêt pour un service public** : ni authentification, ni quotas, ni journalisation maîtrisée, droits sur les textes non réglés (§8).

## 2. Ce qui a été vérifié, avec preuves

Session réelle sur la machine de développement (Apple Silicon, 16 Go, MPS), index `index/tas_v6`, 2026-11-27 10:45, sous `scripts/with_gpu_lock.sh M1`. Sorties brutes du smoke test reproduites ci-dessous ; serveurs arrêtés ensuite (aucun processus restant vérifié par `pgrep`).

| Vérification | Résultat |
|---|---|
| Démarrage HTTP (lancement → `/healthz` 200, modèles chargés) | **9,9 s** |
| `/healthz` | `{"status":"ok","server":"rag-sfar-mcp","index_id":"table_aware_sota-265docs-36872chunks"}` |
| Profil servi | `PRODUCTION` : retrieval `C10_context_notes` sur `index/tas_v6` (265 documents, 36 872 passages) ; prouvé par test (`test_both_servers_retrieve_with_production_profile`, `test_servers_default_to_production_index`) et par l'`index_id` annoncé |
| Client officiel, HTTP, mode `auto` (découverte 2026-07-28) | 12/12 contrôles OK |
| Client officiel, HTTP, mode `legacy` (poignée de main `initialize`) | 12/12 OK |
| Client officiel, HTTP, version épinglée `2026-07-28` + 8 appels parallèles | 13/13 OK |
| Client officiel, **stdio** (`rag-sfar-mcp` lancé par le client) | 6/6 OK (4 outils ; pas de pollution de stdout par le chargement des modèles) |
| `curl` brut `initialize` (protocole 2025-06-18) | réponse JSON-RPC valide (capacités, instructions) |
| En-tête `Host` étranger (DNS rebinding) | **HTTP 421**, refusé |
| Arguments invalides (`top_k`=500, `query` trop courte, `doc_id` manquant) | erreur MCP `isError` avec message de validation, pas de plantage |
| Journal serveur | accès uvicorn + noms d'arguments rejetés ; **le texte des requêtes n'apparaît pas** (vérifié par recherche dans le journal) |
| Suite de tests | `pytest -q` : 221 passés, 1 ignoré ; test anti-fuite silencieux |

Latence (HTTP, un client) : `sfar_search` 0,32–0,37 s à chaud (1,17 s au premier appel), `search_sfar_recommendations` 0,30 s, `compare_sfar_editions` 0,34 s, `list_sfar_catalog` 2 ms, `get_recommendation_sections` 10–20 ms. Stdio : connexion 8,5 s (chargement des modèles inclus), puis mêmes ordres de grandeur.

Concurrence : 8 appels `sfar_search` simultanés → durée totale 2,5 s, médiane 1,6 s, max 2,5 s. Les recherches sont **sérialisées** (un seul appel à la fois par processus, voulu : le retriever n'est pas audité pour le multithread) : le débit est d'environ 3 recherches/s par processus, la latence croît linéairement avec la file.

Mémoire (RSS du processus, macOS) : 674 Mo au repos, 713 Mo après une passe, 668 Mo après les appels parallèles (pas de croissance). Sur MPS une partie des poids est en mémoire unifiée GPU et peut ne pas être comptée ; en conteneur CPU, compter plutôt 1,5–2 Go (estimation, non mesurée).

Sortie du smoke test (HTTP, mode `auto`) :

```
[PASS] tools/list — ['compare_sfar_editions', 'get_recommendation_sections', 'list_sfar_catalog', 'search_sfar_recommendations', 'sfar_search']
[PASS] tools annotated read-only
[PASS] sfar_search returns passages — 5 passages
[PASS] sfar_search citations complete — doc_id/title/year/status/section/url/excerpt
[PASS] sfar_search size bounded — 12714 chars
[PASS] sfar_search announces index_id — table_aware_sota-265docs-36872chunks
[PASS] sfar_search bad args -> MCP error — Error executing tool sfar_search: 2 validation errors …
[PASS] search_sfar_recommendations — 28547 chars
[PASS] compare_sfar_editions — 7429 chars
[PASS] list_sfar_catalog — 3 rows
[PASS] get_recommendation_sections — doc_id=2016_Intubation-et-extubation-du-patient-en-reanimation-ANREA_58d44e, 2980 chars
[PASS] missing required arg -> MCP error — Error executing tool get_recommendation_sections: 1 validation error …
RESULT: OK (12/12 checks)
```

**Non vérifié** : construction et exécution de l'image Docker (démon arrêté ; pas de démarrage de Docker Desktop pour ne pas prendre 2–4 Go de mémoire aux évaluations en cours) ; taille réelle de l'image ; latence et mémoire sur CPU ; service `api` en conteneur (l'image contient ce dont `rag-sfar-serve` a besoin d'après les imports, sans test) ; un vrai agent LLM (Claude Code) branché sur le serveur — seule la syntaxe `claude mcp add` a été vérifiée ; comportement sous charge soutenue (> 8 appels).

## 3. Démarrer le serveur

### Python nu (solution de repli si les conteneurs ne sont pas disponibles)

```bash
pip install -e '.[neural,mcp]'          # extra « mcp » = SDK officiel, mcp>=2.3,<3 (testé : 2.3.0)
export HF_HUB_OFFLINE=1                  # modèles déjà dans le cache Hugging Face
# HTTP (Streamable HTTP), lecture seule, écoute 127.0.0.1 par défaut
rag-sfar-mcp-http --port 8020            # MCP sur http://127.0.0.1:8020/mcp, santé sur /healthz
# stdio (lancé par le client MCP lui-même)
rag-sfar-mcp
# Web API + chatbot de démonstration (agent C1), générateur OpenAI-compatible
RAG_SFAR_LLM_BASE_URL=https://…/v1 RAG_SFAR_LLM_MODEL=… RAG_SFAR_LLM_API_KEY=… rag-sfar-serve --port 8000
```

Variables d'environnement (les options de ligne de commande priment) :

| Variable | Rôle | Défaut |
|---|---|---|
| `RAG_SFAR_INDEX_DIR` | dossier d'index | `index/tas_v6` (profil `PRODUCTION`, chemin relatif au dossier courant) |
| `RAG_SFAR_MCP_HOST` / `RAG_SFAR_MCP_PORT` | adresse d'écoute du serveur MCP HTTP | `127.0.0.1` / `8765` |
| `RAG_SFAR_MCP_ALLOWED_HOSTS` | en-têtes `Host` acceptés (protection DNS rebinding du SDK quand on écoute hors loopback) | vide (protection automatique sur 127.0.0.1) |
| `RAG_SFAR_LLM_BASE_URL`, `RAG_SFAR_LLM_MODEL`, `RAG_SFAR_LLM_API_KEY` | générateur du chatbot (`rag-sfar-serve` seulement ; le serveur MCP ne génère rien) | Ollama local |

Lancé hors du dépôt, le serveur stdio doit recevoir `RAG_SFAR_INDEX_DIR` en chemin absolu (sinon `index/tas_v6` est cherché dans le dossier courant du client).

### Conteneur (écrit, non construit)

Une seule image, deux services : `RAG_SFAR_SERVICE=mcp` (défaut, port 8020) ou `api` (chatbot, port 8000), ou le premier argument (`mcp` / `api`).

```bash
docker build -t rag-sfar:local .                       # BAKE_MODELS=1 : télécharge ~1 Go de modèles une fois
docker run --rm -p 127.0.0.1:8020:8020 -v "$PWD/index/tas_v6:/data/index:ro" rag-sfar:local
python scripts/mcp_smoke_test.py --url http://127.0.0.1:8020/mcp
# chatbot, même image ; la clé est fournie au lancement, jamais dans l'image ni dans le compose
docker run --rm -p 127.0.0.1:8000:8000 -v "$PWD/index/tas_v6:/data/index:ro" \
  -e RAG_SFAR_LLM_BASE_URL -e RAG_SFAR_LLM_MODEL -e RAG_SFAR_LLM_API_KEY rag-sfar:local api
# ou : docker compose up mcp   /   docker compose --profile api up api
```

Fichiers : `Dockerfile`, `.dockerignore` (contexte = code seulement, ni `.env`, ni `data/`, ni `index/`), `docker-compose.yml` (ports publiés sur 127.0.0.1 seulement), `docker/entrypoint.sh`, `docker/healthcheck.py` (`/healthz` ou `/api/health`).

- **Index** : monté en lecture seule sur `/data/index` (576 Mo), pas copié dans l'image (droits sur les textes non réglés, mises à jour d'index sans reconstruire l'image).
- **Modèles** (`intfloat/multilingual-e5-small`, `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`) : téléchargés une fois au build (`BAKE_MODELS=1`, ~0,95 Go, fichiers safetensors + tokenizers seulement), puis `HF_HUB_OFFLINE=1` dans le conteneur. Sans réseau au build : `--build-arg BAKE_MODELS=0` et monter un cache Hugging Face contenant les deux modèles sur `/models/hf`.
- **Torch CPU** (roue CPU, pas CUDA : ~2,5 Go de moins). Taille d'image estimée, non mesurée : **2,5 à 3 Go** (python-slim ~0,15 + torch CPU ~0,7 + dépendances ~0,5 + modèles ~0,95). Mémoire : RSS mesuré 0,67–0,71 Go sur macOS/MPS (§2), à remesurer en CPU ; prévoir **3 Go** de limite pour le service MCP, **4 Go** pour le chatbot (`mem_limit` du compose). Le CPU sera plus lent que le GPU Apple pour le reranking (non mesuré).
- Utilisateur non root, `HEALTHCHECK` intégré (démarrage toléré 120 s).

## 4. Tester

```bash
python scripts/mcp_smoke_test.py --url http://127.0.0.1:8020/mcp [--mode legacy|2026-07-28] [--concurrency 8] [--json]
python scripts/mcp_smoke_test.py --stdio "rag-sfar-mcp"
python -m pytest -q tests/test_mcp_smoke.py tests/test_mcp_http.py     # sans GPU, index jouet
```

Le smoke test vérifie : négociation du protocole, liste des outils, annotation lecture seule, un appel réaliste de chaque outil, champs de citation (`doc_id`, titre, année, statut d'édition, section, URL, extrait verbatim), taille bornée (< 60 000 caractères par résultat), erreurs MCP (`isError`) pour des arguments invalides ou manquants, et en option N appels parallèles. Code de sortie 0 si tout passe.

`tests/test_mcp_smoke.py` (sans GPU, index jouet de deux éditions fictives) : smoke test contre le serveur HTTP (modes `auto`, `legacy`, `2026-07-28`, 3 appels parallèles) et contre le serveur stdio lancé en sous-processus par le client stdio du SDK (`auto`, `legacy`) ; les deux serveurs passent par le profil `PRODUCTION` (configuration `C10_context_notes`, espionnée sur chaque chemin de recherche) ; les deux points d'entrée chargent `index/tas_v6` par défaut et `RAG_SFAR_INDEX_DIR` sinon ; hôte et port HTTP lus dans l'environnement, 127.0.0.1 par défaut.

## 6. Brancher un client

Claude Code (syntaxe vérifiée avec `claude mcp add --help` ; configuration de l'utilisateur non modifiée) :

```bash
# HTTP (serveur déjà lancé)
claude mcp add --transport http sfar http://127.0.0.1:8020/mcp
# stdio (Claude Code lance le serveur)
claude mcp add sfar-stdio -e HF_HUB_OFFLINE=1 -e RAG_SFAR_INDEX_DIR=/chemin/absolu/index/tas_v6 \
  -- /chemin/absolu/.venv/bin/rag-sfar-mcp
```

JSON générique (`mcpServers`, format Claude Desktop / Cursor / `.mcp.json`) :

```json
{
  "mcpServers": {
    "sfar": { "type": "http", "url": "http://127.0.0.1:8020/mcp" },
    "sfar-stdio": {
      "command": "/chemin/absolu/.venv/bin/rag-sfar-mcp",
      "env": { "HF_HUB_OFFLINE": "1", "RAG_SFAR_INDEX_DIR": "/chemin/absolu/index/tas_v6" }
    }
  }
}
```

Client Python : `async with mcp.Client("http://127.0.0.1:8020/mcp") as c: await c.call_tool("sfar_search", {"query": "…"})`.

### Exemple : une question d'agent traitée par les outils

Question posée à l'agent : « Conduite à tenir devant une intubation difficile imprévue au bloc opératoire ? » (exemple générique, hors jeux d'évaluation).

1. L'agent appelle `sfar_search` `{"query": "conduite à tenir devant une intubation difficile imprévue au bloc opératoire", "top_k": 5}`.
2. Il reçoit 5 extraits structurés (12,7 k caractères), chacun avec `doc_id`, titre, année, `status` (`en_vigueur`/`remplacee`), section, GRADE, URL sfar.org et extrait verbatim. Observé : S1 = `2016_Intubation-et-extubation-du-patient-en-reanimation-ANREA_58d44e` (2016, en vigueur), section « Introduction ».
3. Pour lire un document en entier, il appelle `get_recommendation_sections` `{"doc_id": "<doc_id>", "limit": 3}` ; `list_sfar_catalog` `{"keyword": "intubation"}` renvoie 3 documents en vigueur ; lors de la session stdio, le document lu était `2025_2025_RFE-Intubation-adulte-hors-bloc-hors-rea-_f68924`.
4. L'agent rédige sa réponse en citant `[S1]…` et le `doc_id`, signale les éditions remplacées et s'abstient si aucun extrait ne traite la question (consigne `usage_notice` renvoyée avec chaque résultat).

Limite observée : pour cette formulation « au bloc », le premier extrait vient d'une recommandation de réanimation (introduction) ; le serveur renvoie des extraits, la pertinence clinique reste à juger par l'agent et l'utilisateur.

## 7. LibreDataHub : à vérifier sur place

Les contraintes de la plateforme ne sont pas connues ; rien n'est supposé.

1. **Images** : la plateforme accepte-t-elle une image arbitraire (registre privé à fournir) ou faut-il construire sur place ? Sinon, repli en Python nu (§3), avec un venv `pip install -e '.[neural,mcp]'`.
2. **Réseau sortant** : disponible au build ? Sinon `BAKE_MODELS=0` et apporter le cache Hugging Face des deux modèles (~1 Go) avec le reste.
3. **Index** : comment le dossier `index/tas_v6` (576 Mo, git-ignoré) arrive-t-il sur la machine (copie, volume partagé) ? Le reconstruire sur place (`rag-sfar-index`) n'est pas équivalent tant que le build n'a pas été comparé.
4. **Mémoire** : au moins 3 Go pour le serveur MCP seul, 4 Go pour le chatbot ; GPU non requis (CPU plus lent, à mesurer).
5. **Ports** : quels ports peuvent être exposés, et à qui ? Le serveur n'a pas d'authentification : il ne doit être joignable que par l'équipe (proxy de la plateforme, réseau interne).
6. **Générateur** : URL, nom du modèle Qwen 27B et clé de l'API OpenAI-compatible, fournis par variables d'environnement ou secret de la plateforme au lancement.
7. **Hôte HTTP** : si un proxy présente un autre en-tête `Host`, l'ajouter à `RAG_SFAR_MCP_ALLOWED_HOSTS`, sinon les requêtes sont refusées (421/403) par la protection DNS rebinding.

## 8. Manquant pour un service public (vérifié dans le code)

| Point | Existe | Manque | Effort |
|---|---|---|---|
| Authentification | rien | jetons ou OAuth (le SDK fournit le support OAuth côté serveur) ou proxy authentifiant | 1–2 j |
| Quotas / limitation de débit | plafonds de paramètres (`top_k` ≤ 20, requête ≤ 1000 caractères, extrait ≤ 6000) | quotas par IP/clé (proxy ou middleware) | 0,5–1 j |
| Taille des requêtes | validation pydantic des arguments | pas de limite de taille du corps HTTP côté serveur (à poser au proxy) | 0,5 j |
| Journalisation | logs d'accès uvicorn (méthode, chemin, statut) ; le texte des requêtes n'est pas journalisé par notre code | politique écrite, troncature IP, pas de journal applicatif structuré ni de métriques | 1 j |
| Concurrence | un seul appel de recherche à la fois par processus (`CapacityLimiter(1)`), les appels suivants attendent | montée en charge par réplicas ; file d'attente bornée et délai d'expiration | 1 j |
| Démarrage | 9,9 s ; `/healthz` ne répond qu'une fois index et modèles chargés (uvicorn démarre après le chargement) | rien de bloquant | — |
| Serveur stdio | fonctionne avec le client officiel (`auto` et `legacy`) | pas de validation d'arguments (erreur Python renvoyée comme `isError`), `top_k` ignoré par la recherche, aucun résultat → texte vide pour `compare_sfar_editions` | 0,5 j |
| Droits sur les textes SFAR | rien dans le code | autorisation de diffusion d'extraits verbatim par document, champ `license`/attribution (questions ouvertes de `MCP_ARCHITECTURE.md` §6) | décision SFAR |
| Exposition | écoute 127.0.0.1 par défaut, protection DNS rebinding | TLS, nom de domaine, page officielle anti-usurpation | 1–2 j |
