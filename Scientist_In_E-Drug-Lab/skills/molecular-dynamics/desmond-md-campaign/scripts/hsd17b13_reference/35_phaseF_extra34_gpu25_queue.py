#!/usr/bin/env python3
"""Persistent GPU2/5 queue for T5S0045 and T6307 full 2+200 ns runs."""
from __future__ import annotations

import csv
import fcntl
import json
import time
from datetime import datetime
from importlib import import_module

from phaseF_common import ANALYSIS_ROOT, LOG_ROOT


queue = import_module("25_phaseF_200ns_4gpu")
ASSIGNMENTS = [("T5S0045", 2), ("T6307", 5)]
INPUT_DONE = ANALYSIS_ROOT / "INPUT_GPU25_EXTRA34_QC_DONE.flag"
DONE = ANALYSIS_ROOT / "MD_GPU25_EXTRA34_DONE.flag"
TERMINAL_FAILURE = ANALYSIS_ROOT / "MD_GPU25_EXTRA34_TERMINAL_FAILURE.flag"
STATUS = ANALYSIS_ROOT / "gpu25_extra34_queue_status.csv"
LOCK = ANALYSIS_ROOT / ".phaseF_gpu25_extra34_queue.lock"
LOG = LOG_ROOT / "gpu25_extra34_queue.log"
POLL_SECONDS = 30


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def write_status(completed: set[str], failed: set[str], active: dict[int, dict]) -> None:
    active_by_mid = {info["molecule_id"]: info for info in active.values()}
    fields = [
        "molecule_id", "status", "assigned_gpu", "attempts", "jobname", "jobid",
        "submitted", "attempt_path", "last_progress",
    ]
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    with STATUS.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for mid, gpu in ASSIGNMENTS:
            info = active_by_mid.get(mid, {})
            if mid in completed:
                state = "completed"
            elif mid in failed:
                state = "terminal_failed"
            elif info:
                state = "running"
            else:
                state = "queued"
            progress_epoch = info.get("last_progress_epoch")
            writer.writerow({
                "molecule_id": mid,
                "status": state,
                "assigned_gpu": gpu,
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
    """Recover even when the launching terminal died before state.json was written."""
    listing = queue.jobcontrol()
    active = queue.recover([mid for mid, _ in ASSIGNMENTS])
    for mid, gpu in ASSIGNMENTS:
        if gpu in active or queue.completed_attempt(mid):
            continue
        for path in reversed(queue.attempts(mid)):
            state_path = path / "state.json"
            if state_path.exists():
                try:
                    info = json.loads(state_path.read_text())
                    if queue.job_running(info.get("jobname", ""), listing) or queue.gpu_pids(gpu):
                        active[gpu] = info
                    break
                except Exception:
                    pass
            number = queue.attempt_number(path)
            jobname = f"HSD17B13_F202_{mid}_a{number}"
            if not queue.job_running(jobname, listing):
                continue
            launch_log = path / "launch.log"
            jobid = ""
            if launch_log.exists():
                for line in launch_log.read_text(errors="ignore").splitlines():
                    if "JobId:" in line:
                        jobid = line.split("JobId:", 1)[1].strip()
            submitted_epoch = launch_log.stat().st_mtime if launch_log.exists() else path.stat().st_mtime
            progress_epoch, progress_size = queue.progress(path)
            info = {
                "molecule_id": mid,
                "attempt": number,
                "gpu_id": gpu,
                "jobname": jobname,
                "jobid": jobid,
                "launcher_pid": 0,
                "submitted": datetime.fromtimestamp(submitted_epoch).isoformat(timespec="seconds"),
                "submitted_epoch": submitted_epoch,
                "attempt_path": str(path),
                "last_progress_epoch": progress_epoch,
                "last_progress_size": progress_size,
                "last_seen_running_epoch": time.time(),
            }
            queue.save_state(info)
            active[gpu] = info
            log(f"RECOVER ORPHAN gpu={gpu} {mid} attempt={number} job={jobname} id={jobid}")
            break
    return active


def main() -> None:
    if not INPUT_DONE.exists():
        raise RuntimeError("Extra34 medoid input hard-QC flag absent; refusing to queue MD")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("QUEUE already active; duplicate invocation exits")
        return

    DONE.unlink(missing_ok=True)
    TERMINAL_FAILURE.unlink(missing_ok=True)
    completed = {mid for mid, _ in ASSIGNMENTS if queue.completed_attempt(mid)}
    failed: set[str] = set()
    active = recover()
    log(f"QUEUE START completed={len(completed)}/2 fixed_assignments=GPU2:T5S0045,GPU5:T6307")

    while len(completed | failed) < len(ASSIGNMENTS):
        for gpu in list(active):
            info = active[gpu]
            state, notes = queue.state_of(info)
            if state == "running":
                continue
            queue.append_timing(info, state, f"extra34_gpu25; {notes}")
            mid = info["molecule_id"]
            log(f"{state.upper()} gpu={gpu} {mid} attempt={info['attempt']} {notes}")
            del active[gpu]
            if state == "completed":
                completed.add(mid)
            elif len(queue.attempts(mid)) >= queue.MAX_ATTEMPTS:
                failed.add(mid)

        for mid, gpu in ASSIGNMENTS:
            if mid in completed | failed or gpu in active:
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
                    f"LAUNCH gpu={gpu} {mid} attempt={info['attempt']} "
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
