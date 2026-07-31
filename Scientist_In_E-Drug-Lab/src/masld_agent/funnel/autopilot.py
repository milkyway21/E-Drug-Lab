"""Single-call deterministic execution with per-stage reporting."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from masld_agent.funnel.manifest import STAGE_ORDER
from masld_agent.funnel.manifest import campaign_root, load_manifest
from masld_agent.funnel.planner import load_funnel_profile, plan_campaign, resolve_manifest
from masld_agent.funnel.runner import preflight_campaign, run_stage, validate_stage


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _stage_markdown(
    stage: str,
    target_count: int,
    profile: str,
    result: dict[str, Any],
) -> str:
    validation = result.get("validation") or {}
    evidence = validation.get("evidence") or []
    lines = [
        f"# {stage} 自动阶段报告",
        "",
        f"- 状态：`{result.get('status')}`",
        f"- 数量配置：`{profile}`",
        f"- 计划数量：`{target_count}`",
        f"- 复用既有产物：`{bool(result.get('reused_existing'))}`",
        f"- 验收通过：`{bool(validation.get('valid'))}`",
        f"- 后端：`{result.get('backend') or '未配置'}`",
    ]
    if result.get("error"):
        lines.append(f"- 错误：{result['error']}")
    if result.get("log"):
        lines.append(f"- 日志：`{result['log']}`")
    for log in result.get("logs") or []:
        lines.append(f"- 日志：`{log}`")
    lines.extend(["", "## 证据"])
    if not evidence:
        lines.append("- 无已验证证据。")
    for item in evidence:
        lines.append(f"- `{item.get('path')}` — nonempty={item.get('nonempty')}")
    lines.extend(["", f"生成时间：{datetime.now(timezone.utc).isoformat()}", ""])
    return "\n".join(lines)


def _write_stage_report(
    report_root: Path,
    stage: str,
    target_count: int,
    profile: str,
    result: dict[str, Any],
) -> dict[str, str]:
    payload = {"stage": stage, "target_count": target_count, "profile": profile, **result}
    json_path = report_root / f"{stage}.json"
    markdown_path = report_root / f"{stage}.md"
    _atomic_write(json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(markdown_path, _stage_markdown(stage, target_count, profile, result))
    return {"json": str(json_path), "markdown": str(markdown_path)}


def _report_base(manifest: dict[str, Any]) -> Path:
    configured = (manifest.get("stage_output_directories") or {}).get("reports")
    base = Path(configured) if configured else Path("reports")
    if not base.is_absolute():
        base = campaign_root(manifest) / base
    return base


def _report_root(manifest: dict[str, Any], profile: str) -> Path:
    return _report_base(manifest) / "funnel" / profile


def _manifest_state_path(manifest: dict[str, Any]) -> Path:
    return _report_base(manifest) / "funnel" / "AUTOPILOT_STATE.json"


def _write_state(manifest: dict[str, Any], payload: dict[str, Any]) -> None:
    _atomic_write(
        _manifest_state_path(manifest),
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def run_autopilot(
    final_count: int,
    *,
    manifest_path: str | Path | None = None,
    target_id: str | None = None,
    profile: str = "full",
    execute: bool = False,
    confirm: bool = False,
    task_id: str | None = None,
) -> dict[str, Any]:
    plan = plan_campaign(
        final_count,
        manifest_path=manifest_path,
        target_id=target_id,
        profile=profile,
        write=True,
    )
    manifest_path = Path(plan["manifest"])
    manifest_data = load_manifest(manifest_path)
    report_root = _report_root(manifest_data, plan["profile"])
    preflight = preflight_campaign(manifest_path)
    preflight_path = report_root / "PREFLIGHT_EXECUTION.json"
    _atomic_write(preflight_path, json.dumps(preflight, ensure_ascii=False, indent=2) + "\n")
    rows = []
    stopped_at = None
    task = task_id or f"sync-{uuid.uuid4().hex[:10]}"
    _write_state(
        manifest_data,
        {
            "task_id": task,
            "status": "running" if execute else "planning",
            "current_stage": "H0",
            "completed_stages": [],
            "final_count": final_count,
            "profile": plan["profile"],
            "manifest": str(manifest_path),
            "preflight": str(preflight_path),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    if execute and not preflight.get("ready_for_one_shot_execution"):
        blocking_stages = list(preflight.get("blocking_stages") or [])
        stopped_at = blocking_stages[0] if blocking_stages else "H0"
        summary = {
            "status": "gated_preflight",
            "execute": True,
            "confirm": confirm,
            "final_count": final_count,
            "profile": plan["profile"],
            "profile_path": plan["profile_path"],
            "final_stage": plan["final_stage"],
            "manifest": str(manifest_path),
            "plan_path": plan.get("plan_path"),
            "report_root": str(report_root),
            "preflight_report": str(preflight_path),
            "blocking_stages": blocking_stages,
            "stopped_at": stopped_at,
            "stages_processed": 0,
            "rows": [],
            "error": "enabled downstream stages are not ready; no compute was started",
        }
        summary_path = report_root / "AUTOPILOT_SUMMARY.json"
        _atomic_write(summary_path, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        _write_state(
            manifest_data,
            {
                "task_id": task,
                "status": summary["status"],
                "current_stage": stopped_at,
                "completed_stages": [],
                "final_count": final_count,
                "profile": plan["profile"],
                "manifest": str(manifest_path),
                "summary": str(summary_path),
                "preflight": str(preflight_path),
                "blocking_stages": blocking_stages,
                "stopped_at": stopped_at,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return summary
    for stage in STAGE_ORDER:
        target_count = int(plan["stage_targets"][stage])
        if target_count == 0:
            result = {
                "status": "skipped",
                "stage": stage,
                "backend": f"disabled_by_{plan['profile']}_profile",
                "reused_existing": False,
                "validation": {"stage": stage, "valid": True, "evidence": []},
            }
        elif stage == "H0":
            checked = validate_stage(manifest_path, stage)
            result = {
                **checked,
                "reused_existing": bool((checked.get("validation") or {}).get("valid")),
            }
        else:
            result = run_stage(manifest_path, stage, execute=execute, confirm=confirm)
        reports = _write_stage_report(report_root, stage, target_count, plan["profile"], result)
        row = {"stage": stage, "target_count": target_count, "reports": reports, **result}
        rows.append(row)
        _write_state(
            manifest_data,
            {
                "task_id": task,
                "status": "running" if execute else "planning",
                "current_stage": stage,
                "last_stage_status": result.get("status"),
                "completed_stages": [
                    item["stage"]
                    for item in rows
                    if item.get("status") in {"completed", "ok"}
                ],
                "final_count": final_count,
                "profile": plan["profile"],
                "manifest": str(manifest_path),
                "last_report": reports,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        status = result.get("status")
        if execute and status not in {"completed", "ok", "skipped"}:
            stopped_at = stage
            break
        if not execute and status == "error":
            stopped_at = stage
            break
    summary = {
        "status": "completed" if execute and stopped_at is None else "planned",
        "execute": execute,
        "confirm": confirm,
        "final_count": final_count,
        "profile": plan["profile"],
        "profile_path": plan["profile_path"],
        "final_stage": plan["final_stage"],
        "manifest": str(manifest_path),
        "plan_path": plan.get("plan_path"),
        "report_root": str(report_root),
        "preflight_report": str(preflight_path),
        "preflight_ready": bool(preflight.get("ready_for_one_shot_execution")),
        "blocking_stages": list(preflight.get("blocking_stages") or []),
        "stopped_at": stopped_at,
        "stages_processed": len(rows),
        "rows": rows,
    }
    if execute and stopped_at:
        summary["status"] = "blocked_or_failed"
    _atomic_write(
        report_root / "AUTOPILOT_SUMMARY.json",
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )
    _write_state(
        manifest_data,
        {
            "task_id": task,
            "status": summary["status"],
            "current_stage": stopped_at or "H10",
            "completed_stages": [
                item["stage"] for item in rows if item.get("status") in {"completed", "ok"}
            ],
            "final_count": final_count,
            "profile": plan["profile"],
            "manifest": str(manifest_path),
            "summary": str(report_root / "AUTOPILOT_SUMMARY.json"),
            "preflight": str(preflight_path),
            "blocking_stages": list(preflight.get("blocking_stages") or []),
            "stopped_at": stopped_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return summary


def start_autopilot(
    final_count: int,
    *,
    manifest_path: str | Path | None = None,
    target_id: str | None = None,
    profile: str = "full",
    confirm: bool = False,
) -> dict[str, Any]:
    if not confirm:
        return {"status": "gated", "error": "background production requires confirm=true"}
    profile = load_funnel_profile(profile)["profile_id"]
    manifest_path = resolve_manifest(manifest_path, target_id=target_id)
    manifest = load_manifest(manifest_path)
    current = autopilot_status(manifest_path=manifest_path)
    pid = current.get("pid")
    if current.get("status") in {"queued", "running"} and isinstance(pid, int):
        try:
            os.kill(pid, 0)
        except OSError:
            pass
        else:
            if current.get("profile") != profile:
                return {
                    **current,
                    "status": "gated",
                    "error": (
                        f"active worker profile is {current.get('profile')!r}; "
                        f"requested profile is {profile!r}"
                    ),
                }
            return {**current, "reused_existing_worker": True}
    plan = plan_campaign(
        final_count,
        manifest_path=manifest_path,
        profile=profile,
        write=True,
    )
    manifest = load_manifest(manifest_path)
    report_root = _report_root(manifest, profile)
    preflight = preflight_campaign(manifest_path)
    preflight_path = report_root / "PREFLIGHT_EXECUTION.json"
    _atomic_write(preflight_path, json.dumps(preflight, ensure_ascii=False, indent=2) + "\n")
    if not preflight.get("ready_for_one_shot_execution"):
        blocking_stages = list(preflight.get("blocking_stages") or [])
        state = {
            "status": "gated_preflight",
            "pid": None,
            "final_count": final_count,
            "profile": profile,
            "manifest": str(manifest_path),
            "plan": plan.get("plan_path"),
            "preflight": str(preflight_path),
            "blocking_stages": blocking_stages,
            "current_stage": blocking_stages[0] if blocking_stages else "H0",
            "error": "enabled downstream stages are not ready; background worker was not started",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_state(manifest, state)
        return state
    task_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    report_root.mkdir(parents=True, exist_ok=True)
    log_path = report_root / f"autopilot_{task_id}.log"
    command = [
        sys.executable,
        "-m",
        "masld_agent.funnel.worker",
        "--manifest",
        str(manifest_path),
        "--final-count",
        str(final_count),
        "--profile",
        profile,
        "--task-id",
        task_id,
        "--confirm",
    ]
    queued = {
        "task_id": task_id,
        "status": "queued",
        "pid": None,
        "final_count": final_count,
        "profile": profile,
        "manifest": str(manifest_path),
        "log": str(log_path),
        "command": command,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_state(manifest, queued)
    with log_path.open("a", encoding="utf-8") as stream:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=Path(__file__).resolve().parents[3],
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    state = autopilot_status(manifest_path=manifest_path)
    if state.get("task_id") != task_id:
        state = queued
    state["pid"] = process.pid
    state["log"] = str(log_path)
    state["command"] = command
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_state(manifest, state)
    return state


def autopilot_status(
    *,
    manifest_path: str | Path | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_manifest(manifest_path, target_id=target_id)
    manifest = load_manifest(resolved)
    path = _manifest_state_path(manifest)
    if not path.is_file():
        return {"status": "not_started", "manifest": str(resolved), "state_path": str(path)}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "error", "error": f"invalid autopilot state: {exc}", "state_path": str(path)}
    state["state_path"] = str(path)
    return state
