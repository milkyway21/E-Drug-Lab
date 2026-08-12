#!/usr/bin/env python3
"""Analyze the two validated Phase F supplements and build an 18-molecule plate."""
from __future__ import annotations

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
LOG = LOG_ROOT / "extra2_post_analysis.log"
SCHRODINGER = "/opt/schrodinger2023-3"

EXTRA_IDS = ["T16866", "T3232"]
BASE = ANALYSIS / "final_200ns"
EXTRA = ANALYSIS / "extra2_200ns_analysis"
COMBINED = ANALYSIS / "completed18_200ns_assessment"
COMBINED_MANIFEST = ANALYSIS / "phaseF_completed18_manifest.csv"
DONE = ANALYSIS / "ANALYSIS_GPU01_EXTRA2_DONE.flag"


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
    raise RuntimeError(f"{molecule_id}: no hard-validated trajectory")


def build_manifest() -> None:
    sources = [
        ANALYSIS / "phaseF_selection_manifest.csv",
        ANALYSIS / "phaseF_gpu01_extra2_manifest.csv",
    ]
    tables = [pd.read_csv(path) for path in sources]
    manifest = pd.concat(tables, ignore_index=True, sort=False)
    manifest = manifest.drop_duplicates("molecule_id", keep="last")
    manifest.to_csv(COMBINED_MANIFEST, index=False)
    log(f"COMBINED MANIFEST PASS rows={len(manifest)}")


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
        if not png.is_file() or not pdf.is_file():
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
    for directory in (BASE, EXTRA):
        path = directory / name
        if path.is_file() and path.stat().st_size:
            tables.append(pd.read_csv(path))
    if not tables:
        return pd.DataFrame()
    merged = pd.concat(tables, ignore_index=True, sort=False)
    if subset and set(subset).issubset(merged.columns):
        merged = merged.drop_duplicates(subset, keep="last")
    return merged


def merge_outputs() -> None:
    COMBINED.mkdir(parents=True, exist_ok=True)
    traces = merge_csv("md200_traces.csv", ["molecule_id", "frame"])
    contacts = merge_csv("md200_contacts.csv")
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

    traces.to_csv(COMBINED / "md200_traces.csv", index=False)
    contacts.to_csv(COMBINED / "md200_contacts.csv", index=False)
    transitions.to_csv(COMBINED / "md200_transitions.csv", index=False)
    decision.to_csv(COMBINED / "md200_decision_table.csv", index=False)
    decision.to_excel(COMBINED / "md200_decision_table.xlsx", index=False)

    counts = decision["md_class"].value_counts()
    summary = [
        "# HSD17B13 completed-18 200 ns summary",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Class distribution",
        "",
    ]
    for md_class in class_order:
        members = decision.loc[decision["md_class"] == md_class, "molecule_id"].tolist()
        summary.append(f"- {md_class} ({int(counts.get(md_class, 0))}): {', '.join(members) or 'none'}")
    summary.extend(["", "## Ranked decision", ""])
    for row in decision.itertuples(index=False):
        summary.append(
            f"{int(row.rank)}. **{row.molecule_id}** - `{row.md_class}`, score {row.md_score:.1f}"
        )
    (COMBINED / "md200_selection_summary.md").write_text("\n".join(summary) + "\n")
    log(f"MERGE PASS molecules={len(decision)} traces={len(traces)}")


def main() -> None:
    if DONE.is_file():
        log("ALREADY COMPLETE")
        return
    for molecule_id in EXTRA_IDS:
        validated_attempt(molecule_id)
    build_manifest()
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
        "SEA EXTRA2",
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
        "UNIFIED ANALYSIS EXTRA2",
    )
    merge_outputs()
    run(
        [
            f"{SCHRODINGER}/run",
            "python3",
            "scripts/37_plot_phaseF_md200_5x4.py",
            "--traces",
            str(COMBINED / "md200_traces.csv"),
            "--decisions",
            str(COMBINED / "md200_decision_table.csv"),
            "--output",
            str(COMBINED / "figures" / "phaseF_md200_rmsd_5high_4wide_completed18"),
        ],
        "PUBLICATION PLATE COMPLETED18",
    )
    required = [
        COMBINED / "md200_decision_table.csv",
        COMBINED / "md200_traces.csv",
        COMBINED / "figures" / "phaseF_md200_rmsd_5high_4wide_completed18.pdf",
        COMBINED / "figures" / "phaseF_md200_rmsd_5high_4wide_completed18.png",
    ]
    missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"Missing completed18 outputs: {missing}")
    DONE.write_text(f"{datetime.now().isoformat()}\nvalid=18/18\n")
    log("COMPLETE valid=18/18")


if __name__ == "__main__":
    main()
