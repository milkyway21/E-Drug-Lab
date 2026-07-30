#!/usr/bin/env python3
"""Generate Simulation Event Analysis data for validated Phase F trajectories."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from phaseF_common import ANALYSIS_ROOT, IDS_FILE, LOG_ROOT, SCHRODINGER, TRAJECTORY_ROOT, trajectory_dir

OUT_ROOT = ANALYSIS_ROOT / "sea"
LOG = LOG_ROOT / "sea.log"
REPORT_LOCK = threading.Lock()


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as handle:
        handle.write(line + "\n")


def validated_attempt(mid: str) -> Path:
    for attempt in sorted((TRAJECTORY_ROOT / mid).glob("attempt_*"), reverse=True):
        validation = attempt / "attempt_validation.json"
        if validation.exists() and json.loads(validation.read_text()).get("valid"):
            return attempt
    raise FileNotFoundError(f"{mid}: no hard-validated Phase F attempt")


def run(command: list[str], cwd: Path, log_path: Path, timeout: int) -> None:
    environment = os.environ.copy()
    environment.update({
        "SCHRODINGER": SCHRODINGER, "CUDA_VISIBLE_DEVICES": "",
        "SCHRODINGER_CUDA_VISIBLE_DEVICES": "", "MPLBACKEND": "Agg",
        "QT_QPA_PLATFORM": "offscreen",
    })
    tempdir = cwd / ".schrodinger_tmp"
    tempdir.mkdir(exist_ok=True)
    environment["SCHRODINGER_TEMPDIR"] = str(tempdir)
    with log_path.open("w") as stream:
        stream.write("CMD: " + " ".join(command) + "\n")
        stream.flush()
        result = subprocess.run(
            command, cwd=cwd, env=environment, stdout=stream,
            stderr=subprocess.STDOUT, timeout=timeout,
        )
    if result.returncode:
        raise RuntimeError(f"rc={result.returncode}; see {log_path}")


def process_one(mid: str) -> str:
    attempt = validated_attempt(mid)
    cms = attempt / f"{mid}_202ns-out.cms"
    dtr = trajectory_dir(attempt)
    output = OUT_ROOT / mid
    data = output / "data"
    output.mkdir(parents=True, exist_ok=True)
    data.mkdir(exist_ok=True)
    marker = output / "SEA_DONE.flag"
    if marker.exists() and (data / "PL_RMSD.dat").stat().st_size > 100:
        return mid
    base = f"{mid}_F202_sea"
    input_eaf = output / f"{base}-in.eaf"
    output_eaf = output / f"{base}-out.eaf"
    if not input_eaf.exists():
        run(
            [f"{SCHRODINGER}/run", "event_analysis.py", "analyze", str(cms),
             "-prot", "protein", "-lig", "res.ptype UNK", "-out", base],
            output, output / "01_gen_eaf.log", 1800,
        )
    if not output_eaf.exists() or output_eaf.stat().st_size < 1000:
        started = time.time()
        run(
            ["nice", "-n", "10", f"{SCHRODINGER}/run", "analyze_simulation.py",
             "-LOCAL", "-WAIT", "-JOBNAME", f"HSD17B13_SEA_F202_{mid}",
             str(cms), str(dtr), output_eaf.name, input_eaf.name],
            output, output / "02_analyze_sim.log", 12 * 3600,
        )
        log(f"{mid}: SEA backend {(time.time() - started) / 60:.1f} min")
    with REPORT_LOCK:
        if not (data / "PL_RMSD.dat").exists():
            run(
                [f"{SCHRODINGER}/run", "event_analysis.py", "report", str(output_eaf),
                 "-data", "-data_dir", str(data)],
                output, output / "03_report_data.log", 2 * 3600,
            )
    required = ["PL_RMSD.dat", "P_RMSF.dat", "L_RMSF.dat", "L-Properties.dat"]
    missing = [name for name in required if not (data / name).exists()]
    if missing:
        raise RuntimeError(f"{mid}: missing SEA exports {missing}")
    (output / "source_attempt.txt").write_text(str(attempt) + "\n")
    marker.write_text(datetime.now().isoformat() + "\n")
    return mid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--ids", nargs="*")
    args = parser.parse_args()
    molecule_ids = args.ids or IDS_FILE.read_text().split()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    successful, failed = [], []
    log(f"SEA START n={len(molecule_ids)} jobs={args.jobs}")
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
        futures = {executor.submit(process_one, mid): mid for mid in molecule_ids}
        for future in as_completed(futures):
            mid = futures[future]
            try:
                successful.append(future.result())
                log(f"SEA PASS {mid}")
            except Exception as error:
                failed.append(mid)
                log(f"SEA FAIL {mid}: {error!r}")
    (OUT_ROOT / "SEA_BATCH_STATUS.txt").write_text(
        f"time={datetime.now().isoformat()}\nok={sorted(successful)}\nfailed={sorted(failed)}\n"
    )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
