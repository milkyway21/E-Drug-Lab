#!/usr/bin/env python3
"""Analyze the final two Phase F trajectories and assemble the full 20 set."""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BATCH = "phaseF_medoid_pose_2_200_top16_20260728"
ANALYSIS = ROOT / "05_analysis" / BATCH
TRAJECTORIES = ROOT / "04_trajectories" / BATCH
SEA = ANALYSIS / "sea"
LOG_ROOT = ROOT / "logs" / BATCH
LOG = LOG_ROOT / "full20_post_analysis.log"
SCHRODINGER = "/opt/schrodinger2023-3"

EXTRA_IDS = ["T5S0045", "T6307"]
SOURCE_ANALYSES = [
    ANALYSIS / "final_200ns",
    ANALYSIS / "extra2_200ns_analysis",
    ANALYSIS / "extra34_200ns_analysis",
]
EXTRA = SOURCE_ANALYSES[-1]
COMBINED = ANALYSIS / "full20_200ns_assessment"
COMBINED_MANIFEST = ANALYSIS / "phaseF_full20_manifest.csv"
TABLES = COMBINED / "tables_only_2plus200ns_20"
MD_DONE = ANALYSIS / "MD_GPU25_EXTRA34_DONE.flag"
DONE = ANALYSIS / "ANALYSIS_FULL20_DONE.flag"
LOCK = ANALYSIS / ".phaseF_full20_post_analysis.lock"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def run(command: list[str], label: str) -> None:
    log(f"{label} START")
    environment = os.environ.copy()
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "SCHRODINGER_CUDA_VISIBLE_DEVICES": "",
            "MPLBACKEND": "Agg",
            "QT_QPA_PLATFORM": "offscreen",
        }
    )
    with LOG.open("a") as stream:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    if result.returncode:
        raise RuntimeError(f"{label} failed with rc={result.returncode}; see {LOG}")
    log(f"{label} PASS")


def validated_attempt(molecule_id: str) -> Path:
    for attempt in sorted((TRAJECTORIES / molecule_id).glob("attempt_*"), reverse=True):
        validation = attempt / "attempt_validation.json"
        if validation.is_file() and json.loads(validation.read_text()).get("valid"):
            return attempt
    raise RuntimeError(f"{molecule_id}: no hard-validated full 200 ns trajectory")


def build_manifest() -> list[str]:
    sources = [
        ANALYSIS / "phaseF_selection_manifest.csv",
        ANALYSIS / "phaseF_gpu01_extra2_manifest.csv",
        ANALYSIS / "phaseF_gpu25_extra34_manifest.csv",
    ]
    tables = [pd.read_csv(path) for path in sources]
    manifest = pd.concat(tables, ignore_index=True, sort=False)
    manifest = manifest.drop_duplicates("molecule_id", keep="last")
    if len(manifest) != 20 or manifest["molecule_id"].nunique() != 20:
        raise RuntimeError(f"Expected 20 unique manifest rows, found {len(manifest)}")
    manifest.to_csv(COMBINED_MANIFEST, index=False)
    molecule_ids = manifest["molecule_id"].astype(str).tolist()
    log(f"COMBINED MANIFEST PASS rows={len(manifest)}")
    return molecule_ids


def official_reports() -> None:
    rmsd_root = ANALYSIS / "schrodinger_reports" / "rmsd"
    pdf_root = ANALYSIS / "schrodinger_reports" / "pdf"
    rmsd_root.mkdir(parents=True, exist_ok=True)
    pdf_root.mkdir(parents=True, exist_ok=True)
    for molecule_id in EXTRA_IDS:
        molecule_root = SEA / molecule_id
        eaf = molecule_root / f"{molecule_id}_F202_sea-out.eaf"
        official = molecule_root / "official_data"
        official.mkdir(exist_ok=True)
        png = official / "PL-RMSD.png"
        pdf = official / f"{molecule_id}_F202_sea-out.pdf"
        required_data = [
            official / "PL_RMSD.dat",
            official / "P_RMSF.dat",
            official / "L_RMSF.dat",
            official / "L-Properties.dat",
        ]
        if not png.is_file() or not pdf.is_file() or any(not path.is_file() for path in required_data):
            run(
                [
                    f"{SCHRODINGER}/run",
                    "event_analysis.py",
                    "report",
                    str(eaf),
                    "-pdf",
                    str(pdf),
                    "-data",
                    "-plots",
                    "-data_dir",
                    str(official),
                ],
                f"OFFICIAL REPORT {molecule_id}",
            )
        for source, destination in (
            (png, rmsd_root / f"{molecule_id}_PL-RMSD.png"),
            (pdf, pdf_root / f"{molecule_id}_Schrodinger_SEA.pdf"),
        ):
            if destination.is_symlink():
                destination.unlink()
            if not destination.exists():
                destination.symlink_to(source.resolve())


def merge_csv(name: str, subset: list[str] | None = None) -> pd.DataFrame:
    tables = []
    for directory in SOURCE_ANALYSES:
        path = directory / name
        if path.is_file() and path.stat().st_size:
            tables.append(pd.read_csv(path))
    if len(tables) != len(SOURCE_ANALYSES):
        raise RuntimeError(f"Missing one or more source analysis tables named {name}")
    merged = pd.concat(tables, ignore_index=True, sort=False)
    if subset and set(subset).issubset(merged.columns):
        merged = merged.drop_duplicates(subset, keep="last")
    return merged


def merge_outputs() -> None:
    COMBINED.mkdir(parents=True, exist_ok=True)
    traces = merge_csv("md200_traces.csv", ["molecule_id", "frame"])
    contacts = merge_csv(
        "md200_contacts.csv", ["molecule_id", "contact_type", "residue"]
    )
    transitions = merge_csv("md200_transitions.csv")
    decision = merge_csv("md200_decision_table.csv", ["molecule_id"])

    class_order = {
        "A_pose_retained": 0,
        "B_contact_retained_rearrangement": 1,
        "C_inconclusive": 2,
        "D_pose_failure": 3,
    }
    decision["_class_order"] = decision["md_class"].map(class_order).fillna(9)
    decision = decision.sort_values(
        ["_class_order", "md_score"], ascending=[True, False], kind="stable"
    ).drop(columns="_class_order")
    decision["rank"] = range(1, len(decision) + 1)
    decision = decision[["rank"] + [column for column in decision if column != "rank"]]

    expected = set(decision["molecule_id"].astype(str))
    if len(expected) != 20:
        raise RuntimeError(f"Merged decision table has {len(expected)} molecules, expected 20")
    trace_ids = set(traces["molecule_id"].astype(str))
    if trace_ids != expected:
        raise RuntimeError("Merged trace and decision molecule coverage differs")
    frame_counts = traces.groupby("molecule_id")["frame"].nunique()
    if (frame_counts < 1001).any():
        raise RuntimeError(f"Incomplete trace frame counts: {frame_counts[frame_counts < 1001].to_dict()}")

    traces.to_csv(COMBINED / "md200_traces.csv", index=False)
    contacts.to_csv(COMBINED / "md200_contacts.csv", index=False)
    transitions.to_csv(COMBINED / "md200_transitions.csv", index=False)
    decision.to_csv(COMBINED / "md200_decision_table.csv", index=False)
    decision.to_excel(COMBINED / "md200_decision_table.xlsx", index=False)

    counts = decision["md_class"].value_counts()
    summary = [
        "# HSD17B13 full-20 200 ns summary",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Class distribution",
        "",
    ]
    for md_class in class_order:
        members = decision.loc[
            decision["md_class"] == md_class, "molecule_id"
        ].astype(str).tolist()
        summary.append(
            f"- {md_class} ({int(counts.get(md_class, 0))}): {', '.join(members) or 'none'}"
        )
    summary.extend(["", "## Ranked decision", ""])
    for row in decision.itertuples(index=False):
        summary.append(
            f"{int(row.rank)}. **{row.molecule_id}** - `{row.md_class}`, score {row.md_score:.1f}"
        )
    (COMBINED / "md200_selection_summary.md").write_text("\n".join(summary) + "\n")
    log(f"MERGE PASS molecules={len(decision)} traces={len(traces)}")


def required_outputs() -> list[Path]:
    figure = COMBINED / "figures" / "phaseF_md200_rmsd_5high_4wide_full20"
    return [
        COMBINED / "md200_decision_table.csv",
        COMBINED / "md200_decision_table.xlsx",
        COMBINED / "md200_traces.csv",
        COMBINED / "md200_contacts.csv",
        figure.with_suffix(".pdf"),
        figure.with_suffix(".png"),
        TABLES / "00_table_manifest.csv",
        TABLES / "03_protein_residue_rmsf.csv",
        TABLES / "08_residue_contact_heatmap_by_type_late.csv",
        TABLES / "10_residue_contact_heatmap_max_late.csv",
    ]


def main() -> None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("ANALYSIS already active; duplicate invocation exits")
        return

    if DONE.is_file() and all(path.is_file() and path.stat().st_size for path in required_outputs()):
        log("ALREADY COMPLETE valid=20/20")
        return
    if not MD_DONE.is_file():
        raise RuntimeError("Final two hard-validation completion flag is absent")
    for molecule_id in EXTRA_IDS:
        validated_attempt(molecule_id)
    molecule_ids = build_manifest()

    run(
        [
            f"{SCHRODINGER}/run",
            "python3",
            "-u",
            "scripts/26_phaseF_sea.py",
            "--jobs",
            "2",
            "--ids",
            *EXTRA_IDS,
        ],
        "SEA EXTRA34",
    )
    official_reports()
    EXTRA.mkdir(parents=True, exist_ok=True)
    run(
        [
            f"{SCHRODINGER}/run",
            "python3",
            "-u",
            "scripts/12_analyze_md200.py",
            "--ids",
            *EXTRA_IDS,
            "--outdir",
            str(EXTRA),
            "--trajectory-root",
            str(TRAJECTORIES),
            "--sea-root",
            str(SEA),
            "--manifest",
            str(COMBINED_MANIFEST),
        ],
        "UNIFIED ANALYSIS EXTRA34",
    )
    merge_outputs()
    figure = COMBINED / "figures" / "phaseF_md200_rmsd_5high_4wide_full20"
    run(
        [
            f"{SCHRODINGER}/run",
            "python3",
            "scripts/37_plot_phaseF_md200_5x4.py",
            "--traces",
            str(COMBINED / "md200_traces.csv"),
            "--decisions",
            str(COMBINED / "md200_decision_table.csv"),
            "--ids",
            *decision_order(COMBINED / "md200_decision_table.csv"),
            "--output",
            str(figure),
        ],
        "PUBLICATION PLATE FULL20",
    )
    run(
        [
            f"{SCHRODINGER}/run",
            "python3",
            "scripts/42_export_phaseF_full20_tables_only.py",
            "--source",
            str(ANALYSIS),
            "--assessment",
            str(COMBINED),
            "--manifest",
            str(COMBINED_MANIFEST),
            "--output",
            str(TABLES),
        ],
        "TABLES-ONLY FULL20",
    )

    missing = [str(path) for path in required_outputs() if not path.is_file() or not path.stat().st_size]
    if missing:
        raise RuntimeError(f"Missing full20 outputs: {missing}")
    DONE.write_text(
        f"{datetime.now().isoformat()}\nvalid=20/20\nids={','.join(molecule_ids)}\n"
    )
    log("COMPLETE valid=20/20 with figure and tables-only export")


def decision_order(path: Path) -> list[str]:
    table = pd.read_csv(path).sort_values("rank", kind="stable")
    return table["molecule_id"].astype(str).tolist()


if __name__ == "__main__":
    main()
