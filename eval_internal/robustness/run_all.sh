#!/bin/bash
# Runs every configuration, one GPU-lock acquisition per configuration.
cd "$(dirname "$0")/../.."
for c in frozen subword lexicon subword_lexicon bm25_only dense_only glossary; do
  scripts/with_gpu_lock.sh Q1 env HF_HUB_OFFLINE=1 .venv/bin/python eval_internal/robustness/run_retrieval.py --config "$c" 2>&1 | grep -v -i -E "warn|Loading weights|Redirects"
done
echo ALL_DONE
