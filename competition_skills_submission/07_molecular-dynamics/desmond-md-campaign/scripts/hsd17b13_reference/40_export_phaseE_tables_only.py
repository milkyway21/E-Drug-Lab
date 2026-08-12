#!/usr/bin/env python3
"""Export a flat, tables-only analysis package for all 40 Phase E trajectories."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BATCH = "phaseE_corrected_pose_2_50_all40_20260727"
DEFAULT_SOURCE = ROOT / "05_analysis" / BATCH
DEFAULT_OUTPUT = DEFAULT_SOURCE / "tables_only_2plus50ns_20260731"
FRAME_INTERVAL_NS = 0.2

DIAGNOSIS_CLASS = {
    "target_pocket_retained": "A",
    "contact_retained_rearrangement": "B",
    "inconclusive_displacement": "C",
    "pocket_exit": "D",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
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
                "resnum": int(residue_num) if residue_num.isdigit() else -1,
                "ligand_contact": tokens[3] == "Yes",
                "ca_rmsf_A": float(tokens[4]),
                "backbone_rmsf_A": float(tokens[5]),
                "sidechain_rmsf_A": float(tokens[6]),
                "all_heavy_rmsf_A": float(tokens[7]),
                "bfactor": float(tokens[8]),
            }
        )
    table = pd.DataFrame(rows)
    if not table.empty:
        table.insert(
            5,
            "residue_id",
            table["chain"].astype(str)
            + ":"
            + table["resname"].astype(str)
            + table["resnum"].astype(str),
        )
    return table


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
    table.insert(2, "time_ns", table["frame"] * FRAME_INTERVAL_NS)
    return table


def add_class(table: pd.DataFrame, classes: pd.DataFrame) -> pd.DataFrame:
    return table.merge(classes, on="molecule_id", how="left", validate="many_to_one")


def write_table(
    table: pd.DataFrame,
    path: Path,
    purpose: str,
    source: str,
    manifest: list[dict[str, object]],
) -> None:
    table.to_csv(path, index=False)
    manifest.append(
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
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    metrics_path = source / "summary/md27_metrics.csv"
    traces_path = source / "summary/md27_rmsd_traces.csv"
    contacts_path = source / "summary/md27_contacts.csv"
    pocket_summary_path = source / "pocket_geometry/phaseE_target_pocket_diagnostics.csv"
    pocket_traces_path = source / "pocket_geometry/phaseE_target_pocket_traces.csv"

    metrics = require_table(metrics_path)
    traces = require_table(traces_path)
    contacts = require_table(contacts_path)
    pocket_summary = require_table(pocket_summary_path)
    pocket_traces = require_table(pocket_traces_path)
    pose_qc = require_table(source / "corrected_pose_qc.csv")
    build_status = require_table(source / "build_status.csv")
    md_status = require_table(source / "md_queue_status.csv")

    expected_ids = set(metrics["molecule_id"].astype(str))
    if len(expected_ids) != 40:
        raise ValueError(f"Expected 40 molecules, found {len(expected_ids)}")
    for label, table in (
        ("RMSD traces", traces),
        ("contacts", contacts),
        ("pocket summary", pocket_summary),
        ("pocket traces", pocket_traces),
        ("pose QC", pose_qc),
        ("build status", build_status),
        ("MD status", md_status),
    ):
        observed = set(table["molecule_id"].astype(str))
        if observed != expected_ids:
            raise ValueError(f"{label} molecule coverage differs from the 40-molecule metrics table")

    classes = pocket_summary[["molecule_id", "pocket_diagnosis"]].copy()
    classes["md_class"] = classes["pocket_diagnosis"].map(DIAGNOSIS_CLASS)
    if classes["md_class"].isna().any():
        unknown = classes.loc[classes["md_class"].isna(), "pocket_diagnosis"].unique()
        raise ValueError(f"Unknown pocket diagnoses: {unknown.tolist()}")

    order = metrics.sort_values("biochemical_rank", kind="stable")["molecule_id"].astype(str).tolist()
    sea_root = source / "sea"
    protein_tables = []
    ligand_tables = []
    property_tables = []
    for molecule_id in order:
        molecule_root = sea_root / molecule_id
        official_data = molecule_root / "official_data"
        data_dir = (
            official_data
            if (official_data / "PL_RMSD.dat").is_file()
            else molecule_root / "data"
        )
        required = {
            "protein RMSF": data_dir / "P_RMSF.dat",
            "ligand RMSF": data_dir / "L_RMSF.dat",
            "ligand properties": data_dir / "L-Properties.dat",
        }
        missing = [str(path) for path in required.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"{molecule_id}: missing SEA analysis tables: {missing}")
        protein_tables.append(read_protein_rmsf(required["protein RMSF"], molecule_id))
        ligand_tables.append(read_ligand_rmsf(required["ligand RMSF"], molecule_id))
        property_tables.append(read_ligand_properties(required["ligand properties"], molecule_id))

    protein_rmsf = add_class(pd.concat(protein_tables, ignore_index=True), classes)
    ligand_rmsf = add_class(pd.concat(ligand_tables, ignore_index=True), classes)
    ligand_properties = add_class(pd.concat(property_tables, ignore_index=True), classes)
    traces = add_class(traces, classes)
    pocket_traces = add_class(pocket_traces, classes)

    contacts = add_class(contacts, classes)
    contacts["residue_id"] = (
        contacts["chain"].astype(str)
        + ":"
        + contacts["resname"].astype(str)
        + contacts["resnum"].astype(str)
    )
    contacts["heatmap_feature"] = contacts["contact_type"].astype(str) + "|" + contacts["residue_id"]

    by_type = contacts.pivot_table(
        index="molecule_id",
        columns="heatmap_feature",
        values="occupancy",
        aggfunc="max",
        fill_value=0.0,
    ).reindex(order, fill_value=0.0)
    by_type.columns.name = None
    by_type = by_type.reset_index().merge(classes, on="molecule_id", how="left")

    max_residue = (
        contacts.groupby(["molecule_id", "residue_id"], as_index=False)["occupancy"].max()
        .pivot(index="molecule_id", columns="residue_id", values="occupancy")
        .fillna(0.0)
        .reindex(order, fill_value=0.0)
    )
    max_residue.columns.name = None
    max_residue = max_residue.reset_index().merge(classes, on="molecule_id", how="left")

    manifest: list[dict[str, object]] = []
    write_table(
        metrics.merge(classes, on="molecule_id", how="left", validate="one_to_one"),
        output / "01_molecule_metrics.csv",
        "One row per molecule: RMSD, RMSF, contact, ligand-property, docking, and triage metrics.",
        str(metrics_path),
        manifest,
    )
    write_table(
        traces,
        output / "02_rmsd_timeseries.csv",
        "Frame-level protein and ligand RMSD time series for dynamics plots.",
        str(traces_path),
        manifest,
    )
    write_table(
        protein_rmsf,
        output / "03_protein_residue_rmsf.csv",
        "Per-residue protein RMSF values for all molecules.",
        "SEA */official_data/P_RMSF.dat preferred, parsed and combined",
        manifest,
    )
    write_table(
        ligand_rmsf,
        output / "04_ligand_atom_rmsf.csv",
        "Per-atom ligand RMSF relative to protein and ligand fits.",
        "SEA */official_data/L_RMSF.dat preferred, parsed and combined",
        manifest,
    )
    write_table(
        ligand_properties,
        output / "05_ligand_properties_timeseries.csv",
        "Frame-level ligand RMSD, radius of gyration, intramolecular H-bonds, MolSA, SASA, and PSA.",
        "SEA */official_data/L-Properties.dat preferred, parsed and combined",
        manifest,
    )
    write_table(
        contacts,
        output / "06_residue_contacts_long.csv",
        "Long-form per-molecule, per-residue, per-contact-type occupancy table.",
        str(contacts_path),
        manifest,
    )
    write_table(
        by_type,
        output / "07_residue_contact_heatmap_by_type.csv",
        "Heatmap-ready matrix; columns are contact_type|chain:residue and values are occupancies.",
        "Derived from 06_residue_contacts_long.csv",
        manifest,
    )
    write_table(
        max_residue,
        output / "08_residue_contact_heatmap_max.csv",
        "Heatmap-ready matrix using maximum occupancy across contact types per residue.",
        "Derived from 06_residue_contacts_long.csv",
        manifest,
    )
    write_table(
        pocket_traces,
        output / "09_pocket_geometry_timeseries.csv",
        "Frame-level target-pocket COM distance, minimum distance, and source-residue retention.",
        str(pocket_traces_path),
        manifest,
    )
    write_table(
        pocket_summary.merge(
            classes[["molecule_id", "md_class"]],
            on="molecule_id",
            how="left",
            validate="one_to_one",
        ),
        output / "10_pocket_geometry_summary.csv",
        "Pocket-retention summary and A/B/C/D classification evidence.",
        str(pocket_summary_path),
        manifest,
    )
    write_table(
        pose_qc,
        output / "11_corrected_pose_qc.csv",
        "Corrected-pose clash, contact, docking, and source QC table.",
        str(source / "corrected_pose_qc.csv"),
        manifest,
    )
    write_table(
        build_status,
        output / "12_system_build_status.csv",
        "Post-build system integrity and pose consistency table.",
        str(source / "build_status.csv"),
        manifest,
    )
    write_table(
        md_status,
        output / "13_md_queue_status.csv",
        "Final 2+50 ns queue completion status.",
        str(source / "md_queue_status.csv"),
        manifest,
    )

    manifest_path = output / "00_table_manifest.csv"
    pd.DataFrame(manifest).to_csv(manifest_path, index=False)
    print(f"Exported {len(manifest)} analysis tables plus manifest to {output}")
    print(f"Molecules: {len(expected_ids)}; files: {len(list(output.glob('*.csv')))}")


if __name__ == "__main__":
    main()
