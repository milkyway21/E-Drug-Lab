#!/usr/bin/env python3
"""SEA extract + plots for completed Phase B Top6 × 200 ns.

CPU-only. Writes under 05_analysis/phaseB_200ns/<mid>/ so Phase A SEA is kept.

Pipeline:
  1) unpack HSD17B13_B200_<mid>_6-out.tgz traj next to *_202ns-out.cms
  2) event_analysis.py analyze -> *-in.eaf
  3) analyze_simulation.py     -> *-out.eaf
  4) event_analysis.py report -data -plots (then -plots retry if needed)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tarfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")
PHASEB = ROOT / "04_trajectories/phaseB_200ns"
OUTROOT = ROOT / "05_analysis/phaseB_200ns"
LOG = ROOT / "logs/sea_extract_b200.log"

LIG_ASL = "res.ptype UNK"
PROT_ASL = "(protein)"
TOP6 = ["T3040", "T0465", "T4965", "T3232", "T39220", "T5135"]


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def ensure_traj(mid: str) -> Path:
    work = PHASEB / mid
    cms = work / f"{mid}_202ns-out.cms"
    if not cms.exists():
        raise FileNotFoundError(cms)
    trj_name = f"HSD17B13_B200_{mid}_6_trj"
    trj = work / trj_name
    if trj.exists() and (trj / "clickme.dtr").exists():
        return trj
    tgz = work / f"HSD17B13_B200_{mid}_6-out.tgz"
    if not tgz.exists():
        raise FileNotFoundError(tgz)
    log(f"{mid}: unpack {tgz.name}")
    with tarfile.open(tgz, "r:gz") as tf:
        tf.extractall(work)
    nested = work / f"HSD17B13_B200_{mid}_6" / trj_name
    if nested.exists() and not trj.exists():
        nested.rename(trj)
    if not trj.exists() and nested.exists() and (nested / "clickme.dtr").exists():
        nested.rename(trj)
    if not (trj / "clickme.dtr").exists():
        raise RuntimeError(f"{mid}: traj incomplete after unpack: {trj}")
    return trj


def run(cmd: list[str], cwd: Path, log_path: Path, timeout: int | None = None) -> None:
    env = os.environ.copy()
    env["SCHRODINGER"] = SCHRODINGER
    env["CUDA_VISIBLE_DEVICES"] = ""
    env.setdefault("MPLBACKEND", "Agg")
    job_tmp = Path(cwd) / ".schrodinger_tmp"
    job_tmp.mkdir(exist_ok=True)
    env["SCHRODINGER_TEMPDIR"] = str(job_tmp)
    with log_path.open("w") as lf:
        lf.write("CMD: " + " ".join(cmd) + "\n")
        lf.flush()
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=lf,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    if p.returncode != 0:
        raise RuntimeError(f"cmd failed rc={p.returncode}: see {log_path}")


def mirror_outputs(mid: str, data_dir: Path) -> None:
    inter = ROOT / "05_analysis/interaction_tables" / f"{mid}_B200"
    plots = ROOT / "05_analysis/plots" / f"{mid}_B200"
    inter.mkdir(parents=True, exist_ok=True)
    plots.mkdir(parents=True, exist_ok=True)
    for f in data_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() in {".png", ".pdf", ".svg", ".jpg"}:
            dest = plots / f.name
        else:
            dest = inter / f.name
        dest.write_bytes(f.read_bytes())


def process_one(mid: str) -> str:
    out = OUTROOT / mid
    out.mkdir(parents=True, exist_ok=True)
    marker = out / "SEA_DONE.flag"
    if marker.exists() and (out / "data" / "PL_RMSD.dat").exists():
        log(f"{mid}: skip (already done)")
        return mid

    work = PHASEB / mid
    cms = work / f"{mid}_202ns-out.cms"
    trj = ensure_traj(mid)
    base = f"{mid}_B200_sea"
    in_eaf = out / f"{base}-in.eaf"
    out_eaf = out / f"{base}-out.eaf"
    data_dir = out / "data"
    data_dir.mkdir(exist_ok=True)

    if not in_eaf.exists():
        log(f"{mid}: generate in.eaf")
        run(
            [
                f"{SCHRODINGER}/run",
                "event_analysis.py",
                "analyze",
                str(cms),
                "-prot",
                PROT_ASL,
                "-lig",
                LIG_ASL,
                "-out",
                base,
            ],
            cwd=out,
            log_path=out / "01_gen_eaf.log",
        )

    if not out_eaf.exists() or out_eaf.stat().st_size < 1000:
        log(f"{mid}: analyze_simulation (CPU, ~1000 frames)")
        t0 = time.time()
        run(
            [
                "nice",
                "-n",
                "10",
                f"{SCHRODINGER}/run",
                "analyze_simulation.py",
                "-LOCAL",
                "-WAIT",
                "-JOBNAME",
                f"HSD17B13_SEA_B200_{mid}",
                str(cms),
                str(trj),
                f"{base}-out.eaf",
                f"{base}-in.eaf",
            ],
            cwd=out,
            log_path=out / "02_analyze_sim.log",
            timeout=3600 * 12,
        )
        log(f"{mid}: analyze done in {(time.time() - t0) / 60:.1f} min")

    if not (data_dir / "PL_RMSD.dat").exists():
        log(f"{mid}: report -data")
        try:
            run(
                [
                    f"{SCHRODINGER}/run",
                    "event_analysis.py",
                    "report",
                    str(out_eaf),
                    "-data",
                    "-plots",
                    "-data_dir",
                    str(data_dir),
                ],
                cwd=out,
                log_path=out / "03_report.log",
                timeout=3600 * 2,
            )
        except RuntimeError:
            log(f"{mid}: combined report failed; retry -data then -plots")
            run(
                [
                    f"{SCHRODINGER}/run",
                    "event_analysis.py",
                    "report",
                    str(out_eaf),
                    "-data",
                    "-data_dir",
                    str(data_dir),
                ],
                cwd=out,
                log_path=out / "03_report_data.log",
                timeout=3600,
            )
            if not (data_dir / "PL-RMSD.png").exists():
                run(
                    [
                        f"{SCHRODINGER}/run",
                        "event_analysis.py",
                        "report",
                        str(out_eaf),
                        "-plots",
                        "-data_dir",
                        str(data_dir),
                    ],
                    cwd=out,
                    log_path=out / "03_report_plots.log",
                    timeout=3600,
                )

    if not (data_dir / "PL_RMSD.dat").exists():
        raise RuntimeError(f"{mid}: missing PL_RMSD.dat after report")

    mirror_outputs(mid, data_dir)
    marker.write_text(datetime.now().isoformat() + "\n")
    log(f"{mid}: DONE -> {out}")
    return mid


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=None)
    ap.add_argument("--jobs", type=int, default=3, help="parallel SEA jobs")
    args = ap.parse_args()
    ids = args.ids or TOP6
    OUTROOT.mkdir(parents=True, exist_ok=True)
    log(f"B200 SEA start n={len(ids)} jobs={args.jobs} ids={ids}")

    # unpack traj first (serial, IO heavy)
    for mid in ids:
        ensure_traj(mid)

    ok, fail = [], []
    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        futs = {ex.submit(process_one, mid): mid for mid in ids}
        for fut in as_completed(futs):
            mid = futs[fut]
            try:
                ok.append(fut.result())
            except Exception as e:
                log(f"{mid}: FAIL {e}")
                fail.append(mid)

    status = OUTROOT / "SEA_BATCH_STATUS.txt"
    status.write_text(
        f"time={datetime.now().isoformat()}\nok={ok}\nfail={fail}\n"
    )
    log(f"B200 SEA finished ok={ok} fail={fail}")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
