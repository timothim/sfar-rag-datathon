#!/bin/bash
# Hypotheses H-a (concise prompt with coverage check) and H-b (neighbour expansion), sequential GPU.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
MLX=$(ls -d "$HOME"/.cache/huggingface/hub/models--mlx-community--Qwen2.5-7B-Instruct-4bit/snapshots/*/ | head -1)
export HF_HUB_OFFLINE=1
G=(--backend mlx --mlx-model-path "$MLX" --model Qwen2.5-7B-Instruct-4bit --gen-mode clinical_concise --max-tokens 250)
.venv/bin/rag-sfar-eval --suite multirfe_synth --split dev --configs C9 "${G[@]}" --tag c9_concise_v2 > reports/eval/queue_c9_concise_v2_multirfe.log 2>&1
.venv/bin/rag-sfar-eval --suite abp171 --split dev --configs C9 "${G[@]}" --tag c9_concise_v2 > reports/eval/queue_c9_concise_v2_abp.log 2>&1
# H-b: base C9 + neighbour expansion (variant only, base already measured above)
.venv/bin/rag-sfar-eval --suite multirfe_synth --split dev --configs C9 --ablate expand_neighbors=true "${G[@]}" --tag c9_concise_v2_neighbors > reports/eval/queue_c9_neighbors_multirfe.log 2>&1
echo "done $(date)" > reports/eval/queue_h_ab_done.txt
