#!/usr/bin/env python3
"""Summarize completed HSD17B13 Phase-A Desmond trajectories (up to 27).

The script combines:
  * Simulation Event Analysis RMSD/RMSF and interaction exports
  * Glide XP, Prime MM-GBSA, HepG2-risk and safety metadata
  * RDKit 2D descriptors for qualitative cellular-exposure flags

Scores are transparent triage heuristics, not binding free energies or IC50
predictions. The first 10% of the 50 ns production trajectory is discarded.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors
except ImportError:  # pragma: no cover - descriptors are optional
    Chem = None
    Descriptors = None


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = ROOT / "05_analysis"
DEFAULT_OUT = ANALYSIS_ROOT / "md27_summary"
MANIFEST = ROOT / "meta/ligands_manifest.csv"
IDS_FILE = ROOT / "meta/ids_27.txt"
XP_TABLE = (
    ROOT.parent
    / "dock_funnel_xp_mmgbsa/mmgbsa/xp_top50.csv"
)
CURATED_TABLE = (
    ROOT.parent
    / "dock_funnel_xp_mmgbsa/desmond_md_prep_curated20/meta/"
    "selection_full.csv"
)
TOP250_TABLE = (
    ROOT.parent / "dock_funnel_xp_mmgbsa/select/top250_selection.csv"
)
XP_NEXT_TABLE = (
    ROOT.parent / "dock_funnel_xp_mmgbsa/mmgbsa_next80/xp_rank51_130.csv"
)


def _default_ids() -> list[str]:
    if IDS_FILE.exists():
        return [
            line.strip()
            for line in IDS_FILE.read_text().splitlines()
            if line.strip()
        ]
    return []


DEFAULT_IDS = _default_ids()

CONTACT_TYPES = [
    "HBond",
    "Hydrophobic",
    "Pi-Pi",
    "Pi-Cation",
    "Ionic",
    "Metal",
    "WaterBridge",
]
DIRECT_TYPES = set(CONTACT_TYPES) - {"WaterBridge"}
FRAME_INTERVAL_NS = 0.2
BURN_FRACTION = 0.10


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _linear_good(value: float, good: float, bad: float) -> float:
    """Return 1 at/below good and 0 at/above bad."""
    if math.isnan(value):
        return 0.0
    if value <= good:
        return 1.0
    if value >= bad:
        return 0.0
    return (bad - value) / (bad - good)


def _read_rmsd(path: Path) -> pd.DataFrame:
    columns = [
        "frame",
        "protein_ca",
        "protein_backbone",
        "protein_sidechain",
        "protein_all_heavy",
        "ligand_wrt_protein",
        "ligand_wrt_ligand",
    ]
    table = pd.read_csv(
        path,
        sep=r"\s+",
        comment="#",
        header=None,
        names=columns,
    )
    for column in columns:
        table[column] = pd.to_numeric(table[column], errors="coerce")
    return table.dropna(subset=["frame"]).astype({"frame": int})


def _read_ligand_properties(path: Path) -> pd.DataFrame:
    columns = [
        "frame",
        "rmsd",
        "rgyr",
        "intrahb",
        "molsa",
        "sasa",
        "psa",
    ]
    table = pd.read_csv(
        path,
        sep=r"\s+",
        comment="#",
        header=None,
        names=columns,
    )
    for column in columns:
        table[column] = pd.to_numeric(table[column], errors="coerce")
    return table.dropna(subset=["frame"]).astype({"frame": int})


def _read_ligand_rmsf(path: Path) -> pd.DataFrame:
    rows = []
    for line in path.read_text(errors="ignore").splitlines():
        tokens = line.split()
        if not tokens or not tokens[0].isdigit() or len(tokens) < 3:
            continue
        rows.append(
            {
                "atom": int(tokens[0]),
                "wrt_protein": float(tokens[-2]),
                "wrt_ligand": float(tokens[-1]),
            }
        )
    return pd.DataFrame(rows)


def _read_protein_rmsf(path: Path) -> pd.DataFrame:
    rows = []
    for line in path.read_text(errors="ignore").splitlines():
        tokens = line.split()
        if not tokens or not tokens[0].isdigit() or len(tokens) < 9:
            continue
        residue_label = tokens[2]
        residue_name, _, residue_num = residue_label.rpartition("_")
        rows.append(
            {
                "index": int(tokens[0]),
                "chain": tokens[1],
                "resname": residue_name,
                "resnum": int(residue_num) if residue_num.isdigit() else -1,
                "ligand_contact": tokens[3] == "Yes",
                "ca": float(tokens[4]),
                "backbone": float(tokens[5]),
                "sidechain": float(tokens[6]),
                "all_heavy": float(tokens[7]),
                "bfactor": float(tokens[8]),
            }
        )
    return pd.DataFrame(rows)


def _read_contact_rows(path: Path, burn_frame: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(errors="ignore").splitlines():
        tokens = line.split()
        if len(tokens) < 4 or not tokens[0].isdigit():
            continue
        frame = int(tokens[0])
        if frame < burn_frame:
            continue
        if tokens[1] == "prot-side" and len(tokens) >= 3:
            site_parts = tokens[2].split(":")
            if len(site_parts) < 2:
                continue
            chain = site_parts[0]
            residue_name, _, residue_num = site_parts[1].rpartition("_")
            if not residue_num.isdigit():
                continue
            rows.append(
                {
                    "frame": frame,
                    "resnum": int(residue_num),
                    "chain": chain,
                    "resname": residue_name,
                }
            )
            continue
        if not tokens[1].isdigit():
            continue
        rows.append(
            {
                "frame": frame,
                "resnum": int(tokens[1]),
                "chain": tokens[2],
                "resname": tokens[3],
            }
        )
    return rows


def _slope(time_ns: pd.Series, values: pd.Series) -> float:
    if len(values) < 2:
        return math.nan
    return float(np.polyfit(time_ns, values, 1)[0])


def _first_sustained_crossing(
    table: pd.DataFrame,
    column: str,
    threshold: float,
    window: int = 5,
) -> float:
    rolling = table[column].rolling(window=window, min_periods=window).mean()
    crossed = table.loc[rolling >= threshold, "frame"]
    if crossed.empty:
        return math.nan
    return float(crossed.iloc[0] * FRAME_INTERVAL_NS)


def _contact_metrics(
    data_dir: Path,
    n_frames: int,
    burn_frame: int,
    late_start: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    denominator = n_frames - burn_frame
    late_denominator = n_frames - late_start
    all_frames: set[int] = set()
    direct_frames: set[int] = set()
    late_direct_frames: set[int] = set()
    type_frames: dict[str, set[int]] = {}
    contact_sets: dict[tuple[str, str, int, str], set[int]] = defaultdict(set)
    residue_sets: dict[tuple[str, int, str], set[int]] = defaultdict(set)

    for contact_type in CONTACT_TYPES:
        rows = _read_contact_rows(
            data_dir / f"PL-Contacts_{contact_type}.dat",
            burn_frame,
        )
        frames = {row["frame"] for row in rows}
        type_frames[contact_type] = frames
        all_frames.update(frames)
        if contact_type in DIRECT_TYPES:
            direct_frames.update(frames)
            late_direct_frames.update(
                frame for frame in frames if frame >= late_start
            )
        for row in rows:
            key = (
                contact_type,
                row["chain"],
                row["resnum"],
                row["resname"],
            )
            contact_sets[key].add(row["frame"])
            residue_key = (row["chain"], row["resnum"], row["resname"])
            residue_sets[residue_key].add(row["frame"])

    long_rows = []
    for key, frames in contact_sets.items():
        contact_type, chain, resnum, resname = key
        long_rows.append(
            {
                "contact_type": contact_type,
                "chain": chain,
                "resnum": resnum,
                "resname": resname,
                "occupancy": len(frames) / denominator,
                "n_frames": len(frames),
            }
        )
    long_rows.sort(key=lambda row: row["occupancy"], reverse=True)

    direct_rows = [
        row for row in long_rows if row["contact_type"] in DIRECT_TYPES
    ]
    strongest_direct = direct_rows[0] if direct_rows else None
    strongest_any = long_rows[0] if long_rows else None

    metrics: dict[str, Any] = {
        "any_contact_coverage": len(all_frames) / denominator,
        "direct_contact_coverage": len(direct_frames) / denominator,
        "late_direct_contact_coverage": (
            len(late_direct_frames) / late_denominator
        ),
        "hbond_frame_coverage": (
            len(type_frames.get("HBond", set())) / denominator
        ),
        "hydrophobic_frame_coverage": (
            len(type_frames.get("Hydrophobic", set())) / denominator
        ),
        "waterbridge_frame_coverage": (
            len(type_frames.get("WaterBridge", set())) / denominator
        ),
        "persistent_residues_30pct": sum(
            len(frames) / denominator >= 0.30 for frames in residue_sets.values()
        ),
        "strongest_direct_occupancy": (
            strongest_direct["occupancy"] if strongest_direct else 0.0
        ),
        "strongest_direct_contact": (
            (
                f"{strongest_direct['contact_type']}:"
                f"{strongest_direct['chain']}-"
                f"{strongest_direct['resname']}{strongest_direct['resnum']}"
            )
            if strongest_direct
            else ""
        ),
        "strongest_any_occupancy": (
            strongest_any["occupancy"] if strongest_any else 0.0
        ),
        "strongest_any_contact": (
            (
                f"{strongest_any['contact_type']}:"
                f"{strongest_any['chain']}-"
                f"{strongest_any['resname']}{strongest_any['resnum']}"
            )
            if strongest_any
            else ""
        ),
    }
    return metrics, long_rows


def _descriptor_metrics(smiles: str, formal_charge: int) -> dict[str, Any]:
    result = {
        "mw": math.nan,
        "clogp": math.nan,
        "tpsa": math.nan,
        "hbd": math.nan,
        "hba": math.nan,
        "rotatable_bonds": math.nan,
        "ro5_violations": math.nan,
        "cell_exposure_risk": "未知",
    }
    if Chem is None or Descriptors is None:
        return result
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return result

    mw = Descriptors.MolWt(molecule)
    clogp = Descriptors.MolLogP(molecule)
    tpsa = Descriptors.TPSA(molecule)
    hbd = Descriptors.NumHDonors(molecule)
    hba = Descriptors.NumHAcceptors(molecule)
    rotatable = Descriptors.NumRotatableBonds(molecule)
    violations = sum(
        [
            mw > 500,
            clogp > 5,
            hbd > 5,
            hba > 10,
        ]
    )

    if (
        clogp < 0
        or tpsa > 130
        or violations > 1
        or (formal_charge != 0 and tpsa > 100)
    ):
        exposure = "高"
    elif (
        tpsa > 100
        or clogp > 4.5
        or formal_charge != 0
        or mw > 450
    ):
        exposure = "中"
    else:
        exposure = "低"

    result.update(
        {
            "mw": mw,
            "clogp": clogp,
            "tpsa": tpsa,
            "hbd": hbd,
            "hba": hba,
            "rotatable_bonds": rotatable,
            "ro5_violations": violations,
            "cell_exposure_risk": exposure,
        }
    )
    return result


def _upstream_metadata() -> dict[str, dict[str, Any]]:
    manifest = pd.read_csv(MANIFEST)
    xp = pd.read_csv(XP_TABLE)
    xp_by_id = {str(row["title"]): row for _, row in xp.iterrows()}
    curated = pd.read_csv(CURATED_TABLE)
    curated_by_id = {
        str(row["molecule"]): row for _, row in curated.iterrows()
    }
    top250 = (
        pd.read_csv(TOP250_TABLE)
        if TOP250_TABLE.exists()
        else pd.DataFrame()
    )
    top250_by_id = (
        {str(row["library_id"]): row for _, row in top250.iterrows()}
        if not top250.empty
        else {}
    )
    xp_next = (
        pd.read_csv(XP_NEXT_TABLE)
        if XP_NEXT_TABLE.exists()
        else pd.DataFrame()
    )
    xp_next_by_id = (
        {str(row["title"]): row for _, row in xp_next.iterrows()}
        if not xp_next.empty
        else {}
    )
    result = {}
    for _, row in manifest.iterrows():
        molecule_id = str(row["mol_id"])
        xp_row = xp_by_id.get(molecule_id)
        curated_row = curated_by_id.get(molecule_id)
        top_row = top250_by_id.get(molecule_id)
        next_row = xp_next_by_id.get(molecule_id)

        xp_gscore = math.nan
        for candidate in (
            curated_row.get("XP_GScore") if curated_row is not None else None,
            xp_row.get("r_i_docking_score_xp") if xp_row is not None else None,
            top_row.get("r_i_docking_score") if top_row is not None else None,
            next_row.get("r_i_docking_score") if next_row is not None else None,
            next_row.get("r_i_glide_gscore") if next_row is not None else None,
        ):
            value = _safe_float(candidate)
            if not math.isnan(value):
                xp_gscore = value
                break

        hepg2_risk = math.nan
        for candidate in (
            curated_row.get("HepG2_risk") if curated_row is not None else None,
            xp_row.get("HepG2_weighted_risk") if xp_row is not None else None,
            top_row.get("HepG2_weighted_risk") if top_row is not None else None,
        ):
            value = _safe_float(candidate)
            if not math.isnan(value):
                hepg2_risk = value
                break

        safety_score = math.nan
        for candidate in (
            curated_row.get("safety_score") if curated_row is not None else None,
            xp_row.get("core_safety_score") if xp_row is not None else None,
            top_row.get("core_safety_score") if top_row is not None else None,
        ):
            value = _safe_float(candidate)
            if not math.isnan(value):
                safety_score = value
                break

        rank_index = _safe_float(row.get("rank_index"))
        result[molecule_id] = {
            "rank_index": int(rank_index) if not math.isnan(rank_index) else None,
            "mmgbsa": float(row["mmgbsa"]),
            "smiles": str(row["smiles"]),
            "formal_charge": int(row["formal_charge_sum"]),
            "xp_gscore": xp_gscore,
            "hepg2_risk": hepg2_risk,
            "safety_score": safety_score,
        }
    return result


def _pose_and_retention_calls(row: dict[str, Any]) -> tuple[str, str]:
    if (
        row["protein_ca_p95"] <= 2.5
        and row["ligand_rmsd_median"] <= 2.5
        and row["ligand_rmsd_p95"] <= 3.5
        and row["direct_contact_coverage"] >= 0.50
    ):
        pose_call = "PASS"
    elif (
        row["protein_ca_p95"] <= 4.0
        and row["ligand_rmsd_median"] <= 3.5
        and row["ligand_rmsd_p95"] <= 5.0
        and row["any_contact_coverage"] >= 0.50
    ):
        pose_call = "REVIEW"
    else:
        pose_call = "FAIL_POSE"

    if row["ligand_rmsd_late_mean"] > 12.0:
        retention = "LOST"
    elif (
        row["ligand_rmsd_late_mean"] <= 3.5
        and row["late_direct_contact_coverage"] >= 0.50
    ):
        retention = "RETAINED"
    elif (
        row["ligand_rmsd_late_mean"] > 3.5
        and row["late_direct_contact_coverage"] >= 0.70
        and row["strongest_direct_occupancy"] >= 0.25
    ):
        retention = "ALT_POSE"
    elif (
        row["ligand_rmsd_late_mean"] <= 5.0
        and row["any_contact_coverage"] >= 0.50
    ):
        retention = "WEAK_RETENTION"
    else:
        retention = "LOST"
    return pose_call, retention


def _triage_scores(row: dict[str, Any]) -> tuple[float, float, float]:
    ligand_late = _linear_good(row["ligand_rmsd_late_mean"], 2.0, 8.0)
    ligand_p95 = _linear_good(row["ligand_rmsd_p95"], 2.5, 8.0)
    protein = _linear_good(row["protein_ca_p95"], 2.5, 4.0)
    contact = min(max(row["direct_contact_coverage"], 0.0), 1.0)
    persistent = min(row["strongest_direct_occupancy"] / 0.50, 1.0)
    drift = _linear_good(max(row["ligand_rmsd_slope"], 0.0), 0.02, 0.12)
    md_score = 100 * (
        0.25 * ligand_late
        + 0.15 * ligand_p95
        + 0.15 * protein
        + 0.20 * contact
        + 0.15 * persistent
        + 0.10 * drift
    )

    xp_score = (
        min(max((-row["xp_gscore"] - 7.0) / 2.5, 0.0), 1.0)
        if not math.isnan(row["xp_gscore"])
        else 0.0
    )
    mmgbsa_score = (
        min(max((-row["mmgbsa"] - 40.0) / 25.0, 0.0), 1.0)
        if not math.isnan(row["mmgbsa"])
        else 0.0
    )
    safety = (
        min(max((row["safety_score"] - 80.0) / 20.0, 0.0), 1.0)
        if not math.isnan(row["safety_score"])
        else 0.5
    )
    exposure = {"低": 1.0, "中": 0.65, "高": 0.30}.get(
        row["cell_exposure_risk"],
        0.5,
    )
    biochemical = (
        0.75 * md_score + 100 * (0.15 * xp_score + 0.10 * mmgbsa_score)
    )
    cellular = (
        0.55 * md_score
        + 100
        * (
            0.10 * xp_score
            + 0.10 * mmgbsa_score
            + 0.15 * safety
            + 0.10 * exposure
        )
    )
    if row["binding_retention"] == "LOST":
        biochemical = min(biochemical, 40.0)
        cellular = min(cellular, 35.0)
    elif row["binding_retention"] == "ALT_POSE":
        biochemical = min(biochemical, 65.0)
        cellular = min(cellular, 60.0)
    elif row["binding_retention"] == "WEAK_RETENTION":
        biochemical = min(biochemical, 74.9)
        cellular = min(cellular, 69.9)
    if row["cell_exposure_risk"] == "高":
        cellular = min(cellular, 59.9)
    elif row["cell_exposure_risk"] == "中":
        cellular = min(cellular, 74.9)
    if (
        not math.isnan(row["hepg2_risk"])
        and row["hepg2_risk"] >= 0.075
    ):
        cellular = min(cellular, 74.9)
    # Cellular priority cannot exceed the underlying biochemical evidence.
    cellular = min(cellular, biochemical)
    return md_score, biochemical, cellular


def _tier(score: float) -> str:
    if score >= 75:
        return "A"
    if score >= 60:
        return "B"
    if score >= 45:
        return "C"
    return "D"


def _wetlab_note(row: dict[str, Any]) -> str:
    notes = []
    if row["binding_retention"] == "RETAINED":
        notes.append("50 ns内保持口袋接触")
    elif row["binding_retention"] == "ALT_POSE":
        notes.append("保留接触但重排为替代姿势，需目视终态")
    elif row["binding_retention"] == "WEAK_RETENTION":
        notes.append("接触保留有限，建议复现实验或重复轨迹")
    else:
        notes.append("初始对接姿势未保持")

    if row["cell_exposure_risk"] == "高":
        notes.append("细胞通透/暴露可能限制，酶学可能优于细胞读数")
    elif row["cell_exposure_risk"] == "中":
        notes.append("细胞暴露存在一定不确定性")
    if (
        not math.isnan(row["hepg2_risk"])
        and row["hepg2_risk"] >= 0.08
    ):
        notes.append("HepG2风险代理偏高，需同步做活率窗口")
    elif (
        not math.isnan(row["safety_score"])
        and row["safety_score"] >= 95
    ):
        notes.append("现有HepG2风险代理较低")
    return "；".join(notes)


def analyze_one(
    molecule_id: str,
    upstream: dict[str, dict[str, Any]],
    sea_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], pd.DataFrame]:
    molecule_root = sea_root / molecule_id
    official_data = molecule_root / "official_data"
    data_dir = (
        official_data
        if (official_data / "PL_RMSD.dat").exists()
        else molecule_root / "data"
    )
    required = [
        data_dir / "PL_RMSD.dat",
        data_dir / "P_RMSF.dat",
        data_dir / "L_RMSF.dat",
        data_dir / "L-Properties.dat",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"{molecule_id}: missing SEA files: {missing}")

    rmsd = _read_rmsd(required[0])
    n_frames = len(rmsd)
    burn_frame = max(1, int(n_frames * BURN_FRACTION))
    late_start = max(burn_frame, int(n_frames * 0.80))
    post = rmsd[rmsd["frame"] >= burn_frame].copy()
    late = rmsd[rmsd["frame"] >= late_start].copy()
    post["time_ns"] = post["frame"] * FRAME_INTERVAL_NS

    protein_rmsf = _read_protein_rmsf(required[1])
    ligand_rmsf = _read_ligand_rmsf(required[2])
    ligand_properties = _read_ligand_properties(required[3])
    ligand_properties = ligand_properties[
        ligand_properties["frame"] >= burn_frame
    ]

    contact_metrics, contact_rows = _contact_metrics(
        data_dir,
        n_frames,
        burn_frame,
        late_start,
    )
    metadata = upstream[molecule_id]
    row: dict[str, Any] = {
        "molecule_id": molecule_id,
        "production_ns": 50.0,
        "n_frames": n_frames,
        "burn_in_ns": burn_frame * FRAME_INTERVAL_NS,
        "protein_ca_mean": post["protein_ca"].mean(),
        "protein_ca_median": post["protein_ca"].median(),
        "protein_ca_p95": post["protein_ca"].quantile(0.95),
        "protein_ca_late_mean": late["protein_ca"].mean(),
        "protein_ca_late_sd": late["protein_ca"].std(),
        "protein_ca_slope": _slope(post["time_ns"], post["protein_ca"]),
        "ligand_rmsd_mean": post["ligand_wrt_protein"].mean(),
        "ligand_rmsd_median": post["ligand_wrt_protein"].median(),
        "ligand_rmsd_p95": post["ligand_wrt_protein"].quantile(0.95),
        "ligand_rmsd_max": post["ligand_wrt_protein"].max(),
        "ligand_rmsd_late_mean": late["ligand_wrt_protein"].mean(),
        "ligand_rmsd_late_sd": late["ligand_wrt_protein"].std(),
        "ligand_rmsd_slope": _slope(
            post["time_ns"],
            post["ligand_wrt_protein"],
        ),
        "first_sustained_rmsd_gt5_ns": _first_sustained_crossing(
            post,
            "ligand_wrt_protein",
            5.0,
        ),
        "first_sustained_rmsd_gt10_ns": _first_sustained_crossing(
            post,
            "ligand_wrt_protein",
            10.0,
        ),
        "ligand_internal_rmsd_median": post[
            "ligand_wrt_ligand"
        ].median(),
        "ligand_internal_rmsd_p95": post[
            "ligand_wrt_ligand"
        ].quantile(0.95),
        "ligand_rmsf_internal_mean": ligand_rmsf["wrt_ligand"].mean(),
        "ligand_rmsf_internal_p95": ligand_rmsf[
            "wrt_ligand"
        ].quantile(0.95),
        "protein_contact_ca_rmsf_mean": protein_rmsf.loc[
            protein_rmsf["ligand_contact"],
            "ca",
        ].mean(),
        "protein_contact_ca_rmsf_p95": protein_rmsf.loc[
            protein_rmsf["ligand_contact"],
            "ca",
        ].quantile(0.95),
        "ligand_rgyr_mean": ligand_properties["rgyr"].mean(),
        "ligand_rgyr_cv": (
            ligand_properties["rgyr"].std()
            / ligand_properties["rgyr"].mean()
        ),
        "ligand_sasa_mean": ligand_properties["sasa"].mean(),
        "ligand_sasa_cv": (
            ligand_properties["sasa"].std()
            / ligand_properties["sasa"].mean()
        ),
        **contact_metrics,
        **metadata,
    }
    row.update(
        _descriptor_metrics(
            row["smiles"],
            row["formal_charge"],
        )
    )
    pose_call, retention = _pose_and_retention_calls(row)
    row["pose_call"] = pose_call
    row["binding_retention"] = retention
    md_score, biochemical, cellular = _triage_scores(row)
    row["md_triage_score"] = md_score
    row["biochemical_triage_score"] = biochemical
    row["cellular_triage_score"] = cellular
    row["biochemical_tier"] = _tier(biochemical)
    row["cellular_tier"] = _tier(cellular)
    row["wetlab_expectation"] = _wetlab_note(row)
    row["evidence_confidence"] = (
        "中" if pose_call in {"PASS", "FAIL_POSE"} else "低-中"
    )

    for contact_row in contact_rows:
        contact_row["molecule_id"] = molecule_id

    trace = rmsd[
        [
            "frame",
            "protein_ca",
            "ligand_wrt_protein",
            "ligand_wrt_ligand",
        ]
    ].copy()
    trace.insert(0, "molecule_id", molecule_id)
    trace["time_ns"] = trace["frame"] * FRAME_INTERVAL_NS
    return row, contact_rows, trace


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _write_markdown(summary: pd.DataFrame, output: Path) -> None:
    n = len(summary)
    ranked = summary.sort_values(
        ["biochemical_tier", "biochemical_triage_score"],
        ascending=[True, False],
    )
    top = ranked.head(6)["molecule_id"].tolist()
    retained = summary[
        summary["binding_retention"].isin(["RETAINED", "ALT_POSE"])
    ]["molecule_id"].tolist()
    lost = summary[summary["binding_retention"] == "LOST"][
        "molecule_id"
    ].tolist()
    tier_counts = (
        summary["biochemical_tier"].value_counts().to_dict()
    )

    lines = [
        f"# HSD17B13 {n}分子 Phase-A MD 稳定性分析",
        "",
        "## 结论",
        "",
        f"- 酶学优先候选（综合评分前6）：{', '.join(top)}",
        f"- 结合接触保留/替代姿势：{', '.join(retained) or '无'}",
        f"- 初始姿势丢失：{', '.join(lost) or '无'}",
        f"- 分层计数：{tier_counts}",
        "",
        "## 判据",
        "",
        "- 仅分析50 ns生产段，丢弃前10%（约5 ns）。",
        "- PASS：蛋白Cα p95≤2.5 Å、配体RMSD中位数≤2.5 Å、"
        "p95≤3.5 Å且直接接触覆盖≥50%。",
        "- ALT_POSE：初始姿势发生明显重排，但晚期直接接触覆盖≥70%，"
        "且至少一个直接接触占有率≥25%。",
        "- 评分是筛选用启发式，不是ΔG或IC50；湿实验预期只给相对优先级。",
        "",
        "## 数据文件",
        "",
        "- `md27_metrics.csv`：每分子指标与分层",
        "- `md27_contacts.csv`：残基-相互作用占有率",
        "- `md27_rmsd_traces.csv`：50 ns RMSD时间序列",
        "- `md27_summary.json`：Canvas用结构化结果",
        "",
        "## 重要限制",
        "",
        "- 每分子只有一条50 ns轨迹，无独立重复，置信度最高仅为“中”。",
        "- MD支持的是姿势保持/接触保留，不直接证明抑制效力。",
        "- 细胞读数还受通透、溶解度、代谢和膜分配影响；先做无细胞酶学，"
        "再做细胞验证。",
    ]
    (output / "MD27_ANALYSIS.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*", default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--sea-root",
        type=Path,
        default=ANALYSIS_ROOT / "per_molecule",
        help="Directory containing <molecule_id>/data SEA tables",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    molecule_ids = args.ids or DEFAULT_IDS
    if not molecule_ids:
        raise SystemExit("No molecule IDs found (meta/ids_27.txt empty?)")

    upstream = _upstream_metadata()
    summary_rows = []
    contact_rows = []
    traces = []
    for molecule_id in molecule_ids:
        row, contacts, trace = analyze_one(
            molecule_id,
            upstream,
            args.sea_root,
        )
        summary_rows.append(row)
        contact_rows.extend(contacts)
        traces.append(trace)

    summary = pd.DataFrame(summary_rows).sort_values(
        "biochemical_triage_score",
        ascending=False,
    )
    summary.insert(0, "biochemical_rank", range(1, len(summary) + 1))
    summary.to_csv(args.out / "md27_metrics.csv", index=False)
    # keep legacy aliases for older consumers
    summary.to_csv(args.out / "md12_metrics.csv", index=False)

    contacts = pd.DataFrame(contact_rows)
    if not contacts.empty:
        contacts = contacts.sort_values(
            ["molecule_id", "occupancy"],
            ascending=[True, False],
        )
    contacts.to_csv(args.out / "md27_contacts.csv", index=False)
    contacts.to_csv(args.out / "md12_contacts.csv", index=False)

    trace_table = pd.concat(traces, ignore_index=True)
    trace_table.to_csv(args.out / "md27_rmsd_traces.csv", index=False)
    trace_table.to_csv(args.out / "md12_rmsd_traces.csv", index=False)

    records = [
        {key: _json_value(value) for key, value in record.items()}
        for record in summary.to_dict(orient="records")
    ]
    (args.out / "md27_summary.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    )
    (args.out / "md12_summary.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    )
    _write_markdown(summary, args.out)
    print(f"Wrote {len(summary)} molecules to {args.out}")


if __name__ == "__main__":
    main()
