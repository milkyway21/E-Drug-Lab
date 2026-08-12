---
name: "edrug-capability-check"
description: "Run the project capability harness for platform APIs, registered agent tools, UI command routing, and MD dry-prep contracts. Use for capability checks, TOOL_CAPABILITY reports, environment diagnosis, or pre-task harness validation; it does not execute production science stages."
---

# E-Drug Capability Check

验证 Web API / Agent 插件 / UI 总线是否按契约工作。

## 运行

```bash
# Run from the Scientist_In_E-Drug-Lab project root.
.venv/bin/python scripts/capability_harness.py \
  --api-base http://127.0.0.1:8001 \
  --cases scripts/capability_cases/core.yaml \
         scripts/capability_cases/tool_matrix_templates.yaml
```

## 产出

- `memory/TOOL_CAPABILITY.md`
- `reports/capability_harness_<ts>.md`
- 可选：软追加 `memory/GLOBAL_HISTORY.md`

## 评分

`PASS | PARTIAL | GATE | FAIL`

- Desmond：`stub`/`假 completed` → **FAIL**
- `unavailable` / `gated` / template not-run-yet → **GATE**
- dry_prep completed（engine=schrodinger_desmond）→ **PASS**（≠ production）

## GATE 对人类含义

**GATE** = 待人类确认/补齐（confirm、路径、GPU/license、输入），**不是** agent「做不到」。
报表遇 GATE 时须列出人类需提供项，可继续部分（dry_prep、探针）先做。


## Harness 覆盖边界（必读）

| 已测 | 未测 |
|------|------|
| HTTP `POST/GET /api/v1/affinity/md` dry_prep | 真实 Hermes chat / LLM 会话 |
| Python `schrodinger_md_submit` / Hermes handler dry_prep | 执行 `funnel-desmond-*` / `dd-md-desmond` SKILL.md 正文 |
| Hermes `register()` 是否注册 MD tools | 生产 smoke/short（需 confirm + GPU/license） |
| skill 文件存在 + conda/`SCHRODINGER` 文档探针 | `conda activate` / `conda create`（Desmond **不需要**） |

## 环境：Desmond vs conda

- Desmond / `schrodinger_md_*`：使用已配置且可读的 **`$SCHRODINGER`**，**不要**为 MD 建 conda env，也不要硬编码安装路径。
- conda **`diffdynamic`**：仅 DiffDynamic；与 Desmond multisim 无关。

## 相关

- Agent tools: `schrodinger_md_submit`, `schrodinger_md_status`（`hermes_plugin`）
- Playbook: `memory/MAIN_PLAYBOOK.md` § capability check
- Skills: `funnel-desmond-short-md`, `funnel-desmond-long-md`, `dd-md-desmond`, `funnel-campaign-memory`
