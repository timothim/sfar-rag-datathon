#!/bin/bash
# Sequential GPU queue (one GPU job at a time: MLX generation and embedders do not fit together).
# Phase 3 dev measurements, local Qwen2.5-7B-Instruct-4bit (MLX). Logs in reports/eval/queue_*.log.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LEGACY="$ROOT/../sfar-legacy"
PY="$ROOT/.venv/bin/python"
MLX=$(ls -d "$HOME"/.cache/huggingface/hub/models--mlx-community--Qwen2.5-7B-Instruct-4bit/snapshots/*/ | head -1)
export HF_HUB_OFFLINE=1
GEN=(--backend mlx --mlx-model-path "$MLX" --model Qwen2.5-7B-Instruct-4bit)

run_new() {  # suite configs mode max_tokens tag [extra...]
  local suite=$1 cfg=$2 mode=$3 mt=$4 tag=$5; shift 5
  (cd "$ROOT" && .venv/bin/rag-sfar-eval --suite "$suite" --split dev --configs "$cfg" --gen-mode "$mode" \
     --max-tokens "$mt" "${GEN[@]}" --tag "$tag" "$@") > "$ROOT/reports/eval/queue_${tag}_${suite}.log" 2>&1
}

# 0. Qwen3-Embedding index, retrieval only (fast)
(cd "$ROOT" && .venv/bin/rag-sfar-eval --suite multirfe_synth --split dev --configs C9 --retrieval-only \
   --index-map table_aware_sota=tas_qwen3emb06 --tag c9_qwen3emb) > "$ROOT/reports/eval/queue_c9_qwen3emb.log" 2>&1
(cd "$ROOT" && .venv/bin/rag-sfar-eval --suite abp171 --split dev --configs C9 --retrieval-only \
   --index-map table_aware_sota=tas_qwen3emb06 --tag c9_qwen3emb) >> "$ROOT/reports/eval/queue_c9_qwen3emb.log" 2>&1

# 1. Legacy C8 on the internal set (the run that failed with Metal OOM)
(cd "$LEGACY" && PYTHONPATH="$LEGACY/src" "$PY" -c "
import sys; sys.argv=['rag-sfar-eval','--suite','multirfe_synth','--split','dev','--configs','C8','--index-root','$ROOT/index','--backend','mlx','--mlx-model-path','$MLX','--model','Qwen2.5-7B-Instruct-4bit','--max-tokens','400','--tag','legacy_gen_7b']
from rag_sfar.cli import eval_cmd; eval_cmd()") > "$ROOT/reports/eval/queue_legacy_multirfe.log" 2>&1
cp "$LEGACY"/reports/eval/*multirfe_synth_dev_legacy_gen_7b* "$ROOT/reports/eval/" 2>/dev/null

# 2. New C9, same detailed mode as legacy (isolates cleanup + simplification)
run_new multirfe_synth C9 auto 400 c9_detailed
run_new abp171 C9 auto 400 c9_detailed

# 3. New C9, concise answer-first mode (prompt hypothesis)
run_new multirfe_synth C9 clinical_concise 250 c9_concise
run_new abp171 C9 clinical_concise 250 c9_concise
echo "queue done $(date)" > "$ROOT/reports/eval/queue_done.txt"
