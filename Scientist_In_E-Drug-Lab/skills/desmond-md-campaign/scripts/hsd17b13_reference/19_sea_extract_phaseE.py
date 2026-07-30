#!/usr/bin/env python3
"""Extract Desmond SEA tables for completed corrected-pose Phase E runs."""
from __future__ import annotations

import argparse
import os
import subprocess
import tarfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")
TRAJ_ROOT = ROOT / "04_trajectories/phaseE_corrected_pose_2_50_all40_20260727"
OUT_ROOT = ROOT / "05_analysis/phaseE_corrected_pose_2_50_all40_20260727/sea"
LOG = ROOT / "logs/phaseE_sea_extract.log"
LIG_ASL = "res.ptype UNK"
PROT_ASL = "protein"
REPORT_LOCK = threading.Lock()


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def completed_attempt(molecule_id: str) -> Path:
    candidates = []
    for attempt in sorted((TRAJ_ROOT / molecule_id).glob("attempt_*"), reverse=True):
        cms = attempt / f"{molecule_id}_52ns-out.cms"
        archives = list(attempt.glob("HSD17B13_E52C_*_6-out.tgz"))
        if cms.stat().st_size > 1_000_000 if cms.exists() else False:
            if archives and archives[0].stat().st_size > 1_000_000:
                candidates.append(attempt)
    if not candidates:
        raise FileNotFoundError(f"{molecule_id}: no completed Phase E attempt")
    return candidates[0]


def completed_ids() -> list[str]:
    result = []
    for molecule_dir in sorted(TRAJ_ROOT.iterdir()):
        if not molecule_dir.is_dir():
            continue
        try:
            completed_attempt(molecule_dir.name)
        except FileNotFoundError:
            continue
        result.append(molecule_dir.name)
    return result


def ensure_trajectory(molecule_id: str, attempt: Path) -> Path:
    direct = list(attempt.glob("HSD17B13_E52C_*_6_trj"))
    if direct and (direct[0] / "clickme.dtr").exists():
        return direct[0]

    archive = next(attempt.glob("HSD17B13_E52C_*_6-out.tgz"))
    job_stem = archive.name[: -len("-out.tgz")]
    nested = attempt / job_stem / f"{job_stem}_trj"
    if not (nested / "clickme.dtr").exists():
        log(f"{molecule_id}: unpack {archive.name}")
        with tarfile.open(archive, "r:gz") as handle:
            handle.extractall(attempt)
    if not (nested / "clickme.dtr").exists() or not (nested / "timekeys").exists():
        raise RuntimeError(f"{molecule_id}: incomplete trajectory after unpack")
    return nested


def run(command: list[str], cwd: Path, output: Path, timeout: int) -> None:
    environment = os.environ.copy()
    environment["SCHRODINGER"] = SCHRODINGER
    environment["CUDA_VISIBLE_DEVICES"] = ""
    environment["SCHRODINGER_CUDA_VISIBLE_DEVICES"] = ""
    environment.setdefault("MPLBACKEND", "Agg")
    temporary = cwd / ".schrodinger_tmp"
    temporary.mkdir(exist_ok=True)
    environment["SCHRODINGER_TEMPDIR"] = str(temporary)
    with output.open("w") as stream:
        stream.write("CMD: " + " ".join(command) + "\n")
        stream.flush()
        process = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    if process.returncode:
        raise RuntimeError(f"command failed rc={process.returncode}; see {output}")


def process_one(molecule_id: str) -> str:
    attempt = completed_attempt(molecule_id)
    cms = attempt / f"{molecule_id}_52ns-out.cms"
    trajectory = ensure_trajectory(molecule_id, attempt)
    output = OUT_ROOT / molecule_id
    data = output / "data"
    output.mkdir(parents=True, exist_ok=True)
    data.mkdir(exist_ok=True)
    marker = output / "SEA_DONE.flag"
    rmsd_table = data / "PL_RMSD.dat"
    if marker.exists() and rmsd_table.exists() and rmsd_table.stat().st_size > 100:
        return molecule_id

    base = f"{molecule_id}_E52C_sea"
    input_eaf = output / f"{base}-in.eaf"
    output_eaf = output / f"{base}-out.eaf"
    if not input_eaf.exists():
        run(
            [f"{SCHRODINGER}/run", "event_analysis.py", "analyze", str(cms),
             "-prot", PROT_ASL, "-lig", LIG_ASL, "-out", base],
            output,
            output / "01_gen_eaf.log",
            1800,
        )
    if not output_eaf.exists() or output_eaf.stat().st_size < 1000:
        started = time.time()
        run(
            ["nice", "-n", "10", f"{SCHRODINGER}/run", "analyze_simulation.py",
             "-LOCAL", "-WAIT", "-JOBNAME", f"HSD17B13_SEA_E52C_{molecule_id}",
             str(cms), str(trajectory), output_eaf.name, input_eaf.name],
            output,
            output / "02_analyze_sim.log",
            6 * 3600,
        )
        log(f"{molecule_id}: SEA backend completed in {(time.time() - started) / 60:.1f} min")
    if not (data / "PL_RMSD.dat").exists():
        with REPORT_LOCK:
            run(
                [f"{SCHRODINGER}/run", "event_analysis.py", "report", str(output_eaf),
                 "-data", "-data_dir", str(data)],
                output,
                output / "03_report.log",
                2 * 3600,
            )
    required = ["PL_RMSD.dat", "P_RMSF.dat", "L_RMSF.dat", "L-Properties.dat"]
    missing = [name for name in required if not (data / name).exists()]
    if missing:
        raise RuntimeError(f"{molecule_id}: missing SEA outputs {missing}")
    (output / "source_attempt.txt").write_text(str(attempt) + "\n")
    marker.write_text(datetime.now().isoformat() + "\n")
    return molecule_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    ids = args.ids or completed_ids()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    log(f"Phase E SEA start n={len(ids)} jobs={args.jobs} ids={ids}")
    ok, failed = [], []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
        futures = {executor.submit(process_one, molecule_id): molecule_id for molecule_id in ids}
        for future in as_completed(futures):
            molecule_id = futures[future]
            try:
                ok.append(future.result())
                log(f"{molecule_id}: DONE")
            except Exception as error:
                failed.append(molecule_id)
                log(f"{molecule_id}: FAIL {error}")
    status = OUT_ROOT / "SEA_BATCH_STATUS.txt"
    status.write_text(f"time={datetime.now().isoformat()}\nok={sorted(ok)}\nfailed={sorted(failed)}\n")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
