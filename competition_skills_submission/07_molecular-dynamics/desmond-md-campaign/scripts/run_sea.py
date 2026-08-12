#!/usr/bin/env python3
"""Run Simulation Event Analysis for hard-validated Desmond trajectories."""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


REPORT_LOCK = threading.Lock()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectory-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--ids", nargs="+")
    parser.add_argument(
        "--sources-csv",
        type=Path,
        help="Portable CSV with molecule_id,cms,trajectory; paths may be CSV-relative",
    )
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--protein-asl", default="protein")
    parser.add_argument("--ligand-asl", required=True)
    parser.add_argument(
        "--run-launcher",
        help="Registry-resolved sz.bin.run executable",
    )
    parser.add_argument(
        "--schrodinger",
        help="Legacy Schrödinger root; prefer --run-launcher",
    )
    parser.add_argument("--official-report", action="store_true")
    args = parser.parse_args()
    if args.run_launcher:
        args.run_launcher = str(Path(args.run_launcher).expanduser())
    elif args.schrodinger:
        args.run_launcher = str(Path(args.schrodinger).expanduser() / "run")
    else:
        parser.error(
            "resolve sz.bin.run with platform-resolve and pass --run-launcher"
        )
    args.schrodinger_root = str(Path(args.run_launcher).expanduser().parent)
    return args


def load_sources(path: Path) -> dict[str, tuple[Path, Path]]:
    sources = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            molecule_id = (row.get("molecule_id") or "").strip()
            cms = Path(row.get("cms") or row.get("final_cms") or "").expanduser()
            trajectory = Path(row.get("trajectory") or row.get("production_trajectory") or "").expanduser()
            if not cms.is_absolute():
                cms = path.parent / cms
            if not trajectory.is_absolute():
                trajectory = path.parent / trajectory
            if molecule_id:
                sources[molecule_id] = (cms.resolve(), trajectory.resolve())
    return sources


def validated_source(args: argparse.Namespace, molecule_id: str) -> tuple[Path, Path]:
    if molecule_id in args.source_map:
        cms, trajectory = args.source_map[molecule_id]
        if cms.is_file() and trajectory.is_dir() and (trajectory / "clickme.dtr").is_file():
            return cms, trajectory
        raise FileNotFoundError(f"{molecule_id}: sources CSV CMS/DTR is unreadable")
    root = args.trajectory_root
    if root is None:
        raise FileNotFoundError(f"{molecule_id}: no trajectory root or sources CSV entry")
    for attempt in sorted((root / molecule_id).glob("attempt_*"), reverse=True):
        path = attempt / "attempt_validation.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text())
        if data.get("valid"):
            cms = Path(data.get("final_cms", data.get("cms", "")))
            trajectory = Path(data.get("production_trajectory", data.get("trajectory", "")))
            if cms.is_file() and trajectory.is_dir():
                return cms, trajectory
    raise FileNotFoundError(f"{molecule_id}: no readable hard-validated CMS/DTR")


def run(command: list[str], cwd: Path, log_path: Path, environment: dict, timeout: int) -> None:
    with log_path.open("w") as stream:
        stream.write("CMD: " + " ".join(command) + "\n")
        stream.flush()
        result = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    if result.returncode:
        raise RuntimeError(f"rc={result.returncode}; see {log_path}")


def process_one(args: argparse.Namespace, molecule_id: str) -> str:
    cms, trajectory = validated_source(args, molecule_id)
    output = args.output_root / molecule_id
    data = output / "data"
    output.mkdir(parents=True, exist_ok=True)
    data.mkdir(exist_ok=True)
    marker = output / "SEA_DONE.flag"
    rmsd = data / "PL_RMSD.dat"
    if marker.is_file() and rmsd.is_file() and rmsd.stat().st_size > 100:
        return molecule_id

    environment = os.environ.copy()
    environment.update(
        {
            "SCHRODINGER": args.schrodinger_root,
            "CUDA_VISIBLE_DEVICES": "",
            "SCHRODINGER_CUDA_VISIBLE_DEVICES": "",
            "MPLBACKEND": "Agg",
            "QT_QPA_PLATFORM": "offscreen",
            "SCHRODINGER_TEMPDIR": str(output / ".schrodinger_tmp"),
        }
    )
    Path(environment["SCHRODINGER_TEMPDIR"]).mkdir(exist_ok=True)
    base = f"{molecule_id}_sea"
    input_eaf = output / f"{base}-in.eaf"
    output_eaf = output / f"{base}-out.eaf"
    if not input_eaf.is_file():
        run(
            [
                args.run_launcher,
                "event_analysis.py",
                "analyze",
                str(cms),
                "-prot",
                args.protein_asl,
                "-lig",
                args.ligand_asl,
                "-out",
                base,
            ],
            output,
            output / "01_gen_eaf.log",
            environment,
            1800,
        )
    if not output_eaf.is_file() or output_eaf.stat().st_size < 1000:
        run(
            [
                "nice",
                "-n",
                "10",
                args.run_launcher,
                "analyze_simulation.py",
                "-LOCAL",
                "-WAIT",
                "-JOBNAME",
                f"SEA_{molecule_id}",
                str(cms),
                str(trajectory),
                output_eaf.name,
                input_eaf.name,
            ],
            output,
            output / "02_analyze_simulation.log",
            environment,
            12 * 3600,
        )
    with REPORT_LOCK:
        if not rmsd.is_file():
            command = [
                args.run_launcher,
                "event_analysis.py",
                "report",
                str(output_eaf),
                "-data",
                "-data_dir",
                str(data),
            ]
            if args.official_report:
                command.extend(["-plots", "-pdf", str(output / f"{molecule_id}_sea.pdf")])
            run(command, output, output / "03_report.log", environment, 2 * 3600)
    required = ["PL_RMSD.dat", "P_RMSF.dat", "L_RMSF.dat", "L-Properties.dat"]
    missing = [name for name in required if not (data / name).is_file()]
    if missing:
        raise RuntimeError(f"{molecule_id}: missing SEA exports {missing}")
    (output / "source.json").write_text(
        json.dumps({"cms": str(cms), "trajectory": str(trajectory)}, indent=2) + "\n"
    )
    marker.write_text(datetime.now().isoformat() + "\n")
    return molecule_id


def main() -> None:
    args = parse_args()
    # Commands run from each molecule output directory. Resolve shared paths
    # once so report generation cannot accidentally prepend that cwd again.
    args.output_root = args.output_root.resolve()
    if args.trajectory_root is not None:
        args.trajectory_root = args.trajectory_root.resolve()
    if args.sources_csv is not None:
        args.sources_csv = args.sources_csv.resolve()
    args.source_map = load_sources(args.sources_csv) if args.sources_csv else {}
    ids = list(args.ids or args.source_map)
    if not ids:
        raise SystemExit("provide --ids or --sources-csv")
    if args.trajectory_root is None and not args.source_map:
        raise SystemExit("provide --trajectory-root or --sources-csv")
    args.output_root.mkdir(parents=True, exist_ok=True)
    started = time.time()
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
        futures = {executor.submit(process_one, args, molecule_id): molecule_id for molecule_id in ids}
        for future in as_completed(futures):
            molecule_id = futures[future]
            try:
                future.result()
                print(f"SEA PASS {molecule_id}", flush=True)
            except Exception as error:
                failed.append(molecule_id)
                print(f"SEA FAIL {molecule_id}: {error!r}", flush=True)
    print(f"SEA elapsed_min={(time.time() - started) / 60.0:.1f}", flush=True)
    if failed:
        raise SystemExit(f"SEA failures: {', '.join(failed)}")


if __name__ == "__main__":
    main()
