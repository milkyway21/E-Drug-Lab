#!/usr/bin/env python3
"""GLARE 预处理：VAV1 SMILES → PyG graph 对象（无中间 checkpoint，一次跑完）。

用法: cd /data/ye/diffgui/third_party/GLARE && conda run -n diffgui_new python3 /data/ye/e-drug-lab/backend/scripts/preprocess_vav1.py
预计: 250k 分子约 60-80 分钟
"""
import os, sys, json, gc, time
from collections import OrderedDict
from pathlib import Path

# ── Stubs ──
import types
try:
    import torch_sparse  # noqa
except ModuleNotFoundError:
    ts = types.ModuleType("torch_sparse")
    try:
        from torch_geometric.typing import SparseTensor as _ST
    except Exception: _ST = None
    if _ST is not None: ts.SparseTensor = _ST
    sys.modules["torch_sparse"] = ts
try:
    import captum  # noqa
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
from rdkit import Chem

GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
os.chdir(GLARE_ROOT)
sys.path.insert(0, GLARE_ROOT)
from utils.utils import molecular_graph_featurizer, smiles_to_ecfp

DATASET = "VAV1"
SCREEN_DIR = Path(GLARE_ROOT) / "data" / DATASET / "screen"
ORIGINAL_DIR = Path(GLARE_ROOT) / "data" / DATASET / "original"
R2_TRACKING = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al/r2_smiles_tracking.json"


def canonicalize(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else ""


def main():
    SCREEN_DIR.mkdir(parents=True, exist_ok=True)

    # ── 加载 R2 SMILES ──
    r2_set = set()
    if os.path.exists(R2_TRACKING):
        with open(R2_TRACKING) as f:
            r2_set = set(json.load(f)["molecules"].values())

    # ── 读取 + 去重 ──
    with open(ORIGINAL_DIR / "actives.smi") as f:
        actives_raw = [l.strip() for l in f if l.strip()]
    with open(ORIGINAL_DIR / "inactives.smi") as f:
        inactives_raw = [l.strip() for l in f if l.strip()]

    seen = set()
    molecules = []
    for smi in inactives_raw:
        c = canonicalize(smi)
        if c and c not in seen:
            seen.add(c)
            molecules.append((c, 0, c in r2_set))
    for smi in actives_raw:
        c = canonicalize(smi)
        if c and c not in seen:
            seen.add(c)
            molecules.append((c, 1, c in r2_set))

    n_act = sum(1 for _, l, _ in molecules if l == 1)
    n_r2 = sum(1 for _, _, r in molecules if r)
    print(f"Pool: {len(molecules):,} ({n_act} actives, {n_r2} R2)")

    # ── 构建 graphs + ECFP（单次 pass）──
    graphs_list, x_rows, valid_smiles, valid_labels, valid_is_r2 = [], [], [], [], []
    failed = 0
    t0 = time.time()
    report_interval = 10000

    for i, (smi, label, is_r2) in enumerate(molecules):
        try:
            g = molecular_graph_featurizer(smi, y=label)
            if isinstance(g, str): failed += 1; continue

            fp = smiles_to_ecfp([smi], silent=True)
            g.fp = torch.tensor(fp, dtype=torch.float32)
            g.xp = g.x
            g.edgep_index = g.edge_index
            g.edgep_attr = getattr(g, "edge_attr", torch.empty((0, 2), dtype=torch.long))

            graphs_list.append(g)
            x_rows.append(fp[0])
            valid_smiles.append(smi)
            valid_labels.append(label)
            valid_is_r2.append(is_r2)
        except Exception:
            failed += 1

        if (i + 1) % report_interval == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(molecules) - i - 1) / rate / 60
            print(f"  {i+1:>8,}/{len(molecules):,} ({100*(i+1)/len(molecules):.1f}%) "
                  f"rate={rate:.0f}/s, valid={len(valid_smiles):,}, ETA={eta:.1f}min")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed/60:.1f}min. Valid: {len(valid_smiles):,}, Failed: {failed}")

    # ── 保存 ──
    x_final = torch.tensor(np.array(x_rows), dtype=torch.float32)
    y_final = torch.tensor(valid_labels, dtype=torch.long)
    smiles_arr = np.array(valid_smiles)
    index_smiles = OrderedDict({i: s for i, s in enumerate(valid_smiles)})
    smiles_index = OrderedDict({s: i for i, s in enumerate(valid_smiles)})

    print(f"Saving to {SCREEN_DIR}...")
    torch.save(index_smiles, str(SCREEN_DIR / "index_smiles"))
    torch.save(smiles_index, str(SCREEN_DIR / "smiles_index"))
    torch.save(smiles_arr, str(SCREEN_DIR / "smiles"))
    torch.save(x_final, str(SCREEN_DIR / "x"), pickle_protocol=4)
    torch.save(y_final, str(SCREEN_DIR / "y"))
    torch.save(graphs_list, str(SCREEN_DIR / "graphs"), pickle_protocol=4)
    torch.save(graphs_list, str(SCREEN_DIR / "graphs2"), pickle_protocol=4)

    print(f"✅ Done! {len(valid_smiles):,} molecules, {int((y_final==1).sum())} actives, "
          f"{sum(valid_is_r2)} R2 hidden gems")

if __name__ == "__main__":
    main()
