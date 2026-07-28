#!/usr/bin/env bash
# Launch Scientist_In_E-Drug-Lab via Hermes multi-provider chat (Claude-Code-like).
# Usage:
#   bash scripts/start_agent.sh              # hermes chat (default)
#   bash scripts/start_agent.sh chat         # same
#   bash scripts/start_agent.sh shell        # bash with masld-agent CLI
#   bash scripts/start_agent.sh sync         # only sync CC-Switch → .hermes
# Extra args after mode are forwarded to hermes chat, e.g.:
#   bash scripts/start_agent.sh chat --provider volcano-anthropic
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

export HERMES_HOME="${HERMES_HOME:-$ROOT/.hermes}"
export MASLD_COMPETITION_EVAL_MODE="${MASLD_COMPETITION_EVAL_MODE:-true}"
export PYTHONPATH="$ROOT/src:${PYTHONPATH:-}"
export HERMES_ENABLE_PROJECT_PLUGINS="${HERMES_ENABLE_PROJECT_PLUGINS:-true}"

MODE="${1:-chat}"
if [[ $# -ge 1 ]]; then
  shift
fi

python "$ROOT/scripts/sync_providers_from_ccswitch.py" --hermes-home "$HERMES_HOME"
python "$ROOT/scripts/import_drug_skills.py" --hermes-home "$HERMES_HOME" || true

cat <<BANNER
============================================================
  Scientist_In_E-Drug-Lab  |  e-drug-lab scientist
  药物发现科研助手（不限单一疾病；AI4S/MASLD 为竞赛预设）
  HERMES_HOME=$HERMES_HOME
============================================================
  对话（默认，进入 Hermes 后再输入）:
    bash scripts/start_agent.sh
  切换 Provider:
    hermes chat --provider volcengine-plan
    hermes chat --provider volcano-anthropic
    hermes model
  Skills（已导入 skill manager）:
    ddfast 00–10 | drug-design×20 | writing×10 | masld-ai4s 自写
    hermes skills list | rg 'ddfast|drug-design|writing|masld'
    python scripts/import_drug_skills.py
  科学管线 CLI:
    bash scripts/start_agent.sh shell
    masld-agent offline-demo | run | evaluate-target
    masld-agent platform-health | platform-catalog | diffdynamic-status | schrodinger-status
  人设文件: config/SOUL.md → .hermes/SOUL.md
  平台目录: config/platform/ → .hermes/PLATFORM.md + platform/catalog.yaml
  启动横幅: config/skins/edrug-scientist.yaml (SCIENTIST + e-drug-lab)
============================================================
BANNER

case "$MODE" in
  chat|dialogue|对话|"")
    if ! command -v hermes >/dev/null 2>&1; then
      echo "ERROR: hermes not on PATH. Run: pip install -e ./vendor/hermes-agent" >&2
      exit 1
    fi
    exec hermes chat "$@"
    ;;
  shell|bash|sh)
    echo "[ready] venv + HERMES_HOME set — use masld-agent … or hermes chat"
    exec bash --noprofile --norc -i
    ;;
  sync)
    echo "Sync done."
    ;;
  *)
    echo "Unknown mode: $MODE (use chat|shell|sync)" >&2
    exit 2
    ;;
esac
