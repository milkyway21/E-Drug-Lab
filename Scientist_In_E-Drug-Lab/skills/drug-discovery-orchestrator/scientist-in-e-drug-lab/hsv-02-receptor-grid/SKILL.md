---
name: hsv-02-receptor-grid
description: >
  PrepWizard and per-system Glide grid centers for WT + three mutants.
  Invoke before four-system SP, when mutant coords differ from WT, or setting up a new pocket.
catalog_refs: [sz.prepwizard, sz.glide_sp]
---

# HSV-02 — 受体准备与四体系 Grid

科学家角色：**结构生物学 / 对接准备**。突变体与 WT 常不在同一坐标系。

## When to invoke

- 新突变体 PDB 入库  
- Glide 报 grid / 位点离谱  
- `hsv-03` 之前 Grid 缺失

## Procedure

1. PDB → MAE（`pdbconvert`）  
2. PrepWizard（与 WT 同参数：fillsidechains、Epik pH 7.4、S-OPLS…）  
3. **各体系独立**算 GRID_CENTER（共晶/参考配体质心 + 偏移；禁止抄 WT）  
4. 生成 `*_grid.zip`

脚本参考：

- `mmgbsa_4systems/scripts/00_prep_receptors/run_prepwizard.sh`
- `mmgbsa_4systems/scripts/02_glide_sp_redock/gen_grids.sh`

## HSV Pol 历史中心（仅参考）

| 体系 | GRID_CENTER |
|------|-------------|
| WT | 147.23, 145.00, 124.70 |
| N815S | −11.61, −7.27, 7.31 |
| W781V | −9.61, −3.69, 7.29 |
| Y941H | −12.15, −6.88, 6.99 |

产物：`mmgbsa_4systems/grids_full/{SYS}/{SYS}_grid.zip`

## Gate to next

四体系 grid 齐 → `hsv-03-sp-fill-rank`

## Do not

- 突变体直接用 WT `GRID_CENTER`  
- 原 PDB 不经 PrepWizard 就给 Glide（DiffDynamic 可用原 PDB）
