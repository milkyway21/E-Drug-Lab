"""专利 Glide + VAV1 IFP 特征向量（不 strip）。

输出定长 glide_vec + glide_mask。decoy / 无对接 → mask=0。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

BINDING_RL = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/binding_RL")
FEATURE_TABLE = BINDING_RL / "patent_screening" / "results" / "feature_table.csv"
PATENT_GLIDE = BINDING_RL / "patent_docking" / "analysis" / "glide_sp_docking_results.csv"
WETLAB_GLIDE = BINDING_RL / "wetlab_docking" / "analysis" / "glide_sp_docking_results.csv"
# ALLIN 扩展表（R2 实体 + R3 库等）；存在时与专利表合并，同 ID 以扩展表为准
ALLIN_GLIDE_TABLE = BINDING_RL / "features_v1" / "glide" / "allin_glide_feature_table.csv"

# 冻结顺序：能量标量 + IFP（feature_table 11 维）
GLIDE_SCORE_COLS = [
    "docking_score",
    "glide_emodel",
    "glide_evdw",
    "glide_ecoul",
    "n_vav1_residues",
]
IFP_COLS = [
    "ifp_C.ARG.796",
    "ifp_C.ASN.835",
    "ifp_C.ASP.797",
    "ifp_C.GLN.817",
    "ifp_C.GLN.818",
    "ifp_C.GLU.800",
    "ifp_C.PHE.793",
    "ifp_C.PRO.833",
    "ifp_C.SER.799",
    "ifp_C.TRP.820",
    "ifp_C.TYR.836",
]
GLIDE_DIM = len(GLIDE_SCORE_COLS) + len(IFP_COLS)  # 16


def _normalize_id(x: Any) -> str:
    s = str(x).strip()
    if s.endswith(".0") and s.replace(".", "", 1).isdigit() is False:
        pass
    # 0185087 / 185087
    if s.replace(".", "", 1).isdigit():
        try:
            s = f"{int(float(s)):07d}" if float(s) < 1e7 else str(int(float(s)))
        except Exception:
            pass
    return s


class GlideFeatureStore:
    def __init__(self, table: pd.DataFrame, mean: np.ndarray, std: np.ndarray):
        self.table = table
        self.mean = mean
        self.std = np.where(std < 1e-8, 1.0, std)
        self.by_id = {str(r["molecule_id"]): r for _, r in table.iterrows()}

    @classmethod
    def build(cls, train_ids: Optional[set[str]] = None) -> "GlideFeatureStore":
        ft = pd.read_csv(FEATURE_TABLE)
        # ensure IFP cols
        for c in IFP_COLS + GLIDE_SCORE_COLS:
            if c not in ft.columns:
                ft[c] = np.nan
        ft["molecule_id"] = ft["molecule_id"].map(_normalize_id)

        # merge wetlab glide scores if missing from feature_table
        if WETLAB_GLIDE.is_file():
            wg = pd.read_csv(WETLAB_GLIDE)
            id_col = "mol_id" if "mol_id" in wg.columns else "molecule_id"
            for _, r in wg.iterrows():
                mid = _normalize_id(r[id_col])
                if mid in set(ft["molecule_id"]):
                    continue
                row = {c: np.nan for c in ft.columns}
                row["molecule_id"] = mid
                for c in GLIDE_SCORE_COLS:
                    if c in wg.columns:
                        row[c] = r[c]
                for c in IFP_COLS:
                    row[c] = 0.0
                ft = pd.concat([ft, pd.DataFrame([row])], ignore_index=True)

        # ALLIN 扩展：R2/R3 等；同 ID 覆盖（keep=last）
        if ALLIN_GLIDE_TABLE.is_file():
            ext = pd.read_csv(ALLIN_GLIDE_TABLE)
            ext["molecule_id"] = ext["molecule_id"].map(_normalize_id)
            for c in IFP_COLS + GLIDE_SCORE_COLS:
                if c not in ext.columns:
                    ext[c] = np.nan if c in GLIDE_SCORE_COLS else 0.0
            for c in ft.columns:
                if c not in ext.columns:
                    ext[c] = np.nan
            ft = pd.concat([ft, ext[list(ft.columns)]], ignore_index=True)
            ft = ft.drop_duplicates(subset=["molecule_id"], keep="last")

        cols = GLIDE_SCORE_COLS + IFP_COLS
        if train_ids:
            fit = ft[ft["molecule_id"].isin(train_ids)]
        else:
            fit = ft[ft.get("split", "train") == "train"] if "split" in ft.columns else ft
        if len(fit) < 10:
            fit = ft
        mat = fit[cols].to_numpy(dtype=float)
        mean = np.nanmean(mat, axis=0)
        std = np.nanstd(mat, axis=0)
        mean = np.where(np.isnan(mean), 0.0, mean)
        return cls(ft, mean, std)

    def get(self, molecule_id: str) -> dict[str, Any]:
        mid = _normalize_id(molecule_id)
        row = self.by_id.get(mid)
        dim = GLIDE_DIM
        if row is None:
            return {
                "molecule_id": mid,
                "glide_vec": [0.0] * dim,
                "glide_mask": 0,
                "observed": False,
            }
        raw = []
        for c in GLIDE_SCORE_COLS + IFP_COLS:
            v = row.get(c, np.nan)
            try:
                fv = float(v)
            except Exception:
                fv = float("nan")
            raw.append(fv)
        arr = np.asarray(raw, dtype=np.float64)
        # 有 docking_score 才算观测
        observed = not np.isnan(arr[0])
        z = (arr - self.mean) / self.std
        z = np.where(np.isnan(z), 0.0, z)
        z = np.clip(z, -10, 10)
        return {
            "molecule_id": mid,
            "glide_vec": z.astype(float).tolist(),
            "glide_mask": 1 if observed else 0,
            "observed": observed,
        }

    def save_cache(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "dim": GLIDE_DIM,
            "score_cols": GLIDE_SCORE_COLS,
            "ifp_cols": IFP_COLS,
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
        }
        path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        # per-molecule cache
        rows = []
        for mid in self.by_id:
            g = self.get(mid)
            rows.append(
                {
                    "molecule_id": mid,
                    "glide_mask": g["glide_mask"],
                    **{f"g{i}": g["glide_vec"][i] for i in range(GLIDE_DIM)},
                }
            )
        pd.DataFrame(rows).to_csv(path.with_suffix(".csv"), index=False)


def build_default_glide_store() -> GlideFeatureStore:
    train_ids = None
    if FEATURE_TABLE.is_file():
        ft = pd.read_csv(FEATURE_TABLE)
        if "split" in ft.columns:
            train_ids = set(ft.loc[ft["split"] == "train", "molecule_id"].map(_normalize_id))
    return GlideFeatureStore.build(train_ids=train_ids)
