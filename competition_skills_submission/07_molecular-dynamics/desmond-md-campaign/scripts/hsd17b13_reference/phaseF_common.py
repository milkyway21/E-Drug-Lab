#!/usr/bin/env python3
"""Shared constants and validation helpers for the Phase F 2+200 ns campaign."""
from __future__ import annotations

import hashlib
import json
import os
import tarfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BATCH = "phaseF_medoid_pose_2_200_top16_20260728"
SYSTEM_ROOT = ROOT / "03_systems" / BATCH
TRAJECTORY_ROOT = ROOT / "04_trajectories" / BATCH
ANALYSIS_ROOT = ROOT / "05_analysis" / BATCH
LOG_ROOT = ROOT / "logs" / BATCH
SOURCE_TRAJECTORY_ROOT = ROOT / "04_trajectories/phaseE_corrected_pose_2_50_all40_20260727"
SOURCE_ANALYSIS_ROOT = ROOT / "05_analysis/phaseE_corrected_pose_2_50_all40_20260727"
MD_PROTOCOL = ROOT / "scripts/protocols/prod_2ns_eq_200ns.msj"
HOSTS_FILE = ROOT / "meta/phaseF_gpu_hosts"
MANIFEST = ANALYSIS_ROOT / "phaseF_selection_manifest.csv"
IDS_FILE = ANALYSIS_ROOT / "phaseF_selected_ids.txt"
SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")

PRIMARY = [
    ("T66645", 44.4, 0.863), ("T12164", 41.0, 1.000),
    ("T13553", 44.0, 0.686), ("T27695", 49.6, 1.000),
    ("T34698", 47.4, 1.000), ("T3S1089", 48.2, 1.000),
    ("T21969", 44.8, 1.000), ("T4342", 49.8, 0.980),
    ("T16705", 44.4, 1.000), ("T21193", 47.8, 1.000),
    ("T2508", 44.8, 1.000), ("T69150", 43.6, 0.647),
    ("T39220", 45.0, 0.804), ("T10425", 49.6, 1.000),
    ("T60390", 45.4, 1.000), ("T1075", 44.0, 0.980),
]
BACKUPS = [
    ("T16866", 48.0, 0.745), ("T3232", 47.6, 1.000),
    ("T5S0045", 49.2, 0.706), ("T6307", 41.4, 0.941),
    ("T28655", 42.6, 0.863), ("T7151", 47.6, 1.000),
    ("T4965", 43.6, 0.569),
]


def minimum_image(delta: np.ndarray, box: np.ndarray) -> np.ndarray:
    shape = np.asarray(delta).shape
    flat = np.asarray(delta, float).reshape(-1, 3)
    fractional = flat @ np.linalg.inv(np.asarray(box, float))
    fractional -= np.round(fractional)
    return (fractional @ box).reshape(shape)


def unwrap_group(coordinates: np.ndarray, box: np.ndarray) -> np.ndarray:
    coordinates = np.asarray(coordinates, float)
    if len(coordinates) < 2:
        return coordinates.copy()
    return coordinates[0] + minimum_image(coordinates - coordinates[0], box)


def kabsch(mobile: np.ndarray, reference: np.ndarray):
    mc, rc = mobile.mean(axis=0), reference.mean(axis=0)
    u, _, vt = np.linalg.svd((mobile - mc).T @ (reference - rc))
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    return rotation, mc, rc


def align(coordinates: np.ndarray, fit) -> np.ndarray:
    rotation, mobile_center, reference_center = fit
    return (coordinates - mobile_center) @ rotation + reference_center


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_attempt(mid: str) -> Path:
    for attempt in sorted((SOURCE_TRAJECTORY_ROOT / mid).glob("attempt_*"), reverse=True):
        cms = attempt / f"{mid}_52ns-out.cms"
        logs = list(attempt.glob("HSD17B13_E52C_*_multisim.log"))
        if cms.exists() and cms.stat().st_size > 1_000_000 and logs:
            if "Multisim completed" in logs[0].read_text(errors="ignore"):
                return attempt
    raise FileNotFoundError(f"{mid}: no completed Phase E attempt")


def trajectory_dir(attempt: Path, extract: bool = True) -> Path:
    direct = [p for p in attempt.glob("*_6_trj") if (p / "clickme.dtr").exists()]
    nested = [p for p in attempt.glob("*_6/*_trj") if (p / "clickme.dtr").exists()]
    if direct or nested:
        return (direct + nested)[0]
    archives = list(attempt.glob("*_6-out.tgz"))
    if not archives or not extract:
        raise FileNotFoundError(f"No production DTR in {attempt}")
    with tarfile.open(archives[0], "r:gz") as handle:
        handle.extractall(attempt)
    nested = [p for p in attempt.glob("*_6/*_trj") if (p / "clickme.dtr").exists()]
    if not nested:
        raise RuntimeError(f"Production archive did not yield a valid DTR: {attempt}")
    return nested[0]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")
