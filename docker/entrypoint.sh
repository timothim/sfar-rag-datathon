#!/bin/sh
# Select the service: first argument (mcp | api) or RAG_SFAR_SERVICE; any other command is exec'd.
# Inside the container the process binds 0.0.0.0 (required to be reachable through the published
# port); the compose file publishes it on the host's 127.0.0.1 only. For the MCP server, the SDK's
# DNS rebinding protection stays on through RAG_SFAR_MCP_ALLOWED_HOSTS.
set -e
svc="${1:-$RAG_SFAR_SERVICE}"
case "$svc" in
  mcp) [ $# -gt 0 ] && shift
       exec rag-sfar-mcp-http --host "${RAG_SFAR_MCP_HOST:-0.0.0.0}" --port "${RAG_SFAR_MCP_PORT:-8020}" "$@" ;;
  api) [ $# -gt 0 ] && shift
       exec rag-sfar-serve --host "${RAG_SFAR_API_HOST:-0.0.0.0}" --port "${RAG_SFAR_API_PORT:-8000}" "$@" ;;
  *)   exec "$@" ;;
esac
