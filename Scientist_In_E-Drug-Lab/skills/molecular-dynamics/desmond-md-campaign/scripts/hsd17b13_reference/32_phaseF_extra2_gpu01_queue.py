#!/usr/bin/env python3
"""Persistent GPU0/1 follow-on queue for T16866 and T3232 full 2+200 ns runs."""
from __future__ import annotations

import csv
import fcntl
import json
import time
from datetime import datetime
from importlib import import_module
from pathlib import Path

from phaseF_common import ANALYSIS_ROOT, LOG_ROOT


queue = import_module("25_phaseF_200ns_4gpu")
ASSIGNMENTS = [("T16866", 0, "T39220"), ("T3232", 1, "T10425")]
INPUT_DONE = ANALYSIS_ROOT / "INPUT_GPU01_EXTRA2_QC_DONE.flag"
DONE = ANALYSIS_ROOT / "MD_GPU01_EXTRA2_DONE.flag"
TERMINAL_FAILURE = ANALYSIS_ROOT / "MD_GPU01_EXTRA2_TERMINAL_FAILURE.flag"
STATUS = ANALYSIS_ROOT / "gpu01_extra2_queue_status.csv"
LOCK = ANALYSIS_ROOT / ".phaseF_gpu01_extra2_queue.lock"
LOG = LOG_ROOT / "gpu01_extra2_queue.log"
POLL_SECONDS = 30


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def prerequisite_valid(mid: str) -> bool:
    for path in reversed(queue.attempts(mid)):
        marker = path / "attempt_validation.json"
        if not marker.exists():
            continue
        try:
            if json.loads(marker.read_text()).get("valid"):
                return True
        except Exception:
            continue
    return False


def write_status(completed: set[str], failed: set[str], active: dict[int, dict]) -> None:
    active_by_mid = {info["molecule_id"]: info for info in active.values()}
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "molecule_id", "status", "assigned_gpu", "predecessor", "predecessor_valid",
        "attempts", "jobname", "jobid", "submitted", "attempt_path", "last_progress",
    ]
    with STATUS.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for mid, gpu, predecessor in ASSIGNMENTS:
            info = active_by_mid.get(mid, {})
            if mid in completed:
                state = "completed"
            elif mid in failed:
                state = "terminal_failed"
            elif info:
                state = "running"
            elif not prerequisite_valid(predecessor):
                state = "waiting_for_predecessor"
            else:
                state = "queued"
            progress_epoch = info.get("last_progress_epoch")
            writer.writerow({
                "molecule_id": mid,
                "status": state,
                "assigned_gpu": gpu,
                "predecessor": predecessor,
                "predecessor_valid": prerequisite_valid(predecessor),
                "attempts": len(queue.attempts(mid)),
                "jobname": info.get("jobname", ""),
                "jobid": info.get("jobid", ""),
                "submitted": info.get("submitted", ""),
                "attempt_path": info.get("attempt_path", ""),
                "last_progress": (
                    datetime.fromtimestamp(progress_epoch).isoformat(timespec="seconds")
                    if progress_epoch else ""
                ),
            })


def recover() -> dict[int, dict]:
    active = queue.recover([mid for mid, _, _ in ASSIGNMENTS])
    for gpu, info in active.items():
        log(f"RECOVER gpu={gpu} {info['molecule_id']} attempt={info['attempt']}")
    return active


def main() -> None:
    if not INPUT_DONE.exists():
        raise RuntimeError("Extra2 medoid input hard-QC flag absent; refusing to queue MD")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("QUEUE already active; duplicate invocation exits")
        return

    DONE.unlink(missing_ok=True)
    TERMINAL_FAILURE.unlink(missing_ok=True)
    completed = {mid for mid, _, _ in ASSIGNMENTS if queue.completed_attempt(mid)}
    failed: set[str] = set()
    active = recover()
    log(f"QUEUE START completed={len(completed)}/2 fixed_assignments=GPU0:T16866,GPU1:T3232")

    while len(completed | failed) < len(ASSIGNMENTS):
        for gpu in list(active):
            info = active[gpu]
            state, notes = queue.state_of(info)
            if state == "running":
                continue
            queue.append_timing(info, state, f"extra2_gpu01; {notes}")
            mid = info["molecule_id"]
            log(f"{state.upper()} gpu={gpu} {mid} attempt={info['attempt']} {notes}")
            del active[gpu]
            if state == "completed":
                completed.add(mid)
            elif len(queue.attempts(mid)) >= queue.MAX_ATTEMPTS:
                failed.add(mid)

        for mid, gpu, predecessor in ASSIGNMENTS:
            if mid in completed | failed or gpu in active:
                continue
            if not prerequisite_valid(predecessor):
                continue
            if queue.gpu_pids(gpu):
                continue
            if len(queue.attempts(mid)) >= queue.MAX_ATTEMPTS:
                failed.add(mid)
                continue
            try:
                info = queue.launch(mid, gpu)
                active[gpu] = info
                log(
                    f"LAUNCH gpu={gpu} {mid} after={predecessor} attempt={info['attempt']} "
                    f"job={info['jobname']} id={info['jobid']}"
                )
            except Exception as error:
                log(f"LAUNCH ERROR gpu={gpu} {mid}: {error!r}")
                if len(queue.attempts(mid)) >= queue.MAX_ATTEMPTS:
                    failed.add(mid)
        write_status(completed, failed, active)
        time.sleep(POLL_SECONDS)

    write_status(completed, failed, active)
    if failed:
        TERMINAL_FAILURE.write_text(f"{datetime.now().isoformat()}\nfailed={sorted(failed)}\n")
        log(f"QUEUE TERMINAL FAILURE completed={len(completed)} failed={sorted(failed)}")
        raise SystemExit(1)
    DONE.write_text(f"{datetime.now().isoformat()}\nvalid=2/2\n")
    log("QUEUE COMPLETE valid=2/2")


if __name__ == "__main__":
    main()
