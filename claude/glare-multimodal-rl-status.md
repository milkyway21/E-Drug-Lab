# GLARE 多模态残差升级 — 落地状态（2026-07-24）

> 对齐 plan：残差融合；R0 专利 Glide；R1+ MD；MD 管道 QC 门禁。

## 命名约定（2026-07-30 确认）

**ALLIN** = 三类数据联合分析模型 = **`ginl_pc_gl`**：

1. 分子图（GLARE GNN）
2. 理化 101D（PhysChem）
3. Glide SP（能量 + VAV1 IFP）

- `ginl` / `ginl_pc` **不是** ALLIN  
- `ginl_pc_gl_md` = ALLIN + MD（扩展，另称）  
- 历史目录 `validation/allin_progressive/` 若用纯 `ginl` 训练，只能当 **非 ALLIN 基线**，需用 `ginl_pc_gl` 重跑才算 ALLIN 主线

## 已实现

| 模块 | 路径 |
|------|------|
| CRBN strip | `backend/app/pipelines/vav1_rl/crbn_strip.py` |
| PhysChem 101 | `physchem_101.py` + `scripts/rebuild_physchem_101_stripped.py` |
| Glide/IFP | `glide_features.py` → `features_v1/glide/` |
| MD 八体系 | `md_features.py` + `scripts/build_md8_feature_table.py` → `features_v1/md/`（47 维） |
| 残差编码器 | `diffgui/third_party/GLARE/model.py`：`GINLMultimodal` + `md_adv_eta` |
| CLI | `glare_gnn_cli.py`：`ginl` / `ginl_pc` / `ginl_pc_gl`(=ALLIN) / `ginl_pc_gl_md` |
| 消融 | `scripts/run_e47_e53_ablation.py`（含 `--reeval`） |

## 产出目录

```text
$BINDING_RL/features_v1/
  strip_qc/  physchem/  glide/  md/
validation/glare_e47_e53_ablation/   # E48–E52 ckpt + summary.json
```

## E47–E52 结果（patent_test ROC · wetlab13 mean_pos_rank）

| 实验 | 配置 | ROC-AUC | mean_pos_rank |
|------|------|---------|---------------|
| E48 | ginl+strip | 0.773 | 5.67 |
| E49 | +PhysChem | 0.803 | 5.00 |
| E50 | +Glide R0 | 0.831 | 5.67 |
| E51 | Expand 无 MD | 0.828 | 2.67 |
| E52 | Expand+MD | **0.832** | **2.00** |

结论：残差课程有效；MD 对湿实验阳性排名增益最明显。

## 约束备忘

- 训练/query 指纹与 101D **strip 后**；Glide/MD **不 strip**
- `label_active=-1` borderline 剔除
- MD：`reward_*` 自算；关键残基从 consensus CSV 注入；`0185087↔0185078` 别名
- 备份：`/data/ye/glare-backup-20260723`
