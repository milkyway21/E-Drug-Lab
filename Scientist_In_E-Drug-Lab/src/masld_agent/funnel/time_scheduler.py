"""Adaptive timing and low-cost liveness state for long funnel tasks."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from masld_agent.funnel.manifest import STAGE_ORDER, campaign_root, stage_config


MAX_STAGE_TIMEOUT_SECONDS = 48 * 60 * 60
WATCHDOG_POLL_SECONDS = 60
TERMINAL_STATUSES = {"completed", "planned", "blocked_or_failed", "failed", "gated_preflight"}
STAGE_EXPECTED_MINUTES = {
    "H0": 5,
    "H1A": 120,
    "H1B": 180,
    "H2": 60,
    "H3": 60,
    "H4": 30,
    "H5": 60,
    "H6": 120,
    "H7": 120,
    "H8": 360,
    "H9": 1440,
    "H10": 30,
}


def _report_base(manifest: dict[str, Any]) -> Path:
    configured = (manifest.get("stage_output_directories") or {}).get("reports")
    base = Path(configured) if configured else Path("reports")
    return base if base.is_absolute() else campaign_root(manifest) / base


def autopilot_state_path(manifest: dict[str, Any]) -> Path:
    return _report_base(manifest) / "funnel" / "AUTOPILOT_STATE.json"


def heartbeat_path(manifest: dict[str, Any]) -> Path:
    return _report_base(manifest) / "funnel" / "AUTOPILOT_HEARTBEAT.json"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_autopilot_state(manifest: dict[str, Any]) -> dict[str, Any]:
    return read_json(autopilot_state_path(manifest))


def update_autopilot_state(manifest: dict[str, Any], **updates: Any) -> dict[str, Any]:
    state = read_autopilot_state(manifest)
    state.update(updates)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(autopilot_state_path(manifest), state)
    return state


def write_heartbeat(manifest: dict[str, Any], **updates: Any) -> dict[str, Any]:
    heartbeat = read_json(heartbeat_path(manifest))
    heartbeat.update(updates)
    heartbeat.update(
        {
            "pid": os.getpid(),
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _atomic_json(heartbeat_path(manifest), heartbeat)
    return heartbeat


def expected_stage_minutes(
    manifest: dict[str, Any], stage: str, *, target_count: int | None = None
) -> int:
    config = stage_config(manifest, stage)
    explicit = config.get("monitor_expected_minutes") or config.get("expected_duration_minutes")
    if explicit is not None:
        return max(1, min(int(explicit), MAX_STAGE_TIMEOUT_SECONDS // 60))
    units = config.get("steps") or []
    if isinstance(units, list):
        timeouts = [int(unit.get("timeout_seconds") or 0) for unit in units if isinstance(unit, dict)]
        if timeouts:
            configured_minutes = max(timeouts) // 120
            return max(
                STAGE_EXPECTED_MINUTES.get(stage.upper(), 30),
                min(configured_minutes, MAX_STAGE_TIMEOUT_SECONDS // 60),
            )
    expected = STAGE_EXPECTED_MINUTES.get(stage.upper(), 30)
    count = target_count or (manifest.get("pipeline_targets") or {}).get(stage)
    if isinstance(count, int) and count >= 100_000:
        expected = max(expected, 180)
    return expected


def monitor_interval_seconds(expected_minutes: int) -> int:
    if expected_minutes <= 20:
        return 10 * 60
    if expected_minutes <= 120:
        return 30 * 60
    if expected_minutes <= 720:
        return 60 * 60
    return 3 * 60 * 60


def interval_schedule(seconds: int) -> str:
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{seconds // 60}m"


def _next_stage(manifest: dict[str, Any], state: dict[str, Any]) -> str:
    current = str(state.get("current_stage") or "").upper()
    if current in STAGE_ORDER:
        return current
    completed = set(state.get("completed_stages") or [])
    return next((stage for stage in STAGE_ORDER if stage not in completed), "H10")


def build_monitor_plan(
    manifest: dict[str, Any], *, stage: str | None = None, now: datetime | None = None
) -> dict[str, Any]:
    state = read_autopilot_state(manifest)
    current_stage = (stage or _next_stage(manifest, state)).upper()
    expected_minutes = expected_stage_minutes(
        manifest,
        current_stage,
        target_count=(manifest.get("pipeline_targets") or {}).get(current_stage),
    )
    interval_seconds = monitor_interval_seconds(expected_minutes)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    next_wake = current_time + timedelta(seconds=interval_seconds)
    return {
        "stage": current_stage,
        "expected_duration_minutes": expected_minutes,
        "interval_seconds": interval_seconds,
        "cron_schedule": interval_schedule(interval_seconds),
        "next_agent_wake_at": next_wake.isoformat(),
        "watchdog_interval_seconds": WATCHDOG_POLL_SECONDS,
        "max_stage_timeout_seconds": MAX_STAGE_TIMEOUT_SECONDS,
        "reason": "adaptive_stage_duration_policy",
    }


def monitor_prompt(manifest: dict[str, Any], plan: dict[str, Any]) -> str:
    return (
        "Read the persistent funnel state and perform one short monitor tick. "
        f"Manifest: {Path(manifest['_manifest_path']).resolve()}. "
        f"Expected stage: {plan['stage']}. Call funnel_autopilot_status first; "
        "if a stage has newly completed, call funnel_report_update with a factual "
        "stage analysis and then schedule the next adaptive tick. If nothing changed, "
        "return exactly [SILENT]. Never resubmit an active job."
    )
