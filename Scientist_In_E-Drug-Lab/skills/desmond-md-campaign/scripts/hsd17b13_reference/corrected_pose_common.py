#!/usr/bin/env python3
"""Shared helpers for the corrected-pose Phase E campaign."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from schrodinger import structure
from schrodinger.application.desmond.packages import topo


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
BATCH = "phaseE_corrected_pose_2_50_all40_20260727"
SYSTEM_BATCH = "phaseE_corrected_pose_all40_20260727"
SYSTEM_ROOT = ROOT / "03_systems" / SYSTEM_BATCH
TRAJECTORY_ROOT = ROOT / "04_trajectories" / BATCH
ANALYSIS_ROOT = ROOT / "05_analysis" / BATCH
MANIFEST = ROOT / "meta" / f"{SYSTEM_BATCH}.csv"
BUILD_PROTOCOL = ROOT / "scripts/protocols/build_membrane_system.msj"
MD_PROTOCOL = ROOT / "scripts/protocols/prod_2ns_eq_50ns.msj"
ORIGINAL_RECEPTOR = PROJECT / "prepwizard/8G9V_prepared-out.maegz"
ORIENTED_RECEPTOR = ROOT / "01_template/prepared_dimer.mae"


def load_ids() -> list[str]:
    ids: list[str] = []
    for path in (ROOT / "meta/ids_27.txt", ROOT / "meta/phaseD_new13_ids.txt"):
        ids.extend(
            line.strip()
            for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if len(ids) != 40 or len(set(ids)) != 40:
        raise RuntimeError(f"Expected 40 unique molecule IDs, got {len(ids)}/{len(set(ids))}")
    return ids


def read_structure(path: Path):
    return next(structure.StructureReader(str(path)))


def kabsch(mobile: np.ndarray, reference: np.ndarray):
    mobile_center = mobile.mean(axis=0)
    reference_center = reference.mean(axis=0)
    u, _, vt = np.linalg.svd(
        (mobile - mobile_center).T @ (reference - reference_center)
    )
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    return rotation, mobile_center, reference_center


def apply_transform(xyz: np.ndarray, fit) -> np.ndarray:
    rotation, mobile_center, reference_center = fit
    return (xyz - mobile_center) @ rotation + reference_center


def rmsd(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.sum((first - second) ** 2, axis=1))))


def rotation_angle(rotation: np.ndarray) -> float:
    cosine = np.clip((np.trace(rotation) - 1.0) / 2.0, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def ca_map(model) -> dict[tuple, np.ndarray]:
    return {
        (atom.chain.strip(), int(atom.resnum), atom.inscode.strip(), atom.pdbname.strip()):
        np.asarray(atom.xyz, float)
        for atom in model.atom
        if atom.chain.strip() in {"A", "B"} and atom.pdbname.strip() == "CA"
    }


def fit_maps(mobile_map: dict, reference_map: dict):
    keys = sorted(set(mobile_map) & set(reference_map))
    mobile = np.asarray([mobile_map[key] for key in keys])
    reference = np.asarray([reference_map[key] for key in keys])
    fit = kabsch(mobile, reference)
    return fit, len(keys), rmsd(apply_transform(mobile, fit), reference)


def receptor_transform():
    original = read_structure(ORIGINAL_RECEPTOR)
    oriented = read_structure(ORIENTED_RECEPTOR)
    fit, matched, fit_rmsd = fit_maps(ca_map(original), ca_map(oriented))
    determinant = float(np.linalg.det(fit[0]))
    if matched != 566 or fit_rmsd >= 1e-3 or abs(determinant - 1.0) >= 1e-6:
        raise RuntimeError(
            f"Invalid receptor transform: matched={matched} rmsd={fit_rmsd} det={determinant}"
        )
    return fit, matched, fit_rmsd


def distance_matrix(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    return np.sqrt(np.sum((first[:, None, :] - second[None, :, :]) ** 2, axis=2))


def transformed_ligand(mid: str, fit):
    source = ROOT / "meta/ligands" / f"{mid}.mae"
    ligand = read_structure(source)
    all_xyz = np.asarray([atom.xyz for atom in ligand.atom], float)
    moved = apply_transform(all_xyz, fit)
    for atom, xyz in zip(ligand.atom, moved):
        atom.xyz = xyz
    ligand.title = mid
    return ligand, source


def ligand_heavy(model) -> tuple[np.ndarray, list[str]]:
    atoms = [atom for atom in model.atom if atom.element != "H"]
    return np.asarray([atom.xyz for atom in atoms], float), [atom.element for atom in atoms]


def prebuild_pose_qc(mid: str, fit, oriented=None) -> dict:
    oriented = oriented or read_structure(ORIENTED_RECEPTOR)
    ligand, source = transformed_ligand(mid, fit)
    ligand_xyz, elements = ligand_heavy(ligand)
    protein_atoms = [
        atom for atom in oriented.atom
        if atom.chain.strip() in {"A", "B"} and atom.element != "H"
    ]
    protein_xyz = np.asarray([atom.xyz for atom in protein_atoms], float)
    distances = distance_matrix(ligand_xyz, protein_xyz)
    near_indices = np.where(distances.min(axis=0) <= 4.0)[0]
    contacts = sorted({
        f"{protein_atoms[index].chain.strip()}:{protein_atoms[index].pdbres.strip()}"
        f"{int(protein_atoms[index].resnum)}"
        for index in near_indices
    })
    chain_b_contacts = sum(contact.startswith("B:") for contact in contacts)
    clash_pairs = int(np.sum(distances < 1.5))
    if chain_b_contacts == 0 or clash_pairs:
        raise RuntimeError(
            f"{mid}: invalid transformed pose, chain_B_contacts={chain_b_contacts}, "
            f"clash_pairs={clash_pairs}"
        )
    return {
        "molecule_id": mid,
        "source_ligand": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "ligand_heavy_atoms": len(elements),
        "min_protein_heavy_distance_A": float(distances.min()),
        "clash_pairs_lt_1p5A": clash_pairs,
        "chain_B_contact_residues": chain_b_contacts,
        "chain_A_contact_residues": sum(contact.startswith("A:") for contact in contacts),
        "contact_residues_4A": ";".join(contacts),
        "glide_xp": ligand.property.get("r_glide_XP_GScore", ""),
        "mmgbsa": ligand.property.get("r_psp_MMGBSA_dG_Bind", ""),
        "prebuild_pose_valid": True,
    }


def cms_ca_map(cms, aids: list[int]) -> dict[tuple, np.ndarray]:
    return {
        (
            cms.atom[aid].chain.strip(),
            int(cms.atom[aid].resnum),
            cms.atom[aid].inscode.strip(),
            cms.atom[aid].pdbname.strip(),
        ): np.asarray(cms.atom[aid].xyz, float)
        for aid in aids
    }


def validate_built_cms(mid: str, cms_path: Path) -> dict:
    _, cms = topo.read_cms(str(cms_path))
    ca_aids = cms.select_atom("protein and atom.ptype CA")
    ligand_aids = cms.select_atom("res.ptype UNK and not atom.ele H")
    protein_aids = cms.select_atom("protein and not atom.ele H")
    if not ligand_aids:
        raise RuntimeError(f"{mid}: no ligand heavy atoms selected in {cms_path}")

    oriented = read_structure(ORIENTED_RECEPTOR)
    fit, matched, protein_fit_rmsd = fit_maps(cms_ca_map(cms, ca_aids), ca_map(oriented))
    if matched != 566 or protein_fit_rmsd >= 0.1:
        raise RuntimeError(
            f"{mid}: built protein alignment failed: matched={matched}, rmsd={protein_fit_rmsd}"
        )

    expected = read_structure(SYSTEM_ROOT / mid / "corrected_ligand.mae")
    expected_xyz, expected_elements = ligand_heavy(expected)
    actual_elements = [cms.atom[aid].element for aid in ligand_aids]
    if actual_elements != expected_elements:
        raise RuntimeError(f"{mid}: ligand heavy-atom identity/order changed during build")
    actual_xyz = apply_transform(
        np.asarray([cms.atom[aid].xyz for aid in ligand_aids], float), fit
    )
    pose_rmsd = rmsd(actual_xyz, expected_xyz)
    if pose_rmsd >= 0.1:
        raise RuntimeError(f"{mid}: post-build ligand pose RMSD {pose_rmsd:.4f} A")

    protein_xyz = apply_transform(
        np.asarray([cms.atom[aid].xyz for aid in protein_aids], float), fit
    )
    distances = distance_matrix(actual_xyz, protein_xyz)
    clash_pairs = int(np.sum(distances < 1.5))
    if clash_pairs:
        raise RuntimeError(f"{mid}: post-build protein-ligand clashes={clash_pairs}")

    result = {
        "molecule_id": mid,
        "cms_path": str(cms_path),
        "cms_size_bytes": cms_path.stat().st_size,
        "protein_ca_matched": matched,
        "protein_ca_fit_rmsd_A": protein_fit_rmsd,
        "ligand_heavy_atoms": len(ligand_aids),
        "ligand_pose_rmsd_A": pose_rmsd,
        "min_protein_ligand_distance_A": float(distances.min()),
        "clash_pairs_lt_1p5A": clash_pairs,
        "postbuild_valid": True,
    }
    del cms
    return result


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
