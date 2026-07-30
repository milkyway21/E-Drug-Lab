#!/usr/bin/env python3
"""Phase B Top6: 2 ns eq + 200 ns prod on 6 GPUs (1 mol / GPU).

Uses already-built CMS from 03_systems/. Selection from
05_analysis/md27_summary/md27_decision_table.csv ranks 1–6.

Does NOT extend Phase A trajectories; restart from built systems
with the same membrane CMS (user request: 在已经建立的系上).
"""
from __future__ import annotations

import csv
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")
MSJ = ROOT / "scripts/protocols/prod_2ns_eq_200ns.msj"
CSV = ROOT / "05_analysis/md27_summary/md27_decision_table.csv"
JOBDIR = ROOT / "04_trajectories/phaseB_200ns"
TIMING = ROOT / "logs/phaseB200_timing.csv"
QUEUE_LOG = ROOT / "logs/phaseB200_queue.log"

# Fixed Top6 from decision table (rank 1–6)
TOP6 = ["T3040", "T0465", "T4965", "T3232", "T39220", "T5135"]


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


def verify_top6_from_csv() -> None:
    if not CSV.exists():
        log(f"WARN csv missing {CSV}; using hardcoded TOP6")
        return
    rows = list(csv.DictReader(CSV.open()))
    ids = [r["分子"].strip() for r in rows[:6]]
    if ids != TOP6:
        raise SystemExit(f"CSV top6 mismatch: {ids} vs expected {TOP6}")


def launch(mid: str, gpu: int) -> tuple[str, str]:
    work = JOBDIR / mid
    work.mkdir(parents=True, exist_ok=True)
    cms_src = ROOT / "03_systems" / mid / f"{mid}-out.cms"
    if not cms_src.exists():
        raise FileNotFoundError(cms_src)
    cms = work / f"{mid}-out.cms"
    if not cms.exists() or cms.stat().st_size != cms_src.stat().st_size:
        cms.write_bytes(cms_src.read_bytes())
    msj = work / "md.msj"
    msj.write_text(MSJ.read_text())
    jobname = f"HSD17B13_B200_{mid}"
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    env.pop("CONFIRM_PHASE_A", None)
    c0, c1 = gpu * 8, gpu * 8 + 7
    t_submit = datetime.now().isoformat(timespec="seconds")
    launch_log = work / "launch.log"
    cmd = (
        f"numactl --physcpubind={c0}-{c1} "
        f"'{SCHRODINGER}/utilities/multisim' -HOST localhost -maxjob 1 "
        f"-JOBNAME '{jobname}' -m md.msj '{mid}-out.cms' "
        f"-o '{mid}_202ns-out.cms' -mode umbrella > launch.log 2>&1"
    )
    subprocess.Popen(["bash", "-lc", cmd], cwd=str(work), env=env)
    time.sleep(10)
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
            "notes": "2ns_eq+200ns_prod from 03_systems cms",
        }
    )
    return jobname, jobid


def main() -> None:
    if os.environ.get("CONFIRM_PHASE_B200") != "YES":
        raise SystemExit("Set CONFIRM_PHASE_B200=YES to launch Top6 × 200 ns")
    verify_top6_from_csv()
    if not MSJ.exists():
        raise SystemExit(f"missing protocol {MSJ}")
    JOBDIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "meta/phaseB200_top6.txt").write_text("\n".join(TOP6) + "\n")
    log(f"Phase B200 start Top6={TOP6} NGPU=6 protocol={MSJ.name}")
    for gpu, mid in enumerate(TOP6):
        jobname, jobid = launch(mid, gpu)
        log(f"LAUNCH gpu={gpu} {mid} {jobname} {jobid}")
    log("All 6 submitted. Monitor with jobcontrol / nvidia-smi.")
    (ROOT / "06_reports/PHASE_B200_LAUNCHED.flag").write_text(
        datetime.now().isoformat() + "\n" + "\n".join(TOP6) + "\n"
    )


if __name__ == "__main__":
    main()
