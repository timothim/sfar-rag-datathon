# RAG-SFAR: one image, two services (selected at run time, see docker/entrypoint.sh)
#   RAG_SFAR_SERVICE=mcp (default): read-only MCP server, Streamable HTTP, /mcp + /healthz
#   RAG_SFAR_SERVICE=api          : web API + demo chatbot (rag-sfar-serve), generator via an
#                                   OpenAI-compatible endpoint (RAG_SFAR_LLM_BASE_URL/_MODEL/_API_KEY)
# The index is NOT in the image: mount it at /data/index (index/tas_v6, ~576 MB).
# Models: baked at build time (BAKE_MODELS=1, needs network once, ~1 GB) or mounted at run time
# (BAKE_MODELS=0, then mount a Hugging Face cache containing both models at /models/hf).
# No secret in this file: the LLM key is supplied at run time only (env var or secret file).
# Status: written and reviewed, NOT built yet (Docker daemon not running on the dev machine).
FROM python:3.12-slim

ARG BAKE_MODELS=1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/hf HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    RAG_SFAR_INDEX_DIR=/data/index \
    RAG_SFAR_SERVICE=mcp RAG_SFAR_MCP_PORT=8020 RAG_SFAR_API_PORT=8000 \
    RAG_SFAR_MCP_ALLOWED_HOSTS="127.0.0.1:*,localhost:*"

WORKDIR /app
# CPU-only torch (the CUDA wheel is ~2.5 GB larger and the container has no Metal GPU).
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2,<3"
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[neural,mcp]"

# Embedding + reranking models, fetched once at build time (only the files the runtime loads).
RUN if [ "$BAKE_MODELS" = "1" ]; then \
      HF_HUB_OFFLINE=0 python -c "from huggingface_hub import snapshot_download as s; \
p=['*.json','*.safetensors','*.model','*.txt','1_Pooling/*']; \
s('intfloat/multilingual-e5-small', allow_patterns=p); \
s('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1', allow_patterns=p)"; \
    fi

COPY docker/entrypoint.sh docker/healthcheck.py /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh && useradd --uid 10001 --no-create-home sfar
USER sfar

EXPOSE 8020 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python /usr/local/bin/healthcheck.py
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
