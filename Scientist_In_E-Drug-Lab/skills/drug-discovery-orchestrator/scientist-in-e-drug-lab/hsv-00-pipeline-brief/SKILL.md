---
name: hsv-00-pipeline-brief
description: >
  Locks HSV Pol / four-mutant SBDD funnel order, weights, IDs, and paths.
  Invoke at campaign start, before DiffDynamic/Shape/IFD, or when clarifying
  hsv-01…07 routing (not ddfast single-system, not MASLD s00).
catalog_refs: [dd.env, sz.prepwizard, sz.glide_sp, sz.ifd]
---

# HSV-00 — Pipeline Brief（科学家开工清单）

锁定 **四体系抗耐药漏斗**，再进入后续 `hsv-0N` skills。

## When to invoke

- 新口袋 / 新任务开始
- 用户问「流程怎么走 / 先做什么」
- 编排器 `scientist-in-e-drug-lab` 路由的第一步

## Funnel order

```text
00 brief → 01 generate → 02 grid → 03 SP+rank → 04 seed IFD
        → 05 Shape → 06 candidate SP → 07 Top200 IFD
```

## Hard constraints

| 项 | 值 |
|----|-----|
| 体系 | WT / N815S / W781V / Y941H |
| 加权 | `0.5×pct(WT)+⅙×pct(N815S)+⅙×pct(W781V)+⅙×pct(Y941H)` |
| 主键 | `molecule_id` / `library_id` / `QUERY_*` — 禁止 SMILES join |
| IFD 配体 | 抽 **Z:1000** |
| 工作根 | `/home/user/Desktop/Ye/DiffDynamic/hsvpol`（或 `<TARGET>`） |
| Schrödinger | `/opt/schrodinger2023-3` |
| DiffDynamic | `/data/ye/DiffDynamic` |

## Do

1. 确认靶点 PDB + 参考配体路径。  
2. `platform-health` 通过。  
3. Touch `<TARGET>/logs/.done_hsv_00`（可选）。  
4. **下一步只进** `hsv-01-diffdynamic-generate`（已有主库则可跳到 02/03）。

## Do not

- 与 `ddfast-*` 单体系漏斗混用同一工作目录约定而不改路径。  
- 未冒烟就开全量 Shape / IFD。  
- 使用已放弃的 `top200_ifd` N×N redock。

## Related

- 画图：`FULL_PIPELINE_FLOWCHART.md`  
- 手册：`PIPELINE_NEXT_POCKET_HANDBOOK.md`  
- 编排：父级 `scientist-in-e-drug-lab`
