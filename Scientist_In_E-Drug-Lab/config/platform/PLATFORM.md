# E-Drug Lab platform knowledge

This file is **platform capability knowledge** for Scientist_In_E-Drug-Lab.
It does **not** change agent identity (see `config/SOUL.md`: cross-disease drug discovery).

## Three systems

| System | Role | Prefer invoke via |
|--------|------|-------------------|
| **DiffDynamic** | Pocket-conditioned molecule generation | e-drug-lab `DiffDynamicRunner` → conda `diffdynamic` |
| **e-drug-lab backend** | Service wrappers + Affinity APIs | Library import (HTTP optional / often down) |
| **Schrödinger** | PrepWizard / LigPrep / Grid / Glide / QikProp / MMGBSA / IFD / Desmond | `schrodinger_service` → `/opt/schrodinger2023-3` |

Authoritative machine catalog: [`catalog.yaml`](catalog.yaml). Query with:

```bash
masld-agent platform-catalog
masld-agent platform-health
```

## Final-count-only autopilot

用户只提供最终分子数时，Agent 不需要自行决定中间规模：

```bash
# 规划、资源探测、既有产物验收和全阶段报告；不提交计算
masld-agent funnel autopilot --final-count 10 --profile full --target-id HSD17B13

# 只有明确测试时使用小规模配置
masld-agent funnel autopilot --final-count 2 --profile test --target-id HSD17B13

# 用户确认后启动持久监督进程
masld-agent funnel autopilot --final-count 10 --profile full --target-id HSD17B13 \
  --execute --confirm --background

# 读取当前阶段及最新报告
masld-agent funnel autopilot-status --target-id HSD17B13
```

对应 Hermes 工具：`funnel_autopilot`、`funnel_autopilot_status`。生产执行默认后台；
每阶段写 `reports/funnel/<profile>/H*.json` 与 `.md`，验收失败即停止。
`full` 是只给最终数量时的默认；`test` 不得因最终数量较小而自动启用。

生产 worker 启动前会对所有启用阶段做 whole-pipeline readiness preflight；仅当
`ready_for_one_shot_execution=true` 才会开始 H1。`gated_preflight` 表示没有任何计算
启动，Agent 必须报告 `blocking_stages`，不得在任务目录临时编写替代脚本。

## Track H（HSD17B13 整体流程图）→ **master/child** skills

规格：`/data/ye/整体流程图_三轮理解.md`  
映射：`hsvpol/.trae/skills/FUNNEL_SKILL_MAP.md`  
默认入口：`drug-discovery-orchestrator`；执行子技能：`funnel-orchestrator`

| Step | skill_ref | 计划规模 |
|------|-----------|----------|
| H0 | `drug-discovery-orchestrator` → `target-discovery` | gate |
| H1a/b | `dd-generation` → `funnel-diffdynamic-denovo` / `funnel-diffdynamic-prudent` | ~50万→~4万 |
| H2 | `virtual-docking` → `funnel-glide-sp` | ~1000 |
| H3 | `featurehit-finding` → `funnel-featurehit` / `funnel-shape-screen` | ~3000 |
| H4 | `admet` → `funnel-drugflow-hepg2` / `ddfast-06-qikprop-admet` | 显式后端，禁止冒充 |
| H5–H7 | `virtual-docking` → SP / XP / MMGBSA | ~500/~130/~40 |
| H8–H9 | `molecular-dynamics` → `funnel-desmond-short-md` / `funnel-desmond-long-md` | ~20/~10 |
| H10 | `all-analysis` → `funnel-comprehensive-analysis` | Top10 |

旧 `ddfast-*` / `featurehit-shape-expand` 等已 superseded，仅兼容别名。

## Hard rules

1. **Never invent** docking scores, generated structures, or ADMET numbers.
2. **DiffDynamic input PDB** = original receptor (not PrepWizard mae). PrepWizard output is for Glide.
3. **Large jobs** (batch≥100, full Glide funnel) require explicit `confirm=true`.
4. **Do not** use `backend/app/api/integrations/*` remote stubs as production.
5. DDFast classic order (Track A): gate → denovo/scaffold → extract → dedup → QikProp → SP → XP → MMGBSA/IFD → rank.
6. Track **H** inserts FeatureHit/Shape expand + HepG2 before refine docking; MD after MMGBSA; ends at `all-analysis` (not a legacy ddfast ranker).
7. Schrödinger: absolute paths; LigPrep `-nt` ≠ threads; IFD **1:1 only** (no N×N).
8. GPU policy for DDFast sampling: prefer GPUs **1–5**, split seeds to avoid OOM; smoke on **GPU0**.

## Quick env

```bash
# DiffDynamic
conda activate diffdynamic
export PYTHONPATH=/data/ye/DiffDynamic:$PYTHONPATH
cd /data/ye/DiffDynamic

# Schrödinger
export SCHRODINGER=/opt/schrodinger2023-3
# optional large temp:
# export SCHRODINGER_TEMPDIR=/data/.../schrodinger_tmp
```

## When unsure

Call `platform-catalog --id <id>` or `--system dd|ed|sz` before proposing commands.
