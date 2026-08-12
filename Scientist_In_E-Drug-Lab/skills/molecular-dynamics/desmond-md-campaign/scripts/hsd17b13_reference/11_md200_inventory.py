#!/usr/bin/env python3
"""Inventory and validate the six HSD17B13 Phase-B 200 ns trajectories."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from schrodinger.application.desmond.packages import topo, traj


ROOT = Path(__file__).resolve().parents[1]
IDS_FILE = ROOT / "meta/phaseB200_top6.txt"
TRAJ_ROOT = ROOT / "04_trajectories/phaseB_200ns"
SEA_ROOT = ROOT / "05_analysis/phaseB_200ns"
DEFAULT_OUT = ROOT / "05_analysis/md200_selection/md_file_inventory.csv"

REQUIRED_SEA = (
    "PL_RMSD.dat",
    "P_RMSF.dat",
    "L_RMSF.dat",
    "L-Properties.dat",
    "PL-Contacts_HBond.dat",
    "PL-Contacts_Hydrophobic.dat",
    "PL-Contacts_Pi-Pi.dat",
    "PL-Contacts_Pi-Cation.dat",
    "PL-Contacts_Ionic.dat",
    "PL-Contacts_WaterBridge.dat",
)


def read_ids() -> list[str]:
    return [line.strip() for line in IDS_FILE.read_text().splitlines() if line.strip()]


def inventory_one(molecule_id: str) -> dict[str, object]:
    work = TRAJ_ROOT / molecule_id
    cms_path = work / f"{molecule_id}_202ns-out.cms"
    trj_path = work / f"HSD17B13_B200_{molecule_id}_6_trj"
    sea_dir = SEA_ROOT / molecule_id / "data"
    eaf_path = SEA_ROOT / molecule_id / f"{molecule_id}_B200_sea-out.eaf"
    expected_log = work / f"HSD17B13_B200_{molecule_id}_multisim.log"

    missing: list[str] = []
    notes: list[str] = []
    length_ns = np.nan
    frame_count = 0
    first_time_ns = np.nan
    last_time_ns = np.nan
    median_dt_ns = np.nan
    max_dt_ns = np.nan
    time_monotonic = False
    ligand_atoms = 0
    protein_ca_atoms = 0
    topology_readable = False
    trajectory_readable = False

    for path, label in (
        (cms_path, "final_cms"),
        (trj_path / "clickme.dtr", "trajectory_dtr"),
        (trj_path / "timekeys", "trajectory_timekeys"),
        (eaf_path, "sid_eaf"),
        (expected_log, "multisim_log"),
    ):
        if not path.exists():
            missing.append(label)

    sea_files = sorted(path.name for path in sea_dir.glob("*") if path.is_file())
    for filename in REQUIRED_SEA:
        if not (sea_dir / filename).exists():
            missing.append(f"sea:{filename}")

    if cms_path.exists():
        try:
            _, cms_model = topo.read_cms(str(cms_path))
            topology_readable = True
            ligand_atoms = len(cms_model.select_atom("res.ptype UNK"))
            protein_ca_atoms = len(
                cms_model.select_atom("protein and atom.ptype CA")
            )
            if ligand_atoms == 0:
                missing.append("ligand_selection:res.ptype_UNK")
            if protein_ca_atoms == 0:
                missing.append("protein_ca_selection")
        except Exception as exc:  # pragma: no cover - depends on binary input
            missing.append("cms_unreadable")
            notes.append(f"CMS read error: {type(exc).__name__}: {exc}")

    if trj_path.exists() and (trj_path / "clickme.dtr").exists():
        try:
            trajectory = traj.read_traj(str(trj_path))
            frame_count = len(trajectory)
            times = np.asarray([frame.time for frame in trajectory], dtype=float)
            if len(times):
                first_time_ns = float(times[0] / 1000.0)
                last_time_ns = float(times[-1] / 1000.0)
                length_ns = float((times[-1] - times[0]) / 1000.0)
            if len(times) >= 2:
                deltas = np.diff(times) / 1000.0
                time_monotonic = bool(np.all(deltas > 0.0))
                median_dt_ns = float(np.median(deltas))
                max_dt_ns = float(np.max(deltas))
            trajectory_readable = True
        except Exception as exc:  # pragma: no cover - depends on binary input
            missing.append("trajectory_unreadable")
            notes.append(f"DTR read error: {type(exc).__name__}: {exc}")

    complete = bool(
        trajectory_readable
        and topology_readable
        and np.isfinite(length_ns)
        and length_ns >= 190.0
        and frame_count >= 951
        and time_monotonic
        and np.isfinite(max_dt_ns)
        and max_dt_ns <= 0.41
        and ligand_atoms > 0
        and protein_ca_atoms > 0
    )
    trajectory_status = "valid" if complete else "trajectory_invalid"
    if complete:
        notes.append(
            "Continuous single 200 ns production trajectory; expected interval about 0.2 ns."
        )

    return {
        "molecule_id": molecule_id,
        "simulation_length_ns": length_ns,
        "trajectory_path": str(trj_path),
        "cms_path": str(cms_path),
        "sid_path": str(eaf_path),
        "analysis_files": json.dumps(sea_files, ensure_ascii=False),
        "trajectory_complete": complete,
        "trajectory_status": trajectory_status,
        "frame_count": frame_count,
        "first_time_ns": first_time_ns,
        "last_time_ns": last_time_ns,
        "median_frame_interval_ns": median_dt_ns,
        "max_frame_interval_ns": max_dt_ns,
        "frame_times_monotonic": time_monotonic,
        "topology_readable": topology_readable,
        "trajectory_readable": trajectory_readable,
        "ligand_atom_count": ligand_atoms,
        "protein_ca_atom_count": protein_ca_atoms,
        "missing_files": "; ".join(missing),
        "notes": " ".join(notes),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    rows = [inventory_one(molecule_id) for molecule_id in read_ids()]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    valid = sum(row["trajectory_complete"] for row in rows)
    print(f"Wrote {args.out}")
    print(f"Validated {valid}/{len(rows)} trajectories")
    for row in rows:
        print(
            f"{row['molecule_id']}: {row['trajectory_status']}, "
            f"frames={row['frame_count']}, length={row['simulation_length_ns']:.6f} ns, "
            f"missing={row['missing_files'] or 'none'}"
        )


if __name__ == "__main__":
    main()
