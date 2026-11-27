"""Container health check: /healthz (MCP service) or /api/health (web API service)."""
import os
import sys
import urllib.request

if os.environ.get("RAG_SFAR_SERVICE", "mcp") == "api":
    url = f"http://127.0.0.1:{os.environ.get('RAG_SFAR_API_PORT', '8000')}/api/health"
else:
    url = f"http://127.0.0.1:{os.environ.get('RAG_SFAR_MCP_PORT', '8020')}/healthz"
try:
    with urllib.request.urlopen(url, timeout=4) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
