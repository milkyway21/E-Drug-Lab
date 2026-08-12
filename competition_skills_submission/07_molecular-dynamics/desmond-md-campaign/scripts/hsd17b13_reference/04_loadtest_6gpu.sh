#!/usr/bin/env bash
# Launch 6-GPU loadtest. DO NOT run until user confirms review.
# Usage: CONFIRM_LOADTEST=YES bash scripts/04_loadtest_6gpu.sh
set -euo pipefail
SCHRODINGER="${SCHRODINGER:-/opt/schrodinger2023-3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "${CONFIRM_LOADTEST:-}" != "YES" ]]; then
  echo "Refusing to launch. Review systems first, then:"
  echo "  CONFIRM_LOADTEST=YES bash scripts/04_loadtest_6gpu.sh"
  exit 2
fi
MSJ="$ROOT/scripts/protocols/loadtest_1ns.msj"
mapfile -t IDS < "$ROOT/meta/loadtest_6_ids.txt"
# GPU 0-5, 8 CPUs each from cpu_gpu_binding.txt
i=0
for mid in "${IDS[@]}"; do
  cms="$ROOT/03_systems/$mid/${mid}-out.cms"
  [[ -f "$cms" ]] || { echo "missing $cms"; exit 1; }
  jobdir="$ROOT/02_benchmark/${mid}_test"
  mkdir -p "$jobdir"
  cp -f "$cms" "$jobdir/"
  cp -f "$MSJ" "$jobdir/md.msj"
  cd "$jobdir"
  export CUDA_VISIBLE_DEVICES=$i
  # CPU affinity: cores i*8 .. i*8+7
  c0=$((i*8)); c1=$((c0+7))
  echo "Launch $mid on GPU $i CPUs ${c0}-${c1}"
  numactl --physcpubind=${c0}-${c1} \
    "$SCHRODINGER/utilities/multisim" -HOST localhost -maxjob 1 \
    -JOBNAME "HSD17B13_loadtest_${mid}" \
    -m md.msj "${mid}-out.cms" -o "loadtest_${mid}-out.cms" -mode umbrella \
    > launch.log 2>&1 &
  echo $! > launch.pid
  i=$((i+1))
done
echo "Submitted 6 loadtest jobs. Monitor with nvidia-smi / 02_benchmark/*/launch.log"
