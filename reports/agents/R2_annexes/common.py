"""Shared loaders for the R2 offline analyses (no model loaded)."""
import json, sqlite3, os
from pathlib import Path
from functools import lru_cache
from rag_sfar.schemas import Chunk
from rag_sfar.evaluation.datasets import load_suite

ROOT = Path(__file__).resolve().parents[3]
B1RES = Path(os.environ.get("B1RES", "/private/tmp/claude-501/-Users-tim--claude-spares-spare-xXtqK0/fdfce601-0588-4326-8d77-e9ea020e9a31/scratchpad/res"))
R2RES = Path(__file__).parent / "res"
SUITES = ["abpe171", "abp171", "multirfe_synth"]

@lru_cache(None)
def chunks(index="tas_v3_errata"):
    conn = sqlite3.connect(ROOT / "index" / index / "metadata.sqlite")
    rows = conn.execute("SELECT payload_json FROM chunks ORDER BY idx ASC").fetchall()
    conn.close()
    out = [Chunk.model_validate_json(r[0]) for r in rows]
    return {c.chunk_id: c for c in out}, out

@lru_cache(None)
def items(suite):
    return {it.id: it for it in load_suite(suite, "dev")}

def rows(name, suite, src=None):
    for d in ([src] if src else [R2RES, B1RES]):
        p = Path(d) / f"{name}__{suite}.json"
        if p.exists():
            return {r["id"]: r for r in json.loads(p.read_text())["rows"]}
    return None

def attribute(row):
    """For each context position, the 'owner': the reason of the anchor it belongs to.
    Ranked items have reason None -> 'ranked'; window/note items inherit the preceding anchor."""
    owner, cur = [], "ranked"
    for r in row.get("reasons") or [None] * len(row["chunks"]):
        if r in (None, "") or not (r == "context_window" or r == "table_note"):
            cur = r or "ranked"
            owner.append(cur)
        else:
            owner.append(cur)
    return owner
