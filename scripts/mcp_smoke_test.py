#!/usr/bin/env python
"""Smoke test of a RAG-SFAR MCP server with the official MCP Python client (SDK `mcp`>=2.3).

Works against any Streamable HTTP endpoint or any stdio command:

    # HTTP (local process, container, or any URL)
    .venv/bin/python scripts/mcp_smoke_test.py --url http://127.0.0.1:8020/mcp
    # stdio (the client launches the server as a subprocess)
    .venv/bin/python scripts/mcp_smoke_test.py --stdio ".venv/bin/rag-sfar-mcp"

Checks: connection (protocol negotiation `auto`, or `--mode legacy|2026-07-28`), tool list,
one realistic call of each tool, citation fields (document, edition, section, passage), output
size bounds, and that bad arguments come back as MCP errors (`isError`), not as crashes.
Optional `--concurrency N`: N parallel `sfar_search` calls (latency per call and wall time).
Exit code 0 when every check passes. `--json` prints the machine-readable summary.
The queries below are generic examples, not taken from any evaluation set.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
from typing import Any

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters

HTTP_TOOLS = {
    "sfar_search",
    "search_sfar_recommendations",
    "compare_sfar_editions",
    "list_sfar_catalog",
    "get_recommendation_sections",
}
STDIO_TOOLS = HTTP_TOOLS - {"sfar_search"}
CITATION_FIELDS = ("doc_id", "title", "year", "status", "section", "url", "excerpt")
MAX_TEXT_CHARS = 60_000  # upper bound for one tool result (agent context budget)

QUERY = "conduite à tenir devant une intubation difficile imprévue au bloc opératoire"
EDITIONS_QUERY = "évolution entre éditions de la prise en charge de l'intubation difficile"


class Report:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.timings: dict[str, float] = {}

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{' — ' + detail if detail else ''}", flush=True)
        return ok

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.checks)


def _text(res: Any) -> str:
    return "\n".join(getattr(c, "text", "") for c in res.content)


async def _timed(rep: Report, label: str, coro: Any) -> Any:
    t0 = time.perf_counter()
    res = await coro
    rep.timings[label] = round(time.perf_counter() - t0, 3)
    return res


async def run(target: Any, mode: str, concurrency: int, rep: Report) -> None:
    t0 = time.perf_counter()
    async with Client(target, mode=mode, read_timeout_seconds=300) as client:
        rep.timings["connect"] = round(time.perf_counter() - t0, 3)
        tools = (await client.list_tools()).tools
        names = {t.name for t in tools}
        expected = HTTP_TOOLS if "sfar_search" in names else STDIO_TOOLS
        rep.check("tools/list", names == expected, f"{sorted(names)}")
        if "sfar_search" in names:
            ro = all(t.annotations is not None and t.annotations.read_only_hint for t in tools)
            rep.check("tools annotated read-only", ro)

        doc_id = None
        if "sfar_search" in names:
            res = await _timed(rep, "sfar_search", client.call_tool("sfar_search", {"query": QUERY, "top_k": 5}))
            data = res.structured_content or {}
            passages = data.get("passages", [])
            rep.check("sfar_search returns passages", not res.is_error and bool(passages), f"{len(passages)} passages")
            missing = [f for p in passages for f in CITATION_FIELDS if p.get(f) in (None, "")]
            rep.check("sfar_search citations complete", not missing and bool(passages),
                      f"missing={sorted(set(missing))}" if missing else "doc_id/title/year/status/section/url/excerpt")
            size = len(json.dumps(data, ensure_ascii=False))
            rep.check("sfar_search size bounded", len(passages) <= 5 and size < MAX_TEXT_CHARS, f"{size} chars")
            rep.check("sfar_search announces index_id", bool(data.get("index_id")), str(data.get("index_id")))
            if passages:
                p = passages[0]
                doc_id = p["doc_id"]
                print(f"    S1: {p['doc_id']} ({p['year']}, {p['status']}) § {p['section'][:80]}"
                      f" | {p['excerpt'][:160]!r}", flush=True)
            bad = await client.call_tool("sfar_search", {"query": "x", "top_k": 500})
            rep.check("sfar_search bad args -> MCP error", bad.is_error, _text(bad)[:120].replace("\n", " "))

        res = await _timed(rep, "search_sfar_recommendations",
                           client.call_tool("search_sfar_recommendations", {"query": QUERY, "top_k": 5}))
        txt = _text(res)
        rep.check("search_sfar_recommendations", not res.is_error and "[S1]" in txt and len(txt) < MAX_TEXT_CHARS,
                  f"{len(txt)} chars")
        if doc_id is None:
            import re

            m = re.search(r"doc_id[=:]\s*`?([\w\-\.]+)", txt)
            doc_id = m.group(1) if m else None

        res = await _timed(rep, "compare_sfar_editions",
                           client.call_tool("compare_sfar_editions", {"topic_query": EDITIONS_QUERY, "top_k": 6}))
        txt = _text(res)
        rep.check("compare_sfar_editions", not res.is_error and len(txt) > 200 and len(txt) < MAX_TEXT_CHARS,
                  f"{len(txt)} chars")

        res = await _timed(rep, "list_sfar_catalog",
                           client.call_tool("list_sfar_catalog", {"keyword": "intubation", "limit": 10}))
        txt = _text(res)
        rows = [r for r in txt.splitlines() if r.startswith("- [")]
        rep.check("list_sfar_catalog", not res.is_error and 0 < len(rows) <= 10, f"{len(rows)} rows")
        if doc_id is None and rows:
            doc_id = rows[0].split("`")[1]

        if doc_id:
            res = await _timed(rep, "get_recommendation_sections",
                               client.call_tool("get_recommendation_sections", {"doc_id": doc_id, "limit": 3}))
            txt = _text(res)
            rep.check("get_recommendation_sections", not res.is_error and txt.count("### [") == 3
                      and len(txt) < MAX_TEXT_CHARS, f"doc_id={doc_id}, {len(txt)} chars")
        else:
            rep.check("get_recommendation_sections", False, "no doc_id found")

        bad = await client.call_tool("get_recommendation_sections", {})
        rep.check("missing required arg -> MCP error", bad.is_error, _text(bad)[:120].replace("\n", " "))

        if concurrency > 1:
            tool = "sfar_search" if "sfar_search" in names else "search_sfar_recommendations"
            lat: list[float] = []

            async def one(i: int) -> None:
                t = time.perf_counter()
                r = await client.call_tool(tool, {"query": f"{QUERY} (variante {i})", "top_k": 5})
                lat.append(time.perf_counter() - t)
                assert not r.is_error

            t = time.perf_counter()
            async with anyio.create_task_group() as tg:
                for i in range(concurrency):
                    tg.start_soon(one, i)
            wall = time.perf_counter() - t
            lat.sort()
            rep.timings[f"parallel_{concurrency}_wall"] = round(wall, 3)
            rep.timings[f"parallel_{concurrency}_p50"] = round(lat[len(lat) // 2], 3)
            rep.timings[f"parallel_{concurrency}_max"] = round(lat[-1], 3)
            rep.check(f"{concurrency} parallel {tool}", len(lat) == concurrency,
                      f"wall {wall:.2f}s, p50 {lat[len(lat) // 2]:.2f}s, max {lat[-1]:.2f}s")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--url", help="Streamable HTTP endpoint, e.g. http://127.0.0.1:8020/mcp")
    g.add_argument("--stdio", help="stdio server command line, e.g. '.venv/bin/rag-sfar-mcp'")
    ap.add_argument("--mode", default="auto", help="auto (default), legacy, or a modern version (2026-07-28)")
    ap.add_argument("--concurrency", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.url:
        target: Any = args.url
    else:
        cmd = shlex.split(args.stdio)
        import os

        env = {**os.environ, "HF_HUB_OFFLINE": "1"}
        target = StdioServerParameters(command=cmd[0], args=cmd[1:], env=env)
    rep = Report()
    try:
        anyio.run(run, target, args.mode, args.concurrency, rep)
    except Exception as exc:  # connection or protocol failure
        rep.check("session", False, f"{type(exc).__name__}: {exc}")
    print("timings (s):", json.dumps(rep.timings), flush=True)
    print("RESULT:", "OK" if rep.ok else "FAILED", f"({sum(c['ok'] for c in rep.checks)}/{len(rep.checks)} checks)")
    if args.json:
        print(json.dumps({"ok": rep.ok, "checks": rep.checks, "timings": rep.timings}, ensure_ascii=False))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
