"""FastAPI Clinical Demonstrator UI + OpenAI-compatible `/v1/chat/completions` API.

Allows:
1. Physicians & jury to interactively query SFAR guidelines with full citation & score transparency.
2. Sibling datathon teams (`plateforme-evaluation`, `evaluation-cas-cliniques`) to benchmark
   our RAG seamlessly via standard OpenAI SDK (`base_url="http://localhost:8000/v1"`).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from rag_sfar.config import RetrievalConfig, Settings
from rag_sfar.generation.client import SfarRagEngine
from rag_sfar.retrieval.embedder import build_embedder
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.reranker import build_reranker
from rag_sfar.retrieval.vector_store import LocalVectorStore


class SearchRequest(BaseModel):
    query: str
    top_k: int = 8
    latest_only: bool | None = None
    use_reranker: bool = True
    use_hybrid: bool = True
    use_lexicon: bool = True
    expand_callouts: bool = True
    domains: list[str] | None = None


class QueryRequest(SearchRequest):
    mode: str = "clinical_detailed"
    retrieval_only: bool = False


class ChatMessage(BaseModel):
    role: str
    content: str


class OpenAIChatRequest(BaseModel):
    model: str = "rag-sfar-sota"
    messages: list[ChatMessage]
    temperature: float | None = 0.0
    max_tokens: int | None = None


DEMO_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>RAG-SFAR — Assistant Clinique & Explorateur RFE</title>
  <style>
    :root {
      --bg: #0b1220; --card: #131d31; --card2: #192640; --border: #263656;
      --text: #e6edf8; --muted: #93a4c3; --accent: #38bdf8; --ok: #22c55e;
      --warn: #f59e0b; --danger: #ef4444; --pill: #1e2e4f;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }
    header { background: linear-gradient(135deg, #0f1b33, #13294b); border-bottom: 1px solid var(--border); padding: 18px 28px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand h1 { margin: 0; font-size: 1.25rem; letter-spacing: 0.2px; }
    .brand span { font-size: 0.82rem; color: var(--accent); background: rgba(56,189,248,.12); border: 1px solid rgba(56,189,248,.35); padding: 3px 10px; border-radius: 999px; }
    .stats { font-size: 0.85rem; color: var(--muted); }
    main { max-width: 1260px; margin: 22px auto; padding: 0 20px 60px; }
    .search-card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 20px; }
    .query-row { display: flex; gap: 10px; }
    input[type="text"] { flex: 1; background: #0d1629; border: 1px solid var(--border); color: var(--text); border-radius: 10px; padding: 13px 16px; font-size: 1rem; outline: none; }
    input[type="text"]:focus { border-color: var(--accent); }
    button { background: var(--accent); color: #061321; border: none; border-radius: 10px; padding: 0 22px; font-weight: 700; font-size: 0.95rem; cursor: pointer; }
    button.secondary { background: var(--pill); color: var(--text); border: 1px solid var(--border); font-weight: 600; padding: 8px 14px; font-size: 0.84rem; }
    button:hover { opacity: 0.92; }
    .controls { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 14px; align-items: center; font-size: 0.86rem; color: var(--muted); }
    .controls label { display: flex; align-items: center; gap: 6px; cursor: pointer; }
    .controls select { background: #0d1629; color: var(--text); border: 1px solid var(--border); border-radius: 7px; padding: 5px 10px; }
    .examples { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
    .ex-pill { background: var(--pill); border: 1px solid var(--border); color: #cde2ff; border-radius: 999px; padding: 5px 12px; font-size: 0.8rem; cursor: pointer; }
    .ex-pill:hover { border-color: var(--accent); color: #fff; }
    .grid { display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 18px; margin-top: 20px; }
    @media (max-width: 960px) { .grid { grid-template-columns: 1fr; } }
    .panel { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; }
    .panel h2 { margin: 0 0 12px; font-size: 1rem; color: var(--accent); display: flex; justify-content: space-between; align-items: center; }
    .answer-box { white-space: pre-wrap; font-size: 0.96rem; background: #0d1629; border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
    .meta-strip { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .badge { font-size: 0.74rem; padding: 3px 9px; border-radius: 999px; font-weight: 600; background: var(--pill); color: var(--text); border: 1px solid var(--border); }
    .badge.ok { background: rgba(34,197,94,.14); color: #86efac; border-color: rgba(34,197,94,.4); }
    .badge.warn { background: rgba(245,158,11,.15); color: #fde68a; border-color: rgba(245,158,11,.4); }
    .badge.danger { background: rgba(239,68,68,.15); color: #fca5a5; border-color: rgba(239,68,68,.4); }
    .badge.accent { background: rgba(56,189,248,.14); color: #7dd3fc; border-color: rgba(56,189,248,.35); }
    .chunk-card { background: var(--card2); border: 1px solid var(--border); border-radius: 10px; padding: 13px; margin-bottom: 12px; }
    .chunk-head { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
    .chunk-title { font-weight: 700; font-size: 0.9rem; color: #fff; }
    .chunk-sec { font-size: 0.78rem; color: var(--muted); margin-bottom: 8px; }
    .chunk-body { font-size: 0.84rem; white-space: pre-wrap; color: #d7e3f7; max-height: 210px; overflow-y: auto; background: #0d1629; padding: 10px; border-radius: 8px; border: 1px solid #20304f; }
    .scores { font-size: 0.74rem; color: var(--muted); margin-top: 8px; display: flex; gap: 10px; flex-wrap: wrap; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>RAG-SFAR</h1>
      <span>Datathon SFAR × InterHop 2026</span>
    </div>
    <div class="stats" id="statsBar">Chargement de l'index…</div>
  </header>
  <main>
    <div class="search-card">
      <div class="query-row">
        <input id="queryInput" type="text" placeholder="Posez une question clinique SFAR (ex : PTH voie antérieure allergie bêtalactamines, arrêt AOD avant neurochirurgie…)" />
        <button onclick="runQuery(false)">Rechercher + Répondre</button>
        <button class="secondary" onclick="runQuery(true)">Retrieval seul</button>
      </div>
      <div class="controls">
        <label><input type="checkbox" id="chkHybrid" checked /> Hybride (BM25+ & Dense)</label>
        <label><input type="checkbox" id="chkRerank" checked /> Reranker Cross-Encoder</label>
        <label><input type="checkbox" id="chkLexicon" checked /> Lexique médical (PTH, AOD, IIA…)</label>
        <label><input type="checkbox" id="chkCallouts" checked /> Expansion encadrés allergie / notes</label>
        <label>Éditions :
          <select id="selTemporal">
            <option value="auto" selected>Auto (En vigueur par défaut, Diff si comparatif)</option>
            <option value="latest">En vigueur uniquement</option>
            <option value="all">Toutes éditions (2000–2026)</option>
          </select>
        </label>
        <label>Mode :
          <select id="selMode">
            <option value="clinical_detailed" selected>Clinique détaillé + Citations</option>
            <option value="benchmark_open">Benchmark concis (1 molécule)</option>
          </select>
        </label>
      </div>
      <div class="examples">
        <span class="ex-pill" onclick="setExample('Quelle antibioprophylaxie pour une PTH par voie antérieure chez un patient allergique aux bêtalactamines ?')">1. PTH voie ant. + allergie (→ Vanco/Teico 2026)</span>
        <span class="ex-pill" onclick="setExample('Quelle est la recommandation d\\'antibioprophylaxie pour une plaie cranio-cérébrale chez un patient allergique aux pénicillines ?')">2. Plaie cranio + allergie (→ Bactrim 2026)</span>
        <span class="ex-pill" onclick="setExample('Quel est le délai d\\'arrêt des AOD avant une neurochirurgie intracrânienne ou procédure neuraxiale programmée ?')">3. Arrêt AOD neurochirurgie 2026 (→ J-5)</span>
        <span class="ex-pill" onclick="setExample('Patient sous anticoagulant avec hémorragie intracrânienne en urgence : faut-il attendre les tests biologiques pour réverser ?')">4. Hémorragie urgence 2024 (→ CCP sans attendre)</span>
        <span class="ex-pill" onclick="setExample('Antibiothérapie probabiliste d\\'une infection intra-abdominale communautaire sans sepsis ni choc septique chez l\\'adulte (R1.2.1) ?')">5. IIA communautaire 2026 (→ C3G + Métro)</span>
        <span class="ex-pill" onclick="setExample('Qu\\'est-ce qui a changé dans les recommandations d\\'antibioprophylaxie entre 2018 et 2026 ?')">6. Diff temporel 2018 vs 2026</span>
      </div>
    </div>

    <div class="grid">
      <div class="panel">
        <h2>Réponse Clinique Sourcée <span id="latencyBadge" class="badge accent">—</span></h2>
        <div class="meta-strip" id="analysisStrip"></div>
        <div class="meta-strip" id="verifyStrip"></div>
        <div class="answer-box" id="answerBox">Entrez une question clinique ou cliquez sur un exemple ci-dessus.</div>
      </div>
      <div class="panel">
        <h2>Passages SFAR Retrouvés & Transparence Retrieval <span id="countBadge" class="badge">0</span></h2>
        <div id="chunksContainer"></div>
      </div>
    </div>
  </main>
  <script>
    async function loadHealth() {
      try {
        const res = await fetch('/api/health');
        const d = await res.json();
        document.getElementById('statsBar').textContent =
          `${d.num_documents} docs SFAR (${d.num_chunks} chunks) • Embedder: ${d.embedding_model} • Reranker: ${d.reranker_model} • LLM: ${d.llm_model || 'retrieval_only'}`;
      } catch (e) {
        document.getElementById('statsBar').textContent = 'Serveur connecté';
      }
    }
    function setExample(q) {
      document.getElementById('queryInput').value = q;
      runQuery(false);
    }
    function renderRetrieval(data) {
      const qa = data.query_analysis || {};
      const aBadges = [];
      aBadges.push(`<span class="badge accent">Mode temporel: ${qa.temporal_mode}</span>`);
      if (qa.population && qa.population !== 'non_specifie') aBadges.push(`<span class="badge">Population: ${qa.population}</span>`);
      if (qa.setting && qa.setting !== 'non_specifie') aBadges.push(`<span class="badge">Contexte: ${qa.setting}</span>`);
      if (qa.modifiers?.length) aBadges.push(`<span class="badge">Modifieurs: ${qa.modifiers.join(', ')}</span>`);
      if (qa.acronyms_expanded && Object.keys(qa.acronyms_expanded).length) {
        aBadges.push(`<span class="badge ok">Acronymes: ${Object.keys(qa.acronyms_expanded).join(', ')}</span>`);
      }
      document.getElementById('analysisStrip').innerHTML = aBadges.join('');

      const rLat = data.latency_ms?.total_retrieval_ms || 0;
      document.getElementById('latencyBadge').textContent = `Retrieval: ${rLat.toFixed(0)} ms • Génération…`;

      const chunks = data.retrieved_chunks || [];
      document.getElementById('countBadge').textContent = `${chunks.length} sources`;
      document.getElementById('chunksContainer').innerHTML = chunks.map((rc, i) => {
        const c = rc.chunk;
        const edBadge = c.is_latest_edition
          ? `<span class="badge ok">EN VIGUEUR (${c.effective_year || '?'})</span>`
          : `<span class="badge danger">ANTÉRIEURE (${c.effective_year || '?'})</span>`;
        const expBadge = rc.is_expanded_context
          ? `<span class="badge accent">+ ${rc.expansion_reason}</span>` : '';
        const gradeBadge = c.grade_levels?.length
          ? `<span class="badge warn">${c.grade_levels.slice(0,2).join(' • ')}</span>` : '';
        return `
          <div class="chunk-card">
            <div class="chunk-head">
              <div class="chunk-title">[S${i+1}] ${c.doc_title}</div>
              <div>${edBadge} ${expBadge} ${gradeBadge}</div>
            </div>
            <div class="chunk-sec">${c.doc_type} • ${c.chunk_type} • ${c.section_path || 'Général'}</div>
            <div class="chunk-body">${c.text.replace(/</g,'&lt;')}</div>
            <div class="scores">
              <span>Score: <b>${rc.final_score.toFixed(4)}</b></span>
              ${rc.bm25_rank ? `<span>BM25 #${rc.bm25_rank} (${rc.bm25_score.toFixed(2)})</span>` : ''}
              ${rc.dense_rank ? `<span>Dense #${rc.dense_rank} (${rc.dense_score.toFixed(3)})</span>` : ''}
              ${rc.rerank_score !== null && rc.rerank_score !== undefined ? `<span>Cross-Encoder: ${rc.rerank_score.toFixed(3)}</span>` : ''}
              ${rc.metadata_boost ? `<span>Meta boost: ${rc.metadata_boost > 0 ? '+' : ''}${rc.metadata_boost}</span>` : ''}
            </div>
          </div>`;
      }).join('');
    }
    function renderVerification(data) {
      const lat = data.latency_ms?.total_ms || data.latency_ms?.total_retrieval_ms || 0;
      const rLat = data.latency_ms?.total_retrieval_ms || 0;
      document.getElementById('latencyBadge').textContent = `Retrieval ${rLat.toFixed(0)} ms • Total ${(lat/1000).toFixed(1)} s`;
      const v = data.verification || {};
      const vBadges = [];
      if (data.model_used && data.model_used !== 'retrieval_only') {
        const gCls = (v.grounding_score >= 0.85) ? 'ok' : (v.grounding_score >= 0.5 ? 'warn' : 'danger');
        vBadges.push(`<span class="badge ${gCls}">Grounding: ${Math.round((v.grounding_score||0)*100)}%</span>`);
        if (data.extra?.self_corrected) {
          vBadges.push('<span class="badge ok">Auto-corrigé Self-MedRAG ✓</span>');
        }
        if (v.ungrounded_molecules?.length) {
          vBadges.push(`<span class="badge danger">Alerte molécule non sourcée: ${v.ungrounded_molecules.join(', ')}</span>`);
        }
        (v.warnings || []).forEach(w => vBadges.push(`<span class="badge warn">${w}</span>`));
      }
      document.getElementById('verifyStrip').innerHTML = vBadges.join('');
    }
    async function runQuery(retrievalOnly) {
      const q = document.getElementById('queryInput').value.trim();
      if (!q) return;
      document.getElementById('answerBox').textContent = 'Recherche Tri-Canal + CRAG dans les 264 recommandations SFAR…';
      document.getElementById('chunksContainer').innerHTML = '';
      document.getElementById('verifyStrip').innerHTML = '';
      const tempVal = document.getElementById('selTemporal').value;
      const latest_only = tempVal === 'auto' ? null : (tempVal === 'latest');
      const payload = {
        query: q,
        mode: document.getElementById('selMode').value,
        retrieval_only: retrievalOnly,
        use_hybrid: document.getElementById('chkHybrid').checked,
        use_reranker: document.getElementById('chkRerank').checked,
        use_lexicon: document.getElementById('chkLexicon').checked,
        expand_callouts: document.getElementById('chkCallouts').checked,
        latest_only: latest_only,
        top_k: 8
      };
      try {
        const res = await fetch('/api/query/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        let startedTokens = false;
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n\n');
          buf = lines.pop();
          for (const block of lines) {
            const line = block.trim();
            if (!line.startsWith('data:')) continue;
            const ev = JSON.parse(line.slice(5).trim());
            if (ev.type === 'retrieval') {
              renderRetrieval(ev);
              document.getElementById('answerBox').textContent = 'Sources trouvées ! Génération en direct…';
            } else if (ev.type === 'token') {
              if (!startedTokens) {
                document.getElementById('answerBox').textContent = '';
                startedTokens = true;
              }
              document.getElementById('answerBox').textContent += ev.text;
            } else if (ev.type === 'done') {
              if (ev.extra?.self_corrected && ev.answer) {
                document.getElementById('answerBox').textContent = ev.answer;
              }
              renderVerification(ev);
            }
          }
        }
      } catch (err) {
        document.getElementById('answerBox').textContent = 'Erreur: ' + err;
      }
    }
    document.getElementById('queryInput').addEventListener('keydown', e => { if (e.key === 'Enter') runQuery(false); });
    loadHealth();
  </script>
</body>
</html>
"""


def create_app(
    index_dir: Path | None = None,
    settings: Settings | None = None,
    enable_llm: bool = True,
    mlx_model_path: str | None = None,
) -> FastAPI:
    """Create configured FastAPI application."""
    cfg_settings = settings or Settings()
    idx_path = index_dir or cfg_settings.index_dir

    store = LocalVectorStore.load(idx_path)
    manifest = store.manifest
    emb_provider = manifest.get("embedding_provider", cfg_settings.embedding_provider)
    emb_model = manifest.get("embedding_model", cfg_settings.embedding_model)
    # CRITICAL Apple Silicon optimization: when running a local MLX LLM on Metal GPU,
    # pin PyTorch embedder + reranker to CPU so PyTorch MPS never contends with MLX for GPU RAM!
    torch_device = "cpu" if mlx_model_path else None

    embedder = None
    if store.embeddings is not None:
        embedder = build_embedder(
            provider=emb_provider,
            model_name=emb_model,
            base_url=cfg_settings.embedding_base_url,
            api_key=cfg_settings.embedding_api_key,
            index_dir=idx_path,
            device=torch_device,
        )

    reranker = None
    if cfg_settings.reranker_provider != "none":
        try:
            reranker = build_reranker(
                provider=cfg_settings.reranker_provider,
                model_name=cfg_settings.reranker_model,
                device=torch_device,
            )
        except Exception:
            reranker = None

    retriever = SfarRagRetriever(store=store, embedder=embedder, reranker=reranker)
    if mlx_model_path:
        from rag_sfar.generation.client import LocalMlxLLM

        llm = LocalMlxLLM(
            model_path=mlx_model_path,
            model_label=Path(mlx_model_path).name,
            temperature=cfg_settings.llm_temperature,
            max_tokens=min(cfg_settings.llm_max_tokens, 420),
        )
        engine = SfarRagEngine(retriever=retriever, llm=llm)
    else:
        engine = SfarRagEngine.from_settings(
            settings=cfg_settings, retriever=retriever, enable_llm=enable_llm
        )

    app = FastAPI(title="RAG-SFAR Clinical Engine", version="1.0.0")

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return DEMO_HTML

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "index_dir": str(idx_path),
            "num_documents": len(store.documents),
            "num_chunks": len(store.chunks),
            "embedding_model": embedder.model_name if embedder else "bm25_only",
            "reranker_model": reranker.model_name if reranker else "none",
            "llm_model": engine.llm.model if engine.llm else None,
        }

    @app.get("/api/catalog")
    def catalog(latest_only: bool = False) -> dict[str, Any]:
        docs = [
            d.model_dump()
            for d in store.documents
            if (not latest_only or d.is_latest_edition)
        ]
        return {"count": len(docs), "documents": docs}

    @app.post("/api/search")
    def api_search(req: SearchRequest) -> dict[str, Any]:
        rcfg = RetrievalConfig(
            use_bm25=True,
            use_dense=req.use_hybrid and (embedder is not None),
            use_medical_lexicon=req.use_lexicon,
            use_reranker=req.use_reranker and (reranker is not None),
            expand_section_callouts=req.expand_callouts,
            expand_neighbors=req.expand_callouts,
            final_top_k=req.top_k,
        )
        retrieved, analysis, timings = retriever.retrieve(
            query=req.query,
            config=rcfg,
            override_latest_only=req.latest_only,
            override_domains=req.domains,
        )
        return {
            "query_analysis": analysis.model_dump(),
            "latency_ms": timings,
            "retrieved_chunks": [r.model_dump() for r in retrieved],
        }

    @app.post("/api/query/stream")
    def api_query_stream(req: QueryRequest) -> StreamingResponse:
        rcfg = RetrievalConfig(
            use_bm25=True,
            use_dense=req.use_hybrid and (embedder is not None),
            use_medical_lexicon=req.use_lexicon,
            use_reranker=req.use_reranker and (reranker is not None),
            expand_section_callouts=req.expand_callouts,
            expand_neighbors=req.expand_callouts,
            final_top_k=req.top_k,
        )

        def event_gen():
            try:
                for ev in engine.stream_answer(
                    query=req.query,
                    mode=req.mode,
                    config=rcfg,
                    override_latest_only=req.latest_only,
                    override_domains=req.domains,
                    retrieval_only=req.retrieval_only,
                ):
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            except Exception as exc:
                err_ev = {
                    "type": "token",
                    "text": f"\n[Erreur streaming: {type(exc).__name__}: {exc}]",
                }
                yield f"data: {json.dumps(err_ev, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'answer': '', 'latency_ms': {}, 'verification': {}, 'extra': {}})}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @app.post("/api/query")
    def api_query(req: QueryRequest) -> dict[str, Any]:
        rcfg = RetrievalConfig(
            use_bm25=True,
            use_dense=req.use_hybrid and (embedder is not None),
            use_medical_lexicon=req.use_lexicon,
            use_reranker=req.use_reranker and (reranker is not None),
            expand_section_callouts=req.expand_callouts,
            expand_neighbors=req.expand_callouts,
            final_top_k=req.top_k,
        )
        try:
            resp = engine.answer(
                query=req.query,
                mode=req.mode,
                config=rcfg,
                override_latest_only=req.latest_only,
                override_domains=req.domains,
                retrieval_only=req.retrieval_only,
            )
            return resp.model_dump()
        except Exception as exc:
            # Graceful fallback to retrieval-only if local LLM server is offline
            resp = engine.answer(
                query=req.query,
                mode=req.mode,
                config=rcfg,
                override_latest_only=req.latest_only,
                override_domains=req.domains,
                retrieval_only=True,
            )
            resp.answer = (
                f"[Serveur LLM indisponible ({type(exc).__name__}: {exc}) — mode retrieval actif]\n\n"
                + resp.answer
            )
            return resp.model_dump()

    # --- OpenAI-Compatible API for seamless Datathon Evaluation Platform integration ---
    @app.get("/v1/models")
    def openai_models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {"id": "rag-sfar-sota", "object": "model", "owned_by": "sfar-datathon"},
                {"id": "rag-sfar-benchmark-open", "object": "model", "owned_by": "sfar-datathon"},
                {"id": "rag-sfar-benchmark-mcq", "object": "model", "owned_by": "sfar-datathon"},
            ],
        }

    @app.post("/v1/chat/completions")
    def openai_chat(req: OpenAIChatRequest) -> dict[str, Any]:
        user_msgs = [m.content for m in req.messages if m.role == "user"]
        if not user_msgs:
            raise HTTPException(status_code=400, detail="No user message provided.")
        query = user_msgs[-1]
        mode = "clinical_detailed"
        if "benchmark-open" in req.model:
            mode = "benchmark_open"
        elif "benchmark-mcq" in req.model:
            mode = "benchmark_mcq"
        resp = engine.answer(query=query, mode=mode)
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": resp.answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": resp.token_usage.get("prompt_tokens", 0),
                "completion_tokens": resp.token_usage.get("completion_tokens", 0),
                "total_tokens": resp.token_usage.get("total_tokens", 0),
            },
            "sfar_citations": [c.model_dump() for c in resp.citations],
            "sfar_verification": resp.verification.model_dump(),
        }

    return app
