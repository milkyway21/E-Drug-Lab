"""GLARE GNN+GRPO 独立 CLI（在 diffgui_new conda env 子进程里跑）。

主进程（edrug env，无 torch_geometric）通过 conda_run 调用本脚本，避免环境冲突。
本脚本依赖 third_party/GLARE（GIN+GRPO+Ensemble）+ captum。

用法：
  python -m app.pipelines.vav1_rl.glare_gnn_cli train --ckpt <path> --data <json> [--prev <path>] [--epochs 50]
  python -m app.pipelines.vav1_rl.glare_gnn_cli query  --ckpt <path> --smiles <json> [--ensemble 3]

数据 JSON（train）：
  [{"smiles":..,"label":0|1,"weight":..,
    "molecule_id": optional,
    "physchem":[101], "glide":[D], "glide_mask":0|1,
    "md_vec":[D_md], "md_mask":0|1, "reward_total": float}, ...]
结果写 stdout 最后一行 JSON。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
BACKEND_ROOT = "/data/ye/e-drug-lab/backend"
PHYSCHEM_SCALER = (
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/binding_RL/"
    "features_v1/physchem/physchem_scaler_train.json"
)
PHYSCHEM_CSV = (
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/binding_RL/"
    "features_v1/physchem/PAT_training_database_101D_stripped.csv"
)
MD_DIR = (
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/binding_RL/features_v1/md"
)


def _setup():
    sys.path.insert(0, BACKEND_ROOT)
    sys.path.insert(0, GLARE_ROOT)
    os.chdir(GLARE_ROOT)
    if os.environ.get("GLARE_FORCE_CPU", "0") == "1":
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    try:
        import captum  # noqa
    except ModuleNotFoundError:
        import types
        captum_mod = types.ModuleType("captum")
        attr_mod = types.ModuleType("captum.attr")
        import torch
        class _StubIG:
            def __init__(self, *a, **kw): pass
            def attribute(self, *a, **kw):
                return torch.zeros_like(a[0]), torch.tensor(0.0)
        attr_mod.IntegratedGradients = _StubIG
        captum_mod.attr = attr_mod
        sys.modules["captum"] = captum_mod
        sys.modules["captum.attr"] = attr_mod
    import model as glare_model  # noqa
    try:
        import torch_sparse  # noqa
    except ModuleNotFoundError:
        import types
        try:
            from torch_geometric.typing import SparseTensor as _ST
        except Exception:
            _ST = None
        ts = types.ModuleType("torch_sparse")
        if _ST is not None:
            ts.SparseTensor = _ST
        sys.modules["torch_sparse"] = ts
    from utils.utils import molecular_graph_featurizer, to_torch_dataloader, smiles_to_ecfp  # noqa
    from rdkit import Chem  # noqa
    mol_to_graph_data_obj_simple_3D = _make_mol_to_graph_3d()
    return glare_model, molecular_graph_featurizer, to_torch_dataloader, smiles_to_ecfp, mol_to_graph_data_obj_simple_3D, Chem


def _make_mol_to_graph_3d():
    import numpy as np
    import torch
    from rdkit import Chem
    possible_atomic_num = list(range(1, 119)) + [0]
    possible_chirality = ["CHI_UNSPECIFIED", "CHI_TETRAHEDRAL_CW", "CHI_TETRAHEDRAL_CCW", "CHI_OTHER"]
    possible_bonds = [Chem.BondType.SINGLE, Chem.BondType.DOUBLE, Chem.BondType.TRIPLE, Chem.BondType.AROMATIC]
    possible_bond_dirs = [Chem.BondDir.NONE, Chem.BondDir.ENDUPRIGHT, Chem.BondDir.ENDDOWNRIGHT]

    def _fn(mol):
        atom_features = []
        for atom in mol.GetAtoms():
            af = [possible_atomic_num.index(atom.GetAtomicNum() if atom.GetAtomicNum() in possible_atomic_num else 0)] + \
                 [possible_chirality.index(str(atom.GetChiralTag()))]
            atom_features.append(af)
        x = torch.tensor(np.array(atom_features), dtype=torch.long)
        if len(mol.GetBonds()) > 0:
            edges, edge_feats = [], []
            for bond in mol.GetBonds():
                i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
                ef = [possible_bonds.index(bond.GetBondType())] + [possible_bond_dirs.index(bond.GetBondDir())]
                edges += [(i, j), (j, i)]
                edge_feats += [ef, ef]
            edge_index = torch.tensor(np.array(edges).T, dtype=torch.long)
            edge_attr = torch.tensor(np.array(edge_feats), dtype=torch.long)
        else:
            edge_index = torch.empty((2, 0), dtype=torch.long)
            edge_attr = torch.empty((0, 2), dtype=torch.long)
        return x, edge_index, edge_attr
    return _fn


def _arch_flags(architecture: str) -> dict:
    a = (architecture or "ginl").lower()
    return {
        "strip": a != "ginl_raw",  # 默认 strip；ginl_raw 保留对照
        "use_pc": a in ("ginl_pc", "ginl_pc_gl", "ginl_pc_gl_md"),
        "use_gl": a in ("ginl_pc_gl", "ginl_pc_gl_md"),
        "use_md": a == "ginl_pc_gl_md",
        "architecture": "ginl" if a in ("ginl", "ginl_strip") else a,
    }


def _build_graph(smiles, y, fp, featurizer, mol_to_graph_3d, Chem, extras=None):
    """构建 GLARE graph，补 fp / xp / 多模态残差特征。"""
    g = featurizer(smiles, y=int(y), fp=fp)
    if isinstance(g, str):
        return None
    import torch as _t
    fp_t = _t.as_tensor(fp, dtype=_t.float) if not isinstance(fp, _t.Tensor) else fp.float()
    if fp_t.dim() == 1:
        fp_t = fp_t.unsqueeze(0)
    g.fp = fp_t
    mol = Chem.MolFromSmiles(smiles)
    if mol is not None:
        try:
            xp, edgep_index, edgep_attr = mol_to_graph_3d(mol)
            g.xp = xp
            g.edgep_index = edgep_index
            g.edgep_attr = edgep_attr
        except Exception:
            g.xp = g.x
            g.edgep_index = g.edge_index
            g.edgep_attr = getattr(g, "edge_attr", None)
    extras = extras or {}
    if "physchem" in extras:
        pc = _t.as_tensor(extras["physchem"], dtype=_t.float).view(1, -1)
        g.physchem = pc
    if "glide" in extras:
        g.glide = _t.as_tensor(extras["glide"], dtype=_t.float).view(1, -1)
        g.glide_mask = _t.tensor([float(extras.get("glide_mask", 0))], dtype=_t.float)
    if "md_vec" in extras:
        g.md_vec = _t.as_tensor(extras["md_vec"], dtype=_t.float).view(1, -1)
        g.md_mask = _t.tensor([float(extras.get("md_mask", 0))], dtype=_t.float)
        g.md_reward = _t.tensor([float(extras.get("reward_total", 0.0))], dtype=_t.float)
    return g


def _build_args(**kw):
    from argparse import Namespace
    defaults = dict(
        architecture="ginl", strategy="grpo", epochs=50, hidden_dim=1024,
        output_dim=2, mol_emb_dim=130, lr=3e-4, weight_decay=0.0,
        train_batch_size=64, infer_batch_size=512, ensemble_size=3, seed=0,
        anchored=True, grpo_lambda=7e-2, grpo_epsilon=2e-1, grpo_beta=1e-2,
        l2_lambda=3e-4, retrain=1, mode="a", cuda="gpu",
        mlp_fc_layer=3, gcn_graph_conv_layer=5, gcn_x_fc_layer=3,
        gin_graph_conv_layer=3, gin_x_fc_layer=3, gin_fp_fc_layer=3,
        gine_graph_conv_layer=3, gine_x_fc_layer=1, gine_fp_fc_layer=1,
        pretrain_file="", disable_ig=False,
        physchem_dim=0, glide_dim=0, md_dim=0,
        use_glide=False, use_md=False,
        beta_pc=0.1, beta_gl=0.1, beta_md=0.1,
        md_adv_eta=0.0,
    )
    defaults.update(kw)
    return Namespace(**defaults)


def _prepare_smiles_and_features(records, flags, Chem):
    """strip + 组装 physchem/glide/md。records: list[dict] 或 list[str]。"""
    from app.pipelines.vav1_rl.crbn_strip import strip_crbn_anchor_module
    from app.pipelines.vav1_rl.physchem_101 import PhysChemScaler, compute_physchem_101, load_frozen_column_names

    pc_scaler = None
    pc_cols = None
    glide_store = None
    md_store = None
    if flags["use_pc"]:
        pc_cols = load_frozen_column_names()
        if Path(PHYSCHEM_SCALER).is_file():
            pc_scaler = PhysChemScaler.load(PHYSCHEM_SCALER)
    if flags["use_gl"]:
        from app.pipelines.vav1_rl.glide_features import build_default_glide_store, GLIDE_DIM
        glide_store = build_default_glide_store()
        flags["glide_dim"] = GLIDE_DIM
    if flags["use_md"] and Path(MD_DIR, "md8_molecule_features.csv").is_file():
        from app.pipelines.vav1_rl.md_features import MDFeatureStore
        md_store = MDFeatureStore(Path(MD_DIR))
        flags["md_dim"] = md_store.dim

    out = []
    for rec in records:
        if isinstance(rec, str):
            rec = {"smiles": rec}
        raw = rec.get("smiles") or rec.get("smiles_raw")
        mid = rec.get("molecule_id") or rec.get("id")
        if flags["strip"]:
            st = strip_crbn_anchor_module(raw)
            smi = st["smiles_stripped"] if st.get("ok") and st.get("smiles_stripped") else raw
        else:
            smi = raw
        if not smi or Chem.MolFromSmiles(smi) is None:
            continue
        # 协议：去掉 borderline（label=-1），仅保留 0/1
        try:
            lab = int(rec.get("label", 0))
        except Exception:
            continue
        if lab not in (0, 1):
            continue
        extras = {}
        if flags["use_pc"]:
            if rec.get("physchem") is not None:
                extras["physchem"] = rec["physchem"]
            else:
                pc = compute_physchem_101(smi, column_names=pc_cols)
                vec = pc["vector"]
                if pc_scaler is not None:
                    import numpy as np
                    vec = pc_scaler.transform(np.asarray([vec], dtype=float))[0].tolist()
                else:
                    import numpy as np
                    vec = np.nan_to_num(np.asarray(vec, dtype=float), nan=0.0).tolist()
                extras["physchem"] = vec
        if flags["use_gl"]:
            if rec.get("glide") is not None:
                extras["glide"] = rec["glide"]
                extras["glide_mask"] = int(rec.get("glide_mask", 1))
            elif mid and glide_store is not None:
                g = glide_store.get(str(mid))
                extras["glide"] = g["glide_vec"]
                extras["glide_mask"] = g["glide_mask"]
            else:
                extras["glide"] = [0.0] * int(flags.get("glide_dim", 16))
                extras["glide_mask"] = 0
        if flags["use_md"]:
            if rec.get("md_vec") is not None:
                extras["md_vec"] = rec["md_vec"]
                extras["md_mask"] = int(rec.get("md_mask", 0))
                extras["reward_total"] = float(rec.get("reward_total", 0.0))
            elif mid and md_store is not None:
                m = md_store.get(str(mid))
                extras["md_vec"] = m["md_vec"]
                extras["md_mask"] = m["md_mask"]
                extras["reward_total"] = m["reward_total"]
            else:
                extras["md_vec"] = [0.0] * int(flags.get("md_dim", 46))
                extras["md_mask"] = 0
                extras["reward_total"] = 0.0
        out.append({
            "smiles": smi,
            "smiles_raw": raw,
            "label": lab,
            "weight": float(rec.get("weight", 1.0)),
            "molecule_id": mid,
            "extras": extras,
        })
    return out


def cmd_train(args):
    import numpy as np
    import torch
    from torch.utils.data import WeightedRandomSampler
    glare_model, featurizer, to_torch_dataloader, smiles_to_ecfp, mol_to_graph_3d, Chem = _setup()

    data = json.loads(Path(args.data).read_text())
    flags = _arch_flags(args.architecture)
    # strip for ginl baseline as well (plan: train/query unified strip)
    if args.architecture == "ginl":
        flags["strip"] = True
        flags["architecture"] = "ginl"
    prepared = _prepare_smiles_and_features(data, flags, Chem)
    if len(prepared) < 10:
        print(json.dumps({"ok": False, "error": f"样本不足 {len(prepared)}"}))
        return

    smiles = [p["smiles"] for p in prepared]
    labels = [p["label"] for p in prepared]
    weights = [p["weight"] for p in prepared]
    fps = smiles_to_ecfp(smiles, radius=2, nbits=1024)
    graphs, ys, ws = [], [], []
    from utils.utils import check_featurizability
    for smi, y, fp, w, p in zip(smiles, labels, fps, weights, prepared):
        if not check_featurizability(smi):
            continue
        g = _build_graph(smi, y, fp, featurizer, mol_to_graph_3d, Chem, extras=p["extras"])
        if g is None or isinstance(g, str):
            continue
        graphs.append(g)
        ys.append(y)
        ws.append(w)
    if len(graphs) < 10:
        print(json.dumps({"ok": False, "error": f"graph 样本不足 {len(graphs)}"}))
        return

    arch = flags["architecture"]
    ns_kw = dict(
        architecture=arch,
        ensemble_size=args.ensemble, epochs=args.epochs,
        lr=args.lr, grpo_epsilon=args.grpo_epsilon,
        grpo_beta=args.grpo_beta, grpo_lambda=args.grpo_lambda,
        l2_lambda=args.l2_lambda, weight_decay=args.weight_decay,
        train_batch_size=args.batch_size, strategy=args.strategy,
        disable_ig=getattr(args, "disable_ig", False),
        beta_pc=args.beta_pc, beta_gl=args.beta_gl, beta_md=args.beta_md,
        md_adv_eta=args.md_adv_eta,
    )
    if flags["use_pc"]:
        ns_kw["physchem_dim"] = 101
    if flags["use_gl"]:
        ns_kw["use_glide"] = True
        ns_kw["glide_dim"] = int(flags.get("glide_dim", 16))
    if flags["use_md"]:
        ns_kw["use_md"] = True
        ns_kw["md_dim"] = int(flags.get("md_dim", 46))
        if args.md_adv_eta == 0.0:
            ns_kw["md_adv_eta"] = 0.5  # R1+ 默认开启 shaping
    ns = _build_args(**ns_kw)

    y = np.array(ys, dtype=np.int64)
    n_pos, n_neg = int((y == 1).sum()), int((y == 0).sum())
    cw_pos = 1 - n_neg / max(len(y), 1)
    cw_neg = 1 - n_pos / max(len(y), 1)
    sample_w = [cw_pos * w if yi == 1 else cw_neg * w for yi, w in zip(y, ws)]
    sampler = WeightedRandomSampler(sample_w, num_samples=len(y), replacement=True)
    train_loader = to_torch_dataloader(
        graphs, y, batch_size=ns.train_batch_size, sampler=sampler, shuffle=False, pin_memory=False
    )

    ensemble = glare_model.Ensemble(ns)
    if args.prev and Path(args.prev).is_file():
        try:
            state = torch.load(args.prev, map_location="cpu", weights_only=False)
            state = state.get("state", state)
            for i, m in ensemble.models.items():
                if str(i) in state:
                    m.model.load_state_dict(state[str(i)], strict=False)
        except Exception:
            pass

    ensemble.train(train_loader)

    Path(args.ckpt).parent.mkdir(parents=True, exist_ok=True)
    state = {str(i): m.model.state_dict() for i, m in ensemble.models.items()}
    torch.save({"state": state, "args": vars(ns), "encoder_type": ns.architecture}, args.ckpt)
    losses = []
    for m in ensemble.models.values():
        losses.extend(m.train_loss)
    print(json.dumps({
        "ok": True, "checkpoint": args.ckpt,
        "final_loss": losses[-1] if losses else None,
        "n_samples": len(graphs), "encoder_type": ns.architecture,
        "strip": flags["strip"], "md_adv_eta": ns.md_adv_eta,
    }))


def cmd_query(args):
    import torch
    import numpy as np
    glare_model, featurizer, to_torch_dataloader, smiles_to_ecfp, mol_to_graph_3d, Chem = _setup()

    raw = json.loads(Path(args.smiles).read_text())
    # allow list[str] or list[dict]
    if raw and isinstance(raw[0], str):
        records = [{"smiles": s} for s in raw]
    else:
        records = raw

    ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    arch = ckpt.get("args", {}).get("architecture", args.architecture)
    flags = _arch_flags(arch)
    if arch == "ginl":
        flags["strip"] = True
        flags["architecture"] = "ginl"
    # restore dims from ckpt
    cargs = ckpt.get("args", {})
    if cargs.get("physchem_dim"):
        flags["use_pc"] = True
    if cargs.get("use_glide"):
        flags["use_gl"] = True
        flags["glide_dim"] = cargs.get("glide_dim", 16)
    if cargs.get("use_md"):
        flags["use_md"] = True
        flags["md_dim"] = cargs.get("md_dim", 46)

    prepared = _prepare_smiles_and_features(records, flags, Chem)
    smiles = [p["smiles"] for p in prepared]
    fps = smiles_to_ecfp(smiles, radius=2, nbits=1024)
    graphs, meta = [], []
    from utils.utils import check_featurizability
    for smi, fp, p in zip(smiles, fps, prepared):
        if not check_featurizability(smi):
            continue
        g = _build_graph(smi, 0, fp, featurizer, mol_to_graph_3d, Chem, extras=p["extras"])
        if g is None or isinstance(g, str):
            continue
        graphs.append(g)
        meta.append({
            "smiles": smi,
            "smiles_raw": p.get("smiles_raw") or smi,
            "molecule_id": p.get("molecule_id"),
        })
    if not graphs:
        print(json.dumps({"ok": False, "error": "无有效 graph", "ranked": []}))
        return

    ns = _build_args(ensemble_size=args.ensemble, epochs=50)
    for k, v in cargs.items():
        setattr(ns, k, v)
    ns.ensemble_size = args.ensemble
    ns.cuda = "cpu" if os.environ.get("GLARE_FORCE_CPU", "0") == "1" else "gpu"

    ensemble = glare_model.Ensemble(ns)
    state = ckpt.get("state", ckpt)
    for i, m in ensemble.models.items():
        if str(i) in state:
            m.model.load_state_dict(state[str(i)], strict=False)

    from torch_geometric.loader import DataLoader as _DL
    loader = _DL(graphs, batch_size=min(64, len(graphs)), shuffle=False)
    try:
        _dev = next(next(iter(ensemble.models.values())).model.parameters()).device
    except Exception:
        _dev = "cpu"
    all_logits = []
    with torch.no_grad():
        for batch in loader:
            batch = batch.to(_dev)
            per_model = []
            for m in ensemble.models.values():
                m.model.eval()
                yh = m.model(batch)
                if yh.dim() == 1:
                    yh = yh.unsqueeze(0)
                per_model.append(yh)
            all_logits.append(torch.stack(per_model, dim=1))
    logits = torch.cat(all_logits, dim=0).cpu()
    logits = torch.nan_to_num(logits.float(), nan=0.0)
    probs = torch.exp(logits)
    select = probs[:, :, 1].mean(dim=1)
    exclude = probs[:, :, 0].mean(dim=1)
    unc = probs[:, :, 1].std(dim=1)
    order = torch.argsort(select, descending=True).tolist()
    ranked = []
    for rank, idx in enumerate(order):
        ranked.append({
            "smiles": meta[idx]["smiles"],
            "smiles_raw": meta[idx]["smiles_raw"],
            "molecule_id": meta[idx]["molecule_id"],
            "glare_select_prob": float(select[idx]),
            "glare_exclude_prob": float(exclude[idx]),
            "glare_uncertainty": float(unc[idx]),
            "glare_policy_score": float(select[idx]),
            "glare_rank": rank + 1,
            "encoder_type": ns.architecture,
        })
    print(json.dumps({"ok": True, "ranked": ranked, "encoder_type": ns.architecture, "n": len(ranked)}))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    pt = sub.add_parser("train")
    pt.add_argument("--ckpt", required=True)
    pt.add_argument("--data", required=True)
    pt.add_argument("--prev", default=None)
    pt.add_argument("--epochs", type=int, default=50)
    pt.add_argument("--ensemble", type=int, default=3)
    pt.add_argument("--lr", type=float, default=3e-4)
    pt.add_argument("--grpo_epsilon", type=float, default=2e-1)
    pt.add_argument("--grpo_beta", type=float, default=1e-2)
    pt.add_argument("--grpo_lambda", type=float, default=7e-2)
    pt.add_argument("--l2_lambda", type=float, default=3e-4)
    pt.add_argument("--weight_decay", type=float, default=0.0)
    pt.add_argument("--batch_size", type=int, default=64)
    pt.add_argument("--strategy", type=str, default="grpo")
    pt.add_argument("--disable-ig", action="store_true", default=False)
    pt.add_argument("--architecture", type=str, default="ginl",
                    help="ginl | ginl_pc | ginl_pc_gl | ginl_pc_gl_md")
    pt.add_argument("--beta_pc", type=float, default=0.1)
    pt.add_argument("--beta_gl", type=float, default=0.1)
    pt.add_argument("--beta_md", type=float, default=0.1)
    pt.add_argument("--md_adv_eta", type=float, default=0.0,
                    help="MD GRPO advantage shaping; >0 enables (default 0.5 when arch has md)")
    pq = sub.add_parser("query")
    pq.add_argument("--ckpt", required=True)
    pq.add_argument("--smiles", required=True)
    pq.add_argument("--ensemble", type=int, default=3)
    pq.add_argument("--architecture", type=str, default="ginl")
    a = p.parse_args()
    if a.cmd == "train":
        cmd_train(a)
    else:
        cmd_query(a)


if __name__ == "__main__":
    main()
