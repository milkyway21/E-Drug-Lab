#!/usr/bin/env python3
"""Transform all 40 MM-GBSA ligands into the membrane-receptor frame."""
from __future__ import annotations

import csv
import shutil

import numpy as np
from schrodinger import structure

from corrected_pose_common import (
    ANALYSIS_ROOT,
    BUILD_PROTOCOL,
    MANIFEST,
    MD_PROTOCOL,
    ORIGINAL_RECEPTOR,
    ORIENTED_RECEPTOR,
    SYSTEM_ROOT,
    load_ids,
    prebuild_pose_qc,
    read_structure,
    receptor_transform,
    rotation_angle,
    transformed_ligand,
    write_json,
)


def write_structure_once(path, models) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with structure.StructureWriter(str(path)) as writer:
        for model in models:
            writer.append(model)


def main() -> None:
    ids = load_ids()
    fit, matched, fit_rmsd = receptor_transform()
    oriented = read_structure(ORIENTED_RECEPTOR)
    SYSTEM_ROOT.mkdir(parents=True, exist_ok=True)
    ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)

    transform_record = {
        "mobile_receptor": str(ORIGINAL_RECEPTOR),
        "reference_receptor": str(ORIENTED_RECEPTOR),
        "matched_ca_atoms": matched,
        "fit_rmsd_A": fit_rmsd,
        "rotation_determinant": float(np.linalg.det(fit[0])),
        "rotation_angle_deg": rotation_angle(fit[0]),
        "rotation_matrix": fit[0].tolist(),
        "mobile_center": fit[1].tolist(),
        "reference_center": fit[2].tolist(),
    }
    write_json(ANALYSIS_ROOT / "receptor_transform.json", transform_record)

    rows = []
    for mid in ids:
        row = prebuild_pose_qc(mid, fit, oriented)
        work = SYSTEM_ROOT / mid
        work.mkdir(parents=True, exist_ok=True)
        ligand, _ = transformed_ligand(mid, fit)
        corrected_path = work / "corrected_ligand.mae"
        solute_path = work / "solute.mae"
        write_structure_once(corrected_path, [ligand])
        write_structure_once(solute_path, [oriented, ligand])
        for source, target in (
            (BUILD_PROTOCOL, work / "build.msj"),
            (MD_PROTOCOL, work / "md.msj"),
        ):
            if not target.exists():
                shutil.copy2(source, target)
            elif target.read_bytes() != source.read_bytes():
                raise RuntimeError(f"Refusing to overwrite changed protocol: {target}")
        row.update({
            "corrected_ligand": str(corrected_path),
            "solute_path": str(solute_path),
            "system_cms": str(work / f"{mid}-out.cms"),
        })
        rows.append(row)

    for path in (MANIFEST, ANALYSIS_ROOT / "corrected_pose_qc.csv"):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(f"Prepared and validated {len(rows)} corrected ligand poses")
    print(MANIFEST)


if __name__ == "__main__":
    main()
