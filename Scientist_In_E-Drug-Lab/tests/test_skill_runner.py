"""Regression tests for the generic, manifest-driven skill launcher."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from masld_agent.skill_runner import run_skill, skill_status


def _manifest(tmp_path: Path, *, command: list[str] | None = None) -> Path:
    root = tmp_path / "campaign"
    root.mkdir(parents=True)
    writer = root / "write_result.py"
    writer.write_text(
        "from pathlib import Path\n"
        "Path('outputs').mkdir(exist_ok=True)\n"
        "Path('outputs/result.dat').write_text('ok\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    manifest = root / "manifest.json"
    payload = {
        "schema_version": "e-drug-lab.skill-manifest/v1",
        "task_id": "runner-test",
        "skill": "generic-test",
        "stage": "T0",
        "campaign_root": ".",
        "inputs": {},
        "outputs": ["outputs/result.dat"],
        "resources": {"timeout_seconds": 60},
        "validation": {},
        "reporting": {"section": "T0"},
        "command": command or [sys.executable, str(writer)],
    }
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest


def test_runner_preview_gate_execute_and_resume(tmp_path: Path):
    manifest = _manifest(tmp_path)

    preview = run_skill(manifest, expected_skill="generic-test")
    assert preview["status"] == "dry_run"
    assert preview["command_preview"]["steps"][0]["command_available"] is True

    gated = run_skill(manifest, expected_skill="generic-test", execute=True)
    assert gated["status"] == "gated"

    completed = run_skill(
        manifest,
        expected_skill="generic-test",
        execute=True,
        confirm=True,
    )
    assert completed["status"] == "completed"
    assert completed["validation"]["valid"] is True
    assert skill_status(manifest, "generic-test")["status"] == "completed"

    resumed = run_skill(
        manifest,
        expected_skill="generic-test",
        execute=True,
        confirm=True,
        resume=True,
    )
    assert resumed["status"] == "completed"
    assert resumed["reused_existing"] is True


def test_runner_rejects_implicit_adapter_and_inline_program(tmp_path: Path):
    missing = _manifest(tmp_path / "missing")
    payload = json.loads(missing.read_text(encoding="utf-8"))
    payload.pop("command")
    missing.write_text(json.dumps(payload), encoding="utf-8")
    result = run_skill(missing, expected_skill="generic-test")
    assert result["status"] == "error"
    assert "must declare command or steps" in result["error"]

    inline = _manifest(tmp_path / "inline", command=[sys.executable, "-c", "print('no')"])
    result = run_skill(inline, expected_skill="generic-test", execute=True, confirm=True)
    assert result["status"] == "error"
    assert "inline shell/interpreter -c" in result["error"]
