#!/usr/bin/env python3
"""Extract ligand-only structures from a Maestro pose viewer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from schrodinger import structure
from schrodinger.structutils import analyze


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract ligand-only records from a PV MAE/MAEGZ file."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ligand-asl", required=True)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"input does not exist: {args.input}")
    if args.limit < 0:
        parser.error("--limit must be non-negative")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    records = 0
    written = 0
    rejected = []
    with structure.StructureReader(str(args.input)) as reader:
        with structure.StructureWriter(str(args.output), format="sdf") as writer:
            for index, pose in enumerate(reader, start=1):
                records += 1
                if args.limit and written >= args.limit:
                    break
                try:
                    atom_ids = analyze.get_atoms_from_asl(pose, args.ligand_asl)
                    if not atom_ids:
                        raise ValueError("ligand ASL selected zero atoms")
                    ligand = pose.extract(atom_ids, copy_props=True)
                    writer.append(ligand)
                    written += 1
                except Exception as exc:
                    rejected.append({"record_index": index, "reason": str(exc)})

    summary = {
        "input": str(args.input),
        "output": str(args.output),
        "ligand_asl": args.ligand_asl,
        "records_seen": records,
        "records_written": written,
        "records_rejected": len(rejected),
        "rejections": rejected,
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
