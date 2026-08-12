# E-Drug Lab Competition Skills

这是按整体流程图整理的实体技能目录，所有文件均为真实复制文件，不包含符号链接。

目录顺序对应流程图：

1. `01_drug-discovery-orchestrator`：总流程编排、任务记忆、汇报与时间调度
2. `02_target-discovery`：靶点生物学、结构、口袋和原生蛋白-配体准备
3. `03_dd-generation`：DiffDynamic 分子生成
4. `04_virtual-docking`：Glide SP/XP 与 MMGBSA
5. `05_featurehit-finding`：姿势、药效团、形状筛选和分子特征
6. `06_admet`：ADMET、毒性和证据补充
7. `07_molecular-dynamics`：Desmond 分子动力学及分析
8. `08_all-analysis`：候选提名、机制论证和总分析报告

每个主目录下的子目录保留项目现有 skill 名称，并包含对应的 `SKILL.md`、脚本、参考资料和元数据。

## 通用调用

每个主类和子 skill 的 `SKILL.md` 都包含 `Universal Manifest Invocation`，统一使用
Agent 项目根目录的入口：

```bash
bash scripts/run_skill.sh --skill SKILL_NAME --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill SKILL_NAME --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill SKILL_NAME --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill SKILL_NAME --manifest MANIFEST --resume --execute --confirm
```

Manifest 必须显式声明输入、输出、资源、验证、报告以及 `command` 或 `steps`；不会根据
靶点名称猜测受体、配体、口袋、GPU、筛选阈值或模拟时长。`config/skill_manifests/`
中的模板展示通用契约和 DiffDynamic Prudent 的直接入口。

Manifest 是 Agent 的默认编排入口，不是共享 skill 的唯一入口。每个 `SKILL.md` 还包含
`Standalone Command-Line Procedure`：

1. 项目用户可用无 manifest 的 `masld-agent` 命令直接规划、查询和运行阶段。
2. 不使用 Agent 适配器时，可按 skill 中的环境变量和原生命令执行，例如
   `python sample_diffusion.py ...`、`glide grid.in`、`glide dock.in`、`qikprop input.sdf`
   和 `multisim -m protocol.msj system.cms`。
3. Schrödinger/DiffDynamic 的安装位置优先由 `platform-resolve` 注册表解析；完全独立
   使用时才由调用者设置 `SCHRODINGER`、`DD_ROOT`、`DD_PYTHON` 等变量。

因此，manifest 负责自动编排、计数和资源分配；standalone 段落负责公开、可迁移的
原生操作方法。两者共享同一输入格式、验证门、稳定 ID、日志和报告契约。

## 注册表优先

技能正文只引用注册表 ID，不写本机安装目录。每次执行前先查询能力，再解析当前环境：

```bash
masld-agent platform-catalog --system dd
masld-agent platform-catalog --system sz
masld-agent platform-resolve --id dd.env --field python
masld-agent platform-resolve --id sz.bin.glide
masld-agent platform-health
```

Hermes 中对应工具为 `platform_catalog` 和 `platform_resolve`。注册表负责当前机器的
DiffDynamic、Schrödinger 和 e-drug-lab 位置；技能只使用返回值填充 `DD_PYTHON`、
`RUN`、`GLIDE`、`MULTISIM` 等变量。

核心方法已经写入现有 skill：靶点证据与结构/配体清理、DiffDynamic 生成和
`--vina-modes none` 理化分析、Glide SP/XP/MMGBSA、姿势提取、Shape/Phase/Morgan
特征筛选、Desmond 短/长 MD、SEA、轨迹验证、恢复和结果解释。目录只发布八类通用
流程技能，不新增重复 skill 名称。
