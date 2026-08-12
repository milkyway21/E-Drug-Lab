#!/usr/bin/env python3
"""Summarize attempt-level hard validation for a Desmond campaign."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectory-root", type=Path, required=True)
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--ids-file", type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--json", type=Path)
    return parser.parse_args()


def molecule_ids(args: argparse.Namespace) -> list[str]:
    values = list(args.ids or [])
    if args.ids_file:
        values.extend(args.ids_file.read_text().split())
    if not values:
        values = [path.name for path in args.trajectory_root.iterdir() if path.is_dir()]
    return list(dict.fromkeys(values))


def summarize(root: Path, molecule_id: str) -> dict:
    attempts = sorted(path for path in (root / molecule_id).glob("attempt_*") if path.is_dir())
    row = {
        "molecule_id": molecule_id,
        "status": "not_started",
        "attempts": len(attempts),
        "valid_attempt": "",
        "production_frames": None,
        "production_last_ps": None,
        "maximum_frame_gap_ps": None,
        "error": "",
    }
    invalid = []
    for attempt in reversed(attempts):
        validation = attempt / "attempt_validation.json"
        if not validation.is_file():
            continue
        try:
            data = json.loads(validation.read_text())
        except json.JSONDecodeError as error:
            invalid.append(f"{attempt.name}: invalid JSON ({error})")
            continue
        if data.get("valid"):
            row.update(
                {
                    "status": "completed",
                    "valid_attempt": attempt.name,
                    "production_frames": data.get("production_frames", data.get("frames")),
                    "production_last_ps": data.get("production_last_ps", data.get("last_ps")),
                    "maximum_frame_gap_ps": data.get("maximum_frame_gap_ps"),
                }
            )
            return row
        invalid.append(f"{attempt.name}: {data.get('error', 'validation failed')}")
    if attempts:
        row["status"] = "invalid_or_unvalidated" if invalid else "running_or_unvalidated"
        row["error"] = " | ".join(invalid)
    return row


def main() -> None:
    args = parse_args()
    ids = molecule_ids(args)
    rows = [summarize(args.trajectory_root, molecule_id) for molecule_id in ids]
    table = pd.DataFrame(rows)
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(args.csv, index=False)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "trajectory_root": str(args.trajectory_root.resolve()),
        "total": len(rows),
        "completed": int((table["status"] == "completed").sum()) if len(table) else 0,
        "rows": rows,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2) + "\n")
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
