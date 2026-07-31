#!/usr/bin/env python3
"""Hard-validate a Desmond production CMS/DTR pair and emit machine-readable QC."""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime
from pathlib import Path

import numpy as np
from schrodinger.application.desmond.packages import topo, traj


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cms", type=Path, required=True)
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--minimum-ns", type=float, required=True)
    parser.add_argument("--expected-interval-ps", type=float, default=200.0)
    parser.add_argument("--interval-tolerance", type=float, default=1.26)
    parser.add_argument("--minimum-cms-bytes", type=int, default=100_000)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def validate(args: argparse.Namespace) -> dict:
    result = {
        "valid": False,
        "validated_at": datetime.now().isoformat(),
        "cms": str(args.cms.resolve()),
        "trajectory": str(args.trajectory.resolve()),
        "minimum_ns": args.minimum_ns,
        "expected_interval_ps": args.expected_interval_ps,
    }
    try:
        if not args.cms.is_file() or args.cms.stat().st_size <= args.minimum_cms_bytes:
            raise RuntimeError("final CMS is missing or implausibly small")
        if not args.trajectory.is_dir() or not (args.trajectory / "clickme.dtr").is_file():
            raise RuntimeError("trajectory directory or clickme.dtr is missing")
        frames = traj.read_traj(str(args.trajectory))
        times = np.asarray([frame.time for frame in frames], dtype=float)
        required_frames = math.floor(args.minimum_ns * 1000.0 / args.expected_interval_ps) + 1
        if len(frames) < required_frames:
            raise RuntimeError(f"too few frames: {len(frames)} < {required_frames}")
        if not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0):
            raise RuntimeError("frame times are non-finite or not strictly increasing")
        coverage_ps = float(times[-1] - times[0])
        if coverage_ps < args.minimum_ns * 1000.0 - 2.0:
            raise RuntimeError(
                f"production coverage is {coverage_ps / 1000.0:.6f} ns; "
                f"require {args.minimum_ns:.6f} ns"
            )
        maximum_gap = float(np.max(np.diff(times)))
        allowed_gap = args.expected_interval_ps * args.interval_tolerance
        if maximum_gap > allowed_gap:
            raise RuntimeError(f"frame gap {maximum_gap:.3f} ps exceeds {allowed_gap:.3f} ps")
        _, cms = topo.read_cms(str(args.cms))
        consistency = topo.check_consistency(cms, frames[-1])
        if consistency is not None:
            raise RuntimeError(f"topology inconsistent with final frame: {consistency}")
        final_box = np.asarray(frames[-1].box, dtype=float).reshape(3, 3)
        if not np.all(np.isfinite(final_box)) or abs(float(np.linalg.det(final_box))) < 1e-6:
            raise RuntimeError("final frame has an invalid box matrix")
        result.update(
            {
                "valid": True,
                "cms_bytes": args.cms.stat().st_size,
                "atom_total": int(cms.atom_total),
                "frames": len(frames),
                "first_ps": float(times[0]),
                "last_ps": float(times[-1]),
                "coverage_ns": coverage_ps / 1000.0,
                "maximum_frame_gap_ps": maximum_gap,
                "topology_consistency": "pass",
                "final_box_matrix": final_box.tolist(),
            }
        )
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    return result


def main() -> None:
    args = parse_args()
    result = validate(args)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(payload)
        os.replace(temporary, args.output)
    print(payload, end="")
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
