#!/usr/bin/env python3
"""E43 — 累积训练验证持续学习：R0(403) → R1(+13 R1) → R2(+19 R2).

目的：排除 AL 选择偏差，用完全相同的训练方法 + 累积增量数据，
在固定评价基准上证明 R1→R2→R3 持续 RL 让模型能力逐步提升。

流程:
  1. 构建 3 个累积数据集 (R0, R1, R2)
  2. 子进程训练 3 个模型 (glare_gnn_cli.py, GRPO, 50 epochs, disable_ig)
  3. 同一 pool 上查询 19 R2 + 13 R1 排名
  4. 输出对比报告

预期: R2 Mean Rank 单调递减: R0 ~#6000 > R1 ~#4000 > R2 ~#500
"""
import json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, '/data/ye/e-drug-lab/backend')
from app.services.conda_runner import conda_run

# ── 路径 ──
GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
OUTPUT_DIR = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e43_progressive"
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
# GLARE path
sys.path.insert(0, GLARE_ROOT)

# ── 标签定义 ──
R2_LABELS = {
    "0185078(1)": 1, "0228300": 1, "0230953": 1, "0228423": 1, "LXC-201": 1,
    "0228274": 0, "0228325": 0, "0228413": 0, "0228419": 0, "0228429": 0,
    "0230500": 0, "0230853": 0, "0230915": 0, "0230922": 0, "0230994": 0,
    "0231000": 0, "0376960": 0, "LXC-206": 0, "LXC-305": 0,
}
R1_POSITIVE_IDS = {"0228390", "0228414", "LXC-106"}  # 13 个 R1 中的正样本

# ════════════════════════════════════════════════════════════════
# Step 0: 构建累积数据集
# ════════════════════════════════════════════════════════════════

def load_patent_data():
    """加载 403 专利分子，排除 borderline (label_active=-1)"""
    df = pd.read_csv(
        "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv"
    )
    records = []
    for _, row in df.iterrows():
        label = int(row["label_active"])
        if label == -1:
            continue  # borderline pDC50 6.0-7.0, 不参与训练
        records.append({
            "smiles": str(row["canonical_smiles"]),
            "label": label,
            "weight": 5.0 if label == 1 else 1.0,
        })
    return records


def load_r1_data():
    """加载 13 个 R1 湿实验分子（真实标签）"""
    df = pd.read_csv(
        "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
        "glare_e26_patent_320_83_20260630/data/new_13_molecules.csv"
    )
    records = []
    for _, row in df.iterrows():
        mid = str(row["SDF_ID"])
        label = 1 if mid in R1_POSITIVE_IDS else 0
        records.append({
            "smiles": str(row["SMILES"]),
            "label": label,
            "weight": 5.0 if label == 1 else 1.0,
            "mol_id": mid,
        })
    return records


def load_r2_data():
    """加载 19 个 R2 分子（用户湿实验标签：5 正 14 负）"""
    with open(
        "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
        "glare_e41_al/r2_smiles_tracking.json"
    ) as f:
        r2_map = json.load(f)["molecules"]
    records = []
    for mid, smi in r2_map.items():
        label = R2_LABELS.get(mid, 0)
        records.append({
            "smiles": smi,
            "label": label,
            "weight": 5.0 if label == 1 else 1.0,
            "mol_id": mid,
        })
    return records


def dedup_records(existing, new_records):
    """按 canonical SMILES 去重（已存在的跳过）"""
    from rdkit import Chem
    seen = set()
    for r in existing:
        mol = Chem.MolFromSmiles(r["smiles"])
        if mol:
            seen.add(Chem.MolToSmiles(mol))
    added = 0
    for r in new_records:
        mol = Chem.MolFromSmiles(r["smiles"])
        if mol:
            can = Chem.MolToSmiles(mol)
            if can not in seen:
                seen.add(can)
                existing.append({"smiles": can, "label": r["label"], "weight": r["weight"]})
                added += 1
    return added


# 加载原始数据
print("=" * 60)
print("  Step 0: Building cumulative datasets")
print("=" * 60)

patent_recs = load_patent_data()
r1_recs = load_r1_data()
r2_recs = load_r2_data()

print(f"  Patent: {len(patent_recs)} molecules "
      f"({sum(1 for r in patent_recs if r['label']==1)} active)")
print(f"  R1:     {len(r1_recs)} molecules "
      f"({sum(1 for r in r1_recs if r['label']==1)} active)")
print(f"  R2:     {len(r2_recs)} molecules "
      f"({sum(1 for r in r2_recs if r['label']==1)} active)")

# 构建累积数据集
datasets = {}
for name, add_recs in [("R0", []), ("R1", r1_recs), ("R2", r2_recs)]:
    recs = [dict(r) for r in patent_recs]  # 深拷贝
    added = dedup_records(recs, add_recs)
    datasets[name] = recs
    n_pos = sum(1 for r in recs if r["label"] == 1)
    print(f"  {name}: {len(recs)} molecules ({n_pos} positive, +{added} new)")

# 保存数据集
for name, recs in datasets.items():
    data_path = OUTPUT_DIR / f"dataset_{name}.json"
    with open(data_path, "w") as f:
        json.dump(recs, f, indent=2)

# ════════════════════════════════════════════════════════════════
# Step 1: 训练 3 个模型
# ════════════════════════════════════════════════════════════════

TRAIN_ARGS = [
    "python", "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "train",
    "--epochs", "50", "--ensemble", "3", "--batch_size", "64",
    "--strategy", "grpo", "--l2_lambda", "3e-4", "--lr", "3e-4", "--disable-ig",
]

for name in ["R0", "R1", "R2"]:
    ckpt_path = OUTPUT_DIR / f"model_{name}.pt"
    data_path = OUTPUT_DIR / f"dataset_{name}.json"

    if ckpt_path.exists():
        print(f"\n  SKIP Model_{name}: checkpoint exists ({ckpt_path})")
        continue

    print(f"\n{'='*60}")
    print(f"  Step 1: Training Model_{name}")
    print(f"  Data: {len(datasets[name])} molecules -> {ckpt_path}")
    print(f"{'='*60}")

    proc = conda_run("diffgui_new", TRAIN_ARGS + [
        "--ckpt", str(ckpt_path), "--data", str(data_path),
    ], extra_env={"PYTHONPATH": "/data/ye/e-drug-lab/backend"})

    try:
        result_line = proc.stdout.strip().splitlines()[-1]
        result = json.loads(result_line)
        print(f"  Train OK: {result}")
    except (json.JSONDecodeError, IndexError):
        err = proc.stderr[-300:] if proc.stderr else "(no stderr)"
        print(f"  WARNING: stdout parse failed, but checkpoint may exist")
        print(f"  stderr: {err}")

# ════════════════════════════════════════════════════════════════
# Step 2: 构建评价 Pool
# ════════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print(f"  Step 2: Building evaluation pool")
print(f"{'='*60}")


sys.path.insert(0, GLARE_ROOT)
from utils.utils import check_featurizability


def filter_featurizable(smiles_list, label="molecules"):
    """过滤出 GLARE 可 featurize 的分子（跳过金属原子等）"""
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


def load_pool_data(pool_size=10000):
    """构建固定评价 Pool（10k swxds + 所有已标注分子）"""
    SWXDS_CSV = OUTPUT_DIR.parent / "glare_e41_al" / "swxds_250k_smiles.csv"
    from rdkit import Chem

    def norm(smi):
        mol = Chem.MolFromSmiles(smi)
        return Chem.MolToSmiles(mol) if mol else ""

    seen = set()
    pool = []

    # swxds 背景分子
    if SWXDS_CSV.exists():
        raw_smiles = []
        for i, row in pd.read_csv(SWXDS_CSV).iterrows():
            if len(raw_smiles) >= pool_size * 2:  # 多取一些以补偿过滤
                break
            c = norm(str(row["smiles"]))
            if c and c not in seen:
                seen.add(c)
                raw_smiles.append(c)

        # 过滤不可 featurize 的分子
        valid = filter_featurizable(raw_smiles, "swxds background")
        pool = valid[:pool_size]
    else:
        print(f"  WARNING: {SWXDS_CSV} not found, pool may be smaller")

    # 所有训练分子
    all_recs = datasets["R2"]
    for r in all_recs:
        c = norm(r["smiles"])
        if c and c not in seen:
            seen.add(c)
            pool.append(c)

    return pool


pool = load_pool_data()
print(f"  Pool size: {len(pool)} molecules")

# R2/R1 查询分子
r2_smiles = [r["smiles"] for r in r2_recs]
r1_smiles = [r["smiles"] for r in r1_recs]


def dedup_ordered(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


all_for_query = dedup_ordered(pool + r2_smiles + r1_smiles)
query_path = OUTPUT_DIR / "query_smiles.json"
with open(query_path, "w") as f:
    json.dump(all_for_query, f)

print(f"  Query set: {len(all_for_query)} molecules "
      f"(R2: {len(r2_smiles)}, R1: {len(r1_smiles)})")

# ════════════════════════════════════════════════════════════════
# Step 3: 查询所有模型
# ════════════════════════════════════════════════════════════════

results = {}
for name in ["R0", "R1", "R2"]:
    ckpt_path = OUTPUT_DIR / f"model_{name}.pt"
    if not ckpt_path.exists():
        print(f"\n  SKIP {name}: checkpoint not found at {ckpt_path}")
        continue

    print(f"\n{'='*60}")
    print(f"  Step 3: Querying Model_{name}")
    print(f"{'='*60}")

    proc = conda_run("diffgui_new", [
        "python", "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "query",
        "--ckpt", str(ckpt_path), "--smiles", str(query_path), "--ensemble", "3",
    ], extra_env={"PYTHONPATH": "/data/ye/e-drug-lab/backend"})

    try:
        qr = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        print(f"  FAILED: query stdout unparseable: {proc.stderr[-400:]}")
        continue

    ranked = qr.get("ranked", [])
    rank_map = {r["smiles"]: int(r["glare_rank"]) for r in ranked}

    # ── R2 ranks ──
    r2_ranks = {}
    for rec in r2_recs:
        rank = rank_map.get(rec["smiles"])
        if rank:
            r2_ranks[rec["mol_id"]] = rank
        else:
            print(f"  WARNING: R2 molecule {rec['mol_id']} not found in query results")

    r2_mean = float(np.mean(list(r2_ranks.values()))) if r2_ranks else 0
    r2_pos_ranks = [v for k, v in r2_ranks.items() if R2_LABELS.get(k, 0) == 1]
    r2_neg_ranks = [v for k, v in r2_ranks.items() if R2_LABELS.get(k, 0) == 0]

    # ── R1 ranks ──
    r1_ranks = {}
    for rec in r1_recs:
        rank = rank_map.get(rec["smiles"])
        if rank:
            r1_ranks[rec["mol_id"]] = rank

    r1_mean = float(np.mean(list(r1_ranks.values()))) if r1_ranks else 0
    r1_pos_ranks = [v for k, v in r1_ranks.items() if k in R1_POSITIVE_IDS]
    r1_neg_ranks = [v for k, v in r1_ranks.items() if k not in R1_POSITIVE_IDS]

    results[name] = {
        "n_train": len(datasets[name]),
        "n_pool": len(all_for_query),
        "r2_mean_rank": r2_mean,
        "r2_pos_mean_rank": float(np.mean(r2_pos_ranks)) if r2_pos_ranks else 0,
        "r2_neg_mean_rank": float(np.mean(r2_neg_ranks)) if r2_neg_ranks else 0,
        "r2_spread": max(r2_ranks.values()) - min(r2_ranks.values()) if r2_ranks else 0,
        "r1_mean_rank": r1_mean,
        "r1_pos_mean_rank": float(np.mean(r1_pos_ranks)) if r1_pos_ranks else 0,
        "r1_neg_mean_rank": float(np.mean(r1_neg_ranks)) if r1_neg_ranks else 0,
        "r2_ranks": {k: int(v) for k, v in sorted(r2_ranks.items(), key=lambda x: x[1])},
        "r1_ranks": {k: int(v) for k, v in sorted(r1_ranks.items(), key=lambda x: x[1])},
    }

    # 打印当前模型结果
    print(f"  Model_{name}: R2 Mean #{r2_mean:.0f}  |  "
          f"R1 Mean #{r1_mean:.0f}  |  "
          f"Train: {len(datasets[name])} mols")

# ════════════════════════════════════════════════════════════════
# Step 4: 对比报告
# ════════════════════════════════════════════════════════════════

print(f"\n{'='*70}")
print(f"  E43 Progressive RL: Cumulative Training Results")
print(f"{'='*70}")

if len(results) > 1:
    print(f"\n{'Model':>10s}  {'Train':>6s}  {'R2 Mean':>10s}  {'R2 Pos':>10s}  "
          f"{'R2 Neg':>10s}  {'Spread':>8s}  {'R1 Mean':>10s}")
    print(f"{'-'*10}  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*10}")
    for name in ["R0", "R1", "R2"]:
        if name not in results:
            continue
        r = results[name]
        print(f"{name:>10s}  {r['n_train']:>6d}  #{r['r2_mean_rank']:<8.0f}  "
              f"#{r['r2_pos_mean_rank']:<8.0f}  #{r['r2_neg_mean_rank']:<8.0f}  "
              f"{r['r2_spread']:>7.0f}  #{r['r1_mean_rank']:<8.0f}")

    # Δ 分析
    ordered = [n for n in ["R0", "R1", "R2"] if n in results]
    print(f"\n  R2 Mean Rank deltas:")
    for i in range(1, len(ordered)):
        prev, curr = ordered[i-1], ordered[i]
        delta = results[curr]["r2_mean_rank"] - results[prev]["r2_mean_rank"]
        direction = "✅ 改善" if delta < 0 else "❌ 退化"
        print(f"    {prev}→{curr}: {delta:+.0f} ({direction})")

    # 与 E37b/E41b-Chase/E42 对比
    print(f"\n  Cross-experiment comparison (R2 Mean Rank):")
    ref = {"E34": 6583, "E37b": 4174, "E41b-Chase": 407, "E42": 549}
    for exp, rank in ref.items():
        print(f"    {exp:>15s}: #{rank}")

# ════════════════════════════════════════════════════════════════
# 保存结果
# ════════════════════════════════════════════════════════════════

result_path = OUTPUT_DIR / "progressive_results.json"
output = {
    "scheme": "E43_progressive",
    "description": "Cumulative training proof: R0(403) → R1(+13 R1) → R2(+19 R2)",
    "config": {
        "strategy": "grpo",
        "ensemble": 3,
        "epochs": 50,
        "disable_ig": True,
        "lr": "3e-4",
        "l2_lambda": "3e-4",
    },
    "results": results,
    "pool_size": len(pool),
    "query_size": len(all_for_query),
    "reference": {
        "E34": 6583,
        "E37b": 4174,
        "E41b_Chase": 407,
        "E42": 549,
    },
}
with open(result_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False, default=str)

print(f"\n{'='*60}")
print(f"  ✅ Results saved to {result_path}")
print(f"  ✅ Checkpoints in {OUTPUT_DIR}")
print(f"{'='*60}")
