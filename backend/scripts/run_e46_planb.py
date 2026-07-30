#!/usr/bin/env python3
"""E46 — Plan B: Active retrieval with distractor negatives.

池: 100k swxds + 403 patent (全量) + 13 R1 + 19 R2
查询: R0, R1, R2
指标:
  1. 309 专利活性分子 (pDC50>7) 的平均排名
  2. 专利活性分子 vs 专利非活性分子的分离度
  3. 所有已知活性分子 (patent+R1+R2 positives) 的累积召回率
"""
import json, os, sys, time
from pathlib import Path

sys.path.insert(0, '/data/ye/e-drug-lab/backend')
from app.services.conda_runner import conda_run

GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
OUTPUT_DIR = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e46_planb"
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
print("  E46 Plan B: Active retrieval with negatives")
print("=" * 60)

# ════════════════════════════════════════════════════════════════
# Step 1: Label definitions
# ════════════════════════════════════════════════════════════════

R1_POSITIVE = {"0228390", "0228414", "LXC-106"}
R2_POSITIVE = {"0185078(1)", "0228300", "0230953", "0228423", "LXC-201"}

ALL_R1_LABELS = {mid: (1 if mid in R1_POSITIVE else 0) for mid in [
    "0228271", "0228279", "0228283", "0228303", "0228366",
    "0228390", "0228405", "0228414", "0228416", "0228417",
    "LXC-102", "LXC-104", "LXC-106"
]}

ALL_R2_LABELS = {
    "0185078(1)": 1, "0228300": 1, "0230953": 1, "0228423": 1, "LXC-201": 1,
    "0228274": 0, "0228325": 0, "0228413": 0, "0228419": 0, "0228429": 0,
    "0230500": 0, "0230853": 0, "0230915": 0, "0230922": 0, "0230994": 0,
    "0231000": 0, "0376960": 0, "LXC-206": 0, "LXC-305": 0,
}

# ════════════════════════════════════════════════════════════════
# Step 2: Load all molecules
# ════════════════════════════════════════════════════════════════

def norm_smi(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else ""

def filter_featurizable(smiles_list, label=""):
    valid, skipped = [], 0
    for smi in smiles_list:
        if check_featurizability(str(smi)):
            valid.append(str(smi))
        else:
            skipped += 1
    if skipped:
        print(f"  Filtered {skipped}/{len(smiles_list)} {label}")
    return valid

print(f"\n  Loading patent data...")
patent_df = pd.read_csv(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv"
)

# 记录专利分子信息
patent_mols = {}  # canonical_smiles -> {mol_id, label, pdc50, strong}
for _, row in patent_df.iterrows():
    c = norm_smi(row["canonical_smiles"])
    label = int(row["label_active"])
    patent_mols[c] = {
        "mol_id": row["molecule_id"],
        "label": 1 if label == 1 else 0,  # label_active=1 → active, 0/-1 → inactive
        "pdc50_raw": row["pdc50_raw"],
        "strong": 1 if row["strong_active"] == 1 else 0,
    }

patent_pos = {smi for smi, info in patent_mols.items() if info["label"] == 1}
patent_neg = {smi for smi, info in patent_mols.items() if info["label"] == 0}
strong_active = {smi for smi, info in patent_mols.items() if info["strong"] == 1}

print(f"  Patent: {len(patent_mols)} total, {len(patent_pos)} pos, {len(patent_neg)} neg")
print(f"  Strong active (pDC50>8): {len(strong_active)}")

# 加载 R1
print(f"  Loading R1 data...")
r1_df = pd.read_csv(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
    "glare_e26_patent_320_83_20260630/data/new_13_molecules.csv"
)
r1_mols = {}
for _, row in r1_df.iterrows():
    mid = str(row["SDF_ID"])
    c = norm_smi(str(row["SMILES"]))
    label = ALL_R1_LABELS.get(mid, 0)
    r1_mols[c] = {"mol_id": mid, "label": label}

# 加载 R2
print(f"  Loading R2 data...")
with open(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
    "glare_e41_al/r2_smiles_tracking.json"
) as f:
    r2_raw = json.load(f)["molecules"]
r2_mols = {}
for mid, smi in r2_raw.items():
    c = norm_smi(smi)
    label = ALL_R2_LABELS.get(mid, 0)
    r2_mols[c] = {"mol_id": mid, "label": label}

# ════════════════════════════════════════════════════════════════
# Step 3: Build pool
# ════════════════════════════════════════════════════════════════

SWXDS_CSV = OUTPUT_DIR.parent / "glare_e41_al" / "swxds_250k_smiles.csv"

print(f"\n{'='*60}")
print(f"  Building pool: 100k swxds + 403 patent + 13 R1 + 19 R2")
print(f"{'='*60}")

seen = set()
pool = []

# swxds
swxds_n = 0
for i, row in pd.read_csv(SWXDS_CSV).iterrows():
    if swxds_n >= 100000:
        break
    c = norm_smi(str(row["smiles"]))
    if c and c not in seen:
        seen.add(c)
        pool.append(c)
        swxds_n += 1
print(f"  swxds: {swxds_n}")

# patent (all 403)
pat_added = 0
for smi, info in patent_mols.items():
    if smi not in seen:
        seen.add(smi)
        pool.append(smi)
        pat_added += 1
    else:
        print(f"  WARNING: patent molecule {info['mol_id']} already in swxds")
print(f"  patent added: {pat_added}/{len(patent_mols)}")

# R1
r1_added = 0
for smi, info in r1_mols.items():
    if smi not in seen:
        seen.add(smi)
        pool.append(smi)
        r1_added += 1
print(f"  R1 added: {r1_added}/{len(r1_mols)}")

# R2
r2_added = 0
for smi, info in r2_mols.items():
    if smi not in seen:
        seen.add(smi)
        pool.append(smi)
        r2_added += 1
print(f"  R2 added: {r2_added}/{len(r2_mols)}")

# Featurization filter
pool = filter_featurizable(pool, "pool total")
print(f"  Pool size: {len(pool)}")

# 保存
query_path = OUTPUT_DIR / "pool_100k_all_labeled.json"
with open(query_path, "w") as f:
    json.dump(pool, f)

# 建立反向索引: smiles → mol info
mol_info = {}
for smi, info in patent_mols.items():
    mol_info[smi] = {"source": "patent", **info}
for smi, info in r1_mols.items():
    mol_info[smi] = {"source": "r1", **info}
for smi, info in r2_mols.items():
    mol_info[smi] = {"source": "r2", **info}

# ════════════════════════════════════════════════════════════════
# Step 4: Query all three models
# ════════════════════════════════════════════════════════════════

E43_DIR = OUTPUT_DIR.parent / "glare_e43_progressive"
checkpoints = {
    "R0": E43_DIR / "model_R0.pt",
    "R1": E43_DIR / "model_R1.pt",
    "R2": E43_DIR / "model_R2.pt",
}

results = {}
for name, ckpt in checkpoints.items():
    if not ckpt.exists():
        print(f"\n  SKIP {name}")
        continue

    print(f"\n{'='*60}")
    print(f"  Querying Model_{name} ({ckpt.name})")
    print(f"{'='*60}")

    t0 = time.time()
    proc = conda_run("diffgui_new", [
        "python", "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "query",
        "--ckpt", str(ckpt), "--smiles", str(query_path), "--ensemble", "3",
    ], extra_env={"PYTHONPATH": "/data/ye/e-drug-lab/backend"},
    timeout=1800)
    elapsed = time.time() - t0

    try:
        qr = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        print(f"  FAILED: {proc.stderr[-400:]}")
        continue

    ranked = qr.get("ranked", [])
    rank_map = {r["smiles"]: {"rank": int(r["glare_rank"]), "score": float(r.get("glare_select_prob", 0))}
                 for r in ranked}

    # ── 提取各集合排名 ──
    pat_pos_ranks = {smi: rank_map[smi] for smi in patent_pos if smi in rank_map}
    pat_neg_ranks = {smi: rank_map[smi] for smi in patent_neg if smi in rank_map}
    strong_ranks = {smi: rank_map[smi] for smi in strong_active if smi in rank_map}

    # 对每个分子的标签赋权
    def calc_group_stats(smiles_set, rank_map):
        data = [(smi, rank_map[smi]) for smi in smiles_set if smi in rank_map]
        if not data:
            return {}
        ranks = np.array([d[1]["rank"] for d in data])
        scores = np.array([d[1]["score"] for d in data])
        return {
            "n": len(data),
            "mean_rank": float(np.mean(ranks)),
            "median_rank": float(np.median(ranks)),
            "min_rank": int(np.min(ranks)),
            "max_rank": int(np.max(ranks)),
            "mean_score": float(np.mean(scores)),
            "median_score": float(np.median(scores)),
        }

    stats = {
        "patent_pos": calc_group_stats(patent_pos, rank_map),
        "patent_neg": calc_group_stats(patent_neg, rank_map),
        "strong_active": calc_group_stats(strong_active, rank_map),
    }

    # 计算 patent 正负分离度
    pos_rank = stats["patent_pos"].get("mean_rank", 0)
    neg_rank = stats["patent_neg"].get("mean_rank", 0)
    pos_score = stats["patent_pos"].get("mean_score", 0)
    neg_score = stats["patent_neg"].get("mean_score", 0)
    rank_sep = neg_rank - pos_rank  # 正值 = 活性排得更高
    score_sep = pos_score - neg_score  # 正值 = 活性得分更高

    stats["rank_separation"] = rank_sep
    stats["score_separation"] = score_sep

    # 已知活性分子 top-k 召回率
    all_pos_smiles = patent_pos | {smi for smi, info in r1_mols.items() if info["label"] == 1} | \
                     {smi for smi, info in r2_mols.items() if info["label"] == 1}
    all_pos_ranks = [(smi, rank_map[smi]["rank"]) for smi in all_pos_smiles if smi in rank_map]
    all_pos_ranks_sorted = sorted(all_pos_ranks, key=lambda x: x[1])

    recall = {}
    for k in [10, 50, 100, 200, 500, 1000, 5000]:
        n_recalled = sum(1 for _, r in all_pos_ranks_sorted if r <= k)
        recall[f"recall_top{k}"] = n_recalled

    stats["recall"] = recall
    stats["query_time_s"] = elapsed
    stats["n_pool"] = len(pool)

    results[name] = stats

    print(f"  Patent pos mean rank: #{pos_rank:.0f} (score: {pos_score:.4f})")
    print(f"  Patent neg mean rank: #{neg_rank:.0f} (score: {neg_score:.4f})")
    print(f"  Rank separation: {rank_sep:+.0f}  |  Score separation: {score_sep:+.4f}")
    print(f"  Strong active mean rank: #{stats['strong_active'].get('mean_rank', 0):.0f}")
    print(f"  Recall @500: {recall.get('recall_top500', 0)}/{len(all_pos_smiles)} actives")

# ════════════════════════════════════════════════════════════════
# Step 5: Summary
# ════════════════════════════════════════════════════════════════

print(f"\n{'='*70}")
print(f"  E46 Plan B: Progressive improvement summary")
print(f"{'='*70}")

ordered = [n for n in ["R0", "R1", "R2"] if n in results]

if len(results) > 1:
    print(f"\n{'Metric':<35s}  {'R0':>10s}  {'R1':>10s}  {'R2':>10s}  {'Trend':>10s}")
    print(f"{'-'*35}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*10}")

    metrics = [
        ("Patent Pos Mean Rank", "patent_pos", "mean_rank", "↓"),
        ("Patent Neg Mean Rank", "patent_neg", "mean_rank", "↑"),
        ("Strong Active Mean Rank", "strong_active", "mean_rank", "↓"),
        ("Rank Separation (neg-pos)", None, "rank_separation", "↑"),
        ("Score Separation (pos-neg)", None, "score_separation", "↑"),
        ("Patent Pos Mean Score", "patent_pos", "mean_score", "↑"),
        ("Patent Neg Mean Score", "patent_neg", "mean_score", "↓"),
        ("Strong Active Mean Score", "strong_active", "mean_score", "↑"),
    ]

    for label, group, key, direction in metrics:
        vals = []
        for name in ordered:
            if group:
                v = results[name].get(group, {}).get(key, "N/A")
            else:
                v = results[name].get(key, "N/A")
            vals.append(v)
        val_strs = [f"{v:<10}" if isinstance(v, str) else f"#{v:<8.0f}" if "rank" in label.lower() and isinstance(v, (int, float)) else f"{v:<10.4f}" if isinstance(v, float) else str(v) for v in vals]
        print(f"  {label:<35s}  {val_strs[0]:>10s}  {val_strs[1]:>10s}  {val_strs[2]:>10s}  {direction:>10s}")

    # Recall comparison
    print(f"\n  {'Recall @top-k':<35s}  {'R0':>10s}  {'R1':>10s}  {'R2':>10s}")
    print(f"  {'-'*35}  {'-'*10}  {'-'*10}  {'-'*10}")
    for k in [10, 50, 100, 200, 500, 1000, 5000]:
        recall_vals = []
        for name in ordered:
            r = results[name].get("recall", {}).get(f"recall_top{k}", 0)
            recall_vals.append(r)
        print(f"  {'Top-'+str(k):<35s}  {recall_vals[0]:>10d}  {recall_vals[1]:>10d}  {recall_vals[2]:>10d}")

    # Δ analysis
    print(f"\n  Patent Pos Mean Rank deltas:")
    for i in range(1, len(ordered)):
        prev, curr = ordered[i-1], ordered[i]
        delta = results[curr]["patent_pos"]["mean_rank"] - results[prev]["patent_pos"]["mean_rank"]
        direction = "✅ 改善" if delta < 0 else "❌ 退化"
        print(f"    {prev}→{curr}: {delta:+.0f} {direction}")

    print(f"\n  Patent Pos-Neg Rank Separation:")
    for i in range(len(ordered)):
        name = ordered[i]
        sep = results[name]["rank_separation"]
        print(f"    {name}: {sep:+.0f}")

    print(f"\n  Patent Pos-Neg Score Separation:")
    for i in range(len(ordered)):
        name = ordered[i]
        sep = results[name]["score_separation"]
        print(f"    {name}: {sep:+.4f}")

# 保存
result_path = OUTPUT_DIR / "E46_planb_results.json"
output = {
    "scheme": "E46_planb",
    "description": "Active retrieval with distractor negatives: 100k swxds + 403 patent + 13 R1 + 19 R2",
    "config": {
        "pool_size": len(pool),
        "n_swxds": 100000,
        "n_patent": len(patent_mols),
        "n_patent_pos": len(patent_pos),
        "n_patent_neg": len(patent_neg),
        "n_strong": len(strong_active),
        "n_r1": len(r1_mols),
        "n_r2": len(r2_mols),
    },
    "results": results,
}
with open(result_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False, default=str)

print(f"\n  ✅ {result_path}")
print(f"  Done at {time.strftime('%H:%M:%S')}")
