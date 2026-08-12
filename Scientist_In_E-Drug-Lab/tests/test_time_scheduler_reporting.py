"""Tests for adaptive funnel monitoring and the single cumulative report."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from masld_agent.funnel.manifest import load_manifest
from masld_agent.funnel.time_scheduler import (
    heartbeat_path,
    build_monitor_plan,
    monitor_interval_seconds,
    read_autopilot_state,
    update_autopilot_state,
    write_heartbeat,
)
from masld_agent.reporting.funnel_report import update_funnel_report
from masld_agent.funnel import watchdog


def _manifest(tmp_path: Path, *, stages: dict | None = None) -> Path:
    root = tmp_path / "campaign"
    inputs = root / "inputs"
    inputs.mkdir(parents=True)
    path = inputs / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "campaign_id": "scheduler_report_test",
                "target_id": "TEST",
                "campaign_root": str(root),
                "inputs": {},
                "pipeline_targets": {"H2": 10, "H9": 1},
                "stages": stages or {},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_monitor_intervals_cover_short_to_48_hour_tasks():
    assert monitor_interval_seconds(20) == 600
    assert monitor_interval_seconds(21) == 1800
    assert monitor_interval_seconds(120) == 1800
    assert monitor_interval_seconds(121) == 3600
    assert monitor_interval_seconds(720) == 3600
    assert monitor_interval_seconds(721) == 10800


def test_h9_plan_uses_three_hour_agent_wake(tmp_path: Path):
    manifest_path = _manifest(tmp_path)
    manifest = load_manifest(manifest_path)
    plan = build_monitor_plan(
        manifest,
        stage="H9",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert plan["interval_seconds"] == 10800
    assert plan["cron_schedule"] == "3h"
    assert plan["watchdog_interval_seconds"] == 60
    assert plan["max_stage_timeout_seconds"] == 172800


def test_state_and_heartbeat_are_atomic_and_recoverable(tmp_path: Path):
    manifest_path = _manifest(tmp_path)
    manifest = load_manifest(manifest_path)
    state = update_autopilot_state(manifest, status="running", current_stage="H9", worker_pid=123)
    heartbeat = write_heartbeat(manifest, task_id="task-1", worker_pid=123)
    assert state["status"] == "running"
    assert read_autopilot_state(manifest)["current_stage"] == "H9"
    assert heartbeat["worker_pid"] == 123
    assert heartbeat_path(manifest).is_file()


def test_report_is_one_incremental_document_with_figures(tmp_path: Path):
    figure_dir = tmp_path / "campaign" / "h2_figures"
    figure_dir.mkdir(parents=True)
    figure = figure_dir / "glide_summary.png"
    Image.new("RGB", (120, 80), "#66bb6a").save(figure)
    manifest_path = _manifest(tmp_path, stages={"H2": {"figure_dirs": ["h2_figures"]}})
    first = update_funnel_report(
        manifest_path,
        stage="H1B",
        target_count=100,
        profile="test",
        result={
            "status": "completed",
            "observed_count": 100,
            "validation": {"valid": True, "evidence": [{"path": str(figure)}]},
        },
    )
    second = update_funnel_report(
        manifest_path,
        stage="H2",
        target_count=10,
        profile="test",
        result={"status": "completed", "observed_count": 10, "validation": {"valid": True}},
        analysis="The current Glide result passed artifact validation and is eligible for H3.",
    )
    markdown = Path(second["markdown"]).read_text(encoding="utf-8")
    data = json.loads(Path(second["report_data"]).read_text(encoding="utf-8"))
    assert first["markdown"] == second["markdown"]
    assert "## H1B  completed" in markdown
    assert "## H2  completed" in markdown
    assert "The current Glide result" in markdown
    assert str(figure) not in markdown
    assert "h2_figures/glide_summary.png" in markdown
    assert set(data["stages"]) == {"H1B", "H2"}
    assert Path(second["docx"]).is_file()
    assert Path(second["pdf"]).is_file()
    assert Path(second["pdf"]).stat().st_size > 1000
    figure_paths = [item["path"] for item in data["stages"]["H2"]["figures"]]
    assert any(path.endswith("glide_summary.png") for path in figure_paths)


def test_watchdog_recovers_dead_worker_without_duplicate_completion(tmp_path: Path, monkeypatch):
    manifest_path = _manifest(tmp_path)
    manifest = load_manifest(manifest_path)
    update_autopilot_state(manifest, status="running", current_stage="H9", worker_pid=999999)
    spawned: list[list[str]] = []

    class FakeProcess:
        pid = 222222

    def fake_popen(command, **kwargs):
        spawned.append(command)
        return FakeProcess()

    monkeypatch.setattr(watchdog.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        watchdog.time,
        "sleep",
        lambda _seconds: update_autopilot_state(manifest, status="completed", current_stage="H9"),
    )
    result = watchdog.supervise(
        manifest_path=manifest_path,
        final_count=1,
        profile="test",
        task_id="task-recovery",
        worker_pid=999999,
        poll_seconds=1,
        max_restarts=1,
    )

    assert result == {"status": "completed", "restarts": 1}
    assert len(spawned) == 1
    assert "--task-id" in spawned[0]
