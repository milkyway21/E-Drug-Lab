# GLARE 多模态强化筛选升级项目（Project Brief）

> **状态**：立项 / 理解旧模型阶段（改动前）  
> **日期**：2026-07-24  
> **备份基线**：`/data/ye/glare-backup-20260723`（代码 + 数据 + 实验，约 51G）  
> **实验真源**：`backend/outputs/vav1_rl_project/reports/experiment_log.md`  
> （下文简称 **experiment.md**；同目录还有 `glare_experiment_comparison.md`）

---

## 0. 一句话目标

在**保留现有 GLARE 强化学习 + 持续学习范式**的前提下，把策略网络从「几乎只吃分子指纹 / 图拓扑」升级为：

\[
\mathbf{h} = \mathrm{Fuse}\big(\underbrace{\mathrm{FP/Graph}}_{\text{现有}},\;
\underbrace{\mathrm{PhysChem}_{101}}_{\text{新增}},\;
\underbrace{\mathrm{MD}}_{\text{新增}}\big)
\]

完成改动与训练后，在 **experiment.md 已记录的可比协议**下，**全面优于旧模型最佳表现**（见 §5 成功标准）。

---

## 1. 角色与项目定位

| 维度 | 定义 |
|------|------|
| 角色 | 资深 AI 工程师 × 计算药物学家 |
| 软件宿主 | `e-drug-lab`（编排 / API / 实验记录） |
| 模型宿主 | `/data/ye/diffgui/third_party/GLARE`（策略网络本体） |
| 业务封装 | `/data/ye/diffgui/glare_selector` + `backend/.../glare_gnn_adapter.py` |
| 靶点场景 | VAV1 分子胶：专利 pDC50 + 湿实验反馈 → 大库排序 / Active Learning |
| 架构原则 | **软件主体 + 可插拔模型**；模型模块只做结构化 IO，流程逻辑留在软件层 |

本项目是 **模型层升级**，不是另起筛选流程。RL 闭环（生成 → 筛选 → 湿实验 → 强化 → 再筛选）保持不变。

---

## 2. 旧模型现状（必须先理解的事实）

### 2.1 论文定位

GLARE（NeurIPS 2025）：将大规模虚拟筛选写成 MDP，用 **GRPO（Group Relative Policy Optimization）** 学习可适应的分子选取策略，替代手工 acquisition heuristic。

### 2.2 当前表征（改动前）

实践中 VAV1 路径常用 **GIN / GINE + ECFP 指纹**：

| 通道 | 来源 | 在网络中的角色 |
|------|------|----------------|
| 分子图 | atom / bond featurization → GIN/GINE | `global_add_pool` 得到图向量 |
| 指纹 FP | ECFP（预处理写入 `graph.fp` / `x`） | MLP 投影后与图向量 **相加融合**（`x = x + fp`） |
| 理化性质 | **未进入策略网络主路径** | 仅出现在后处理打分 / wrapper 表格特征 / 分析脚本 |
| 分子动力学 MD | **未进入策略网络** | 若有 Desmond 等结果，目前最多作外部排序信号 |

结论（与你的判断一致）：现有 GLARE 强化学习 / 持续学习，**本质上是在指纹（+图拓扑）维度上更新策略**；对 ADMET 相关理化剖面、结合动力学 / 构象稳定性等信息利用不足。

### 2.3 持续学习与湿实验闭环（已验证）

```
Round N: DiffGUI 生成 → 评估 → GLARE query
              ↓
         合成 + 湿实验 pDC50
              ↓
       wetlab reinforce / 累积训练 → Round N+1
```

关键文档：`claude/workflow-diffgui-glare-wetlab.md`、`claude/rl-path.md`。

### 2.4 旧实验里已踩过的坑（改动时禁止重蹈）

摘自 experiment.md / comparison：

1. **小批量增量 AL 易假收敛**（E13/E14）：轮间排名相关 ≈ 1.0，后续轮几乎不动。  
2. **Vina 伪标签作负样本有害**（E13）：对接弱 ≠ inactive。  
3. **纯 GRPO 在小 decoy 上易坍缩**（select_prob→1）；大 decoy 可不坍缩但排序仍可能差。  
4. **监督 / 受控反馈放大**在多轮指标上更稳（E22 `fb_amp` 等）。  
5. **评估必须防泄漏**：训练分子不可混进「提升」叙事的测试探针（E43/E44 教训）。  
6. **排名绝对值依赖池大小**：跨实验比 ΔROC / ΔRank / 分离度，勿裸比不同池的 rank。

---

## 3. 改造范围（In / Out）

### 3.1 In Scope

1. **特征层**  
   - 固定 **101 维理化性质向量**（每分子可复现计算 / 缓存）。  
   - **分子动力学信息向量**（对接后 MD / 轨迹摘要；缺失时有明确 fallback）。  
2. **模型层**  
   - 为 PhysChem / MD 增加独立 encoder（或门控融合），接入 GLARE policy / classifier head。  
   - 保持 GRPO / supervised / ensemble 等训练接口兼容，或提供显式 `architecture` 开关。  
3. **数据层**  
   - 训练 / 筛选池为每个 SMILES 附带 `physchem_101`、`md_feat`（或路径引用）。  
   - 与现有 `patent_train/test`、`new_13`、decoy 拆分协议对齐（E26+ 不可擅自重拆）。  
4. **实验层**  
   - 新实验编号续写 experiment.md（建议从 **E47+**）。  
   - 对照：**同一评估协议** 下新旧模型 head-to-head。  
5. **工程层**  
   - 改动落在工作副本；回滚以 `/data/ye/glare-backup-20260723` 为准。

### 3.2 Out of Scope（本阶段不做）

- 更换生成模型（DiffGUI / DiffDynamic）本体  
- 重写湿实验 / 合成物流  
- 用对接分数重新发明标签体系  
- 删除或覆盖旧实验目录与 checkpoint  

---

## 4. 拟议技术设计（理解旧模型后的默认方案）

> 实施前仍可微调；**101 维清单与 MD 维定义见 §7 待确认项**。

### 4.1 三分支融合

```
SMILES / Graph
   ├─ GraphEncoder (现有 GIN/GINE)     → h_g
   ├─ FingerprintEncoder (现有 ECFP)   → h_fp
   ├─ PhysChemEncoder (101 → MLP)     → h_pc     [NEW]
   └─ MDEncoder (d_md → MLP)          → h_md     [NEW]
                ↓
        Fuse = Gate/Concat+MLP / 加权和
                ↓
           Policy / Logits (active vs inactive)
```

设计约束：

- **缺失 MD**：用零向量 + `md_mask`，训练时对 mask 样本降低 MD 分支梯度，避免「无 MD 分子被系统性惩罚」。  
- **PhysChem 必须可批量、CPU 可算**，筛选 10k–100k 库时不能依赖 MD。  
- **归一化**：PhysChem / MD 用训练集统计量做 z-score 或 robust scale，统计量写入 checkpoint sidecar。  
- **消融必做**：FP-only（旧） / +PC / +MD / +PC+MD，证明增益来自新模态而非偶然超参。

### 4.2 训练策略（继承旧最优经验）

默认对照配置（可被实验推翻）：

| 阶段 | 策略建议 | 备注 |
|------|----------|------|
| R0 | supervised warmup，lr≈3e-4，ensemble≥3 | 对齐 E22/E26 稳基线 |
| R1+ | 湿实验反馈：weight 放大优先于盲目 10× LR | E24+：high_weight 比 fb_amp 更稳 |
| 负样本 | 独立 Enamine / 多样性 decoy，禁止 Vina 伪 inactive | experiment.md 明确结论 |
| 持续学习 | 累积真实标签；OOD 探针不得进训练集 | E43 修正版协议 |

### 4.3 软件接入点（改模型时同步碰）

| 组件 | 路径 |
|------|------|
| 核心网络 | `diffgui/third_party/GLARE/model.py` |
| 数据加载 | `diffgui/third_party/GLARE/dataset.py` + preprocess |
| VAV1 封装 | `diffgui/glare_selector/*` |
| 后端 adapter | `backend/app/pipelines/vav1_rl/glare_gnn_*.py` |
| API | `backend/app/api/routes/glare.py`、`services/glare_runner.py` |
| 配置 | `diffgui/glare_selector/glare_config.yaml` |

---

## 5. 成功标准（必须优于 experiment.md）

### 5.1 硬门槛（全部满足才算升级成功）

在 **与旧实验相同的数据拆分与标签定义**（见 experiment.md「评估标准 E24+」）下：

| # | 指标 | 旧基线（摘录） | 新模型要求 |
|---|------|----------------|------------|
| H1 | patent_test **ROC-AUC** | E22 `fb_amp` 终值 **0.976**；监督线常见 **≥0.95** | **≥ 旧对照 + 0.01**，且不得低于对照 |
| H2 | patent_test **PR-AUC / Combined** | 同协议记录值 | **≥ 对照** |
| H3 | PASS 判定 | `ΔRank_strong < 0` 且 `ΔROC ≥ -0.03` | **PASS**，且 ΔRank_strong **优于** 同协议旧最佳 |
| H4 | 持续学习 within-round 正负分离 | E43：训后分离度大幅提升（量级 10³） | **同协议下分离度 ≥ 旧模型** |
| H5 | 消融 | — | **FP+PC+MD ≥ FP+PC ≥ FP**（允许 MD 仅在有 MD 子集上显著） |

### 5.2 软门槛（优先争取）

| # | 指标 | 参考 |
|---|------|------|
| S1 | 高活性检索 / 大池排序 | E11 自合成 mean rank 百分位 **~18.5%**；E21/E22 `rank_ge7` **~177** |
| S2 | AL 场景 | 不低于 E41b-Chase 量级的有效命中（同池注明） |
| S3 | 跨轮 OOD | 相对 E43 修正版「跨轮几乎无区分」有可报告改善 |

### 5.3 明确不算成功的情况

- 只在训练过的分子上「完美记忆」（E44 式污染），无 OOD / held-out 增益。  
- ROC 虚高但强活性排名恶化，或排名变好但 ROC 崩（旧 `fb_amp` 翻车模式）。  
- 换了更大 / 更小排名池却直接比绝对 rank。  

---

## 6. 工作阶段（建议顺序）

| Phase | 内容 | 产出 |
|:-----:|------|------|
| **P0** | 读透旧模型 + 冻结备份 + 本文档 | ✅ 进行中 |
| **P1** | 锁定 101 维 PhysChem schema + MD schema | `features_spec.md` + 可跑脚本 |
| **P2** | 特征缓存管线（专利 / decoy / wetlab） | `*.pt` / parquet 特征库 |
| **P3** | 改 GLARE 融合网络 + 训练接口 | 新 `architecture`，单测 forward |
| **P4** | 对照训练（旧 vs 新，消融） | E47+ 写入 experiment.md |
| **P5** | 达标判定 / 不达则迭代融合与正则 | PASS 报告 |
| **P6** | 接入 e-drug-lab API / 筛选闭环 | 生产路径可用 |

当前停留在 **P0 → 准备 P1**。未确认 §7 前不改网络权重训练协议。

---

## 7. 待你确认的关键歧义（停下询问）

按项目约定：**模糊处不猜死**。请确认后再动代码：

1. **101 维理化性质** — ✅ 已定位：`PAT_training_database_101D.csv`（101 个 `RDKit_*` + 10 元数据；**388 行**，详见数据地图）。仍需确认：如何映射到 403 专利缺行、以及是否按同列定义扩展到 DrugFlow/wetlab。  
2. **MD 信息** — ✅ 八体系发布树已登记（`all8_*.parquet`）。仍需确认：编码进网络的具体向量（window 摘要？occupancy？MMGBSA？）以及无 MD 分子的 mask/代理策略。  
3. **主对照实验锚点**  
   - 建议默认：**E26 拆分 + E22/E24+ PASS 协议** 为硬门槛；大池排序以同池复现旧 checkpoint 为对照。是否同意？  
4. **训练主策略**  
   - 新模态上线首轮：先做 **supervised + 反馈 weight**，还是直接上 **GRPO**？  
5. **代码落点**  
   - 在 `third_party/GLARE` 原地改（易与备份 diff），还是 `glare_selector` 外包一层 MultiModalGLARE？

---

## 8. 路径速查

| 用途 | 路径 |
|------|------|
| 本项目定义 | `e-drug-lab/claude/project.md`（本文） |
| **Glide/MD/101D 数据地图** | [`claude/data-storage-binding-rl.md`](data-storage-binding-rl.md) |
| Glide+MD 根目录 | `backend/outputs/vav1_rl_project/binding_RL/` |
| 101 维理化表 | `backend/outputs/vav1_rl_project/PAT_training_database_101D.csv`（388×101 RDKit） |
| 实验记录（experiment.md） | `backend/outputs/vav1_rl_project/reports/experiment_log.md` |
| 实验对比 | `.../reports/glare_experiment_comparison.md` |
| 实验汇总入口 | `.../glare_experiments_summary/README.md` |
| 改动前备份 | `/data/ye/glare-backup-20260723` |
| 训练数据 | `e-drug-lab/glaretrain/` |
| 种子 / 湿实验相关 | `diffgui/data/seed/` |

---

## 9. 变更日志

| 日期 | 变更 |
|------|------|
| 2026-07-24 | 初版：定义旧模型边界、多模态升级目标、成功标准与待确认项 |
