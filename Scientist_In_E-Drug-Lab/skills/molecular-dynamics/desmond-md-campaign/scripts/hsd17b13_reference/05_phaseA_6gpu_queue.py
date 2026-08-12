#!/usr/bin/env python3
"""Phase A: dynamic 6-GPU queue for 27× (2+50 ns). Records wall times.
Does NOT start Phase B (100 ns / 12 mol / 4 GPU).
"""
from __future__ import annotations

import csv
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")
NGPU = int(os.environ.get("NGPU", "6"))
MSJ = ROOT / "scripts/protocols/prod_2ns_eq_50ns.msj"
TIMING = ROOT / "logs/phaseA_timing.csv"
QUEUE_LOG = ROOT / "logs/phaseA_queue.log"
JOBDIR = ROOT / "04_trajectories/phaseA"


def log(msg: str) -> None:
    QUEUE_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with QUEUE_LOG.open("a") as f:
        f.write(line + "\n")


def append_timing(row: dict) -> None:
    TIMING.parent.mkdir(parents=True, exist_ok=True)
    write_header = not TIMING.exists()
    with TIMING.open("a", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "mol_id",
                "gpu_id",
                "jobname",
                "jobid",
                "t_submit",
                "t_end",
                "wall_h",
                "status",
                "notes",
            ],
        )
        if write_header:
            w.writeheader()
        w.writerow(row)


def jobcontrol_list() -> str:
    return subprocess.check_output(
        [f"{SCHRODINGER}/jobcontrol", "-list"], text=True, errors="ignore"
    )


def launch(mid: str, gpu: int) -> tuple[str, str, str]:
    """Return (jobname, launch_log_path, t_submit_iso)."""
    work = JOBDIR / mid
    work.mkdir(parents=True, exist_ok=True)
    cms_src = ROOT / "03_systems" / mid / f"{mid}-out.cms"
    if not cms_src.exists():
        raise FileNotFoundError(cms_src)
    cms = work / f"{mid}-out.cms"
    if not cms.exists():
        cms.write_bytes(cms_src.read_bytes())
    msj = work / "md.msj"
    msj.write_text(MSJ.read_text())
    jobname = f"HSD17B13_A52_{mid}"
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    c0, c1 = gpu * 8, gpu * 8 + 7
    t_submit = datetime.now().isoformat(timespec="seconds")
    launch_log = work / "launch.log"
    cmd = (
        f"numactl --physcpubind={c0}-{c1} "
        f"'{SCHRODINGER}/utilities/multisim' -HOST localhost -maxjob 1 "
        f"-JOBNAME '{jobname}' -m md.msj '{mid}-out.cms' "
        f"-o '{mid}_52ns-out.cms' -mode umbrella > launch.log 2>&1"
    )
    subprocess.Popen(["bash", "-lc", cmd], cwd=str(work), env=env)
    time.sleep(8)
    jobid = ""
    if launch_log.exists():
        for line in launch_log.read_text(errors="ignore").splitlines():
            if "JobId:" in line:
                jobid = line.split("JobId:")[-1].strip()
    append_timing(
        {
            "mol_id": mid,
            "gpu_id": gpu,
            "jobname": jobname,
            "jobid": jobid,
            "t_submit": t_submit,
            "t_end": "",
            "wall_h": "",
            "status": "submitted",
            "notes": "",
        }
    )
    return jobname, str(launch_log), t_submit


def job_done(jobname: str) -> bool | None:
    """True=finished, False=running, None=unknown/not listed."""
    out = jobcontrol_list()
    if jobname in out and "running" in out:
        # crude: if name appears with running
        for line in out.splitlines():
            if jobname in line:
                if "running" in line:
                    return False
                if "finished" in line or "complete" in line.lower():
                    return True
    # check multisim completed in traj dir
    mid = jobname.replace("HSD17B13_A52_", "")
    log = JOBDIR / mid / f"{jobname}_multisim.log"
    if log.exists() and "Multisim completed" in log.read_text(errors="ignore"):
        return True
    if jobname not in out:
        # maybe finished and dropped from list
        if log.exists():
            txt = log.read_text(errors="ignore")
            if "Multisim completed" in txt:
                return True
            if "ERROR" in txt and "Fail" in txt:
                return True
        return None
    return False


def mark_finished(mid: str, jobname: str, t_submit: str, status: str, notes: str = "") -> None:
    t_end = datetime.now().isoformat(timespec="seconds")
    try:
        t0 = datetime.fromisoformat(t_submit)
        t1 = datetime.fromisoformat(t_end)
        wall_h = f"{(t1 - t0).total_seconds() / 3600.0:.3f}"
    except Exception:
        wall_h = ""
    append_timing(
        {
            "mol_id": mid,
            "gpu_id": "",
            "jobname": jobname,
            "jobid": "",
            "t_submit": t_submit,
            "t_end": t_end,
            "wall_h": wall_h,
            "status": status,
            "notes": notes,
        }
    )


def main() -> None:
    if os.environ.get("CONFIRM_PHASE_A") != "YES":
        raise SystemExit("Set CONFIRM_PHASE_A=YES to launch Phase A queue")

    ids = [l.strip() for l in open(ROOT / "meta/ids_27.txt") if l.strip()]
    pending = set(ids)
    finished_ids: set[str] = set()
    log(f"Phase A start NGPU={NGPU} n={len(ids)} (launch as CMS ready; do not idle GPUs)")

    # Do not block on full CMS set. Start as soon as any CMS exists and GPUs free.
    active: dict[int, dict] = {}  # gpu -> info

    def cms_ready(mid: str) -> bool:
        return (ROOT / "03_systems" / mid / f"{mid}-out.cms").exists()

    def next_ready() -> str | None:
        # prefer larger cms first among ready, not yet launched/finished
        launched = {info["mid"] for info in active.values()} | finished_ids
        cands = []
        for mid in pending:
            if mid in launched:
                continue
            p = ROOT / "03_systems" / mid / f"{mid}-out.cms"
            if p.exists():
                cands.append((-p.stat().st_size, mid))
        if not cands:
            return None
        cands.sort()
        return cands[0][1]

    while len(finished_ids) < len(ids) or active:
        # free finished GPUs
        for gpu in list(active):
            info = active[gpu]
            st = job_done(info["jobname"])
            if st is True:
                log(f"DONE gpu={gpu} {info['mid']}")
                mark_finished(info["mid"], info["jobname"], info["t_submit"], "completed")
                finished_ids.add(info["mid"])
                del active[gpu]
            elif st is False:
                pass
            else:
                if time.time() - info["t0"] > 3600 * 14:
                    log(f"TIMEOUT? gpu={gpu} {info['mid']}")
                    mark_finished(
                        info["mid"], info["jobname"], info["t_submit"], "unknown", "timeout_check"
                    )
                    finished_ids.add(info["mid"])
                    del active[gpu]

        # launch on free GPUs when CMS ready
        for gpu in range(NGPU):
            if gpu in active:
                continue
            mid = next_ready()
            if mid is None:
                n_ready = sum(1 for m in pending if cms_ready(m) and m not in finished_ids)
                n_miss = sum(1 for m in pending if not cms_ready(m))
                if n_miss and not active:
                    log(f"GPU{gpu} idle waiting CMS (ready_left={n_ready} building={n_miss})")
                break
            try:
                jobname, _, t_submit = launch(mid, gpu)
                active[gpu] = {
                    "mid": mid,
                    "jobname": jobname,
                    "t_submit": t_submit,
                    "t0": time.time(),
                }
                log(f"LAUNCH gpu={gpu} {mid} {jobname}")
            except Exception as e:
                log(f"FAIL launch {mid}: {e}")
                mark_finished(mid, "", "", "launch_failed", str(e))
                finished_ids.add(mid)

        time.sleep(45)

    log("Phase A queue drained. Do NOT start Phase B until user confirms Top12.")
    (ROOT / "06_reports/PHASE_A_QUEUE_DONE.flag").write_text(
        datetime.now().isoformat() + "\n"
    )


if __name__ == "__main__":
    main()
