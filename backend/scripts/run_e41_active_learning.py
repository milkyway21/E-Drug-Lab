#!/usr/bin/env python3
"""E41 — GLARE 论文原版 Active Learning（自包含，无需预处理）。

Pool: N 个 swxds 背景分子 + 403 patent + 13 wet-lab + 19 R2
Active Learning: 初始64 → 每轮选64 → 共15轮 → 筛选1000

用法:
  cd /data/ye/diffgui/third_party/GLARE
  conda run -n diffgui_new python3 -u /data/ye/e-drug-lab/backend/scripts/run_e41_active_learning.py --pool-size 50000 --scheme E41a
"""
import argparse, json, os, sys, time, gc
from collections import OrderedDict
from math import ceil
from pathlib import Path

# ── Stubs ──
import types
try: import torch_sparse  # noqa
except ModuleNotFoundError:
    ts = types.ModuleType("torch_sparse")
    try:
        from torch_geometric.typing import SparseTensor as _ST
    except Exception: _ST = None
    if _ST is not None: ts.SparseTensor = _ST
    sys.modules["torch_sparse"] = ts

try: import captum  # noqa
except ModuleNotFoundError:
    cm, am = types.ModuleType("captum"), types.ModuleType("captum.attr")
    import torch as _t
    class _StubIG:
        def __init__(self, *a, **kw): pass
        def attribute(self, *a, **kw): return _t.zeros_like(a[0]), _t.tensor(0.0)
    am.IntegratedGradients = _StubIG; cm.attr = am
    sys.modules["captum"] = cm; sys.modules["captum.attr"] = am

import numpy as np
import torch
from torch.utils.data import WeightedRandomSampler
from rdkit import Chem

GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
os.chdir(GLARE_ROOT)
sys.path.insert(0, GLARE_ROOT)
from utils.utils import molecular_graph_featurizer, smiles_to_ecfp, to_torch_dataloader, random_baseline, check_featurizability
from model import Ensemble
from acquisition import acquire

# ── Paths ──
SWXDS_CSV = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al/swxds_250k_smiles.csv"
PATENT_CSV = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv"
WETLAB_CSV = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e26_patent_320_83_20260630/data/new_13_molecules.csv"
R2_TRACKING = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al/r2_smiles_tracking.json"
OUTPUT_DIR = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al")

POSITIVE_IDS = {"0228390", "0228414", "LXC-106"}


def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else ""


def build_graph(smi, label):
    """构建 GLARE PyG Data 对象，与 MasterDataset.process() 相同格式。"""
    # 先算 ECFP，再传给 featurizer（与 GLARE 原始流程一致）
    fp = smiles_to_ecfp([smi], silent=True)
    g = molecular_graph_featurizer(smi, y=int(label), fp=fp[0])
    if isinstance(g, str):
        return None
    # 与 GLARE MasterDataset.process 完全一致：fp 是 [1, 1024]
    g.fp = torch.tensor([fp[0]], dtype=torch.float32)
    g.xp = g.x
    g.edgep_index = g.edge_index
    g.edgep_attr = getattr(g, "edge_attr", torch.empty((0, 2), dtype=torch.long))
    return g


def load_pool(pool_size=50000):
    """加载并构建分子图 pool。返回 (graphs, labels, smiles_array, r2_mask, stats)。"""
    import pandas as pd

    print(f"Loading pool ({pool_size} swxds + patent + wetlab + R2)...")

    # ── R2 SMILES ──
    with open(R2_TRACKING) as f:
        r2_data = json.load(f)
    r2_smiles = set(r2_data["molecules"].values())
    r2_map = r2_data["molecules"]  # mol_id → SMILES

    # ── 收集 SMILES ──
    seen = set()
    pool_entries = []  # (canonical_smiles, label, is_r2, mol_id)

    # swxds (label=0)
    swxds_df = pd.read_csv(SWXDS_CSV)
    swxds_count = 0
    for _, row in swxds_df.iterrows():
        if swxds_count >= pool_size:
            break
        canon = norm(str(row["smiles"]))
        if canon and canon not in seen:
            seen.add(canon)
            pool_entries.append((canon, 0, canon in r2_smiles, ""))
            swxds_count += 1
    print(f"  swxds: {swxds_count}")

    # Patent 403
    patent_df = pd.read_csv(PATENT_CSV)
    p_a, p_i = 0, 0
    for _, row in patent_df.iterrows():
        canon = norm(str(row["canonical_smiles"]))
        if not canon or canon in seen:
            continue
        seen.add(canon)
        label = int(row["label_active"])
        pool_entries.append((canon, label, canon in r2_smiles, f"PAT-{row.get('molecule_id', '')}"))
        if label == 1: p_a += 1
        else: p_i += 1
    print(f"  patent: {p_a} actives + {p_i} inactives")

    # Wet-lab 13
    wetlab_df = pd.read_csv(WETLAB_CSV)
    w_a, w_i = 0, 0
    for _, row in wetlab_df.iterrows():
        canon = norm(str(row["SMILES"]))
        if not canon or canon in seen:
            continue
        seen.add(canon)
        sid = str(row["SDF_ID"])
        label = 1 if sid in POSITIVE_IDS else 0
        pool_entries.append((canon, label, canon in r2_smiles, sid))
        if label == 1: w_a += 1
        else: w_i += 1
    print(f"  wet-lab: {w_a} actives + {w_i} inactives")

    # ── R2 molecules (explicitly add all 19, regardless of swxds overlap) ──
    r2_added = 0
    for mid, smi in r2_map.items():
        canon = norm(str(smi))
        if not canon:
            continue
        if canon in seen:
            # Already in pool — update is_r2 flag
            for j, (s, l, r, m) in enumerate(pool_entries):
                if s == canon:
                    pool_entries[j] = (s, l, True, mid)
                    break
        else:
            seen.add(canon)
            # R2 molecules: label unknown in real scenario; here label=1 (active) for evaluation
            pool_entries.append((canon, 1, True, mid))
            r2_added += 1
    print(f"  R2 explicit: {r2_added} added (total: {sum(1 for _, _, r, _ in pool_entries if r)} in pool)")

    total_actives = sum(1 for _, l, _, _ in pool_entries if l == 1)
    total_r2 = sum(1 for _, _, r, _ in pool_entries if r)
    print(f"  Total: {len(pool_entries):,} ({total_actives} actives, {total_r2} R2)")

    # ── 构建 graphs ──
    print(f"\nBuilding molecular graphs ({len(pool_entries):,} molecules)...")
    t0 = time.time()
    graphs, labels, smiles_list, is_r2_list, mol_ids = [], [], [], [], []
    rejected = 0

    report_int = max(5000, len(pool_entries) // 10)
    for i, (smi, label, is_r2, mol_id) in enumerate(pool_entries):
        if not check_featurizability(smi):
            rejected += 1
            continue
        g = build_graph(smi, label)
        if g is None:
            rejected += 1
            continue
        graphs.append(g)
        labels.append(label)
        smiles_list.append(smi)
        is_r2_list.append(is_r2)
        mol_ids.append(mol_id)

        if (i + 1) % report_int == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(pool_entries) - i - 1) / rate / 60
            print(f"    {i+1:>7,}/{len(pool_entries):,} rate={rate:.0f}/s ETA={eta:.1f}min")

    elapsed = time.time() - t0
    print(f"  Built {len(graphs):,} graphs in {elapsed/60:.1f}min ({rejected} rejected)")

    labels_t = torch.tensor(labels, dtype=torch.long)
    is_r2_t = torch.tensor(is_r2_list, dtype=torch.bool)
    smiles_arr = np.array(smiles_list)

    stats = {
        "total": len(graphs), "actives": int((labels_t == 1).sum()),
        "inactives": int((labels_t == 0).sum()), "r2_count": int(is_r2_t.sum()),
        "pool_size": pool_size, "rejected": rejected,
        "r2_map": r2_map,
    }

    return graphs, labels_t, smiles_arr, is_r2_t, mol_ids, stats


def construct_dataloaders(train_idx, screen_idx, graphs, labels):
    """构建 train/screen DataLoaders（模拟 ActiveLearningDataset.construct_dataloader）。"""
    train_graphs = [graphs[i] for i in train_idx]
    train_y = labels[train_idx].clamp(0, 1)  # 防御 label 越界

    # WeightedRandomSampler（与 GLARE 一致）
    n_pos = int((train_y == 1).sum())
    n_neg = int((train_y == 0).sum())
    n_total = max(len(train_y), 1)
    class_weights = [1 - n_pos / n_total, 1 - n_neg / n_total]
    weights = [class_weights[max(0, min(1, int(yi)))] for yi in train_y]  # 防御越界
    sampler = WeightedRandomSampler(weights, num_samples=len(train_y), replacement=True)

    train_loader = to_torch_dataloader(train_graphs, train_y.numpy(),
                                        batch_size=512, shuffle=False, pin_memory=False)
    train_loader_balanced = to_torch_dataloader(train_graphs, train_y.numpy(),
                                                 batch_size=64, sampler=sampler,
                                                 shuffle=False, pin_memory=False)

    screen_graphs = [graphs[i] for i in screen_idx]
    screen_y = labels[screen_idx]
    screen_loader = to_torch_dataloader(screen_graphs, screen_y.numpy(),
                                         batch_size=512, shuffle=False, pin_memory=False)

    return train_loader, train_loader_balanced, screen_loader


def run_active_learning(scheme_key, scheme_cfg, graphs, labels_t, smiles_arr, is_r2_t, mol_ids, stats):
    """运行 GLARE 主动学习循环。"""
    from argparse import Namespace

    print(f"\n{'='*70}")
    print(f"  {scheme_key}: {scheme_cfg['label']}")
    print(f"  Strategy={scheme_cfg['strategy']}, Ens={scheme_cfg['ensemble_size']}, "
          f"disable_ig={scheme_cfg.get('disable_ig', False)}")
    print(f"{'='*70}")

    # GLARE args
    args = Namespace(
        architecture="ginl", strategy=scheme_cfg["strategy"],
        epochs=scheme_cfg.get("epochs", 50), hidden_dim=1024, output_dim=2, mol_emb_dim=130,
        lr=3e-4, weight_decay=0.0,
        train_batch_size=64, infer_batch_size=512,
        ensemble_size=scheme_cfg["ensemble_size"], seed=0,
        anchored=True, l2_lambda=3e-4,
        grpo_lambda=7e-2, grpo_epsilon=2e-1, grpo_beta=1e-2,
        retrain=1, mode="a", cuda="0",
        mlp_fc_layer=3, gin_graph_conv_layer=3, gin_x_fc_layer=3, gin_fp_fc_layer=3,
        gcn_graph_conv_layer=5, gcn_x_fc_layer=3,
        gine_graph_conv_layer=3, gine_x_fc_layer=1, gine_fp_fc_layer=1,
        pretrain_file="", model_save_file="",
        disable_ig=scheme_cfg.get("disable_ig", False),
    )

    n_total = len(graphs)
    start_num = 64
    batch_size = 64
    max_screen = scheme_cfg.get("max_screen", 1000)
    total_hits_in_pool = stats["actives"]

    # ── 初始化训练集 ──
    rng = np.random.default_rng(42)
    hit_idx = np.where(labels_t.numpy() == 1)[0]
    start_hit = rng.choice(hit_idx, size=1, replace=False)
    remain_idx = np.array([i for i in range(n_total) if i not in start_hit])
    start_other = rng.choice(remain_idx, size=start_num - 1, replace=False)
    train_idx = np.concatenate([start_hit, start_other])
    train_idx = rng.permutation(train_idx)
    screen_idx = np.array([i for i in range(n_total) if i not in train_idx])

    r2_found_log = []
    total_hit_discover = [int((labels_t[train_idx] == 1).sum())]
    total_mol_screen = [len(train_idx)]

    cycles = ceil((max_screen - start_num) / batch_size)
    print(f"  Start: {start_num} mols, {total_hit_discover[0]} hits")
    print(f"  Pool: {n_total:,}, Actives: {total_hits_in_pool}, R2 hidden: {stats['r2_count']}")
    print(f"  Cycles: {cycles} (batch={batch_size}, max={max_screen})")

    for cycle_i in range(1, cycles + 1):
        t0 = time.time()

        # DataLoaders
        train_loader, train_balanced, screen_loader = construct_dataloaders(
            train_idx, screen_idx, graphs, labels_t)

        # Train
        model = Ensemble(args)
        model.train(train_balanced)

        # Predict
        screen_logits = model.predict(screen_loader)

        # Select next batch
        if len(train_idx) + batch_size < max_screen:
            n_pick = batch_size
        else:
            n_pick = max_screen - len(train_idx)

        screen_smiles = smiles_arr[screen_idx]

        if args.strategy == "grpo":
            mean_probs = torch.mean(torch.exp(screen_logits), dim=1)[:, 1].cpu()
            random_val = torch.rand(mean_probs.shape[0])
            pick_flag = torch.where(mean_probs - random_val > 0,
                                    torch.ones_like(mean_probs),
                                    torch.zeros_like(mean_probs))
            scored = mean_probs + pick_flag
            local_pick = torch.argsort(scored, descending=True)[:n_pick]
            smiles_pick = screen_smiles[local_pick.cpu().numpy()]
        else:
            screen_hits = smiles_arr[train_idx][labels_t[train_idx].numpy() == 1]
            smiles_pick = acquire(acquisition=args.strategy,
                                  logits_N_K_C=screen_logits,
                                  smiles_screen=screen_smiles,
                                  n=n_pick,
                                  smiles_hit=screen_hits)

        # Track R2 discovery
        r2_found_now = []
        r2_map = stats["r2_map"]
        for mid, r2_smi in r2_map.items():
            if r2_smi in set(smiles_pick):
                already_found = any(
                    mid in log.get("r2_ids_found", [])
                    for log in r2_found_log
                )
                if not already_found:
                    r2_found_now.append(mid)

        r2_found_log.append({
            "cycle": cycle_i,
            "n_r2_found": len(r2_found_now),
            "r2_ids_found": r2_found_now,
            "n_r2_cumulative": sum(len(log["r2_ids_found"]) for log in r2_found_log),
        })

        # Expand training set
        pick_indices = [int(np.where(smiles_arr == s)[0][0]) for s in smiles_pick]
        train_idx = np.concatenate([train_idx, pick_indices])
        screen_idx = np.array([i for i in range(n_total) if i not in train_idx])

        total_hit_discover.append(int((labels_t[train_idx] == 1).sum()))
        total_mol_screen.append(len(train_idx))

        elapsed = time.time() - t0
        print(f"  Cycle {cycle_i:2d}/{cycles}: +{n_pick} mols, hits={total_hit_discover[-1]}, "
              f"R2 found={len(r2_found_now)}, time={elapsed:.0f}s")

        gc.collect()
        torch.cuda.empty_cache()

    # ── ═══ R2 Ranking (vs E37b 横向对比) ═══ ──
    # 用最后一个 cycle 的模型对所有 pool 分子做排序
    # 报告 19 个 R2 分子的 Mean Rank, 直接对比 E37b #4174
    print("\n  ── R2 Ranking vs E37b ──")
    r2_map = stats["r2_map"]
    all_loader = to_torch_dataloader(graphs, labels_t.numpy(),
                                      batch_size=512, shuffle=False, pin_memory=False)
    all_logits = model.predict(all_loader)  # [N, K, C]
    # NaN 安全
    all_logits = torch.nan_to_num(all_logits.float(), nan=0.0)
    probs = torch.exp(all_logits)
    active_prob = probs[:, :, 1].mean(dim=1)  # [N] — ensemble mean of active class prob

    # 按活性概率降序排序
    sorted_indices = torch.argsort(active_prob, descending=True).tolist()

    # 找每个 R2 分子的排名
    r2_ranks = {}
    for rank, idx in enumerate(sorted_indices, 1):
        smi = smiles_arr[idx]
        for mid, r2_smi in r2_map.items():
            if r2_smi == smi and mid not in r2_ranks:
                r2_ranks[mid] = rank

    mean_rank = float(np.mean(list(r2_ranks.values()))) if r2_ranks else None
    print(f"  R2 Mean Rank: #{mean_rank:.0f} / {n_total}")
    print(f"  vs E37b:      #4174 / 11697")
    if mean_rank:
        pct_improvement = (4174 - mean_rank) / 4174 * 100 if 4174 > mean_rank else 0
        print(f"  Δ vs E37b:    {'+' if mean_rank < 4174 else ''}{4174 - mean_rank:.0f} ({pct_improvement:.1f}%)")

    # ── Enrichment Factor ──
    baseline = random_baseline(total_hits_in_pool, batch_size, start_num, n_total, max_screen)
    ef = [h / b for h, b in zip(total_hit_discover, baseline)]

    result = {
        "scheme": scheme_key,
        "label": scheme_cfg["label"],
        "config": {k: str(v) for k, v in scheme_cfg.items()},
        "pool_stats": stats,
        "total_hit_discover": total_hit_discover,
        "total_mol_screen": total_mol_screen,
        "enrichment_factor": ef,
        "r2_discovery": r2_found_log,
        "n_r2_found_total": sum(len(log["r2_ids_found"]) for log in r2_found_log),
        "r2_ranking": {
            "mean_rank": mean_rank,
            "n_pool": n_total,
            "e37b_baseline": 4174,
            "r2_ranks": r2_ranks,
        },
    }

    print(f"\n  Final: {total_hit_discover[-1]} hits in {total_mol_screen[-1]} screened")
    print(f"  EF: {ef[-1]:.3f}, R2 found: {result['n_r2_found_total']}/{stats['r2_count']}")

    # Save
    out_path = OUTPUT_DIR / f"{scheme_key.lower()}_result.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"  ✅ Saved: {out_path}")

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool-size", type=int, default=50000)
    parser.add_argument("--scheme", type=str, default=None,
                        help="E41a, E41b, E41c, E41d. Omit to run all.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only build graphs, skip active learning")
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs per cycle")
    parser.add_argument("--max-screen", type=int, default=1000, help="Max molecules to screen")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    SCHEMES = {
        "E41a": {"key": "E41a", "label": "GRPO ens=10 (论文原版)",
                 "strategy": "grpo", "ensemble_size": 10, "disable_ig": False,
                 "epochs": args.epochs, "max_screen": args.max_screen},
        "E41b": {"key": "E41b", "label": "GRPO ens=3 (E37b最优ens)",
                 "strategy": "grpo", "ensemble_size": 3, "disable_ig": False,
                 "epochs": args.epochs, "max_screen": args.max_screen},
        "E41c": {"key": "E41c", "label": "Greedy ens=10 (无GRPO基线)",
                 "strategy": "greedy", "ensemble_size": 10, "disable_ig": False,
                 "epochs": args.epochs, "max_screen": args.max_screen},
        "E41d": {"key": "E41d", "label": "Random baseline",
                 "strategy": "random", "ensemble_size": 1, "disable_ig": False,
                 "epochs": args.epochs, "max_screen": args.max_screen},
    }

    # ── Load & build pool ──
    graphs, labels_t, smiles_arr, is_r2_t, mol_ids, stats = load_pool(args.pool_size)

    if args.dry_run:
        print("Dry run complete. Graphs built.")
        return

    # ── Run schemes ──
    if args.scheme:
        cfg = SCHEMES[args.scheme]
        run_active_learning(args.scheme, cfg, graphs, labels_t, smiles_arr, is_r2_t, mol_ids, stats)
    else:
        # E41d first (fast, random baseline doesn't need training)
        for key in ["E41d"]:  # random first
            cfg = SCHEMES[key]
            run_active_learning(key, cfg, graphs, labels_t, smiles_arr, is_r2_t, mol_ids, stats)
        for key in ["E41c", "E41b", "E41a"]:  # then greedy, then GRPO
            cfg = SCHEMES[key]
            run_active_learning(key, cfg, graphs, labels_t, smiles_arr, is_r2_t, mol_ids, stats)


if __name__ == "__main__":
    main()
