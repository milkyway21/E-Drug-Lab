#!/usr/bin/env python3
"""Phase C next13: 2 ns eq + 50 ns prod on 6 GPUs (dynamic queue).

Selection: md27_decision_table.csv ranks 7–19 (after Top6, before tail undocked).
Uses already-built CMS from 03_systems/ (hardlinked into job dirs at prep).

Default: dry-prep only (ensure job dirs / CMS / md.msj).
Launch ONLY when CONFIRM_PHASE_C=YES.

Do NOT run while Phase B200 (HSD17B13_B200_*) still occupies GPUs.
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
NGPU = int(os.environ.get("NGPU", "6"))
MSJ = ROOT / "scripts/protocols/prod_2ns_eq_50ns.msj"
CSV = ROOT / "05_analysis/md27_summary/md27_decision_table.csv"
IDS_FILE = ROOT / "meta/phaseC_next13_ids.txt"
META_FILE = ROOT / "meta/phaseC_next13.txt"
JOBDIR = ROOT / "04_trajectories/phaseC_2_50_next13"
TIMING = ROOT / "logs/phaseC_next13_timing.csv"
QUEUE_LOG = ROOT / "logs/phaseC_next13_queue.log"

# Fallback if meta missing (must match CSV ranks 7–19)
NEXT13_FALLBACK = [
    "T3S1089",
    "T7531",
    "T12164",
    "T6307",
    "T28655",
    "T2508",
    "T1571",
    "T1075",
    "T0499",
    "TP1672L",
    "T1368",
    "T69150",
    "T13553",
]


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


def load_ids() -> list[str]:
    if IDS_FILE.exists():
        ids = [ln.strip() for ln in IDS_FILE.read_text().splitlines() if ln.strip()]
        if len(ids) == 13:
            return ids
    return list(NEXT13_FALLBACK)


def verify_ids_from_csv(ids: list[str]) -> None:
    if not CSV.exists():
        log(f"WARN csv missing {CSV}; skipping rank check")
        return
    rows = list(csv.DictReader(CSV.open()))
    csv_ids = [r["分子"].strip() for r in rows[6:19]]  # ranks 7–19 (0-based 6:19)
    if csv_ids != ids:
        raise SystemExit(f"CSV ranks 7–19 mismatch: {csv_ids} vs expected {ids}")


def ensure_job_dir(mid: str) -> Path:
    """Dry-prep: hardlink CMS + copy protocol. Never mutates 03_systems."""
    work = JOBDIR / mid
    work.mkdir(parents=True, exist_ok=True)
    cms_src = ROOT / "03_systems" / mid / f"{mid}-out.cms"
    if not cms_src.exists():
        raise FileNotFoundError(cms_src)
    cms = work / f"{mid}-out.cms"
    if not cms.exists():
        try:
            os.link(cms_src, cms)
        except OSError:
            if not cms.exists():
                cms.symlink_to(cms_src)
    elif cms.is_symlink() or cms.stat().st_ino == cms_src.stat().st_ino:
        pass
    elif cms.stat().st_size != cms_src.stat().st_size:
        cms.unlink()
        try:
            os.link(cms_src, cms)
        except OSError:
            cms.symlink_to(cms_src)
    msj = work / "md.msj"
    msj.write_text(MSJ.read_text())
    (work / "READY.txt").write_text(
        "\n".join(
            [
                f"mol_id={mid}",
                f"cms_src={cms_src}",
                f"cms_job={cms}",
                "protocol=prod_2ns_eq_50ns.msj",
                "status=dry-prep",
                "note=Await CONFIRM_PHASE_C=YES; do not compete with B200 GPUs",
                "",
            ]
        )
    )
    return work


def dry_prep(ids: list[str]) -> None:
    JOBDIR.mkdir(parents=True, exist_ok=True)
    if not MSJ.exists():
        raise SystemExit(f"missing protocol {MSJ}")
    ok, fail = [], []
    for mid in ids:
        try:
            ensure_job_dir(mid)
            ok.append(mid)
        except Exception as e:
            fail.append((mid, str(e)))
            log(f"PREP FAIL {mid}: {e}")
    META_FILE.write_text(
        "\n".join(
            [
                "# Phase C next13: md27_decision_table.csv ranks 7–19",
                f"# CSV: {CSV.relative_to(ROOT)}",
                f"# Protocol: {MSJ.relative_to(ROOT)} (2 ns eq + 50 ns prod)",
                f"# Prepared: {datetime.now().isoformat(timespec='seconds')}",
                "# DO NOT launch until Top6 B200 finishes and user sets CONFIRM_PHASE_C=YES",
            ]
            + [f"{7 + i} {mid}" for i, mid in enumerate(ids)]
            + [""]
        )
    )
    IDS_FILE.write_text("\n".join(ids) + "\n")
    status = JOBDIR / "STATUS.txt"
    status.write_text(
        "\n".join(
            [
                f"phase=C_next13",
                f"n_ids={len(ids)}",
                f"prep_ok={len(ok)}",
                f"prep_fail={len(fail)}",
                f"protocol={MSJ}",
                f"jobdir={JOBDIR}",
                f"gate=CONFIRM_PHASE_C=YES",
                f"md_submitted=NO",
                f"updated={datetime.now().isoformat(timespec='seconds')}",
                "",
                "ids:",
                *[f"  {m}" for m in ok],
                *(["failures:"] + [f"  {m}: {e}" for m, e in fail] if fail else []),
                "",
            ]
        )
    )
    log(f"dry-prep done ok={len(ok)} fail={len(fail)} jobdir={JOBDIR}")
    if fail:
        raise SystemExit(f"prep failures: {fail}")


def jobcontrol_list() -> str:
    return subprocess.check_output(
        [f"{SCHRODINGER}/jobcontrol", "-list"], text=True, errors="ignore"
    )


def b200_still_running() -> list[str]:
    out = jobcontrol_list()
    hits = []
    for line in out.splitlines():
        if "HSD17B13_B200_" in line and "running" in line:
            hits.append(line.strip())
    return hits


def launch(mid: str, gpu: int) -> tuple[str, str]:
    work = ensure_job_dir(mid)
    jobname = f"HSD17B13_C52_{mid}"
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    env.pop("CONFIRM_PHASE_A", None)
    env.pop("CONFIRM_PHASE_B200", None)
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
    time.sleep(10)
    jobid = ""
    if launch_log.exists():
        for line in launch_log.read_text(errors="ignore").splitlines():
            if "JobId:" in line:
                jobid = line.split("JobId:")[-1].strip()
    (work / "READY.txt").write_text(
        "\n".join(
            [
                f"mol_id={mid}",
                f"jobname={jobname}",
                f"jobid={jobid}",
                f"gpu={gpu}",
                f"t_submit={t_submit}",
                "status=submitted",
                "protocol=prod_2ns_eq_50ns.msj",
                "",
            ]
        )
    )
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
            "notes": "2ns_eq+50ns_prod PhaseC next13",
        }
    )
    return jobname, jobid


def job_done(jobname: str) -> bool | None:
    out = jobcontrol_list()
    mid = jobname.replace("HSD17B13_C52_", "")
    logf = JOBDIR / mid / f"{jobname}_multisim.log"
    for line in out.splitlines():
        if jobname in line:
            if "running" in line:
                return False
            if "finished" in line or "complete" in line.lower():
                return True
    if logf.exists():
        txt = logf.read_text(errors="ignore")
        if "Multisim completed" in txt:
            return True
        if "ERROR" in txt and "Fail" in txt:
            return True
    if jobname not in out and logf.exists():
        return True if "Multisim completed" in logf.read_text(errors="ignore") else None
    return None


def mark_finished(mid: str, jobname: str, t_submit: str, status: str, notes: str = "") -> None:
    t_end = datetime.now().isoformat(timespec="seconds")
    try:
        wall_h = f"{(datetime.fromisoformat(t_end) - datetime.fromisoformat(t_submit)).total_seconds() / 3600.0:.3f}"
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


def run_queue(ids: list[str]) -> None:
    pending = list(ids)
    finished_ids: set[str] = set()
    active: dict[int, dict] = {}
    log(f"Phase C start NGPU={NGPU} n={len(ids)} protocol={MSJ.name}")

    def next_mol() -> str | None:
        launched = {info["mid"] for info in active.values()} | finished_ids
        for mid in pending:
            if mid not in launched:
                return mid
        return None

    while len(finished_ids) < len(ids) or active:
        for gpu in list(active):
            info = active[gpu]
            st = job_done(info["jobname"])
            if st is True:
                log(f"DONE gpu={gpu} {info['mid']}")
                mark_finished(info["mid"], info["jobname"], info["t_submit"], "completed")
                finished_ids.add(info["mid"])
                del active[gpu]
            elif st is None and time.time() - info["t0"] > 3600 * 14:
                log(f"TIMEOUT? gpu={gpu} {info['mid']}")
                mark_finished(
                    info["mid"], info["jobname"], info["t_submit"], "unknown", "timeout_check"
                )
                finished_ids.add(info["mid"])
                del active[gpu]

        for gpu in range(NGPU):
            if gpu in active:
                continue
            mid = next_mol()
            if mid is None:
                break
            try:
                jobname, jobid = launch(mid, gpu)
                active[gpu] = {
                    "mid": mid,
                    "jobname": jobname,
                    "t_submit": datetime.now().isoformat(timespec="seconds"),
                    "t0": time.time(),
                }
                log(f"LAUNCH gpu={gpu} {mid} {jobname} {jobid}")
            except Exception as e:
                log(f"FAIL launch {mid}: {e}")
                mark_finished(mid, "", "", "launch_failed", str(e))
                finished_ids.add(mid)

        time.sleep(45)

    log("Phase C queue drained.")
    (ROOT / "06_reports/PHASE_C_NEXT13_DONE.flag").write_text(
        datetime.now().isoformat() + "\n" + "\n".join(ids) + "\n"
    )


def main() -> None:
    ids = load_ids()
    verify_ids_from_csv(ids)
    dry_prep(ids)

    if os.environ.get("CONFIRM_PHASE_C") != "YES":
        print(
            "\n".join(
                [
                    "=== Phase C dry-prep ONLY (no MD submitted) ===",
                    f"jobdir: {JOBDIR}",
                    f"n: {len(ids)}",
                    "To launch later (AFTER B200 finishes):",
                    "  CONFIRM_PHASE_C=YES python3 scripts/08_phaseC_next13_6gpu.py",
                    "Gate env: CONFIRM_PHASE_C=YES",
                    "Do NOT compete with HSD17B13_B200_* GPUs.",
                ]
            )
        )
        return

    still = b200_still_running()
    force = os.environ.get("FORCE_PHASE_C_OVER_B200") == "YES"
    if still and not force:
        raise SystemExit(
            "Refusing to launch: B200 still running:\n  "
            + "\n  ".join(still)
            + "\nWait for B200 or set FORCE_PHASE_C_OVER_B200=YES (not recommended)."
        )

    (ROOT / "06_reports/PHASE_C_NEXT13_LAUNCHED.flag").write_text(
        datetime.now().isoformat() + "\n" + "\n".join(ids) + "\n"
    )
    run_queue(ids)


if __name__ == "__main__":
    main()
