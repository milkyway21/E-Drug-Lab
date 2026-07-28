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

启动时 `scripts/import_drug_skills.py` 会把本地 skills **symlink 进** `$HERMES_HOME/skills/`，供 Hermes Skill Manager 发现与调用：

| 分类 | 数量 | 内容 |
|------|------|------|
| `ddfast/` | 11 | DiffDynamic-Fast 漏斗 00–10 全套 |
| `drug-design/` | 20 | DiffDynamic / 对接 / RDKit / PubChem 等专项 |
| `writing/` | 10 | Nature 写作 / 润色 / 图表 / 文献 |
| `masld-ai4s/` | 10 | s00–s08 + `scientist-in-e-drug-lab` 自写 |

```bash
python scripts/import_drug_skills.py
HERMES_HOME=$PWD/.hermes hermes skills list | rg 'ddfast|drug-design|writing|masld'
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

## 管线 CLI（非对话）

```bash
bash scripts/start_agent.sh shell
masld-agent offline-demo --fixture tests/fixtures/hsd17b13 --output runs
masld-agent run --top-targets 10 --output runs/demo
```
