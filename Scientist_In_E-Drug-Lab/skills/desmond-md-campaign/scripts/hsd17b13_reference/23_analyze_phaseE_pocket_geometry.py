#!/usr/bin/env python3
"""Diagnose target-pocket retention in completed corrected-pose Phase E runs."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from schrodinger.application.desmond.packages import topo, traj


ROOT = Path(__file__).resolve().parents[1]
TRAJECTORY_ROOT = ROOT / "04_trajectories/phaseE_corrected_pose_2_50_all40_20260727"
ANALYSIS_ROOT = ROOT / "05_analysis/phaseE_corrected_pose_2_50_all40_20260727"
SEA_ROOT = ANALYSIS_ROOT / "sea"
OUTPUT = ANALYSIS_ROOT / "pocket_geometry"
QC_PATH = ANALYSIS_ROOT / "corrected_pose_qc.csv"
LATE_START_NS = 40.0
EARLY_END_NS = 10.0
DIRECT_TYPES = ("HBond", "Hydrophobic", "Pi-Pi", "Pi-Cation", "Ionic", "Metal")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MD200 = load_module("md200_geometry_helpers", ROOT / "scripts/12_analyze_md200.py")


def completed_attempt(molecule_id: str) -> Path:
    candidates = []
    for attempt in sorted((TRAJECTORY_ROOT / molecule_id).glob("attempt_*"), reverse=True):
        cms = attempt / f"{molecule_id}_52ns-out.cms"
        archives = list(attempt.glob("HSD17B13_E52C_*_6-out.tgz"))
        if cms.exists() and cms.stat().st_size > 1_000_000:
            if archives and archives[0].stat().st_size > 1_000_000:
                candidates.append(attempt)
    if not candidates:
        raise FileNotFoundError(f"{molecule_id}: no completed attempt")
    return candidates[0]


def trajectory_path(attempt: Path) -> Path:
    direct = sorted(attempt.glob("HSD17B13_E52C_*_6_trj"))
    if direct and (direct[0] / "clickme.dtr").exists():
        return direct[0]
    nested = sorted(attempt.glob("HSD17B13_E52C_*_6/*_trj"))
    if nested and (nested[0] / "clickme.dtr").exists():
        return nested[0]
    raise FileNotFoundError(f"No extracted production trajectory below {attempt}")


def completed_ids() -> list[str]:
    result = []
    for path in sorted(TRAJECTORY_ROOT.iterdir()):
        if not path.is_dir():
            continue
        try:
            trajectory_path(completed_attempt(path.name))
        except FileNotFoundError:
            continue
        result.append(path.name)
    return result


def parse_qc_pocket(value: str) -> set[tuple[str, int]]:
    result: set[tuple[str, int]] = set()
    for token in str(value).split(";"):
        match = re.fullmatch(r"([A-Za-z0-9_]+):[A-Za-z]+(-?\d+)", token.strip())
        if match and match.group(1) == "B":
            result.add((match.group(1), int(match.group(2))))
    return result


def residue_label(atom: Any) -> str:
    return f"{atom.chain.strip() or '_'}:{atom.pdbres.strip()}{int(atom.resnum)}"


def select_target_pocket(cms: Any, residues: set[tuple[str, int]]):
    heavy = [
        atom.index
        for atom in cms.atom
        if (atom.chain.strip(), int(atom.resnum)) in residues and atom.element != "H"
    ]
    ca = [aid for aid in heavy if cms.atom[aid].pdbname.strip() == "CA"]
    if len(heavy) < 10 or len(ca) < 3:
        raise ValueError(f"Target pocket selection too small: heavy={len(heavy)} CA={len(ca)}")
    return heavy, ca


def unwrap_near_pocket(
    ligand: np.ndarray,
    pocket: np.ndarray,
    box: np.ndarray,
    masses: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ligand = MD200.unwrap_group(ligand, box)
    pocket = MD200.unwrap_group(pocket, box)
    ligand_com = np.average(ligand, axis=0, weights=masses)
    pocket_center = pocket.mean(axis=0)
    raw_delta = ligand_com - pocket_center
    nearest_delta = MD200.minimum_image(raw_delta, box)
    ligand += nearest_delta - raw_delta
    return ligand, pocket, nearest_delta


def sea_data_dir(molecule_id: str) -> Path:
    root = SEA_ROOT / molecule_id
    for path in (root / "official_data", root / "data"):
        if (path / "PL_RMSD.dat").exists() and (path / "PL-Contacts_HBond.dat").exists():
            return path
    raise FileNotFoundError(f"{molecule_id}: no complete SEA data directory")


def contact_metrics(molecule_id: str, times: np.ndarray) -> dict[str, Any]:
    data_dir = sea_data_dir(molecule_id)
    n_frames = len(times)
    residue_frames: dict[str, set[int]] = defaultdict(set)
    chain_frames: dict[str, set[int]] = defaultdict(set)
    for contact_type in DIRECT_TYPES:
        rows = MD200.parse_contact_file(
            data_dir / f"PL-Contacts_{contact_type}.dat", contact_type, n_frames
        )
        for row in rows:
            frame = int(row["frame"])
            residue_frames[row["residue"]].add(frame)
            chain_frames[row["chain"]].add(frame)

    early_mask = times <= EARLY_END_NS
    late_mask = times >= LATE_START_NS
    n_early = max(int(early_mask.sum()), 1)
    n_late = max(int(late_mask.sum()), 1)

    early = {
        residue: sum(bool(early_mask[frame]) for frame in frames) / n_early
        for residue, frames in residue_frames.items()
        if residue.startswith("B:")
    }
    late = {
        residue: sum(bool(late_mask[frame]) for frame in frames) / n_late
        for residue, frames in residue_frames.items()
        if residue.startswith("B:")
    }
    ranked = sorted(early, key=early.get, reverse=True)
    key_residues = [residue for residue in ranked if early[residue] >= 0.30][:6]
    if len(key_residues) < 2:
        key_residues = [residue for residue in ranked if early[residue] >= 0.10][:3]
    denominator = sum(early.get(residue, 0.0) for residue in key_residues)
    retained = sum(
        min(early.get(residue, 0.0), late.get(residue, 0.0))
        for residue in key_residues
    )
    key_retention = retained / denominator if denominator else math.nan
    new_stable = [
        residue
        for residue in sorted(late, key=late.get, reverse=True)
        if late[residue] >= 0.30 and early.get(residue, 0.0) < 0.10
    ]

    def coverage(chain: str, mask: np.ndarray) -> float:
        denominator = max(int(mask.sum()), 1)
        return sum(bool(mask[frame]) for frame in chain_frames.get(chain, set())) / denominator

    return {
        "b_direct_coverage_full": len(chain_frames.get("B", set())) / max(n_frames, 1),
        "b_direct_coverage_late": coverage("B", late_mask),
        "a_direct_coverage_full": len(chain_frames.get("A", set())) / max(n_frames, 1),
        "a_direct_coverage_late": coverage("A", late_mask),
        "initial_key_contact_retention": key_retention,
        "initial_key_contacts": ";".join(
            f"{residue}:{early.get(residue, 0.0):.2f}->{late.get(residue, 0.0):.2f}"
            for residue in key_residues
        ),
        "new_stable_b_contacts": ";".join(
            f"{residue}:{late[residue]:.2f}" for residue in new_stable[:6]
        ),
    }


def input_to_production_rmsd(
    input_cms: Any,
    production_cms: Any,
    first_frame: Any,
    protein_ca_aids: list[int],
    ligand_aids: list[int],
    pocket_heavy_aids: list[int],
    masses: np.ndarray,
) -> tuple[float, float]:
    reference_ca = np.asarray([input_cms.atom[aid].xyz for aid in protein_ca_aids], float)
    mobile_ca = first_frame.pos(
        topo.aids2gids(production_cms, protein_ca_aids, include_pseudoatoms=False)
    )
    rotation, mobile_center, reference_center = MD200.kabsch(mobile_ca, reference_ca)
    box = np.asarray(first_frame.box, float)
    ligand, pocket, _ = unwrap_near_pocket(
        first_frame.pos(topo.aids2gids(production_cms, ligand_aids, include_pseudoatoms=False)),
        first_frame.pos(
            topo.aids2gids(production_cms, pocket_heavy_aids, include_pseudoatoms=False)
        ),
        box,
        masses,
    )
    ligand = MD200.apply_alignment(ligand, rotation, mobile_center, reference_center)
    pocket = MD200.apply_alignment(pocket, rotation, mobile_center, reference_center)
    reference_ligand = np.asarray([input_cms.atom[aid].xyz for aid in ligand_aids], float)
    pose_rmsd = MD200.rmsd(ligand, reference_ligand)
    reference_pocket = np.asarray(
        [input_cms.atom[aid].xyz for aid in pocket_heavy_aids], float
    )
    reference_delta = np.average(reference_ligand, axis=0, weights=masses) - reference_pocket.mean(axis=0)
    production_delta = np.average(ligand, axis=0, weights=masses) - pocket.mean(axis=0)
    return pose_rmsd, float(np.linalg.norm(production_delta - reference_delta))


def classify(row: dict[str, Any]) -> tuple[str, str]:
    b_late = row["b_direct_coverage_late"]
    min_late = row["target_pocket_min_distance_late_median"]
    com_delta = row["target_pocket_com_delta"]
    key = row["initial_key_contact_retention"]
    source_fraction = row["source_pocket_residue_fraction_late"]
    if min_late > 10.0 and com_delta > 12.0 and source_fraction < 0.05:
        return (
            "pocket_exit",
            "left the target pocket; residual contacts are on a different protein surface",
        )
    if min_late > 5.0 and b_late < 0.25 and com_delta > 5.0:
        return "pocket_exit", "target B-chain contact and proximity both lost"
    if b_late >= 0.70 and min_late <= 4.5:
        if com_delta <= 2.5 and (not math.isfinite(key) or key >= 0.35):
            return "target_pocket_retained", "target-pocket position and initial anchors retained"
        return "contact_retained_rearrangement", "still contacts target pocket after pose rearrangement"
    if min_late <= 4.5 and b_late >= 0.40:
        return "partial_displacement", "edge/partial target-pocket occupancy remains"
    return "inconclusive_displacement", "target-pocket evidence is conflicting or insufficient"


def analyze_one(molecule_id: str, qc: dict[str, str]) -> tuple[dict[str, Any], pd.DataFrame]:
    attempt = completed_attempt(molecule_id)
    input_cms_path = attempt / f"{molecule_id}-out.cms"
    final_cms_path = attempt / f"{molecule_id}_52ns-out.cms"
    trj_path = trajectory_path(attempt)
    _, input_cms = topo.read_cms(str(input_cms_path))
    _, cms = topo.read_cms(str(final_cms_path))
    trajectory = traj.read_traj(str(trj_path))
    times = np.asarray([frame.time / 1000.0 for frame in trajectory], float)

    protein_ca_aids = cms.select_atom("protein and atom.ptype CA")
    ligand_aids = cms.select_atom("res.ptype UNK and not atom.ele H")
    ligand_gids = topo.aids2gids(cms, ligand_aids, include_pseudoatoms=False)
    masses = np.asarray([cms.atom[aid].atomic_weight for aid in ligand_aids], float)
    target_residues = parse_qc_pocket(qc["contact_residues_4A"])
    pocket_heavy_aids, pocket_ca_aids = select_target_pocket(cms, target_residues)
    pocket_heavy_gids = topo.aids2gids(cms, pocket_heavy_aids, include_pseudoatoms=False)
    pocket_ca_gids = topo.aids2gids(cms, pocket_ca_aids, include_pseudoatoms=False)

    eq_pose_rmsd, eq_relative_shift = input_to_production_rmsd(
        input_cms,
        cms,
        trajectory[0],
        protein_ca_aids,
        ligand_aids,
        pocket_heavy_aids,
        masses,
    )

    com_distances = []
    min_distances = []
    source_residue_fractions = []
    for frame in trajectory:
        box = np.asarray(frame.box, float)
        ligand, pocket, delta = unwrap_near_pocket(
            frame.pos(ligand_gids), frame.pos(pocket_heavy_gids), box, masses
        )
        pair_delta = ligand[:, None, :] - pocket[None, :, :]
        distances = np.linalg.norm(MD200.minimum_image(pair_delta, box), axis=2)
        contacted_residues = {
            (cms.atom[pocket_heavy_aids[index]].chain.strip(), int(cms.atom[pocket_heavy_aids[index]].resnum))
            for index in np.where(np.min(distances, axis=0) <= 4.0)[0]
        }
        com_distances.append(float(np.linalg.norm(delta)))
        min_distances.append(float(np.min(distances)))
        source_residue_fractions.append(len(contacted_residues) / len(target_residues))

    trace = pd.DataFrame(
        {
            "molecule_id": molecule_id,
            "frame": np.arange(len(trajectory)),
            "time_ns": times,
            "target_pocket_com_distance": com_distances,
            "target_pocket_min_distance": min_distances,
            "source_pocket_residue_fraction_4A": source_residue_fractions,
        }
    )
    early2 = trace[trace["time_ns"] <= 2.0]
    late = trace[trace["time_ns"] >= LATE_START_NS]
    contact = contact_metrics(molecule_id, times)
    com_initial = float(early2["target_pocket_com_distance"].median())
    com_late = float(late["target_pocket_com_distance"].median())
    row: dict[str, Any] = {
        "molecule_id": molecule_id,
        "attempt": attempt.name,
        "n_frames": len(trajectory),
        "production_ns": float(times.max()),
        "individual_pose_source": qc["source_ligand"],
        "initial_chain_b_contact_residues": int(qc["chain_B_contact_residues"]),
        "prebuild_min_protein_distance_A": float(qc["min_protein_heavy_distance_A"]),
        "prebuild_clash_pairs_lt_1p5A": int(qc["clash_pairs_lt_1p5A"]),
        "equilibration_pose_rmsd_A": eq_pose_rmsd,
        "equilibration_relative_com_shift_A": eq_relative_shift,
        "target_pocket_com_initial": com_initial,
        "target_pocket_com_late": com_late,
        "target_pocket_com_delta": com_late - com_initial,
        "target_pocket_min_distance_late_median": float(
            late["target_pocket_min_distance"].median()
        ),
        "target_pocket_min_distance_late_p95": float(
            late["target_pocket_min_distance"].quantile(0.95)
        ),
        "source_pocket_residue_fraction_late": float(
            late["source_pocket_residue_fraction_4A"].mean()
        ),
        **contact,
    }
    diagnosis, evidence = classify(row)
    row["pocket_diagnosis"] = diagnosis
    row["diagnosis_evidence"] = evidence
    return row, trace


def make_plot(summary: pd.DataFrame, traces: pd.DataFrame, output: Path) -> None:
    order = summary.sort_values("target_pocket_com_delta")["molecule_id"].tolist()
    columns = 4
    rows = math.ceil(len(order) / columns)
    figure, axes = plt.subplots(rows, columns, figsize=(14.0, 2.65 * rows), sharex=True)
    axes = np.asarray(axes).reshape(-1)
    diagnoses = summary.set_index("molecule_id")["pocket_diagnosis"].to_dict()
    colors = {
        "target_pocket_retained": "#2A6F97",
        "contact_retained_rearrangement": "#F56E1A",
        "partial_displacement": "#8C6D31",
        "pocket_exit": "#B23A48",
        "inconclusive_displacement": "#6C757D",
    }
    for axis, molecule_id in zip(axes, order):
        subset = traces[traces["molecule_id"] == molecule_id]
        diagnosis = diagnoses[molecule_id]
        axis.plot(
            subset["time_ns"],
            subset["target_pocket_com_distance"],
            color=colors[diagnosis],
            linewidth=1.35,
        )
        axis.axvspan(40, 50, color="#D9D9D9", alpha=0.35, linewidth=0)
        axis.set_title(f"{molecule_id} | {diagnosis.replace('_', ' ')}", fontsize=8.5)
        axis.grid(axis="y", color="#E6E6E6", linewidth=0.6)
    for axis in axes[len(order):]:
        axis.axis("off")
    figure.supxlabel("Production time (ns)")
    figure.supylabel("Ligand-target pocket COM distance (A)")
    figure.tight_layout()
    figure.savefig(output, dpi=240, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*")
    args = parser.parse_args()
    ids = args.ids or completed_ids()
    qc_rows = {
        row["molecule_id"]: row
        for row in csv.DictReader(QC_PATH.open())
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = []
    traces = []
    failures = {}
    for molecule_id in ids:
        print(f"Analyze target-pocket geometry: {molecule_id}", flush=True)
        try:
            row, trace = analyze_one(molecule_id, qc_rows[molecule_id])
            rows.append(row)
            traces.append(trace)
            print(
                f"  {row['pocket_diagnosis']} COM_delta={row['target_pocket_com_delta']:+.2f} "
                f"B_late={row['b_direct_coverage_late']:.0%} "
                f"eq_RMSD={row['equilibration_pose_rmsd_A']:.2f}",
                flush=True,
            )
        except Exception as error:
            failures[molecule_id] = f"{type(error).__name__}: {error}"
            print(f"  FAIL {failures[molecule_id]}", flush=True)
    if not rows:
        raise SystemExit("No molecule completed successfully")
    summary = pd.DataFrame(rows).sort_values(
        ["pocket_diagnosis", "target_pocket_com_delta", "molecule_id"]
    )
    all_traces = pd.concat(traces, ignore_index=True)
    summary.to_csv(OUTPUT / "phaseE_target_pocket_diagnostics.csv", index=False)
    all_traces.to_csv(OUTPUT / "phaseE_target_pocket_traces.csv", index=False)
    make_plot(summary, all_traces, OUTPUT / "phaseE_target_pocket_com_overview.png")
    (OUTPUT / "analysis_failures.json").write_text(
        json.dumps(failures, indent=2, sort_keys=True) + "\n"
    )
    print(f"Wrote {len(summary)} results to {OUTPUT}")


if __name__ == "__main__":
    main()
