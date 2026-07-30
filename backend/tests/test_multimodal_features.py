"""physchem_101 / md_features / glide_features 单测。"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

BINDING = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/binding_RL")
PC_DIR = BINDING / "features_v1" / "physchem"
MD_DIR = BINDING / "features_v1" / "md"


def test_physchem_compute_and_scaler():
    from app.pipelines.vav1_rl.physchem_101 import (
        PhysChemScaler,
        compute_physchem_101,
        load_frozen_column_names,
    )

    cols = load_frozen_column_names()
    assert len(cols) == 101
    # stripped warhead-like fragment
    r = compute_physchem_101("Cc1ccc(N)cc1", column_names=cols)
    assert r["ok"]
    assert len(r["vector"]) == 101
    assert all(np.isfinite(r["vector"]))


@pytest.mark.skipif(not (PC_DIR / "physchem_scaler_train.json").is_file(), reason="physchem not built")
def test_physchem_artifacts_gate():
    qc = json.loads((PC_DIR / "physchem_qc_report.json").read_text())
    assert qc["gate_pass"]
    assert qc["n_features"] == 101
    scaler = json.loads((PC_DIR / "physchem_scaler_train.json").read_text())
    assert len(scaler["mean"]) == 101


@pytest.mark.skipif(not (MD_DIR / "md_qc_report.json").is_file(), reason="md not built")
def test_md_artifacts_gate():
    from app.pipelines.vav1_rl.md_features import MDFeatureStore

    qc = json.loads((MD_DIR / "md_qc_report.json").read_text())
    assert qc["gate_pass"]
    assert qc["n_molecules"] == 8
    assert qc["dim"] == 47
    store = MDFeatureStore(MD_DIR)
    # alias
    a = store.get("0185078")
    b = store.get("0185087")
    assert a["observed"] and b["observed"]
    assert a["md_mask"] == 1
    assert len(a["md_vec"]) == 47
    # unknown → mask 0
    u = store.get("NOT_A_MOL")
    assert u["md_mask"] == 0


def test_glide_store_mask():
    from app.pipelines.vav1_rl.glide_features import GLIDE_DIM, build_default_glide_store

    store = build_default_glide_store()
    g = store.get("PAT-101")
    assert len(g["glide_vec"]) == GLIDE_DIM
    # decoy-like unknown
    d = store.get("DECOY_XYZ")
    assert d["glide_mask"] == 0
