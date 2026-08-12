---
name: hsv-04-seed-ifd
description: >
  Unique Top100 IFD (Prime), Z:1000 extract, 1:1 Glide, and Shape query seeds.
  Invoke after unique Top100 exists, before Shape 01–14, or when repairing IFD ligand extract.
catalog_refs: [sz.ifd, sz.glide_sp]
---

# HSV-04 — 唯一种子 IFD → Shape Query

科学家角色：**诱导契合精修**。产出 Shape 的 3D query，不是终筛 Top200。

## When to invoke

- Unique100 已选好  
- 需要 `QUERY_001…100`  
- 修复 Z:999/Z:1000 抽错

## Procedure

1. LigPrep（Epik）  
2. IFD：`GLIDE_GRID_GEN → GLIDE_DOCKING2 → COMPILE_RESIDUE_LIST → PRIME_REFINEMENT`（无第二段 N×N Glide）  
3. 从 Prime out **提取 Z:1000**  
4. Glide **1:1** SP（每配体对自身 apo）  
5. 合并四体系分 → `unique100_ifd_4systems.csv`  
6. 导出 Shape 种子：`similarity_expand/top100_unique_seeds.csv`

参考：`merged_library/fill21_ifd/`、`scripts/run_prime80_glide1to1.py`、`merge_unique100_ifd_scores.py`

## Hard pitfalls

| 坑 | 正确做法 |
|----|----------|
| Z:999 vs Z:1000 | 只抽 **Z:1000** |
| `top200_ifd` N×N | **已放弃**，勿复用 |
| 进度日志 | 看 `work/*.log`，勿只看 JobId 文件 |

## Gate to next

100 query 3D + seeds CSV → `hsv-05-shape-screen`

## Do not

- BatchGlide 全员交叉对接  
- 跳过 1:1 直接用 IFD 内嵌第二段 Glide 当分（本任务约定）
