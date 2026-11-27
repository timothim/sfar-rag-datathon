"""K3 - Build index/tas_v6_tablefix: same build as tas_v6 (default chunker options, e5-small,
corpus overlay) with only RAG_SFAR_TABLE_ADJACENT_HEADERS=1, plus gap_wrapper (continuation_gap
passed to table_parser without editing chunker.py).

Run from a checkout whose src/ holds the code to build (here a git worktree of the commit, so
that uncommitted changes of other agents in the main tree are excluded):
  RAG_SFAR_TABLE_ADJACENT_HEADERS=1 HF_HUB_OFFLINE=1 scripts/with_gpu_lock.sh K3 \
    .venv/bin/python -I <checkout>/reports/agents/K3_annexes/build_tablefix.py \
    --corpus-dir data/sfar_recommendations/output --output-dir index/tas_v6_tablefix
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CHECKOUT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import rag_sfar.ingestion.table_parser as tp  # noqa: E402
import gap_wrapper  # noqa: E402
from rag_sfar.cli import build_and_save_index  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--corpus-dir", type=Path, required=True)
ap.add_argument("--output-dir", type=Path, required=True)
args = ap.parse_args()
if args.output_dir.exists():
    raise SystemExit(f"{args.output_dir} exists: refusing to overwrite an index folder")
if not tp.ADJACENT_HEADERS:
    raise SystemExit("RAG_SFAR_TABLE_ADJACENT_HEADERS=1 is required for this build")
gap_wrapper.install()
t0 = time.time()
build_and_save_index(corpus_dir=args.corpus_dir, output_dir=args.output_dir)
src = CHECKOUT / "src" / "rag_sfar" / "ingestion"
notes = {
    "index": args.output_dir.name,
    "base": "index/tas_v6 build (default ChunkOptions, intfloat/multilingual-e5-small, corpus overlay)",
    "switches": {"RAG_SFAR_TABLE_ADJACENT_HEADERS": "1"},
    "continuation_gap": "reports/agents/K3_annexes/gap_wrapper.py (chunker.py not modified)",
    "other_agents_changes": "none (built from a clean worktree of the commit below; K2 chunker switches absent)",
    "commit": subprocess.run(["git", "-C", str(CHECKOUT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
    "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (src / "table_parser.py", src / "chunker.py")},
    "wall_seconds": round(time.time() - t0, 1),
}
(args.output_dir / "BUILD_NOTES.json").write_text(json.dumps(notes, indent=1))
print(json.dumps(notes, indent=1))
