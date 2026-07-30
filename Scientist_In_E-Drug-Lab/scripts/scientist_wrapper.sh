#!/usr/bin/env bash
# User-facing wrapper: `scientist chat` → hermes chat (no Hermes branding in help text).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export SCIENTIST_ROOT="$ROOT"

scientist() {
  local cmd="${1:-chat}"
  shift || true
  case "$cmd" in
    chat|对话)
      exec bash "$ROOT/scripts/start_agent.sh" chat "$@"
      ;;
    shell|sh)
      exec bash "$ROOT/scripts/start_agent.sh" shell "$@"
      ;;
    sync)
      exec bash "$ROOT/scripts/start_agent.sh" sync "$@"
      ;;
    help|-h|--help)
      cat <<EOF
E-Drug Lab Scientist — 药物发现科研助手

  scientist chat [hermes args…]   启动对话（内部 hermes chat）
  scientist shell                 进入 masld-agent CLI 环境
  scientist sync                  同步 provider / SOUL / skills

任务记忆: \$SCIENTIST_ROOT/memory/MAIN_PLAYBOOK.md
EOF
      ;;
    *)
      echo "Unknown: $cmd (try: scientist chat|shell|sync)" >&2
      return 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  scientist "$@"
fi
