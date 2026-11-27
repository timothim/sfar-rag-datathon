"""Stand-in OpenAI-compatible server for smoke tests of the live-model paths (no model loaded).

It answers the three kinds of prompt the pipeline sends, in their strict formats, with
deterministic, content-free text (it is NOT a generator and its answers mean nothing):
- question normalisation (query_rewrite "normalize"): every other question "INCHANGEE", the
  others "NORMALISEE: <question with its first word repeated>" (a change the add mode accepts);
- decomposition (multi_query "decompose"): every third question "MULTIPLE" + two
  sub-questions (the two halves of the question), the others "SIMPLE";
- generation (any other prompt): a one-sentence answer citing [S1].
Which branch fires depends on a hash of the question, so runs are reproducible.

    .venv/bin/python scripts/standin_openai_server.py --port 8099
    # then: --backend openai --base-url http://127.0.0.1:8099/v1 --model standin

Counts of each kind of call are printed on exit (Ctrl-C) and served at GET /stats.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATS = {"normalize": 0, "decompose": 0, "generate": 0, "other": 0}


def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _question(user: str) -> str:
    m = re.search(r"Question :\n(.*)", user, re.S)
    return (m.group(1) if m else user).strip()


def answer(system: str, user: str) -> tuple[str, str]:
    if "normaliser l'écriture de la question" in system:
        q = _question(user)
        if _h(q) % 2 == 0:
            return "normalize", "INCHANGEE"
        first = q.split()[0] if q.split() else "Question"
        return "normalize", "NORMALISEE: " + " ".join((first + " " + q).split())
    if "SIMPLE" in system and "MULTIPLE" in system:
        q = _question(user)
        words = q.split()
        if _h(q) % 3 == 0 and len(words) >= 8:
            half = len(words) // 2
            return "decompose", f"MULTIPLE\n1. {' '.join(words[:half])}\n2. {' '.join(words[half:])}"
        return "decompose", "SIMPLE"
    if "[S1]" in system or "[S1]" in user or "EXTRAITS" in user.upper():
        return "generate", "Réponse de substitution du serveur de test, sans valeur clinique [S1]."
    return "other", "Réponse de substitution du serveur de test."


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": "standin", "object": "model"}]})
        elif self.path.rstrip("/").endswith("/stats"):
            self._json(200, STATS)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": "not found"})
            return
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        msgs = req.get("messages", [])
        system = "\n".join(m.get("content", "") for m in msgs if m.get("role") == "system")
        user = "\n".join(m.get("content", "") for m in msgs if m.get("role") == "user")
        kind, text = answer(system, user)
        STATS[kind] += 1
        if req.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunk = {"id": "standin", "object": "chat.completion.chunk", "model": req.get("model", "standin"),
                     "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
            self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            return
        self._json(200, {
            "id": "standin", "object": "chat.completion", "model": req.get("model", "standin"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": (len(system) + len(user)) // 4, "completion_tokens": len(text) // 4,
                      "total_tokens": (len(system) + len(user) + len(text)) // 4},
        })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    a = ap.parse_args()
    httpd = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"stand-in OpenAI server on http://{a.host}:{a.port}/v1", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    print(json.dumps(STATS), flush=True)


if __name__ == "__main__":
    main()
