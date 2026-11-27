#!/bin/bash
# Run one heavy job (index build, embedding, reranker evaluation, MLX generation) at a time.
# Usage: scripts/with_gpu_lock.sh <label> <command> [args...]
# The 16 GB machine runs out of Metal memory when two heavy jobs overlap. The lock is a
# directory (atomic mkdir); a lock whose owner process is gone is taken over.
set -u
LOCK="$(cd "$(dirname "$0")/.." && pwd)/.gpu_lock"
label="$1"; shift
waited=0
while ! mkdir "$LOCK" 2>/dev/null; do
  owner=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
    rm -rf "$LOCK"; continue
  fi
  if [ -z "$owner" ] && [ "$waited" -ge 30 ]; then rm -rf "$LOCK"; continue; fi
  sleep 10; waited=$((waited + 10))
done
echo $$ > "$LOCK/pid"; echo "$label $(date '+%H:%M:%S')" > "$LOCK/owner"
trap 'rm -rf "$LOCK"' EXIT INT TERM
[ "$waited" -gt 0 ] && echo "[gpu-lock] $label waited ${waited}s" >&2
"$@"
