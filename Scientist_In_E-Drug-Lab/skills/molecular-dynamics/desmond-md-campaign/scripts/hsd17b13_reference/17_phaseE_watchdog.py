#!/usr/bin/env python3
"""Restart Phase E build, MD queue, or analysis watcher if one exits early."""
from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")
ANALYSIS = ROOT / "05_analysis/phaseE_corrected_pose_2_50_all40_20260727"
LOG = ROOT / "logs/phaseE_corrected_pose_watchdog.log"
BUILD_SCRIPT = "scripts/15_build_corrected_pose_all40.py"
QUEUE_SCRIPT = "scripts/16_phaseE_corrected_all40_6gpu.py"
AUTO_ANALYSIS_SCRIPT = "scripts/21_phaseE_auto_analysis.py"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def running(fragment: str) -> bool:
    result = subprocess.run(
        ["pgrep", "-f", fragment], text=True, capture_output=True, check=False
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def spawn(script: str, output_name: str, extra: list[str] | None = None) -> None:
    output = ROOT / "logs" / output_name
    handle = output.open("a")
    command = [f"{SCHRODINGER}/run", "python3", "-u", script, *(extra or [])]
    subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    handle.close()
    log(f"RESTART {' '.join(command)}")


def main() -> None:
    log("WATCHDOG start")
    while True:
        build_done = (ANALYSIS / "BUILD_ALL40_DONE.flag").exists()
        md_done = (ANALYSIS / "MD_ALL40_DONE.flag").exists()
        analysis_done = (ANALYSIS / "ANALYSIS_ALL40_DONE.flag").exists()
        if not build_done and not running("15_build_corrected_pose_all40.py"):
            spawn(
                BUILD_SCRIPT,
                "phaseE_corrected_pose_build_stdout.log",
                ["--max-parallel", "2"],
            )
        if not md_done and not running("16_phaseE_corrected_all40_6gpu.py"):
            spawn(QUEUE_SCRIPT, "phaseE_corrected_pose_queue_stdout.log")
        if not analysis_done and not running("21_phaseE_auto_analysis.py"):
            spawn(AUTO_ANALYSIS_SCRIPT, "phaseE_auto_analysis_stdout.log")
        if build_done and md_done and analysis_done:
            log("WATCHDOG complete: build, MD, and analysis flags present")
            return
        log(
            f"HEARTBEAT build_done={build_done} md_done={md_done} "
            f"analysis_done={analysis_done}"
        )
        time.sleep(300)


if __name__ == "__main__":
    main()
