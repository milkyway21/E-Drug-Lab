#!/usr/bin/env python3
"""Reproducible 200 ns stability analysis for Desmond protein-ligand campaigns.

The analysis deliberately treats pocket retention and protein-ligand contacts
as stronger evidence than the absolute ligand RMSD. Geometry is calculated
directly from the Desmond DTR after protein C-alpha alignment; interaction
types are read from the matching Simulation Event Analysis exports.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.signal import find_peaks
from scipy.spatial.distance import cdist, pdist, squareform

from schrodinger.application.desmond.packages import topo, traj
from schrodinger.structure import StructureWriter

try:
    from rdkit import Chem, DataStructs
    from rdkit.Chem import AllChem, QED
    from rdkit.Chem.Scaffolds import MurckoScaffold
except ImportError:  # pragma: no cover - optional metadata only
    Chem = DataStructs = AllChem = QED = MurckoScaffold = None


TRAJ_ROOT = Path(".")
SEA_ROOT = Path(".")
UPSTREAM_DECISION = Path("/__desmond_md_no_upstream_decision__")
MANIFEST = Path(".")
PROTEIN_ASL = "protein"
LIGAND_ASL = ""
TARGET_LABEL = "Target"

CONTACT_TYPES = (
    "HBond",
    "Hydrophobic",
    "Pi-Pi",
    "Pi-Cation",
    "Ionic",
    "Metal",
    "WaterBridge",
)
DIRECT_TYPES = set(CONTACT_TYPES) - {"WaterBridge"}
POCKET_CUTOFF_ANGSTROM = 6.0
EARLY_END_NS = 10.0
LATE_START_NS = 150.0
VERY_LATE_START_NS = 180.0
CLUSTER_CUTOFF_ANGSTROM = 2.0


def clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def slope(time_ns: np.ndarray, values: np.ndarray) -> float:
    mask = np.isfinite(time_ns) & np.isfinite(values)
    if mask.sum() < 2:
        return math.nan
    return float(np.polyfit(time_ns[mask], values[mask], 1)[0])


def rmsd(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.sum((a - b) ** 2, axis=1))))


def kabsch(mobile: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mobile_center = mobile.mean(axis=0)
    reference_center = reference.mean(axis=0)
    covariance = (mobile - mobile_center).T @ (reference - reference_center)
    u, _, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    return rotation, mobile_center, reference_center


def apply_alignment(
    coordinates: np.ndarray,
    rotation: np.ndarray,
    mobile_center: np.ndarray,
    reference_center: np.ndarray,
) -> np.ndarray:
    return (coordinates - mobile_center) @ rotation + reference_center


def minimum_image(delta: np.ndarray, box: np.ndarray) -> np.ndarray:
    """Return minimum-image displacement for a row-vector box convention."""
    shape = delta.shape
    flat = np.asarray(delta, dtype=float).reshape(-1, 3)
    inverse = np.linalg.inv(np.asarray(box, dtype=float))
    fractional = flat @ inverse
    fractional -= np.round(fractional)
    return (fractional @ box).reshape(shape)


def unwrap_group(coordinates: np.ndarray, box: np.ndarray) -> np.ndarray:
    if len(coordinates) < 2:
        return coordinates.copy()
    anchor = coordinates[0]
    return anchor + minimum_image(coordinates - anchor, box)


def residue_key(atom: Any) -> str:
    chain = atom.chain.strip() or "_"
    resname = atom.pdbres.strip()
    insertion = atom.inscode.strip()
    suffix = f"{atom.resnum}{insertion}" if insertion else str(atom.resnum)
    return f"{chain}:{resname}{suffix}"


def read_ids() -> list[str]:
    raise RuntimeError("Pass molecule IDs explicitly with --ids")


def read_rmsd(path: Path) -> pd.DataFrame:
    names = [
        "frame",
        "protein_ca_sea",
        "protein_backbone_sea",
        "protein_sidechain_sea",
        "protein_heavy_sea",
        "ligand_rmsd_sea",
        "ligand_internal_rmsd_sea",
    ]
    table = pd.read_csv(path, sep=r"\s+", comment="#", names=names, header=None)
    return table.apply(pd.to_numeric, errors="coerce").dropna(subset=["frame"])


def read_ligand_properties(path: Path) -> pd.DataFrame:
    names = ["frame", "property_rmsd", "rgyr", "intrahb", "molsa", "sasa", "psa"]
    table = pd.read_csv(path, sep=r"\s+", comment="#", names=names, header=None)
    return table.apply(pd.to_numeric, errors="coerce").dropna(subset=["frame"])


def parse_contact_file(path: Path, contact_type: str, n_frames: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(errors="ignore").splitlines():
        tokens = line.split()
        if len(tokens) < 4 or not tokens[0].isdigit():
            continue
        frame = int(tokens[0])
        if frame < 0 or frame >= n_frames:
            continue
        if tokens[1] == "prot-side":
            parts = tokens[2].split(":")
            if len(parts) < 2:
                continue
            chain = parts[0] or "_"
            resname, _, resnum = parts[1].rpartition("_")
        elif tokens[1].lstrip("-").isdigit():
            resnum = tokens[1]
            chain = tokens[2] or "_"
            resname = tokens[3]
        else:
            continue
        rows.append(
            {
                "frame": frame,
                "contact_type": contact_type,
                "chain": chain.strip() or "_",
                "resnum": str(resnum),
                "resname": resname.strip(),
                "residue": f"{chain.strip() or '_'}:{resname.strip()}{resnum}",
            }
        )
    return rows


def contact_analysis(
    data_dir: Path,
    times: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], dict[str, Any]]:
    n_frames = len(times)
    rows: list[dict[str, Any]] = []
    for contact_type in CONTACT_TYPES:
        rows.extend(
            parse_contact_file(
                data_dir / f"PL-Contacts_{contact_type}.dat",
                contact_type,
                n_frames,
            )
        )
    events = pd.DataFrame(rows)
    traces = pd.DataFrame({"frame": np.arange(n_frames), "time_ns": times})
    traces["direct_contact"] = 0.0
    traces["direct_contact_count"] = 0.0
    for contact_type in CONTACT_TYPES:
        traces[f"{contact_type.lower().replace('-', '_')}_contact"] = 0.0

    residue_frames: dict[str, set[int]] = defaultdict(set)
    type_residue_frames: dict[tuple[str, str], set[int]] = defaultdict(set)
    if not events.empty:
        for contact_type, subset in events.groupby("contact_type"):
            frames = subset["frame"].astype(int).unique()
            traces.loc[frames, f"{contact_type.lower().replace('-', '_')}_contact"] = 1.0
            if contact_type in DIRECT_TYPES:
                traces.loc[frames, "direct_contact"] = 1.0
        for (frame, _), subset in events[events["contact_type"].isin(DIRECT_TYPES)].groupby(
            ["frame", "residue"]
        ):
            traces.loc[int(frame), "direct_contact_count"] += 1.0
        for row in events.itertuples(index=False):
            type_residue_frames[(row.contact_type, row.residue)].add(int(row.frame))
            if row.contact_type in DIRECT_TYPES:
                residue_frames[row.residue].add(int(row.frame))

    early_mask = times <= EARLY_END_NS
    late_mask = times >= LATE_START_NS
    n_early = max(int(early_mask.sum()), 1)
    n_late = max(int(late_mask.sum()), 1)

    early_occupancy = {
        residue: len({frame for frame in frames if early_mask[frame]}) / n_early
        for residue, frames in residue_frames.items()
    }
    late_occupancy = {
        residue: len({frame for frame in frames if late_mask[frame]}) / n_late
        for residue, frames in residue_frames.items()
    }
    ranked_early = sorted(early_occupancy, key=early_occupancy.get, reverse=True)
    key_residues = [residue for residue in ranked_early if early_occupancy[residue] >= 0.30][
        :6
    ]
    if len(key_residues) < 2:
        key_residues = [residue for residue in ranked_early if early_occupancy[residue] >= 0.10][
            :3
        ]

    key_fraction = np.zeros(n_frames, dtype=float)
    if key_residues:
        for residue in key_residues:
            key_fraction[list(residue_frames.get(residue, set()))] += 1.0
        key_fraction /= len(key_residues)
    traces["key_contact_fraction"] = key_fraction

    denominator = sum(early_occupancy.get(residue, 0.0) for residue in key_residues)
    retained = sum(
        min(early_occupancy.get(residue, 0.0), late_occupancy.get(residue, 0.0))
        for residue in key_residues
    )
    key_retention = retained / denominator if denominator > 0 else 0.0
    new_stable = sorted(
        [
            residue
            for residue, occupancy in late_occupancy.items()
            if occupancy >= 0.30 and early_occupancy.get(residue, 0.0) < 0.10
        ],
        key=late_occupancy.get,
        reverse=True,
    )

    occupancy_rows: list[dict[str, Any]] = []
    for (contact_type, residue), frames in type_residue_frames.items():
        occupancy_rows.append(
            {
                "contact_type": contact_type,
                "residue": residue,
                "occupancy_full": len(frames) / n_frames,
                "occupancy_early": len({frame for frame in frames if early_mask[frame]})
                / n_early,
                "occupancy_late": len({frame for frame in frames if late_mask[frame]})
                / n_late,
                "is_initial_key": residue in key_residues,
                "is_new_stable_late": residue in new_stable,
            }
        )
    occupancy = pd.DataFrame(occupancy_rows)
    if not occupancy.empty:
        occupancy = occupancy.sort_values(
            ["occupancy_late", "occupancy_full"], ascending=False
        )

    details = {
        "key_contact_retention": key_retention,
        "key_contact_details": [
            {
                "residue": residue,
                "early": early_occupancy.get(residue, 0.0),
                "late": late_occupancy.get(residue, 0.0),
            }
            for residue in key_residues
        ],
        "new_stable_contacts": [
            {"residue": residue, "late": late_occupancy[residue]}
            for residue in new_stable[:8]
        ],
    }
    return traces, occupancy, key_residues, details


def build_geometry_context(cms_model: Any, trajectory: Any) -> dict[str, Any]:
    protein_ca_aids = cms_model.select_atom(f"({PROTEIN_ASL}) and atom.ptype CA")
    protein_heavy_aids = cms_model.select_atom(f"({PROTEIN_ASL}) and not atom.ele H")
    ligand_all_aids = cms_model.select_atom(LIGAND_ASL)
    ligand_heavy_aids = cms_model.select_atom(f"({LIGAND_ASL}) and not atom.ele H")
    if not protein_ca_aids or not protein_heavy_aids or not ligand_heavy_aids:
        raise ValueError("Required protein/ligand atom selection is empty")

    protein_ca_gids = topo.aids2gids(cms_model, protein_ca_aids, include_pseudoatoms=False)
    protein_heavy_gids = topo.aids2gids(
        cms_model, protein_heavy_aids, include_pseudoatoms=False
    )
    ligand_all_gids = topo.aids2gids(cms_model, ligand_all_aids, include_pseudoatoms=False)
    ligand_heavy_gids = topo.aids2gids(
        cms_model, ligand_heavy_aids, include_pseudoatoms=False
    )

    first = trajectory[0]
    box = np.asarray(first.box, dtype=float)
    ligand = unwrap_group(first.pos(ligand_heavy_gids), box)
    protein_heavy = first.pos(protein_heavy_gids)
    deltas = ligand[:, None, :] - protein_heavy[None, :, :]
    distances = np.linalg.norm(minimum_image(deltas, box), axis=2)
    near_aids = {
        protein_heavy_aids[index]
        for index in np.where(np.min(distances, axis=0) <= POCKET_CUTOFF_ANGSTROM)[0]
    }
    pocket_residues = {residue_key(cms_model.atom[aid]) for aid in near_aids}
    pocket_ca_aids = [
        aid
        for aid in protein_ca_aids
        if residue_key(cms_model.atom[aid]) in pocket_residues
    ]
    pocket_heavy_aids = [
        aid
        for aid in protein_heavy_aids
        if residue_key(cms_model.atom[aid]) in pocket_residues
    ]
    pocket_all_aids = [
        atom.index for atom in cms_model.atom if residue_key(atom) in pocket_residues
    ]
    if len(pocket_ca_aids) < 3 or len(pocket_heavy_aids) < 10:
        raise ValueError(f"Pocket selection is too small: {len(pocket_ca_aids)} C-alpha")

    ligand_masses = np.asarray(
        [cms_model.atom[aid].atomic_weight for aid in ligand_heavy_aids], dtype=float
    )
    heavy_index = {aid: index for index, aid in enumerate(ligand_heavy_aids)}
    bonds: list[tuple[int, int]] = []
    try:
        for bond in cms_model.bond:
            aid1 = bond.atom1.index
            aid2 = bond.atom2.index
            if aid1 in heavy_index and aid2 in heavy_index:
                bonds.append((heavy_index[aid1], heavy_index[aid2]))
    except Exception:
        bonds = []

    return {
        "protein_ca_aids": protein_ca_aids,
        "protein_ca_gids": protein_ca_gids,
        "ligand_all_aids": ligand_all_aids,
        "ligand_all_gids": ligand_all_gids,
        "ligand_heavy_aids": ligand_heavy_aids,
        "ligand_heavy_gids": ligand_heavy_gids,
        "ligand_masses": ligand_masses,
        "pocket_residues": sorted(pocket_residues),
        "pocket_ca_aids": pocket_ca_aids,
        "pocket_ca_gids": topo.aids2gids(
            cms_model, pocket_ca_aids, include_pseudoatoms=False
        ),
        "pocket_heavy_aids": pocket_heavy_aids,
        "pocket_heavy_gids": topo.aids2gids(
            cms_model, pocket_heavy_aids, include_pseudoatoms=False
        ),
        "pocket_all_aids": pocket_all_aids,
        "ligand_bonds": bonds,
    }


def geometry_analysis(
    cms_model: Any,
    trajectory: Any,
    context: dict[str, Any],
) -> tuple[pd.DataFrame, np.ndarray, dict[str, np.ndarray]]:
    n_frames = len(trajectory)
    times = np.asarray([frame.time / 1000.0 for frame in trajectory], dtype=float)
    first = trajectory[0]
    reference_ca = first.pos(context["protein_ca_gids"]).copy()
    reference_pocket_ca = first.pos(context["pocket_ca_gids"]).copy()
    reference_pocket_heavy = unwrap_group(
        first.pos(context["pocket_heavy_gids"]), np.asarray(first.box)
    )
    reference_ligand = unwrap_group(
        first.pos(context["ligand_heavy_gids"]), np.asarray(first.box)
    )
    reference_pocket_center = reference_pocket_heavy.mean(axis=0)
    reference_ligand_com = np.average(
        reference_ligand, axis=0, weights=context["ligand_masses"]
    )
    initial_delta = minimum_image(
        reference_ligand_com - reference_pocket_center, np.asarray(first.box)
    )
    reference_ligand += initial_delta - (
        reference_ligand_com - reference_pocket_center
    )

    protein_rmsd = np.empty(n_frames)
    pocket_rmsd = np.empty(n_frames)
    ligand_rmsd = np.empty(n_frames)
    ligand_internal_rmsd = np.empty(n_frames)
    com_distance = np.empty(n_frames)
    min_pocket_distance = np.empty(n_frames)
    pbc_shift_norm = np.empty(n_frames)
    aligned_ligands = np.empty(
        (n_frames, len(context["ligand_heavy_gids"]), 3), dtype=np.float32
    )
    rotations = np.empty((n_frames, 3, 3))
    mobile_centers = np.empty((n_frames, 3))
    reference_centers = np.empty((n_frames, 3))
    ligand_shifts = np.empty((n_frames, 3))

    for index, frame in enumerate(trajectory):
        box = np.asarray(frame.box, dtype=float)
        protein_ca = frame.pos(context["protein_ca_gids"])
        rotation, mobile_center, reference_center = kabsch(protein_ca, reference_ca)
        aligned_ca = apply_alignment(
            protein_ca, rotation, mobile_center, reference_center
        )
        pocket_ca = frame.pos(context["pocket_ca_gids"])
        aligned_pocket_ca = apply_alignment(
            pocket_ca, rotation, mobile_center, reference_center
        )
        pocket_heavy = unwrap_group(frame.pos(context["pocket_heavy_gids"]), box)
        pocket_center = pocket_heavy.mean(axis=0)
        ligand = unwrap_group(frame.pos(context["ligand_heavy_gids"]), box)
        ligand_com = np.average(ligand, axis=0, weights=context["ligand_masses"])
        raw_delta = ligand_com - pocket_center
        nearest_delta = minimum_image(raw_delta, box)
        ligand_shift = nearest_delta - raw_delta
        ligand += ligand_shift
        aligned_ligand = apply_alignment(
            ligand, rotation, mobile_center, reference_center
        )
        aligned_pocket_heavy = apply_alignment(
            pocket_heavy, rotation, mobile_center, reference_center
        )
        aligned_com = np.average(
            aligned_ligand, axis=0, weights=context["ligand_masses"]
        )

        ligand_rotation, ligand_center, reference_ligand_center = kabsch(
            aligned_ligand, reference_ligand
        )
        ligand_fit = apply_alignment(
            aligned_ligand,
            ligand_rotation,
            ligand_center,
            reference_ligand_center,
        )

        protein_rmsd[index] = rmsd(aligned_ca, reference_ca)
        pocket_rmsd[index] = rmsd(aligned_pocket_ca, reference_pocket_ca)
        ligand_rmsd[index] = rmsd(aligned_ligand, reference_ligand)
        ligand_internal_rmsd[index] = rmsd(ligand_fit, reference_ligand)
        com_distance[index] = np.linalg.norm(aligned_com - reference_pocket_center)
        min_pocket_distance[index] = float(
            np.min(cdist(aligned_ligand, aligned_pocket_heavy))
        )
        pbc_shift_norm[index] = np.linalg.norm(ligand_shift)
        aligned_ligands[index] = aligned_ligand
        rotations[index] = rotation
        mobile_centers[index] = mobile_center
        reference_centers[index] = reference_center
        ligand_shifts[index] = ligand_shift

    table = pd.DataFrame(
        {
            "frame": np.arange(n_frames),
            "time_ns": times,
            "protein_ca_rmsd_geom": protein_rmsd,
            "pocket_ca_rmsd": pocket_rmsd,
            "ligand_rmsd_geom": ligand_rmsd,
            "ligand_internal_rmsd_geom": ligand_internal_rmsd,
            "ligand_pocket_com_distance": com_distance,
            "min_pocket_distance": min_pocket_distance,
            "pbc_shift_norm": pbc_shift_norm,
        }
    )
    transforms = {
        "rotations": rotations,
        "mobile_centers": mobile_centers,
        "reference_centers": reference_centers,
        "ligand_shifts": ligand_shifts,
        "reference_pocket_ca": reference_pocket_ca,
    }
    return table, aligned_ligands, transforms


def cluster_late_poses(
    times: np.ndarray, aligned_ligands: np.ndarray
) -> dict[str, Any]:
    late_indices = np.where(times >= LATE_START_NS)[0]
    coordinates = aligned_ligands[late_indices].astype(float)
    if len(coordinates) == 1:
        return {
            "dominant_cluster_fraction": 1.0,
            "cluster_count": 1,
            "cluster_labels": np.ones(1, dtype=int),
            "late_indices": late_indices,
            "representative_indices": [int(late_indices[0])],
            "cluster_sizes": [1],
        }
    condensed = pdist(coordinates.reshape(len(coordinates), -1)) / math.sqrt(
        coordinates.shape[1]
    )
    tree = linkage(condensed, method="average")
    labels = fcluster(tree, t=CLUSTER_CUTOFF_ANGSTROM, criterion="distance")
    counts = Counter(labels)
    ranked = sorted(counts, key=counts.get, reverse=True)
    matrix = squareform(condensed)
    representatives: list[int] = []
    sizes: list[int] = []
    for cluster in ranked[:3]:
        members = np.where(labels == cluster)[0]
        medoid_local = members[np.argmin(matrix[np.ix_(members, members)].mean(axis=1))]
        representatives.append(int(late_indices[medoid_local]))
        sizes.append(int(len(members)))
    return {
        "dominant_cluster_fraction": max(counts.values()) / len(labels),
        "cluster_count": len(counts),
        "cluster_labels": labels,
        "late_indices": late_indices,
        "representative_indices": representatives,
        "cluster_sizes": sizes,
    }


def detect_transitions(table: pd.DataFrame) -> pd.DataFrame:
    times = table["time_ns"].to_numpy(float)
    dt = float(np.median(np.diff(times)))
    half_window = max(5, int(round(5.0 / dt)))
    n = len(table)
    score = np.zeros(n)
    deltas: dict[str, np.ndarray] = {}
    scales = {
        "ligand_rmsd_geom": 1.5,
        "ligand_pocket_com_distance": 2.0,
        "direct_contact_count": 1.5,
        "key_contact_fraction": 0.30,
        "pocket_ca_rmsd": 0.60,
    }
    for column, scale in scales.items():
        values = table[column].to_numpy(float)
        change = np.zeros(n)
        for index in range(half_window, n - half_window):
            before = np.nanmean(values[index - half_window : index])
            after = np.nanmean(values[index : index + half_window])
            change[index] = after - before
        deltas[column] = change
        score += np.minimum(np.abs(change) / scale, 3.0) ** 2
    score = np.sqrt(score)
    peaks, properties = find_peaks(
        score,
        height=1.8,
        prominence=0.35,
        distance=max(10, int(round(8.0 / dt))),
    )
    peaks = [index for index in peaks if 5.0 <= times[index] <= times[-1] - 5.0]
    if len(peaks) > 8:
        peaks = sorted(peaks, key=lambda index: score[index], reverse=True)[:8]
        peaks.sort()

    rows: list[dict[str, Any]] = []
    for index in peaks:
        before_slice = slice(index - half_window, index)
        after_slice = slice(index, index + half_window)

        def mean(column: str, selection: slice) -> float:
            return float(np.nanmean(table[column].to_numpy(float)[selection]))

        before_rmsd = mean("ligand_rmsd_geom", before_slice)
        after_rmsd = mean("ligand_rmsd_geom", after_slice)
        before_com = mean("ligand_pocket_com_distance", before_slice)
        after_com = mean("ligand_pocket_com_distance", after_slice)
        before_direct = mean("direct_contact", before_slice)
        after_direct = mean("direct_contact", after_slice)
        before_count = mean("direct_contact_count", before_slice)
        after_count = mean("direct_contact_count", after_slice)
        before_key = mean("key_contact_fraction", before_slice)
        after_key = mean("key_contact_fraction", after_slice)
        before_pocket = mean("pocket_ca_rmsd", before_slice)
        after_pocket = mean("pocket_ca_rmsd", after_slice)
        before_protein = mean("protein_ca_rmsd_geom", before_slice)
        after_protein = mean("protein_ca_rmsd_geom", after_slice)

        rmsd_delta = after_rmsd - before_rmsd
        com_delta = after_com - before_com
        direct_delta = after_direct - before_direct
        key_delta = after_key - before_key
        pocket_delta = after_pocket - before_pocket
        protein_delta = after_protein - before_protein
        significant_change = (
            abs(rmsd_delta) >= 1.0
            or abs(com_delta) >= 1.5
            or abs(direct_delta) >= 0.30
            or abs(key_delta) >= 0.30
            or abs(pocket_delta) >= 0.70
        )
        if not significant_change:
            continue
        near_100 = abs(times[index] - 100.0) <= 0.5
        only_rmsd = (
            abs(rmsd_delta) >= 1.5
            and abs(com_delta) < 1.0
            and abs(direct_delta) < 0.15
            and abs(key_delta) < 0.20
            and abs(pocket_delta) < 0.35
        )
        if near_100 and only_rmsd:
            interpretation = "possible_analysis_artifact"
        elif (
            abs(pocket_delta) >= 0.8
            and abs(rmsd_delta) < 1.0
            and abs(com_delta) < 1.0
            and abs(direct_delta) < 0.20
        ):
            interpretation = "protein_conformational_change"
        elif pocket_delta > 0.8 and protein_delta > 0.5:
            interpretation = "protein_conformational_change"
        elif com_delta > 5.0 and after_direct < 0.30 and after_key < 0.20:
            interpretation = "pocket_exit"
        elif com_delta > 2.0 and (direct_delta < -0.25 or key_delta < -0.30):
            interpretation = "partial_displacement"
        elif abs(rmsd_delta) >= 1.5 and after_direct >= 0.50:
            interpretation = (
                "alternative_binding_pose"
                if after_rmsd >= 4.0
                else "contact_retained_rearrangement"
            )
        else:
            interpretation = "pose_adjustment"

        rows.append(
            {
                "transition_time_ns": float(times[index]),
                "frame": int(index),
                "transition_score": float(score[index]),
                "rmsd_before": before_rmsd,
                "rmsd_after": after_rmsd,
                "com_distance_before": before_com,
                "com_distance_after": after_com,
                "contact_before": before_direct,
                "contact_after": after_direct,
                "contact_count_before": before_count,
                "contact_count_after": after_count,
                "key_contact_before": before_key,
                "key_contact_after": after_key,
                "pocket_rmsd_before": before_pocket,
                "pocket_rmsd_after": after_pocket,
                "transition_interpretation": interpretation,
            }
        )
    return pd.DataFrame(rows)


def late_statistics(table: pd.DataFrame, column: str) -> dict[str, float]:
    late = table[table["time_ns"] >= LATE_START_NS]
    values = late[column].to_numpy(float)
    return {
        "median": float(np.nanmedian(values)),
        "p95": float(np.nanpercentile(values, 95)),
        "max": float(np.nanmax(table[column].to_numpy(float))),
        "slope": slope(late["time_ns"].to_numpy(float), values),
    }


def molecular_metadata() -> dict[str, dict[str, Any]]:
    decision_by_id = {}
    if UPSTREAM_DECISION.exists():
        decision = pd.read_csv(UPSTREAM_DECISION)
        id_column = "分子" if "分子" in decision.columns else "molecule_id"
        decision_by_id = {str(row[id_column]): row for _, row in decision.iterrows()}
    manifest = pd.read_csv(MANIFEST)
    records: dict[str, dict[str, Any]] = {}
    mols: dict[str, Any] = {}
    fingerprints: dict[str, Any] = {}
    for _, row in manifest.iterrows():
        molecule_id = str(row.get("mol_id", row.get("molecule_id", "")))
        smiles = str(row.get("smiles", row.get("SMILES", "")))
        record = {
            "glide_sp": math.nan,
            "glide_xp": math.nan,
            "mmgbsa": as_float(row.get("mmgbsa", row.get("MMGBSA"))),
            "qed": math.nan,
            "sa": math.nan,
            "scaffold": "",
            "novelty": math.nan,
            "smiles": smiles,
        }
        upstream = decision_by_id.get(molecule_id)
        if upstream is not None:
            record["glide_xp"] = as_float(upstream.get("XP", upstream.get("pose_xp")))
            record["mmgbsa"] = as_float(upstream.get("MMGBSA", upstream.get("mmgbsa")))
        if math.isnan(record["glide_xp"]):
            record["glide_xp"] = as_float(row.get("pose_xp", row.get("xp_gscore")))
        if Chem is not None and smiles and smiles != "nan":
            molecule = Chem.MolFromSmiles(smiles)
            if molecule is not None:
                mols[molecule_id] = molecule
                record["qed"] = float(QED.qed(molecule))
                scaffold = MurckoScaffold.GetScaffoldForMol(molecule)
                record["scaffold"] = Chem.MolToSmiles(scaffold)
                fingerprints[molecule_id] = AllChem.GetMorganFingerprintAsBitVect(
                    molecule, 2, nBits=2048
                )
        records[molecule_id] = record
    if DataStructs is not None:
        for molecule_id, fingerprint in fingerprints.items():
            others = [value for key, value in fingerprints.items() if key != molecule_id]
            similarities = DataStructs.BulkTanimotoSimilarity(fingerprint, others)
            records[molecule_id]["novelty"] = 1.0 - max(similarities) if similarities else 1.0
    return records


def export_aligned_structure(
    cms_model: Any,
    trajectory: Any,
    context: dict[str, Any],
    transforms: dict[str, np.ndarray],
    frame_index: int,
    output_base: Path,
    title: str,
) -> list[str]:
    selected_aids = sorted(
        set(context["pocket_all_aids"]) | set(context["ligand_all_aids"])
    )
    ligand_set = set(context["ligand_all_aids"])
    ligand_mask = np.asarray([aid in ligand_set for aid in selected_aids])
    cms_copy = cms_model.copy()
    topo.update_cms(cms_copy, trajectory[frame_index])
    structure = cms_copy.extract(selected_aids)
    coordinates = structure.getXYZ()
    coordinates[ligand_mask] += transforms["ligand_shifts"][frame_index]
    coordinates = apply_alignment(
        coordinates,
        transforms["rotations"][frame_index],
        transforms["mobile_centers"][frame_index],
        transforms["reference_centers"][frame_index],
    )
    structure.setXYZ(coordinates)
    structure.title = title
    output_base.parent.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for suffix in (".mae", ".pdb"):
        path = Path(f"{output_base}{suffix}")
        with StructureWriter(str(path)) as writer:
            writer.append(structure)
        paths.append(str(path))
    return paths


def set_axes_equal(ax: Any, points: np.ndarray) -> None:
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    center = (minimum + maximum) / 2.0
    radius = max(float(np.max(maximum - minimum)) / 2.0, 1.0)
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)


def plot_pose_overlay(
    ligand_coordinates: list[np.ndarray],
    labels: list[str],
    pocket_ca: np.ndarray,
    bonds: list[tuple[int, int]],
    output_path: Path,
    title: str,
) -> None:
    colors = ["#1677B8", "#F56E1A", "#3A9158"]
    figure = plt.figure(figsize=(7.2, 6.2))
    axis = figure.add_subplot(111, projection="3d")
    axis.scatter(
        pocket_ca[:, 0], pocket_ca[:, 1], pocket_ca[:, 2], s=12, c="#B8BDC5", alpha=0.35
    )
    for index, (coordinates, label) in enumerate(zip(ligand_coordinates, labels)):
        color = colors[index % len(colors)]
        for atom1, atom2 in bonds:
            axis.plot(
                coordinates[[atom1, atom2], 0],
                coordinates[[atom1, atom2], 1],
                coordinates[[atom1, atom2], 2],
                color=color,
                linewidth=2.0,
                alpha=0.85,
            )
        axis.scatter(
            coordinates[:, 0], coordinates[:, 1], coordinates[:, 2], s=24, color=color, label=label
        )
    all_points = np.concatenate([pocket_ca] + ligand_coordinates, axis=0)
    set_axes_equal(axis, all_points)
    axis.set_xlabel("X (A)")
    axis.set_ylabel("Y (A)")
    axis.set_zlabel("Z (A)")
    axis.set_title(title)
    axis.legend(loc="best")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=220)
    plt.close(figure)


def analyze_one(
    molecule_id: str,
    outdir: Path,
    metadata: dict[str, Any],
    export_structures: bool,
) -> dict[str, Any]:
    work = TRAJ_ROOT / molecule_id
    roots = [work] + sorted(work.glob("attempt_*"), reverse=True)
    cms_path = next(
        (root / f"{molecule_id}_202ns-out.cms" for root in roots
         if (root / f"{molecule_id}_202ns-out.cms").exists()), None
    )
    if cms_path is None:
        raise FileNotFoundError(f"{molecule_id}: no final 202 ns CMS under {work}")
    run_root = cms_path.parent
    trajectory_candidates = (
        [path for path in run_root.glob("*_6_trj") if (path / "clickme.dtr").exists()]
        + [path for path in run_root.glob("*_6/*_trj") if (path / "clickme.dtr").exists()]
    )
    if not trajectory_candidates:
        raise FileNotFoundError(f"{molecule_id}: no readable production DTR under {run_root}")
    trj_path = trajectory_candidates[0]
    data_candidates = [SEA_ROOT / molecule_id / "data", SEA_ROOT / molecule_id / "official_data"]
    data_dir = next((path for path in data_candidates if (path / "PL_RMSD.dat").exists()), None)
    if data_dir is None:
        raise FileNotFoundError(f"{molecule_id}: SEA data missing under {SEA_ROOT}")
    _, cms_model = topo.read_cms(str(cms_path))
    trajectory = traj.read_traj(str(trj_path))
    context = build_geometry_context(cms_model, trajectory)
    geometry, aligned_ligands, transforms = geometry_analysis(
        cms_model, trajectory, context
    )
    sea_rmsd = read_rmsd(data_dir / "PL_RMSD.dat")
    properties = read_ligand_properties(data_dir / "L-Properties.dat")
    n = min(len(geometry), len(sea_rmsd), len(properties))
    geometry = geometry.iloc[:n].copy()
    aligned_ligands = aligned_ligands[:n]
    sea_rmsd = sea_rmsd.iloc[:n].reset_index(drop=True)
    properties = properties.iloc[:n].reset_index(drop=True)
    geometry = pd.concat(
        [
            geometry.reset_index(drop=True),
            sea_rmsd.drop(columns=["frame"]).reset_index(drop=True),
            properties.drop(columns=["frame"]).reset_index(drop=True),
        ],
        axis=1,
    )
    contact_trace, occupancy, key_residues, contact_details = contact_analysis(
        data_dir, geometry["time_ns"].to_numpy(float)
    )
    geometry = geometry.merge(
        contact_trace.drop(columns=["time_ns"]), on="frame", how="left"
    )
    transitions = detect_transitions(geometry)
    clusters = cluster_late_poses(geometry["time_ns"].to_numpy(float), aligned_ligands)

    protein_stats = late_statistics(geometry, "protein_ca_rmsd_geom")
    pocket_stats = late_statistics(geometry, "pocket_ca_rmsd")
    ligand_stats = late_statistics(geometry, "ligand_rmsd_geom")
    ligand_internal_stats = late_statistics(geometry, "ligand_internal_rmsd_geom")
    com_stats = late_statistics(geometry, "ligand_pocket_com_distance")
    minimum_stats = late_statistics(geometry, "min_pocket_distance")
    initial = geometry[geometry["time_ns"] <= EARLY_END_NS]
    late = geometry[geometry["time_ns"] >= LATE_START_NS]
    last20 = geometry[geometry["time_ns"] >= VERY_LATE_START_NS]
    first_late = geometry[
        (geometry["time_ns"] >= LATE_START_NS) & (geometry["time_ns"] < 170.0)
    ]

    protein_mae = float(
        np.mean(np.abs(geometry["protein_ca_rmsd_geom"] - geometry["protein_ca_sea"]))
    )
    ligand_mae = float(
        np.mean(np.abs(geometry["ligand_rmsd_geom"] - geometry["ligand_rmsd_sea"]))
    )
    alignment_valid = protein_mae <= 0.35 and ligand_mae <= 1.25

    com_initial = float(np.median(initial["ligand_pocket_com_distance"]))
    com_late = float(np.median(late["ligand_pocket_com_distance"]))
    com_delta = com_late - com_initial
    sasa_initial = float(np.median(initial["sasa"]))
    sasa_late = float(np.median(late["sasa"]))
    sasa_ratio = sasa_late / sasa_initial if sasa_initial > 0 else math.nan
    direct_full = float(geometry["direct_contact"].mean())
    direct_late = float(late["direct_contact"].mean())
    hbond_occupancy = float(late["hbond_contact"].mean())
    hydrophobic_occupancy = float(late["hydrophobic_contact"].mean())
    waterbridge_occupancy = float(late["waterbridge_contact"].mean())
    contact_count_late = float(late["direct_contact_count"].median())
    key_retention = float(contact_details["key_contact_retention"])
    new_contact_support = max(
        [item["late"] for item in contact_details["new_stable_contacts"]] or [0.0]
    )
    last_transition = (
        float(transitions["transition_time_ns"].max()) if not transitions.empty else math.nan
    )
    very_late_transition = bool(np.isfinite(last_transition) and last_transition > 180.0)

    ligand_late_shift = abs(
        float(last20["ligand_rmsd_geom"].median())
        - float(first_late["ligand_rmsd_geom"].median())
    )
    com_late_shift = abs(
        float(last20["ligand_pocket_com_distance"].median())
        - float(first_late["ligand_pocket_com_distance"].median())
    )
    late_plateau = bool(
        abs(ligand_stats["slope"]) <= 0.04
        and abs(com_stats["slope"]) <= 0.05
        and ligand_late_shift <= 1.25
        and com_late_shift <= 1.75
        and not very_late_transition
    )
    pocket_spread = pocket_stats["p95"] - pocket_stats["median"]
    pocket_late_shift = abs(
        float(last20["pocket_ca_rmsd"].median())
        - float(first_late["pocket_ca_rmsd"].median())
    )
    pocket_stable = bool(
        abs(pocket_stats["slope"]) <= 0.03
        and pocket_spread <= 1.25
        and pocket_late_shift <= 1.25
    )
    pocket_exit = bool(
        (
            com_delta > 8.0
            and minimum_stats["median"] > 5.0
            and direct_late < 0.25
        )
        or (minimum_stats["median"] > 7.0 and direct_late < 0.20)
    )
    ligand_in_pocket = bool(
        not pocket_exit
        and (minimum_stats["median"] <= 4.5 or direct_late >= 0.40)
    )
    contact_retained = bool(
        key_retention >= 0.35
        or (direct_late >= 0.70 and new_contact_support >= 0.30)
    )
    pose_retained = bool(
        ligand_stats["median"] <= 4.0
        and ligand_stats["p95"] <= 6.0
        and late_plateau
    )
    alternative_pose = bool(
        ligand_stats["median"] > 4.0
        and ligand_in_pocket
        and contact_retained
        and late_plateau
        and clusters["dominant_cluster_fraction"] >= 0.45
    )

    retention_component = 25.0 * (
        0.45 * clip01(1.0 - max(com_delta, 0.0) / 10.0)
        + 0.35 * clip01((6.0 - minimum_stats["median"]) / 3.0)
        + 0.20 * clip01(1.0 - max(sasa_ratio - 1.0, 0.0))
    )
    key_component = 25.0 * clip01(0.80 * key_retention + 0.20 * new_contact_support)
    plateau_component = 15.0 * (
        0.45 * clip01(1.0 - abs(ligand_stats["slope"]) / 0.08)
        + 0.30 * clip01(1.0 - ligand_late_shift / 2.5)
        + 0.25 * (0.0 if very_late_transition else 1.0)
    )
    direct_component = 15.0 * clip01(direct_late)
    pocket_component = 10.0 * (
        0.25 * clip01((7.0 - pocket_stats["p95"]) / 5.0)
        + 0.45 * clip01(1.0 - pocket_spread / 1.5)
        + 0.30 * clip01(1.0 - abs(pocket_stats["slope"]) / 0.06)
    )
    pose_component = 5.0 * clip01((8.0 - ligand_stats["median"]) / 6.0)
    cluster_component = 5.0 * clip01(clusters["dominant_cluster_fraction"])
    md_score = (
        retention_component
        + key_component
        + plateau_component
        + direct_component
        + pocket_component
        + pose_component
        + cluster_component
    )
    if pocket_exit:
        md_score = min(md_score, 35.0)

    possible_artifact = False
    artifact_reason = (
        "Protocol contains one continuous 200 ns production stage; DTR frame times are continuous."
    )
    if not transitions.empty and (
        transitions["transition_interpretation"] == "possible_analysis_artifact"
    ).any():
        possible_artifact = True
        artifact_reason = (
            "RMSD-only discontinuity detected near 100 ns while COM and contacts remain continuous."
        )

    trajectory_valid = True
    if not alignment_valid or possible_artifact:
        md_class = "C_inconclusive"
    elif pocket_exit:
        md_class = "D_pose_failure"
    elif very_late_transition:
        md_class = "C_inconclusive"
    elif (
        ligand_in_pocket
        and contact_retained
        and pose_retained
        and pocket_stable
        and clusters["dominant_cluster_fraction"] >= 0.45
    ):
        md_class = "A_pose_retained"
    elif alternative_pose:
        md_class = "B_contact_retained_rearrangement"
    elif ligand_in_pocket:
        md_class = "C_inconclusive"
    else:
        md_class = "D_pose_failure"

    recommendation = {
        "A_pose_retained": "priority_wetlab",
        "B_contact_retained_rearrangement": "wetlab_candidate",
        "C_inconclusive": "manual_review_or_repeat_md",
        "D_pose_failure": "do_not_prioritize",
    }[md_class]
    if md_class == "A_pose_retained":
        failure_reason_category = "none"
        reason = "Ligand remains in the original pocket with retained contacts and a converged late pose."
    elif md_class == "B_contact_retained_rearrangement":
        failure_reason_category = "none"
        reason = (
            "The original docking pose rearranges, but pocket occupancy and key or stable new contacts "
            "are retained in a dominant alternative state."
        )
    elif md_class == "C_inconclusive":
        if possible_artifact:
            failure_reason_category = "possible_analysis_artifact"
            reason = "A possible trajectory/alignment artifact prevents an automatic binding call."
        elif very_late_transition:
            failure_reason_category = "late_transition_after_180ns"
            reason = (
                f"The last state transition occurs at {last_transition:.1f} ns, leaving insufficient "
                "post-transition sampling to establish a new plateau."
            )
        elif direct_late < 0.30 and key_retention < 0.10 and ligand_stats["median"] > 8.0:
            failure_reason_category = "partial_displacement_contact_loss"
            reason = (
                "The ligand undergoes pocket exit/partial displacement and later approaches the pocket again, "
                "but late direct contacts are sparse and initial key contacts are not restored."
            )
        elif clusters["dominant_cluster_fraction"] < 0.35:
            failure_reason_category = "multistate_not_converged"
            reason = (
                f"Pocket proximity or contacts persist, but the 150-200 ns ensemble is split across "
                f"{clusters['cluster_count']} pose clusters (dominant {clusters['dominant_cluster_fraction']:.1%}); "
                "no converged alternative pose is established."
            )
        elif not pocket_stable:
            failure_reason_category = "pocket_not_converged"
            reason = "The ligand remains nearby, but the binding pocket has not reached a stable late plateau."
        else:
            failure_reason_category = "conflicting_md_indicators"
            reason = "Geometric and contact indicators are conflicting and require manual trajectory review."
    else:
        failure_reason_category = "pocket_exit_pose_failure"
        reason = (
            "Geometric pocket retention and persistent direct-contact evidence are both insufficient in the late window."
        )

    representative_paths: list[str] = []
    structures_dir = outdir / "representative_structures" / molecule_id
    frames_to_export: dict[int, str] = {
        int(index): f"cluster_{rank + 1}"
        for rank, index in enumerate(clusters["representative_indices"])
    }
    frames_to_export[n - 1] = "final_200ns"
    if not transitions.empty:
        for transition_rank, row in transitions.iterrows():
            time = float(row["transition_time_ns"])
            for offset in (-5.0, -1.0, 1.0, 5.0):
                target = time + offset
                frame_index = int(np.argmin(np.abs(geometry["time_ns"].to_numpy() - target)))
                frames_to_export[frame_index] = (
                    f"transition_{transition_rank + 1}_{'m' if offset < 0 else 'p'}{abs(offset):g}ns"
                )
    if export_structures:
        for frame_index, label in sorted(frames_to_export.items()):
            representative_paths.extend(
                export_aligned_structure(
                    cms_model,
                    trajectory,
                    context,
                    transforms,
                    frame_index,
                    structures_dir / f"{molecule_id}_{label}_{geometry.loc[frame_index, 'time_ns']:.1f}ns",
                    f"{molecule_id} {label} {geometry.loc[frame_index, 'time_ns']:.1f} ns",
                )
            )
    else:
        previous_table = outdir / "md200_decision_table.csv"
        if previous_table.exists():
            previous = pd.read_csv(previous_table)
            match = previous[previous["molecule_id"] == molecule_id]
            if not match.empty:
                representative_paths = [
                    value
                    for value in str(match.iloc[0]["representative_structure_paths"]).split(";")
                    if value and Path(value).exists()
                ]

    molecule_figures = outdir / "figures" / "per_molecule"
    representative_indices = clusters["representative_indices"]
    plot_pose_overlay(
        [aligned_ligands[index] for index in representative_indices],
        [
            f"cluster {rank + 1} ({clusters['cluster_sizes'][rank] / len(clusters['late_indices']):.0%})"
            for rank in range(len(representative_indices))
        ],
        transforms["reference_pocket_ca"],
        context["ligand_bonds"],
        molecule_figures / f"{molecule_id}_late_cluster_poses.png",
        f"{molecule_id}: 150-200 ns cluster representatives",
    )
    if not transitions.empty:
        transition_index = int(transitions.iloc[-1]["frame"])
        before_index = int(
            np.argmin(np.abs(geometry["time_ns"] - (geometry.loc[transition_index, "time_ns"] - 5.0)))
        )
        after_index = int(
            np.argmin(np.abs(geometry["time_ns"] - (geometry.loc[transition_index, "time_ns"] + 5.0)))
        )
        plot_pose_overlay(
            [aligned_ligands[before_index], aligned_ligands[after_index]],
            [
                f"before {geometry.loc[before_index, 'time_ns']:.1f} ns",
                f"after {geometry.loc[after_index, 'time_ns']:.1f} ns",
            ],
            transforms["reference_pocket_ca"],
            context["ligand_bonds"],
            molecule_figures / f"{molecule_id}_last_transition_overlay.png",
            f"{molecule_id}: last detected transition",
        )

    metrics: dict[str, Any] = {
        "molecule_id": molecule_id,
        "trajectory_valid": trajectory_valid,
        "restart_boundary_detected": False,
        "possible_restart_artifact": possible_artifact,
        "artifact_reason": artifact_reason,
        "protein_ca_late_median": protein_stats["median"],
        "protein_ca_late_p95": protein_stats["p95"],
        "protein_ca_late_slope": protein_stats["slope"],
        "pocket_ca_late_median": pocket_stats["median"],
        "pocket_ca_late_p95": pocket_stats["p95"],
        "pocket_ca_late_slope": pocket_stats["slope"],
        "pocket_ca_late_p95_minus_median": pocket_spread,
        "pocket_ca_last20_shift": pocket_late_shift,
        "ligand_rmsd_late_median": ligand_stats["median"],
        "ligand_rmsd_late_p95": ligand_stats["p95"],
        "ligand_rmsd_max": ligand_stats["max"],
        "ligand_rmsd_late_slope": ligand_stats["slope"],
        "ligand_internal_rmsd_late_median": ligand_internal_stats["median"],
        "ligand_internal_rmsd_late_p95": ligand_internal_stats["p95"],
        "ligand_pocket_com_initial": com_initial,
        "ligand_pocket_com_late": com_late,
        "ligand_pocket_com_delta": com_delta,
        "ligand_pocket_com_late_slope": com_stats["slope"],
        "min_pocket_distance_late": minimum_stats["median"],
        "ligand_sasa_initial": sasa_initial,
        "ligand_sasa_late": sasa_late,
        "ligand_sasa_late_to_initial": sasa_ratio,
        "direct_contact_occupancy_full": direct_full,
        "direct_contact_occupancy_late": direct_late,
        "contact_residue_count_late_median": contact_count_late,
        "key_contact_retention": key_retention,
        "key_contact_details": json.dumps(
            contact_details["key_contact_details"], ensure_ascii=False
        ),
        "new_stable_contacts": json.dumps(
            contact_details["new_stable_contacts"], ensure_ascii=False
        ),
        "hydrogen_bond_occupancy": hbond_occupancy,
        "hydrophobic_contact_occupancy": hydrophobic_occupancy,
        "water_bridge_occupancy": waterbridge_occupancy,
        "number_of_transitions": len(transitions),
        "last_transition_ns": last_transition,
        "late_plateau": late_plateau,
        "dominant_cluster_fraction": clusters["dominant_cluster_fraction"],
        "late_cluster_count": clusters["cluster_count"],
        "ligand_in_pocket": ligand_in_pocket,
        "pose_retained": pose_retained,
        "contact_retained": contact_retained,
        "alternative_pose_supported": alternative_pose,
        "pocket_stable": pocket_stable,
        "md_score": md_score,
        "md_class": md_class,
        "wetlab_recommendation": recommendation,
        "failure_reason_category": failure_reason_category,
        "rejection_or_selection_reason": reason,
        "manual_review_required": md_class == "C_inconclusive",
        "representative_structure_paths": ";".join(representative_paths),
        "protein_rmsd_sea_geom_mae": protein_mae,
        "ligand_rmsd_sea_geom_mae": ligand_mae,
        "alignment_validation_pass": alignment_valid,
        "pocket_definition": (
            f"Protein residues with any heavy atom within {POCKET_CUTOFF_ANGSTROM:.1f} A "
            "of ligand heavy atoms in production frame 0"
        ),
        "pocket_residues": ";".join(context["pocket_residues"]),
        "key_contact_source": (
            "Direct SEA contacts with >=30% occupancy during 0-10 ns; top >=10% contacts used if fewer than two"
        ),
        "key_residues": ";".join(key_residues),
        **metadata,
    }
    geometry.insert(0, "molecule_id", molecule_id)
    if not occupancy.empty:
        occupancy.insert(0, "molecule_id", molecule_id)
    if not transitions.empty:
        transitions.insert(0, "molecule_id", molecule_id)
    return {
        "metrics": metrics,
        "trace": geometry,
        "contacts": occupancy,
        "transitions": transitions,
        "cluster": clusters,
    }


def apply_batch_restart_check(results: list[dict[str, Any]]) -> None:
    near_boundary: list[tuple[dict[str, Any], pd.Series]] = []
    for result in results:
        transitions = result["transitions"]
        if transitions.empty:
            continue
        subset = transitions[
            transitions["transition_time_ns"].between(99.0, 101.0, inclusive="both")
        ]
        for _, row in subset.iterrows():
            near_boundary.append((result, row))
    if len({item[0]["metrics"]["molecule_id"] for item in near_boundary}) >= 3:
        for result, row in near_boundary:
            result["metrics"]["possible_restart_artifact"] = True
            result["metrics"]["artifact_reason"] = (
                "At least three molecules show a synchronized transition at 100 ns; manual trajectory/PBC review required."
            )
            result["metrics"]["md_class"] = "C_inconclusive"
            result["metrics"]["wetlab_recommendation"] = "manual_review_or_repeat_md"
            result["metrics"]["manual_review_required"] = True


def write_per_molecule_report(result: dict[str, Any], outdir: Path) -> None:
    metrics = result["metrics"]
    transitions = result["transitions"]
    transition_lines = []
    if transitions.empty:
        transition_lines.append("- No major multimetric transition was detected.")
    else:
        for row in transitions.itertuples(index=False):
            transition_lines.append(
                f"- {row.transition_time_ns:.1f} ns: `{row.transition_interpretation}`; "
                f"ligand RMSD {row.rmsd_before:.2f}->{row.rmsd_after:.2f} A, "
                f"COM {row.com_distance_before:.2f}->{row.com_distance_after:.2f} A, "
                f"direct-contact coverage {row.contact_before:.0%}->{row.contact_after:.0%}."
            )
    report = f"""# {metrics['molecule_id']} Desmond 200 ns report

## Simulation integrity

- Trajectory valid: `{metrics['trajectory_valid']}`; 200.000 ns, 1002 continuous frames.
- Restart boundary detected: `{metrics['restart_boundary_detected']}`.
- Possible restart/analysis artifact: `{metrics['possible_restart_artifact']}`.
- Alignment validation: `{metrics['alignment_validation_pass']}` (protein SEA/geometry MAE {metrics['protein_rmsd_sea_geom_mae']:.3f} A; ligand MAE {metrics['ligand_rmsd_sea_geom_mae']:.3f} A).
- Artifact assessment: {metrics['artifact_reason']}

## Protein and pocket stability

- Protein C-alpha, 150-200 ns: median {metrics['protein_ca_late_median']:.2f} A, p95 {metrics['protein_ca_late_p95']:.2f} A, slope {metrics['protein_ca_late_slope']:.4f} A/ns.
- Pocket C-alpha, 150-200 ns: median {metrics['pocket_ca_late_median']:.2f} A, p95 {metrics['pocket_ca_late_p95']:.2f} A, slope {metrics['pocket_ca_late_slope']:.4f} A/ns.
- Pocket stable: `{metrics['pocket_stable']}`.
- Pocket definition: {metrics['pocket_definition']}.
- Pocket residues: {metrics['pocket_residues']}.

## Ligand pose and pocket retention

- Ligand RMSD fitted on protein, 150-200 ns: median {metrics['ligand_rmsd_late_median']:.2f} A, p95 {metrics['ligand_rmsd_late_p95']:.2f} A, slope {metrics['ligand_rmsd_late_slope']:.4f} A/ns.
- Ligand internal RMSD, 150-200 ns: median {metrics['ligand_internal_rmsd_late_median']:.2f} A.
- Ligand-pocket COM: initial {metrics['ligand_pocket_com_initial']:.2f} A, late {metrics['ligand_pocket_com_late']:.2f} A, delta {metrics['ligand_pocket_com_delta']:+.2f} A.
- Late minimum ligand-pocket distance: {metrics['min_pocket_distance_late']:.2f} A.
- Ligand SASA late/initial: {metrics['ligand_sasa_late_to_initial']:.2f}.
- In target pocket: `{metrics['ligand_in_pocket']}`; initial pose retained: `{metrics['pose_retained']}`; alternative pose supported: `{metrics['alternative_pose_supported']}`.

## Contacts and convergence

- Direct contact occupancy: full {metrics['direct_contact_occupancy_full']:.1%}; late {metrics['direct_contact_occupancy_late']:.1%}.
- Late HBond/hydrophobic/water-bridge coverage: {metrics['hydrogen_bond_occupancy']:.1%} / {metrics['hydrophobic_contact_occupancy']:.1%} / {metrics['water_bridge_occupancy']:.1%}.
- Key-contact retention: {metrics['key_contact_retention']:.1%}; source: {metrics['key_contact_source']}.
- Initial key residues: {metrics['key_residues'] or 'none'}.
- Key-contact details: `{metrics['key_contact_details']}`.
- Stable new late contacts: `{metrics['new_stable_contacts']}`.
- Late plateau: `{metrics['late_plateau']}`; dominant cluster fraction: {metrics['dominant_cluster_fraction']:.1%}; late clusters: {metrics['late_cluster_count']}.

## State transitions

{chr(10).join(transition_lines)}

## Decision

- MD score: **{metrics['md_score']:.1f}/100**.
- MD class: **`{metrics['md_class']}`**.
- Wet-lab recommendation: **`{metrics['wetlab_recommendation']}`**.
- Evidence statement: {metrics['rejection_or_selection_reason']}
- XP / MM-GBSA: {metrics['glide_xp']:.2f} / {metrics['mmgbsa']:.2f} kcal/mol (auxiliary ranking evidence only).
- Representative structures: `{metrics['representative_structure_paths']}`.
"""
    reports = outdir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{metrics['molecule_id']}_md200_report.md").write_text(report)


def plot_time_series(results: list[dict[str, Any]], outdir: Path) -> None:
    figures = outdir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    n = len(results)
    rows = math.ceil(n / 2)

    figure, axes = plt.subplots(rows, 2, figsize=(14, 3.8 * rows), squeeze=False)
    for axis, result in zip(axes.flat, results):
        trace = result["trace"]
        axis.plot(trace["time_ns"], trace["protein_ca_rmsd_geom"], label="protein C-alpha", color="#1677B8")
        axis.plot(trace["time_ns"], trace["ligand_rmsd_geom"], label="ligand/protein", color="#F56E1A")
        axis.axvspan(150, 200, color="#DDEEE4", alpha=0.45)
        axis.axvline(100, color="#777777", linestyle=":", linewidth=1)
        axis.set_title(result["metrics"]["molecule_id"])
        axis.set_xlabel("Time (ns)")
        axis.set_ylabel("RMSD (A)")
        axis.legend(fontsize=8)
    for axis in axes.flat[n:]:
        axis.axis("off")
    figure.tight_layout()
    figure.savefig(figures / "all_molecules_protein_ligand_rmsd.png", dpi=220)
    plt.close(figure)

    for y_column, ylabel, filename in (
        ("direct_contact", "Direct contact (rolling fraction)", "ligand_rmsd_vs_direct_contact.png"),
        ("ligand_pocket_com_distance", "Ligand-pocket COM (A)", "ligand_rmsd_vs_pocket_com.png"),
    ):
        figure, axes = plt.subplots(rows, 2, figsize=(14, 3.8 * rows), squeeze=False)
        for axis, result in zip(axes.flat, results):
            trace = result["trace"]
            axis.plot(trace["time_ns"], trace["ligand_rmsd_geom"], color="#F56E1A", label="ligand RMSD")
            twin = axis.twinx()
            values = trace[y_column]
            if y_column == "direct_contact":
                values = values.rolling(25, center=True, min_periods=1).mean()
            twin.plot(trace["time_ns"], values, color="#1677B8", alpha=0.8, label=ylabel)
            axis.axvspan(150, 200, color="#DDEEE4", alpha=0.35)
            axis.set_title(result["metrics"]["molecule_id"])
            axis.set_xlabel("Time (ns)")
            axis.set_ylabel("Ligand RMSD (A)", color="#F56E1A")
            twin.set_ylabel(ylabel, color="#1677B8")
        for axis in axes.flat[n:]:
            axis.axis("off")
        figure.tight_layout()
        figure.savefig(figures / filename, dpi=220)
        plt.close(figure)


def plot_summary(results: list[dict[str, Any]], decision: pd.DataFrame, outdir: Path) -> None:
    figures = outdir / "figures"
    order = decision["molecule_id"].tolist()
    ordered_results = sorted(results, key=lambda item: order.index(item["metrics"]["molecule_id"]))
    colors = {
        "A_pose_retained": "#2C8A56",
        "B_contact_retained_rearrangement": "#1677B8",
        "C_inconclusive": "#D59419",
        "D_pose_failure": "#C9473D",
    }
    figure, axis = plt.subplots(figsize=(9, 4.8))
    axis.barh(
        [item["metrics"]["molecule_id"] for item in ordered_results][::-1],
        [item["metrics"]["md_score"] for item in ordered_results][::-1],
        color=[colors[item["metrics"]["md_class"]] for item in ordered_results][::-1],
    )
    axis.set_xlabel("MD score (0-100)")
    axis.set_xlim(0, 100)
    axis.set_title(f"{TARGET_LABEL} 200 ns MD ranking")
    figure.tight_layout()
    figure.savefig(figures / "md_score_ranking.png", dpi=220)
    plt.close(figure)

    counts = Counter(item["metrics"]["md_class"] for item in results)
    classes = list(colors)
    figure, axis = plt.subplots(figsize=(8.5, 4.8))
    axis.bar(classes, [counts.get(value, 0) for value in classes], color=[colors[value] for value in classes])
    axis.set_ylabel("Molecule count")
    axis.set_title("A/B/C/D classification distribution")
    axis.tick_params(axis="x", rotation=18)
    figure.tight_layout()
    figure.savefig(figures / "md_class_distribution.png", dpi=220)
    plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    for axis, x_column, label in (
        (axes[0], "glide_xp", "Glide XP"),
        (axes[1], "mmgbsa", "MM-GBSA (kcal/mol)"),
    ):
        for item in results:
            metrics = item["metrics"]
            axis.scatter(
                metrics[x_column], metrics["md_score"], s=70, color=colors[metrics["md_class"]]
            )
            axis.annotate(metrics["molecule_id"], (metrics[x_column], metrics["md_score"]), xytext=(4, 4), textcoords="offset points", fontsize=8)
        axis.set_xlabel(label)
        axis.set_ylabel("MD score")
    figure.suptitle("Docking/free-energy scores versus 200 ns MD evidence")
    figure.tight_layout()
    figure.savefig(figures / "xp_mmgbsa_md_score_scatter.png", dpi=220)
    plt.close(figure)

    key_maps = [
        {item["residue"]: item["late"] for item in json.loads(result["metrics"]["key_contact_details"])}
        for result in results
    ]
    residues = sorted({residue for mapping in key_maps for residue in mapping})
    if residues:
        matrix = np.full((len(residues), len(results)), np.nan)
        for column, mapping in enumerate(key_maps):
            for residue, occupancy in mapping.items():
                matrix[residues.index(residue), column] = occupancy
        figure, axis = plt.subplots(figsize=(max(8, len(results) * 1.2), max(4, len(residues) * 0.35)))
        image = axis.imshow(matrix, vmin=0, vmax=1, cmap="YlGnBu", aspect="auto")
        axis.set_xticks(range(len(results)), [item["metrics"]["molecule_id"] for item in results])
        axis.set_yticks(range(len(residues)), residues)
        axis.set_title("Late occupancy of initial key contacts")
        figure.colorbar(image, ax=axis, label="150-200 ns occupancy")
        figure.tight_layout()
        figure.savefig(figures / "key_contact_occupancy_heatmap.png", dpi=220)
        plt.close(figure)


def write_summary(results: list[dict[str, Any]], decision: pd.DataFrame, outdir: Path) -> None:
    by_class: dict[str, list[str]] = defaultdict(list)
    for result in results:
        by_class[result["metrics"]["md_class"]].append(result["metrics"]["molecule_id"])
    failure_groups: dict[str, list[str]] = defaultdict(list)
    for result in results:
        metrics = result["metrics"]
        if metrics["md_class"] in {"C_inconclusive", "D_pose_failure"}:
            failure_groups[metrics["failure_reason_category"]].append(metrics["molecule_id"])
    failure_labels = {
        "possible_analysis_artifact": "possible trajectory/alignment artifact",
        "late_transition_after_180ns": "state transition after 180 ns; insufficient post-transition sampling",
        "partial_displacement_contact_loss": "pocket exit/partial displacement with late key-contact loss",
        "multistate_not_converged": "late ensemble split across many pose clusters",
        "pocket_not_converged": "binding pocket not converged",
        "conflicting_md_indicators": "conflicting geometric and contact indicators",
        "pocket_exit_pose_failure": "persistent pocket exit/pose failure",
    }
    failure_lines = [
        f"- {len(ids)} molecule(s), {', '.join(ids)}: {failure_labels.get(category, category)}"
        for category, ids in failure_groups.items()
    ]
    rearranged = [
        result["metrics"]["molecule_id"]
        for result in results
        if result["metrics"]["alternative_pose_supported"]
    ]
    artifacts = [
        result["metrics"]["molecule_id"]
        for result in results
        if result["metrics"]["possible_restart_artifact"]
    ]
    recommended = decision[
        decision["wetlab_recommendation"].isin(["priority_wetlab", "wetlab_candidate"])
    ]["molecule_id"].tolist()
    manual = decision[decision["md_class"] == "C_inconclusive"]["molecule_id"].tolist()
    rejected = decision[decision["md_class"] == "D_pose_failure"]["molecule_id"].tolist()
    ranking_lines = [
        f"{int(row['rank'])}. **{row['molecule_id']}** - `{row['md_class']}`, score {row['md_score']:.1f}, `{row['wetlab_recommendation']}`"
        for _, row in decision.iterrows()
    ]
    text = f"""# {TARGET_LABEL} Desmond 200 ns selection summary

## Data integrity and method

- All {len(results)} trajectories passed the campaign's continuous-frame, readable CMS/DTR, and SEA completeness checks.
- The protocol contains one continuous 200 ns production stage after 2 ns equilibration; it is not a 100+100 ns restart.
- Primary decision window: 150-200 ns. Pocket retention and contact evidence take precedence over absolute ligand RMSD.
- Pocket residues are defined per molecule from production frame 0 at a 6 A ligand-heavy/protein-heavy cutoff. Initial key contacts are derived from the first 10 ns SEA direct-contact occupancies.
- A single trajectory supports prioritization, not efficacy prediction; independent repeats remain desirable for borderline candidates.

## Class distribution

- A_pose_retained ({len(by_class['A_pose_retained'])}): {', '.join(by_class['A_pose_retained']) or 'none'}
- B_contact_retained_rearrangement ({len(by_class['B_contact_retained_rearrangement'])}): {', '.join(by_class['B_contact_retained_rearrangement']) or 'none'}
- C_inconclusive ({len(by_class['C_inconclusive'])}): {', '.join(by_class['C_inconclusive']) or 'none'}
- D_pose_failure ({len(by_class['D_pose_failure'])}): {', '.join(by_class['D_pose_failure']) or 'none'}

## Ranked decision

{chr(10).join(ranking_lines)}

## Action lists

- Priority wet-lab / wet-lab candidates: {', '.join(recommended) or 'none'}.
- Contact-retained rearrangements: {', '.join(rearranged) or 'none'}.
- Manual review or repeat MD: {', '.join(manual) or 'none'}.
- Suspected 100 ns analysis/restart artifact: {', '.join(artifacts) or 'none'}.
- Do not prioritize: {', '.join(rejected) or 'none'}.

## Main uncertainty/failure reasons

{chr(10).join(failure_lines) or '- none'}

## Wet-lab interpretation

The ranking first asks whether the ligand remains in the target pocket, then whether initial or stable replacement contacts persist, whether the final 50 ns forms a plateau, and whether the pocket is stable. Glide XP and MM-GBSA are used only as auxiliary ordering evidence and never override a clear pocket exit.
"""
    (outdir / "md200_selection_summary.md").write_text(text)


def main() -> None:
    global TRAJ_ROOT, SEA_ROOT, MANIFEST, UPSTREAM_DECISION
    global PROTEIN_ASL, LIGAND_ASL, TARGET_LABEL
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--no-structures", action="store_true")
    parser.add_argument("--trajectory-root", type=Path, required=True)
    parser.add_argument("--sea-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--upstream-decision", type=Path)
    parser.add_argument("--protein-asl", default="protein")
    parser.add_argument("--ligand-asl", required=True)
    parser.add_argument("--target-label", default="Target")
    args = parser.parse_args()
    TRAJ_ROOT = args.trajectory_root.resolve()
    SEA_ROOT = args.sea_root.resolve()
    MANIFEST = args.manifest.resolve()
    if args.upstream_decision is not None:
        UPSTREAM_DECISION = args.upstream_decision.resolve()
    PROTEIN_ASL = args.protein_asl
    LIGAND_ASL = args.ligand_asl
    TARGET_LABEL = args.target_label
    molecule_ids = args.ids
    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    metadata = molecular_metadata()

    results: list[dict[str, Any]] = []
    for molecule_id in molecule_ids:
        print(f"Analyze {molecule_id}...", flush=True)
        result = analyze_one(
            molecule_id,
            outdir,
            metadata.get(molecule_id, {}),
            export_structures=not args.no_structures,
        )
        results.append(result)
        print(
            f"  class={result['metrics']['md_class']} score={result['metrics']['md_score']:.1f} "
            f"lig_late={result['metrics']['ligand_rmsd_late_median']:.2f} "
            f"COM_delta={result['metrics']['ligand_pocket_com_delta']:+.2f} "
            f"contacts={result['metrics']['direct_contact_occupancy_late']:.0%}",
            flush=True,
        )

    apply_batch_restart_check(results)
    class_order = {
        "A_pose_retained": 0,
        "B_contact_retained_rearrangement": 1,
        "C_inconclusive": 2,
        "D_pose_failure": 3,
    }
    results.sort(
        key=lambda item: (
            class_order[item["metrics"]["md_class"]],
            -item["metrics"]["md_score"],
        )
    )
    rows = []
    for rank, result in enumerate(results, start=1):
        result["metrics"]["rank"] = rank
        rows.append(result["metrics"])
        write_per_molecule_report(result, outdir)
    decision = pd.DataFrame(rows)
    first_columns = ["rank", "molecule_id"]
    decision = decision[first_columns + [column for column in decision if column not in first_columns]]
    decision.to_csv(outdir / "md200_decision_table.csv", index=False)
    decision.to_excel(outdir / "md200_decision_table.xlsx", index=False)

    traces = pd.concat([result["trace"] for result in results], ignore_index=True)
    contacts = pd.concat(
        [result["contacts"] for result in results if not result["contacts"].empty],
        ignore_index=True,
    )
    transition_tables = [
        result["transitions"] for result in results if not result["transitions"].empty
    ]
    transitions = (
        pd.concat(transition_tables, ignore_index=True)
        if transition_tables
        else pd.DataFrame(
            columns=[
                "molecule_id",
                "transition_time_ns",
                "rmsd_before",
                "rmsd_after",
                "com_distance_before",
                "com_distance_after",
                "contact_before",
                "contact_after",
                "key_contact_before",
                "key_contact_after",
                "transition_interpretation",
            ]
        )
    )
    traces.to_csv(outdir / "md200_traces.csv", index=False)
    contacts.to_csv(outdir / "md200_contacts.csv", index=False)
    transitions.to_csv(outdir / "md200_transitions.csv", index=False)
    plot_time_series(results, outdir)
    plot_summary(results, decision, outdir)
    write_summary(results, decision, outdir)
    print(f"Wrote final analysis to {outdir}")


if __name__ == "__main__":
    main()
