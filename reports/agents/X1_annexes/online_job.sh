#!/bin/bash
# X1 online job (run under scripts/with_gpu_lock.sh): wrapper disabled (identity), counterparts
# enabled (gated), then the slow identity test.
cd /Users/tim/Me/SFAR-datathon
export HF_HUB_OFFLINE=1
PY=".venv/bin/python -u reports/agents/X1_annexes/capture.py"
$PY --name wrapoff --links index/tas_v6_links --policy '{}'
$PY --name cp --links index/tas_v6_links --policy '{"counterparts": true}'
$PY --name cpnotes --links index/tas_v6_links --policy '{"counterparts": true, "notes": true}'
RAG_SFAR_SLOW_TESTS=1 .venv/bin/python -m pytest -q tests/test_x1_links.py -k frozen_retriever 2>&1 | tail -3
