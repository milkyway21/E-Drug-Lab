#!/usr/bin/env python3
"""Dynamic GPU queue for corrected-pose 40 x (2 ns equilibration + 50 ns)."""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from corrected_pose_common import (
    ANALYSIS_ROOT,
    MD_PROTOCOL,
    ROOT,
    SYSTEM_ROOT,
    TRAJECTORY_ROOT,
    load_ids,
)


SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")
GPU_LIST = [int(value) for value in os.environ.get("PHASE_E_GPU_LIST", "0,1,2,3,4,5").split(",")]
# attempt_01 was intentionally cancelled after detecting incorrect GPU affinity.
# Keep two additional attempts available for the corrected host-bound launches.
MAX_ATTEMPTS = int(os.environ.get("PHASE_E_MAX_ATTEMPTS", "3"))
HOSTS_FILE = ROOT / "meta/phaseE_gpu_hosts"
QUEUE_LOG = ROOT / "logs/phaseE_corrected_pose_all40_queue.log"
TIMING = ROOT / "logs/phaseE_corrected_pose_all40_timing.csv"
STATUS = ANALYSIS_ROOT / "md_queue_status.csv"
DONE = ANALYSIS_ROOT / "MD_ALL40_DONE.flag"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    QUEUE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_LOG.open("a") as handle:
        handle.write(line + "\n")


def append_timing(row: dict) -> None:
    TIMING.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "molecule_id", "attempt", "gpu_id", "jobname", "jobid",
        "submitted", "ended", "wall_h", "status", "notes",
    ]
    write_header = not TIMING.exists()
    with TIMING.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def jobcontrol_list() -> str:
    return subprocess.check_output(
        [f"{SCHRODINGER}/jobcontrol", "-list"], text=True, errors="ignore"
    )


def gpu_processes(gpu: int) -> list[int]:
    result = subprocess.run(
        [
            "nvidia-smi", "-i", str(gpu), "--query-compute-apps=pid",
            "--format=csv,noheader,nounits",
        ],
        text=True, capture_output=True, check=False,
    )
    return [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]


def attempts(mid: str) -> list[Path]:
    parent = TRAJECTORY_ROOT / mid
    if not parent.exists():
        return []
    return sorted(path for path in parent.glob("attempt_*") if path.is_dir())


def multisim_log(attempt: Path) -> Path | None:
    matches = list(attempt.glob("HSD17B13_E52C_*_multisim.log"))
    return matches[0] if matches else None


def attempt_complete(mid: str, attempt: Path) -> bool:
    log_path = multisim_log(attempt)
    final_cms = attempt / f"{mid}_52ns-out.cms"
    production = list(attempt.glob("HSD17B13_E52C_*_6_trj")) + list(
        attempt.glob("HSD17B13_E52C_*_6-out.tgz")
    )
    return bool(
        log_path and final_cms.exists() and production
        and "Multisim completed" in log_path.read_text(errors="ignore")
    )


def next_attempt(mid: str) -> tuple[Path, int]:
    existing = attempts(mid)
    number = len(existing) + 1
    if number > MAX_ATTEMPTS:
        raise RuntimeError(f"{mid}: exhausted {MAX_ATTEMPTS} attempts")
    path = TRAJECTORY_ROOT / mid / f"attempt_{number:02d}"
    path.mkdir(parents=True, exist_ok=False)
    return path, number


def cms_ready(mid: str) -> bool:
    cms = SYSTEM_ROOT / mid / f"{mid}-out.cms"
    qc = SYSTEM_ROOT / mid / "postbuild_qc.json"
    if not cms.exists() or not qc.exists():
        return False
    try:
        return bool(json.loads(qc.read_text()).get("postbuild_valid"))
    except Exception:
        return False


def launch(mid: str, gpu: int) -> dict:
    attempt, number = next_attempt(mid)
    cms_source = SYSTEM_ROOT / mid / f"{mid}-out.cms"
    cms_target = attempt / f"{mid}-out.cms"
    try:
        os.link(cms_source, cms_target)
    except OSError:
        cms_target.symlink_to(cms_source)
    shutil.copy2(MD_PROTOCOL, attempt / "md.msj")
    jobname = f"HSD17B13_E52C_{mid}_a{number}"
    launch_log = attempt / "launch.log"
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    env["SCHRODINGER_CUDA_VISIBLE_DEVICES"] = str(gpu)
    env["SCHRODINGER_HOSTS"] = str(HOSTS_FILE)
    c0, c1 = gpu * 8, gpu * 8 + 7
    cmd = [
        "numactl", f"--physcpubind={c0}-{c1}",
        f"{SCHRODINGER}/utilities/multisim",
        "-HOST", f"phaseE_gpu{gpu}",
        "-SUBHOST", f"phaseE_gpu{gpu}",
        "-maxjob", "1",
        "-JOBNAME", jobname,
        "-m", "md.msj", cms_target.name,
        "-o", f"{mid}_52ns-out.cms",
        "-mode", "umbrella",
    ]
    submitted = datetime.now().isoformat(timespec="seconds")
    with launch_log.open("x") as handle:
        subprocess.Popen(
            cmd, cwd=attempt, env=env, stdout=handle, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    time.sleep(10)
    jobid = ""
    if launch_log.exists():
        for line in launch_log.read_text(errors="ignore").splitlines():
            if "JobId:" in line:
                jobid = line.split("JobId:")[-1].strip()
    state = {
        "molecule_id": mid,
        "attempt": number,
        "gpu_id": gpu,
        "jobname": jobname,
        "jobid": jobid,
        "submitted": submitted,
        "t0": time.time(),
        "attempt_path": str(attempt),
    }
    (attempt / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    append_timing({**{key: state.get(key, "") for key in [
        "molecule_id", "attempt", "gpu_id", "jobname", "jobid", "submitted"
    ]}, "ended": "", "wall_h": "", "status": "submitted", "notes": "2ns_eq+50ns_prod"})
    return state


def active_status(info: dict) -> str:
    output = jobcontrol_list()
    for line in output.splitlines():
        if info["jobname"] in line:
            if "running" in line:
                return "running"
            if "finished" in line or "complete" in line.lower():
                break
    attempt = Path(info["attempt_path"])
    if attempt_complete(info["molecule_id"], attempt):
        return "completed"
    log_path = multisim_log(attempt)
    if log_path:
        text = log_path.read_text(errors="ignore")
        if "Multisim failed" in text or "Job failed" in text:
            return "failed"
    if time.time() - info["t0"] > 14 * 3600:
        return "failed"
    return "running"


def finish_row(info: dict, status: str) -> None:
    ended = datetime.now().isoformat(timespec="seconds")
    wall_h = (time.time() - info["t0"]) / 3600.0
    append_timing({
        "molecule_id": info["molecule_id"], "attempt": info["attempt"],
        "gpu_id": info["gpu_id"], "jobname": info["jobname"],
        "jobid": info["jobid"], "submitted": info["submitted"],
        "ended": ended, "wall_h": f"{wall_h:.3f}", "status": status, "notes": "",
    })


def write_status(ids: list[str], completed: set[str], failed: set[str], active: dict) -> None:
    active_by_mid = {info["molecule_id"]: info for info in active.values()}
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    with STATUS.open("w", newline="") as handle:
        fields = ["molecule_id", "status", "gpu_id", "jobname", "attempt_path"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for mid in ids:
            info = active_by_mid.get(mid, {})
            status = (
                "completed" if mid in completed else "failed" if mid in failed
                else "running" if info else "cms_ready" if cms_ready(mid) else "waiting_cms"
            )
            writer.writerow({
                "molecule_id": mid, "status": status,
                "gpu_id": info.get("gpu_id", ""), "jobname": info.get("jobname", ""),
                "attempt_path": info.get("attempt_path", ""),
            })


def recover_active_jobs(ids: list[str]) -> dict[int, dict]:
    output = jobcontrol_list()
    active: dict[int, dict] = {}
    for mid in ids:
        for attempt in attempts(mid):
            state_path = attempt / "state.json"
            if not state_path.exists():
                continue
            try:
                info = json.loads(state_path.read_text())
            except Exception:
                continue
            running = any(
                info.get("jobname", "") in line and "running" in line
                for line in output.splitlines()
            )
            if not running:
                continue
            gpu = int(info["gpu_id"])
            info["attempt_path"] = str(attempt)
            active[gpu] = info
            log(f"RECOVER running gpu={gpu} {mid} {info['jobname']}")
    return active


def main() -> None:
    ids = load_ids()
    TRAJECTORY_ROOT.mkdir(parents=True, exist_ok=True)
    completed = {
        mid for mid in ids if any(attempt_complete(mid, path) for path in attempts(mid))
    }
    failed: set[str] = set()
    active = recover_active_jobs(ids)
    log(f"QUEUE start ids={len(ids)} completed={len(completed)} GPUs={GPU_LIST}")

    while len(completed | failed) < len(ids):
        active_molecules = {info["molecule_id"] for info in active.values()}
        for mid in ids:
            if mid in completed | failed | active_molecules:
                continue
            if any(attempt_complete(mid, path) for path in attempts(mid)):
                completed.add(mid)
                log(f"RECOVER completed {mid}")

        for gpu in list(active):
            info = active[gpu]
            status = active_status(info)
            if status == "completed":
                finish_row(info, status)
                completed.add(info["molecule_id"])
                log(f"DONE gpu={gpu} {info['molecule_id']}")
                del active[gpu]
            elif status == "failed":
                finish_row(info, status)
                mid = info["molecule_id"]
                log(f"FAIL gpu={gpu} {mid} attempt={info['attempt']}")
                del active[gpu]
                if len(attempts(mid)) >= MAX_ATTEMPTS:
                    failed.add(mid)

        busy_molecules = {info["molecule_id"] for info in active.values()}
        for gpu in GPU_LIST:
            if gpu in active or gpu_processes(gpu):
                continue
            candidate = next((
                mid for mid in ids
                if mid not in completed and mid not in failed and mid not in busy_molecules
                and cms_ready(mid) and len(attempts(mid)) < MAX_ATTEMPTS
            ), None)
            if candidate is None:
                continue
            try:
                info = launch(candidate, gpu)
                active[gpu] = info
                busy_molecules.add(candidate)
                log(f"LAUNCH gpu={gpu} {candidate} {info['jobname']} {info['jobid']}")
            except Exception as exc:
                log(f"LAUNCH FAIL gpu={gpu} {candidate}: {exc}")
                if len(attempts(candidate)) >= MAX_ATTEMPTS:
                    failed.add(candidate)

        if (ANALYSIS_ROOT / "BUILD_ALL40_DONE.flag").exists() and not active:
            blocked = [mid for mid in ids if mid not in completed | failed and not cms_ready(mid)]
            if blocked:
                log(f"TERMINAL build failures: {blocked}")
                failed.update(blocked)
        write_status(ids, completed, failed, active)
        time.sleep(30)

    write_status(ids, completed, failed, active)
    DONE.write_text(
        datetime.now().isoformat() + f"\ncompleted={len(completed)}\nfailed={len(failed)}\n"
    )
    log(f"QUEUE drained completed={len(completed)} failed={len(failed)}")
    if failed:
        raise SystemExit(f"Failed molecules: {sorted(failed)}")


if __name__ == "__main__":
    main()
