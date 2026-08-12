---
name: hsv-03-sp-fill-rank
description: >
  Four-system Glide SP fill, percentile-weighted ranking, and unique Top100 seeds.
  Invoke after grids+library exist, for SP gaps, weighted shortlists, or unique seed selection.
catalog_refs: [sz.glide_sp, ed.svc.schrodinger]
---

# HSV-03 — 四体系 SP 补全 + 加权 + 唯一种子

科学家角色：**虚拟筛选负责人**。在十万级主库上补齐四体系分并选出 Shape/IFD 种子。

## When to invoke

- 主库缺 `*_SP`  
- 需要 `sp_weighted_score` / Top 池  
- 准备 Unique100 / Shape query 种子

## Procedure

1. 导出缺口：`scripts/export_missing_sp_jobs.py`  
2. Phase1 WT / Phase2 三突变：`run_sp_fill_phase1_wt.sh`、`run_sp_fill_phase2_mutants.sh`  
3. 回写：`ingest_sp_results.py`  
4. 加权：`compute_sp_weighted_score.py`  
5. 唯一种子：`select_unique_top100_for_ifd.py`（或项目等价脚本）

CPU：`PARALLEL_BATCHES × NJOBS ≤ 100`；hosts `processors` 96–100。

## 加权公式

```text
sp_weighted = 0.5·pct(WT_SP) + ⅙·pct(N815S) + ⅙·pct(W781V) + ⅙·pct(Y941H)
```

百分位：gscore 越负 → pct 越低（越好）。

## 关键产物

- `merged_library/csv/wt_le_8_4sys_ranked.csv`
- Unique Top100 表 / SDF（下游 IFD 输入）

## Gate to next

Top100 唯一结构就绪 → `hsv-04-seed-ifd`

## Do not

- 用 SMILES merge 四体系表  
- 未 ingest 完整四体系就宣称「稳健 Top」
