---
name: hsv-06-shape-candidate-sp
description: >
  Expand Shape to k=25 (2500), run 100-shard four-system Glide SP, ingest and pick Top200.
  Invoke after final_1000 exists, for 2500 docking, or weighted Top200 export.
catalog_refs: [sz.glide_sp]
---

# HSV-06 — Shape 2500 × 四体系 SP → Top200

科学家角色：**大规模对接调度**。把 Shape 类似物压成可 IFD 的 Top200。

## When to invoke

- Shape k=10 完成，要扩库  
- 用户要 2500 四体系分 / Top200  
- 百核分片 SP 任务

## Procedure

1. `09_solve_unique_assignment.py --k 25` → `query_candidate_assignment_k25.csv`  
2. `12b_export_final_2500.py` → `final_2500_unique_compounds.{csv,smi,sdf}`  
3. hosts `processors: 100`  
4. `16c_split_sdf_100.py` → 100 shard  
5. `16d_run_4sys_sp_100shards.sh`（LigPrep×100 → 按体系串行 Glide）  
6. `16e_merge_shard_sp_csvs.py` + `16b_ingest_4sys_sp.py`  
7. 导出加权 Top200（及可选抗耐药子集）

工作目录：`shape_screen_unique100/11_glide_4sys_sp_k25/`  
结果：`09_results/final_2500_4sys_sp*.csv`

## 注意

- 与 k=10 重叠应 = 1000  
- SDF title 必须是 `library_id`（`swxds_*`）  
- 旧 similarity_expand 1000 analogs **与 Shape Top200 重叠可为 0**，勿混用

## Gate to next

`final_2500_4sys_sp_top200_weighted.*` → `hsv-07-shape-top200-ifd`

## Do not

- 未合并 ingest 就开 IFD  
- 用冒烟 1 分子 meta 覆盖全量 200 导出而不重导
