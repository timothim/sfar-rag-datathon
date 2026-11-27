#!/bin/bash
# Run one heavy job (index build, embedding, reranker evaluation, MLX generation) at a time.
# Usage: scripts/with_gpu_lock_fair.sh <label> <command> [args...]
# The 16 GB machine runs out of Metal memory when two heavy jobs overlap. The lock is the
# directory .gpu_lock/ (atomic mkdir), shared with scripts/with_gpu_lock.sh. Waiters are served
# first come, first served: each takes a ticket in .gpu_queue/ and only the oldest live ticket
# may take the lock, so a chain of jobs from one agent cannot starve another agent. Tickets and
# locks whose process is gone are removed.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCK="$ROOT/.gpu_lock"
QUEUE="$ROOT/.gpu_queue"
label="$1"
shift
mkdir -p "$QUEUE"
ticket="$QUEUE/$(printf '%012d-%07d' "$(date +%s)" $$)"
echo "$label" > "$ticket"
trap 'rm -f "$ticket"' EXIT INT TERM
waited=0
while :; do
  for t in "$QUEUE"/*; do
    [ -e "$t" ] || continue
    pid=$((10#$(basename "$t" | cut -d- -f2)))
    kill -0 "$pid" 2>/dev/null || rm -f "$t"
  done
  first=$(ls "$QUEUE" | sort | head -1)
  if [ "$QUEUE/$first" = "$ticket" ] && mkdir "$LOCK" 2>/dev/null; then
    break
  fi
  owner=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
    rmdir "$LOCK" 2>/dev/null || { rm -f "$LOCK/pid" "$LOCK/owner"; rmdir "$LOCK" 2>/dev/null; }
    continue
  fi
  sleep 5
  waited=$((waited + 5))
done
echo $$ > "$LOCK/pid"
echo "$label $(date '+%H:%M:%S')" > "$LOCK/owner"
trap 'rm -f "$LOCK/pid" "$LOCK/owner" "$ticket"; rmdir "$LOCK" 2>/dev/null' EXIT INT TERM
rm -f "$ticket"
[ "$waited" -gt 0 ] && echo "[gpu-lock] $label waited ${waited}s" >&2
"$@"
