#!/usr/bin/env bash
# Launch Scientist_In_E-Drug-Lab via Hermes multi-provider chat (Claude-Code-like).
# Usage:
#   bash scripts/start_agent.sh              # hermes chat (default)
#   bash scripts/start_agent.sh chat         # same
#   bash scripts/start_agent.sh shell        # bash with masld-agent CLI
#   bash scripts/start_agent.sh sync         # refresh provider config from templates
# Extra args after mode are forwarded to hermes chat, e.g.:
#   bash scripts/start_agent.sh chat --provider openai-relay
#
# Credentials (never commit):
#   export OPENAI_API_KEY=...
#   export OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
#   # or put them in .env / .hermes/.env after copying .env.example
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

# Optional local .env (gitignored)
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export HERMES_HOME="${HERMES_HOME:-$ROOT/.hermes}"
export MASLD_COMPETITION_EVAL_MODE="${MASLD_COMPETITION_EVAL_MODE:-true}"
export PYTHONPATH="$ROOT/src:${PYTHONPATH:-}"
export HERMES_ENABLE_PROJECT_PLUGINS="${HERMES_ENABLE_PROJECT_PLUGINS:-true}"
unset ANTHROPIC_API_KEY ANTHROPIC_BASE_URL ARK_API_KEY MASLD_LLM_API_KEY MASLD_LLM_BASE_URL 2>/dev/null || true

export HERMES_INFERENCE_PROVIDER="${HERMES_INFERENCE_PROVIDER:-openai-relay}"
export HERMES_INFERENCE_MODEL="${HERMES_INFERENCE_MODEL:-gpt-5.6-sol}"
export HERMES_MODEL_CONTEXT_LENGTH="${HERMES_MODEL_CONTEXT_LENGTH:-1050000}"
export HERMES_REASONING_EFFORT="${HERMES_REASONING_EFFORT:-xhigh}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://your-openai-compatible-endpoint/v1}"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "WARNING: OPENAI_API_KEY is unset. Copy .env.example → .env and fill keys before chat." >&2
fi

MODE="${1:-chat}"
if [[ $# -ge 1 ]]; then
  shift
fi

python "$ROOT/scripts/sync_providers_from_ccswitch.py" \
  --hermes-home "$HERMES_HOME" \
  --skip-ccswitch \
  --strip-provider-env \
  --prune-unlisted-providers \
  --activate-provider "$HERMES_INFERENCE_PROVIDER" \
  --model "$HERMES_INFERENCE_MODEL" \
  --context-length "$HERMES_MODEL_CONTEXT_LENGTH" \
  --reasoning-effort "$HERMES_REASONING_EFFORT"
python "$ROOT/scripts/import_drug_skills.py" --hermes-home "$HERMES_HOME" --check

cat <<BANNER
============================================================
  E-Drug Lab Scientist  |  药物发现科研助手
  跨靶点/跨疾病；AI4S/MASLD 仅为竞赛预设
  任务记忆: memory/MAIN_PLAYBOOK.md + targets/<id>/CAMPAIGN.md
  HERMES_HOME=$HERMES_HOME
  模型来源: $HERMES_INFERENCE_PROVIDER
  推理模型: $HERMES_INFERENCE_MODEL
  推理强度: $HERMES_REASONING_EFFORT
  上下文窗口: $HERMES_MODEL_CONTEXT_LENGTH tokens
  OPENAI_BASE_URL: $OPENAI_BASE_URL
============================================================
  对话:
    bash scripts/start_agent.sh
  Skills（funnel + 精简 ddfast/drug-design/campaign）:
    python scripts/import_drug_skills.py
    hermes skills list | rg 'funnel|ddfast|drug-design|campaign'
  科学管线 CLI:
    bash scripts/start_agent.sh shell
    masld-agent funnel autopilot --final-count N --profile full --target-id TARGET
  人设: config/SOUL.md → .hermes/SOUL.md
  网页浮窗: frontend ScientistFloat → backend /api/v1/agent/*
============================================================
BANNER

case "$MODE" in
  chat|dialogue|对话|"")
    if ! command -v hermes >/dev/null 2>&1; then
      echo "ERROR: hermes not on PATH." >&2
      echo "  mkdir -p vendor && git clone --depth 1 https://github.com/NousResearch/hermes-agent.git vendor/hermes-agent" >&2
      echo "  pip install -e ./vendor/hermes-agent" >&2
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
