#!/usr/bin/env bash
# Universal manifest-driven launcher for canonical E-Drug Lab skills.
# Example: bash scripts/run_skill.sh --skill funnel-diffdynamic-prudent --manifest MANIFEST --dry-run
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi
export PATH="$ROOT/.venv/bin:$PATH"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m masld_agent.skill_runner "$@"
