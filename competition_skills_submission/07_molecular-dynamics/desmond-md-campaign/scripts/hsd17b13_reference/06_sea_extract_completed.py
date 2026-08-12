#!/usr/bin/env python3
"""Extract full Simulation Event Analysis (SEA / PL interaction survey)
for completed Phase A molecules. CPU-only; does not touch GPUs.

Pipeline per molecule:
  1) unpack production traj from *_6-out.tgz next to *-52ns-out.cms
  2) event_analysis.py analyze  -> *-in.eaf  (all PLIS keywords)
  3) analyze_simulation.py      -> *-out.eaf
  4) event_analysis.py report -data -plots -> text + plots
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tarfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")
PHASEA = ROOT / "04_trajectories/phaseA"
OUTROOT = ROOT / "05_analysis"
LOG = ROOT / "logs/sea_extract.log"

LIG_ASL = "res.ptype UNK"
PROT_ASL = "(protein)"


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def completed_ids() -> list[str]:
    ids = []
    for p in sorted(PHASEA.glob("*/*_52ns-out.cms")):
        ids.append(p.parent.name)
    return ids


def ensure_traj(mid: str) -> Path:
    work = PHASEA / mid
    cms = work / f"{mid}_52ns-out.cms"
    if not cms.exists():
        raise FileNotFoundError(cms)
    trj_name = f"HSD17B13_A52_{mid}_6_trj"
    trj = work / trj_name
    if trj.exists() and (trj / "clickme.dtr").exists():
        return trj
    tgz = work / f"HSD17B13_A52_{mid}_6-out.tgz"
    if not tgz.exists():
        raise FileNotFoundError(tgz)
    log(f"{mid}: unpack {tgz.name}")
    with tarfile.open(tgz, "r:gz") as tf:
        tf.extractall(work)
    nested = work / f"HSD17B13_A52_{mid}_6" / trj_name
    if nested.exists() and not trj.exists():
        nested.rename(trj)
    if not (trj / "clickme.dtr").exists():
        # sometimes clickme is only inside nested after extract
        if nested.exists() and (nested / "clickme.dtr").exists() and not trj.exists():
            nested.rename(trj)
    if not trj.exists():
        raise RuntimeError(f"{mid}: traj not found after unpack")
    return trj


def run(cmd: list[str], cwd: Path, log_path: Path, timeout: int | None = None) -> None:
    env = os.environ.copy()
    env["SCHRODINGER"] = SCHRODINGER
    # never attach to GPUs used by MD
    env["CUDA_VISIBLE_DEVICES"] = ""
    env.setdefault("MPLBACKEND", "Agg")
    # isolate per-job tmp so parallel PDF/report jobs do not clobber image_tmp*.png
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
        raise RuntimeError(f"cmd failed rc={p.returncode}: {' '.join(cmd)} (see {log_path})")


def process_one(mid: str) -> Path:
    out = OUTROOT / "per_molecule" / mid
    out.mkdir(parents=True, exist_ok=True)
    marker = out / "SEA_DONE.flag"
    if marker.exists() and (out / f"{mid}_sea-out.eaf").exists():
        log(f"{mid}: skip (already done)")
        return out

    work = PHASEA / mid
    cms = work / f"{mid}_52ns-out.cms"
    trj = ensure_traj(mid)
    base = f"{mid}_sea"
    in_eaf = out / f"{base}-in.eaf"
    out_eaf = out / f"{base}-out.eaf"
    data_dir = out / "data"
    plots_dir = out / "plots"
    data_dir.mkdir(exist_ok=True)
    plots_dir.mkdir(exist_ok=True)

    # 1) generate analysis definition
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
        if not in_eaf.exists():
            raise RuntimeError(f"{mid}: missing {in_eaf}")

    # 2) run SEA backend
    if not out_eaf.exists() or out_eaf.stat().st_size < 1000:
        log(f"{mid}: analyze_simulation (CPU)")
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
                f"HSD17B13_SEA_{mid}",
                str(cms),
                str(trj),
                f"{base}-out.eaf",
                f"{base}-in.eaf",
            ],
            cwd=out,
            log_path=out / "02_analyze_sim.log",
            timeout=3600 * 6,
        )
        log(f"{mid}: analyze_simulation done in {(time.time()-t0)/60:.1f} min")
        if not out_eaf.exists():
            raise RuntimeError(f"{mid}: missing {out_eaf}")

    # 3) export data + plots (SEA dumps both into data_dir)
    need_report = not (data_dir / "PL_RMSD.dat").exists()
    if need_report:
        log(f"{mid}: export report data/plots")
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
            timeout=3600,
        )

    # mirror tables / plots to top-level analysis dirs
    inter = OUTROOT / "interaction_tables" / mid
    inter.mkdir(parents=True, exist_ok=True)
    plot_mirror = OUTROOT / "plots" / mid
    plot_mirror.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(exist_ok=True)
    for f in data_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() in {".png", ".pdf", ".svg", ".jpg"}:
            for dest in (plot_mirror / f.name, plots_dir / f.name):
                if not dest.exists():
                    dest.write_bytes(f.read_bytes())
        else:
            dest = inter / f.name
            if not dest.exists():
                dest.write_bytes(f.read_bytes())

    marker.write_text(datetime.now().isoformat() + "\n")
    log(f"{mid}: DONE -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--ids",
        nargs="*",
        default=None,
        help="Molecule IDs (default: all with *_52ns-out.cms)",
    )
    args = ap.parse_args()
    ids = args.ids or completed_ids()
    log(f"SEA extract start n={len(ids)} ids={ids}")
    ok, fail = [], []
    for mid in ids:
        try:
            process_one(mid)
            ok.append(mid)
        except Exception as e:
            log(f"{mid}: FAIL {e}")
            fail.append(mid)
    log(f"SEA extract finished ok={ok} fail={fail}")
    (OUTROOT / "SEA_BATCH_STATUS.txt").write_text(
        f"time={datetime.now().isoformat()}\nok={ok}\nfail={fail}\n"
    )


if __name__ == "__main__":
    main()
