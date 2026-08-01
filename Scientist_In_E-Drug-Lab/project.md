# e-drug lab Scientist Agent：低毒降脂化合物发现项目

> 更新日期：2026-08-01  
> 当前示范项目：MASLD / HSD17B13（PDB 8G9V）小分子抑制剂发现  
> 本文件用途：记录项目目标、计算漏斗、关键结论、数据位置和后续接手规则。安装与启动方法仍以仓库根目录的 `README.md` 为准。

## 1. 项目目标

本项目搭建 **e-drug lab Scientist Agent**，把生成式分子设计、已知化合物库检索、分子对接、结合自由能估算、分子动力学和毒性证据整合为一条可追溯的药物发现流程。

当前完整实例以 HSD17B13 为靶点，目标是在 MASLD 场景中发现：

- 具有潜在HSD17B13抑制作用和细胞降脂活性的化合物；
- 在HepG2游离脂肪酸（FFA）模型中具备验证价值；
- 相对低细胞毒性、低肝毒性风险；
- 具有骨架多样性，并能映射到TargetMol等现有化合物库；
- 计算来源、结构、分数、轨迹和最终提名均可复现、可审计。

“新型”“抑制剂”和“低毒”目前都是**计算提名**，不能替代酶学、靶点占有、HepG2-FFA降脂和细胞毒性实验结论。

## 2. 系统分工

| 组件 | 主要职责 |
|---|---|
| Scientist Agent | 编排流程、调用技能和计算工具、核验产物、整合证据、候选排序及实验交接 |
| DiffDynamic-Prudent | 基于8G9V口袋条件进行从头分子生成和基础化学质量控制 |
| 相似性/形状筛选 | 用生成分子查询大库，寻找可采购或已知化合物，并进行三维形状分配与去重 |
| Schrödinger Glide | SP粗筛和XP精筛，保留受体口袋中的候选结合姿势 |
| Prime MM-GBSA | 对XP姿势进行相对结合能重排序；只作相对排序，不解释为实验Ki或Kd |
| Desmond MD | 在显式POPC膜、水和离子体系中检验口袋保留、重排、接触持续性和收敛性 |
| 安全性证据层 | 汇总HepG2风险、肝毒性及其他细胞安全性字段，支持而不是取代实验筛选 |

Agent代码与技能库：

```text
/data/ye/e-drug-lab/Scientist_In_E-Drug-Lab
```

本次HSD17B13完整计算工程：

```text
/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001
```

## 3. 发现流程与当前规模

```text
8G9V口袋与生物学假说
  -> DiffDynamic-Prudent从头生成
  -> 化学质量控制与去重
  -> 大库二维相似性/三维形状匹配
  -> LigPrep
  -> Glide SP
  -> Glide XP
  -> Prime MM-GBSA
  -> 40分子 corrected-pose 2+50 ns MD
  -> 晚期主簇medoid起始姿势
  -> 20分子 2+200 ns MD
  -> 口袋接触、稳定性、能量、安全性和骨架多样性综合排序
  -> 最终10个实验提名
```

| 阶段 | 当前结果 | 主要产物 |
|---|---:|---|
| DiffDynamic-Prudent生成 | 49,999条 | `01_generation/denovo_prudent_50k_evaluation_merged.csv` |
| 去重 | 49,977个唯一分子 | `02_dedup/unique.csv` |
| 大库扩展 | 生成Top1000种子并分配约3,000个库分子 | `similarity_expand/`、`shape_screen_top1000/` |
| Glide SP | 全部SP结果147,838行；assigned-3000结果4,363行 | `glide_sp/` |
| Glide XP | 401条输出记录 | `dock_funnel_xp_mmgbsa/xp/8G9V_xp.csv` |
| Prime MM-GBSA | 130个唯一分子全部完成 | XP Top50 + XP rank 51-130 |
| 50 ns MD | 40/40完成 | Phase E corrected-pose，2 ns平衡 + 50 ns生产 |
| 200 ns MD | 20/20完成 | Phase F晚期medoid姿势，2 ns平衡 + 200 ns生产 |
| 当前实验提名 | 10个 | 抑制剂导向综合重评及TargetMol映射 |

注意：MM-GBSA总池是130个，已经做过50 ns MD的40个是其子集。因此排除MD40后，**尚未做50 ns MD的候补为90个**，不是另外130个。

## 4. 筛选和排序原则

1. 生成阶段先保证结构有效性、合理化学键、可处理性和分子去重。
2. 大库映射保留生成分子与库分子的对应关系，最终提交使用稳定库ID和实际库结构。
3. SP用于宽松粗筛，XP用于更精细的口袋姿势排序；不以单一对接分数作最终结论。
4. MM-GBSA只用于同一流程内的相对优先级，并结合配体效率、应变能和XP姿势检查。
5. MD优先判断配体是否持续位于目标B链口袋、是否保持直接接触、晚期是否收敛，以及重排后是否形成稳定结合模式。
6. 配体RMSD不是唯一标准。对潜在抑制剂而言，偏离原始docking pose但在目标口袋中形成稳定新接触，可以作为“稳定重排”保留。
7. 末段表现很重要，但必须同时查看完整轨迹的漂移、变化点、主簇占比和后期接触，不能只截取最后少量帧。
8. 最终排序综合200 ns MD、50 ns MD、MM-GBSA、XP、接触网络、骨架去重及HepG2/肝毒性风险。

## 5. MM-GBSA候选池

总汇总工作簿：

```text
/data/ye/8G9V_targetmol_t001_tables_images_20260731/05_xp_mmgbsa_md/HSD17B13_XP_MMGBSA_SP_Tox_summary.xlsx
```

其中：

- `All_MMGBSA`：130个唯一分子，均有MM-GBSA；
- `XP_Top100`：XP前100名视图；
- `MD_Top20`：当时用于MD准备的20分子视图；
- 包含XP/SP、MM-GBSA及分项能量、配体效率、SMILES、HepG2风险、肝毒性和综合安全性字段。

MM-GBSA原始结果和优化后姿势：

```text
/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001/dock_funnel_xp_mmgbsa/mmgbsa/
/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001/dock_funnel_xp_mmgbsa/mmgbsa_next80/
```

第一目录对应XP Top50；第二目录对应XP rank 51-130。CSV、MAEGZ、输入文件和运行日志均保留。

## 6. 分子动力学主线

### 6.1 体系与协议

| 项目 | 设定 |
|---|---|
| 蛋白体系 | 8G9V HSD17B13 WT二聚体 + 2×NAD⁺ |
| 目标结合位点 | B链口袋 |
| 膜 | 100% POPC显式膜 |
| 溶剂 | 显式水和离子 |
| 力场 | OPLS4 |
| 温度 | 310.15 K |
| 系综 | 平衡后NPT生产 |
| 轨迹间隔 | 200 ps |
| 50 ns协议 | 约2 ns分阶段平衡 + 50 ns连续生产 |
| 200 ns协议 | 约2 ns分阶段平衡 + 200 ns连续生产 |

“至少190 ns”曾作为200 ns任务的完整性验收下限，不是模拟设计长度。当前Phase F的设计和有效轨迹均为**200 ns生产段**。

### 6.2 Phase E：40分子 2+50 ns

Phase E是50 ns分析的唯一决策主线。40/40分子均保留输入CMS、最终52 ns CMS和DTR逐帧轨迹，原始数据约39 GB。

```text
# 建系
/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001/HSD17B13_MD/03_systems/phaseE_corrected_pose_all40_20260727

# 原始轨迹
/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001/HSD17B13_MD/04_trajectories/phaseE_corrected_pose_2_50_all40_20260727

# SEA、RMSD、接触、口袋几何和汇总分析
/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001/HSD17B13_MD/05_analysis/phaseE_corrected_pose_2_50_all40_20260727
```

完成标记包括 `MD_ALL40_DONE.flag`、`BUILD_ALL40_DONE.flag` 和 `ANALYSIS_ALL40_DONE.flag`。

### 6.3 Phase F：20分子 2+200 ns

Phase F从各分子Phase E轨迹40-50 ns窗口中提取主簇medoid。聚类前先用目标口袋Cα对齐，再按配体重原子RMSD聚类；起点不是简单末帧或最低RMSD帧。

20/20分子均有最终202 ns CMS和DTR轨迹，原始数据约50 GB。

```text
# medoid起始CMS
/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001/HSD17B13_MD/03_systems/phaseF_medoid_pose_2_200_top16_20260728

# 原始轨迹
/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001/HSD17B13_MD/04_trajectories/phaseF_medoid_pose_2_200_top16_20260728

# 20分子统一分析、SEA、变化点、聚类和最终排序
/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001/HSD17B13_MD/05_analysis/phaseF_medoid_pose_2_200_top16_20260728
```

目录名保留最初的 `top16`，但后续已补入4个分子，权威全量清单为 `phaseF_full20_manifest.csv`。

### 6.4 不用于决策的旧批次

Phase A 50 ns和Phase B旧Top6 200 ns在早期建系时未把对接配体正确变换到膜取向后的受体坐标系，存在错帧冷启动问题。它们只能用于方法开发或历史审计，不得用于口袋保留、结合模式稳定性或最终候选排名。

旧结果在200 ns轻量包中位于：

```text
/home/user/Desktop/HSD17B13_PhaseF_full20_200ns_light_package_20260731/07_legacy6_200ns_invalid_pose_reference
```

## 7. 当前最终10个候选

经过20个校正姿势200 ns结果、MM-GBSA、50 ns结果和抑制剂导向重评，当前最终提名为：

```text
T13553
T6307
T34698
T2508
T39220
T16705
T5S0045
T27695
T21193
T60390
```

分析目录名中的 `union_26runs` 表示曾把20个校正批次与旧6次运行合并做ID/骨架去重和历史对照；旧6条错帧轨迹不贡献MD稳定性证据。权威排序表：

```text
/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001/HSD17B13_MD/05_analysis/phaseF_medoid_pose_2_200_top16_20260728/best20_union_26runs_200ns_assessment/inhibitor_oriented_top10.csv
```

最终生成分子与TargetMol库分子映射、两组SDF及压缩包：

```text
/home/user/Desktop/HSD17B13_final10_generated_TargetMol_mapping_20260731
```

该目录中的 `final10_generated_to_TargetMol_mapping.csv` 是结构映射入口。较早生成的 `top10_stable_binding_candidates.csv` 和 `final_top10_union26_reselected.csv` 是中间版本，不是当前最终提交清单。

## 8. 数据存储地图

| 数据类型 | 权威位置 | 说明 |
|---|---|---|
| Scientist Agent代码和技能 | `/data/ye/e-drug-lab/Scientist_In_E-Drug-Lab` | Agent、CLI、技能、配置和测试 |
| HSD17B13原始工程 | `/data/zhang/Ye/DiffDynamic_outputs/hsvpol/targetmol_t001` | 全部生成、筛选、对接和MD原始数据 |
| DiffDynamic生成 | `.../diffdynamic/denovo_prudent_100k` | 生成结果、分批结果和日志 |
| 相似性扩展 | `.../similarity_expand` | Top1000 SP种子 |
| 三维形状筛选 | `.../shape_screen_top1000` | 查询准备、形状GPU筛选、分配与报告 |
| SP结果 | `.../glide_sp` | 8G9V SP和assigned-3000结果 |
| XP/MM-GBSA | `.../dock_funnel_xp_mmgbsa` | XP、130分子MM-GBSA、MAEGZ和日志 |
| MD原始数据 | `.../HSD17B13_MD/04_trajectories` | Phase E 39 GB、Phase F 50 GB及历史批次 |
| MD分析 | `.../HSD17B13_MD/05_analysis` | SEA、RMSD、接触、聚类、变化点和决策表 |
| 表格/图片汇总包 | `/data/ye/8G9V_targetmol_t001_tables_images_20260731` | 约330 MB，适合报告和快速查表 |
| 50 ns轻量分析包 | `/data/ye/8G9V_HSD17B13_MD_2plus50ns_stats_plots_pdf_20260731` | 统计、图和PDF，不含原始轨迹 |
| 200 ns轻量分析包 | `/home/user/Desktop/HSD17B13_PhaseF_full20_200ns_light_package_20260731` | 约603 MB，含20分子分析、SEA和复现脚本 |
| 最终Top10结构包 | `/home/user/Desktop/HSD17B13_final10_generated_TargetMol_mapping_20260731` | 最终映射表、生成查询SDF和库分子SDF |

原始大文件以 `/data/zhang/Ye/DiffDynamic_outputs/` 为权威源；`/data/ye/`和桌面目录主要是轻量归档或交付包，不应反向覆盖原始工程。

## 9. 后续工作入口

### 继续筛选90个MM-GBSA候补

1. 从 `All_MMGBSA` 中排除Phase E的40个 `molecule_id`。
2. 结合MM-GBSA相对排名、XP姿势、HepG2风险、肝毒性和骨架多样性形成候补池。
3. 在新增MD前检查与当前Top10及MD40的Morgan相似度，避免重复骨架。
4. 新批次必须使用正确受体坐标变换和独立目录，不得复用Phase A/B错帧CMS。

### 实验验证

最终10个应优先进入：

- HSD17B13酶学或靶点结合验证；
- HepG2-FFA脂滴/甘油三酯双读出；
- 同板细胞活性、膜完整性和剂量反应；
- 必要时增加肝毒性、线粒体毒性和反应性风险验证；
- 对活性命中物开展复测、正交验证和结构确认。

## 10. 维护与安全规则

- 新增筛选或MD批次只能写入新目录，不覆盖Phase E、Phase F或最终Top10源文件。
- 每次更新本文件时同步记录日期、分子数量、完成标记、权威清单和新数据路径。
- 不以进程名或单个输出文件判断MD完成；必须核验最终CMS、DTR可读性、时间长度和帧连续性。
- 不把单一RMSD、docking score或MM-GBSA绝对值作为活性结论。
- 不在本文件、日志或版本库中保存API密钥、供应商令牌或个人凭据。
- 删除或移动大轨迹前必须先确认权威副本、轻量分析包和复现所需manifest均存在。
