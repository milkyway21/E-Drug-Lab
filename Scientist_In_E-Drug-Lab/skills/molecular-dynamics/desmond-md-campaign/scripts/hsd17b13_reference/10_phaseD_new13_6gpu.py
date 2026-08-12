#!/usr/bin/env python3
"""Phase D new13: 2 ns eq + 50 ns prod on 6 GPUs (dynamic queue).

User-specified NEW 13 ligand IDs (NOT phaseC ranks 7–19).
Uses CMS from 03_systems/ (hardlinked into job dirs at prep).

Default: dry-prep only (ensure job dirs / CMS / md.msj).
Launch ONLY when CONFIRM_PHASE_D=YES.

Do NOT run while Phase B200 (HSD17B13_B200_*) still occupies GPUs
unless FORCE_PHASE_D_OVER_B200=YES.
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
# Optional: comma-separated physical GPU ids, e.g. PHASE_D_GPU_LIST=5
# When set, only these GPUs are used (length may be 1 for sequential on one card).
_GPU_LIST_ENV = os.environ.get("PHASE_D_GPU_LIST", "").strip()
GPU_LIST: list[int] | None = (
    [int(x) for x in _GPU_LIST_ENV.replace(" ", ",").split(",") if x.strip()]
    if _GPU_LIST_ENV
    else None
)
MSJ = ROOT / "scripts/protocols/prod_2ns_eq_50ns.msj"
IDS_FILE = ROOT / "meta/phaseD_new13_ids.txt"
META_FILE = ROOT / "meta/phaseD_new13.txt"
POSE_CSV = ROOT / "meta/phaseD_new13_pose_sources.csv"
JOBDIR = ROOT / "04_trajectories/phaseD_2_50_new13"
TIMING = ROOT / "logs/phaseD_new13_timing.csv"
QUEUE_LOG = ROOT / "logs/phaseD_new13_queue.log"

NEW13_FALLBACK = [
    "T66645",
    "T16705",
    "T7151",
    "T60390",
    "T7412",
    "T4342",
    "T21193",
    "T16866",
    "T10425",
    "T27695",
    "T22365",
    "T7591",
    "T34698",
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
    # Optional subset: PHASE_D_IDS="T66645,T16705,..." or argv after --ids
    env_ids = os.environ.get("PHASE_D_IDS", "").strip()
    if env_ids:
        return [x.strip() for x in env_ids.replace(" ", ",").split(",") if x.strip()]
    if IDS_FILE.exists():
        ids = [
            ln.strip()
            for ln in IDS_FILE.read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if len(ids) == 13:
            return ids
    return list(NEW13_FALLBACK)


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
                "note=Await CONFIRM_PHASE_D=YES; do not compete with B200 GPUs",
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
                "# Phase D new13 — user-specified IDs (NOT phaseC ranks 7–19)",
                f"# Pose sources: {POSE_CSV.relative_to(ROOT) if POSE_CSV.exists() else 'N/A'}",
                f"# Protocol: {MSJ.relative_to(ROOT)} (2 ns eq + 50 ns prod)",
                f"# Prepared: {datetime.now().isoformat(timespec='seconds')}",
                "# DO NOT launch until user sets CONFIRM_PHASE_D=YES",
                "# Do NOT compete with HSD17B13_B200_* or SEA processes",
            ]
            + [f"{i+1} {mid}" for i, mid in enumerate(ids)]
            + [""]
        )
    )
    IDS_FILE.write_text("\n".join(ids) + "\n")
    status = JOBDIR / "STATUS.txt"
    status.write_text(
        "\n".join(
            [
                f"phase=D_new13",
                f"n_ids={len(ids)}",
                f"prep_ok={len(ok)}",
                f"prep_fail={len(fail)}",
                f"protocol={MSJ}",
                f"jobdir={JOBDIR}",
                f"gate=CONFIRM_PHASE_D=YES",
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
    readme = JOBDIR / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Phase D new13 — 2 ns eq + 50 ns prod (STAGED, MD NOT STARTED)",
                "",
                "## Molecules (13)",
                "",
                *[f"- `{m}`" for m in ids],
                "",
                "## Pose sources",
                "",
                f"See `{POSE_CSV}` (MMGBSA best pose from xp_top50 / xp_next80).",
                "Occupancy: **single** (same HSD17B13_MD policy).",
                "",
                "## How to launch (after user approval)",
                "",
                "```bash",
                "cd " + str(ROOT),
                "export SCHRODINGER=/opt/schrodinger2023-3",
                "CONFIRM_PHASE_D=YES python3 scripts/10_phaseD_new13_6gpu.py",
                "```",
                "",
                "Gate: `CONFIRM_PHASE_D=YES`.",
                "If B200 still running, launch is refused unless `FORCE_PHASE_D_OVER_B200=YES`.",
                "",
                "## Do NOT",
                "",
                "- Compete with `HSD17B13_B200_*` GPUs",
                "- Kill/pause SEA (`09_sea_extract_b200.py`) or B200 jobs",
                "- Launch without explicit user confirmation",
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
    jobname = f"HSD17B13_D52_{mid}"
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    env.pop("CONFIRM_PHASE_A", None)
    env.pop("CONFIRM_PHASE_B200", None)
    env.pop("CONFIRM_PHASE_C", None)
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
            "notes": "2ns_eq+50ns_prod PhaseD new13",
        }
    )
    return jobname, jobid


def job_done(jobname: str) -> bool | None:
    out = jobcontrol_list()
    mid = jobname.replace("HSD17B13_D52_", "")
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
    active: dict[int, dict] = {}  # physical gpu id -> info
    gpus = list(GPU_LIST) if GPU_LIST else list(range(NGPU))
    log(f"Phase D start GPUS={gpus} n={len(ids)} protocol={MSJ.name}")

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

        for gpu in gpus:
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

    log("Phase D queue drained.")
    tag = "all13" if len(ids) == 13 else "subset_" + "_".join(ids[:3])
    (ROOT / f"06_reports/PHASE_D_NEW13_{tag}_DONE.flag").write_text(
        datetime.now().isoformat() + "\n" + "\n".join(ids) + "\n"
    )


def main() -> None:
    ids = load_ids()
    full_ids = list(NEW13_FALLBACK)
    if IDS_FILE.exists():
        full_from_file = [
            ln.strip()
            for ln in IDS_FILE.read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if len(full_from_file) == 13:
            full_ids = full_from_file

    # Always keep full-13 metadata; only ensure dirs for the launch subset
    if set(ids) == set(full_ids) and len(ids) == 13:
        dry_prep(ids)
    else:
        JOBDIR.mkdir(parents=True, exist_ok=True)
        for mid in ids:
            ensure_job_dir(mid)
        log(f"subset prep n={len(ids)} ids={ids} (full meta left intact)")

    if os.environ.get("CONFIRM_PHASE_D") != "YES":
        print(
            "\n".join(
                [
                    "=== Phase D dry-prep ONLY (no MD submitted) ===",
                    f"jobdir: {JOBDIR}",
                    f"n: {len(ids)}",
                    "To launch later:",
                    "  CONFIRM_PHASE_D=YES python3 scripts/10_phaseD_new13_6gpu.py",
                    "  # first5 on 5 GPUs:",
                    "  CONFIRM_PHASE_D=YES NGPU=5 PHASE_D_IDS=T66645,T16705,T7151,T60390,T7412 \\",
                    "    python3 scripts/10_phaseD_new13_6gpu.py",
                    "Gate env: CONFIRM_PHASE_D=YES",
                    "Do NOT compete with HSD17B13_B200_* GPUs / SEA.",
                ]
            )
        )
        return

    still = b200_still_running()
    force = os.environ.get("FORCE_PHASE_D_OVER_B200") == "YES"
    if still and not force:
        raise SystemExit(
            "Refusing to launch: B200 still running:\n  "
            + "\n  ".join(still)
            + "\nWait for B200 or set FORCE_PHASE_D_OVER_B200=YES (not recommended)."
        )

    (ROOT / "06_reports/PHASE_D_NEW13_LAUNCHED.flag").write_text(
        datetime.now().isoformat()
        + f"\nsubset_n={len(ids)} NGPU={NGPU}\n"
        + "\n".join(ids)
        + "\n"
    )
    run_queue(ids)


if __name__ == "__main__":
    main()
