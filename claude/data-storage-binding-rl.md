# GLARE 升级 — Glide / MD / 101D 数据存储地图

> **用途**：多模态 GLARE（指纹 + 101 维理化 + 对接/动力学）的数据真源索引（列级详表）。  
> **核对日期**：2026-08-01（在 2026-07-24 基线上补 round2/3 与 `features_v1`）  
> **关联**：项目导航真源 [`project.md`](project.md) · 旁路 [`binding_RL/PROJECT.md`](../backend/outputs/vav1_rl_project/binding_RL/PROJECT.md) · 实验记录 `backend/outputs/vav1_rl_project/reports/experiment_log.md`

**根目录（Glide + MD）**

```text
/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/binding_RL
```

下文用 `$BINDING_RL` 表示该路径。

**101 维理化（在 `vav1_rl_project` 下，与 `binding_RL` 并列）**

```text
/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/PAT_training_database_101D.csv
```

---

## 0. 总览与体量

| 资产 | 路径 | 约体量 | 分子规模 | 角色 |
|------|------|--------|----------|------|
| DrugFlow Glide SP | `$BINDING_RL/docking/` | ~293M | 11659 / 11682 成功 | 大库对接 + 接触矩阵 |
| 专利 403 Glide SP | `$BINDING_RL/patent_docking/` | ~16M | **403/403** | 有标签训练集对接 |
| wetlab 13 Glide SP | `$BINDING_RL/wetlab_docking/` | ~1.5M | **13/13** | 湿实验探针对接 |
| 第二轮实体 Glide | `$BINDING_RL/round2_entity_docking/` | ~1.6M | **19/19** | R2 实体对接 |
| 第三轮生成库 Glide | `$BINDING_RL/round3_docking/` | ~205M | **~9209** unique | R3 库对接（≤30 核） |
| 合并 Glide 特征表 | `$BINDING_RL/features_v1/glide/` | — | ~9644 行表 | ALLIN 训练/query 加载 |
| PhysChem / MD 特征 | `$BINDING_RL/features_v1/{physchem,md}/` | ~2.5M 合计 features_v1 | 专利 101D；MD 8 体系 | 多模态特征缓存 |
| MD 八体系原始 | `$BINDING_RL/MD_information/` | ~296M（含 tar） | **8 systems** | 动力学状态 / reward |
| 衍生特征 | `$BINDING_RL/patent_screening/` | ~0.7M | 403 | Glide+IFP+MD 权重+split |
| 101D 理化原表 | `.../PAT_training_database_101D.csv` | ~0.6M | **388 行** | 101 维 RDKit 特征 + 标签 |

Glide **共用格点**：`$BINDING_RL/docking/grid/9nfr_grid.zip`（受体 `docking/prep/9nfr_prepared.mae`）。

```
binding_RL/
├── PROJECT.md            # 旁路入口 → claude/project.md
├── docking/              # DrugFlow ~1.1 万
├── patent_docking/       # 专利 403
├── wetlab_docking/       # wetlab 13
├── round2_entity_docking/# 第二轮实体 19
├── round3_docking/       # 第三轮生成库 ~9209
├── features_v1/          # glide / physchem / md / strip_qc
├── MD_information/       # 八体系 MD + tar 备份
├── patent_screening/     # 衍生特征表
├── patent_to_wetlab/     # 专利→湿实验相关（旁路）
├── screening/            # 其他筛选产物（旁路）
├── 9nfr.pdb / scaffold / DrugFlow SDF/CSV …
└── README_zh.md
```

---

## 一、Glide SP 数据（历史 3 套 + 分轮补充）

### 1.1 DrugFlow 全库（~1.1 万分子）

| 内容 | 路径 |
|------|------|
| 主结果表 | `$BINDING_RL/docking/results/glide_sp_docking_results.csv` |
| VAV1 接触矩阵 | `$BINDING_RL/docking/results/residue_contact_matrix_vav1.csv` |
| 全残基接触矩阵 | `$BINDING_RL/docking/results/residue_contact_matrix.csv` |
| CRBN 接触矩阵 | `$BINDING_RL/docking/results/residue_contact_matrix_crbn.csv` |
| QC | `$BINDING_RL/docking/results/qc_report.json` |
| pose（maegz 等） | `$BINDING_RL/docking/glide/` |
| LigPrep | `$BINDING_RL/docking/ligprep/` |
| 格点 | `$BINDING_RL/docking/grid/9nfr_grid.zip` |
| 受体 | `$BINDING_RL/docking/prep/9nfr_prepared.mae` |
| 参数说明 | `$BINDING_RL/docking/VERIFIED_PARAMS.md` · `README.md` |

**QC 摘要（已读文件）**

| 字段 | 值 |
|------|-----|
| 输入分子 | 11682 |
| 有 pose 分子 | **11659**（成功率 ≈ 99.80%） |
| 分析 pose 数 | 19454 |
| docking_score | min −12.12 / mean −8.31 / median −8.56 / max −2.24 |
| 接触残基 | 64（CRBN 42 · VAV1 22 · DDB1 0） |

**主表列（19）**：`mol_id`, `docking_score`, `glide_gscore`, `ligand_efficiency`, `glide_emodel`, `glide_evdw`, `glide_ecoul`, `n_contact_residues`, `n_crbn_residues`, `n_vav1_residues`, `n_ddb1_residues`, `crbn_residues`, `vav1_residues`, `ddb1_residues`, `hbond_residues`, `salt_bridge_residues`, `pi_pi_residues`, `pi_cation_residues`, `hydrophobic_residues`

**原始库旁路**：根目录 `DrugFlow_jobs_unique.csv` / `DrugFlow_jobs_*_unique.sdf`（对接输入侧）。

---

### 1.1b 第二轮实体 / 第三轮生成库（2026-07 补）

| 集合 | 路径 | 规模 | 主结果 |
|------|------|------|--------|
| Round-2 实体 | `$BINDING_RL/round2_entity_docking/` | 19/19 | `results/glide_sp_docking_results.csv` · `qc_report.json` |
| Round-3 生成库 | `$BINDING_RL/round3_docking/` | ~9209 unique；24/24 shards | `results/glide_sp_docking_results.csv` · `qc_report.json` |
| R3 编排脚本 | `$BINDING_RL/round3_docking/scripts/` | — | `01_prepare_smi_shards.py` · `02_run_round3_docking.py` · `03_fast_vav1_contacts_round3.py` |

约束：Glide **≤30 核**（`--parallel 1 --host localhost:30`）。  
第一/二轮**生成库全库**对接尚未做；ALLIN 前两轮 query 时 Glide 多为 `mask=0`（见 [`project.md`](project.md) §8）。

**合并特征表（训练/query 真源）**

| 内容 | 路径 |
|------|------|
| 合并 CSV | `$BINDING_RL/features_v1/glide/allin_glide_feature_table.csv`（~9644 行） |
| 构建脚本 | `$BINDING_RL/features_v1/glide/build_allin_glide_table.py` |
| meta | `allin_glide_feature_meta.json` 等 |

加载：`backend/app/pipelines/vav1_rl/glide_features.py`（可经 `ALLIN_GLIDE_TABLE` 合并，按 `molecule_id` keep=last）。

---

### 1.2 专利集 403

| 内容 | 路径 |
|------|------|
| 主结果表 | `$BINDING_RL/patent_docking/analysis/glide_sp_docking_results.csv` |
| VAV1 接触矩阵 | `$BINDING_RL/patent_docking/analysis/residue_contact_matrix_vav1.csv` |
| 全残基接触矩阵 | `$BINDING_RL/patent_docking/analysis/residue_contact_matrix.csv` |
| QC（403/403） | `$BINDING_RL/patent_docking/analysis/qc_report.json` |
| 标签副本 | `$BINDING_RL/patent_docking/patent_403_labels.csv` |
| SMILES | `$BINDING_RL/patent_docking/smi/patent_403.smi`（另有 `shard_000..003.smi`） |
| LigPrep | `$BINDING_RL/patent_docking/ligprep/` |
| pose | `$BINDING_RL/patent_docking/glide/pat_shard_*_pv.maegz` |

**QC**：`n_expected=403`, `n_with_pose=403`, `n_missing=0`；score mean ≈ −9.81；方法标记 `fast_vav1_only_vdw4A`。

**主表列（11）**：`mol_id`, `pose_title`, `docking_score`, `glide_gscore`, `ligand_efficiency`, `glide_emodel`, `glide_evdw`, `glide_ecoul`, `n_vav1_residues`, `vav1_residues`, `all_residues`

**标签列（`patent_403_labels.csv`，403 行）**：`molecule_id`, `smiles`, `canonical_smiles`, `neutralized_smiles`, `inchikey`, `pdc50_raw`, `pdc50_norm`, `label_active`, `strong_active`, `sample_weight`, `source`

---

### 1.3 wetlab 13

| 内容 | 路径 |
|------|------|
| 主结果表 | `$BINDING_RL/wetlab_docking/analysis/glide_sp_docking_results.csv` |
| QC（13/13） | `$BINDING_RL/wetlab_docking/analysis/qc_report.json` |
| 标签 | `$BINDING_RL/wetlab_docking/wetlab_13_labels.csv` |
| 合并输入 SDF | `$BINDING_RL/wetlab_docking/sdf/wetlab_13.sdf`（另有逐分子 `*.sdf`） |
| LigPrep | `$BINDING_RL/wetlab_docking/ligprep/wetlab_13_prepared.sdf` |
| pose | `$BINDING_RL/wetlab_docking/glide/wl_13_pv.maegz` |

**QC 分子 ID**：`0228271`, `0228279`, `0228283`, `0228303`, `0228366`, `0228390`, `0228405`, `0228414`, `0228416`, `0228417`, `LXC-102`, `LXC-104`, `LXC-106`（score mean ≈ −8.74）。

**标签列**：`SDF_ID`, `SMILES`, `pDC50`, `label`, `weight`, `is_strong`

---

### 1.4 共用格点 / 受体

| 内容 | 路径 |
|------|------|
| 格点 zip | `$BINDING_RL/docking/grid/9nfr_grid.zip`（另有 `9nfr_grid-gridgen.zip` / `.in` / `.log`） |
| 受体 MAE | `$BINDING_RL/docking/prep/9nfr_prepared.mae` |
| 结构参考 | `$BINDING_RL/9nfr.pdb`, `9nfr scaffold.sdf` |

---

## 二、分子动力学数据（八体系）

### 2.1 优先使用：已解压发布树

```text
$BINDING_RL/MD_information/VAV1_RL_RELEASE/VAV1_RL_dataset_8systems_v1/
```

| 内容 | 路径 |
|------|------|
| 合并主表（window × 残基） | `.../COMBINED/all8_dynamic_window_residue.parquet` |
| VAV1/全残基占有率 | `.../COMBINED/all8_residue_occupancy_canonical.parquet` |
| 相互作用占有率 | `.../COMBINED/all8_interaction_occupancy_canonical.parquet` |
| 帧级 IFP | `.../COMBINED/all8_ifp_frame_interaction_canonical.parquet` |
| MM/GBSA ΔTDC | `.../COMBINED/all8_mmgbsa_delta_TDC_frame_residue.parquet` |
| RMSF | `.../COMBINED/all8_rmsf_residue.parquet` |
| key-residue 模板 | `.../COMBINED/all8_key_residue_config_template.parquet` |
| 单体系 | `.../SYSTEMS/{0185087,0228300,0228390,0228414,0228423,0230953,LXC-106,LXC-201}/` |
| 文档 | `.../DOCUMENTATION/`（`RL_USAGE_GUIDE.md` · `DATA_DICTIONARY.md` · `QC_REPORT.md` · `README.md`） |
| 清单 | `.../MANIFEST/` |

**八体系 ID**：`0185087` · `0228300` · `0228390` · `0228414` · `0228423` · `0230953` · `LXC-106` · `LXC-201`

每个 `SYSTEMS/<id>/` 下分组（见 `DATA_DICTIONARY.md`）：`ENERGY/` · `INTERACTIONS/` · `FLEXIBILITY/` · `RL_READY/` · `QC/` · `METADATA/` · `REVIEW/`。

### 2.2 压缩包备份

| 文件 | 说明 |
|------|------|
| `$BINDING_RL/MD_information/VAV1_RL_dataset_8systems_v1.tar.gz` | 主备份（~89M） |
| `.../VAV1_RL_dataset_8systems_v1.tar.gz.sha256` | 校验 |
| `.../VAV1_RL_dataset_8systems_v1(1).tar(1).tar.gz` | 同内容重复包（勿当第三份不同数据） |
| `.../VAV1_RL_dataset_8systems_v1(1).tar.gz` | **0 字节空壳，勿用** |

### 2.3 中文说明

```text
$BINDING_RL/MD_information/VAV1_RL_dataset_8systems_v1_详细使用说明.md
$BINDING_RL/MD_information/VAV1_RL_八体系核心文件与推荐用法说明.docx
```

### 2.4 RL 使用要点（摘自官方 guide）

```python
import pandas as pd
state = pd.read_parquet("COMBINED/all8_dynamic_window_residue.parquet")
assert state["molecule_id"].nunique() == 8
assert state.groupby("molecule_id")["window_id"].nunique().eq(100).all()
```

- 主状态表：`all8_dynamic_window_residue.parquet`（残基 × 时间窗，含观测 mask）。  
- **禁止**对未观测 MM/GBSA / IFP 直接填 0，除非模型同时吃 `*_observed` flag 且做过验证。  
- 建议 reward 分解列：`reward_key_hit` / `reward_persistence` / `reward_interaction_type` / `reward_energy` / `penalty_flexibility` / `penalty_missing_or_invalid` / `reward_total`。  
- 能量项建议有界变换，例如 `-tanh((energy - center) / scale)`。

### 2.5 与 wetlab / 专利 ID 的重叠（接入模型时注意）

| 集合 | ID |
|------|-----|
| MD 八体系 | 0185087, 0228300, 0228390, 0228414, 0228423, 0230953, LXC-106, LXC-201 |
| wetlab Glide 13 | 0228271, 0228279, 0228283, 0228303, 0228366, **0228390**, 0228405, **0228414**, 0228416, 0228417, LXC-102, LXC-104, **LXC-106** |

**明确交集仅部分 ID**。对无 MD 的分子必须走 `md_mask` / 代理特征，不能 silently 填零当「无结合」。

---

## 三、衍生特征表（可选）

路径前缀：`$BINDING_RL/patent_screening/results/`

| 内容 | 文件 | 规模 |
|------|------|------|
| 专利 Glide + IFP + 标签 + split | `feature_table.csv` | 403 × 24 |
| MD 共识权重 | `md_vav1_consensus_weights.csv` | 11 残基 × weight |
| 指标 / 图 | `metrics.json`, `roc_*.png`, `pr_*.png`, `test_predictions_*.csv` | — |

**`feature_table.csv` 列**：  
`molecule_id`, `docking_score`, `glide_gscore`, `glide_emodel`, `glide_evdw`, `glide_ecoul`, `n_vav1_residues`,  
`ifp_C.ARG.796`, `ifp_C.ASN.835`, `ifp_C.ASP.797`, `ifp_C.GLN.817`, `ifp_C.GLN.818`, `ifp_C.GLU.800`,  
`ifp_C.PHE.793`, `ifp_C.PRO.833`, `ifp_C.SER.799`, `ifp_C.TRP.820`, `ifp_C.TYR.836`,  
`md_sim`, `label_active`, `sample_weight`, `pdc50_raw`, `neutralized_smiles`, `split`

**`md_vav1_consensus_weights.csv`**：`canonical_res_num`, `weight`（11 行关键残基先验）。

---

## 四、101 维理化性质

```text
/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/PAT_training_database_101D.csv
```

| 项 | 值 |
|----|-----|
| 总列数 | **111** = 10 元数据 + **101** `RDKit_*` |
| 数据行 | **388**（≠ 403：接入时需与专利集做 ID/SMILES 对齐，缺行要记录） |
| 编码 | UTF-8（可能带 BOM；读入用 `utf-8-sig`） |

### 4.1 元数据列（10）

`Cpd.`, `Cpd_Aliases`, `Source_Count`, `pDC50`, `Activity_Code`, `Activity_Class`, `Canonical_SMILES`, `InChIKey`, `Formula`, `Formal_Charge`

### 4.2 101 维 `RDKit_*`（完整清单）

1. MolWt · 2. MolLogP · 3. MolMR · 4. TPSA · 5. FractionCSP3  
6. NHOHCount · 7. NOCount · 8. NumHAcceptors · 9. NumHeteroatoms · 10. NumRotatableBonds  
11–20. RingCount / NumAromaticRings / NumAliphaticRings / NumSaturatedRings / NumAromaticHeterocycles / NumAliphaticHeterocycles / NumSaturatedHeterocycles / NumAromaticCarbocycles / NumAliphaticCarbocycles / NumAmideBonds  
21. qed · 22. BalabanJ · 23. BertzCT · 24–28. Chi0n/Chi1/Chi1n/Chi2n/Chi3v · 29. HallKierAlpha · 30–32. Kappa1–3  
33. NumSpiroAtoms · 34. NumAtomStereoCenters · 35–37. Max/Min/MinAbs EStateIndex · 38–40. Max/Min/MaxAbs PartialCharge  
41–48. BCUT2D_{MWHI,MWLOW,CHGHI,CHGLO,LOGPHI,LOGPLOW,MRHI,MRLOW}  
49–61. PEOE_VSA{1,2,3,4,6,7,8,9,10,11,12,13,14}  
62–69. SMR_VSA{1,3,4,5,6,7,9,10}  
70–80. SlogP_VSA{1,2,3,4,5,6,7,8,10,11,12}  
81–91. EState_VSA{1..11}  
92–101. VSA_EState{1..10}

> 训练时只用这 101 列作 PhysChem 分支；标签用 `pDC50` / `Activity_*`，主键建议 `InChIKey` 或规范化 `Canonical_SMILES`。

---

## 五、多模态接入建议（数据视角）

| 模态 | 覆盖范围 | 建议用法 |
|------|----------|----------|
| 指纹 / 图 | 任意 SMILES | 现有 GLARE 主路径 |
| PhysChem 101 | 当前表 388 专利 + `features_v1/physchem/`；**生成库 1/2/3 尚无预计算落盘** | 全库可算，筛选必选通道；库 query 目前多现场算 |
| Glide SP | DrugFlow 11k + 专利 403 + wetlab 13 + R2 实体 + R3 库；合并表 `features_v1/glide/` | 对接分 / IFP；缺对接则 `mask=0` |
| MD | **仅 8 体系**（`features_v1/md/`） | 高价值子集：动力学 encoder / reward；其余分子 `md_mask=0` |

**Join 键约定（建议）**

| 数据 | 主键 |
|------|------|
| Glide DrugFlow | `mol_id` |
| Glide 专利 / feature_table | `mol_id` / `molecule_id` |
| 专利标签 | `molecule_id` |
| wetlab | `SDF_ID` ↔ Glide `mol_id` |
| MD | `molecule_id` ∈ 八体系 |
| 101D | `Cpd.` / `InChIKey` / `Canonical_SMILES` → 需建映射表 |

---

## 六、禁止事项

1. **不要**把 MD 未观测能量/IFP 默认为 0 当真实弱结合。  
2. **不要**使用 `VAV1_RL_dataset_8systems_v1(1).tar.gz`（0 字节）。  
3. **不要**假设 101D 的 388 行 = 专利 403（先对齐再训）。  
4. **不要**用 Vina/Glide 弱分直接当 inactive 伪标签（见 experiment.md 历史结论）。  
5. 大文件（pose maegz、DrugFlow SDF、MD tar）只存 `/data/ye`，勿拷到系统盘。

---

## 七、变更日志

| 日期 | 变更 |
|------|------|
| 2026-07-24 | 初版：登记 Glide 三套、MD 八体系、衍生表、101D 清单与 QC 实测数字 |
| 2026-08-01 | 补 `round2_entity_docking` / `round3_docking` / `features_v1`；交叉链到重写后的 [`project.md`](project.md) |
