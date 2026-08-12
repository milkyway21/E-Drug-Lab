"""Terminal-session watchdog for a detached funnel worker."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from masld_agent.funnel.manifest import load_manifest
from masld_agent.funnel.time_scheduler import (
    TERMINAL_STATUSES,
    WATCHDOG_POLL_SECONDS,
    read_autopilot_state,
    update_autopilot_state,
    write_heartbeat,
)


def _process_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _process_group_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.killpg(pid, 0)
    except OSError:
        return False
    return True


def _worker_command(manifest: Path, final_count: int, profile: str, task_id: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "masld_agent.funnel.worker",
        "--manifest",
        str(manifest),
        "--final-count",
        str(final_count),
        "--profile",
        profile,
        "--task-id",
        task_id,
        "--confirm",
    ]


def supervise(
    *,
    manifest_path: Path,
    final_count: int,
    profile: str,
    task_id: str,
    worker_pid: int,
    poll_seconds: int = WATCHDOG_POLL_SECONDS,
    max_restarts: int = 3,
) -> dict:
    manifest = load_manifest(manifest_path)
    recovery_count = 0
    while True:
        state = read_autopilot_state(manifest)
        status = str(state.get("status") or "queued")
        write_heartbeat(
            manifest,
            task_id=task_id,
            worker_pid=worker_pid,
            watchdog_pid=os.getpid(),
            worker_alive=_process_alive(worker_pid),
            monitor_status=status,
        )
        if status in TERMINAL_STATUSES:
            return {"status": status, "restarts": recovery_count}
        if _process_alive(worker_pid) or _process_group_alive(worker_pid):
            time.sleep(max(1, poll_seconds))
            continue
        if recovery_count >= max_restarts:
            update_autopilot_state(
                manifest,
                status="failed",
                monitor_status="failed",
                error=f"worker exited and exceeded {max_restarts} automatic recoveries",
                recovery_count=recovery_count,
            )
            return {"status": "failed", "restarts": recovery_count}
        command = _worker_command(manifest_path, final_count, profile, task_id)
        environment = os.environ.copy()
        environment["MASLD_AUTOPILOT_WORKER"] = "1"
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=Path(__file__).resolve().parents[3],
            env=environment,
            start_new_session=True,
        )
        recovery_count += 1
        worker_pid = process.pid
        update_autopilot_state(
            manifest,
            status="queued",
            worker_pid=worker_pid,
            pid=worker_pid,
            watchdog_pid=os.getpid(),
            recovery_count=recovery_count,
            last_recovery_at=datetime.now(timezone.utc).isoformat(),
        )
        time.sleep(max(1, poll_seconds))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--final-count", type=int, required=True)
    parser.add_argument("--profile", choices=("test", "full"), default="full")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--worker-pid", type=int, required=True)
    parser.add_argument("--poll-seconds", type=int, default=WATCHDOG_POLL_SECONDS)
    parser.add_argument("--max-restarts", type=int, default=3)
    args = parser.parse_args()
    result = supervise(
        manifest_path=args.manifest.resolve(),
        final_count=args.final_count,
        profile=args.profile,
        task_id=args.task_id,
        worker_pid=args.worker_pid,
        poll_seconds=args.poll_seconds,
        max_restarts=args.max_restarts,
    )
    print(result, flush=True)


if __name__ == "__main__":
    main()
