#!/usr/bin/env python3
"""One-time authorized Phase F burst: T60390/T1075 on GPU0/GPU1 only."""
from __future__ import annotations

from datetime import datetime

from phaseF_common import ANALYSIS_ROOT, LOG_ROOT
from importlib import import_module

queue = import_module("25_phaseF_200ns_4gpu")
ASSIGNMENTS = [("T60390", 0), ("T1075", 1)]
AUDIT = ANALYSIS_ROOT / "gpu01_one_time_burst.csv"


def main() -> None:
    rows = []
    for mid, gpu in ASSIGNMENTS:
        if queue.completed_attempt(mid):
            raise RuntimeError(f"{mid}: already completed; burst launch refused")
        if queue.attempts(mid):
            raise RuntimeError(f"{mid}: attempt already exists; burst launch refused")
        if queue.gpu_pids(gpu):
            raise RuntimeError(f"GPU{gpu}: compute process already present")
    for mid, gpu in ASSIGNMENTS:
        info = queue.launch(mid, gpu)
        rows.append(info)
        queue.log(
            f"ONE-TIME BURST LAUNCH gpu={gpu} {mid} attempt={info['attempt']} "
            f"job={info['jobname']} id={info['jobid']}; GPU0/1 will not receive later queue work"
        )
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("w") as handle:
        handle.write("authorized_at,molecule_id,gpu_id,attempt,jobname,jobid,attempt_path,policy\n")
        for info in rows:
            handle.write(
                f"{datetime.now().isoformat(timespec='seconds')},{info['molecule_id']},"
                f"{info['gpu_id']},{info['attempt']},{info['jobname']},{info['jobid']},"
                f"{info['attempt_path']},one_time_only_main_queue_remains_gpu2_5\n"
            )
    print(f"Burst submitted: {[(row['molecule_id'], row['gpu_id']) for row in rows]}")


if __name__ == "__main__":
    main()
