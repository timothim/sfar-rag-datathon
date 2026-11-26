#!/usr/bin/env bash
# ==============================================================================
# One-command LibreDataHub GPU Setup & Upgrade Script (Day 1 — Nov 26, 2026)
# Upgrades embeddings to BAAI/bge-m3 & reranker to BAAI/bge-reranker-v2-m3 on GPU,
# builds all 3 ablation indexes, runs C0->C8 ablation, and starts the Web UI + API!
# ==============================================================================
set -euo pipefail

echo "=== 1. Installing RAG-SFAR + neural dependencies ==="
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[neural,dev]"

echo "=== 2. Running unit & integration test suite ==="
pytest -q

echo "=== 3. Running forensic corpus audit ==="
rag-sfar-audit --corpus-dir data/sfar_recommendations/output --output-dir reports

echo "=== 4. Building GPU SOTA indexes (BAAI/bge-m3) ==="
EMBED_MODEL="${RAG_SFAR_EMBEDDING_MODEL:-BAAI/bge-m3}"
RERANK_MODEL="${RAG_SFAR_RERANKER_MODEL:-BAAI/bge-reranker-v2-m3}"

rag-sfar-index --strategy naive_fixed --output-dir index/naive_fixed \
  --embedding-provider sentence_transformer --embedding-model "$EMBED_MODEL" --batch-size 64
rag-sfar-index --strategy hierarchical_markdown --output-dir index/hierarchical_markdown \
  --skip-embeddings
rag-sfar-index --strategy table_aware_sota --output-dir index/table_aware_sota \
  --embedding-provider sentence_transformer --embedding-model "$EMBED_MODEL" --batch-size 64

echo "=== 5. Running full C0->C8 ablation benchmark ==="
rag-sfar-eval --index-root index --output-dir reports \
  --reranker-provider cross_encoder --reranker-model "$RERANK_MODEL"

echo "=== DONE! Launch demo UI + OpenAI API with: ==="
echo "  rag-sfar-serve --index-dir index/table_aware_sota --host 0.0.0.0 --port 8000"
