#!/usr/bin/env bash
# Wait until the A6000 is genuinely free, then run the resumable static amount
# generation. Other projects keep priority: this never signals, stops, or
# competes with their processes, and it requires the card to be clear of all
# other compute applications for two consecutive checks before loading.
set -u -o pipefail

PROJECT=/opt/tokkio-data0/tokkio_projects/Metacom5_3
PYTHON=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
OUT="$PROJECT/project/outputs/paper1_calibration/static_generation_20260917_v1"
LOG="$OUT/watcher.log"
INTERVAL="${INTERVAL:-120}"
REQUIRED_FREE_MIB="${REQUIRED_FREE_MIB:-18432}"
SELF_PID=$$

mkdir -p "$OUT"

log() { printf '%s %s\n' "$(date -Is)" "$*" >>"$LOG"; }

# One watcher at a time, so a re-launch can never start a second generation run.
exec 9>"$OUT/watcher.lock"
if ! flock -n 9; then
  log "another watcher already holds the lock; exiting"
  exit 0
fi

a6000_uuid() {
  nvidia-smi --query-gpu=uuid,name --format=csv,noheader | awk -F', *' '$2=="NVIDIA RTX A6000"{print $1; exit}'
}

log "watcher started (pid $SELF_PID); interval ${INTERVAL}s; required free ${REQUIRED_FREE_MIB} MiB"

clear_checks=0
checks=0
heartbeat_every=$(( 900 / INTERVAL )); [ "$heartbeat_every" -lt 1 ] && heartbeat_every=1
while true; do
  checks=$((checks + 1))
  uuid="$(a6000_uuid)"
  if [ -z "$uuid" ]; then
    log "no A6000 visible; waiting"
    clear_checks=0
    sleep "$INTERVAL"; continue
  fi
  free_mib="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i "$uuid" | tr -d ' ')"
  others="$(nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader \
            | awk -F', *' -v u="$uuid" -v me="$SELF_PID" '$1==u && $2!=me {print $2}' | wc -l)"
  if [ "$others" -eq 0 ] && [ "$free_mib" -ge "$REQUIRED_FREE_MIB" ]; then
    clear_checks=$((clear_checks + 1))
    log "A6000 clear (${free_mib} MiB free, ${others} other compute apps); consecutive clear checks=${clear_checks}"
  else
    [ "$clear_checks" -gt 0 ] && log "A6000 busy again (${free_mib} MiB free, ${others} other compute apps); resetting"
    clear_checks=0
    # Heartbeat so a long wait is visibly a wait rather than a dead watcher.
    if [ $((checks % heartbeat_every)) -eq 1 ]; then
      log "waiting: ${free_mib} MiB free, ${others} other compute apps still on the A6000"
    fi
  fi
  if [ "$clear_checks" -ge 2 ]; then
    log "starting static amount generation"
    CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1 \
      "$PYTHON" "$PROJECT/project/scripts/paper1/79_run_static_amount_generation.py" >>"$OUT/run.log" 2>&1
    status=$?
    log "generation invocation exited with status ${status}"
    if [ "$status" -eq 0 ]; then
      log "watcher finished"
      exit 0
    fi
    # A device or contention error is not fatal: the run is resumable, so go
    # back to waiting rather than retrying immediately against a busy card.
    clear_checks=0
  fi
  sleep "$INTERVAL"
done
