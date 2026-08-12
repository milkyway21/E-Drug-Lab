#!/usr/bin/env python3
"""Wait for the final Phase F validations, then launch full20 analysis once."""
from __future__ import annotations

import fcntl
import os
import subprocess
import time
from datetime import datetime

from phaseF_common import ANALYSIS_ROOT, LOG_ROOT, ROOT, SCHRODINGER


MD_DONE = ANALYSIS_ROOT / "MD_GPU25_EXTRA34_DONE.flag"
MD_FAILED = ANALYSIS_ROOT / "MD_GPU25_EXTRA34_TERMINAL_FAILURE.flag"
ANALYSIS_DONE = ANALYSIS_ROOT / "ANALYSIS_FULL20_DONE.flag"
LOCK = ANALYSIS_ROOT / ".phaseF_full20_analysis_watchdog.lock"
LOG = LOG_ROOT / "full20_analysis_watchdog.log"
ANALYSIS_LOG = LOG_ROOT / "full20_analysis_stdout.log"
POLL_SECONDS = 60
MAX_ANALYSIS_ATTEMPTS = 3


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def run_analysis() -> int:
    environment = os.environ.copy()
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "SCHRODINGER_CUDA_VISIBLE_DEVICES": "",
            "MPLBACKEND": "Agg",
            "QT_QPA_PLATFORM": "offscreen",
        }
    )
    with ANALYSIS_LOG.open("a") as stream:
        result = subprocess.run(
            [f"{SCHRODINGER}/run", "python3", "-u", "scripts/41_phaseF_full20_post_analysis.py"],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    return result.returncode


def main() -> None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("WATCHDOG already active; duplicate invocation exits")
        return

    log("WATCHDOG START waiting for final two hard validations")
    attempts = 0
    while True:
        if ANALYSIS_DONE.is_file():
            log("WATCHDOG COMPLETE analysis valid=20/20")
            return
        if MD_FAILED.is_file():
            log("WATCHDOG STOP MD terminal failure flag present")
            return
        if MD_DONE.is_file():
            attempts += 1
            log(f"ANALYSIS LAUNCH attempt={attempts}/{MAX_ANALYSIS_ATTEMPTS}")
            return_code = run_analysis()
            if return_code == 0 and ANALYSIS_DONE.is_file():
                log("WATCHDOG COMPLETE analysis valid=20/20")
                return
            log(f"ANALYSIS FAILED rc={return_code}; see {ANALYSIS_LOG}")
            if attempts >= MAX_ANALYSIS_ATTEMPTS:
                log("WATCHDOG STOP analysis retries exhausted")
                return
            time.sleep(300)
            continue
        log("HEARTBEAT md_validated=18/20 analysis_started=False")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
