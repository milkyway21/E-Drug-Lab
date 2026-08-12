#!/usr/bin/env python3
"""Export heatmap-ready and dynamics-ready CSV tables for Phase F full20."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BATCH = "phaseF_medoid_pose_2_200_top16_20260728"
DEFAULT_SOURCE = ROOT / "05_analysis" / BATCH
DEFAULT_ASSESSMENT = DEFAULT_SOURCE / "full20_200ns_assessment"
DEFAULT_MANIFEST = DEFAULT_SOURCE / "phaseF_full20_manifest.csv"
DEFAULT_OUTPUT = DEFAULT_ASSESSMENT / "tables_only_2plus200ns_20"
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--assessment", type=Path, default=DEFAULT_ASSESSMENT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-count", type=int, default=20)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def read_protein_rmsf(path: Path, molecule_id: str) -> pd.DataFrame:
    rows = []
    for line in path.read_text(errors="ignore").splitlines():
        tokens = line.split()
        if not tokens or not tokens[0].isdigit() or len(tokens) < 9:
            continue
        residue_name, _, residue_num = tokens[2].rpartition("_")
        rows.append(
            {
                "molecule_id": molecule_id,
                "residue_index": int(tokens[0]),
                "chain": tokens[1],
                "resname": residue_name,
                "resnum": int(residue_num) if residue_num.lstrip("-").isdigit() else residue_num,
                "residue_id": f"{tokens[1]}:{residue_name}{residue_num}",
                "ligand_contact": tokens[3] == "Yes",
                "ca_rmsf_A": float(tokens[4]),
                "backbone_rmsf_A": float(tokens[5]),
                "sidechain_rmsf_A": float(tokens[6]),
                "all_heavy_rmsf_A": float(tokens[7]),
                "bfactor": float(tokens[8]),
            }
        )
    return pd.DataFrame(rows)


def read_ligand_rmsf(path: Path, molecule_id: str) -> pd.DataFrame:
    rows = []
    for line in path.read_text(errors="ignore").splitlines():
        tokens = line.split()
        if not tokens or not tokens[0].isdigit() or len(tokens) < 3:
            continue
        rows.append(
            {
                "molecule_id": molecule_id,
                "atom_index": int(tokens[0]),
                "rmsf_wrt_protein_A": float(tokens[-2]),
                "rmsf_wrt_ligand_A": float(tokens[-1]),
            }
        )
    return pd.DataFrame(rows)


def read_ligand_properties(path: Path, molecule_id: str) -> pd.DataFrame:
    columns = ["frame", "rmsd_A", "rgyr_A", "intrahb", "molsa_A2", "sasa_A2", "psa_A2"]
    table = pd.read_csv(path, sep=r"\s+", comment="#", header=None, names=columns)
    for column in columns:
        table[column] = pd.to_numeric(table[column], errors="coerce")
    table = table.dropna(subset=["frame"]).astype({"frame": int})
    table.insert(0, "molecule_id", molecule_id)
    return table


def add_metadata(table: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    return table.merge(metadata, on="molecule_id", how="left", validate="many_to_one")


def heatmap(
    contacts: pd.DataFrame,
    order: list[str],
    metadata: pd.DataFrame,
    value: str,
    by_type: bool,
) -> pd.DataFrame:
    feature = "contact_feature" if by_type else "residue"
    matrix = contacts.pivot_table(
        index="molecule_id",
        columns=feature,
        values=value,
        aggfunc="max",
        fill_value=0.0,
    ).reindex(order, fill_value=0.0)
    matrix.columns.name = None
    return matrix.reset_index().merge(metadata, on="molecule_id", how="left")


def write_table(
    table: pd.DataFrame,
    path: Path,
    purpose: str,
    source: str,
    records: list[dict[str, object]],
) -> None:
    table.to_csv(path, index=False)
    records.append(
        {
            "file": path.name,
            "purpose": purpose,
            "rows": len(table),
            "columns": len(table.columns),
            "molecule_count": (
                table["molecule_id"].astype(str).nunique()
                if "molecule_id" in table.columns
                else ""
            ),
            "source": source,
            "sha256": sha256(path),
        }
    )


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    assessment = args.assessment.resolve()
    selection_path = args.manifest.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    decisions = require_table(assessment / "md200_decision_table.csv")
    traces = require_table(assessment / "md200_traces.csv")
    contacts = require_table(assessment / "md200_contacts.csv")
    transitions = require_table(assessment / "md200_transitions.csv")
    selection = require_table(selection_path)

    decisions = decisions.sort_values("rank", kind="stable")
    order = decisions["molecule_id"].astype(str).tolist()
    if len(order) != args.expected_count or len(set(order)) != args.expected_count:
        raise ValueError(f"Expected {args.expected_count} unique decisions, found {len(set(order))}")
    expected_ids = set(order)
    for label, table in (("traces", traces), ("selection manifest", selection)):
        observed = set(table["molecule_id"].astype(str))
        if observed != expected_ids:
            raise ValueError(f"{label} molecule coverage differs from decision table")

    frame_counts = traces.groupby("molecule_id")["frame"].nunique()
    if (frame_counts < 1001).any():
        raise ValueError(f"Incomplete dynamics traces: {frame_counts[frame_counts < 1001].to_dict()}")

    metadata = decisions[["molecule_id", "rank", "md_class"]].copy()
    metadata["class_letter"] = metadata["md_class"].astype(str).str[:1]
    traces = add_metadata(traces, metadata)

    protein_tables = []
    ligand_tables = []
    property_tables = []
    sea_root = source / "sea"
    for molecule_id in order:
        molecule_root = sea_root / molecule_id
        official = molecule_root / "official_data"
        ordinary = molecule_root / "data"
        data_dir = official if all(
            (official / name).is_file()
            for name in ("PL_RMSD.dat", "P_RMSF.dat", "L_RMSF.dat", "L-Properties.dat")
        ) else ordinary
        required = {
            "protein RMSF": data_dir / "P_RMSF.dat",
            "ligand RMSF": data_dir / "L_RMSF.dat",
            "ligand properties": data_dir / "L-Properties.dat",
        }
        missing = [str(path) for path in required.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"{molecule_id}: missing SEA tables: {missing}")
        protein_tables.append(read_protein_rmsf(required["protein RMSF"], molecule_id))
        ligand_tables.append(read_ligand_rmsf(required["ligand RMSF"], molecule_id))
        property_tables.append(read_ligand_properties(required["ligand properties"], molecule_id))

    protein_rmsf = add_metadata(pd.concat(protein_tables, ignore_index=True), metadata)
    ligand_rmsf = add_metadata(pd.concat(ligand_tables, ignore_index=True), metadata)
    properties = pd.concat(property_tables, ignore_index=True)
    properties = properties.merge(
        traces[["molecule_id", "frame", "time_ns"]],
        on=["molecule_id", "frame"],
        how="left",
        validate="one_to_one",
    )
    if properties["time_ns"].isna().any():
        raise ValueError("Ligand-property frames do not map one-to-one to dynamics times")
    property_columns = list(properties.columns)
    property_columns.insert(2, property_columns.pop(property_columns.index("time_ns")))
    properties = add_metadata(properties[property_columns], metadata)
    property_counts = properties.groupby("molecule_id")["frame"].nunique()
    if (property_counts < 1001).any():
        raise ValueError(f"Incomplete ligand properties: {property_counts[property_counts < 1001].to_dict()}")

    contacts = add_metadata(contacts, metadata)
    residue_pattern = re.compile(r"^([^:]+):([A-Za-z0-9]+?)(-?\d+[A-Za-z]?)$")
    parsed = contacts["residue"].astype(str).str.extract(residue_pattern)
    contacts.insert(3, "chain", parsed[0].fillna(""))
    contacts.insert(4, "resname", parsed[1].fillna(""))
    contacts.insert(5, "resnum", parsed[2].fillna(""))
    contacts["contact_feature"] = contacts["contact_type"].astype(str) + "|" + contacts["residue"].astype(str)

    heat_by_type_full = heatmap(contacts, order, metadata, "occupancy_full", True)
    heat_by_type_late = heatmap(contacts, order, metadata, "occupancy_late", True)
    heat_max_full = heatmap(contacts, order, metadata, "occupancy_full", False)
    heat_max_late = heatmap(contacts, order, metadata, "occupancy_late", False)
    transitions = add_metadata(transitions, metadata)

    validation_rows = []
    trajectory_root = ROOT / "04_trajectories" / BATCH
    for molecule_id in order:
        found = None
        for attempt in sorted((trajectory_root / molecule_id).glob("attempt_*"), reverse=True):
            path = attempt / "attempt_validation.json"
            if path.is_file() and json.loads(path.read_text()).get("valid"):
                found = path
                break
        if found is None:
            raise FileNotFoundError(f"{molecule_id}: no valid attempt_validation.json")
        record = json.loads(found.read_text())
        record["molecule_id"] = molecule_id
        validation_rows.append(record)
    validations = add_metadata(pd.DataFrame(validation_rows), metadata)

    records: list[dict[str, object]] = []
    write_table(decisions, output / "01_molecule_decisions.csv", "One-row 200 ns classification, score, pocket stability, contact, and ranking metrics.", str(assessment / "md200_decision_table.csv"), records)
    write_table(traces, output / "02_dynamics_timeseries.csv", "Frame-level protein, pocket, and ligand RMSD; pocket distances; ligand properties; and contact traces.", str(assessment / "md200_traces.csv"), records)
    write_table(protein_rmsf, output / "03_protein_residue_rmsf.csv", "Per-residue protein RMSF for residue-level dynamics and heatmaps.", "SEA */official_data/P_RMSF.dat preferred", records)
    write_table(ligand_rmsf, output / "04_ligand_atom_rmsf.csv", "Per-ligand-atom RMSF relative to protein and ligand fits.", "SEA */official_data/L_RMSF.dat preferred", records)
    write_table(properties, output / "05_ligand_properties_timeseries.csv", "Frame-level ligand RMSD, radius of gyration, intramolecular H bonds, MolSA, SASA, and PSA.", "SEA */official_data/L-Properties.dat preferred", records)
    write_table(contacts, output / "06_residue_contacts_long.csv", "Long-form residue/contact-type occupancies over full, early, and final-50-ns windows.", str(assessment / "md200_contacts.csv"), records)
    write_table(heat_by_type_full, output / "07_residue_contact_heatmap_by_type_full.csv", "Heatmap matrix of full-trajectory occupancy by contact type and residue.", "Derived from 06_residue_contacts_long.csv", records)
    write_table(heat_by_type_late, output / "08_residue_contact_heatmap_by_type_late.csv", "Heatmap matrix of final-50-ns occupancy by contact type and residue.", "Derived from 06_residue_contacts_long.csv", records)
    write_table(heat_max_full, output / "09_residue_contact_heatmap_max_full.csv", "Heatmap matrix of maximum full-trajectory occupancy across contact types per residue.", "Derived from 06_residue_contacts_long.csv", records)
    write_table(heat_max_late, output / "10_residue_contact_heatmap_max_late.csv", "Heatmap matrix of maximum final-50-ns occupancy across contact types per residue.", "Derived from 06_residue_contacts_long.csv", records)
    write_table(transitions, output / "11_pose_transitions.csv", "Detected pose or protein transitions and before/after evidence.", str(assessment / "md200_transitions.csv"), records)
    write_table(validations, output / "12_trajectory_validation.csv", "Hard 200 ns trajectory continuity, frame count, CMS, and topology validation.", "Validated attempt JSON records", records)
    write_table(selection, output / "13_selection_and_medoid_manifest.csv", "Selection, source medoid, docking, diversity, topology, and input-QC provenance.", str(selection_path), records)

    manifest_path = output / "00_table_manifest.csv"
    pd.DataFrame(records).to_csv(manifest_path, index=False)
    print(f"Exported {len(records)} analysis tables plus manifest to {output}")
    print(f"Molecules: {len(expected_ids)}; files: {len(list(output.glob('*.csv')))}")


if __name__ == "__main__":
    main()
