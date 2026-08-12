"""VAV1 MD 八体系特征工程（按分子聚合，禁止 window 泄漏切分）。

约束（plan §9）：
- reward_* 全 NaN → 自行计算
- is_key_residue 全 False → 从 md_vav1_consensus_weights.csv 注入
- 0185087 ↔ 0185078 别名
- 仅 protein_component==VAV1 关键残基进入 md_vec
- 一切聚合带 *_observed；禁止 silent 填 0 当观测
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import yaml

BINDING_RL = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/binding_RL")
MD_ROOT = (
    BINDING_RL
    / "MD_information"
    / "VAV1_RL_RELEASE"
    / "VAV1_RL_dataset_8systems_v1"
)
COMBINED = MD_ROOT / "COMBINED"
CONSENSUS_CSV = BINDING_RL / "patent_screening" / "results" / "md_vav1_consensus_weights.csv"
OUT_DIR = BINDING_RL / "features_v1" / "md"

# occupancy / interaction / frame IFP 实际覆盖的 11 个关键残基（上游 DESMOND 统计范围）
KEY_RESIDUES = [796, 797, 798, 799, 800, 815, 816, 817, 818, 820, 831]

# dynamic_window / mmgbsa 表覆盖的 19 个残基（energy/rmsf 可扩展到的全部残基）
# 并集：KEY_RESIDUES 11 + dynamic_window 独有 8（793,801,813,819,821,822,832,833）
DYN_RESIDUES = [793, 796, 797, 798, 799, 800, 801, 813, 815, 816, 817, 818, 819, 820, 821, 822, 831, 832, 833]

# 特征工程覆盖的残基集合：energy/rmsf 扩展到 DYN_RESIDUES 全部 19 个
# occupancy 仍以 KEY_RESIDUES 为准（上游无数据），其余残基 occupancy 填 0
FEATURE_RESIDUES = DYN_RESIDUES

INTERACTION_CANON = {
    "HBA": "HBAcceptor",
    "HBAcceptor": "HBAcceptor",
    "HBD": "HBDonor",
    "HBDonor": "HBDonor",
    "Hydrophobic": "Hydrophobic",
    "PiStacking": "PiStacking",
    "PiCation": "PiCation",
    "VdWContact": "VdWContact",
}
TYPE_ORDER = ["HBDonor", "HBAcceptor", "Hydrophobic", "PiStacking", "PiCation", "VdWContact"]

# ID 别名：MD molecule_id ↔ wetlab/专利侧标签
DEFAULT_ID_ALIASES = {
    "0185087": ["0185087", "0185078", "185087", "185078"],
    "0185078": ["0185087", "0185078", "185087", "185078"],
}


def _norm_mol_id(x: Any) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip()
    if s.lower() in ("nan", "none", "<na>"):
        return ""
    try:
        if s.replace(".", "", 1).replace("-", "", 1).isdigit():
            v = float(s)
            if abs(v - int(v)) < 1e-9:
                return f"{int(v):07d}" if abs(int(v)) < 10_000_000 else str(int(v))
    except Exception:
        pass
    return s


def load_consensus_weights(path: Path = CONSENSUS_CSV) -> dict[int, float]:
    """加载 MD 共识权重（occupancy 归一化）。

    返回覆盖 FEATURE_RESIDUES 19 个残基的权重字典，缺失残基权重=0；
    归一化只在有权重的 11 个残基上做，保持相对比例不变。
    """
    df = pd.read_csv(path)
    col_res = "canonical_res_num" if "canonical_res_num" in df.columns else df.columns[0]
    col_w = "weight" if "weight" in df.columns else df.columns[1]
    w = {int(r[col_res]): float(r[col_w]) for _, r in df.iterrows()}
    out = {r: float(w.get(r, 0.0)) for r in FEATURE_RESIDUES}
    s = sum(out.values())
    if s <= 0:
        out = {r: 1.0 / len(FEATURE_RESIDUES) for r in FEATURE_RESIDUES}
    else:
        out = {r: v / s for r, v in out.items()}
    return out


def build_id_map(molecule_ids: list[str], source_labels: dict[str, str]) -> dict[str, Any]:
    aliases: dict[str, list[str]] = {}
    for mid in molecule_ids:
        mid_n = _norm_mol_id(mid)
        al = set(DEFAULT_ID_ALIASES.get(mid_n, [mid_n]))
        al.add(mid_n)
        src = source_labels.get(mid) or source_labels.get(mid_n)
        if src:
            al.add(_norm_mol_id(src))
            al.add(str(src).strip())
        aliases[mid_n] = sorted({a for a in al if a})
    # reverse lookup
    rev: dict[str, str] = {}
    for canon, als in aliases.items():
        for a in als:
            rev[a] = canon
    return {"canonical_to_aliases": aliases, "alias_to_canonical": rev}


def _read_parquet(name: str) -> pd.DataFrame:
    path = COMBINED / name
    if not path.is_file():
        # 顶层也可能有副本
        alt = MD_ROOT / name
        path = alt if alt.is_file() else path
    return pd.read_parquet(path)


def _feature_spec() -> dict[str, Any]:
    names: list[str] = []
    defs: dict[str, str] = {}
    for r in FEATURE_RESIDUES:
        n = f"occ_r{r}"
        names.append(n)
        defs[n] = f"VAV1 残基 {r} 的 any_interaction_occupancy（轨迹级，MD 无数据残基为 0）"
    names.append("occ_w")
    defs["occ_w"] = "关键残基加权占有 Σ w_r·occ_r"
    for t in TYPE_ORDER:
        n = f"type_{t}"
        names.append(n)
        defs[n] = f"关键残基上 {t} 相互作用平均 occupancy"
    for r in FEATURE_RESIDUES:
        n = f"energy_r{r}"
        names.append(n)
        defs[n] = f"残基 {r} ΔTDC_total 均值经 tanh 有界（仅 observed）"
    names += ["energy_w", "energy_cover"]
    defs["energy_w"] = "关键残基能量加权和（tanh 空间）"
    defs["energy_cover"] = "关键残基能量观测覆盖率"
    for r in FEATURE_RESIDUES:
        n = f"rmsf_r{r}"
        names.append(n)
        defs[n] = f"残基 {r} RMSF(Å)，仅 observed"
    names.append("rmsf_w")
    defs["rmsf_w"] = "关键残基加权 RMSF"
    for n, d in [
        ("persist_early", "前 20% window 关键残基平均占有"),
        ("persist_late", "后 20% window 关键残基平均占有"),
        ("persist_delta", "persist_late - persist_early"),
        ("complete_rate", "关键残基×window 有占有观测的完整率"),
    ]:
        names.append(n)
        defs[n] = d
    return {
        "dim": len(names),
        "names": names,
        "definitions": defs,
        "key_residues": FEATURE_RESIDUES,
        "type_order": TYPE_ORDER,
        "protein_component": "VAV1",
    }


def _default_reward_config() -> dict[str, Any]:
    return {
        "weights": {
            "reward_key_hit": 0.35,
            "reward_persistence": 0.20,
            "reward_interaction_type": 0.15,
            "reward_energy": 0.20,
            "penalty_flexibility": 0.05,
            "penalty_missing": 0.05,
        },
        "energy_center": -1.5,
        "energy_scale": 2.0,
        "rmsf_center": 1.5,
        "rmsf_scale": 1.0,
        "md_mask_min_key_cover": 0.6,
        "md_mask_min_complete_rate": 0.5,
    }


def compute_rewards(
    feat: dict[str, float],
    *,
    cfg: dict[str, Any],
    type_vals: dict[str, float],
) -> dict[str, float]:
    w = cfg["weights"]
    occ_w = float(feat.get("occ_w", 0.0))
    persist_late = float(feat.get("persist_late", 0.0))
    persist_delta = float(feat.get("persist_delta", 0.0))
    energy_w = float(feat.get("energy_w", 0.0))
    rmsf_w = float(feat.get("rmsf_w", 0.0))
    complete = float(feat.get("complete_rate", 0.0))

    reward_key_hit = float(np.clip(occ_w, 0, 1))
    reward_persistence = float(np.clip(0.5 * persist_late + 0.5 * (persist_delta + 1) / 2, 0, 1))
    # 偏好 Hbond / Pi，弱化纯 VdW
    tw = {
        "HBDonor": 0.25,
        "HBAcceptor": 0.25,
        "Hydrophobic": 0.15,
        "PiStacking": 0.2,
        "PiCation": 0.1,
        "VdWContact": 0.05,
    }
    reward_interaction_type = float(
        np.clip(sum(tw[t] * float(type_vals.get(t, 0.0)) for t in TYPE_ORDER), 0, 1)
    )
    # energy_w 已在 tanh 空间约 [-1,1]，越负越好 → 取 -energy 映射到 [0,1] 近似
    reward_energy = float(np.clip(0.5 * (1.0 - energy_w), 0, 1))
    penalty_flexibility = float(
        np.clip((rmsf_w - cfg["rmsf_center"]) / max(cfg["rmsf_scale"], 1e-6), 0, 1)
    )
    penalty_missing = float(np.clip(1.0 - complete, 0, 1))

    total = (
        w["reward_key_hit"] * reward_key_hit
        + w["reward_persistence"] * reward_persistence
        + w["reward_interaction_type"] * reward_interaction_type
        + w["reward_energy"] * reward_energy
        - w["penalty_flexibility"] * penalty_flexibility
        - w["penalty_missing"] * penalty_missing
    )
    # 映射到约 [-1,1]
    reward_total = float(np.clip(2 * total - 1, -1, 1))
    return {
        "reward_key_hit": reward_key_hit,
        "reward_persistence": reward_persistence,
        "reward_interaction_type": reward_interaction_type,
        "reward_energy": reward_energy,
        "penalty_flexibility": penalty_flexibility,
        "penalty_missing": penalty_missing,
        "reward_total": reward_total,
    }


def build_md8_features(
    *,
    out_dir: Path = OUT_DIR,
    consensus_csv: Path = CONSENSUS_CSV,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = _default_reward_config()
    weights = load_consensus_weights(consensus_csv)
    spec = _feature_spec()

    occ = _read_parquet("all8_residue_occupancy_canonical.parquet")
    ix = _read_parquet("all8_interaction_occupancy_canonical.parquet")
    rmsf = _read_parquet("all8_rmsf_residue.parquet")
    dyn = _read_parquet("all8_dynamic_window_residue.parquet")

    # 规范化
    for df in (occ, ix, rmsf, dyn):
        df["molecule_id"] = df["molecule_id"].map(_norm_mol_id)
        if "canonical_res_num" in df.columns:
            df["canonical_res_num"] = pd.to_numeric(df["canonical_res_num"], errors="coerce").astype("Int64")

    ix["interaction_type"] = ix["interaction_type"].map(lambda t: INTERACTION_CANON.get(str(t), str(t)))

    # source labels
    src_map: dict[str, str] = {}
    for _, r in dyn[["molecule_id", "source_molecule_label"]].drop_duplicates().iterrows():
        src_map[r["molecule_id"]] = _norm_mol_id(r["source_molecule_label"])
    mol_ids = sorted(occ["molecule_id"].dropna().unique().tolist())
    id_map = build_id_map(mol_ids, src_map)

    # filter VAV1 key
    def _vav1_key(df: pd.DataFrame) -> pd.DataFrame:
        m = (df["protein_component"] == "VAV1") & (df["canonical_res_num"].isin(FEATURE_RESIDUES))
        return df.loc[m].copy()

    occ_k = _vav1_key(occ)
    ix_k = _vav1_key(ix)
    rmsf_k = _vav1_key(rmsf)
    dyn_k = _vav1_key(dyn)

    rows = []
    errors = []
    for mid in mol_ids:
        feat: dict[str, float] = {}
        observed_flags: dict[str, int] = {}

        # A occupancy
        sub = occ_k[occ_k["molecule_id"] == mid]
        occ_map = {
            int(r["canonical_res_num"]): float(r["any_interaction_occupancy"])
            for _, r in sub.iterrows()
            if pd.notna(r["any_interaction_occupancy"])
        }
        for r in FEATURE_RESIDUES:
            if r in occ_map:
                feat[f"occ_r{r}"] = occ_map[r]
                observed_flags[f"occ_r{r}"] = 1
            else:
                feat[f"occ_r{r}"] = 0.0
                observed_flags[f"occ_r{r}"] = 0
        # cover_occ 仅按实际有 occupancy 数据的 11 个关键残基计算，避免扩集导致 md_mask 失效
        occ_cover_base = [r for r in KEY_RESIDUES if r in FEATURE_RESIDUES]
        cover_occ = sum(observed_flags[f"occ_r{r}"] for r in occ_cover_base) / max(len(occ_cover_base), 1)
        feat["occ_w"] = float(sum(weights[r] * feat[f"occ_r{r}"] for r in FEATURE_RESIDUES))

        # C interaction types
        isub = ix_k[ix_k["molecule_id"] == mid]
        type_vals: dict[str, float] = {}
        for t in TYPE_ORDER:
            vals = isub.loc[isub["interaction_type"] == t, "occupancy"]
            if len(vals):
                type_vals[t] = float(np.nanmean(vals.to_numpy(dtype=float)))
                observed_flags[f"type_{t}"] = 1
            else:
                type_vals[t] = 0.0
                observed_flags[f"type_{t}"] = 0
            feat[f"type_{t}"] = type_vals[t]

        # D energy from dynamic window mmgbsa_total_mean (per residue across windows)
        dsub = dyn_k[dyn_k["molecule_id"] == mid]
        e_map: dict[int, float] = {}
        e_obs: dict[int, int] = {}
        for r in FEATURE_RESIDUES:
            vals = dsub.loc[dsub["canonical_res_num"] == r, "mmgbsa_total_mean"]
            vals = vals[vals.notna()]
            if len(vals):
                mean_e = float(vals.mean())
                # tanh 有界
                center, scale = cfg["energy_center"], cfg["energy_scale"]
                e_map[r] = float(np.tanh((mean_e - center) / max(scale, 1e-6)))
                e_obs[r] = 1
            else:
                e_map[r] = 0.0
                e_obs[r] = 0
            feat[f"energy_r{r}"] = e_map[r]
            observed_flags[f"energy_r{r}"] = e_obs[r]
        energy_cover = sum(e_obs.values()) / len(FEATURE_RESIDUES)
        feat["energy_cover"] = float(energy_cover)
        if energy_cover > 0:
            feat["energy_w"] = float(
                sum(weights[r] * e_map[r] for r in FEATURE_RESIDUES if e_obs[r]) / max(sum(weights[r] for r in FEATURE_RESIDUES if e_obs[r]), 1e-8)
            )
        else:
            feat["energy_w"] = 0.0

        # E RMSF
        rsub = rmsf_k[rmsf_k["molecule_id"] == mid]
        rmsf_map: dict[int, float] = {}
        for r in FEATURE_RESIDUES:
            vals = rsub.loc[rsub["canonical_res_num"] == r, "rmsf_A"]
            vals = vals[vals.notna()]
            if len(vals):
                rmsf_map[r] = float(vals.mean())
                observed_flags[f"rmsf_r{r}"] = 1
            else:
                rmsf_map[r] = 0.0
                observed_flags[f"rmsf_r{r}"] = 0
            feat[f"rmsf_r{r}"] = rmsf_map[r]
        if any(observed_flags[f"rmsf_r{r}"] for r in FEATURE_RESIDUES):
            feat["rmsf_w"] = float(
                sum(weights[r] * rmsf_map[r] for r in FEATURE_RESIDUES if observed_flags[f"rmsf_r{r}"])
                / max(sum(weights[r] for r in FEATURE_RESIDUES if observed_flags[f"rmsf_r{r}"]), 1e-8)
            )
        else:
            feat["rmsf_w"] = 0.0

        # F persistence early/late windows
        if len(dsub) and "window_id" in dsub.columns:
            wins = sorted(dsub["window_id"].dropna().unique().tolist())
            n_w = len(wins)
            if n_w >= 5:
                n_edge = max(1, int(round(0.2 * n_w)))
                early = set(wins[:n_edge])
                late = set(wins[-n_edge:])
                early_occ = dsub[dsub["window_id"].isin(early)]["any_interaction_occupancy"].dropna()
                late_occ = dsub[dsub["window_id"].isin(late)]["any_interaction_occupancy"].dropna()
                persist_early = float(early_occ.mean()) if len(early_occ) else 0.0
                persist_late = float(late_occ.mean()) if len(late_occ) else 0.0
            else:
                persist_early = float(dsub["any_interaction_occupancy"].dropna().mean() or 0.0)
                persist_late = persist_early
            # complete_rate: fraction of key×window with non-null occupancy
            # occupancy 仅 KEY_RESIDUES 有数据，expected 按其计算
            expected = len(KEY_RESIDUES) * max(n_w, 1)
            got = dsub[dsub["canonical_res_num"].isin(KEY_RESIDUES)]["any_interaction_occupancy"].notna().sum()
            complete_rate = float(got / max(expected, 1))
        else:
            persist_early = persist_late = 0.0
            complete_rate = 0.0
        feat["persist_early"] = persist_early
        feat["persist_late"] = persist_late
        feat["persist_delta"] = float(persist_late - persist_early)
        feat["complete_rate"] = complete_rate

        try:
            rewards = compute_rewards(feat, cfg=cfg, type_vals=type_vals)
            reward_ok = True
            reward_err = None
        except Exception as e:  # noqa: BLE001
            rewards = {k: float("nan") for k in (
                "reward_key_hit", "reward_persistence", "reward_interaction_type",
                "reward_energy", "penalty_flexibility", "penalty_missing", "reward_total",
            )}
            reward_ok = False
            reward_err = str(e)
            errors.append({"molecule_id": mid, "error": reward_err})

        md_mask = int(
            cover_occ >= cfg["md_mask_min_key_cover"]
            and complete_rate >= cfg["md_mask_min_complete_rate"]
            and reward_ok
            and not any(np.isnan(rewards[k]) for k in rewards)
        )

        vec = [float(feat[n]) for n in spec["names"]]
        row = {
            "molecule_id": mid,
            "source_molecule_label": src_map.get(mid, ""),
            "md_mask": md_mask,
            "key_occ_cover": cover_occ,
            "energy_cover": energy_cover,
            "complete_rate": complete_rate,
            "reward_ok": reward_ok,
            **{f"md_{i}": vec[i] for i in range(len(vec))},
            **{n: feat[n] for n in spec["names"]},
            **rewards,
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # scaler：仅 md_mask=1 分子（训练可见 MD 子集 = 全部 8，但协议上只 fit mask=1）
    fit = df[df["md_mask"] == 1]
    if len(fit) < 2:
        fit = df
    mat = fit[spec["names"]].to_numpy(dtype=float)
    mean = np.nanmean(mat, axis=0)
    std = np.nanstd(mat, axis=0)
    std = np.where((std < 1e-8) | np.isnan(std), 1.0, std)
    mean = np.where(np.isnan(mean), 0.0, mean)
    scaler = {"columns": spec["names"], "mean": mean.tolist(), "std": std.tolist(), "n_fit": int(len(fit))}

    # scaled vectors
    full = df[spec["names"]].to_numpy(dtype=float)
    z = (full - mean) / std
    z = np.where(np.isnan(z), 0.0, z)
    z = np.clip(z, -10, 10)
    for i, n in enumerate(spec["names"]):
        df[f"z_{n}"] = z[:, i]

    # write outputs
    (out_dir / "MD_FEATURE_SPEC.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    (out_dir / "md_id_map.json").write_text(json.dumps(id_map, indent=2), encoding="utf-8")
    (out_dir / "md_reward_config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    (out_dir / "md_scaler.json").write_text(json.dumps(scaler, indent=2), encoding="utf-8")
    df.to_parquet(out_dir / "md8_molecule_features.parquet", index=False)
    df.to_csv(out_dir / "md8_molecule_features.csv", index=False)

    qc = {
        "n_molecules": int(len(df)),
        "dim": spec["dim"],
        "n_md_mask_1": int((df["md_mask"] == 1).sum()),
        "key_residues": KEY_RESIDUES,
        "key_weights": weights,
        "reward_nan_any": bool(df[[c for c in df.columns if c.startswith("reward_")]].isna().any().any()),
        "id_aliases_0185087": id_map["canonical_to_aliases"].get("0185087"),
        "molecule_ids": mol_ids,
        "errors": errors,
        "gate_pass": bool(
            len(df) == 8
            and spec["dim"] == len(spec["names"])
            and (df["md_mask"] == 1).sum() >= 6
            and not df[[c for c in df.columns if c.startswith("reward_")]].isna().any().any()
            and all(r in weights for r in KEY_RESIDUES)
        ),
    }
    (out_dir / "md_qc_report.json").write_text(json.dumps(qc, indent=2, default=str), encoding="utf-8")
    return qc


class MDFeatureStore:
    """训练时按 molecule_id / 别名取 md_vec（已标准化）与 reward_total。"""

    def __init__(self, out_dir: Path = OUT_DIR):
        out_dir = Path(out_dir)
        self.spec = json.loads((out_dir / "MD_FEATURE_SPEC.json").read_text(encoding="utf-8"))
        self.id_map = json.loads((out_dir / "md_id_map.json").read_text(encoding="utf-8"))
        self.scaler = json.loads((out_dir / "md_scaler.json").read_text(encoding="utf-8"))
        self.df = pd.read_csv(out_dir / "md8_molecule_features.csv")
        self.by_id = {str(r["molecule_id"]): r for _, r in self.df.iterrows()}
        self.dim = int(self.spec["dim"])

    def resolve_id(self, molecule_id: str) -> Optional[str]:
        mid = _norm_mol_id(molecule_id)
        rev = self.id_map.get("alias_to_canonical", {})
        if mid in self.by_id:
            return mid
        if mid in rev and rev[mid] in self.by_id:
            return rev[mid]
        # also try raw
        if molecule_id in self.by_id:
            return str(molecule_id)
        return None

    def get(self, molecule_id: str) -> dict[str, Any]:
        canon = self.resolve_id(molecule_id)
        if canon is None:
            return {
                "molecule_id": molecule_id,
                "md_vec": [0.0] * self.dim,
                "md_mask": 0,
                "reward_total": 0.0,
                "observed": False,
            }
        r = self.by_id[canon]
        names = self.spec["names"]
        vec = [float(r[f"z_{n}"]) for n in names]
        return {
            "molecule_id": canon,
            "md_vec": vec,
            "md_mask": int(r["md_mask"]),
            "reward_total": float(r["reward_total"]),
            "observed": True,
        }
