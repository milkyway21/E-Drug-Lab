#!/usr/bin/env python3
"""Collect Phase E Schrödinger RMSD plots and PDF reports into one folder."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "05_analysis/phaseE_corrected_pose_2_50_all40_20260727"
SEA = ANALYSIS / "sea"
OUTPUT = ANALYSIS / "schrodinger_reports"
SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")


def link(source: Path, destination: Path) -> None:
    if destination.is_symlink():
        destination.unlink()
    elif destination.exists():
        return
    destination.symlink_to(source.resolve())


def generate_report(molecule_root: Path) -> Optional[Path]:
    molecule_id = molecule_root.name
    eaf = molecule_root / f"{molecule_id}_E52C_sea-out.eaf"
    if not eaf.exists():
        return None
    data_dir = molecule_root / "official_data"
    data_dir.mkdir(exist_ok=True)
    rmsd = data_dir / "PL-RMSD.png"
    pdf = data_dir / f"{molecule_id}_E52C_sea-out.pdf"
    if rmsd.exists() and pdf.exists():
        return data_dir

    environment = os.environ.copy()
    environment.setdefault("MPLBACKEND", "Agg")
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    log = molecule_root / "04_official_report.log"
    command = [
        f"{SCHRODINGER}/run",
        "event_analysis.py",
        "report",
        str(eaf),
        "-pdf",
        str(pdf),
        "-data",
        "-plots",
        "-data_dir",
        str(data_dir),
    ]
    with log.open("w") as stream:
        process = subprocess.run(
            command,
            cwd=molecule_root,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    if process.returncode or not rmsd.exists() or not pdf.exists():
        raise RuntimeError(f"{molecule_id}: official report failed; see {log}")
    return data_dir


def main() -> None:
    rmsd_output = OUTPUT / "rmsd"
    pdf_output = OUTPUT / "pdf"
    rmsd_output.mkdir(parents=True, exist_ok=True)
    pdf_output.mkdir(parents=True, exist_ok=True)
    collected = []
    for molecule_root in sorted(SEA.iterdir()):
        if not molecule_root.is_dir():
            continue
        molecule_id = molecule_root.name
        generate_report(molecule_root)
        candidates = [molecule_root / "official_data", molecule_root / "data"]
        data_dir = next((path for path in candidates if (path / "PL-RMSD.png").exists()), None)
        pdf_dir = next((path for path in candidates if list(path.glob("*-out.pdf"))), None)
        if data_dir is None or pdf_dir is None:
            continue
        rmsd = data_dir / "PL-RMSD.png"
        pdf = next(pdf_dir.glob("*-out.pdf"))
        link(rmsd, rmsd_output / f"{molecule_id}_PL-RMSD.png")
        link(pdf, pdf_output / f"{molecule_id}_Schrodinger_SEA.pdf")
        collected.append(molecule_id)
    (OUTPUT / "COLLECTED_IDS.txt").write_text("\n".join(collected) + "\n")
    print(f"Collected {len(collected)} Schrödinger reports in {OUTPUT}")


if __name__ == "__main__":
    main()
