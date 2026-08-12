#!/usr/bin/env python3
"""Run Phase F SEA, official Schrödinger reports, and unified 200 ns analysis."""
from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from phaseF_common import ANALYSIS_ROOT, IDS_FILE, LOG_ROOT, MANIFEST, ROOT, SCHRODINGER, TRAJECTORY_ROOT

SEA = ANALYSIS_ROOT / "sea"
REPORTS = ANALYSIS_ROOT / "schrodinger_reports"
FINAL = ANALYSIS_ROOT / "final_200ns"
DONE = ANALYSIS_ROOT / "ANALYSIS_ALL16_DONE.flag"
LOG = LOG_ROOT / "post_analysis.log"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def run(command: list[str], output: Path) -> None:
    environment = os.environ.copy()
    environment.update({"CUDA_VISIBLE_DEVICES": "", "SCHRODINGER_CUDA_VISIBLE_DEVICES": "", "MPLBACKEND": "Agg", "QT_QPA_PLATFORM": "offscreen"})
    with output.open("a") as stream:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"rc={result.returncode}: {' '.join(command)}; see {output}")


def official_reports(molecule_ids: list[str]) -> None:
    rmsd_root, pdf_root = REPORTS / "rmsd", REPORTS / "pdf"
    rmsd_root.mkdir(parents=True, exist_ok=True)
    pdf_root.mkdir(parents=True, exist_ok=True)
    for mid in molecule_ids:
        molecule_root = SEA / mid
        eaf = molecule_root / f"{mid}_F202_sea-out.eaf"
        official = molecule_root / "official_data"
        official.mkdir(exist_ok=True)
        png = official / "PL-RMSD.png"
        pdf = official / f"{mid}_F202_sea-out.pdf"
        if not png.exists() or not pdf.exists():
            run(
                [f"{SCHRODINGER}/run", "event_analysis.py", "report", str(eaf),
                 "-pdf", str(pdf), "-data", "-plots", "-data_dir", str(official)],
                molecule_root / "04_official_report.log",
            )
        for source, destination in ((png, rmsd_root / f"{mid}_PL-RMSD.png"), (pdf, pdf_root / f"{mid}_Schrodinger_SEA.pdf")):
            if destination.is_symlink():
                destination.unlink()
            if not destination.exists():
                destination.symlink_to(source.resolve())
        log(f"OFFICIAL REPORT PASS {mid}")


def main() -> None:
    if not (ANALYSIS_ROOT / "MD_ALL16_DONE.flag").exists():
        raise RuntimeError("16/16 full 200 ns MD validation flag absent")
    molecule_ids = IDS_FILE.read_text().split()
    output = LOG_ROOT / "post_analysis_stdout.log"
    run([f"{SCHRODINGER}/run", "python3", "-u", "scripts/26_phaseF_sea.py", "--jobs", "4"], output)
    official_reports(molecule_ids)
    FINAL.mkdir(parents=True, exist_ok=True)
    run(
        [f"{SCHRODINGER}/run", "python3", "-u", "scripts/12_analyze_md200.py",
         "--ids", *molecule_ids, "--outdir", str(FINAL),
         "--trajectory-root", str(TRAJECTORY_ROOT), "--sea-root", str(SEA),
         "--manifest", str(MANIFEST)],
        output,
    )
    required = [
        FINAL / "md200_decision_table.csv", FINAL / "md200_traces.csv",
        FINAL / "md200_contacts.csv", FINAL / "figures/all_molecules_protein_ligand_rmsd.png",
    ]
    missing = [str(path) for path in required if not path.exists() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"final unified outputs missing: {missing}")
    DONE.write_text(f"{datetime.now().isoformat()}\nvalid=16/16\n")
    log("POST ANALYSIS COMPLETE 16/16")


if __name__ == "__main__":
    main()
