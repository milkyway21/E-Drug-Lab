# e-drug-lab Agent Memory

This folder is the persistent memory store for the Claude agent working on the
`e-drug-lab` project. Each `.md` file captures one topic so context survives
across sessions. Add new files as knowledge accumulates; update existing ones
rather than duplicating.

## Index

- [allin-multimodal-fix-audit.md](allin-multimodal-fix-audit.md) — **ALLIN 多模态修复审计冻结**（docx 对照缺口；代码准备 vs 等 SP）。
- [project.md](project.md) — **项目现状 + 数据地图真源**（ALLIN=`ginl_pc_gl` 主线路径、对接覆盖、特征表、缺口/待办）。找东西先读这个。旁路入口：`binding_RL/PROJECT.md`、`ALLIN/docs/project.md`。
- [glare-multimodal-rl-status.md](glare-multimodal-rl-status.md) — **残差多模态落地状态**；**ALLIN 命名**=`ginl_pc_gl`（图+理化+Glide SP 三类联合，E47–E52 数字）。
- [data-storage-binding-rl.md](data-storage-binding-rl.md) — **Glide / MD / 101D 列级详表**（`binding_RL` + `features_v1` + round2/3 docking + `PAT_training_database_101D.csv`），含 QC 与列清单。
- [project-structure.md](project-structure.md) — full repo layout, runtimes,
  routes, data model, and current status. **平台总览先读这个。**
- [env-and-tool-runtime.md](env-and-tool-runtime.md) — 五个工具的 conda 环境与调用方案、关键事实、既有 bug。
- [rl-path.md](rl-path.md) — GLARE 强化学习闭环链路、状态管理、Task 6 路径修复、端到端验证记录。
- [workflow-diffgui-glare-wetlab.md](workflow-diffgui-glare-wetlab.md) — DiffGUI生成→GLARE筛选→湿实验反馈 完整实验流程操作手册。
- [diffgui-vav1-eval-pipeline.md](diffgui-vav1-eval-pipeline.md) — VAV1 DiffGUI生成+correct-reconstruct评估链路、8个vendored bug修复、round_100结果。
- [round200-production-run.md](round200-production-run.md) — round_200 双卡10000分子生产任务（GPU1+2,batch_size=8,exhaustiveness=8 dock）、batch_lab索引bug+显存O(N²)分析、驱动/进度脚本。
- [round200-checkpoint.md](round200-checkpoint.md) — round_200 生成断点（GPU1/2各跑到run_009,共923分子,下次--start_run 10续跑）、stop_guard逻辑缺陷、评估分析进行中。
