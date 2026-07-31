#!/usr/bin/env python3
"""Extract clash-checked full-system CMS inputs from late-trajectory pose medoids."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist, squareform
from schrodinger.application.desmond.packages import topo, traj


FF_TABLES = (
    "site",
    "bond",
    "angle",
    "dihedral",
    "exclusion",
    "pair",
    "constraint",
    "vdwtype",
    "vdwtypescombined",
    "pseudo",
    "virtual",
    "restraint",
    "stretchfbhw",
    "anglefbhw",
    "improperfbhw",
    "posfbhw",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--ligand-asl", required=True)
    parser.add_argument("--pocket-asl", help="Global pocket ASL if input CSV lacks pocket_asl")
    parser.add_argument("--late-start-ns", type=float, default=40.0)
    parser.add_argument("--cluster-cutoff-a", type=float, default=2.0)
    parser.add_argument("--clash-cutoff-a", type=float, default=1.5)
    parser.add_argument("--maximum-pocket-min-a", type=float, default=4.0)
    parser.add_argument("--time-tolerance-ns", type=float, default=0.201)
    parser.add_argument("--fraction-tolerance", type=float, default=0.011)
    return parser.parse_args()


def minimum_image(delta: np.ndarray, box: np.ndarray) -> np.ndarray:
    shape = np.asarray(delta).shape
    flat = np.asarray(delta, dtype=float).reshape(-1, 3)
    fractional = flat @ np.linalg.inv(np.asarray(box, dtype=float))
    fractional -= np.round(fractional)
    return (fractional @ box).reshape(shape)


def unwrap_group(coordinates: np.ndarray, box: np.ndarray) -> np.ndarray:
    coordinates = np.asarray(coordinates, dtype=float)
    if len(coordinates) < 2:
        return coordinates.copy()
    return coordinates[0] + minimum_image(coordinates - coordinates[0], box)


def kabsch(mobile: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mobile_center = mobile.mean(axis=0)
    reference_center = reference.mean(axis=0)
    u, _, vt = np.linalg.svd((mobile - mobile_center).T @ (reference - reference_center))
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    return rotation, mobile_center, reference_center


def align(coordinates: np.ndarray, fit: tuple[np.ndarray, np.ndarray, np.ndarray]) -> np.ndarray:
    rotation, mobile_center, reference_center = fit
    return (coordinates - mobile_center) @ rotation + reference_center


def pbc_distances(first: np.ndarray, second: np.ndarray, box: np.ndarray) -> np.ndarray:
    delta = first[:, None, :] - second[None, :, :]
    return np.sqrt(np.sum(minimum_image(delta, box) ** 2, axis=2))


def stable(value: object) -> object:
    return round(value, 8) if isinstance(value, float) else value


def semantic_properties(properties: object) -> list[tuple[str, object]]:
    return sorted(
        (key, stable(value))
        for key, value in properties.items()
        if not key.endswith(("_x_coord", "_y_coord", "_z_coord")) and "velocity" not in key
    )


def forcefield_fingerprint(cms: object) -> str:
    records = []
    for index, component in enumerate(cms.comp_ct):
        forcefield = component.ffio
        record = {
            "index": index,
            "title": component.title,
            "atoms": len(component.atom),
            "ct_type": component.property.get("s_ffio_ct_type"),
            "combining_rule": forcefield.combining_rule,
            "name": forcefield.name,
            "version": forcefield.version,
            "property": semantic_properties(forcefield.property),
            "tables": {},
        }
        for name in FF_TABLES:
            record["tables"][name] = [semantic_properties(item.property) for item in getattr(forcefield, name)]
        records.append(record)
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def topology_signature(cms: object) -> dict:
    atoms = [
        (
            atom.index,
            atom.atomic_number,
            atom.formal_charge,
            atom.chain.strip(),
            int(atom.resnum),
            atom.inscode.strip(),
            atom.pdbres.strip(),
            atom.pdbname.strip(),
        )
        for atom in cms.atom
    ]
    return {
        "atom_total": int(cms.atom_total),
        "component_count": len(cms.comp_ct),
        "formal_charge": int(sum(atom.formal_charge for atom in cms.atom)),
        "atom_identity_sha256": hashlib.sha256(repr(atoms).encode()).hexdigest(),
        "forcefield_sha256": forcefield_fingerprint(cms),
    }


def pose_medoid(
    cms: object,
    frames: list,
    ligand_heavy_aids: list[int],
    pocket_ca_aids: list[int],
    late_start_ns: float,
    cluster_cutoff: float,
) -> dict:
    late_indices = [index for index, frame in enumerate(frames) if frame.time >= late_start_ns * 1000.0]
    if len(late_indices) < 2:
        raise RuntimeError(f"only {len(late_indices)} frame(s) at or after {late_start_ns} ns")
    ligand_gids = topo.aids2gids(cms, ligand_heavy_aids, include_pseudoatoms=False)
    pocket_ca_gids = topo.aids2gids(cms, pocket_ca_aids, include_pseudoatoms=False)
    reference_ca = None
    aligned_ligands = []
    for index in late_indices:
        frame = frames[index]
        box = np.asarray(frame.box, dtype=float)
        pocket_ca = unwrap_group(frame.pos(pocket_ca_gids), box)
        ligand = unwrap_group(frame.pos(ligand_gids), box)
        displacement = ligand.mean(axis=0) - pocket_ca.mean(axis=0)
        ligand += minimum_image(displacement, box) - displacement
        if reference_ca is None:
            reference_ca = pocket_ca.copy()
        aligned_ligands.append(align(ligand, kabsch(pocket_ca, reference_ca)))
    coordinates = np.asarray(aligned_ligands)
    condensed = pdist(coordinates.reshape(len(coordinates), -1)) / np.sqrt(len(ligand_gids))
    labels = fcluster(linkage(condensed, method="average"), t=cluster_cutoff, criterion="distance")
    counts = Counter(labels)
    dominant = max(counts, key=counts.get)
    members = np.where(labels == dominant)[0]
    distances = squareform(condensed)
    medoid_local = int(members[np.argmin(distances[np.ix_(members, members)].mean(axis=1))])
    return {
        "frame_index": late_indices[medoid_local],
        "time_ns": float(frames[late_indices[medoid_local]].time / 1000.0),
        "dominant_cluster_count": int(counts[dominant]),
        "late_frame_count": len(late_indices),
        "dominant_cluster_fraction": float(counts[dominant] / len(late_indices)),
    }


def optional_float(row: pd.Series, name: str) -> float | None:
    value = row.get(name)
    return None if value is None or pd.isna(value) else float(value)


def process_one(args: argparse.Namespace, row: pd.Series) -> dict:
    molecule_id = str(row["molecule_id"])
    cms_path = Path(str(row["source_cms"]))
    trajectory_path = Path(str(row["source_trajectory"]))
    pocket_asl = str(row.get("pocket_asl", "")).strip() or args.pocket_asl
    if not pocket_asl:
        raise RuntimeError(f"{molecule_id}: pocket_asl is required")
    _, cms = topo.read_cms(str(cms_path))
    frames = traj.read_traj(str(trajectory_path))
    consistency = topo.check_consistency(cms, frames[-1])
    if consistency is not None:
        raise RuntimeError(f"{molecule_id}: source topology inconsistency: {consistency}")

    ligand_all_aids = cms.select_atom(args.ligand_asl)
    ligand_heavy_aids = cms.select_atom(f"({args.ligand_asl}) and not atom.ele H")
    pocket_heavy_aids = cms.select_atom(f"({pocket_asl}) and not atom.ele H")
    pocket_ca_aids = cms.select_atom(f"({pocket_asl}) and atom.ptype CA")
    protein_heavy_aids = cms.select_atom("protein and not atom.ele H")
    if not ligand_heavy_aids or not pocket_heavy_aids or len(pocket_ca_aids) < 3:
        raise RuntimeError(
            f"{molecule_id}: invalid selections ligand={len(ligand_heavy_aids)} "
            f"pocket={len(pocket_heavy_aids)} pocket_CA={len(pocket_ca_aids)}"
        )
    medoid = pose_medoid(
        cms,
        frames,
        ligand_heavy_aids,
        pocket_ca_aids,
        args.late_start_ns,
        args.cluster_cutoff_a,
    )
    planned = optional_float(row, "planned_medoid_time_ns")
    expected_fraction = optional_float(row, "expected_cluster_fraction")
    if planned is not None and abs(medoid["time_ns"] - planned) > args.time_tolerance_ns:
        raise RuntimeError(f"{molecule_id}: medoid time differs from plan")
    if expected_fraction is not None and abs(medoid["dominant_cluster_fraction"] - expected_fraction) > args.fraction_tolerance:
        raise RuntimeError(f"{molecule_id}: dominant-cluster fraction differs from plan")

    frame = frames[medoid["frame_index"]].copy()
    box = np.asarray(frame.box, dtype=float).copy()
    ligand_all_gids = topo.aids2gids(cms, ligand_all_aids, include_pseudoatoms=False)
    ligand_heavy_gids = topo.aids2gids(cms, ligand_heavy_aids, include_pseudoatoms=False)
    pocket_heavy_gids = topo.aids2gids(cms, pocket_heavy_aids, include_pseudoatoms=False)
    source_ligand = unwrap_group(frame.pos(ligand_all_gids), box)
    pocket = unwrap_group(frame.pos(pocket_heavy_gids), box)
    displacement = source_ligand[0] - pocket.mean(axis=0)
    image_shift = minimum_image(displacement, box) - displacement
    normalized_ligand = source_ligand + image_shift
    frame.pos()[ligand_all_gids] = normalized_ligand

    source_signature = topology_signature(cms)
    output_cms = cms.copy()
    topo.update_cms(output_cms, frame)
    output_dir = args.output_root / molecule_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{molecule_id}-out.cms"
    temporary = output_dir / f".{molecule_id}-out.cms.tmp"
    output_cms.fix_filenames(str(output_path), None)
    output_cms.write(str(temporary))
    os.replace(temporary, output_path)
    _, reread = topo.read_cms(str(output_path))
    if topo.check_consistency(reread, frame) is not None:
        raise RuntimeError(f"{molecule_id}: written CMS failed topology consistency")
    if topology_signature(reread) != source_signature:
        raise RuntimeError(f"{molecule_id}: topology or force-field fingerprint changed")
    if not np.allclose(np.asarray(reread.box).reshape(3, 3), box, atol=1e-5):
        raise RuntimeError(f"{molecule_id}: box matrix changed")

    output_ligand = np.asarray([reread.atom[aid].xyz for aid in ligand_heavy_aids])
    output_pocket = np.asarray([reread.atom[aid].xyz for aid in pocket_heavy_aids])
    output_protein = np.asarray([reread.atom[aid].xyz for aid in protein_heavy_aids])
    source_heavy = frame.pos(ligand_heavy_gids)
    pocket_min = float(pbc_distances(output_ligand, output_pocket, box).min())
    protein_distances = pbc_distances(output_ligand, output_protein, box)
    clashes = int(np.sum(protein_distances < args.clash_cutoff_a))
    coordinate_error = float(np.max(np.abs(output_ligand - source_heavy)))
    if clashes or pocket_min > args.maximum_pocket_min_a or coordinate_error > 1e-4:
        raise RuntimeError(
            f"{molecule_id}: geometry QC failed clashes={clashes} "
            f"pocket_min={pocket_min:.3f} coordinate_error={coordinate_error:.6f}"
        )
    result = {
        "molecule_id": molecule_id,
        **medoid,
        "source_cms": str(cms_path.resolve()),
        "source_trajectory": str(trajectory_path.resolve()),
        "output_cms": str(output_path.resolve()),
        "pocket_asl": pocket_asl,
        "ligand_asl": args.ligand_asl,
        "ligand_image_shift_a": image_shift.tolist(),
        "minimum_protein_ligand_a": float(protein_distances.min()),
        "minimum_pocket_ligand_a": pocket_min,
        "clash_pairs": clashes,
        "coordinate_max_error_a": coordinate_error,
        "topology_consistency": "pass",
        **source_signature,
    }
    (output_dir / "input_qc.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    args = parse_args()
    table = pd.read_csv(args.input_csv)
    required = {"molecule_id", "source_cms", "source_trajectory"}
    missing = required.difference(table.columns)
    if missing:
        raise SystemExit(f"Input CSV is missing columns: {sorted(missing)}")
    records = []
    for _, row in table.iterrows():
        print(f"PREP {row['molecule_id']}", flush=True)
        records.append(process_one(args, row))
        print(f"PASS {row['molecule_id']}", flush=True)
    args.output_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(args.output_root / "medoid_cms_manifest.csv", index=False)


if __name__ == "__main__":
    main()
