---
name: hsv-01-diffdynamic-generate
description: >
  DiffDynamic pocket sampling, PT→SDF eval, and master-library merge for HSV campaigns.
  Invoke after hsv-00, when generating molecules, or merging seed batches into merged_library.
catalog_refs: [dd.env, dd.script.sample, dd.script.batch, dd.script.eval]
---

# HSV-01 — DiffDynamic 生成 → 主库

科学家角色：**计算化学家 / 生成模型操作员**。产出可对接的主库，不在此步做四体系排名。

## When to invoke

- 新口袋需要 de novo / scaffold 分子  
- 用户要求「生成 / 采样 / 合并主库」  
- `hsv-00` 完成后的默认下一步

## Procedure

1. `conda activate diffdynamic`；`PYTHONPATH=/data/ye/DiffDynamic`  
2. GPU 预检：选空闲显存最大的卡（避免与 Shape GPU 冲突）  
3. 采样：
   - 并行：`batch_sampleandeval_parallel.py --sample-only …`
   - 单任务：`scripts/sample_diffusion.py configs/sampling.yml …`
4. 评估：`split_and_eval_parallel.py` 或 `evaluate_pt_with_correct_reconstruct.py`  
5. 合并：`hsvpol/scripts/merge_all_sources.py` → `merged_library/csv/merged_library_master.csv`

## Inputs / Outputs

| In | Out |
|----|-----|
| 受体 PDB、参考配体 SDF、sampling.yml | `result_*.pt`、`reconstructed_molecules/*.sdf` |
| 多批次 SDF | `merged_library_master.csv`、`sdf/{molecule_id}.sdf` |

冒烟：`batch_size=5` / `num_samples=5`。

## Gate to next

- 主库存在且 `molecule_id` 唯一  
- → `hsv-02-receptor-grid`（缺 Grid）或 `hsv-03-sp-fill-rank`（Grid 已有）

## Do not

- 编造 Vina/综合分；未评估的 PT 不当作成品库。  
- 把生成物直接写入 AI4S 官方 Top10 CSV。
