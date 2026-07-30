#!/usr/bin/env python3
"""Extract Phase E late-pose medoids as full-system, clash-checked Phase F CMS inputs."""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist, squareform
from schrodinger.application.desmond.packages import topo, traj

from phaseF_common import (
    ANALYSIS_ROOT, BACKUPS, IDS_FILE, MANIFEST, PRIMARY, ROOT, SYSTEM_ROOT,
    align, kabsch, minimum_image, sha256, source_attempt, trajectory_dir,
    unwrap_group, write_json,
)

SOURCE_QC = ROOT / "05_analysis/phaseE_corrected_pose_2_50_all40_20260727/corrected_pose_qc.csv"
METRICS = ROOT / "05_analysis/phaseE_corrected_pose_2_50_all40_20260727/summary/md27_metrics.csv"
POCKET = ROOT / "05_analysis/phaseE_corrected_pose_2_50_all40_20260727/pocket_geometry/phaseE_target_pocket_diagnostics.csv"
SMILES = ROOT.parent / "dock_funnel_xp_mmgbsa/mmgbsa_next80/xp_all250_ranked.csv"
DONE = ANALYSIS_ROOT / "INPUT_ALL16_QC_DONE.flag"
FAILED = ANALYSIS_ROOT / "INPUT_QC_FAILED.flag"
FF_TABLES = (
    "site", "bond", "angle", "dihedral", "exclusion", "pair", "constraint",
    "vdwtype", "vdwtypescombined", "pseudo", "virtual", "restraint",
    "stretchfbhw", "anglefbhw", "improperfbhw", "posfbhw",
)


def stable(value):
    if isinstance(value, float):
        return round(value, 8)
    return value


def ff_fingerprint(cms) -> str:
    # Pseudo-site coordinates are frame state, not force-field semantics, and
    # legitimately change when topo.update_cms installs the selected frame.
    def semantic_properties(properties):
        return sorted(
            (key, stable(value)) for key, value in properties.items()
            if not key.endswith(("_x_coord", "_y_coord", "_z_coord"))
            and "velocity" not in key
        )

    records = []
    for index, ct in enumerate(cms.comp_ct):
        ff = ct.ffio
        record = {
            "index": index, "title": ct.title, "atoms": len(ct.atom),
            "ct_type": ct.property.get("s_ffio_ct_type"),
            "combining_rule": ff.combining_rule, "name": ff.name,
            "version": ff.version, "property": semantic_properties(ff.property),
            "tables": {},
        }
        for name in FF_TABLES:
            table = getattr(ff, name)
            record["tables"][name] = [
                semantic_properties(item.property)
                for item in table
            ]
        records.append(record)
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def topology_signature(cms) -> dict:
    atom_rows = [
        (atom.index, atom.atomic_number, atom.formal_charge, atom.chain.strip(),
         int(atom.resnum), atom.inscode.strip(), atom.pdbres.strip(), atom.pdbname.strip())
        for atom in cms.atom
    ]
    digest = hashlib.sha256(repr(atom_rows).encode()).hexdigest()
    return {
        "atom_total": int(cms.atom_total), "comp_atom_total": int(cms.comp_atom_total),
        "component_count": len(cms.comp_ct),
        "components": [
            {"title": ct.title, "atoms": len(ct.atom),
             "ct_type": ct.property.get("s_ffio_ct_type")}
            for ct in cms.comp_ct
        ],
        "formal_charge": int(sum(atom.formal_charge for atom in cms.atom)),
        "atom_identity_sha256": digest, "forcefield_sha256": ff_fingerprint(cms),
    }


def contact_residues(mid: str, table: pd.DataFrame) -> set[int]:
    value = str(table.loc[mid, "contact_residues_4A"])
    residues = set()
    for item in value.split(";"):
        if not item.startswith("B:"):
            continue
        digits = "".join(character for character in item.split(":", 1)[1] if character.isdigit())
        if digits:
            residues.add(int(digits))
    if not residues:
        raise RuntimeError(f"{mid}: no source chain-B pocket residues")
    return residues


def cluster_medoid(cms, frames, residues: set[int]):
    late_indices = [i for i, frame in enumerate(frames) if frame.time >= 40000.0 - 1e-3]
    ligand_aids = cms.select_atom("res.ptype UNK and not atom.ele H")
    ca_aids = [
        aid for aid in cms.select_atom("protein and chain.name B and atom.ptype CA")
        if int(cms.atom[aid].resnum) in residues
    ]
    if not ligand_aids or len(ca_aids) < 3:
        raise RuntimeError(f"invalid selections ligand={len(ligand_aids)} pocket_CA={len(ca_aids)}")
    ligand_gids = topo.aids2gids(cms, ligand_aids, include_pseudoatoms=False)
    ca_gids = topo.aids2gids(cms, ca_aids, include_pseudoatoms=False)
    aligned_ligands = []
    reference_ca = None
    for index in late_indices:
        frame = frames[index]
        box = np.asarray(frame.box, float)
        ca = unwrap_group(frame.pos(ca_gids), box)
        ligand = unwrap_group(frame.pos(ligand_gids), box)
        ligand += minimum_image(ligand.mean(axis=0) - ca.mean(axis=0), box) - (
            ligand.mean(axis=0) - ca.mean(axis=0)
        )
        if reference_ca is None:
            reference_ca = ca.copy()
        aligned_ligands.append(align(ligand, kabsch(ca, reference_ca)))
    coordinates = np.asarray(aligned_ligands)
    condensed = pdist(coordinates.reshape(len(coordinates), -1)) / np.sqrt(len(ligand_gids))
    labels = fcluster(linkage(condensed, method="average"), t=2.0, criterion="distance")
    counts = Counter(labels)
    dominant = max(counts, key=counts.get)
    members = np.where(labels == dominant)[0]
    if len(members) == 1:
        medoid_local = int(members[0])
        radius = 0.0
    else:
        distances = squareform(condensed)[np.ix_(members, members)]
        medoid_local = int(members[np.argmin(distances.mean(axis=1))])
        radius = float(np.median(squareform(condensed)[medoid_local, members]))
    return {
        "frame_index": late_indices[medoid_local],
        "time_ns": frames[late_indices[medoid_local]].time / 1000.0,
        "dominant_count": int(counts[dominant]), "late_frame_count": len(late_indices),
        "fraction": float(counts[dominant] / len(late_indices)), "radius_A": radius,
        "ligand_aids": ligand_aids, "ca_aids": ca_aids,
    }


def pbc_distances(first: np.ndarray, second: np.ndarray, box: np.ndarray) -> np.ndarray:
    delta = first[:, None, :] - second[None, :, :]
    return np.sqrt(np.sum(minimum_image(delta, box) ** 2, axis=2))


def prepare_one(mid: str, planned_time: float, expected_fraction: float, replacement_of: str = "") -> dict:
    attempt = source_attempt(mid)
    source_cms_path = attempt / f"{mid}_52ns-out.cms"
    dtr = trajectory_dir(attempt)
    _, source_cms = topo.read_cms(str(source_cms_path))
    frames = traj.read_traj(str(dtr))
    consistency = topo.check_consistency(source_cms, frames[-1])
    if consistency is not None:
        raise RuntimeError(f"{mid}: source topology inconsistent: {consistency}")
    qc_table = pd.read_csv(SOURCE_QC).set_index("molecule_id")
    residues = contact_residues(mid, qc_table)
    medoid = cluster_medoid(source_cms, frames, residues)
    if abs(medoid["time_ns"] - planned_time) > 0.2001:
        raise RuntimeError(f"{mid}: medoid {medoid['time_ns']:.3f} ns != plan {planned_time:.3f} ns")
    if abs(medoid["fraction"] - expected_fraction) > 0.011:
        raise RuntimeError(f"{mid}: dominant fraction {medoid['fraction']:.6f} != {expected_fraction}")

    frame = frames[medoid["frame_index"]].copy()
    box = np.asarray(frame.box, float).copy()
    ligand_all_aids = source_cms.select_atom("res.ptype UNK")
    ligand_heavy_aids = medoid["ligand_aids"]
    protein_heavy_aids = source_cms.select_atom("protein and not atom.ele H")
    pocket_heavy_aids = [
        aid for aid in source_cms.select_atom("protein and chain.name B and not atom.ele H")
        if int(source_cms.atom[aid].resnum) in residues
    ]
    ligand_all_gids = topo.aids2gids(source_cms, ligand_all_aids, include_pseudoatoms=False)
    ligand_heavy_gids = topo.aids2gids(source_cms, ligand_heavy_aids, include_pseudoatoms=False)
    protein_heavy_gids = topo.aids2gids(source_cms, protein_heavy_aids, include_pseudoatoms=False)
    pocket_heavy_gids = topo.aids2gids(source_cms, pocket_heavy_aids, include_pseudoatoms=False)
    source_ligand = unwrap_group(frame.pos(ligand_all_gids), box)
    pocket = unwrap_group(frame.pos(pocket_heavy_gids), box)
    raw = source_ligand[0] - pocket.mean(axis=0)
    image_shift = minimum_image(raw, box) - raw
    normalized_ligand = source_ligand + image_shift
    frame.pos()[ligand_all_gids] = normalized_ligand

    source_topology = topology_signature(source_cms)
    output_cms = source_cms.copy()
    topo.update_cms(output_cms, frame)
    output_dir = SYSTEM_ROOT / mid
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"{mid}-out.cms"
    temporary = output_dir / f".{mid}-out.cms.tmp"
    output_cms.fix_filenames(str(final_path), None)
    output_cms.write(str(temporary))
    os.replace(temporary, final_path)
    _, reread = topo.read_cms(str(final_path))
    output_topology = topology_signature(reread)
    reread_frame = frame.copy()
    reread_frame.pos()[reread.allaid_gids] = reread.getXYZ()
    # The written CMS contains physical atoms; retain source pseudoatom coordinates for consistency check.
    check = topo.check_consistency(reread, frame)
    if check is not None:
        raise RuntimeError(f"{mid}: written CMS topology inconsistent: {check}")
    if source_topology != output_topology:
        raise RuntimeError(f"{mid}: topology/force-field fingerprint changed during write")
    if not np.allclose(np.asarray(reread.box, float).reshape(3, 3), box, atol=1e-5):
        raise RuntimeError(f"{mid}: box matrix changed during write")

    out_lig = np.asarray([reread.atom[aid].xyz for aid in ligand_heavy_aids], float)
    out_protein = np.asarray([reread.atom[aid].xyz for aid in protein_heavy_aids], float)
    out_pocket = np.asarray([reread.atom[aid].xyz for aid in pocket_heavy_aids], float)
    source_heavy = normalized_ligand[[ligand_all_aids.index(aid) for aid in ligand_heavy_aids]]
    source_min = float(pbc_distances(source_heavy, pocket, box).min())
    output_min = float(pbc_distances(out_lig, out_pocket, box).min())
    source_com = float(np.linalg.norm(minimum_image(source_heavy.mean(0) - pocket.mean(0), box)))
    output_com = float(np.linalg.norm(minimum_image(out_lig.mean(0) - out_pocket.mean(0), box)))
    protein_dist = pbc_distances(out_lig, out_protein, box)
    clash_pairs = int(np.sum(protein_dist < 1.5))
    if clash_pairs or output_min > 4.0:
        raise RuntimeError(f"{mid}: hard geometry QC failed clashes={clash_pairs} pocket_min={output_min:.3f}")
    if abs(output_min - source_min) > 0.1 or abs(output_com - source_com) > 0.1:
        raise RuntimeError(f"{mid}: source/output pocket geometry changed")
    max_coordinate_error = float(np.max(np.abs(out_lig - source_heavy)))
    if max_coordinate_error > 1e-4:
        raise RuntimeError(f"{mid}: written coordinates changed by {max_coordinate_error:.6f} A")

    result = {
        "molecule_id": mid, "replacement_of": replacement_of,
        "planned_medoid_time_ns": planned_time, "actual_medoid_time_ns": medoid["time_ns"],
        "medoid_frame_index": medoid["frame_index"],
        "dominant_cluster_fraction": medoid["fraction"],
        "dominant_cluster_count": medoid["dominant_count"],
        "late_frame_count": medoid["late_frame_count"], "cluster_radius_A": medoid["radius_A"],
        "source_attempt": str(attempt), "source_cms": str(source_cms_path),
        "source_trajectory": str(dtr), "output_cms": str(final_path),
        "atom_total": source_topology["atom_total"],
        "component_count": source_topology["component_count"],
        "component_titles": ";".join(item["title"] for item in source_topology["components"]),
        "formal_charge": source_topology["formal_charge"],
        "atom_identity_sha256": source_topology["atom_identity_sha256"],
        "forcefield_sha256": source_topology["forcefield_sha256"],
        "box_matrix": json.dumps(box.tolist()), "ligand_image_shift_A": json.dumps(image_shift.tolist()),
        "source_pocket_com_A": source_com, "output_pocket_com_A": output_com,
        "pocket_com_error_A": abs(output_com - source_com),
        "source_pocket_min_A": source_min, "output_pocket_min_A": output_min,
        "pocket_min_error_A": abs(output_min - source_min),
        "min_protein_ligand_A": float(protein_dist.min()),
        "clash_pairs_lt_1p5A": clash_pairs, "coordinate_max_error_A": max_coordinate_error,
        "topo_consistency": "pass", "cms_size_bytes": final_path.stat().st_size,
        "cms_sha256": sha256(final_path), "input_qc_valid": True,
    }
    write_json(output_dir / "input_qc.json", result)
    del frames, source_cms, output_cms, reread
    gc.collect()
    return result


def add_metadata(records: list[dict]) -> list[dict]:
    metrics = pd.read_csv(METRICS).set_index("molecule_id")
    pocket = pd.read_csv(POCKET).set_index("molecule_id")
    source = pd.read_csv(SMILES).drop_duplicates("title").set_index("title")
    try:
        from rdkit import Chem, DataStructs
        from rdkit.Chem import AllChem
        from rdkit.Chem.Scaffolds import MurckoScaffold
    except ImportError as error:
        raise RuntimeError("RDKit is required for diversity verification") from error
    fingerprints = {}
    for rank, record in enumerate(records, 1):
        mid = record["molecule_id"]
        smiles = str(source.loc[mid, "SMILES"])
        molecule = Chem.MolFromSmiles(smiles)
        scaffold = MurckoScaffold.GetScaffoldForMol(molecule)
        scaffold_smiles = Chem.MolToSmiles(scaffold, isomericSmiles=False)
        fingerprints[mid] = AllChem.GetMorganFingerprintAsBitVect(molecule, 2, nBits=2048)
        record.update({
            "selection_rank": rank,
            "selection_class": "A_target_pocket_retained",
            "selection_rationale": "top-16 A-class by MD score, late contacts, pocket retention, convergence, and scaffold diversity",
            "smiles": smiles, "pose_xp": float(source.loc[mid, "r_i_glide_gscore"]),
            "mmgbsa": float(metrics.loc[mid, "mmgbsa"]),
            "md_triage_score": float(metrics.loc[mid, "md_triage_score"]),
            "late_direct_contact_coverage": float(metrics.loc[mid, "late_direct_contact_coverage"]),
            "pocket_diagnosis": str(pocket.loc[mid, "pocket_diagnosis"]),
            "murcko_scaffold": scaffold_smiles,
        })
    scaffolds = [record["murcko_scaffold"] for record in records]
    if len(scaffolds) != len(set(scaffolds)):
        raise RuntimeError("Selected inputs contain duplicate exact Murcko scaffolds")
    maximum = 0.0
    maximum_pair = ""
    ids = [record["molecule_id"] for record in records]
    for i, first in enumerate(ids):
        for second in ids[i + 1:]:
            similarity = float(DataStructs.TanimotoSimilarity(fingerprints[first], fingerprints[second]))
            if similarity > maximum:
                maximum, maximum_pair = similarity, f"{first}:{second}"
    if maximum >= 0.70:
        raise RuntimeError(f"Diversity QC failed max Tanimoto={maximum:.3f} ({maximum_pair})")
    for record in records:
        record["batch_max_pairwise_morgan_tanimoto"] = maximum
        record["batch_max_similarity_pair"] = maximum_pair
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="revalidate and overwrite isolated Phase F inputs")
    args = parser.parse_args()
    ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)
    SYSTEM_ROOT.mkdir(parents=True, exist_ok=True)
    FAILED.unlink(missing_ok=True)
    records = []
    failures = []
    backup_index = 0
    for mid, planned, fraction in PRIMARY:
        selected = (mid, planned, fraction, "")
        while True:
            try:
                print(f"PREP {selected[0]} medoid={selected[1]:.1f} ns", flush=True)
                record = prepare_one(*selected)
                records.append(record)
                print(f"PASS {selected[0]} min={record['min_protein_ligand_A']:.3f} A", flush=True)
                break
            except Exception as error:
                failures.append({"candidate": selected[0], "replacement_of": selected[3], "error": repr(error)})
                print(f"FAIL {selected[0]}: {error}", flush=True)
                if selected[3]:
                    raise
                if backup_index >= len(BACKUPS):
                    raise
                backup = BACKUPS[backup_index]
                backup_index += 1
                selected = (backup[0], backup[1], backup[2], mid)
                print(f"REPLACE {mid} -> {selected[0]}", flush=True)
    records = add_metadata(records)
    fields = list(records[0])
    with MANIFEST.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    IDS_FILE.write_text("\n".join(record["molecule_id"] for record in records) + "\n")
    write_json(ANALYSIS_ROOT / "input_qc_failures_and_replacements.json", {"failures": failures})
    DONE.write_text(f"{datetime.now().isoformat()}\nvalid=16\nmanifest={MANIFEST}\n")
    print(f"DONE 16/16 input CMS validated; manifest={MANIFEST}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)
        FAILED.write_text(f"{datetime.now().isoformat()}\n{error!r}\n")
        raise
