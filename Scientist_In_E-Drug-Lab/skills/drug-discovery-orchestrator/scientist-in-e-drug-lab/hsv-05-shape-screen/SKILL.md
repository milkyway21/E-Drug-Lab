---
name: hsv-05-shape-screen
description: >
  Schrödinger Phase Shape screen 01–14: swxds library → unique k=10 (1000 parents).
  Invoke after IFD/query seeds exist, for shape expansion, or resuming 08–14.
catalog_refs: [sz.funnel.ddfast]
---

# HSV-05 — Shape Screen 01–14（扩至 1000）

科学家角色：**配体相似性 / 化学空间扩展**。Query 来自 IFD 种子（HSV 主路径）。

## When to invoke

- `top100_unique_seeds` + query MAE 就绪  
- 用户要求 Shape / 类似物 / unique1000  
- 断点续跑 08–14

## Workdir

`merged_library/shape_screen_unique100/`  
一键：`scripts/run_all.sh`  
手册：`PIPELINE_NEXT_POCKET_HANDBOOK.md` §5

## Stage map

| # | 做什么 |
|---|--------|
| 01–04 | 库 QC → 1D 预筛 → 候选并集 |
| 05–06 | LigPrep → 快速构象 + shape bin |
| 07 | GPU 3D Shape（避开 DiffDynamic GPU） |
| 08–09 | 母体折叠 + 唯一分配 **k=10 → 1000** |
| 10–14 | refine / backfill / 导出 / 校验 / 报告 |

环境：

```bash
export SCHRODINGER=/opt/schrodinger2023-3
export SCHRODINGER_TEMPDIR=/data/zhang/Ye/DiffDynamic_outputs/hsvpol/schrodinger_tmp
```

## 产物

- `09_results/final_1000_unique_compounds.*`
- `10_reports/FINAL_REPORT.md`

## Gate to next

1000 唯一 + 校验 PASSED → `hsv-06-shape-candidate-sp`（扩 k=25）

## Do not

- 用 SMILES 对齐 query 与 library  
- 未 smoke 就全量 03+  
- 与 `ddshape-*`（SP Top1000 query、无 IFD）路径混用而不改 `MAXQ`/标题格式

## Related

单体系 SP-query Shape 变体见 `ddshape-00-pipeline-brief`（不同任务）。
