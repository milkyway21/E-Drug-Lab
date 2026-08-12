#!/usr/bin/env python3
"""Five-minute watchdog for the Phase F GPU2/5 extra34 queue."""
from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime

from phaseF_common import ANALYSIS_ROOT, LOG_ROOT, ROOT, SCHRODINGER


INPUT_DONE = ANALYSIS_ROOT / "INPUT_GPU25_EXTRA34_QC_DONE.flag"
DONE = ANALYSIS_ROOT / "MD_GPU25_EXTRA34_DONE.flag"
TERMINAL_FAILURE = ANALYSIS_ROOT / "MD_GPU25_EXTRA34_TERMINAL_FAILURE.flag"
LOG = LOG_ROOT / "gpu25_extra34_watchdog.log"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def queue_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "35_phaseF_extra34_gpu25_queue.py"],
        text=True, capture_output=True, check=False,
    )
    return any(int(value) != os.getpid() for value in result.stdout.split() if value.isdigit())


def start_queue() -> None:
    output = (LOG_ROOT / "gpu25_extra34_queue_stdout.log").open("a")
    subprocess.Popen(
        [f"{SCHRODINGER}/run", "python3", "-u", "scripts/35_phaseF_extra34_gpu25_queue.py"],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
        start_new_session=True, close_fds=True,
    )
    output.close()
    log("RESTART scripts/35_phaseF_extra34_gpu25_queue.py")


def main() -> None:
    log("WATCHDOG START interval=300s")
    while True:
        if TERMINAL_FAILURE.exists():
            log("WATCHDOG STOP terminal failure flag present")
            return
        if DONE.exists():
            log("WATCHDOG COMPLETE extra34 valid=2/2")
            return
        if INPUT_DONE.exists() and not queue_running():
            start_queue()
        log(
            f"HEARTBEAT input_done={INPUT_DONE.exists()} queue_running={queue_running()} "
            f"md_done={DONE.exists()}"
        )
        time.sleep(300)


if __name__ == "__main__":
    main()
