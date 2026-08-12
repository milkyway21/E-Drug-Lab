# VAV1 / ALLIN 项目现状与数据地图

> **状态**：ALLIN（`ginl_pc_gl`）R0→R3 持续学习 + 三轮相似物排名已完成；库 1/2 Glide 覆盖不足，待审计后重排  
> **更新日期**：2026-08-01  
> **备份基线**：`/data/ye/glare-backup-20260723`（约 51G）  
> **实验真源**：[`backend/outputs/vav1_rl_project/reports/experiment_log.md`](../backend/outputs/vav1_rl_project/reports/experiment_log.md)

本文档是「东西在哪、现在跑到哪」的导航真源。详表下钻见 [`data-storage-binding-rl.md`](data-storage-binding-rl.md)；落地状态见 [`glare-multimodal-rl-status.md`](glare-multimodal-rl-status.md)。

---

## 0. 一句话目标与当前阶段

**目标**：在保留 GLARE RL / 持续学习闭环的前提下，用多模态策略（图 + 101D 理化 + Glide SP，可选 MD）做 VAV1 分子胶大库排序与湿实验反馈强化。

**当前阶段（2026-07-31 主线完成）**：

| 项 | 状态 |
|----|------|
| ALLIN 架构 `ginl_pc_gl` | ✅ 已落地（E50 专利测试 ROC≈0.831） |
| R0→R3 累积训练 + 三轮相似物排名 | ✅ 产出在 `validation/allin_pc_gl_progressive/` |
| 第三轮生成库 Glide SP（≤30 核） | ✅ ~9209 分子 |
| 第二轮实体 Glide | ✅ 19/19 |
| 生成库预计算 101D | ❌ 仅有专利级表；query 时多现场算 |
| 库 1 / 库 2 全库或相似物 Glide | ❌ query 时多为 `mask=0` |
| 审计后重排 `allin_pc_gl_rerank_v2` | ⏳ 待办 |

---

## 1. 命名铁律

| 名称 | 含义 | 是否可称 ALLIN |
|------|------|----------------|
| **`ginl_pc_gl`** | 图 GNN + 101D PhysChem + Glide SP | **是（ALLIN）** |
| `ginl_pc_gl_md` | ALLIN + MD 八体系 | 扩展，另称 |
| `ginl` / `ginl_pc` | 仅图 / 图+理化 | **否** |
| `validation/allin_progressive/` | 历史误跑：纯 `ginl` | **非 ALLIN 基线** |
| `validation/allin_pc_gl_progressive/` | ALLIN 持续学习主线 | **是** |

CLI：`glare_gnn_cli.py --architecture ginl_pc_gl`。

约束备忘：训练/query 时图与 101D **CRBN strip**；Glide / MD 特征 **不 strip**。

---

## 2. 根路径速查（找东西先看这里）

```text
$EDRUG     = /data/ye/e-drug-lab
$VAV1      = $EDRUG/backend/outputs/vav1_rl_project
$BINDING_RL = $VAV1/binding_RL
$VALIDATION = $VAV1/validation
$ALLIN     = /data/ye/ALLIN
$GLARE     = /data/ye/diffgui/third_party/GLARE
```

| 你想找 | 去哪 |
|--------|------|
| **本文 / 项目导航** | `$EDRUG/claude/project.md` |
| Glide / MD / 101D 详表 | `$EDRUG/claude/data-storage-binding-rl.md` |
| 实验流水账 | `$VAV1/reports/experiment_log.md` |
| 对接 + 特征 + 分轮 docking | `$BINDING_RL/`（旁路入口：`PROJECT.md`） |
| ALLIN 代码精简仓 | `$ALLIN/`（入口：`docs/project.md`） |
| 三轮生成库 / 实体 CSV·SDF | `$ALLIN/data/` |
| ALLIN 训练权重 + 排名 | `$VALIDATION/allin_pc_gl_progressive/` |
| 纯 ginl 误跑基线 | `$VALIDATION/allin_progressive/` |
| E43 持续学习对照 | `$VALIDATION/glare_e43_progressive/` |
| E47–E53 消融 | `$VALIDATION/glare_e47_e53_ablation/` |
| 专利 101D 原表 | `$VAV1/PAT_training_database_101D.csv`（388 行） |
| 合并 Glide 特征表 | `$BINDING_RL/features_v1/glide/allin_glide_feature_table.csv` |
| GLARE 网络本体 | `$GLARE/model.py` |
| VAV1 流水线 Python | `$EDRUG/backend/app/pipelines/vav1_rl/` |
| 改动前备份 | `/data/ye/glare-backup-20260723` |

数据盘约定：大文件一律在 `/data/ye`，勿占系统盘。

---

## 3. 代码入口

| 角色 | 路径 |
|------|------|
| ALLIN / GLARE CLI | `$EDRUG/backend/app/pipelines/vav1_rl/glare_gnn_cli.py` |
| PhysChem 101 | `.../physchem_101.py` |
| Glide 特征加载 | `.../glide_features.py`（可读 `ALLIN_GLIDE_TABLE`） |
| MD 特征 | `.../md_features.py` |
| CRBN strip | `.../crbn_strip.py` |
| ALLIN 持续学习驱动 | `$EDRUG/backend/scripts/run_allin_pc_gl_progressive.py`（副本：`$ALLIN/pipelines/`） |
| 纯 ginl 误跑脚本 | `$EDRUG/backend/scripts/run_allin_progressive_rl.py` |
| 构建合并 Glide 表 | `$BINDING_RL/features_v1/glide/build_allin_glide_table.py` |
| 第三轮对接编排 | `$BINDING_RL/round3_docking/scripts/`（`01_prepare_smi_shards.py` · `02_run_round3_docking.py` · `03_fast_vav1_contacts_round3.py`） |
| 第二轮实体对接 | `$BINDING_RL/round2_entity_docking/scripts/` |
| 消融 E47–E53 | `$EDRUG/backend/scripts/run_e47_e53_ablation.py` |
| Conda（GLARE 训练） | `diffgui_new`（`/home/user/anaconda3/bin/conda`） |

Glide 资源约束：**≤30 核**（实践：`--parallel 1 --host localhost:30`）。

---

## 4. 数据目录树（精简）

### 4.1 `$BINDING_RL` — 对接 / MD / 特征

```text
binding_RL/
├── PROJECT.md                 # 本目录旁路入口（指向本文件）
├── README_zh.md               # DrugFlow 去重说明（历史）
├── docking/                   # DrugFlow ~1.16 万 Glide SP + 格点
├── patent_docking/            # 专利 403/403
├── wetlab_docking/            # wetlab 13/13
├── round2_entity_docking/     # 第二轮实体 19 Glide
├── round3_docking/            # 第三轮生成库 Glide（~9209）
├── MD_information/            # 八体系 MD + 发布树
├── features_v1/
│   ├── glide/                 # allin_glide_feature_table.csv 等
│   ├── physchem/              # 专利级 strip/scaled 101D（非生成库）
│   ├── md/                    # md8_molecule_features.*
│   └── strip_qc/
├── patent_screening/          # 衍生筛选表
├── DrugFlow_jobs_unique.csv / *.sdf
└── 9nfr.pdb · scaffold …
```

详列与 QC：[`data-storage-binding-rl.md`](data-storage-binding-rl.md)。

### 4.2 `$ALLIN/data` — 业务分子与三轮库

| 资产 | 路径（相对 `$ALLIN/data/`） | 约行数 / 规模 |
|------|------------------------------|---------------|
| 第一轮生成库 | `第一轮生成分子库.csv` | ~13586 |
| 第二轮生成库 | `第二轮生成分子库.csv` | ~10242 |
| 第三轮生成库 | `第三轮生成分子库.csv` | ~9214 |
| 第一轮实体 | `第一轮分子生成15个实体分子/` | 湿实验相关实体 SDF |
| 第二轮实体 | `第二轮动力学指导的分子生成/` | 含 19 实体等 |
| 第三轮实体 | `第三轮限制范围的分子生成/` | 限制范围实体 |
| 专利 / 合成库 | `01-MGDs-Patent-DataBase*` · `00-MGDs-Synthesis-DataBase/` | — |
| 标签表等 | `DataSet-GNN-SMILES-pDC50.xlsx` 等 | — |

库 CSV 常带 MolFactory 列（MW/TPSA/LogP/CarsiScore 等），**不等于** ALLIN 冻结 101D。

### 4.3 `$VALIDATION` — 实验产物

| 目录 | 含义 |
|------|------|
| `allin_pc_gl_progressive/` | **ALLIN 主线**：`model_R{0..3}.pt`、`dataset_R*.json`、`ranks/`、`RANK_SUMMARY.md` |
| `allin_progressive/` | 纯 `ginl` 误跑基线（勿当 ALLIN） |
| `glare_e43_progressive/` | E43 持续学习（图为主） |
| `glare_e47_e53_ablation/` | 消融；E50=`ginl_pc_gl` |
| `glare_e32_*` / `glare_e33_*` | 历史论文 / 全专利实验 |

---

## 5. 特征表真源

| 模态 | 真源路径 | 覆盖范围 | 备注 |
|------|----------|----------|------|
| Glide SP（合并） | `$BINDING_RL/features_v1/glide/allin_glide_feature_table.csv` | ~9644 行（含 DrugFlow + 专利 + wetlab + R3 等 merge） | `glide_features.py` keep=last by `molecule_id` |
| Glide 构建脚本 | `.../glide/build_allin_glide_table.py` | — | 改对接结果后需重建 |
| PhysChem 101（专利） | `$VAV1/PAT_training_database_101D.csv` | **388 行** | 原始 |
| PhysChem strip/scaled | `$BINDING_RL/features_v1/physchem/` | 专利级 | **生成库 1/2/3 无此预计算表** |
| MD 八体系 | `$BINDING_RL/features_v1/md/md8_molecule_features.csv` | 8 systems | 另有 parquet / scaler / QC |

第三轮原始对接结果：`$BINDING_RL/round3_docking/results/glide_sp_docking_results.csv`。  
第二轮实体：`$BINDING_RL/round2_entity_docking/results/glide_sp_docking_results.csv`。

---

## 6. ALLIN 训练与排名产物

**目录**：`$VALIDATION/allin_pc_gl_progressive/`（约 558M）

| 文件 / 子目录 | 说明 |
|---------------|------|
| `model_R0.pt` … `model_R3.pt` | `architecture=ginl_pc_gl`，`use_glide=True` |
| `dataset_R0.json` … `dataset_R3.json` | 含 `molecule_id`；R0≈专利 352；+R1 13；+R2 19；+R3 6 |
| `query_lib_round{1,2,3}.json` | 各轮大库 query 缓存 |
| `ranks/rank_round{1,2,3}.csv` | 相似物名次明细 |
| `RANK_SUMMARY.md` | 活性 vs 非活性相似物均值名次摘要 |
| `similarity/` · `logs/` | 相似检索与日志 |

**排名摘要（摘自 RANK_SUMMARY，仅供定位；以文件为准）**：

| 轮次 | 模型→库 | 活性相似物均值名次 | 非活性均值名次 |
|------|---------|-------------------|----------------|
| R1 | R0→库1 | #11338 | #10872（非活性略好） |
| R2 | R1→库2 | #5840 | #4796（非活性更好） |
| R3 | R2→库3（有 Glide） | #7164 | #7563（活性略好） |

注意：专利 held-out ROC（E50≈0.831）**不能**直接等同于「未标注生成库上的 Tanimoto 邻居排名好坏」。

---

## 7. 对接覆盖一览

| 集合 | 路径 | 规模 | 状态 |
|------|------|------|------|
| DrugFlow 大库 | `$BINDING_RL/docking/` | ~11659/11682 | ✅ |
| 专利 403 | `$BINDING_RL/patent_docking/` | 403/403 | ✅ |
| wetlab 13 | `$BINDING_RL/wetlab_docking/` | 13/13 | ✅ |
| 第二轮实体 | `$BINDING_RL/round2_entity_docking/` | 19/19 | ✅ |
| 第三轮生成库 | `$BINDING_RL/round3_docking/` | ~9209 unique | ✅ |
| 第一/二轮生成库全库或相似物子集 | — | — | ❌ 待补（计划：相似物子集 ≤30 核） |

共用格点：`$BINDING_RL/docking/grid/9nfr_grid.zip`。

---

## 8. 已知缺口（找问题先看）

1. **生成库无预计算 ALLIN 101D**：`features_v1/physchem/` 与 `PAT_training_database_101D.csv` 只覆盖专利量级；库 1/2 query 时 101D 多为现场计算，未落盘缓存。  
2. **库 1/2 Glide 缺失**：ALLIN 前两轮大库排序时 Glide 通道大量 `mask=0`；仅 R3 库有较完整对接。  
3. **库 CSV 理化列 ≠ 101D**：MolFactory 的 MW/TPSA/LogP/Carsi 等不是冻结 101 维向量。  
4. **命名坑**：`allin_progressive/` 目录名带 allin，实为纯 `ginl`。  
5. **评估语义**：专利 ROC 高 ≠ 生成库相似物排名分离好。

---

## 9. 待办（下一刀）

1. **（等 SP）** 库 1/2 Glide 齐套 → 并入 `allin_glide_feature_table` → progressive 实跑 / 覆盖率收紧。  
2. 写 `MODALITY_AUDIT.md`：实验记录 / 库 CSV / 101D 表 / Glide 覆盖对照。  
3. 预计算并缓存第 1/2/3 轮库 ALLIN 101D。  
4. 代码准备已落地：见 [`allin-multimodal-fix-audit.md`](allin-multimodal-fix-audit.md)（anchor / schema / learnable_gate / MD CLI）。  
5. 重排到新目录 `$VALIDATION/allin_pc_gl_rerank_v2/`（**不覆盖**现有 progressive）— 需 SP 后执行。

---

## 10. 立项目标摘要（历史，仍有效）

保留 GLARE 闭环，融合 PhysChem（+ 可选 MD），在 experiment.md 可比协议下优于旧最佳。成功标准与旧坑见历史简报逻辑（E13 假收敛、禁止 Vina 伪负、防泄漏、勿跨池裸比 rank）。消融锚点：E48–E52（见 `glare-multimodal-rl-status.md`）。

工作流文档：[`workflow-diffgui-glare-wetlab.md`](workflow-diffgui-glare-wetlab.md) · [`rl-path.md`](rl-path.md)。

---

## 11. 相关文档索引

| 文档 | 内容 |
|------|------|
| [`data-storage-binding-rl.md`](data-storage-binding-rl.md) | Glide / MD / 101D 列级详表与 QC |
| [`glare-multimodal-rl-status.md`](glare-multimodal-rl-status.md) | 残差多模态落地 + ALLIN 命名 + E47–E52 |
| [`project-structure.md`](project-structure.md) | e-drug-lab 平台总览 |
| `$ALLIN/README.md` · `STRUCTURE.md` | ALLIN 代码仓说明 |
| `$ALLIN/docs/ALLIN_设计到测试完整报告.md` | 设计到实测长报告；**算法/公式见 §4.5** |
| [`allin-multimodal-fix-audit.md`](allin-multimodal-fix-audit.md) | 修复审计：anchor/schema/gate/MD；**等 SP 前只做代码准备** |
| `$BINDING_RL/PROJECT.md` | 数据目录旁路入口 |
| `$VALIDATION/allin_pc_gl_progressive/RANK_SUMMARY.md` | 三轮排名摘要 |

---

## 12. 变更日志

| 日期 | 变更 |
|------|------|
| 2026-07-24 | 初版：多模态立项 brief（目标 / 成功标准 / 待确认） |
| 2026-08-01 | **重写为项目现状 + 数据地图**：ALLIN 主线路径、对接覆盖、特征真源、缺口与待办；binding_RL / ALLIN 旁路入口 |
