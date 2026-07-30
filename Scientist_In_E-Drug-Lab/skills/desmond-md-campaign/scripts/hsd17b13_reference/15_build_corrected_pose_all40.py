#!/usr/bin/env python3
"""Build and validate corrected-pose POPC systems, with resumable outputs."""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from corrected_pose_common import (
    ANALYSIS_ROOT,
    BUILD_PROTOCOL,
    ROOT,
    SYSTEM_ROOT,
    load_ids,
    validate_built_cms,
    write_json,
)


SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")
LOG = ROOT / "logs/phaseE_corrected_pose_build.log"
STATUS = ANALYSIS_ROOT / "build_status.csv"
DONE = ANALYSIS_ROOT / "BUILD_ALL40_DONE.flag"
lock = threading.Lock()


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    with lock:
        print(line, flush=True)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as handle:
            handle.write(line + "\n")


def parse_ids(value: str | None) -> list[str]:
    all_ids = load_ids()
    if not value:
        return all_ids
    requested = [item.strip() for item in value.replace(" ", ",").split(",") if item.strip()]
    unknown = sorted(set(requested) - set(all_ids))
    if unknown:
        raise SystemExit(f"Unknown molecule IDs: {unknown}")
    return requested


def build_one(mid: str) -> dict:
    work = SYSTEM_ROOT / mid
    cms = work / f"{mid}-out.cms"
    qc_path = work / "postbuild_qc.json"
    if cms.exists():
        try:
            qc = validate_built_cms(mid, cms)
            write_json(qc_path, qc)
            log(f"SKIP valid {mid} size={cms.stat().st_size}")
            return {"molecule_id": mid, "status": "valid_existing", **qc}
        except Exception as exc:
            raise RuntimeError(f"Refusing to overwrite invalid existing CMS {cms}: {exc}")

    solute = work / "solute.mae"
    build_msj = work / "build.msj"
    if not solute.exists() or not build_msj.exists():
        raise FileNotFoundError(f"{mid}: run 14_prepare_corrected_pose_all40.py first")
    launch_log = work / "build_launch.log"
    if launch_log.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        launch_log.rename(work / f"build_launch.previous_{stamp}.log")
    jobname = f"HSD17B13_EBLD_{mid}"
    cmd = [
        f"{SCHRODINGER}/utilities/multisim",
        "-WAIT", "-HOST", "localhost", "-maxjob", "1",
        "-JOBNAME", jobname,
        "-m", build_msj.name,
        solute.name,
        "-o", cms.name,
        "-mode", "umbrella",
    ]
    log(f"BUILD start {mid}")
    with launch_log.open("w") as handle:
        completed = subprocess.run(
            cmd, cwd=work, stdout=handle, stderr=subprocess.STDOUT, check=False
        )
    if completed.returncode != 0 or not cms.exists():
        raise RuntimeError(f"{mid}: multisim build failed rc={completed.returncode}")
    qc = validate_built_cms(mid, cms)
    write_json(qc_path, qc)
    log(f"BUILD valid {mid} pose_rmsd={qc['ligand_pose_rmsd_A']:.6f} A")
    return {"molecule_id": mid, "status": "built_valid", **qc}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", help="Comma-separated subset; default is all 40")
    parser.add_argument(
        "--max-parallel", type=int, default=int(os.environ.get("MAX_PARALLEL", "2"))
    )
    args = parser.parse_args()
    ids = parse_ids(args.ids)
    rows = []
    with ThreadPoolExecutor(max_workers=args.max_parallel) as executor:
        futures = {executor.submit(build_one, mid): mid for mid in ids}
        for future in as_completed(futures):
            mid = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                log(f"BUILD FAIL {mid}: {exc}")
                rows.append({"molecule_id": mid, "status": "failed", "error": str(exc)})

    STATUS.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with STATUS.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: ids.index(row["molecule_id"])))
    failures = [row for row in rows if row["status"] == "failed"]
    if failures:
        raise SystemExit(f"Build failures: {[row['molecule_id'] for row in failures]}")
    if len(ids) == 40:
        DONE.write_text(datetime.now().isoformat() + "\n")
    log(f"BUILD batch complete n={len(rows)}")


if __name__ == "__main__":
    main()
