"""Detached funnel autopilot worker entrypoint."""
from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from masld_agent.funnel.autopilot import _write_state, run_autopilot
from masld_agent.funnel.manifest import load_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--final-count", type=int, required=True)
    parser.add_argument("--profile", choices=("test", "full"), default="full")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    try:
        result = run_autopilot(
            args.final_count,
            manifest_path=args.manifest,
            profile=args.profile,
            execute=True,
            confirm=args.confirm,
            task_id=args.task_id,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    except Exception as exc:  # noqa: BLE001
        manifest = load_manifest(args.manifest)
        _write_state(
            manifest,
            {
                "task_id": args.task_id,
                "status": "failed",
                "manifest": str(args.manifest.resolve()),
                "final_count": args.final_count,
                "profile": args.profile,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        raise


if __name__ == "__main__":
    main()
