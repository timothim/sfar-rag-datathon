#!/bin/bash
# K2 measurement jobs needing the embedder / reranker (run under scripts/with_gpu_lock.sh K2).
set -e
cd "$(dirname "$0")/../../.."
export HF_HUB_OFFLINE=1 PYTHONPATH=src
.venv/bin/python reports/agents/K2_annexes/run_retrieval_v7.py
.venv/bin/python reports/agents/K2_annexes/probe_v7.py tas_v7
.venv/bin/python reports/agents/K2_annexes/probe_v7.py tas_v6
echo GPU_JOBS_DONE
