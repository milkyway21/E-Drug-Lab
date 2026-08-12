---
name: hsv-07-shape-top200-ifd
description: >
  Shape Top200 IFD campaign: LigPrep, 8×4-system IFD (60 cores), Z:1000, 1:1 Glide, weighted rank.
  Invoke after Top200 exists; smoke one molecule first; full run only when user orders.
catalog_refs: [sz.ifd, sz.glide_sp]
---

# HSV-07 — Shape Top200 IFD 终筛

科学家角色：**终局诱导契合与排序**。本任务最重计算环节；**冒烟通过 + 用户下令**才全量。

## When to invoke

- Top200 加权表已有  
- 用户说「开始 IFD / 全量跑」  
- 查进度 / ETA / 软失败（缺 pose 文件）

## Workdir

`merged_library/shape_top200_ifd/`  
全量：`scripts/run_shape_top200_pipeline.sh`（`NJOBS=15` → 四体系 60 核）  
冒烟：`scripts/smoke_one.sh`  
说明：`SMOKE_OK.md`

## Procedure

1. `export_shape_top200_for_ifd.py`（全量 200；勿残留 `--smoke-one` meta）  
2. LigPrep → `split_ligprep_shards.py`（8 shard）→ `generate_ifd_configs.py`  
3. 逐 shard `run_ifd.sh`（四体系并行）+ `update_ifd_progress.py`  
4. `extract_for_glide1to1.py`（Z:1000）  
5. `run_glide1to1.py` → `collect_and_rank.py`  
6. 终表：`results/shape_top200_ifd_4systems_ranked.csv`；完成旗：`PIPELINE_DONE.txt`

## 进度与排障

| 现象 | 处理 |
|------|------|
| `pipeline.nohup` 停在 ifd-start | 看 `work/shard_*_*.log` |
| W781V「File does not exist」若干 pv | 常为软失败，带剩余态继续；必要时事后补跑 |
| 冒烟污染 200 meta | 重导 export；清冒烟 mae |

IFD 内阶段：Grid → Dock → Residue list → **Prime**（最慢）。

## Gate / Done

`PIPELINE_DONE.txt` + 加权终表；可选回写实验记录 / 画图手册。

## Do not

- 复用已放弃的 `merged_library/top200_ifd/` N×N 路径  
- 无人下令开全量  
- 只盯 JobId 日志判死活
