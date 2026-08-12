#!/usr/bin/env bash
# Build membrane CMS for Phase D new13 (CPU only; never submits GPU MD).
set -euo pipefail
SCHRODINGER="${SCHRODINGER:-/opt/schrodinger2023-3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MSJ="$ROOT/scripts/protocols/build_membrane_system.msj"
MAX_PARALLEL="${MAX_PARALLEL:-2}"
TODO="$ROOT/meta/phaseD_new13_ids.txt"
LOG="$ROOT/logs/phaseD_cms_build.log"

mkdir -p "$ROOT/logs"
echo "[$(date -Is)] Phase D CMS build start MAX_PARALLEL=$MAX_PARALLEL" | tee -a "$LOG"

build_one() {
  local mid="$1"
  local work="$ROOT/03_systems/$mid"
  mkdir -p "$work"
  if [[ -f "$work/${mid}-out.cms" ]]; then
    if "$SCHRODINGER/run" python3 -c "from schrodinger.application.desmond.cms import Cms; Cms(file='$work/${mid}-out.cms')" 2>/dev/null; then
      echo "[skip] $mid" | tee -a "$LOG"
      return 0
    fi
  fi
  if [[ ! -f "$ROOT/meta/ligands/${mid}.mae" ]]; then
    echo "[FAIL] $mid missing ligand mae" | tee -a "$LOG" >&2
    return 1
  fi
  "$SCHRODINGER/run" python3 -c "
from schrodinger import structure
from pathlib import Path
ROOT=Path('$ROOT'); mid='$mid'; work=Path('$work')
rec=next(structure.StructureReader(str(ROOT/'01_template/prepared_dimer.mae')))
lig=next(structure.StructureReader(str(ROOT/'meta/ligands'/f'{mid}.mae')))
lig.title=mid
with structure.StructureWriter(str(work/'solute.mae')) as w:
    w.append(rec); w.append(lig)
"
  cp -f "$MSJ" "$work/build.msj"
  cd "$work"
  echo "[build] $mid $(date -Is)" | tee -a "$LOG"
  "$SCHRODINGER/utilities/multisim" -WAIT -HOST localhost -maxjob 1 \
    -JOBNAME "${mid}_phaseD_build" -m build.msj solute.mae -o "${mid}-out.cms" -mode umbrella \
    > build_launch.log 2>&1
  if "$SCHRODINGER/run" python3 -c "from schrodinger.application.desmond.cms import Cms; Cms(file='$work/${mid}-out.cms')"; then
    echo "[ok] $mid $(du -h $work/${mid}-out.cms | awk '{print $1}')" | tee -a "$LOG"
  else
    echo "[FAIL] $mid" | tee -a "$LOG" >&2
    return 1
  fi
}

pids=()
fails=0
while read -r mid; do
  [[ -z "$mid" || "$mid" == \#* ]] && continue
  build_one "$mid" &
  pids+=($!)
  while (( ${#pids[@]} >= MAX_PARALLEL )); do
    wait -n || ((fails++)) || true
    new=()
    for p in "${pids[@]}"; do
      kill -0 "$p" 2>/dev/null && new+=("$p") || true
    done
    pids=("${new[@]}")
  done
done < "$TODO"
for p in "${pids[@]}"; do
  wait "$p" || ((fails++)) || true
done
echo "[$(date -Is)] Phase D CMS builds done fails=$fails" | tee -a "$LOG"
exit "$fails"
