#!/usr/bin/env python3
"""E42 — Round 3 强化学习：加入 R2 真实标签（5正14负）后的 AL 训练与评估。

沿用 E41b-Chase 已验证方案：AL 选择192 → 子进程训练50ep → 查询R2排名。
唯一变化：R2 分子不再全标 hidden gem (label=1)，而是用真实湿实验标签。
"""
import json, os, sys, time, tempfile, gc
from pathlib import Path
import numpy as np
import pandas as pd

# ── GLARE 环境 ──
GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
sys.path.insert(0, GLARE_ROOT)
os.chdir(GLARE_ROOT)

sys.path.insert(0, '/data/ye/e-drug-lab/backend')
from app.services.conda_runner import conda_run

# ── Stubs ──
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

from rdkit import Chem
import torch
from argparse import Namespace
from torch.utils.data import WeightedRandomSampler
from utils.utils import molecular_graph_featurizer, smiles_to_ecfp, check_featurizability, to_torch_dataloader
from model import Ensemble

# ── Paths ──
BASE = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project")
OUTPUT_DIR = BASE / "validation/glare_e42_r3"
SWXDS = str(BASE / "validation/glare_e41_al/swxds_250k_smiles.csv")
PAT = str(BASE / "data/processed/patent_403_cleaned.csv")
WL = str(BASE / "validation/glare_e26_patent_320_83_20260630/data/new_13_molecules.csv")

# ═══ R2 真实标签 ═══
R2_LABELS = {
    "0185078(1)": 1, "0228300": 1, "0230953": 1, "0228423": 1, "LXC-201": 1,  # 正
    "0228274": 0, "0228325": 0, "0228413": 0, "0228419": 0, "0228429": 0,
    "0230500": 0, "0230853": 0, "0230915": 0, "0230922": 0, "0230994": 0,
    "0231000": 0, "0376960": 0, "LXC-206": 0, "LXC-305": 0,  # 负
}
R2_POSITIVE_IDS = {mid for mid, lab in R2_LABELS.items() if lab == 1}

R2_SDF_DIR = str(BASE / "第二轮动力学指导的分子生成")
POSITIVE_IDS = {"0228390", "0228414", "LXC-106"}  # R1 positives
GLARE_ATOMS = {'C','N','O','S','F','Cl','Br','I','P','Si','B','Se'}


def norm(s):
    try:
        mol = Chem.MolFromSmiles(str(s))
        return Chem.MolToSmiles(mol) if mol else ""
    except: return ""

def is_valid(smi):
    try:
        mol = Chem.MolFromSmiles(smi)
        if mol is None: return False
        return all(atom.GetSymbol() in GLARE_ATOMS for atom in mol.GetAtoms())
    except: return False

def extract_r2_smiles():
    """从 SDF 中提取 19 R2 分子的 SMILES，返回 {mid: canonical_smiles}"""
    r2_map = {}
    for fname in sorted(os.listdir(R2_SDF_DIR)):
        if not fname.endswith('.sdf'): continue
        sid = fname.replace('.sdf', '')
        suppl = Chem.SDMolSupplier(os.path.join(R2_SDF_DIR, fname))
        if not suppl or len(suppl) == 0: continue
        mol = suppl[0]
        smi = Chem.MolToSmiles(mol)
        if smi: r2_map[sid] = norm(smi)
    return r2_map

def build_pool(r2_map):
    """构建 pool：swxds 10k + 403 patent + 13 R1 + 19 R2（真实标签）"""
    seen = set(); pool = []  # (canonical, label, is_r2, mol_id)

    # swxds
    for i,row in pd.read_csv(SWXDS).iterrows():
        if i >= 10000: break
        c = norm(str(row['smiles']))
        if c and c not in seen: seen.add(c); pool.append((c,0,False,""))

    # patent
    for _,row in pd.read_csv(PAT).iterrows():
        c = norm(str(row['canonical_smiles']))
        if not c or c in seen: continue
        seen.add(c); pool.append((c, int(row['label_active']), False, f"PAT-{row.get('molecule_id','')}"))

    # R1
    wl_df = pd.read_csv(WL)
    for _,row in wl_df.iterrows():
        c = norm(str(row['SMILES']))
        if not c or c in seen: continue
        sid = str(row['SDF_ID'])
        lab = 1 if sid in POSITIVE_IDS else 0
        seen.add(c); pool.append((c, lab, False, sid))

    # R2 (with REAL labels)
    for mid, smi in r2_map.items():
        c = norm(smi) if smi else ""
        if not c: continue
        lab = R2_LABELS.get(mid, 0)  # real label
        if c in seen:
            for j, (s, l, r, m) in enumerate(pool):
                if s == c: pool[j] = (s, lab, True, mid); break
        else:
            seen.add(c); pool.append((c, lab, True, mid))

    return pool, r2_map


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("="*70)
    print("  E42: Round 3 — R2 真实标签强化学习")
    print("="*70)

    # ── 1. Build pool ──
    r2_map = extract_r2_smiles()
    pool, r2_map = build_pool(r2_map)
    n_act = sum(1 for _,l,_,_ in pool if l==1)
    n_r2_pos = sum(1 for _,l,r,_ in pool if r and l==1)
    n_r2_neg = sum(1 for _,l,r,_ in pool if r and l==0)
    print(f"Pool: {len(pool)} ({n_act} actives, R2: {n_r2_pos}pos/{n_r2_neg}neg)")

    # ── 2. Build graphs ──
    print("Building graphs...")
    graphs, labels, smiles_list, is_r2_list, mid_list = [], [], [], [], []
    for smi, lab, is_r2, mid in pool:
        if not check_featurizability(smi): continue
        if not is_valid(smi): continue
        fp = smiles_to_ecfp([smi], silent=True)
        g = molecular_graph_featurizer(smi, y=lab, fp=fp[0])
        if isinstance(g, str): continue
        g.fp = torch.tensor([fp[0]], dtype=torch.float32)
        g.xp = g.x; g.edgep_index = g.edge_index
        g.edgep_attr = getattr(g, "edge_attr", torch.empty((0,2), dtype=torch.long))
        graphs.append(g); labels.append(lab); smiles_list.append(smi)
        is_r2_list.append(is_r2); mid_list.append(mid)

    labels_t = torch.tensor(labels, dtype=torch.long)
    smiles_arr = np.array(smiles_list)
    n_total = len(graphs)
    print(f"  {n_total} graphs ({int((labels_t==1).sum())} actives, {sum(is_r2_list)} R2)")

    # ── 3. AL selection (GRPO, 2 cycles) ──
    print(f"\n{'─'*60}")
    print("  AL Selection (GRPO ens=3, 2 cycles, 192 mols)")
    print(f"{'─'*60}")

    args = Namespace(architecture="ginl", strategy="grpo", epochs=50, hidden_dim=1024,
        output_dim=2, mol_emb_dim=130, lr=3e-4, weight_decay=0.0,
        train_batch_size=64, infer_batch_size=512, ensemble_size=3, seed=0, disable_ig=True,
        anchored=True, l2_lambda=3e-4, grpo_lambda=7e-2, grpo_epsilon=2e-1, grpo_beta=1e-2,
        retrain=1, mode="a", cuda="0",
        mlp_fc_layer=3, gin_graph_conv_layer=3, gin_x_fc_layer=3, gin_fp_fc_layer=3,
        gcn_graph_conv_layer=5, gcn_x_fc_layer=3, gine_graph_conv_layer=3, gine_x_fc_layer=1, gine_fp_fc_layer=1,
        pretrain_file="", model_save_file="")

    np.random.seed(42)
    hit_idx = np.where(labels_t.numpy() == 1)[0]
    train_idx = np.concatenate([np.random.choice(hit_idx, 1), np.random.choice(n_total, 63)]).tolist()
    screen_idx = [i for i in range(n_total) if i not in train_idx]

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

        hits = int((labels_t[train_idx] == 1).sum())
        r2_in_train = sum(1 for i in train_idx if is_r2_list[i])
        r2_pos_in_train = sum(1 for i in train_idx if is_r2_list[i] and labels_t[i]==1)
        print(f"  Cycle {cycle_i}/2: hits={hits}, R2_in_train={r2_in_train} ({r2_pos_in_train}pos), {time.time()-t0:.0f}s")
        gc.collect(); torch.cuda.empty_cache()

    al_smiles = [smiles_arr[i] for i in train_idx]
    al_labels = [max(0, min(1, int(labels_t[i]))) for i in train_idx]
    al_is_r2 = [is_r2_list[i] for i in train_idx]
    print(f"AL selected: {len(al_smiles)} mols ({sum(al_labels)} hits, {sum(al_is_r2)} R2)")

    # Save AL selection for record
    al_record = [{"smiles": s, "label": l, "is_r2": r}
                 for s, l, r in zip(al_smiles, al_labels, al_is_r2)]
    with open(OUTPUT_DIR/"al_selected.json","w") as f:
        json.dump(al_record, f, indent=2)

    # ── 4. Subprocess training (50 epochs) ──
    print(f"\n{'─'*60}")
    print("  Subprocess training (50 epochs, GRPO ens=3, disable_ig)")
    print(f"{'─'*60}")

    data_records = [{"smiles": s, "label": l, "weight": 5.0 if l == 1 else 1.0}
                    for s, l in zip(al_smiles, al_labels)]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(data_records, f); data_path = f.name

    ckpt_path = str(OUTPUT_DIR / "e42.pt")
    proc = conda_run("diffgui_new", [
        "python", "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "train",
        "--ckpt", ckpt_path, "--data", data_path,
        "--epochs", "50", "--ensemble", "3",
        "--lr", "3e-4", "--batch_size", "64",
        "--strategy", "grpo", "--l2_lambda", "3e-4",
        "--disable-ig",
    ], extra_env={"PYTHONPATH": "/data/ye/e-drug-lab/backend"})

    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        print(f"  Train: loss={result.get('final_loss')}, samples={result.get('n_samples')}")
    except:
        print(f"  Train FAILED: {proc.stderr[-500:]}")
        sys.exit(1)

    # ── 5. Query R2 ranking ──
    print(f"\n{'─'*60}")
    print("  Query: 19 R2 molecules vs pool")
    print(f"{'─'*60}")

    # Build query: pool + all R2 SMILES (don't include non-R2 in pool for ranking)
    pool_smiles = [smiles_arr[i] for i in range(n_total) if not is_r2_list[i]]
    r2_in_pool = [(mid, smi) for mid, smi in r2_map.items()]
    r2_smis = [norm(smi) for _, smi in r2_in_pool]
    query = list(dict.fromkeys(pool_smiles + [s for s in r2_smis if s]))

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(query, f); smi_path = f.name

    proc = conda_run("diffgui_new", [
        "python", "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "query",
        "--ckpt", ckpt_path, "--smiles", smi_path, "--ensemble", "3",
    ], extra_env={"PYTHONPATH": "/data/ye/e-drug-lab/backend"})

    lines = [l.strip() for l in proc.stdout.strip().splitlines() if l.strip()]
    qr = None
    for line in reversed(lines):
        if line.startswith('{'):
            try: qr = json.loads(line); break
            except: continue
    if not qr:
        print("Query FAILED:", proc.stderr[-500:]); sys.exit(1)

    rank_map = {r['smiles']: int(r['glare_rank']) for r in qr.get('ranked', [])}
    n_p = len(rank_map)

    # R2 ranks
    r2_ranks = {}
    for mid, smi in r2_in_pool:
        r = rank_map.get(norm(smi))
        if r: r2_ranks[mid] = r

    mean_rank = np.mean(list(r2_ranks.values()))
    pos_ranks = [r for mid, r in r2_ranks.items() if R2_LABELS.get(mid, 0) == 1]
    neg_ranks = [r for mid, r in r2_ranks.items() if R2_LABELS.get(mid, 0) == 0]
    pos_mean = np.mean(pos_ranks) if pos_ranks else None
    neg_mean = np.mean(neg_ranks) if neg_ranks else None

    print(f"\n  E42 R2 Results:")
    print(f"  Mean Rank:  #{mean_rank:.0f} / {n_p} ({100*mean_rank/n_p:.1f}%)")
    print(f"  Pos Mean:   #{pos_mean:.0f}" if pos_mean else "")
    print(f"  Neg Mean:   #{neg_mean:.0f}" if neg_mean else "")
    for mid in sorted(r2_ranks.keys()):
        r = r2_ranks[mid]
        lab = R2_LABELS.get(mid, "?")
        print(f"    {mid:>16s} #{r:>5d} ({100*r/n_p:.1f}%) {'[POS]' if lab==1 else '[NEG]'}")

    # ── 6. Query R1 ranking ──
    print(f"\n{'─'*60}")
    print("  Query: 13 R1 molecules vs pool")
    print(f"{'─'*60}")

    wl_df = pd.read_csv(WL)
    r1_smiles = {}
    for _, row in wl_df.iterrows():
        sid = str(row['SDF_ID']); c = norm(str(row['SMILES']))
        if c: r1_smiles[sid] = (c, 1 if sid in POSITIVE_IDS else 0)

    r1_canon = [s for s, l in r1_smiles.values()]
    q2 = list(dict.fromkeys(pool_smiles + r1_canon))

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(q2, f); smi_path2 = f.name

    proc2 = conda_run("diffgui_new", [
        "python", "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "query",
        "--ckpt", ckpt_path, "--smiles", smi_path2, "--ensemble", "3",
    ], extra_env={"PYTHONPATH": "/data/ye/e-drug-lab/backend"})

    lines2 = [l.strip() for l in proc2.stdout.strip().splitlines() if l.strip()]
    qr2 = None
    for line in reversed(lines2):
        if line.startswith('{'):
            try: qr2 = json.loads(line); break
            except: continue

    if qr2:
        rank_map2 = {r['smiles']: int(r['glare_rank']) for r in qr2.get('ranked', [])}
        n_p2 = len(rank_map2)
        r1_ranks = {}
        for sid, (smi, lab) in r1_smiles.items():
            r = rank_map2.get(smi)
            if r: r1_ranks[sid] = {"rank": r, "label": lab}
        r1_mean = np.mean([v["rank"] for v in r1_ranks.values()])
        r1_pos = np.mean([v["rank"] for v in r1_ranks.values() if v["label"]==1])
        r1_neg = np.mean([v["rank"] for v in r1_ranks.values() if v["label"]==0])
        print(f"  R1 Mean Rank: #{r1_mean:.0f} / {n_p2}")
        print(f"  R1 Pos Mean:  #{r1_pos:.0f}")
        print(f"  R1 Neg Mean:  #{r1_neg:.0f}")

    # ── 7. Save results ──
    result = {
        "scheme": "E42", "description": "Round 3 — R2 real labels (5pos/14neg)",
        "r2": {"mean_rank": float(mean_rank), "n_pool": n_p,
               "pos_mean": float(pos_mean) if pos_mean else None,
               "neg_mean": float(neg_mean) if neg_mean else None,
               "ranks": {k: int(v) for k,v in r2_ranks.items()}},
        "r1": {"mean_rank": float(r1_mean), "n_pool": n_p2,
               "pos_mean": float(r1_pos), "neg_mean": float(r1_neg),
               "ranks": {k: int(v["rank"]) for k,v in r1_ranks.items()}},
        "al_selection": {"total": len(al_smiles), "hits": sum(al_labels),
                         "r2_selected": sum(al_is_r2),
                         "r2_pos_selected": sum(1 for i in train_idx if is_r2_list[i] and labels_t[i]==1)},
        "checkpoint": ckpt_path,
    }
    with open(OUTPUT_DIR/"e42_result.json","w") as f:
        json.dump(result, f, indent=2)
    print(f"\n✅ Saved: {OUTPUT_DIR/'e42_result.json'}")

    # ── 8. Comparison ──
    print(f"\n{'='*80}")
    print("  横向对比: E42 vs E41b-Chase vs E37b vs E34")
    print(f"{'='*80}")

    # Load E41b-Chase result
    try:
        with open(BASE/"validation/glare_e41_al/e41b_chase_result.json") as f:
            e41d = json.load(f)
        e41_mean = e41d["mean_rank"]
        e41_pool = e41d["n_pool"]
    except:
        e41_mean, e41_pool = None, None

    # Load E37b
    try:
        with open(BASE/"validation/glare_e37_transfer/e37_10schemes_comparison.json") as f:
            e37d = json.load(f)
        e37_mean = e37d["schemes"]["E37b"]["mean_rank"]
    except:
        e37_mean = 4174

    # E34
    try:
        with open(BASE/"validation/round2_dynamics_ranking/e34_vs_e36_round2_dynamics.json") as f:
            e34d = json.load(f)
        e34_mean = np.mean([r["e34_rank"] for r in e34d["results"]])
    except:
        e34_mean = 6583

    print(f"  {'Scheme':>16s}  {'Mean Rank':>10s}  {'Pool':>8s}  {'Pct':>6s}  {'vs E34':>10s}  {'vs E37b':>10s}  {'vs E41b':>10s}")
    print(f"  {'─'*16}  {'─'*10}  {'─'*8}  {'─'*6}  {'─'*10}  {'─'*10}  {'─'*10}")

    schemes = [
        ("E34", e34_mean, 11697, None),
        ("E37b", e37_mean, 11697, None),
        ("E41b-Chase", e41_mean, e41_pool or 10424, None),
        ("E42 🔥", mean_rank, n_p, None),
    ]
    for i, (name, mr, np_, _) in enumerate(schemes):
        vs34 = f"{(mr-e34_mean)/e34_mean*100:+.1f}%" if e34_mean else "N/A"
        vs37 = f"{(mr-e37_mean)/e37_mean*100:+.1f}%" if e37_mean else "N/A"
        vs41 = f"{(mr-e41_mean)/e41_mean*100:+.1f}%" if e41_mean else "N/A"
        prev_vs34 = f"{abs(mr-e34_mean):.0f}" if e34_mean else ""
        print(f"  {name:>16s}  #{mr:>8.0f}  {np_:>8,d}  {100*mr/np_:>5.1f}%  {prev_vs34:>+9s}  {prev_vs37:>+9s}  {prev_vs41:>+9s}  {vs34:>9s} {vs37:>9s} {vs41:>9s}" if False else
              f"  {name:>16s}  #{mr:>8.0f}  {np_:>8,d}  {100*mr/np_:>5.1f}%")

    comp = {
        "E34": {"mean_rank": e34_mean, "pool": 11697},
        "E37b": {"mean_rank": e37_mean, "pool": 11697},
        "E41b_Chase": {"mean_rank": e41_mean, "pool": e41_pool},
        "E42": {"mean_rank": mean_rank, "pool": n_p},
    }
    with open(OUTPUT_DIR/"e42_comparison.json","w") as f:
        json.dump(comp, f, indent=2)
    print(f"\n✅ Comparison saved")

if __name__ == "__main__":
    main()
