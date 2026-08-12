# Hermes 集成（多 Provider 对话）

Scientist_In_E-Drug-Lab **不自研 LLM 路由**。对话与换 API 走 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 官方 runtime（与 Claude Code CLI 同级：Anthropic / OpenAI 兼容 / OpenRouter / 命名 custom provider…）。

本包只提供确定性科学工具（Plugin / Skill / MCP）。

## 一次性安装

```bash
cd /data/ye/e-drug-lab/Scientist_In_E-Drug-Lab
source .venv/bin/activate
pip install -e ".[dev]"
pip install -e "./vendor/hermes-agent"
```

## 启动对话

```bash
bash scripts/start_agent.sh
# 等价：同步 CC-Switch → .hermes 后
#   HERMES_HOME=$PWD/.hermes hermes chat
```

启动脚本会：

1. 调用 `scripts/sync_providers_from_ccswitch.py`（读 `~/.cc-switch` 当前「火山Agentplan」等 Claude provider）
2. 写入项目隔离的 `$PWD/.hermes/config.yaml` + `.hermes/.env`（**不进 git**）
3. 将 [`config/SOUL.md`](../config/SOUL.md) 同步为 `.hermes/SOUL.md`（**e-drug-lab 广义药物发现人设**；AI4S/MASLD 仅为竞赛预设）
4. 同步皮肤 [`config/skins/edrug-scientist.yaml`](../config/skins/edrug-scientist.yaml) → `.hermes/skins/`，并设置 `display.skin: edrug-scientist`（启动 ASCII 为 **SCIENTIST / E-Drug Lab**，非 Hermes 金杖）
5. 执行 `hermes chat`

## 切换 API / Provider

```bash
# 火山 Coding Plan — OpenAI wire（默认）
hermes chat --provider volcengine-plan

# 同一套 Coding Plan — Anthropic Messages wire
hermes chat --provider volcano-anthropic

# Hermes 内置 / 已配置凭据的其它厂商
hermes chat --provider anthropic
hermes chat --provider openrouter
hermes model   # 交互选择
```

配置模板：[`config/hermes.config.yaml`](../config/hermes.config.yaml)。

密钥只放在 `.hermes/.env` / 项目 `.env`，通过 `key_env` 引用。

手动同步（不进入对话）：

```bash
bash scripts/start_agent.sh sync
# 或
python scripts/sync_providers_from_ccswitch.py
```

## 本地技能包（药物设计 / 论文 / 自写）

启动时 `scripts/import_drug_skills.py` 会把本地 canonical skills **symlink 进**
`$HERMES_HOME/skills/<master>/<child>/`，供 Hermes Skill Manager 发现与调用；旧直属
名称只在项目源码中作为兼容别名，不会重复发布：

| 分类 | 数量 | 内容 |
|------|------|------|
| `drug-discovery-orchestrator/` | 7 | 默认入口、记忆、调度、报告和能力门控 |
| `target-discovery/` | 8 | 靶点、生物学、结构、配体和口袋证据 |
| `dd-generation/` | 2 | DiffDynamic de novo / Prudent |
| `virtual-docking/` | 4 | Glide SP / XP / MMGBSA |
| `featurehit-finding/` | 4 | FeatureHit / Shape / RDKit / 库筛选 |
| `admet/` | 4 | ADMET、证据和毒性分层 |
| `molecular-dynamics/` | 6 | Desmond MD 和 QC |
| `all-analysis/` | 3 | H10/E6 分析与机制报告 |

```bash
python scripts/import_drug_skills.py
HERMES_HOME=$PWD/.hermes hermes skills list | rg 'drug-discovery-orchestrator|target-discovery|dd-generation|virtual-docking|featurehit-finding|admet|molecular-dynamics|all-analysis'
```

清单：[`skills_pack/MANIFEST.json`](../skills_pack/MANIFEST.json)。

## MCP（工具）

项目 `.hermes/config.yaml` 已包含：

```yaml
mcp_servers:
  scientist_in_e_drug_lab:
    command: "python"
    args: ["-m", "masld_agent.mcp_server"]
    tools:
      include: ["masld_offline_demo", "masld_run"]
```

也可粘贴到全局 `~/.hermes/config.yaml`。

## Plugin entry-point

`pyproject.toml`:

```toml
[project.entry-points."hermes_agent.plugins"]
scientist_in_e_drug_lab = "masld_agent.hermes_plugin:register"
```

注册工具：`masld_offline_demo`、`masld_run_pipeline`；slash：`/masld-offline`。

## 评测模式

`config/competition_life_science.yaml` 与 Hermes 侧 `memory_enabled: false` / `disabled_toolsets: [memory]`：关闭不可控长期记忆写入。科学计算仍走 `masld-agent` 工具，不交给 LLM 编造。

## 结构化任务 Memory（替代 Hermes 原生 memory）

根目录：`memory/`

| 文件 | 用途 |
|------|------|
| `MAIN_PLAYBOOK.md` | **主流程** funnel 编排完整实现（= `funnel-orchestrator` 主记忆） |
| `GLOBAL_HISTORY.md` | 跨靶点简史 |
| `targets/<id>/CAMPAIGN.md` | 单靶点任务状态（文件名保持 `CAMPAIGN.md`） |
| `targets/<id>/DECISIONS.jsonl` | 追加式决策日志 |
| `targets/<id>/session.json` | CLI/网页共用 session 绑定 |

**开场必读**（`config/SOUL.md`）：`MAIN_PLAYBOOK` + `GLOBAL_HISTORY` + 当前 `CAMPAIGN`。

Agent 工具（Hermes plugin，非原生 memory toolset）：

- `campaign_memory_read` / `campaign_memory_write` / `global_history_append`
- Skill：`funnel-campaign-memory`

种子任务：`memory/targets/HSD17B13/CAMPAIGN.md`

## 网页浮窗 + BFF

产品 UI 为 e-drug-lab Next.js 浮窗，**不复用** Hermes 默认 Web UI。

| 组件 | 路径 |
|------|------|
| 浮窗 | `frontend/src/components/agent/ScientistFloat.tsx` |
| API 客户端 | `frontend/src/lib/agent-client.ts` |
| UI 命令总线 | `frontend/src/lib/agent-command-context.tsx` |
| BFF 路由 | `backend/app/api/routes/agent.py` |
| 网关 | `backend/app/services/hermes_gateway.py` |
| UI 白名单 | `Scientist_In_E-Drug-Lab/src/masld_agent/ui_command_bus.py` |

### 启动命令

```bash
# 终端 1 — 后端 BFF（默认 :8001）
cd /data/ye/e-drug-lab/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# 终端 2 — 前端浮窗（默认 :3001）
cd /data/ye/e-drug-lab/frontend
npm run dev

# 可选 — Hermes 独立服务（JSON-RPC/WS，默认 127.0.0.1:9119）
# 浮窗 BFF 通过 /api/ws 透传；须与 BFF 共享同一 session token：
cd /data/ye/e-drug-lab/Scientist_In_E-Drug-Lab
source .venv/bin/activate
export HERMES_DASHBOARD_SESSION_TOKEN=${HERMES_DASHBOARD_SESSION_TOKEN:-edrug-local}
HERMES_HOME=$PWD/.hermes hermes serve --skip-build --host 127.0.0.1 --port 9119

# BFF 进程同样设置（或 HERMES_SERVE_TOKEN）：
#   export HERMES_DASHBOARD_SESSION_TOKEN=edrug-local

# CLI 对话（非 BFF；也可作 live-cli 回退）
source scripts/scientist_wrapper.sh && scientist chat
```

BFF **不**把 `hermes serve` 的 WebSocket 直接暴露给浏览器；浮窗 = Hermes 界面映射，网关按优先级桥接：

1. **`live-serve`**：`hermes serve` 可达且 token 已配置时，经 `/api/ws` JSON-RPC（`session.create` / `prompt.submit`），流式透传 `message.delta` / `thinking.delta` / `tool.*`
2. **`live-cli`**：可恢复子进程 `hermes chat -Q -q --resume`（非空壳 stub）
3. **`ui-intent`**：纯导航/选靶薄适配（入队 UI 命令 + 短 ack），**不**替代 Hermes 任务回答
4. **`offline`**：Hermes 不可达时返回明确「Hermes 未连接」，**禁止**「【收到】…」回显冒充答案

每次 chat 响应与 `GET /memory/{target}` / `GET /bridge` 均带 `bridge_mode`；SSE 事件类型：`delta` / `thinking` / `tool` / `done` / `error`（及 `ui_command`）。

会话创建时注入 **MAIN_PLAYBOOK + GLOBAL_HISTORY + CAMPAIGN** 摘要（见 `hermes_gateway._build_memory_context`）。`memory_enabled` 保持 **false**，禁用 Hermes 原生 memory toolset。

### BFF 接口（`:8001`）

- `POST /api/v1/agent/session` — 创建会话（注入三层 memory 摘要）
- `GET /api/v1/agent/session/{id}` — 查询会话
- `POST /api/v1/agent/chat` — 同步回复（含 `bridge_mode`）
- `POST /api/v1/agent/chat/stream` — SSE 流式
- `GET /api/v1/agent/memory/{target_id}` — 只读 memory 预览（含 `bridge_mode`）
- `GET /api/v1/agent/ui-commands/{session_id}` — 拉取 UI 命令队列
- `POST /api/v1/agent/ui-commands` — 手动入队 UI 命令（调试）

### Smoke / 验收（curl）

```bash
BASE=http://127.0.0.1:8001

# 1. 创建会话
SID=$(curl -s -X POST "$BASE/api/v1/agent/session" \
  -H 'Content-Type: application/json' \
  -d '{"target_id":"HSD17B13"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['session']['id'])")

# 2. Memory 预览
curl -s "$BASE/api/v1/agent/memory/HSD17B13" | python3 -m json.tool | head

# 3. Chat（观察 bridge_mode: live-cli 或 stub）
curl -s -X POST "$BASE/api/v1/agent/chat" \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"message\":\"当前任务阶段？\"}"

# 4. UI 命令总线
curl -s -X POST "$BASE/api/v1/agent/ui-commands" \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"type\":\"navigate\",\"path\":\"/workflow\"}"
curl -s "$BASE/api/v1/agent/ui-commands/$SID"
```

验收标准：

- `bridge_mode` 在 hermes 可用时为 `live-cli` 或 `live-serve`（纯导航/选靶可为 `ui-intent`；不可达为 `offline`，**禁止**永久 stub 回显）
- memory 预览含 `main_playbook` / `global_history` / `campaign`
- `edrug_ui_start_task` 仅允许 `ui_command_bus.TASK_WHITELIST` 内路径
- 浮窗轮询 `ui-commands` 能消费 navigate / set_target / start_task
- SSE：`delta` / `thinking` / `tool` / `done` / `error`

### 实机验收（2026-07-30）

**环境**：`frontend :3001` + `backend :8001`；Chromium headless（puppeteer-core）点浮窗；`memory_enabled=false`。

| 项 | 结果 |
|----|------|
| curl：`chat`「打开 workflow」→ ~0.1s 入队 `navigate /workflow`（ui-intent-fast，不经 Hermes） | 通过 |
| curl：非法 `start_task` `/api/v1/admin/secret` | 通过（白名单拒绝） |
| 浏览器：FAB → 「当前漏斗主流程是什么」→ 回复含 H0–H10（playbook-fast stub） | 通过 |
| 浏览器：等发送钮空闲后「打开 workflow」→ URL `/workflow` | 通过 |
| 浏览器：非首页浮窗「打开 docs」→ `/docs` | 通过 |
| 浮窗 header 显示 `bridge_mode` | 通过 |

**实机验收（2026-07-30，Chromium + puppeteer-core）**：

| 用例 | 结果 |
|------|------|
| 首页 FAB 打开浮窗 | PASS |
| 「当前漏斗主流程是什么」→ H0–H10 / MAIN_PLAYBOOK | PASS（`bridge_mode=stub` playbook-fast，&lt;1s） |
| 「打开 workflow」→ `/workflow` | PASS（BFF 入队 + 浮窗解析 ack 直接 `router.push`） |
| 「打开 database」→ `/database` | PASS |
| curl 非法 `start_task` `/api/v1/admin/secret` | PASS（拒绝） |
| curl 合法 navigate 入队 | PASS |

**本次配合修复**：

- Float ↔ Provider：`setSessionId` + `onSessionSync` 双通道；开窗校验 session（清僵尸 ID）
- BFF：`_maybe_enqueue_ui_intents`；纯导航 / playbook 快路径；导航 stub 按路径区分；`HERMES_CHAT_TIMEOUT` 默认 25s
- 浮窗：回复含 `已入队 navigate → \`/path\`` 时立即 `router.push`（不单靠轮询）
- `AgentUiEffects`：消费 `highlight` / `start_task`；轮询 800ms 仍作备份

**已知限制**：

- 流式 `busy` 期间不可连发；须等发送钮恢复
- `highlight` 仅对页内已有 `[data-entity-id]` 生效
- 非 UI/playbook 意图仍可能走 `live-cli`（最长约 `HERMES_CHAT_TIMEOUT`），失败回 stub
- 路由跳转后浮窗 `open` 状态保留在 AppShell；若 UI 未显示输入框需再点 FAB
- cursor-ide-browser MCP 不可用时，用 Chromium + puppeteer-core 验收

### UI 桥工具（与 `edrug_bridge` 计算桥分离）

| 工具 | 作用 |
|------|------|
| `edrug_ui_navigate` | 白名单路由跳转 |
| `edrug_ui_highlight` | 高亮实体 |
| `edrug_ui_open_molecule` | 打开分子面板 |
| `edrug_ui_set_target` | 设置 workflow 靶点 |
| `edrug_ui_start_task` | 白名单 POST 已有领域 API（见 `ui_command_bus.py`） |

`edrug_ui_start_task` 白名单覆盖：`screening`、`pipeline`、`targets`、`libraries`、`admet`、`diffdynamic`、`affinity`、`molecules`、`ranking`、`wetlab`、`molecule-db`、`glare`、`drugclip`、`diffgui`、`tame-vs`、`vav1-rl`、`rl-rounds` 等路由下的安全 POST 端点；带路径参数的如 `/api/v1/pipeline/runs/{id}/resume` 通过前缀规则放行。

### 对外品牌

- Skin：`config/skins/edrug-scientist.yaml`（E-Drug Lab Scientist，无 Hermes 对外文案）
- 包装命令：`source scripts/scientist_wrapper.sh && scientist chat`

## 管线 CLI（非对话）

```bash
bash scripts/start_agent.sh shell
masld-agent offline-demo --fixture tests/fixtures/hsd17b13 --output runs
masld-agent run --top-targets 10 --output runs/demo
```
