# round_200 断点记录（2026-06-22）

> 用户要求"这轮生成完暂停生成进行分析，保存断点记录方便下次开始生成"。
> 已在 GPU1 run_009 + GPU2 run_009 跑完后停止生成（用户选定"等当前这批 run 跑完即停"）。
> 现进入 correct-reconstruct 评估（分析阶段）。生成断点已保存，下次从 run_010 续跑。

## 生成断点（关键！下次续跑看这里）

| 卡 | 完整 run | 已生成分子 | 不完整 run | 下次续跑 `--start_run` | base seed |
|----|---------|-----------|-----------|----------------------|-----------|
| GPU1 | run_001–009（9个）| **465** | run_010/011 已删 | **10** | 0 |
| GPU2 | run_001–009（9个）| **458** | run_010(空) 已删 | **10** | 5000000 |
| **合计** | — | **923** | — | — | — |

- 每 run 产出 ~50-53 分子（num_mols=50，DiffGUI 内部 `while finished<num_mols` 会多采补足失败分子）
- 续跑 seed 自动衔接：`seed = base + run_idx × 10007`。GPU1 run_010 → seed 100070；GPU2 run_010 → seed 50100070。与已跑 run_001-009 不重叠。
- 续跑目标：每卡再跑 run_010–run_100（91 个 run × ~51 分子 ≈ 4641 分子/卡），加上已有 465/458，凑满每卡 ~5000、合计 ~10000。

## 下次续跑命令

`generate_batch.py` 已加 `--start_run` 参数（见 [[round200-production-run]] bug#9 之后的新增）。续跑命令：

```bash
# GPU1 续跑（seed 0 系，从 run_010）
cd /data/ye/diffgui
CUDA_VISIBLE_DEVICES=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  conda run -n diffgui_new --no-capture-output python3 scripts/generate_batch.py \
    --config configs/sample/sample_vav1_gpu1.yml \
    --outdir /data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200/gpu1 \
    --total_mols 4640 --batch_size 8 --mols_per_run 50 --device cuda:0 \
    --start_run 10

# GPU2 续跑（seed 5000000 系，从 run_010）
CUDA_VISIBLE_DEVICES=2 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  conda run -n diffgui_new --no-capture-output python3 scripts/generate_batch.py \
    --config configs/sample/sample_vav1_gpu2.yml \
    --outdir /data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200/gpu2 \
    --total_mols 4650 --batch_size 8 --mols_per_run 50 --device cuda:0 \
    --start_run 10
```

> `--total_mols` 设为剩余量（4640/4650），generate_batch 会从 run_010 跑到凑满。若想直接跑满 100 run，可设 `--total_mols 4550 --start_run 10`（91 run × 50）。
> 续跑后重跑转换+评估即可（转换器递归 glob 所有 samples_*.pt，会自动包含新旧）。

## 停止时踩的坑（stop_guard 逻辑缺陷）

`round200_stop_guard.sh` 用 `find run_010/samples_*.pt` 判断 run 完成再杀进程。但 DiffGUI 的 `sample.py` 在 `pool.finished < num_mols(50)` 时会**循环开新 batch 采样**（每 run 50 分子需多轮 batch + 每分子 Vina score_only 后处理），导致 run_010 的 .pt 迟迟不写、generate_batch 又 fork 出 run_011。结果：
- GPU2 run_009 先完成、正常停止、进评估 ✅
- GPU1 run_010 卡在循环采样，stop_guard 干等不到 .pt，最终手动 kill PID 才停

**教训**：下次"等当前 run 跑完即停"应改用更直接的判定（如监控 gen.log 的 `=== Run N ===` 切换、或固定等待时间后 kill），而非等 .pt 写出。已手动清理 run_010/011 不完整目录。

## 当前阶段（分析 = correct-reconstruct 评估）

停止生成后 pipeline 自动进入：
1. ✅ **转换**：convert_diffgui_pt_to_eval，gpu1.pt(464样本,跳过含Br) / gpu2.pt(458样本)
2. 🔄 **评估**：evaluate_pt_with_correct_reconstruct，exhaustiveness=8 vina dock，~12s/分子
   - GPU2 评估：8/458 已跑，预计 ~1.5h
   - GPU1 评估：刚启动，464 分子，预计 ~1.5h
   - 评估参数：`--vina-modes dock --vina-timeout-seconds 180 --exhaustiveness 8`，12 worker 并行

评估产物：`round_200/eval/{gpu1,gpu2}/`（xlsx + reconstructed SDF + report）。完成后合并到 `round_200/merged/`。

## 关键文件

- 生成输出：`round_200/{gpu1,gpu2}/run_001-009/sample_run_*/samples_vav1.pt`
- 转换后：`round_200/converted/{gpu1,gpu2}.pt`
- 评估输出：`round_200/eval/{gpu1,gpu2}/`
- 日志：`round_200/logs/{gpu1,gpu2}_{gen,convert,eval}.log` + `_status.txt`
- 驱动脚本：`backend/scripts/run_round200_pipeline.sh`
- 进度查询：`backend/scripts/round200_progress.sh`
- 停止守护（有缺陷，参考上方坑）：`backend/scripts/round200_stop_guard.sh`

## 相关

- [[round200-production-run]] —— 任务全貌、参数、bug#9/#10、启动命令
- [[diffgui-vav1-eval-pipeline]] —— 链路原型 + 早期 8 bug
