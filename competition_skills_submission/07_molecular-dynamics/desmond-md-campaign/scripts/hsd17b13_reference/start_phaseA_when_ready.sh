#!/usr/bin/env bash
set -euo pipefail
SCHRODINGER="${SCHRODINGER:-/opt/schrodinger2023-3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/logs/start_phaseA_when_ready.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== start_phaseA_when_ready $(date -Is) ==="

# 1) wait loadtest lt2 done
while true; do
  out=$("$SCHRODINGER/jobcontrol" -list 2>&1 || true)
  if echo "$out" | grep -q "HSD17B13_lt2_.*running"; then
    echo "$(date -Is) waiting loadtest..."
    sleep 30
  else
    echo "$(date -Is) loadtest clear"
    break
  fi
done

# 2) wait until at least 1 CMS ready (queue itself fills GPUs as more CMS appear)
while true; do
  n=0
  while read -r mid; do
    [[ -f "$ROOT/03_systems/$mid/${mid}-out.cms" ]] && n=$((n+1))
  done < "$ROOT/meta/ids_27.txt"
  echo "$(date -Is) cms_ready=$n/27"
  (( n >= 1 )) && break
  sleep 30
done

# 3) launch Phase A queue (do not wait for full 27 — avoids idle GPUs)
echo "$(date -Is) launching Phase A 6GPU queue (CMS may still be building)"
cd "$ROOT"
CONFIRM_PHASE_A=YES NGPU=6 python3 scripts/05_phaseA_6gpu_queue.py
echo "$(date -Is) phaseA queue script exited"
