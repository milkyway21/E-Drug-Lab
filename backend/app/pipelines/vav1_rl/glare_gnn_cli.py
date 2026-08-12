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

PROJECT_ROOT = Path("/data/ye/e-drug-lab/backend")
GLARE_ROOT = "/data/ye/diffgui/third_party/GLARE"
BACKEND_ROOT = str(PROJECT_ROOT)
PHYSCHEM_SCALER = str(
    PROJECT_ROOT / "outputs/vav1_rl_project/binding_RL/features_v1/physchem/"
    "physchem_scaler_train.json"
)
PHYSCHEM_CSV = str(
    PROJECT_ROOT / "outputs/vav1_rl_project/binding_RL/features_v1/physchem/"
    "PAT_training_database_101D_stripped.csv"
)
MD_DIR = str(PROJECT_ROOT / "outputs/vav1_rl_project/binding_RL/features_v1/md")


def _load_target_profile(args):
    from app.pipelines.vav1_rl.target_profile import load_or_infer_profile

    profile = load_or_infer_profile(
        getattr(args, "target_profile", None),
        target_id=getattr(args, "target_id", None),
        glide_table=getattr(args, "glide_table", None),
    )
    requested_target = getattr(args, "target_id", None)
    if requested_target and str(requested_target).lower() != "vav1" and profile is None:
        raise ValueError(
            "target_profile is required for every non-VAV1 target; target_id alone "
            "cannot select VAV1 feature files"
        )
    if profile is not None:
        profile.validate_files()
        if requested_target and str(requested_target) != profile.target_id:
            raise ValueError(
                f"target_id '{requested_target}' does not match profile target "
                f"'{profile.target_id}'"
            )
    return profile


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
        "use_pc": a in ("ginl_pc", "ginl_pc_gl", "ginl_pc_gl_md", "ginl_pc_gl_mdprior"),
        "use_gl": a in ("ginl_pc_gl", "ginl_pc_gl_md", "ginl_pc_gl_mdprior"),
        "use_md": a == "ginl_pc_gl_md",
        "use_md_prior": a == "ginl_pc_gl_mdprior",
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
        # MD-Glide consistency q_i（用于 mdprior 架构的 output gate）
        if "q" in extras:
            g.md_q = _t.tensor([float(extras.get("q", 0.0))], dtype=_t.float)
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
        use_md_prior=False,
        beta_pc=0.1, beta_gl=0.1, beta_md=0.1,
        md_adv_eta=0.0,
        fusion_type="fixed_residual",
        training_mode="supervised",
        gate_reg_lambda=0.0,
        md_bottleneck=0,
        continual_strategy="replay_anchor",
    )
    defaults.update(kw)
    return Namespace(**defaults)


def _prepare_smiles_and_features(
    records,
    flags,
    Chem,
    *,
    feature_schema=None,
    fit_disk_scaler=True,
    target_profile=None,
    train_ids=None,
):
    """strip + 组装 physchem/glide/md。

    feature_schema: 若提供（来自 checkpoint），优先用其中的 scaler，禁止再 fit。
    fit_disk_scaler: 训练首轮可读磁盘 scaler；query 应 False 或仅 legacy。
    返回 (prepared_list, stores_dict) stores 用于写 schema。
    """
    import numpy as np
    from app.pipelines.vav1_rl.crbn_strip import strip_crbn_anchor_module
    from app.pipelines.vav1_rl.physchem_101 import PhysChemScaler, compute_physchem_101, load_frozen_column_names
    from app.pipelines.vav1_rl import checkpoint_io as ckio

    pc_scaler = None
    pc_cols = None
    glide_store = None
    md_store = None
    schema = feature_schema or {}

    if flags["use_pc"]:
        pc_cols = load_frozen_column_names()
        if schema.get("physchem"):
            pc_scaler = ckio.scaler_from_schema_block(schema["physchem"])
            if schema["physchem"].get("columns"):
                pc_cols = list(schema["physchem"]["columns"])
        elif fit_disk_scaler and Path(PHYSCHEM_SCALER).is_file():
            pc_scaler = PhysChemScaler.load(PHYSCHEM_SCALER)
    if flags["use_gl"]:
        from app.pipelines.vav1_rl.glide_features import build_default_glide_store, GLIDE_DIM
        profile_train_ids = None
        if target_profile is not None and feature_schema is None:
            profile_train_ids = set(train_ids or ())
            if not profile_train_ids:
                raise ValueError(
                    "target-profile Glide training requires molecule_id values in records"
                )
        glide_store = build_default_glide_store(
            profile=target_profile,
            train_ids=profile_train_ids,
            fit_all=feature_schema is not None,
        )
        saved_glide = schema.get("glide") or {}
        if saved_glide.get("mean") is not None and saved_glide.get("std") is not None:
            if (
                len(saved_glide["mean"]) != glide_store.feature_dim
                or len(saved_glide["std"]) != glide_store.feature_dim
            ):
                raise ValueError("checkpoint Glide schema dimension does not match target profile")
            glide_store.mean = np.asarray(saved_glide["mean"], dtype=float)
            glide_store.std = np.nan_to_num(
                np.where(
                    np.asarray(saved_glide["std"], dtype=float) < 1e-8,
                    1.0,
                    np.asarray(saved_glide["std"], dtype=float),
                ),
                nan=1.0,
            )
        flags["glide_dim"] = int(
            schema.get("glide", {}).get("dim") or glide_store.feature_dim or GLIDE_DIM
        )
    if target_profile and target_profile.md_dir:
        md_root = Path(target_profile.md_dir)
    elif target_profile is None or target_profile.target_id == "vav1":
        md_root = Path(MD_DIR)
    else:
        md_root = None
    if flags["use_md"] and md_root is not None and (md_root / "md8_molecule_features.csv").is_file():
        from app.pipelines.vav1_rl.md_features import MDFeatureStore
        md_store = MDFeatureStore(md_root)
        flags["md_dim"] = int(schema.get("md", {}).get("dim") or md_store.dim)

    allow_no_label = bool(flags.get("allow_no_label", False))
    out = []
    for rec in records:
        if isinstance(rec, str):
            rec = {"smiles": rec}
        raw = rec.get("smiles") or rec.get("smiles_raw")
        mid = next(
            (
                rec.get(key)
                for key in ("molecule_id", "generated_id", "compound_id", "mol_id", "id")
                if rec.get(key) not in (None, "")
            ),
            None,
        )
        if flags["strip"]:
            st = strip_crbn_anchor_module(raw)
            smi = st["smiles_stripped"] if st.get("ok") and st.get("smiles_stripped") else raw
        else:
            smi = raw
        if not smi or Chem.MolFromSmiles(smi) is None:
            continue
        raw_label = rec.get("label", rec.get("label_active"))
        if raw_label is not None and str(raw_label) != "":
            try:
                lab = int(raw_label)
            except Exception:
                continue
            if lab not in (0, 1):
                continue
        else:
            if not allow_no_label:
                continue
            lab = 0
        extras = {}
        if flags["use_pc"]:
            if rec.get("physchem") is not None:
                extras["physchem"] = rec["physchem"]
            else:
                pc = compute_physchem_101(smi, column_names=pc_cols)
                vec = pc["vector"]
                if pc_scaler is not None:
                    vec = pc_scaler.transform(np.asarray([vec], dtype=float))[0].tolist()
                else:
                    vec = np.nan_to_num(np.asarray(vec, dtype=float), nan=0.0).tolist()
                extras["physchem"] = vec
        if flags["use_gl"]:
            if rec.get("glide") is not None:
                extras["glide"] = rec["glide"]
                extras["glide_mask"] = int(rec.get("glide_mask", 1))
                # MD-Glide consistency q_i（mdprior 架构用）
                if flags.get("use_md_prior"):
                    extras["q"] = float(rec.get("q", 0.0))
            elif mid and glide_store is not None:
                g = glide_store.get(str(mid))
                extras["glide"] = g["glide_vec"]
                extras["glide_mask"] = g["glide_mask"]
                # MD-Glide consistency q_i（mdprior 架构用）
                if flags.get("use_md_prior"):
                    extras["q"] = float(g.get("q", 0.0))
            else:
                extras["glide"] = [0.0] * int(flags.get("glide_dim", 16))
                extras["glide_mask"] = 0
                if flags.get("use_md_prior"):
                    extras["q"] = 0.0
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
                extras["md_vec"] = [0.0] * int(flags.get("md_dim", 16))
                extras["md_mask"] = 0
                extras["reward_total"] = 0.0
        out.append({
            "smiles": smi,
            "smiles_raw": raw,
            "label": lab,
            "weight": float(rec.get("weight", 1.0)),
            "molecule_id": mid,
            "extras": extras,
            "glide_mask": int(extras.get("glide_mask", 0)),
            "md_mask": int(extras.get("md_mask", 0)),
            "physchem": extras.get("physchem"),
        })
    stores = {"pc_scaler": pc_scaler, "pc_cols": pc_cols, "glide_store": glide_store, "md_store": md_store}
    return out, stores


def _build_schema_from_stores(stores, flags, target_profile=None, profile_path=None):
    from app.pipelines.vav1_rl import checkpoint_io as ckio
    pc = None
    gl = None
    md = None
    if flags.get("use_pc") and stores.get("pc_scaler") is not None:
        cols = stores.get("pc_cols") or []
        pc = ckio.physchem_schema_from_scaler(stores["pc_scaler"], cols)
    if flags.get("use_gl") and stores.get("glide_store") is not None:
        gl = ckio.glide_schema_from_store(stores["glide_store"])
    if flags.get("use_md") and stores.get("md_store") is not None:
        md = ckio.md_schema_from_store(stores["md_store"])
    return ckio.build_feature_schema(
        physchem=pc,
        glide=gl,
        md=md,
        target_id=target_profile.target_id if target_profile else None,
        profile_path=profile_path or (str(target_profile.glide_table) if target_profile else None),
    )


def cmd_train(args):
    import numpy as np
    import torch
    import warnings
    from torch.utils.data import WeightedRandomSampler
    from app.pipelines.vav1_rl import checkpoint_io as ckio

    glare_model, featurizer, to_torch_dataloader, smiles_to_ecfp, mol_to_graph_3d, Chem = _setup()

    data = json.loads(Path(args.data).read_text())
    target_profile = _load_target_profile(args)
    flags = _arch_flags(args.architecture)
    if args.architecture == "ginl":
        flags["strip"] = True
        flags["architecture"] = "ginl"
    if getattr(args, "enable_md", False):
        flags["use_md"] = True
        if flags["architecture"] == "ginl_pc_gl":
            flags["architecture"] = "ginl_pc_gl_md"

    parent_sha = None
    parent_path = None
    loaded_parent = None
    if args.prev:
        parent_path = str(Path(args.prev))
        loaded_parent = ckio.load_checkpoint_file(
            args.prev,
            allow_legacy_pickle=bool(getattr(args, "allow_legacy_pickle", False)),
        )
        parent_sha = loaded_parent["sha256"]
        ckio.verify_architecture(
            loaded_parent["ckpt"].get("args", {}), flags["architecture"]
        )
        if target_profile is not None:
            if loaded_parent["legacy_mode"] and target_profile.target_id != "vav1":
                raise RuntimeError(
                    "a legacy VAV1 checkpoint cannot seed a non-VAV1 target run; "
                    "train the new target from an explicit target profile"
                )
        elif (loaded_parent["ckpt"].get("feature_schema") or {}).get("glide", {}).get("version") == "glide_target_v2":
            raise RuntimeError(
                "target-profile is required to continue a target-independent checkpoint"
            )
        if loaded_parent["legacy_mode"]:
            warnings.warn(f"[legacy] prev checkpoint has no feature_schema: {args.prev}", stacklevel=1)

    record_ids = {
        str(rec.get(key))
        for rec in data
        if isinstance(rec, dict)
        for key in ("molecule_id", "generated_id", "compound_id", "mol_id", "id")
        if rec.get(key) not in (None, "")
    }
    prepared, stores = _prepare_smiles_and_features(
        data,
        flags,
        Chem,
        fit_disk_scaler=True,
        target_profile=target_profile,
        train_ids=record_ids,
    )
    feature_schema = _build_schema_from_stores(
        stores,
        flags,
        target_profile,
        profile_path=getattr(args, "target_profile", None),
    )
    if loaded_parent is not None:
        ckio.validate_target_schema(
            loaded_parent["ckpt"],
            target_id=target_profile.target_id if target_profile else None,
            feature_schema=feature_schema,
        )
    if len(prepared) < 10:
        print(json.dumps({"ok": False, "error": f"样本不足 {len(prepared)}"}))
        return

    coverage = ckio.compute_coverage(prepared)
    ckio.enforce_coverage(
        coverage,
        architecture=flags["architecture"],
        min_glide_coverage=float(getattr(args, "min_glide_coverage", 0.0) or 0.0),
        min_md_coverage=float(getattr(args, "min_md_coverage", 0.0) or 0.0),
        fail_on_low_coverage=bool(getattr(args, "fail_on_low_coverage", False)),
    )

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
        # track md for sampler cap
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
        fusion_type=getattr(args, "fusion_type", "fixed_residual"),
        training_mode=getattr(args, "training_mode", "supervised"),
        gate_reg_lambda=float(getattr(args, "gate_reg_lambda", 0.0) or 0.0),
        md_bottleneck=int(getattr(args, "md_bottleneck", 0) or 0),
        continual_strategy=getattr(args, "continual_strategy", "replay_anchor"),
        anchored=True,
    )
    if flags["use_pc"]:
        ns_kw["physchem_dim"] = 101
    if flags["use_gl"]:
        ns_kw["use_glide"] = True
        ns_kw["glide_dim"] = int(flags.get("glide_dim", 16))
    if flags["use_md"]:
        ns_kw["use_md"] = True
        ns_kw["md_dim"] = int(flags.get("md_dim", 16))
        if args.md_adv_eta == 0.0:
            ns_kw["md_adv_eta"] = 0.5
    if flags.get("use_md_prior"):
        ns_kw["use_md_prior"] = True
    ns = _build_args(**ns_kw)

    y = np.array(ys, dtype=np.int64)
    n_pos, n_neg = int((y == 1).sum()), int((y == 0).sum())
    cw_pos = 1 - n_neg / max(len(y), 1)
    cw_neg = 1 - n_pos / max(len(y), 1)
    # 限制 MD 样本在采样权重上的放大，避免 8 个分子霸占 epoch
    # mdprior 架构：MD 信息通过 q_i gate 传播，不需要 MD 样本过采样
    md_cap = float(getattr(args, "md_sample_weight_cap", 3.0) or 3.0)
    skip_md_oversample = bool(flags.get("use_md_prior"))
    sample_w = []
    for yi, w, p in zip(y, ws, prepared[: len(ys)]):
        # prepared 与 graphs 可能因 featurize 失败不对齐；用长度截断后的对应
        base = cw_pos * w if yi == 1 else cw_neg * w
        sample_w.append(base)
    # 重新按 graphs 顺序对齐 md_mask（与上面 loop 一致）
    sample_w = []
    gi = 0
    for smi, yi, fp, w, p in zip(smiles, labels, fps, weights, prepared):
        if not check_featurizability(smi):
            continue
        # graph already built earlier; recompute weight only for kept
        base = (cw_pos * w) if yi == 1 else (cw_neg * w)
        if not skip_md_oversample and int(p.get("md_mask", 0)) == 1:
            base = min(base * 2.0, base * md_cap) if base > 0 else base
            # actually: cap absolute weight
            base = min(base, md_cap * max(cw_pos, cw_neg, 1e-6))
        sample_w.append(base)
        gi += 1
        if gi >= len(graphs):
            break
    if len(sample_w) != len(graphs):
        sample_w = [cw_pos * w if yi == 1 else cw_neg * w for yi, w in zip(y, ws)]

    sampler = WeightedRandomSampler(sample_w, num_samples=len(y), replacement=True)
    train_loader = to_torch_dataloader(
        graphs, y, batch_size=ns.train_batch_size, sampler=sampler, shuffle=False, pin_memory=False
    )

    ensemble = glare_model.Ensemble(ns)
    load_reports = []
    if loaded_parent is not None:
        ckpt = loaded_parent["ckpt"]
        state = ckpt.get("state", ckpt)
        for i, m in ensemble.models.items():
            if str(i) not in state:
                raise RuntimeError(f"prev checkpoint missing ensemble member {i}")
            rep = ckio.load_state_dict_strictly(m.model, state[str(i)])
            load_reports.append(rep)
        # 关键：先 load 再设 anchor（previous-model anchor）
        ensemble.set_anchor_from_current_weights()
        print(json.dumps({
            "event": "prev_loaded",
            "parent": parent_path,
            "parent_sha256": parent_sha,
            "anchor_distance": ensemble.anchor_distance_mean(),
            "load_reports": load_reports,
        }), flush=True)
    else:
        # R0：anchor 已在 Model.__init__ 设为初始权重
        print(json.dumps({
            "event": "r0_init",
            "anchor_distance": ensemble.anchor_distance_mean(),
        }), flush=True)

    if getattr(args, "train_md_adapter_only", False) or getattr(args, "freeze_base", False):
        ensemble.freeze_base_train_md_only()

    ensemble.train(train_loader)

    Path(args.ckpt).parent.mkdir(parents=True, exist_ok=True)
    state = {str(i): m.model.state_dict() for i, m in ensemble.models.items()}
    payload = ckio.dump_ckpt_payload(
        state=state,
        args=vars(ns),
        encoder_type=ns.architecture,
        feature_schema=feature_schema,
        parent_checkpoint=parent_path,
        parent_sha256=parent_sha,
        coverage=coverage,
        target_id=target_profile.target_id if target_profile else None,
        profile_path=str(args.target_profile) if args.target_profile else None,
    )
    torch.save(payload, args.ckpt)
    losses = []
    loss_comp = []
    for m in ensemble.models.values():
        losses.extend(m.train_loss)
        if getattr(m, "loss_components", None):
            loss_comp.extend(m.loss_components)
    print(json.dumps({
        "ok": True, "checkpoint": args.ckpt,
        "sha256": ckio.file_sha256(args.ckpt),
        "final_loss": losses[-1] if losses else None,
        "n_samples": len(graphs), "encoder_type": ns.architecture,
        "strip": flags["strip"], "md_adv_eta": ns.md_adv_eta,
        "fusion_type": ns.fusion_type,
        "training_mode": ns.training_mode,
        "coverage": coverage,
        "parent_checkpoint": parent_path,
        "anchor_distance_end": ensemble.anchor_distance_mean(),
        "loss_components_last": loss_comp[-1] if loss_comp else None,
        "note": "strategy=grpo means grpo_style_classifier_regularization, not generative GRPO",
    }))


def cmd_query(args):
    import torch
    import warnings
    from app.pipelines.vav1_rl import checkpoint_io as ckio

    glare_model, featurizer, to_torch_dataloader, smiles_to_ecfp, mol_to_graph_3d, Chem = _setup()

    raw = json.loads(Path(args.smiles).read_text())
    if raw and isinstance(raw[0], str):
        records = [{"smiles": s} for s in raw]
    else:
        records = raw

    loaded = ckio.load_checkpoint_file(
        args.ckpt,
        allow_legacy_pickle=bool(getattr(args, "allow_legacy_pickle", False)),
    )
    ckpt = loaded["ckpt"]
    if loaded["legacy_mode"]:
        warnings.warn(f"[legacy] checkpoint lacks feature_schema; using disk scalers: {args.ckpt}", stacklevel=1)

    target_profile = _load_target_profile(args)
    requested_target = target_profile.target_id if target_profile else getattr(args, "target_id", None)
    ckio.validate_target_schema(ckpt, target_id=requested_target)
    if loaded["legacy_mode"] and requested_target and requested_target != "vav1":
        raise RuntimeError(
            "a legacy VAV1 checkpoint cannot be queried for a non-VAV1 target; "
            "train a target-profile checkpoint first"
        )
    saved_schema = ckpt.get("feature_schema") or {}
    if saved_schema.get("glide", {}).get("version") == "glide_target_v2" and target_profile is None:
        raise RuntimeError(
            "target-profile is required to query a target-independent checkpoint"
        )

    requested_architecture = getattr(args, "architecture", None)
    arch = ckpt.get("args", {}).get("architecture", requested_architecture)
    ckio.verify_architecture(ckpt.get("args", {}), requested_architecture or arch)
    flags = _arch_flags(arch)
    if arch == "ginl":
        flags["strip"] = True
        flags["architecture"] = "ginl"
    flags["allow_no_label"] = True
    cargs = ckpt.get("args", {})
    if cargs.get("physchem_dim"):
        flags["use_pc"] = True
    if cargs.get("use_glide"):
        flags["use_gl"] = True
        flags["glide_dim"] = cargs.get("glide_dim", 16)
    if cargs.get("use_md"):
        flags["use_md"] = True
        flags["md_dim"] = cargs.get("md_dim", 47)
    if cargs.get("use_md_prior"):
        flags["use_md_prior"] = True

    schema = ckpt.get("feature_schema")
    saved_schema_hash = None
    if schema:
        saved_schema_hash = schema.get("schema_hash") or ckio.schema_hash(schema)
    prepared, _stores = _prepare_smiles_and_features(
        records, flags, Chem,
        feature_schema=schema,
        fit_disk_scaler=bool(schema is None),  # legacy only
        target_profile=target_profile,
    )
    current_schema = _build_schema_from_stores(
        _stores,
        flags,
        target_profile,
        profile_path=getattr(args, "target_profile", None),
    )
    if schema and target_profile is not None:
        ckio.validate_target_schema(
            ckpt,
            target_id=requested_target,
            feature_schema=current_schema,
        )
    coverage = ckio.compute_coverage(prepared)
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
        gl_obs = int(p.get("glide_mask", 0)) == 1
        md_obs = int(p.get("md_mask", 0)) == 1
        mods = ["graph", "fp"]
        if flags.get("use_pc"):
            mods.append("physchem")
        if flags.get("use_gl") and gl_obs:
            mods.append("glide")
        if flags.get("use_md") and md_obs:
            mods.append("md")
        meta.append({
            "smiles": smi,
            "smiles_raw": p.get("smiles_raw") or smi,
            "molecule_id": p.get("molecule_id"),
            "glide_observed": gl_obs,
            "md_observed": md_obs,
            "modalities_used": mods,
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
        if str(i) not in state:
            raise RuntimeError(f"checkpoint missing ensemble member {i}")
        ckio.load_state_dict_strictly(m.model, state[str(i)])

    from torch_geometric.loader import DataLoader as _DL
    geo_loader = _DL(graphs, batch_size=min(64, len(graphs)), shuffle=False)
    try:
        _dev = next(next(iter(ensemble.models.values())).model.parameters()).device
    except Exception:
        _dev = "cpu"
    all_logits = []
    with torch.no_grad():
        for batch in geo_loader:
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
        row = dict(meta[idx])
        row.update({
            "glare_select_prob": float(select[idx]),
            "glare_exclude_prob": float(exclude[idx]),
            "glare_uncertainty": float(unc[idx]),
            "glare_policy_score": float(select[idx]),
            "score": float(select[idx]),
            "glare_rank": rank + 1,
            "encoder_type": ns.architecture,
        })
        ranked.append(row)
    print(json.dumps({
        "ok": True,
        "ranked": ranked,
        "encoder_type": ns.architecture,
        "n": len(ranked),
        "coverage": coverage,
        "ckpt_sha256": loaded["sha256"],
        "feature_schema_hash": saved_schema_hash,
        "legacy_mode": loaded["legacy_mode"],
        "fusion_type": getattr(ns, "fusion_type", "fixed_residual"),
    }))


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
    pt.add_argument("--strategy", type=str, default="grpo",
                    help="legacy name; with training_mode forms grpo_style_classifier_regularization")
    pt.add_argument("--training_mode", type=str, default="supervised",
                    choices=["supervised", "bandit", "grpo_style_classifier_regularization"])
    pt.add_argument("--disable-ig", action="store_true", default=False)
    pt.add_argument("--architecture", type=str, default="ginl",
                    help="ginl | ginl_pc | ginl_pc_gl | ginl_pc_gl_md")
    pt.add_argument("--fusion_type", type=str, default="fixed_residual",
                    choices=["fixed_residual", "learnable_gate"])
    pt.add_argument("--gate_reg_lambda", type=float, default=0.0)
    pt.add_argument("--beta_pc", type=float, default=0.1)
    pt.add_argument("--beta_gl", type=float, default=0.1)
    pt.add_argument("--beta_md", type=float, default=0.1)
    pt.add_argument("--md_adv_eta", type=float, default=0.0,
                    help="MD advantage shaping; >0 enables (default 0.5 when arch has md)")
    pt.add_argument("--md_bottleneck", type=int, default=0, help="MD MLP hidden; 0=full hidden_dim")
    pt.add_argument("--enable-md", action="store_true", default=False)
    pt.add_argument("--train-md-adapter-only", action="store_true", default=False)
    pt.add_argument("--freeze-base", action="store_true", default=False)
    pt.add_argument("--continual-strategy", type=str, default="replay_anchor",
                    choices=["replay", "replay_anchor", "replay_distill", "replay_anchor_distill"])
    pt.add_argument("--min_glide_coverage", type=float, default=0.0)
    pt.add_argument("--min_md_coverage", type=float, default=0.0)
    pt.add_argument("--fail_on_low_coverage", action="store_true", default=False)
    pt.add_argument("--md_sample_weight_cap", type=float, default=3.0)
    pt.add_argument("--target-profile", default=None)
    pt.add_argument("--target-id", default=None)
    pt.add_argument("--glide-table", default=None)
    pt.add_argument(
        "--allow-legacy-pickle",
        action="store_true",
        default=False,
        help="allow unsafe pickle loading for a trusted legacy VAV1 checkpoint",
    )
    pq = sub.add_parser("query")
    pq.add_argument("--ckpt", required=True)
    pq.add_argument("--smiles", required=True)
    pq.add_argument("--ensemble", type=int, default=3)
    pq.add_argument("--architecture", type=str, default=None)
    pq.add_argument("--target-profile", default=None)
    pq.add_argument("--target-id", default=None)
    pq.add_argument("--glide-table", default=None)
    pq.add_argument(
        "--allow-legacy-pickle",
        action="store_true",
        default=False,
        help="allow unsafe pickle loading for a trusted legacy VAV1 checkpoint",
    )
    a = p.parse_args()
    if a.cmd == "train":
        cmd_train(a)
    else:
        cmd_query(a)


if __name__ == "__main__":
    main()
