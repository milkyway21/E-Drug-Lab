#!/usr/bin/env python3
"""E41b 追赶 E37b：AL 选择 192 个训练分子 + 50 epochs 训练 + R2 排序。

流程:
  1. E41b AL 跑 2 cycles → 选出 192 个训练分子
  2. 用 glare_gnn_cli.py 子进程在 192 个分子上训练 50 epochs
  3. 查询 19 R2 分子在 10k 池中的排名

输出: Mean Rank 直接对比 E37b #4174
"""
import json, os, sys, time, tempfile
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, '/data/ye/e-drug-lab/backend')
from app.services.conda_runner import conda_run

# ── GLARE 环境 ──
GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
OUTPUT_DIR = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al")
sys.path.insert(0, GLARE_ROOT)
os.chdir(GLARE_ROOT)

# ── Stubs（必须在 import GLARE 前注入） ──
import types
try: import torch_sparse  # noqa
except:
    ts=types.ModuleType("torch_sparse")
    try:
        from torch_geometric.typing import SparseTensor as _ST
        if _ST is not None: ts.SparseTensor=_ST
    except: pass
    sys.modules["torch_sparse"]=ts
try: import captum  # noqa
except:
    cm,am=types.ModuleType("captum"),types.ModuleType("captum.attr")
    import torch as _t
    class _S:
        def __init__(s,*a,**k): pass
        def attribute(s,*a,**k): return _t.zeros_like(a[0]),_t.tensor(0.0)
    am.IntegratedGradients=_S;cm.attr=am
    sys.modules["captum"]=cm;sys.modules["captum.attr"]=am

# ── 加载之前 E41b 的 pool 和选中的训练分子 ──
from rdkit import Chem
R2_TRACKING = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al/r2_smiles_tracking.json"
with open(R2_TRACKING) as f:
    r2_map = json.load(f)["molecules"]
r2_smiles_set = set(r2_map.values())

# 重新构建 pool（与 E41b 相同逻辑）
def load_pool_data(pool_size=10000):
    import pandas as pd
    from rdkit import Chem
    SWXDS_CSV = OUTPUT_DIR / "swxds_250k_smiles.csv"
    PATENT_CSV = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv"
    WETLAB_CSV = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e26_patent_320_83_20260630/data/new_13_molecules.csv"
    POSITIVE_IDS = {"0228390", "0228414", "LXC-106"}

    def norm(smi):
        mol = Chem.MolFromSmiles(smi)
        return Chem.MolToSmiles(mol) if mol else ""

    seen = set()
    pool = []  # (smiles, label, is_r2, mol_id)

    for i, row in pd.read_csv(SWXDS_CSV).iterrows():
        if i >= pool_size: break
        c = norm(str(row["smiles"]))
        if c and c not in seen:
            seen.add(c); pool.append((c, 0, False, ""))

    for _, row in pd.read_csv(PATENT_CSV).iterrows():
        c = norm(str(row["canonical_smiles"]))
        if not c or c in seen: continue
        seen.add(c); pool.append((c, int(row["label_active"]), False, f"PAT-{row.get('molecule_id','')}"))

    for _, row in pd.read_csv(WETLAB_CSV).iterrows():
        c = norm(str(row["SMILES"]))
        if not c or c in seen: continue
        lab = 1 if str(row["SDF_ID"]) in POSITIVE_IDS else 0
        seen.add(c); pool.append((c, lab, False, str(row["SDF_ID"])))

    for mid, smi in r2_map.items():
        c = norm(str(smi))
        if not c: continue
        if c in seen:
            for j, (s, l, r, m) in enumerate(pool):
                if s == c: pool[j] = (s, l, True, mid); break
        else:
            seen.add(c); pool.append((c, 1, True, mid))

    return pool

# ── 步骤 1: E41b AL 选择 ──
print("="*70)
print("  Step 1: E41b Active Learning (select 192 training molecules)")
print("="*70)
pool = load_pool_data()
print(f"Pool: {len(pool)} molecules")

import torch
from argparse import Namespace
from torch.utils.data import WeightedRandomSampler
from utils.utils import molecular_graph_featurizer, smiles_to_ecfp, check_featurizability, to_torch_dataloader
from model import Ensemble
from acquisition import acquire

# Build graphs
print("Building graphs...")
graphs, labels, smiles_list, is_r2_list = [], [], [], []
for smi, lab, is_r2, mid in pool:
    if not check_featurizability(smi): continue
    fp = smiles_to_ecfp([smi], silent=True)
    g = molecular_graph_featurizer(smi, y=lab, fp=fp[0])
    if isinstance(g, str): continue
    g.fp = torch.tensor([fp[0]], dtype=torch.float32)
    g.xp = g.x; g.edgep_index = g.edge_index
    g.edgep_attr = getattr(g, "edge_attr", torch.empty((0,2), dtype=torch.long))
    graphs.append(g); labels.append(lab); smiles_list.append(smi)
    is_r2_list.append(is_r2)

labels_t = torch.tensor(labels, dtype=torch.long)
smiles_arr = np.array(smiles_list)
n_total = len(graphs)

# AL 选择（与 E41b 相同）
import gc
np.random.seed(42)
hit_idx = np.where(labels_t.numpy() == 1)[0]
train_idx = np.concatenate([np.random.choice(hit_idx, 1), np.random.choice(n_total, 63)]).tolist()
screen_idx = [i for i in range(n_total) if i not in train_idx]

args = Namespace(architecture="ginl", strategy="grpo", epochs=50, hidden_dim=1024,
    output_dim=2, mol_emb_dim=130, lr=3e-4, weight_decay=0.0,
    train_batch_size=64, infer_batch_size=512, ensemble_size=3, seed=0, disable_ig=True,
    anchored=True, l2_lambda=3e-4, grpo_lambda=7e-2, grpo_epsilon=2e-1, grpo_beta=1e-2,
    retrain=1, mode="a", cuda="0",
    mlp_fc_layer=3, gin_graph_conv_layer=3, gin_x_fc_layer=3, gin_fp_fc_layer=3,
    gcn_graph_conv_layer=5, gcn_x_fc_layer=3, gine_graph_conv_layer=3, gine_x_fc_layer=1, gine_fp_fc_layer=1,
    pretrain_file="", model_save_file="")

for cycle_i in range(1, 3):
    t0 = time.time()
    train_graphs = [graphs[i] for i in train_idx]
    train_y = labels_t[train_idx].clamp(0, 1)
    n_pos = int((train_y == 1).sum()); n_neg = int((train_y == 0).sum())
    cw = [1-n_pos/max(len(train_y),1), 1-n_neg/max(len(train_y),1)]
    weights = [cw[int(yi)] for yi in train_y]
    sampler = WeightedRandomSampler(weights, num_samples=len(train_y), replacement=True)
    train_balanced = to_torch_dataloader(train_graphs, train_y.numpy(),
        batch_size=64, sampler=sampler, shuffle=False, pin_memory=False)
    model = Ensemble(args)
    model.train(train_balanced)

    screen_graphs = [graphs[i] for i in screen_idx]
    screen_y = labels_t[screen_idx].numpy()
    screen_loader = to_torch_dataloader(screen_graphs, screen_y,
        batch_size=512, shuffle=False, pin_memory=False)
    screen_logits = model.predict(screen_loader)

    screen_smiles = smiles_arr[screen_idx]
    mean_probs = torch.mean(torch.exp(screen_logits), dim=1)[:, 1].cpu()
    random_val = torch.rand(mean_probs.shape[0])
    pick_flag = torch.where(mean_probs - random_val > 0, torch.ones_like(mean_probs), torch.zeros_like(mean_probs))
    scored = mean_probs + pick_flag
    local_pick = torch.argsort(scored, descending=True)[:64]
    smiles_pick = screen_smiles[local_pick.cpu().numpy()]

    for s in smiles_pick:
        idx = int(np.where(smiles_arr == s)[0][0])
        if idx not in train_idx:
            train_idx.append(idx); screen_idx.remove(idx)

    print(f"  Cycle {cycle_i}/2: hits={int((labels_t[train_idx]==1).sum())}, {time.time()-t0:.0f}s")
    gc.collect(); torch.cuda.empty_cache()

al_smiles = [smiles_arr[i] for i in train_idx]
al_labels = [max(0, min(1, int(labels_t[i]))) for i in train_idx]  # 防御 label 越界
print(f"AL selected: {len(al_smiles)} molecules ({sum(al_labels)} hits)")

# ── 步骤 2: 用 glare_gnn_cli.py 子进程训练 50 epochs ──
print(f"\n{'='*70}")
print(f"  Step 2: glare_gnn_cli.py train (50 epochs, GRPO ens=3)")
print(f"{'='*70}")

# 保存选中分子到临时文件
data_records = [{"smiles": s, "label": l, "weight": 5.0 if l == 1 else 1.0}
                for s, l in zip(al_smiles, al_labels)]
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump(data_records, f)
    data_path = f.name

ckpt_path = str(OUTPUT_DIR / "e41b_chase.pt")

CLI_MODULE = "app.pipelines.vav1_rl.glare_gnn_cli"
proc = conda_run("diffgui_new", [
    "python", "-m", CLI_MODULE, "train",
    "--ckpt", ckpt_path, "--data", data_path,
    "--epochs", "50", "--ensemble", "3",
    "--lr", "3e-4", "--batch_size", "64",
    "--strategy", "grpo", "--l2_lambda", "3e-4",
    "--disable-ig",
], extra_env={"PYTHONPATH": "/data/ye/e-drug-lab/backend"})
try:
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    print(f"  Train: {result}")
except:
    print(f"  Train failed: {proc.stderr[-500:]}")
    sys.exit(1)

# ── 步骤 3: 查询 R2 排名 ──
print(f"\n{'='*70}")
print(f"  Step 3: Query 19 R2 molecules in 10k pool")
print(f"{'='*70}")

# 池分子 = pool 中所有非 R2 分子
pool_smiles = [smiles_arr[i] for i in range(n_total) if not is_r2_list[i]]
r2_smiles = [smiles_arr[i] for i in range(n_total) if is_r2_list[i]]

# 构建查询：全部池分子 + R2 分子
query_smiles = list(dict.fromkeys(pool_smiles + r2_smiles))
print(f"Querying {len(query_smiles)} molecules ({len(r2_smiles)} R2)...")

with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump(query_smiles, f)
    smi_path = f.name

proc = conda_run("diffgui_new", [
    "python", "-m", CLI_MODULE, "query",
    "--ckpt", ckpt_path, "--smiles", smi_path,
    "--ensemble", "3",
], extra_env={"PYTHONPATH": "/data/ye/e-drug-lab/backend"})
try:
    qr = json.loads(proc.stdout.strip().splitlines()[-1])
except:
    print(f"  Query failed: {proc.stderr[-500:]}")
    sys.exit(1)

ranked = qr.get("ranked", [])
rank_map = {r["smiles"]: int(r["glare_rank"]) for r in ranked}

# R2 排名
r2_ranks = {}
for mid, smi in r2_map.items():
    rank = rank_map.get(smi)
    if rank:
        r2_ranks[mid] = rank

mean_rank = float(np.mean(list(r2_ranks.values())))

print(f"\n{'='*60}")
print(f"  E41b Chase vs E37b")
print(f"{'='*60}")
print(f"  E37b  (#4174 / 11697)")
print(f"  E41b-AL (#{mean_rank:.0f} / {len(query_smiles)})")
delta = 4174 - mean_rank
print(f"  Δ: {delta:+.0f}")
if mean_rank < 4174:
    print(f"  🏆 超越 E37b! pct_improvement = {delta/4174*100:.1f}%")
else:
    print(f"  ❌ 未超越 E37b (差 {delta*-1})")

# 输出细节
for mid, rank in sorted(r2_ranks.items(), key=lambda x: x[1]):
    pct = 100*rank/len(query_smiles)
    print(f"    {mid:>16s} #{rank:>6d} ({pct:.2f}%)")

# 保存
result = {
    "scheme": "E41b_chase",
    "description": "E41b AL selection(192) + glare_gnn_cli 50 epochs + query",
    "mean_rank": mean_rank,
    "e37b_baseline": 4174,
    "n_pool": len(query_smiles),
    "delta_vs_e37b": delta,
    "r2_ranks": r2_ranks,
    "al_train_mols": len(al_smiles),
    "al_train_hits": sum(al_labels),
    "al_train_smiles": al_smiles,
    "al_train_labels": al_labels,
}
with open(OUTPUT_DIR / "e41b_chase_result.json", "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False, default=str)

print(f"\n✅ Checkpoint: {ckpt_path}")
print(f"✅ Result: {OUTPUT_DIR / 'e41b_chase_result.json'}")
