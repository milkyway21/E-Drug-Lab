# DiffGUI 生成 → GLARE 筛选 → 湿实验反馈 完整实验流程

> 2026-06-20 整理。e-drug-lab 核心闭环的操作手册，所有步骤均对应已验证的脚本/API。

## 整体闭环

```
Round N
  ① DiffGUI 生成 → ② 评估打分 → ③ GLARE 筛选(query)
                                   │
                       ④ 合成 + 湿实验 pDC50
                                   │
  ⑥ GLARE 重新筛选 ← ⑤ 湿实验反馈强化 GLARE(wetlab reinforce)
       (更优 top-N)        (policy 向真实活性靠近)
       │
       └────→ 进入 Round N+1（用新 checkpoint 生成/筛选）
```

## ① DiffGUI 生成分子胶候选

- 脚本：`/data/ye/diffgui/scripts/run_batch_generate.py`
- conda env：`diffgui_new`（torch 2.4.1 + CUDA）
- API：`POST /api/v1/diffgui/generate` → `DiffGuiRunner.run_generate`
- 关键参数：`--protein_file`(必填)、`--num_mols`(测试 5 / 生产 10000)、`--batch_size`(5)、`--round_id`(N)、`--require_achiral`(true)、`--config`(configs/sample/sample.yml)、`--device`
- 输出：`backend/outputs/rl_rounds/round_{N}/generated/round_{N}_all.sdf`(+.pt)

## ② 评估打分 → evaluated 文件

- pipeline 各步打分汇总，`pipeline_eval_bridge.write_evaluated_xlsx()` 写成 `round_{N}_evaluated.xlsx`
- 列含：SMILES、名称、对接分、ADMET、正交分等
- **evaluated.xlsx 是 GLARE 训练/筛选的核心输入**

## ③ GLARE 筛选

### 第一轮：种子数据强化（建初始策略）
- 脚本：`glare_selector/reinforce_glare_with_seed_data.py`
- API：`POST /api/v1/glare/train`(`run_seed_reinforce=true`)
- 输入：seed_file=`/data/ye/diffgui/data/seed/seed_activity_data.xlsx` + evaluated_file
- 输出：`round_{N}_glare_seed_reinforced_checkpoint.pt` + reward表 + similarity表 + 报告

### 筛选 top-N
- 脚本：`glare_selector/train_glare_policy.py query`
- API：`POST /api/v1/glare/screen` → `GlareRunner.run_screen`
- 参数：`--top_n=200`、`--wetlab_sample_count`、`--diversity_max_per_scaffold=5`、`--similarity_dedup_thresh=0.85`
- 输出：`round_{N}_glare_ranked_all.csv` + `round_{N}_glare_selected_top5.csv/.sdf`

## ④ 合成 + 湿实验 pDC50

- 人工环节：GLARE 选出的 top-N 送合成 + 测 pDC50
- 上传：`POST /api/v1/glare/import-wetlab?round_id={N}`(上传 xlsx)
- 脚本：`glare_selector/import_wetlab_pdc50.py` → 导入 `labeled_pool_master.xlsx`(累积标注池)

## ⑤ 湿实验反馈强化 GLARE（核心闭环）

- 脚本：`glare_selector/reinforce_glare_with_wetlab.py`
- API：`POST /api/v1/glare/train`(带 wetlab_file，run_seed_reinforce=false, run_train=false)
- 输入：labeled_pool + wetlab_file + evaluated_file + previous_checkpoint
- 内部机制：自动识别新增湿实验字段 → 四档 training_reward 权重 → 8 类 hard case → <20 小样本保护(conservative)
- 输出：`round_{N}_glare_reinforced_checkpoint.pt`

## ⑥ 用强化后 GLARE 重新筛选 → 进入下一轮

- 同③ query，但用⑤的新 checkpoint
- 可选：`run_train`(`train_glare_policy.py train`)做完整训练而非仅强化

## 一轮最小操作序列

```
1. POST /api/v1/rl-rounds  {round_id:1, target_id:"VAV1"}
2. POST /api/v1/diffgui/generate {protein_file, round_id:1, num_mols:5}
3. (pipeline 各步打分，前端汇总)
4. POST /api/v1/glare/train   {round_id:1, run_seed_reinforce:true}
   POST /api/v1/glare/screen  {round_id:1, top_n:200, wetlab_sample_count:5}
5. (湿实验合成 top-5 → 测 pDC50)
6. POST /api/v1/glare/import-wetlab?round_id=1  (上传 xlsx)
7. POST /api/v1/glare/train {round_id:1, wetlab_file, run_seed_reinforce:false, run_train:false}
8. POST /api/v1/glare/screen {round_id:1, top_n:200}
   → 进入 round 2，循环
```

## 关键设计要点

1. evaluated.xlsx 是中枢：生成→评估→筛选围绕它，GLARE 据此学 reward
2. labeled_pool_master 累积：湿实验数据跨轮累积，GLARE 越练越准
3. 小样本保护：<20 湿实验点 conservative 更新，防过拟合（分子胶场景数据稀缺的关键）
4. 多样性+去重：GLARE 筛选内置骨架多样性 + 相似度去重
5. 每步异步+可追溯：长任务走 job_store 异步，前端轮询；每轮状态入库可回溯
6. conda 隔离：DiffGUI/GLARE 共用 diffgui_new 环境，输出统一到 backend/outputs/rl_rounds/

## VAV1 项目数据

- 项目目录：`/data/ye/e-drug-lab/data/VAV1_degron/`
  - `9nfr.pdb`(1.9M，VAV1 蛋白结构)
  - `9nfrligand.pdb`(2.2K，配体)

## 相关

- [[rl-path]] —— GLARE 链路、状态管理、Task 6 路径修复、端到端验证
- [[env-and-tool-runtime]] —— conda 环境、conda_runner
- [[project-structure]] —— 整体架构
