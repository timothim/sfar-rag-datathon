#!/bin/bash
# K2 follow-up: build tas_v7b (bibliography switch off) then retrieval + probe (under with_gpu_lock.sh K2).
set -e
cd "$(dirname "$0")/../../.."
export HF_HUB_OFFLINE=1 PYTHONPATH=src
unset RAG_SFAR_TABLE_ADJACENT_HEADERS RAG_SFAR_CHUNK_BIBLIO
date +%T
/usr/bin/time -p env RAG_SFAR_CHUNK_GRADE_HEADINGS=1 RAG_SFAR_CHUNK_GRADES=1 RAG_SFAR_CHUNK_REC_IDS=1 \
  .venv/bin/rag-sfar-index --strategy table_aware_sota --output-dir index/tas_v7b
date +%T
.venv/bin/python reports/agents/K2_annexes/run_retrieval_v7.py tas_v7b
.venv/bin/python reports/agents/K2_annexes/probe_v7.py tas_v7b
echo GPU_JOBS_DONE
