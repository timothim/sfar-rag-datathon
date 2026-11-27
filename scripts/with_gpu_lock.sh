#!/bin/bash
# Run heavy jobs (embedding, reranker evaluation, index build) a few at a time.
# Usage: scripts/with_gpu_lock.sh <label> <command> [args...]
#
# Up to GPU_LOCK_SLOTS jobs (default 3) hold a slot at once. The retrieval models are small
# (about 1.5-2 GB per process on the 16 GB machine); the single-slot rule dated from the time a
# 9B generator shared the GPU. Set GPU_LOCK_SLOTS=1 before starting a generator model or a job
# whose latency must be measured without contention.
#
# Slot 1 is the directory .gpu_lock/ (atomic mkdir), kept compatible with the previous
# single-slot version of this script: a waiter started with the old version only ever takes
# slot 1, in queue order. Slots 2..N are .gpu_lock_2/ ... Waiters take a ticket in .gpu_queue/
# and are served first come, first served. Tickets and slots whose process is gone are removed.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QUEUE="$ROOT/.gpu_queue"
SLOTS="${GPU_LOCK_SLOTS:-3}"
label="$1"
shift
mkdir -p "$QUEUE"
ticket="$QUEUE/$(printf '%012d-%07d' "$(date +%s)" $$)-n"
echo "$label" > "$ticket"
trap 'rm -f "$ticket"' EXIT INT TERM

slot_dir() {
  if [ "$1" -eq 1 ]; then echo "$ROOT/.gpu_lock"; else echo "$ROOT/.gpu_lock_$1"; fi
}

waited=0
got=""
while :; do
  # drop tickets of dead processes
  for t in "$QUEUE"/*; do
    [ -e "$t" ] || continue
    pid=$((10#$(basename "$t" | cut -d- -f2)))
    kill -0 "$pid" 2>/dev/null || rm -f "$t"
  done
  # free slots whose owner is gone
  k=1
  while [ "$k" -le "$SLOTS" ]; do
    d="$(slot_dir "$k")"
    owner=$(cat "$d/pid" 2>/dev/null || echo "")
    if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
      rm -f "$d/pid" "$d/owner"
      rmdir "$d" 2>/dev/null
    fi
    k=$((k + 1))
  done
  # slot 1: only the oldest ticket of the whole queue (same rule as the old script)
  first=$(ls "$QUEUE" | sort | head -1)
  if [ "$QUEUE/$first" = "$ticket" ] && mkdir "$(slot_dir 1)" 2>/dev/null; then
    got="$(slot_dir 1)"
    break
  fi
  # extra slots: first come, first served among tickets of this version of the script
  rank=$(ls "$QUEUE" | grep -- '-n$' | sort | grep -n -x -- "$(basename "$ticket")" | cut -d: -f1)
  free_extra=0
  k=2
  while [ "$k" -le "$SLOTS" ]; do
    [ -d "$(slot_dir "$k")" ] || free_extra=$((free_extra + 1))
    k=$((k + 1))
  done
  if [ -n "$rank" ] && [ "$rank" -le "$free_extra" ]; then
    k=2
    while [ "$k" -le "$SLOTS" ]; do
      if mkdir "$(slot_dir "$k")" 2>/dev/null; then
        got="$(slot_dir "$k")"
        break
      fi
      k=$((k + 1))
    done
    [ -n "$got" ] && break
  fi
  sleep 3
  waited=$((waited + 3))
done
echo $$ > "$got/pid"
echo "$label $(date '+%H:%M:%S')" > "$got/owner"
trap 'rm -f "$got/pid" "$got/owner" "$ticket"; rmdir "$got" 2>/dev/null' EXIT INT TERM
rm -f "$ticket"
[ "$waited" -gt 0 ] && echo "[gpu-lock] $label waited ${waited}s" >&2
"$@"
