#!/usr/bin/env python3
"""Resumable four-GPU queue for Phase F 16 x (2 ns equilibration + 200 ns)."""
from __future__ import annotations

import csv
import fcntl
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from schrodinger.application.desmond.packages import topo, traj

from phaseF_common import (
    ANALYSIS_ROOT, HOSTS_FILE, IDS_FILE, LOG_ROOT, MD_PROTOCOL, SCHRODINGER,
    SYSTEM_ROOT, TRAJECTORY_ROOT, trajectory_dir, write_json,
)

GPUS = [2, 3, 4, 5]
MAX_ATTEMPTS = 3
POLL_SECONDS = int(os.environ.get("PHASE_F_QUEUE_POLL", "30"))
STALL_SECONDS = 90 * 60
STATUS = ANALYSIS_ROOT / "md_queue_status.csv"
DONE = ANALYSIS_ROOT / "MD_ALL16_DONE.flag"
TERMINAL_FAILURE = ANALYSIS_ROOT / "MD_TERMINAL_FAILURE.flag"
LOCK = ANALYSIS_ROOT / ".phaseF_queue.lock"
LOG = LOG_ROOT / "queue.log"
TIMING = LOG_ROOT / "timing.csv"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def ids() -> list[str]:
    values = IDS_FILE.read_text().split()
    if len(values) != 16 or len(set(values)) != 16:
        raise RuntimeError(f"Expected 16 unique Phase F IDs, got {len(values)}")
    return values


def attempts(mid: str) -> list[Path]:
    return sorted(path for path in (TRAJECTORY_ROOT / mid).glob("attempt_*") if path.is_dir())


def attempt_number(path: Path) -> int:
    return int(path.name.rsplit("_", 1)[1])


def multisim_log(path: Path) -> Path | None:
    found = list(path.glob("HSD17B13_F202_*_multisim.log"))
    return found[0] if found else None


def multisim_completed(path: Path) -> bool:
    log_path = multisim_log(path)
    return bool(log_path and "Multisim completed" in log_path.read_text(errors="ignore"))


def validate_attempt(mid: str, path: Path, persist: bool = True) -> tuple[bool, dict]:
    result = {
        "molecule_id": mid, "attempt": attempt_number(path), "attempt_path": str(path),
        "validated_at": datetime.now().isoformat(), "valid": False,
    }
    try:
        if not multisim_completed(path):
            raise RuntimeError("Multisim completion marker absent")
        cms_path = path / f"{mid}_202ns-out.cms"
        if not cms_path.exists() or cms_path.stat().st_size <= 1_000_000:
            raise RuntimeError("final CMS missing or too small")
        trj_path = trajectory_dir(path, extract=True)
        frames = traj.read_traj(str(trj_path))
        times = np.asarray([frame.time for frame in frames], float)
        if len(times) < 1001:
            raise RuntimeError(f"too few production frames: {len(times)}")
        if not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0):
            raise RuntimeError("production frame times are not strictly increasing")
        # The requested production run is a full 200 ns.  Permit only 1 ps of
        # floating-point timestamp tolerance; even a missing final 0.2 ns
        # output frame is incomplete and must be retried.
        if float(times[-1]) < 199999.0:
            raise RuntimeError(f"production duration only {times[-1] / 1000:.3f} ns; require 200 ns")
        if float(times[0]) > 1.0 or float(times[-1] - times[0]) < 199998.0:
            raise RuntimeError(
                f"production coverage is incomplete: first={times[0]:.3f} ps "
                f"last={times[-1]:.3f} ps"
            )
        if float(np.max(np.diff(times))) > 250.5:
            raise RuntimeError(f"production frame gap {np.max(np.diff(times)):.3f} ps")
        _, cms = topo.read_cms(str(cms_path))
        consistency = topo.check_consistency(cms, frames[-1])
        if consistency is not None:
            raise RuntimeError(f"topology inconsistent with final frame: {consistency}")
        result.update({
            "valid": True, "final_cms": str(cms_path), "final_cms_bytes": cms_path.stat().st_size,
            "production_trajectory": str(trj_path), "production_frames": len(frames),
            "production_first_ps": float(times[0]), "production_last_ps": float(times[-1]),
            "maximum_frame_gap_ps": float(np.max(np.diff(times))), "topo_consistency": "pass",
        })
    except Exception as error:
        result["error"] = repr(error)
    if persist:
        write_json(path / "attempt_validation.json", result)
    return bool(result["valid"]), result


def completed_attempt(mid: str) -> Path | None:
    for path in reversed(attempts(mid)):
        marker = path / "attempt_validation.json"
        if marker.exists():
            try:
                if json.loads(marker.read_text()).get("valid"):
                    return path
            except Exception:
                pass
        if multisim_completed(path):
            valid, _ = validate_attempt(mid, path)
            if valid:
                return path
    return None


def jobcontrol() -> str:
    result = subprocess.run(
        [f"{SCHRODINGER}/jobcontrol", "-list"], text=True, capture_output=True, check=False
    )
    return result.stdout + result.stderr


def job_running(jobname: str, listing: str | None = None) -> bool:
    listing = listing if listing is not None else jobcontrol()
    return any(jobname in line and "running" in line.lower() for line in listing.splitlines())


def gpu_pids(gpu: int) -> list[int]:
    result = subprocess.run(
        ["nvidia-smi", "-i", str(gpu), "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
        text=True, capture_output=True, check=False,
    )
    return [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]


def append_timing(info: dict, status: str, notes: str = "") -> None:
    fields = ["molecule_id", "attempt", "gpu_id", "jobname", "jobid", "submitted", "ended", "wall_h", "status", "notes"]
    row = {key: info.get(key, "") for key in fields}
    row["status"] = status
    row["notes"] = notes
    if status != "submitted":
        row["ended"] = datetime.now().isoformat(timespec="seconds")
        row["wall_h"] = f"{(time.time() - float(info.get('submitted_epoch', time.time()))) / 3600:.3f}"
    TIMING.parent.mkdir(parents=True, exist_ok=True)
    new = not TIMING.exists()
    with TIMING.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if new:
            writer.writeheader()
        writer.writerow(row)


def progress(path: Path) -> tuple[float, int]:
    files = [p for p in path.rglob("*") if p.is_file() and p.name != "state.json"]
    if not files:
        return path.stat().st_mtime, 0
    return max(p.stat().st_mtime for p in files), sum(p.stat().st_size for p in files)


def save_state(info: dict) -> None:
    write_json(Path(info["attempt_path"]) / "state.json", info)


def launch(mid: str, gpu: int) -> dict:
    number = len(attempts(mid)) + 1
    if number > MAX_ATTEMPTS:
        raise RuntimeError(f"{mid}: attempts exhausted")
    path = TRAJECTORY_ROOT / mid / f"attempt_{number:02d}"
    path.mkdir(parents=True, exist_ok=False)
    source = SYSTEM_ROOT / mid / f"{mid}-out.cms"
    if not source.exists():
        raise FileNotFoundError(source)
    target = path / f"{mid}-out.cms"
    try:
        os.link(source, target)
    except OSError:
        target.symlink_to(source)
    shutil.copy2(MD_PROTOCOL, path / "md.msj")
    jobname = f"HSD17B13_F202_{mid}_a{number}"
    environment = os.environ.copy()
    environment.update({
        "CUDA_VISIBLE_DEVICES": str(gpu), "SCHRODINGER_CUDA_VISIBLE_DEVICES": str(gpu),
        "SCHRODINGER_HOSTS": str(HOSTS_FILE),
    })
    command = [
        "numactl", f"--physcpubind={gpu * 8}-{gpu * 8 + 7}",
        f"{SCHRODINGER}/utilities/multisim", "-HOST", f"phaseF_gpu{gpu}",
        "-SUBHOST", f"phaseF_gpu{gpu}", "-maxjob", "1", "-JOBNAME", jobname,
        "-m", "md.msj", target.name, "-o", f"{mid}_202ns-out.cms", "-mode", "umbrella",
    ]
    launch_log = path / "launch.log"
    submitted_epoch = time.time()
    with launch_log.open("x") as stream:
        process = subprocess.Popen(
            command, cwd=path, env=environment, stdin=subprocess.DEVNULL,
            stdout=stream, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True,
        )
    time.sleep(8)
    jobid = ""
    if launch_log.exists():
        for line in launch_log.read_text(errors="ignore").splitlines():
            if "JobId:" in line:
                jobid = line.split("JobId:", 1)[1].strip()
    mtime, size = progress(path)
    info = {
        "molecule_id": mid, "attempt": number, "gpu_id": gpu, "jobname": jobname,
        "jobid": jobid, "launcher_pid": process.pid,
        "submitted": datetime.now().isoformat(timespec="seconds"), "submitted_epoch": submitted_epoch,
        "attempt_path": str(path), "last_progress_epoch": mtime,
        "last_progress_size": size, "last_seen_running_epoch": time.time(),
    }
    save_state(info)
    append_timing(info, "submitted", "2ns_eq+200ns_prod; trajectory_interval=200ps")
    return info


def recover(molecule_ids: list[str]) -> dict[int, dict]:
    listing = jobcontrol()
    active = {}
    for mid in molecule_ids:
        if completed_attempt(mid):
            continue
        for path in reversed(attempts(mid)):
            state_path = path / "state.json"
            if not state_path.exists():
                continue
            try:
                info = json.loads(state_path.read_text())
            except Exception:
                continue
            gpu = int(info["gpu_id"])
            recent = time.time() - float(info.get("last_progress_epoch", 0)) < STALL_SECONDS
            if job_running(info.get("jobname", ""), listing) or (recent and gpu_pids(gpu)):
                active[gpu] = info
                log(f"RECOVER gpu={gpu} {mid} attempt={info['attempt']}")
            break
    return active


def state_of(info: dict) -> tuple[str, str]:
    mid, path, gpu = info["molecule_id"], Path(info["attempt_path"]), int(info["gpu_id"])
    if multisim_completed(path):
        valid, details = validate_attempt(mid, path)
        return ("completed", "hard validation passed") if valid else ("failed", details.get("error", "validation failed"))
    log_path = multisim_log(path)
    if log_path:
        text = log_path.read_text(errors="ignore")
        if "Multisim failed" in text or "Job failed" in text or "FATAL" in text:
            return "failed", "explicit Multisim failure"
    current_mtime, current_size = progress(path)
    if current_mtime > float(info.get("last_progress_epoch", 0)) + 1 or current_size > int(info.get("last_progress_size", 0)):
        info["last_progress_epoch"] = current_mtime
        info["last_progress_size"] = current_size
        save_state(info)
    running = job_running(info["jobname"])
    pids = gpu_pids(gpu)
    if running or pids:
        info["last_seen_running_epoch"] = time.time()
        save_state(info)
        return "running", ""
    stalled = time.time() - float(info.get("last_progress_epoch", info["submitted_epoch"]))
    if stalled >= STALL_SECONDS:
        return "failed", f"no file progress and no GPU/job process for {stalled / 60:.1f} min"
    return "running", "scheduler/process transition grace period"


def estimated_finish(active: dict[int, dict], remaining_count: int) -> str:
    default_hours = 13.5
    durations = []
    if TIMING.exists():
        for row in csv.DictReader(TIMING.open()):
            if row["status"] == "completed" and row.get("wall_h"):
                durations.append(float(row["wall_h"]))
    per_job = float(np.median(durations[-8:])) if durations else default_hours
    # GPU0/1 may contain the explicitly authorized one-time last-two burst,
    # but they are not reusable queue slots.  ETA scheduling remains based on
    # the persistent four-worker GPU2-5 pool.
    active_remaining = [
        max(0.0, per_job - (time.time() - float(info["submitted_epoch"])) / 3600)
        for gpu, info in active.items() if gpu in GPUS
    ]
    slots = active_remaining + [0.0] * (len(GPUS) - len(active_remaining))
    for _ in range(remaining_count):
        index = int(np.argmin(slots))
        slots[index] += per_job
    return (datetime.now() + timedelta(hours=max(slots, default=0.0))).isoformat(timespec="minutes")


def write_status(molecule_ids: list[str], completed: set[str], failed: set[str], active: dict[int, dict]) -> None:
    active_by_mid = {info["molecule_id"]: info for info in active.values()}
    pending_count = sum(mid not in completed | failed | set(active_by_mid) for mid in molecule_ids)
    eta = estimated_finish(active, pending_count)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    fields = ["molecule_id", "status", "attempts", "gpu_id", "jobname", "jobid", "submitted", "attempt_path", "last_progress", "estimated_batch_finish"]
    with STATUS.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for mid in molecule_ids:
            info = active_by_mid.get(mid, {})
            status = "completed" if mid in completed else "terminal_failed" if mid in failed else "running" if info else "queued"
            progress_time = info.get("last_progress_epoch")
            writer.writerow({
                "molecule_id": mid, "status": status, "attempts": len(attempts(mid)),
                "gpu_id": info.get("gpu_id", ""), "jobname": info.get("jobname", ""),
                "jobid": info.get("jobid", ""), "submitted": info.get("submitted", ""),
                "attempt_path": info.get("attempt_path", ""),
                "last_progress": datetime.fromtimestamp(progress_time).isoformat(timespec="seconds") if progress_time else "",
                "estimated_batch_finish": eta,
            })


def main() -> None:
    ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)
    lock_handle = LOCK.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("QUEUE already active; duplicate invocation exits without submitting")
        return
    if not (ANALYSIS_ROOT / "INPUT_ALL16_QC_DONE.flag").exists():
        raise RuntimeError("Phase F input hard-QC flag absent; refusing to launch MD")
    molecule_ids = ids()
    TRAJECTORY_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    DONE.unlink(missing_ok=True)
    completed = {mid for mid in molecule_ids if completed_attempt(mid)}
    failed = set()
    active = recover(molecule_ids)
    log(f"QUEUE START selected={len(molecule_ids)} completed={len(completed)} GPUs={GPUS}")
    while len(completed | failed) < len(molecule_ids):
        for gpu in list(active):
            info = active[gpu]
            state, notes = state_of(info)
            if state == "running":
                continue
            append_timing(info, state, notes)
            mid = info["molecule_id"]
            log(f"{state.upper()} gpu={gpu} {mid} attempt={info['attempt']} {notes}")
            del active[gpu]
            if state == "completed":
                completed.add(mid)
            elif len(attempts(mid)) >= MAX_ATTEMPTS:
                failed.add(mid)

        busy = {info["molecule_id"] for info in active.values()}
        for gpu in GPUS:
            if gpu in active or gpu_pids(gpu):
                continue
            candidate = next((
                mid for mid in molecule_ids
                if mid not in completed | failed | busy and len(attempts(mid)) < MAX_ATTEMPTS
            ), None)
            if candidate is None:
                continue
            try:
                info = launch(candidate, gpu)
                active[gpu] = info
                busy.add(candidate)
                log(f"LAUNCH gpu={gpu} {candidate} attempt={info['attempt']} job={info['jobname']} id={info['jobid']}")
            except Exception as error:
                log(f"LAUNCH ERROR gpu={gpu} {candidate}: {error!r}")
                if len(attempts(candidate)) >= MAX_ATTEMPTS:
                    failed.add(candidate)
        write_status(molecule_ids, completed, failed, active)
        time.sleep(POLL_SECONDS)

    write_status(molecule_ids, completed, failed, active)
    if failed:
        TERMINAL_FAILURE.write_text(f"{datetime.now().isoformat()}\nfailed={sorted(failed)}\n")
        log(f"QUEUE TERMINAL FAILURE completed={len(completed)} failed={sorted(failed)}")
        raise SystemExit(1)
    DONE.write_text(f"{datetime.now().isoformat()}\nvalid=16/16\n")
    log("QUEUE COMPLETE valid=16/16")


if __name__ == "__main__":
    main()
