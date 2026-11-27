#!/bin/bash
# B3 generation queue: each line of the runs file = "<tag> <cache> <preset> <gen-overrides|-> <gen-mode> <mcq-mode> [ids-files]".
# Runs one MLX process per line under the shared GPU lock (scripts/with_gpu_lock.sh).
cd "$(dirname "$0")/.."
export HF_HUB_OFFLINE=1
RUNS="$1"
MODEL=/Users/tim/.cache/rag_sfar_models/Qwen3.5-9B-MLX-4bit-nothink
DEF_IDS=eval_internal/work/b3_subsets/abpe171_iter.json,eval_internal/work/b3_subsets/multirfe_synth_iter.json
while read -r tag cache preset gen mode mcq ids extra; do
  [ -z "$tag" ] || [[ "$tag" == \#* ]] && continue
  [ "$gen" = "-" ] && gen=""
  { [ -z "$ids" ] || [ "$ids" = "-" ]; } && ids=$DEF_IDS
  echo "=== $tag $(date +%H:%M:%S)"
  scripts/with_gpu_lock.sh "b3-$tag" .venv/bin/python eval_internal/gen_replay.py run --cache "$cache" \
    --suite "${SUITES:-abpe171,multirfe_synth}" --ids-file "$ids" --preset "$preset" --gen "$gen" --gen-mode "$mode" \
    --mcq-mode "$mcq" --backend mlx --mlx-model-path "$MODEL" --model qwen3.5-9b-4bit-nothink --tag "$tag" $extra 2>&1 \
    | grep -E "^(abpe171|multirfe_synth):|Traceback|Error|error" 
done < "$RUNS"
echo "=== QUEUE_DONE $(date +%H:%M:%S)"
