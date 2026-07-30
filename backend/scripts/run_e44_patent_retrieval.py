#!/usr/bin/env python3
"""E44 — 专利高活性分子检索实验：pDC50>7 分子在 100k swxds 背景中的排名.

目的：用 E43 训练的三轮权重 (R0/R1/R2) 对"专利高活性分子 + 100k swxds 背景"
进行排序，计算 pDC50>7 分子的平均排名，观察 R0→R1→R2 是否持续提升。

如果 R1 的活性分子平均排名 < R0，R2 的 < R1，
则证明持续学习让模型更擅长从海量背景中识别出已知活性分子。

输出：
  - 每轮模型下 pDC50>7 分子的平均排名、中位排名、排名分布
  - 与强弱活性子集对比
"""
import json, os, sys
import time
from pathlib import Path

sys.path.insert(0, '/data/ye/e-drug-lab/backend')
from app.services.conda_runner import conda_run

# ── 路径 ──
GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
OUTPUT_DIR = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e44_retrieval"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Stubs（必须在 import GLARE 前注入） ──
import types
try:
    import torch_sparse  # noqa
except ModuleNotFoundError:
    ts = types.ModuleType("torch_sparse")
    try:
        from torch_geometric.typing import SparseTensor as _ST
        if _ST is not None:
            ts.SparseTensor = _ST
    except Exception:
        pass
    sys.modules["torch_sparse"] = ts
try:
    import captum  # noqa
except ModuleNotFoundError:
    cm = types.ModuleType("captum")
    am = types.ModuleType("captum.attr")
    import torch as _t
    class _S:
        def __init__(self, *a, **k): pass
        def attribute(self, *a, **k): return _t.zeros_like(a[0]), _t.tensor(0.0)
    am.IntegratedGradients = _S
    cm.attr = am
    sys.modules["captum"] = cm
    sys.modules["captum.attr"] = am
sys.path.insert(0, GLARE_ROOT)

from utils.utils import check_featurizability
import pandas as pd
import numpy as np
from rdkit import Chem

# ════════════════════════════════════════════════════════════════
# Step 1: 加载专利数据，分离高活性分子 (pDC50 > 7)
# ════════════════════════════════════════════════════════════════

print("=" * 60)
print("  E44: Patent active retrieval — 100k swxds background")
print("=" * 60)

patent_df = pd.read_csv(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv"
)

# 筛选 pDC50 > 7 (label_active == 1)
active_df = patent_df[patent_df["label_active"] == 1].copy()
active_smiles = active_df["canonical_smiles"].tolist()

# 也准备强活性子集 (strong_active == 1, 即 pDC50 > ~8)
strong_df = patent_df[patent_df["strong_active"] == 1].copy()
strong_smiles_set = set(strong_df["canonical_smiles"].tolist())

# 弱活性/非活性分子 (label_active == 0 或 -1)
inactive_df = patent_df[patent_df["label_active"] != 1].copy()
inactive_smiles_set = set(inactive_df["canonical_smiles"].tolist())

print(f"  Patent active (pDC50>7):  {len(active_smiles)} molecules")
print(f"    Strong active (pDC50>8): {len(strong_df)} molecules")
print(f"  Patent weak/inactive:     {len(inactive_df)} molecules")
print(f"  Total patent:             {len(patent_df)} molecules")

# ════════════════════════════════════════════════════════════════
# Step 2: 加载 100k swxds 背景分子
# ════════════════════════════════════════════════════════════════

SWXDS_CSV = OUTPUT_DIR.parent / "glare_e41_al" / "swxds_250k_smiles.csv"

def norm_smi(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else ""

def filter_featurizable(smiles_list, label=""):
    valid = []
    skipped = 0
    for smi in smiles_list:
        if check_featurizability(str(smi)):
            valid.append(str(smi))
        else:
            skipped += 1
    if skipped:
        print(f"  Filtered {skipped}/{len(smiles_list)} {label} (not featurizable)")
    return valid

print(f"\n{'='*60}")
print(f"  Step 2: Building pool (100k swxds + patent)")
print(f"{'='*60}")

seen = set()
pool = []

# swxds: 取 100k
swxds_loaded = 0
for i, row in pd.read_csv(SWXDS_CSV).iterrows():
    if swxds_loaded >= 100000:
        break
    c = norm_smi(str(row["smiles"]))
    if c and c not in seen:
        seen.add(c)
        pool.append(c)
        swxds_loaded += 1

print(f"  Loaded {swxds_loaded} swxds molecules (deduplicated)")

# 专利高活性分子添加进去（去重可能很小）
patent_added = 0
for smi in active_smiles:
    c = norm_smi(smi)
    if c and c not in seen:
        seen.add(c)
        pool.append(c)
        patent_added += 1
print(f"  Added {patent_added} patent active molecules (new, not in swxds)")

# 过滤不可 featurize 的分子
pool = filter_featurizable(pool, "pool")
print(f"  Pool size (after featurization filter): {len(pool)} molecules")

# 记录活性分子的 SMILES → pDC50 映射
active_smi_set = set()
active_pdc50 = {}
for _, row in active_df.iterrows():
    c = norm_smi(row["canonical_smiles"])
    if c:
        active_smi_set.add(c)
        active_pdc50[c] = {
            "mol_id": row["molecule_id"],
            "pdc50_raw": row["pdc50_raw"],
            "strong": 1 if row["strong_active"] == 1 else 0,
        }

# ════════════════════════════════════════════════════════════════
# Step 3: 保存 pool → query
# ════════════════════════════════════════════════════════════════

query_path = OUTPUT_DIR / "pool_100k_patent_active.json"
with open(query_path, "w") as f:
    json.dump(pool, f)
print(f"\n  Query SMILES saved: {query_path} ({len(pool)} molecules)")

# ════════════════════════════════════════════════════════════════
# Step 4: 查询三轮权重
# ════════════════════════════════════════════════════════════════

checkpoints = {
    "R0": OUTPUT_DIR.parent / "glare_e43_progressive" / "model_R0.pt",
    "R1": OUTPUT_DIR.parent / "glare_e43_progressive" / "model_R1.pt",
    "R2": OUTPUT_DIR.parent / "glare_e43_progressive" / "model_R2.pt",
}

results = {}
for name, ckpt in checkpoints.items():
    if not ckpt.exists():
        print(f"\n  SKIP {name}: checkpoint not found at {ckpt}")
        continue

    print(f"\n{'='*60}")
    print(f"  Step 4: Querying Model_{name}")
    print(f"  Checkpoint: {ckpt}")
    print(f"{'='*60}")

    t0 = time.time()
    proc = conda_run("diffgui_new", [
        "python", "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "query",
        "--ckpt", str(ckpt), "--smiles", str(query_path), "--ensemble", "3",
    ], extra_env={"PYTHONPATH": "/data/ye/e-drug-lab/backend"})
    elapsed = time.time() - t0

    try:
        qr = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        print(f"  FAILED: stdout unparseable")
        print(f"  stderr (last 500): {proc.stderr[-500:]}")
        continue

    ranked = qr.get("ranked", [])
    rank_map = {}
    for r in ranked:
        rank_map[r["smiles"]] = int(r["glare_rank"])

    total_ranked = len(ranked)
    print(f"  Total ranked: {total_ranked}, query time: {elapsed:.0f}s")

    # ── 提取活性分子排名 ──
    active_ranks = {}
    active_strong_ranks = {}
    for smi in active_smi_set:
        rank = rank_map.get(smi)
        if rank is not None:
            active_ranks[smi] = rank
            if active_pdc50[smi]["strong"]:
                active_strong_ranks[smi] = rank

    if not active_ranks:
        print(f"  WARNING: No patent active molecules found in query results!")
        continue

    ranks_array = np.array(list(active_ranks.values()))
    strong_ranks_array = np.array(list(active_strong_ranks.values())) if active_strong_ranks else np.array([])

    results[name] = {
        "n_pool": len(pool),
        "n_ranked": total_ranked,
        "n_active_found": len(active_ranks),
        "n_active_total": len(active_smi_set),
        "n_strong_found": len(active_strong_ranks),
        "active_mean_rank": float(np.mean(ranks_array)),
        "active_median_rank": float(np.median(ranks_array)),
        "active_min_rank": int(np.min(ranks_array)),
        "active_max_rank": int(np.max(ranks_array)),
        "active_std_rank": float(np.std(ranks_array)),
        "strong_mean_rank": float(np.mean(strong_ranks_array)) if len(strong_ranks_array) > 0 else None,
        "query_time_s": elapsed,
        # 百分位分布
        "active_pct_below_1k": int(np.sum(ranks_array <= 1000)),
        "active_pct_below_5k": int(np.sum(ranks_array <= 5000)),
        "active_pct_below_10k": int(np.sum(ranks_array <= 10000)),
        "active_pct_above_50k": int(np.sum(ranks_array > 50000)),
    }

    print(f"\n  ── Results: Model_{name} ──")
    print(f"  Active (pDC50>7) molecules found: {len(active_ranks)}/{len(active_smi_set)}")
    print(f"  Mean rank:  #{results[name]['active_mean_rank']:.0f}")
    print(f"  Median rank:#{results[name]['active_median_rank']:.0f}")
    print(f"  Min/Max:    #{results[name]['active_min_rank']} / #{results[name]['active_max_rank']}")
    print(f"  Strong active (pDC50>8) mean: #{results[name]['strong_mean_rank']:.0f}" if results[name]['strong_mean_rank'] else "")
    print(f"  Distribution: <1k={results[name]['active_pct_below_1k']}, "
          f"<5k={results[name]['active_pct_below_5k']}, "
          f"<10k={results[name]['active_pct_below_10k']}, "
          f">50k={results[name]['active_pct_above_50k']}")

    # 前十名活性分子详情
    top_actives = sorted(active_ranks.items(), key=lambda x: x[1])[:10]
    print(f"\n  Top 10 ranked active molecules:")
    for smi, rank in top_actives:
        info = active_pdc50[smi]
        strong_tag = " ★" if info["strong"] else ""
        print(f"    #{rank:<6d}  {info['mol_id']:<15s}  pDC50={info['pdc50_raw']:.2f}{strong_tag}")

# ════════════════════════════════════════════════════════════════
# Step 5: 对比报告
# ════════════════════════════════════════════════════════════════

print(f"\n{'='*70}")
print(f"  E44 Summary: Patent Active Retrieval Across Rounds")
print(f"{'='*70}")

if len(results) > 1:
    print(f"\n{'Model':>8s}  {'Active(n)':>10s}  {'Mean Rank':>10s}  {'Median':>8s}  "
          f"{'Strong Mean':>11s}  {'<1k':>6s}  {'<5k':>6s}  {'<10k':>7s}  {'>50k':>6s}")
    print(f"{'-'*8}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*11}  {'-'*6}  {'-'*6}  {'-'*7}  {'-'*6}")

    ordered = [n for n in ["R0", "R1", "R2"] if n in results]
    for name in ordered:
        r = results[name]
        sm = f"#{r['strong_mean_rank']:<.0f}" if r['strong_mean_rank'] else "N/A"
        print(f"{name:>8s}  {r['n_active_found']:>4d}/{r['n_active_total']:<4d}  "
              f"#{r['active_mean_rank']:<8.0f}  #{r['active_median_rank']:<6.0f}  "
              f"{sm:>11s}  {r['active_pct_below_1k']:>4d}  {r['active_pct_below_5k']:>4d}  "
              f"{r['active_pct_below_10k']:>5d}  {r['active_pct_above_50k']:>4d}")

    # Δ 分析
    print(f"\n  Active Mean Rank deltas:")
    for i in range(1, len(ordered)):
        prev, curr = ordered[i-1], ordered[i]
        delta = results[curr]["active_mean_rank"] - results[prev]["active_mean_rank"]
        direction = "✅ 改善 (更低)" if delta < 0 else "❌ 退化 (更高)"
        improvement_pct = abs(delta) / results[prev]["active_mean_rank"] * 100 if results[prev]["active_mean_rank"] > 0 else 0
        print(f"    {prev}→{curr}: {delta:+.0f} ({improvement_pct:.1f}%) {direction}")

    # 强活性子集 Δ
    if all(results[n].get("strong_mean_rank") for n in ordered):
        print(f"\n  Strong Active Mean Rank deltas:")
        for i in range(1, len(ordered)):
            prev, curr = ordered[i-1], ordered[i]
            delta = results[curr]["strong_mean_rank"] - results[prev]["strong_mean_rank"]
            direction = "✅ 改善 (更低)" if delta < 0 else "❌ 退化 (更高)"
            print(f"    {prev}→{curr}: {delta:+.0f} ({direction})")
else:
    print("  Insufficient results for comparison")

# ════════════════════════════════════════════════════════════════
# 保存结果
# ════════════════════════════════════════════════════════════════

result_path = OUTPUT_DIR / "E44_retrieval_results.json"
output = {
    "scheme": "E44_retrieval",
    "description": "Patent active retrieval: rank pDC50>7 molecules among 100k swxds background",
    "config": {
        "pool_size": len(pool),
        "n_swxds": 100000,
        "n_active_patent": len(active_smi_set),
        "threshold_pdc50": ">7 (label_active=1)",
        "checkpoints": {k: str(v) for k, v in checkpoints.items()},
    },
    "results": results,
}
with open(result_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False, default=str)

print(f"\n  ✅ Results saved to {result_path}")

# 写入实验日志摘要
log_entry = f"""
## E44: 专利高活性分子检索实验（持续学习验证）

**日期**: 2026-07-17
**目的**: 将专利 pDC50>7 的 {len(active_smi_set)} 个高活性分子混入 100k swxds，用 E43 三轮权重排序，
        计算活性分子平均排名，看 R0→R1→R2 是否持续提升。
**评价指标**: 活性分子在 100k 池中的平均排名（越低越好）

### 结果

| 模型 | 训练数据 | 活性分子数 | Mean Rank | Median Rank | Strong Mean | <1k | <5k | <10k | >50k |
|------|---------|:---------:|:---------:|:----------:|:----------:|:---:|:---:|:----:|:----:|
"""
for name in ordered:
    r = results[name]
    sm = f"#{r['strong_mean_rank']:.0f}" if r.get('strong_mean_rank') else "N/A"
    log_entry += (f"| {name} | — | {r['n_active_found']}/{r['n_active_total']} | "
                  f"#{r['active_mean_rank']:.0f} | #{r['active_median_rank']:.0f} | "
                  f"{sm} | {r['active_pct_below_1k']} | {r['active_pct_below_5k']} | "
                  f"{r['active_pct_below_10k']} | {r['active_pct_above_50k']} |\n")

log_entry += f"\n### Δ 分析\n"
for i in range(1, len(ordered)):
    prev, curr = ordered[i-1], ordered[i]
    delta = results[curr]["active_mean_rank"] - results[prev]["active_mean_rank"]
    direction = "改善" if delta < 0 else "退化"
    log_entry += f"- **{prev}→{curr}**: {delta:+.0f} ({direction})\n"

log_entry += f"\n### 结论\n待补充"

log_path = OUTPUT_DIR / "E44_summary.md"
with open(log_path, "w") as f:
    f.write(log_entry)
print(f"  ✅ Summary saved to {log_path}")
