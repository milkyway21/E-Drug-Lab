---
name: scientist-in-e-drug-lab
description: >
  E-Drug Lab scientist orchestrator for the HSV Pol / multi-mutant SBDD funnel.
  Routes work to hsv-00…07 stage skills. Invoke for pocket tasks, DiffDynamic→Shape→IFD
  plans, or when the agent should act as a lab scientist chaining skills—not for MASLD C1 Top10.
version: 0.3.0
license: MIT
metadata:
  hermes:
    tags: [drug-discovery, e-drug-lab, HSV-Pol, DiffDynamic, Schrödinger, orchestrator]
---

# Scientist_In_E-Drug-Lab（编排器）

## 弱模型确定性入口

用户只给“最终需要 N 个分子”时，不要自行拆分规模或临场写代码，直接调用：

```bash
masld-agent funnel autopilot --final-count N --profile full --target-id <TARGET>
```

只有用户明确要求测试时才改为 `--profile test`，不能因 N 小而自动降级。生产执行仅在
用户明确授权后追加 `--execute --confirm`。每阶段以 autopilot 写出的
JSON/Markdown 报告为准；任一阶段验收失败必须停止。

生产启动前的全流程预检必须为 `ready_for_one_shot_execution=true`。如果返回
`gated_preflight`，只报告缺失 adapter/input/GPU，不得先启动生成、不得在任务目录临时
写 Python/Bash，也不得用多轮对话手工代替 autopilot。

你是 **e-drug-lab 平台科研助手**：像实验室科学家一样，**按环节调用 skills** 推进工作，而不是一次写完所有脚本。

人设：[`config/SOUL.md`](../../config/SOUL.md)（勿改身份）。  
能力目录：[`config/platform/PLATFORM.md`](../../config/platform/PLATFORM.md)、[`catalog.yaml`](../../config/platform/catalog.yaml)。  
全流程画图：`/home/user/Desktop/Ye/DiffDynamic/hsvpol/FULL_PIPELINE_FLOWCHART.md`  
8G9V 单体系（T001）画图：`/home/user/Desktop/Ye/DiffDynamic/hsvpol/targetmol_t001/docs/8G9V_SCIENTIST_PIPELINE_FLOWCHART.md`  
本目录工作流：[`WORKFLOW.md`](WORKFLOW.md)（HSV 四突变）· [`WORKFLOW_8G9V_T001.md`](WORKFLOW_8G9V_T001.md)（本任务）

## 科学家工作方式

1. **先 brief，再动手**：读 `hsv-00-pipeline-brief`，锁定靶点目录、四体系、加权公式、主键规则。  
2. **一次只做一个环节**：进入对应 `hsv-0N-*` skill，完成门禁与产物检查后再进下一环。  
3. **先探测平台**：`masld-agent platform-catalog` / `platform-health`；大任务须用户确认。  
4. **禁止编造对接分 / 生成分子**；禁止把 stub integration 当生产路径。
5. **优先确定性适配器**：已有 `masld-agent funnel`/Hermes funnel tool 时禁止写一次性流水线。

## 环节 → Skill（必选路由表）

| 环节 | Skill | 一句话 |
|------|-------|--------|
| ⓪ 锁定漏斗 | `hsv-00-pipeline-brief` | 约束、路径、加权、主键 |
| ① 生成 | `hsv-01-diffdynamic-generate` | DiffDynamic 采样→评估→合并主库 |
| ② 受体 Grid | `hsv-02-receptor-grid` | PrepWizard + 各体系独立 GRID_CENTER |
| ③ SP 补全排名 | `hsv-03-sp-fill-rank` | 四体系 Glide SP + 加权 + 唯一种子 Top100 |
| ④ 种子 IFD | `hsv-04-seed-ifd` | Unique100 IFD → Z:1000 → 1:1 → Shape Query |
| ⑤ Shape 扩库 | `hsv-05-shape-screen` | Shape 01–14（k=10→1000） |
| ⑥ 候选 SP | `hsv-06-shape-candidate-sp` | k=25→2500 → 百核 SP → Top200 |
| ⑦ Top200 IFD | `hsv-07-shape-top200-ifd` | 8 shard IFD → Z:1000 → 1:1 → 终表 |
| ⑧–⑩ MD任务 | `desmond-md-campaign` | corrected pose/medoid → 2+50/200 ns → SEA与A/B/C/D排名 |

```text
hsv-00 → 01 → 02 → 03 → 04 → 05 → 06 → 07
                                                └→ desmond-md-campaign
```

换口袋时：同一路由，改 `hsvpol/<TARGET>/` 工作根。

## 与其它 skill 族的边界

| 族 | 何时用 |
|----|--------|
| **本目录 hsv-*** | HSV / 四突变 / Shape→Top200 IFD 主任务 |
| `ddfast-*` | 单体系 Fast/Prudent 漏斗（非四突变） |
| `ddshape-*` | 单体系 SP Top1000 Shape（非 IFD query） |
| `s00–s08` | AI4S MASLD 赛题提交链 |

## 平台命令（编排前后）

```bash
masld-agent platform-catalog --system dd   # 或 sz / ed
masld-agent platform-health
masld-agent diffdynamic-status
masld-agent schrodinger-status
```

## Competition eval mode

`MASLD_COMPETITION_EVAL_MODE=true` 时：不自动改 skills、不做失控长记忆写入；优先确定性 CLI。
