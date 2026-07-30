#!/usr/bin/env bash
# Build membrane CMS for molecules listed in meta/cms_todo.txt
set -euo pipefail
SCHRODINGER="${SCHRODINGER:-/opt/schrodinger2023-3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MSJ="$ROOT/scripts/protocols/build_membrane_system.msj"
MAX_PARALLEL="${MAX_PARALLEL:-2}"
TODO="$ROOT/meta/cms_todo.txt"

build_one() {
  local mid="$1"
  local work="$ROOT/03_systems/$mid"
  mkdir -p "$work"
  if [[ -f "$work/${mid}-out.cms" ]]; then
    if "$SCHRODINGER/run" python3 -c "from schrodinger.application.desmond.cms import Cms; Cms(file='$work/${mid}-out.cms')" 2>/dev/null; then
      echo "[skip] $mid"
      return 0
    fi
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
  echo "[build] $mid $(date -Is)"
  "$SCHRODINGER/utilities/multisim" -WAIT -HOST localhost -maxjob 1 \
    -JOBNAME "${mid}_build" -m build.msj solute.mae -o "${mid}-out.cms" -mode umbrella \
    > build_launch.log 2>&1
  if "$SCHRODINGER/run" python3 -c "from schrodinger.application.desmond.cms import Cms; Cms(file='$work/${mid}-out.cms')"; then
    echo "[ok] $mid $(du -h $work/${mid}-out.cms | awk '{print $1}')"
  else
    echo "[FAIL] $mid" >&2
    return 1
  fi
}

pids=()
while read -r mid; do
  [[ -z "$mid" ]] && continue
  build_one "$mid" &
  pids+=($!)
  while (( ${#pids[@]} >= MAX_PARALLEL )); do
    wait -n || true
    new=()
    for p in "${pids[@]}"; do
      kill -0 "$p" 2>/dev/null && new+=("$p") || true
    done
    pids=("${new[@]}")
  done
done < "$TODO"
wait
echo "ALL_CMS_BUILDS_DONE"
