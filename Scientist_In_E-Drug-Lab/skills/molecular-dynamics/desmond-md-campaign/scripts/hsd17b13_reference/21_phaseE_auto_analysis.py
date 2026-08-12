#!/usr/bin/env python3
"""Analyze each newly completed Phase E trajectory batch until all 40 finish."""
from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")
TRAJECTORIES = ROOT / "04_trajectories/phaseE_corrected_pose_2_50_all40_20260727"
ANALYSIS = ROOT / "05_analysis/phaseE_corrected_pose_2_50_all40_20260727"
SEA_ROOT = ANALYSIS / "sea"
SUMMARY = ANALYSIS / "summary"
STATE = ANALYSIS / "AUTO_ANALYZED_IDS.txt"
DONE = ANALYSIS / "ANALYSIS_ALL40_DONE.flag"
LOG = ROOT / "logs/phaseE_auto_analysis.log"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def run(command: list[str], output_name: str) -> None:
    output = ROOT / "logs" / output_name
    with output.open("a") as stream:
        process = subprocess.run(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    if process.returncode:
        raise RuntimeError(f"rc={process.returncode}: {' '.join(command)}")


def extractor_active() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "scripts/19_sea_extract_phaseE.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def completed_ids() -> list[str]:
    result = []
    for molecule_dir in sorted(TRAJECTORIES.iterdir()):
        if not molecule_dir.is_dir():
            continue
        valid = False
        for attempt in molecule_dir.glob("attempt_*"):
            cms = attempt / f"{molecule_dir.name}_52ns-out.cms"
            archives = list(attempt.glob("HSD17B13_E52C_*_6-out.tgz"))
            if cms.exists() and cms.stat().st_size > 1_000_000 and archives:
                valid = archives[0].stat().st_size > 1_000_000
            if valid:
                break
        if valid:
            result.append(molecule_dir.name)
    return result


def sea_done_ids() -> list[str]:
    if not SEA_ROOT.exists():
        return []
    return sorted(
        path.parent.name
        for path in SEA_ROOT.glob("*/SEA_DONE.flag")
        if (path.parent / "data/PL_RMSD.dat").exists()
    )


def rebuild_summary(ids: list[str]) -> None:
    SUMMARY.mkdir(parents=True, exist_ok=True)
    run(
        [
            "python3",
            "scripts/07_analyze_md12.py",
            "--ids",
            *ids,
            "--sea-root",
            str(SEA_ROOT),
            "--out",
            str(SUMMARY),
        ],
        "phaseE_summary_stdout.log",
    )
    run(
        ["python3", "scripts/20_plot_phaseE_rmsd.py", "--summary", str(SUMMARY)],
        "phaseE_summary_stdout.log",
    )
    run(
        ["python3", "scripts/22_collect_phaseE_schrodinger_reports.py"],
        "phaseE_summary_stdout.log",
    )
    run(
        [
            f"{SCHRODINGER}/run",
            "python3",
            "scripts/23_analyze_phaseE_pocket_geometry.py",
            "--ids",
            *ids,
        ],
        "phaseE_summary_stdout.log",
    )
    STATE.write_text("\n".join(ids) + "\n")
    log(f"SUMMARY rebuilt n={len(ids)}")


def main() -> None:
    log("AUTO ANALYSIS start")
    while True:
        completed = completed_ids()
        sea_done = sea_done_ids()
        pending = sorted(set(completed) - set(sea_done))
        if pending and not extractor_active():
            log(f"SEA launch n={len(pending)} ids={pending}")
            try:
                run(
                    [
                        f"{SCHRODINGER}/run",
                        "python3",
                        "-u",
                        "scripts/19_sea_extract_phaseE.py",
                        "--jobs",
                        str(min(16, len(pending))),
                        "--ids",
                        *pending,
                    ],
                    "phaseE_sea_auto_stdout.log",
                )
            except Exception as error:
                log(f"SEA ERROR {error}")
            sea_done = sea_done_ids()

        previous = STATE.read_text().split() if STATE.exists() else []
        if sea_done and sea_done != sorted(previous) and not extractor_active():
            try:
                rebuild_summary(sea_done)
            except Exception as error:
                log(f"SUMMARY ERROR {error}")

        if len(completed) == 40 and len(sea_done) == 40 and STATE.exists():
            analyzed = STATE.read_text().split()
            if len(analyzed) == 40:
                DONE.write_text(datetime.now().isoformat() + "\n")
                log("AUTO ANALYSIS complete n=40")
                return
        log(
            f"HEARTBEAT md_completed={len(completed)} sea_done={len(sea_done)} "
            f"pending={len(pending)} extractor_active={extractor_active()}"
        )
        time.sleep(300)


if __name__ == "__main__":
    main()
