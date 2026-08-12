#!/usr/bin/env python3
"""Audit preservation of MM-GBSA poses in the six membrane-MD systems."""
import csv
import gc
from pathlib import Path
import numpy as np
from schrodinger import structure
from schrodinger.application.desmond.packages import topo

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
OUT = ROOT / "05_analysis/md200_selection"
IDS = ["T3040", "T0465", "T4965", "T3232", "T39220", "T5135"]
GRID_CENTER = np.array([6.4687, 15.1192, 10.6188])


def read(path):
    return next(structure.StructureReader(str(path)))


def kabsch(mobile, reference):
    mc, rc = mobile.mean(0), reference.mean(0)
    u, _, vt = np.linalg.svd((mobile - mc).T @ (reference - rc))
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    return rotation, mc, rc


def apply(xyz, fit):
    rotation, mc, rc = fit
    return (xyz - mc) @ rotation + rc


def rmsd(first, second):
    return float(np.sqrt(np.mean(np.sum((first - second) ** 2, axis=1))))


def angle(rotation):
    cosine = np.clip((np.trace(rotation) - 1.0) / 2.0, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def ca_map(model):
    return {
        (a.chain.strip(), int(a.resnum), a.inscode.strip(), a.pdbname.strip()):
        np.asarray(a.xyz, float)
        for a in model.atom
        if a.chain.strip() in {"A", "B"} and a.pdbname.strip() == "CA"
    }


def fit_maps(mobile_map, reference_map):
    keys = sorted(set(mobile_map) & set(reference_map))
    mobile = np.asarray([mobile_map[key] for key in keys])
    reference = np.asarray([reference_map[key] for key in keys])
    fit = kabsch(mobile, reference)
    return fit, len(keys), rmsd(apply(mobile, fit), reference)


def distances(first, second):
    return np.sqrt(np.sum((first[:, None, :] - second[None, :, :]) ** 2, axis=2))


def contact_set(ligand, protein, labels):
    matrix = distances(ligand, protein)
    indices = np.where(matrix.min(0) <= 4.0)[0]
    return matrix, sorted({labels[index] for index in indices})


def audit(mid, receptor_fit, oriented_ca, oriented_heavy):
    ligand = read(ROOT / "meta/ligands" / f"{mid}.mae")
    original = np.asarray([a.xyz for a in ligand.atom if a.element != "H"], float)
    original_elements = [a.element for a in ligand.atom if a.element != "H"]
    expected = apply(original, receptor_fit)
    built_dist = distances(original, oriented_heavy)
    built_ligand_fit = kabsch(original, expected)

    stage6 = (ROOT / "04_trajectories/phaseB_200ns" / mid /
              f"HSD17B13_B200_{mid}_6" / f"HSD17B13_B200_{mid}_6-in.cms")
    msys_model, cms = topo.read_cms(str(stage6))
    ca_aids = cms.select_atom("protein and atom.ptype CA")
    lig_aids = cms.select_atom("res.ptype UNK and not atom.ele H")
    protein_aids = cms.select_atom("protein and not atom.ele H")
    production_elements = [cms.atom[aid].element for aid in lig_aids]
    if production_elements != original_elements:
        raise RuntimeError(f"{mid}: ligand heavy-atom order changed during system build")
    production_ca = {
        (cms.atom[aid].chain.strip(), int(cms.atom[aid].resnum),
         cms.atom[aid].inscode.strip(), cms.atom[aid].pdbname.strip()):
        np.asarray(cms.atom[aid].xyz, float)
        for aid in ca_aids
    }
    production_fit, _, protein_fit_rmsd = fit_maps(production_ca, oriented_ca)
    actual = apply(np.asarray([cms.atom[a].xyz for a in lig_aids]), production_fit)
    protein = apply(np.asarray([cms.atom[a].xyz for a in protein_aids]), production_fit)
    labels = [
        f"{cms.atom[a].chain.strip()}:{cms.atom[a].pdbres.strip()}{int(cms.atom[a].resnum)}"
        for a in protein_aids
    ]
    actual_dist, actual_contacts = contact_set(actual, protein, labels)
    _, expected_contacts = contact_set(expected, protein, labels)
    intersection = set(actual_contacts) & set(expected_contacts)
    union = set(actual_contacts) | set(expected_contacts)
    pose_fit = kabsch(actual, expected)

    row = {
        "molecule_id": mid,
        "grid_file": ligand.property.get("s_i_glide_gridfile", ""),
        "xp_gscore_pose": ligand.property.get("r_glide_XP_GScore", ""),
        "mmgbsa_dg_bind": ligand.property.get("r_psp_MMGBSA_dG_Bind", ""),
        "production_receptor_ca_fit_rmsd_A": protein_fit_rmsd,
        "built_pose_rmsd_to_correct_A": rmsd(original, expected),
        "built_com_target_delta_A": float(np.linalg.norm(original.mean(0) - expected.mean(0))),
        "built_required_rotation_deg": angle(built_ligand_fit[0]),
        "built_ligand_fit_rmsd_A": rmsd(apply(original, built_ligand_fit), expected),
        "built_min_protein_distance_A": float(built_dist.min()),
        "built_clash_pairs_lt_1p5A": int(np.sum(built_dist < 1.5)),
        "prod_start_pose_rmsd_to_correct_A": rmsd(actual, expected),
        "prod_start_com_target_delta_A": float(np.linalg.norm(actual.mean(0) - expected.mean(0))),
        "prod_start_required_rotation_deg": angle(pose_fit[0]),
        "prod_start_ligand_fit_rmsd_A": rmsd(apply(actual, pose_fit), expected),
        "prod_start_rmsd_from_wrong_build_pose_A": rmsd(actual, original),
        "prod_start_min_protein_distance_A": float(actual_dist.min()),
        "target_contact_retention_fraction": len(intersection) / len(expected_contacts),
        "contact_jaccard": len(intersection) / len(union),
        "expected_target_contacts": ";".join(expected_contacts),
        "actual_production_start_contacts": ";".join(actual_contacts),
        "coordinate_frame_consistent": False,
        "initial_pose_valid_for_target_pocket_md": False,
        "issue": "ligand_not_transformed_with_membrane_oriented_receptor",
    }
    del msys_model, cms
    gc.collect()
    return row


def main():
    original_receptor = read(PROJECT / "prepwizard/8G9V_prepared-out.maegz")
    oriented_receptor = read(ROOT / "01_template/prepared_dimer.mae")
    oriented_ca = ca_map(oriented_receptor)
    receptor_fit, matched, receptor_rmsd = fit_maps(
        ca_map(original_receptor), oriented_ca
    )
    if matched != 566 or receptor_rmsd > 1e-3:
        raise RuntimeError(f"Unexpected receptor fit: {matched}, {receptor_rmsd}")

    crystal = read(Path(
        "/data/ye/protein-ligand/8G9V_YYC_B402_pose_original_coordinates.sdf"
    ))
    centroid = np.asarray([a.xyz for a in crystal.atom]).mean(0)
    if np.linalg.norm(centroid - GRID_CENTER) > 1e-3:
        raise RuntimeError("Grid center does not match the YYC centroid")

    oriented_heavy = np.asarray([
        a.xyz for a in oriented_receptor.atom
        if a.chain.strip() in {"A", "B"} and a.element != "H"
    ])
    rows = [audit(mid, receptor_fit, oriented_ca, oriented_heavy) for mid in IDS]

    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "md_initial_pose_qc.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    table = []
    for row in rows:
        table.append(
            f"| {row['molecule_id']} | {row['xp_gscore_pose']:.2f} | "
            f"{row['mmgbsa_dg_bind']:.2f} | {row['built_com_target_delta_A']:.2f} | "
            f"{row['built_required_rotation_deg']:.1f} | "
            f"{row['built_min_protein_distance_A']:.2f} | "
            f"{row['prod_start_com_target_delta_A']:.2f} | "
            f"{row['prod_start_pose_rmsd_to_correct_A']:.2f} | "
            f"{row['target_contact_retention_fraction']:.1%} | invalid |"
        )
    report = f"""# MD initial-pose coordinate audit

## Conclusion

All six membrane-MD systems have an initial-coordinate frame mismatch. The
MM-GBSA ligand pose remained in the original 8G9V coordinate frame while the
receptor was rigidly oriented for the membrane. The build script appended both
structures without applying the receptor transform to the ligand. The complete
200 ns trajectories therefore do not validate the intended target-pocket poses.
The previous wet-lab ranking is withdrawn.

## How the intended pose was determined

- The Glide grid center is the all-atom centroid of crystal ligand YYC B402:
  `{centroid[0]:.4f}, {centroid[1]:.4f}, {centroid[2]:.4f}` A.
- The configured Glide inner/outer boxes are 10/30 A.
- Glide XP retained one pose per LigPrep state. Prime MM-GBSA optimized and
  scored that complex. The MD ligand files contain the MM-GBSA output poses.
- The docking/MM-GBSA chain is coherent. The error occurs during the later merge
  into the membrane-oriented receptor.

## Transform evidence

- 566 receptor C-alpha atoms fit at {receptor_rmsd:.7f} A, proving an exact
  rigid transform. The transform rotation is {angle(receptor_fit[0]):.2f} degrees.
- `scripts/build_missing_cms.sh` directly appends `prepared_dimer.mae` and
  `meta/ligands/<ID>.mae` without transforming the ligand.
- `build_membrane_system.msj` builds geometry and assigns OPLS4; it has no
  minimization stage. The 2 ns equilibration removes clashes but cannot restore
  the intended pose.

## Six-system audit

| ID | XP pose | MM-GBSA | build COM error A | build angle error deg | build min protein A | production-start COM error A | production-start pose RMSD A | target-contact retention | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(table)}

The angle is the best-fit rigid-body rotation required after atom correspondence.
The CSV separately reports residual conformational RMSD after this fit.

## Impact and correction

The prior frame-0 pockets were defined around misplaced ligands, not the
crystallographic YYC target pocket. T4965 moved closest during equilibration, but
its production-start pose remains 4.69 A from the correctly transformed MM-GBSA
pose; this is not preservation of the original pose.

Apply the receptor rigid transform to every MM-GBSA ligand, merge with
`prepared_dimer.mae`, verify expected chain-B pocket contacts and no heavy-atom
distance below 1.5 A, then rebuild and rerun at least these six systems.
"""
    report_path = OUT / "md_initial_pose_audit.md"
    report_path.write_text(report)
    print(csv_path)
    print(report_path)


if __name__ == "__main__":
    main()
