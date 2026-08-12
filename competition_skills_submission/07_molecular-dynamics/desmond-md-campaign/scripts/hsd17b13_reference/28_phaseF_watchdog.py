#!/usr/bin/env python3
"""Five-minute watchdog for the resumable Phase F MD and analysis pipeline."""
from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime

from phaseF_common import ANALYSIS_ROOT, LOG_ROOT, ROOT, SCHRODINGER

LOG = LOG_ROOT / "watchdog.log"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def running(fragment: str) -> bool:
    result = subprocess.run(["pgrep", "-f", fragment], text=True, capture_output=True, check=False)
    pids = [int(value) for value in result.stdout.split() if value.isdigit()]
    return any(pid != os.getpid() for pid in pids)


def spawn(script: str, output_name: str) -> None:
    output = LOG_ROOT / output_name
    handle = output.open("a")
    command = [f"{SCHRODINGER}/run", "python3", "-u", script]
    subprocess.Popen(
        command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=handle,
        stderr=subprocess.STDOUT, start_new_session=True, close_fds=True,
    )
    handle.close()
    log(f"RESTART {' '.join(command)}")


def main() -> None:
    log("WATCHDOG START interval=300s")
    while True:
        input_done = (ANALYSIS_ROOT / "INPUT_ALL16_QC_DONE.flag").exists()
        md_done = (ANALYSIS_ROOT / "MD_ALL16_DONE.flag").exists()
        terminal_failure = (ANALYSIS_ROOT / "MD_TERMINAL_FAILURE.flag").exists()
        analysis_done = (ANALYSIS_ROOT / "ANALYSIS_ALL16_DONE.flag").exists()
        if input_done and not md_done and not terminal_failure and not running("25_phaseF_200ns_4gpu.py"):
            spawn("scripts/25_phaseF_200ns_4gpu.py", "queue_stdout.log")
        if md_done and not analysis_done and not running("27_phaseF_post_analysis.py"):
            spawn("scripts/27_phaseF_post_analysis.py", "post_analysis_stdout.log")
        if terminal_failure:
            log("WATCHDOG STOP terminal MD failure flag present")
            return
        if md_done and analysis_done:
            log("WATCHDOG COMPLETE MD and analysis flags present")
            return
        log(f"HEARTBEAT input_done={input_done} md_done={md_done} analysis_done={analysis_done}")
        time.sleep(300)


if __name__ == "__main__":
    main()
