"""冻结 101 维 RDKit 理化特征：strip 后重算 + train-only scaler。

列名以 PAT_training_database_101D.csv 的 RDKit_* 为真源冻结。
纯 IO：SMILES → 向量 / 表 → scaler，不含训练流程。
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors

DEFAULT_101D_CSV = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/PAT_training_database_101D.csv"
)

_FROZEN_NAMES: Optional[list[str]] = None


def load_frozen_column_names(csv_path: Path | str = DEFAULT_101D_CSV) -> list[str]:
    """返回冻结的 RDKit_* 列名（含前缀），顺序固定。"""
    global _FROZEN_NAMES
    if _FROZEN_NAMES is not None and Path(csv_path) == DEFAULT_101D_CSV:
        return list(_FROZEN_NAMES)
    import csv

    with Path(csv_path).open(encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    names = [c for c in header if c.startswith("RDKit_")]
    if len(names) != 101:
        raise ValueError(f"期望 101 列 RDKit_*，得到 {len(names)} @ {csv_path}")
    if Path(csv_path) == DEFAULT_101D_CSV:
        _FROZEN_NAMES = list(names)
    return names


def descriptor_keys(csv_path: Path | str = DEFAULT_101D_CSV) -> list[str]:
    """不含 RDKit_ 前缀的描述符名（CalcMolDescriptors 键）。"""
    return [c[len("RDKit_") :] for c in load_frozen_column_names(csv_path)]


def compute_physchem_101(
    smiles: str,
    *,
    column_names: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """对单分子计算冻结 101 维；失败时 ok=False，向量为 NaN。"""
    cols = list(column_names) if column_names is not None else load_frozen_column_names()
    keys = [c[len("RDKit_") :] for c in cols]
    out: dict[str, Any] = {
        "smiles": smiles,
        "ok": False,
        "vector": [float("nan")] * len(keys),
        "error": None,
    }
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        out["error"] = "invalid_smiles"
        return out
    try:
        desc = Descriptors.CalcMolDescriptors(mol)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"calc_failed:{e}"
        return out
    vec: list[float] = []
    for k in keys:
        v = desc.get(k)
        if v is None:
            vec.append(float("nan"))
        else:
            try:
                fv = float(v)
                if math.isnan(fv) or math.isinf(fv):
                    vec.append(float("nan"))
                else:
                    vec.append(fv)
            except (TypeError, ValueError):
                vec.append(float("nan"))
    out["vector"] = vec
    out["ok"] = True
    return out


def vectors_to_matrix(vectors: Sequence[Sequence[float]]) -> np.ndarray:
    return np.asarray(vectors, dtype=np.float64)


class PhysChemScaler:
    """逐列 mean/std；fit 时忽略 NaN；transform 时 NaN→0 并 clip。"""

    def __init__(self, mean: np.ndarray, std: np.ndarray, columns: list[str]):
        self.mean = np.asarray(mean, dtype=np.float64)
        self.std = np.asarray(std, dtype=np.float64)
        self.columns = list(columns)

    @classmethod
    def fit(cls, matrix: np.ndarray, columns: Sequence[str]) -> "PhysChemScaler":
        x = np.asarray(matrix, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != len(columns):
            raise ValueError(f"matrix shape {x.shape} vs n_cols {len(columns)}")
        mean = np.nanmean(x, axis=0)
        std = np.nanstd(x, axis=0)
        std = np.where(std < 1e-8, 1.0, std)
        mean = np.where(np.isnan(mean), 0.0, mean)
        return cls(mean=mean, std=std, columns=list(columns))

    def transform(self, matrix: np.ndarray, *, fill_nan: float = 0.0, clip: float = 10.0) -> np.ndarray:
        x = np.asarray(matrix, dtype=np.float64)
        z = (x - self.mean) / self.std
        z = np.where(np.isnan(z), fill_nan, z)
        if clip is not None:
            z = np.clip(z, -clip, clip)
        return z.astype(np.float32)

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "n_features": len(self.columns),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PhysChemScaler":
        return cls(
            mean=np.asarray(d["mean"], dtype=np.float64),
            std=np.asarray(d["std"], dtype=np.float64),
            columns=list(d["columns"]),
        )

    def save(self, path: Path | str) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> "PhysChemScaler":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
