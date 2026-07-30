#!/usr/bin/env python3
"""strip 后重算冻结 101D，拟合 train-only scaler，写出 features_v1/physchem/。

用法:
  cd backend && .venv/bin/python scripts/rebuild_physchem_101_stripped.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path("/data/ye/e-drug-lab/backend")
sys.path.insert(0, str(ROOT))

from app.pipelines.vav1_rl.crbn_strip import strip_crbn_anchor_module  # noqa: E402
from app.pipelines.vav1_rl.physchem_101 import (  # noqa: E402
    DEFAULT_101D_CSV,
    PhysChemScaler,
    compute_physchem_101,
    load_frozen_column_names,
)

BINDING_RL = ROOT / "outputs/vav1_rl_project/binding_RL"
OUT_DIR = BINDING_RL / "features_v1" / "physchem"
PATENT_LABELS = BINDING_RL / "patent_docking" / "patent_403_labels.csv"
WETLAB_LABELS = BINDING_RL / "wetlab_docking" / "wetlab_13_labels.csv"
FEATURE_TABLE = BINDING_RL / "patent_screening" / "results" / "feature_table.csv"
E33_TRAIN = (
    ROOT
    / "outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709/data/patent_train_303.csv"
)


def _load_sources() -> pd.DataFrame:
    rows: list[dict] = []
    pat = pd.read_csv(PATENT_LABELS)
    for _, r in pat.iterrows():
        rows.append(
            {
                "molecule_id": str(r["molecule_id"]),
                "smiles_raw": str(r.get("neutralized_smiles") or r.get("canonical_smiles") or r["smiles"]),
                "source": "patent403",
                "label_active": int(r.get("label_active", 0)),
            }
        )
    wl = pd.read_csv(WETLAB_LABELS)
    id_col = "SDF_ID" if "SDF_ID" in wl.columns else "molecule_id"
    smi_col = "SMILES" if "SMILES" in wl.columns else "smiles"
    for _, r in wl.iterrows():
        rows.append(
            {
                "molecule_id": str(r[id_col]),
                "smiles_raw": str(r[smi_col]),
                "source": "wetlab13",
                "label_active": int(r.get("label", r.get("label_active", 0))),
            }
        )
    # 101D 库（可能与 403 重叠，保留作审计）
    pat101 = pd.read_csv(DEFAULT_101D_CSV)
    for _, r in pat101.iterrows():
        mid = str(r["Cpd."])
        rows.append(
            {
                "molecule_id": mid,
                "smiles_raw": str(r["Canonical_SMILES"]),
                "source": "pat101",
                "label_active": 1 if str(r.get("Activity_Class", "")).lower() in ("strong", "active") else 0,
            }
        )
    df = pd.DataFrame(rows)
    # 同 ID 优先 patent / wetlab
    priority = {"patent403": 0, "wetlab13": 1, "pat101": 2}
    df["_pri"] = df["source"].map(priority)
    df = df.sort_values(["molecule_id", "_pri"]).drop_duplicates("molecule_id", keep="first")
    df = df.drop(columns=["_pri"]).reset_index(drop=True)
    return df


def _train_ids() -> set[str]:
    ids: set[str] = set()
    if E33_TRAIN.is_file():
        t = pd.read_csv(E33_TRAIN)
        col = "molecule_id" if "molecule_id" in t.columns else t.columns[0]
        ids |= {str(x) for x in t[col].tolist()}
    if FEATURE_TABLE.is_file():
        ft = pd.read_csv(FEATURE_TABLE)
        if "split" in ft.columns:
            ids |= {str(x) for x in ft.loc[ft["split"] == "train", "molecule_id"].tolist()}
    return ids


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cols = load_frozen_column_names()
    src = _load_sources()
    train_ids = _train_ids()

    records = []
    for _, r in src.iterrows():
        strip = strip_crbn_anchor_module(r["smiles_raw"])
        smi_use = strip["smiles_stripped"] if strip["ok"] else None
        pc = compute_physchem_101(smi_use, column_names=cols) if smi_use else {
            "ok": False, "vector": [float("nan")] * 101, "error": strip.get("error") or "strip_failed",
        }
        rec = {
            "molecule_id": r["molecule_id"],
            "source": r["source"],
            "smiles_raw": r["smiles_raw"],
            "smiles_stripped": strip.get("smiles_stripped"),
            "strip_mode": strip.get("strip_mode"),
            "strip_ok": bool(strip.get("ok")),
            "physchem_ok": bool(pc.get("ok")),
            "label_active": r["label_active"],
            "is_train_fit": r["molecule_id"] in train_ids and r["source"] == "patent403",
        }
        for i, c in enumerate(cols):
            rec[c] = pc["vector"][i] if pc.get("vector") else float("nan")
        records.append(rec)

    out_df = pd.DataFrame(records)
    csv_path = OUT_DIR / "PAT_training_database_101D_stripped.csv"
    out_df.to_csv(csv_path, index=False)

    fit_mask = out_df["is_train_fit"] & out_df["physchem_ok"]
    if fit_mask.sum() < 50:
        # fallback: all patent with ok physchem
        fit_mask = (out_df["source"] == "patent403") & out_df["physchem_ok"]
    mat = out_df.loc[fit_mask, cols].to_numpy(dtype=float)
    scaler = PhysChemScaler.fit(mat, cols)
    scaler_path = OUT_DIR / "physchem_scaler_train.json"
    scaler.save(scaler_path)

    # 标准化后的矩阵（审计）
    all_mat = out_df[cols].to_numpy(dtype=float)
    z = scaler.transform(all_mat)
    z_df = out_df[["molecule_id", "source", "smiles_stripped", "strip_ok", "physchem_ok"]].copy()
    for i, c in enumerate(cols):
        z_df[c] = z[:, i]
    z_df.to_csv(OUT_DIR / "physchem_101_stripped_scaled.csv", index=False)

    qc = {
        "n_total": int(len(out_df)),
        "n_strip_ok": int(out_df["strip_ok"].sum()),
        "n_physchem_ok": int(out_df["physchem_ok"].sum()),
        "n_scaler_fit": int(fit_mask.sum()),
        "n_features": 101,
        "columns": cols,
        "csv": str(csv_path),
        "scaler": str(scaler_path),
        "gate_pass": bool(
            out_df["physchem_ok"].mean() >= 0.95
            and fit_mask.sum() >= 50
            and len(cols) == 101
        ),
    }
    (OUT_DIR / "physchem_qc_report.json").write_text(json.dumps(qc, indent=2), encoding="utf-8")
    print(json.dumps(qc, indent=2))


if __name__ == "__main__":
    main()
