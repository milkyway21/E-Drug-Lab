# round_200：VAV1 10000 分子生产任务（2026-06-21 启动）

> 双卡（GPU1+2）DiffGUI 生成 10000 个 VAV1 分子胶候选 → 转换 → correct-reconstruct 评估（exhaustiveness=8 dock）→ 合并。round_id=200。

## 任务参数（用户确认）

- **GPU**：1 + 2 各 1 个任务（用户原说"gpu12"，实为 GPU1+2；服务器仅 0-5）
- **batch_size=8**（用户要 50，但 50/40/20 全 OOM；b8 安全。见下方显存分析）
- **分子数**：每卡 5000，共 10000
- **seed**：GPU1 base seed=0，GPU2 base seed=5000000（远偏移防重叠）；每卡 100 run × 50 mol/run = 100 个 seed（对应"各负责100个随机数"）
- **评估**：全量 10000 跑 exhaustiveness=8 vina **dock**（用户明确"vinadock 选项"），vina-timeout=180s，12 worker 并行
- **预计总时长**：~6.5 天（生成 ~5.8 天 + 评估 ~21h）

## 目录结构

```
backend/outputs/rl_rounds/round_200/
  gpu1/ gpu2/              # 各卡 generate_batch 输出（run_001..run_100/sample_run_*/samples_vav1.pt）
  converted/gpu1.pt gpu2.pt  # 转换后 TargetDiff 格式
  eval/gpu1/ gpu2/         # correct-reconstruct 评估输出（xlsx + sdf + report）
  merged/                  # 两卡合并结果
  logs/{gpu1,gpu2}_{gen,convert,eval}.log + _status.txt + _driver.out
```

## 驱动与查询脚本

- **驱动**：`backend/scripts/run_round200_pipeline.sh <GPU_ID> <CONFIG> <GEN_OUTDIR>`
  - 链式：generate(diffgui_new env) → convert(diffdynamic env) → evaluate(diffdynamic env)
  - 用 `setsid nohup` 启动，完全脱离 session，6 天长跑不被杀
- **进度查询**：`backend/scripts/round200_progress.sh`（统计 samples_*.pt 数、累计 finished 分子、当前 run/步、GPU 占用、阶段状态）
- **两份 GPU config**：`/data/ye/diffgui/configs/sample/sample_vav1_gpu{1,2}.yml`（仅 sample.seed 不同：0 / 5000000）

## 启动命令（已执行）

```bash
setsid nohup bash backend/scripts/run_round200_pipeline.sh 1 sample_vav1_gpu1.yml .../round_200/gpu1 &
setsid nohup bash backend/scripts/run_round200_pipeline.sh 2 sample_vav1_gpu2.yml .../round_200/gpu2 &
```

## 此任务修的新 bug（vendored DiffGUI）

### 9. `scripts/sample.py` batch_lab 索引越界（batch_size > config 时崩）
`sample.py:147-148` 原用 `config.sample.batch_size`(=5) 建 `batch_lab`(5 行)，但生成用 `args.batch_size`(=50) → `n_graphs=50`，`ligand_batch`(0..49) 索引 5 行的 `lab` → `srcIndex < srcSelectDimSize` 断言失败，模型未加载即崩（显存峰值 14MiB，误判为别的错）。
**修复**：`batch_size = args.batch_size if args.batch_size > 0 else config.sample.batch_size`，用实际 batch_size 建 batch_lab。

### 10. batch_size 显存超线性暴涨（O(N²) over 蛋白口袋节点）
denoiser 对全部节点（蛋白口袋 350 原子 × n_graphs 占大头）做 O(N²) 边/注意力。实测：

| batch_size | 显存峰值 | 结果 |
|---|---|---|
| 5 | 25GB | ✅ 安全（round_100 验证）|
| 8 | ~22GB | ✅ 安全（round_200 采用）|
| 10 | 48.2GB | ⚠️ 险过（余量 929MiB）|
| 20/40/50 | ~47GB | ❌ OOM |

**关键洞察：吞吐与 batch_size 无关**。b5=2.78 it/s、b10=1.39 it/s（恰好 2 倍慢 2 倍分子）→ ~0.83 分子/分钟恒定，GPU 算力饱和。大 batch 不提速只费显存。→ 选最小安全 batch_size 即可。

## 评估参数偏离测试规则的说明

CLAUDE.md 测试规则 `vina_timeout=20` 是给**测试**用的；本任务是**生产** exhaustiveness=8 dock，20s 会让绝大多数 dock 超时拿不到分。故生产用 `--vina-timeout-seconds 180`。`--vina-modes dock`（只跑 dock，省 2/3 时间；round_100 测试时跑了 dock+score_only+minimize 三模式）。

## 监控

- 近期：Monitor 盯 `logs/*_status.txt` + `*_gen.log` 的 OOM/Traceback/阶段切换
- 长期：随时 `bash backend/scripts/round200_progress.sh`
- 完成后：两卡 eval xlsx 合并到 `merged/`

## 相关

- [[diffgui-vav1-eval-pipeline]] —— 同链路 round_100 原型 + 8 个早期 bug
- [[workflow-diffgui-glare-wetlab]] —— 整体闭环
