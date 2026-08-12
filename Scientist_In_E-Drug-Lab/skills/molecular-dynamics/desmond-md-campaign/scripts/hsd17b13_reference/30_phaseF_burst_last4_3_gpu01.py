#!/usr/bin/env python3
"""User-authorized second burst: fourth/third from end on GPU0/GPU1."""
from __future__ import annotations

from datetime import datetime
from importlib import import_module

from phaseF_common import ANALYSIS_ROOT

queue = import_module("25_phaseF_200ns_4gpu")
# In the fixed Phase F selection order, T39220 and T10425 are fourth and
# third from the end, respectively.  Map in ascending physical-GPU order.
ASSIGNMENTS = [("T39220", 0), ("T10425", 1)]
AUDIT = ANALYSIS_ROOT / "gpu01_second_burst.csv"


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
            f"SECOND ONE-TIME BURST LAUNCH gpu={gpu} {mid} attempt={info['attempt']} "
            f"job={info['jobname']} id={info['jobid']}; persistent queue remains GPU2-5"
        )
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("w") as handle:
        handle.write("authorized_at,molecule_id,gpu_id,attempt,jobname,jobid,attempt_path,policy\n")
        for info in rows:
            handle.write(
                f"{datetime.now().isoformat(timespec='seconds')},{info['molecule_id']},"
                f"{info['gpu_id']},{info['attempt']},{info['jobname']},{info['jobid']},"
                f"{info['attempt_path']},removed_from_gpu2_5_waiting_order_one_time_gpu01\n"
            )
    print(f"Second burst submitted: {[(row['molecule_id'], row['gpu_id']) for row in rows]}")


if __name__ == "__main__":
    main()
