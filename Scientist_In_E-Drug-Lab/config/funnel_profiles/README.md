# Funnel 数量配置表

`full` 是用户只给最终分子数时的默认正式配置；`test` 只能由用户或测试命令显式选择。
所有数字是计划目标，不是已完成结果。

每个阶段同时声明 `master_skill` 和兼容的 `skill`：前者用于 agent 主类路由，后者保留
现有 stage adapter、旧 manifest 和工具调用的子技能名称。新任务先加载
`drug-discovery-orchestrator`，再按 `master_skill` 读取对应主类和 `skill` 子技能。

## 测试配置（`test.yaml`，参考最终 2 个）

| 阶段 | H1A | H1B | H2 | H3 | H4 | H5 | H6–H7 | H8 | H9–H10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 目标数 | 0 | 100 | 10 | 30 | 5 | 2 | 0 | 2 | 0 |

测试链路为 Prudent → `--vina-modes none` 理化性质/去重 → Glide SP → 扩库 →
Schrödinger ADMET → refined Glide SP 精选 2 个 → 每个 10 ns。它只验证工具、资源、
续跑和报告能力。

## 完整配置（`full.yaml`，参考最终 10 个）

| 阶段 | H1A | H1B | H2 | H3 | H4 工作量 | H5 | H6 | H7 | H8 | H9 | H10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 目标数 | 500000 | 40000 | 1000 | 3000 | 3000 | 500 | 130 | 40 | 20 | 10 | 10 |

完整表严格对应 `/data/ye/整体流程图_三轮理解.md`。H8 为每个分子两条独立 50 ns，
H9 为每个分子 200 ns。H1B 后处理不运行 Vina，直接进入 H2 Glide SP；H4 按用户要求
固定使用 Schrödinger/QikProp 替代 DrugFlow，并在报告中保留真实后端名称。
