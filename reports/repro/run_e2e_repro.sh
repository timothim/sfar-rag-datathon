#!/bin/bash
# Re-run the README end-to-end claims with the exact question IDs of the original reports.
set -u
cd "$(dirname "$0")/../.."
export HF_HUB_OFFLINE=1
PY=.venv/bin/python
MLX="${HOME}/.cache/huggingface/hub/models--mlx-community--Qwen2.5-7B-Instruct-4bit/snapshots/c26a38f6a37d0a51b4e9a1eb3026530fa35d9fed/"
R=reports/repro
$PY scripts/run_e2e_eval.py --backend mlx --mlx-model-path "$MLX" --model Qwen2.5-7B-Instruct-4bit --ids-file $R/e2e_c8_v3_7b_ids.json --modes c8_frontier --output $R/e2e_stratified50_c8.json --md-output $R/e2e_stratified50_c8.md
$PY scripts/run_e2e_eval.py --backend mlx --mlx-model-path "$MLX" --model Qwen2.5-7B-Instruct-4bit --ids-file $R/e2e_heldout_unseen_50_7b_ids.json --modes c8_frontier --output $R/e2e_heldout50_c8.json --md-output $R/e2e_heldout50_c8.md
$PY scripts/run_e2e_eval.py --backend mlx --mlx-model-path "$MLX" --model Qwen2.5-7B-Instruct-4bit --ids-file $R/e2e_c8_v3_7b_ids.json --modes zero_shot,c0_naive --output $R/e2e_stratified50_zs_c0.json --md-output $R/e2e_stratified50_zs_c0.md
