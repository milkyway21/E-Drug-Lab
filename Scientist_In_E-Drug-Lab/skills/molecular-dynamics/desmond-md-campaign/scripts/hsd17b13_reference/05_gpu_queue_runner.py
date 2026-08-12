#!/usr/bin/env python3
"""Dynamic GPU queue for remaining systems AFTER loadtest.
Default: 4 GPUs (0-3) for the remaining 21 molecules.
Requires CONFIRM_FULL=YES and loadtest decision present.
"""
import os, sys, time, subprocess, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHRODINGER = os.environ.get("SCHRODINGER", "/opt/schrodinger2023-3")
NGPU = int(os.environ.get("NGPU", "4"))  # user policy: 4 after loadtest
CPUS_PER = 8

def main():
    if os.environ.get("CONFIRM_FULL") != "YES":
        print("Refusing full queue. Set CONFIRM_FULL=YES after approving loadtest.")
        sys.exit(2)
    all_ids = [l.strip() for l in open(ROOT/"meta/ids_27.txt") if l.strip()]
    load_ids = set(l.strip() for l in open(ROOT/"meta/loadtest_6_ids.txt") if l.strip())
    queue = [m for m in all_ids if m not in load_ids]
    # optionally include loadtest molecules for full production later via INCLUDE_LOADTEST=YES
    if os.environ.get("INCLUDE_LOADTEST") == "YES":
        queue = all_ids[:]
    print(f"Queue {len(queue)} systems on {NGPU} GPUs")
    # Placeholder: actual multisim launch loop to be used after systems built
    (ROOT/"06_reports/queue_pending_21.txt").write_text("\n".join(queue)+"\n")
    print("Wrote 06_reports/queue_pending_21.txt — build remaining CMS then launch.")

if __name__ == "__main__":
    main()
