#!/usr/bin/env python3
"""E45 — R2 湿实验分子在 R0 vs R1 模型下的排名对比.

目的：将 19 个 R2 湿实验分子混入 100k swxds 背景,
分别用 R0 模型（仅专利训练）和 R1 模型（专利+13 R1 训练）排序，
看 R1 是否比 R0 更擅长排名 R2 分子（平均排名越低越好）。

如果 R1 的 R2 平均排名 < R0，证明 R1 标注数据帮助模型泛化到 R2 → 持续学习有效。
"""
import json, os, sys, time
from pathlib import Path

sys.path.insert(0, '/data/ye/e-drug-lab/backend')
from app.services.conda_runner import conda_run

# ── 路径 ──
GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
OUTPUT_DIR = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e45_r2_ood_100k"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Stubs ──
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

print("=" * 60)
print("  E45: R2 molecules — R0 vs R1 ranking (100k swxds)")
print("=" * 60)

# ════════════════════════════════════════════════════════════════
# Step 1: Load R2 molecules
# ════════════════════════════════════════════════════════════════

R2_POSITIVE = {"0185078(1)", "0228300", "0230953", "0228423", "LXC-201"}

with open(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
    "glare_e41_al/r2_smiles_tracking.json"
) as f:
    r2_data = json.load(f)

r2_molecules = r2_data["molecules"]  # {mol_id: smiles}
print(f"  R2 molecules: {len(r2_molecules)} ({sum(1 for k in r2_molecules if k in R2_POSITIVE)} positive)")

# ════════════════════════════════════════════════════════════════
# Step 2: Build pool (100k swxds + 19 R2, NO patent molecules)
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
        print(f"  Filtered {skipped}/{len(smiles_list)} {label}")
    return valid

print(f"\n{'='*60}")
print(f"  Step 2: Building pool (100k swxds + 19 R2)")
print(f"{'='*60}")

seen = set()
pool = []

# 100k swxds
swxds_loaded = 0
for i, row in pd.read_csv(SWXDS_CSV).iterrows():
    if swxds_loaded >= 100000:
        break
    c = norm_smi(str(row["smiles"]))
    if c and c not in seen:
        seen.add(c)
        pool.append(c)
        swxds_loaded += 1
print(f"  Loaded {swxds_loaded} swxds molecules")

# R2 分子（确保唯一）
r2_smiles_map = {}
r2_added = 0
for mid, smi in r2_molecules.items():
    c = norm_smi(smi)
    if c and c not in seen:
        seen.add(c)
        pool.append(c)
        r2_smiles_map[mid] = c
        r2_added += 1
    elif c:
        r2_smiles_map[mid] = c  # 即使已在池中也记录（极不可能）
print(f"  Added {r2_added} new R2 molecules to pool")

# Featurization filter
pool = filter_featurizable(pool, "pool")
print(f"  Pool size: {len(pool)} molecules")

# 确认 R2 分子都在池中
r2_in_pool = {}
for mid, smi in r2_smiles_map.items():
    c = norm_smi(smi)
    if c in pool:
        r2_in_pool[mid] = c
print(f"  R2 molecules in pool: {len(r2_in_pool)}/{len(r2_molecules)}")

# 保存查询文件
query_path = OUTPUT_DIR / "pool_100k_r2.json"
with open(query_path, "w") as f:
    json.dump(pool, f)

# ════════════════════════════════════════════════════════════════
# Step 3: Query R0 model
# ════════════════════════════════════════════════════════════════

E43_DIR = OUTPUT_DIR.parent / "glare_e43_progressive"
checkpoints = {
    "R0": E43_DIR / "model_R0.pt",
    "R1": E43_DIR / "model_R1.pt",
}

results = {}
for name, ckpt in checkpoints.items():
    if not ckpt.exists():
        print(f"\n  SKIP {name}: no checkpoint")
        continue

    print(f"\n{'='*60}")
    print(f"  Step 3: Querying Model_{name}")
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
        print(f"  FAILED: stdout unparseable: {proc.stderr[-400:]}")
        continue

    ranked = qr.get("ranked", [])
    rank_map = {r["smiles"]: (int(r["glare_rank"]), float(r["glare_select_prob"])) for r in ranked}
    total_ranked = len(ranked)

    # 提取 R2 分子排名
    r2_ranks = {}
    r2_pos_ranks = {}
    r2_neg_ranks = {}
    for mid, smi in r2_in_pool.items():
        if smi in rank_map:
            rank, prob = rank_map[smi]
            r2_ranks[mid] = rank
            if mid in R2_POSITIVE:
                r2_pos_ranks[mid] = rank
            else:
                r2_neg_ranks[mid] = rank

    r2_mean = float(np.mean(list(r2_ranks.values()))) if r2_ranks else 0
    r2_pos_mean = float(np.mean(list(r2_pos_ranks.values()))) if r2_pos_ranks else 0
    r2_neg_mean = float(np.mean(list(r2_neg_ranks.values()))) if r2_neg_ranks else 0
    r2_median = float(np.median(list(r2_ranks.values()))) if r2_ranks else 0

    results[name] = {
        "n_pool": len(pool),
        "n_ranked": total_ranked,
        "r2_mean_rank": r2_mean,
        "r2_median_rank": r2_median,
        "r2_pos_mean_rank": r2_pos_mean,
        "r2_neg_mean_rank": r2_neg_mean,
        "r2_min_rank": int(min(r2_ranks.values())) if r2_ranks else 0,
        "r2_max_rank": int(max(r2_ranks.values())) if r2_ranks else 0,
        "r2_separation": r2_pos_mean - r2_neg_mean if r2_pos_mean and r2_neg_mean else None,
        "query_time_s": elapsed,
        "r2_ranks_sorted": {k: int(v) for k, v in sorted(r2_ranks.items(), key=lambda x: x[1])},
    }

    pos_str = ", ".join([f"{k}:#{v}" for k, v in sorted(r2_pos_ranks.items(), key=lambda x: x[1])])
    neg_str = ", ".join([f"{k}:#{v}" for k, v in sorted(r2_neg_ranks.items(), key=lambda x: x[1])])
    print(f"  Model_{name}: R2 Mean #{r2_mean:.0f} | Pos #{r2_pos_mean:.0f} | Neg #{r2_neg_mean:.0f}")
    print(f"  Positives: {pos_str}")
    print(f"  Negatives: {neg_str}")

# ════════════════════════════════════════════════════════════════
# Step 4: 对比
# ════════════════════════════════════════════════════════════════

print(f"\n{'='*70}")
print(f"  E45: R2 OOD ranking — R0 vs R1 (100k swxds background)")
print(f"{'='*70}")

if "R0" in results and "R1" in results:
    r0, r1 = results["R0"], results["R1"]
    delta = r1["r2_mean_rank"] - r0["r2_mean_rank"]
    direction = "✅ 改善" if delta < 0 else "❌ 退化" if delta > 0 else "— 无变化"
    pct_change = delta / r0["r2_mean_rank"] * 100 if r0["r2_mean_rank"] > 0 else 0

    print(f"\n  {'指标':<25s}  {'R0模型':>10s}  {'R1模型':>10s}  {'Δ':>10s}")
    print(f"  {'-'*25}  {'-'*10}  {'-'*10}  {'-'*10}")
    print(f"  {'R2 Mean Rank':<25s}  #{r0['r2_mean_rank']:<8.0f}  #{r1['r2_mean_rank']:<8.0f}  {delta:>+9.0f}")
    print(f"  {'R2 Median Rank':<25s}  #{r0['r2_median_rank']:<8.0f}  #{r1['r2_median_rank']:<8.0f}")
    print(f"  {'R2 Pos Mean Rank':<25s}  #{r0['r2_pos_mean_rank']:<8.0f}  #{r1['r2_pos_mean_rank']:<8.0f}")
    print(f"  {'R2 Neg Mean Rank':<25s}  #{r0['r2_neg_mean_rank']:<8.0f}  #{r1['r2_neg_mean_rank']:<8.0f}")
    print(f"  {'R2 Pos-Neg Separation':<25s}  {r0.get('r2_separation', 0):>+9.0f}  {r1.get('r2_separation', 0):>+9.0f}")

    sep_delta = (r1.get('r2_separation', 0) or 0) - (r0.get('r2_separation', 0) or 0)
    sep_dir = "✅ 区分度提升" if sep_delta > 0 else "❌ 区分度下降" if sep_delta < 0 else "—"
    print(f"\n  R0→R1 Mean Rank Δ: {delta:+.0f} ({pct_change:.1f}%) {direction}")
    print(f"  R0→R1 Separation Δ: {sep_delta:+.0f} {sep_dir}")

    # 每个 R2 分子排名对比
    print(f"\n  Per-molecule rank comparison:")
    print(f"  {'Molecule':<15s}  {'Label':>6s}  {'R0 Rank':>8s}  {'R1 Rank':>8s}  {'Δ':>8s}")
    print(f"  {'-'*15}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*8}")
    for mid in sorted(r2_in_pool.keys()):
        r0r = r0.get("r2_ranks_sorted", {}).get(mid, "-")
        r1r = r1.get("r2_ranks_sorted", {}).get(mid, "-")
        label = "POS" if mid in R2_POSITIVE else "NEG"
        d = r1r - r0r if isinstance(r0r, (int, float)) and isinstance(r1r, (int, float)) else ""
        d_str = f"{d:>+8.0f}" if d != "" else "        "
        print(f"  {mid:<15s}  {label:>6s}  {str(r0r):>8s}  {str(r1r):>8s}  {d_str}")

    conclusion = "✅ 持续学习有效" if delta < 0 else "❌ 持续学习未能显著改善OOD泛化" if delta > 0 else "— 无变化"
    print(f"\n  === 结论: {conclusion} ===")
    if delta < 0:
        print(f"     训练 R1 湿实验数据后，模型对未见过的 R2 分子排名提升了 {abs(delta):.0f} 位 ({abs(pct_change):.1f}%)")
    elif delta > 0:
        print(f"     R1 模型的 R2 排名反而比 R0 差 {delta:.0f} 位 — 13 个 R1 分子信号不足以驱动跨轮泛化")
    else:
        print(f"     R0 和 R1 对 R2 的排名完全相同")

# ════════════════════════════════════════════════════════════════
# 保存结果
# ════════════════════════════════════════════════════════════════

result_path = OUTPUT_DIR / "E45_r2_ood_results.json"
output = {
    "scheme": "E45_r2_ood",
    "description": "R2 molecules OOD ranking: R0 vs R1 model, 100k swxds background",
    "config": {
        "pool_size": len(pool),
        "n_swxds": 100000,
        "n_r2": len(r2_in_pool),
        "n_r2_positive": len([m for m in r2_in_pool if m in R2_POSITIVE]),
        "n_r2_negative": len([m for m in r2_in_pool if m not in R2_POSITIVE]),
        "strict_ood": "R0从未见过R1/R2, R1从未见过R2",
    },
    "results": results,
}
with open(result_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False, default=str)

print(f"\n  ✅ Results: {result_path}")
print(f"  Done at {time.strftime('%H:%M:%S')}")
