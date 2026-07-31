"""Safe, resume-first runner for existing H0-H10 implementations."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from masld_agent.funnel.artifacts import validate_artifacts
from masld_agent.funnel.manifest import (
    STAGE_ORDER,
    ManifestError,
    campaign_root,
    load_manifest,
    normalize_stage,
    resolve_campaign_path,
    stage_config,
)
from masld_agent.platform.paths import DIFFDYNAMIC_CONDA, DIFFDYNAMIC_ROOT, SCHRODINGER_HOME


COMPUTE_STAGES = frozenset({"H1A", "H1B", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9"})
ALLOWED_ENV_PREFIXES = ("CUDA_", "SCHRODINGER_", "MASLD_", "OMP_", "MKL_", "PYTHONPATH")


def _error_payload(error: Exception) -> dict[str, Any]:
    return {"status": "error", "error": f"{type(error).__name__}: {error}"}


def _command_policy_violations(command: list[str], stage: str) -> list[str]:
    executable = Path(command[0]).name.lower()
    violations = []
    if any(not item.strip() for item in command):
        violations.append("empty argv values are forbidden")
    if executable in {"bash", "sh", "zsh", "python", "python3"} and "-c" in command:
        violations.append("inline shell/Python -c programs are forbidden; call a reusable file")
    if executable in {"pkill", "killall"}:
        violations.append("pattern-wide process termination is forbidden")
    if stage == "H3" and "shape_screen_gpu" in executable:
        if "-osd" in command and "-ocsv" in command:
            violations.append("Schrödinger Shape cannot receive -osd and -ocsv together")
    if stage in {"H2", "H5"} and executable == "glide" and "-OVERWRITE" not in command:
        violations.append("non-interactive Glide requires -OVERWRITE")
    if stage == "H4" and "qikprop" in executable:
        if "-inp" in command or any(item.lower().endswith((".smi", ".smiles")) for item in command):
            violations.append("QikProp must receive LigPrep structure input, not direct SMILES/-inp")
    if stage in {"H8", "H9"} and executable == "conda":
        violations.append("Desmond stages use $SCHRODINGER and must not launch through conda")
    return violations


def _safe_command(config: dict[str, Any], stage: str) -> list[str]:
    command = config.get("command") or []
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        raise ManifestError("stage command must be a non-empty argv array, never a shell string")
    if any("\x00" in item for item in command):
        raise ManifestError("stage command contains a NUL byte")
    violations = _command_policy_violations(command, stage)
    if violations:
        raise ManifestError("; ".join(violations))
    return command


def _command_available(command: list[str], cwd: Path) -> bool:
    executable = Path(command[0]).expanduser()
    if executable.is_absolute():
        return executable.is_file() and os.access(executable, os.X_OK)
    if "/" in command[0]:
        return (cwd / executable).is_file()
    return shutil.which(command[0]) is not None


def _clean_environment(config: dict[str, Any]) -> dict[str, str]:
    environment = os.environ.copy()
    additions = config.get("env") or {}
    if not isinstance(additions, dict):
        raise ManifestError("stage env must be an object")
    for key, value in additions.items():
        if not isinstance(key, str) or not key.startswith(ALLOWED_ENV_PREFIXES):
            raise ManifestError(f"stage env key is not allowed: {key!r}")
        environment[key] = str(value)
    return environment


def _stage_units(config: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    steps = config.get("steps")
    if steps is None:
        steps = [config] if config.get("command") else []
    if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
        raise ManifestError("stage steps must be an array of command objects")
    units = []
    for index, step in enumerate(steps, start=1):
        merged = {key: value for key, value in config.items() if key != "steps"}
        merged.update(step)
        environment = dict(config.get("env") or {})
        environment.update(step.get("env") or {})
        merged["env"] = environment
        name = str(step.get("name") or f"step_{index:02d}")
        merged["name"] = "".join(char if char.isalnum() or char in "-_" else "_" for char in name)
        merged["command"] = _safe_command(merged, stage)
        units.append(merged)
    return units


def _next_attempt(root: Path, stage: str) -> Path:
    parent = root / "logs" / "funnel" / stage
    parent.mkdir(parents=True, exist_ok=True)
    numbers = []
    for path in parent.glob("attempt_*"):
        try:
            numbers.append(int(path.name.split("_", 1)[1]))
        except (IndexError, ValueError):
            continue
    attempt = parent / f"attempt_{max(numbers, default=0) + 1:02d}"
    attempt.mkdir()
    return attempt


def validate_stage(manifest_path: str | Path, stage: str) -> dict[str, Any]:
    try:
        manifest = load_manifest(manifest_path)
        validation = validate_artifacts(manifest, stage)
        return {
            "status": "ok" if validation["valid"] else "incomplete",
            "manifest": manifest["_manifest_path"],
            "campaign_root": manifest["_campaign_root"],
            "backend": stage_config(manifest, stage).get("backend"),
            "validation": validation,
        }
    except Exception as exc:  # noqa: BLE001
        return _error_payload(exc)


def _planned_target(manifest: dict[str, Any], stage: str) -> int | None:
    config = stage_config(manifest, stage)
    value = config.get("target_count")
    if value is None:
        value = (manifest.get("pipeline_targets") or {}).get(stage)
    if value is None:
        return None
    return int(value)


def _stage_preflight(manifest: dict[str, Any], stage: str, root: Path) -> dict[str, Any]:
    config = stage_config(manifest, stage)
    validation = validate_artifacts(manifest, stage)
    target_count = _planned_target(manifest, stage)
    enabled = target_count != 0
    configured = bool(config.get("command") or config.get("steps"))
    command_ok: bool | None = None
    command_error: str | None = None
    if configured:
        try:
            units = _stage_units(config, stage)
            command_ok = all(
                _command_available(
                    unit["command"],
                    resolve_campaign_path(manifest, unit.get("cwd") or root),
                )
                for unit in units
            )
        except (ManifestError, OSError, ValueError) as exc:
            command_ok = False
            command_error = str(exc)
    resources = config.get("resources") or {}
    resources_ready = not bool(resources.get("gated_no_free_gpu"))
    blockers = []
    if enabled and not validation["valid"]:
        if stage == "H0":
            blockers.append("invalid_required_inputs")
        elif not configured:
            blockers.append("missing_argv_adapter")
        elif not command_ok:
            blockers.append("adapter_command_unavailable")
        if stage != "H0" and not resources_ready:
            blockers.append("no_allocated_gpu")
    return {
        "target_count": target_count,
        "enabled": enabled,
        "valid": validation["valid"],
        "configured": configured,
        "command_available": command_ok,
        "command_error": command_error,
        "resources_ready": resources_ready,
        "ready": not blockers,
        "blockers": blockers,
        "backend": config.get("backend"),
    }


def preflight_campaign(manifest_path: str | Path) -> dict[str, Any]:
    try:
        manifest = load_manifest(manifest_path)
        root = campaign_root(manifest)
        stages = {}
        for stage in STAGE_ORDER:
            stages[stage] = _stage_preflight(manifest, stage, root)
        environment = {
            "diffdynamic_root": str(DIFFDYNAMIC_ROOT),
            "diffdynamic_root_exists": DIFFDYNAMIC_ROOT.is_dir(),
            "diffdynamic_python": str(DIFFDYNAMIC_CONDA / "bin" / "python"),
            "diffdynamic_python_exists": (DIFFDYNAMIC_CONDA / "bin" / "python").is_file(),
            "schrodinger": str(SCHRODINGER_HOME),
            "schrodinger_exists": SCHRODINGER_HOME.is_dir(),
            "schrodinger_tools": {
                name: (SCHRODINGER_HOME / name).is_file()
                for name in ("glide", "ligprep", "qikprop", "shape_screen_gpu", "prime_mmgbsa", "run")
            },
        }
        h0 = validate_artifacts(manifest, "H0")
        blocking_stages = [stage for stage, row in stages.items() if not row["ready"]]
        return {
            "status": "ok" if h0["valid"] and not blocking_stages else "gated",
            "manifest": manifest["_manifest_path"],
            "campaign_root": str(root),
            "campaign_id": manifest.get("campaign_id"),
            "target_id": manifest.get("target_id"),
            "h0": h0,
            "environment": environment,
            "stages": stages,
            "blocking_stages": blocking_stages,
            "ready_for_one_shot_execution": h0["valid"] and not blocking_stages,
            "warnings": [
                "preflight is read-only",
                "planned counts are not completed counts",
                "all enabled stages must be valid or have an available argv adapter before compute starts",
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return _error_payload(exc)


def run_stage(
    manifest_path: str | Path,
    stage: str,
    *,
    execute: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    try:
        manifest = load_manifest(manifest_path)
        normalized = normalize_stage(stage)
        config = stage_config(manifest, normalized)
        existing = validate_artifacts(manifest, normalized)
        if existing["valid"]:
            return {
                "status": "completed",
                "stage": normalized,
                "backend": config.get("backend"),
                "reused_existing": True,
                "validation": existing,
                "command_preview": config.get("command"),
            }
        if not (config.get("command") or config.get("steps")):
            return {
                "status": "gated",
                "stage": normalized,
                "backend": config.get("backend"),
                "reused_existing": False,
                "error": "stage has no reusable artifact and no configured argv adapter",
                "validation": existing,
                "command_preview": None,
            }
        units = _stage_units(config, normalized)
        previews = []
        for unit in units:
            cwd = resolve_campaign_path(
                manifest, unit.get("cwd") or campaign_root(manifest)
            )
            if not _command_available(unit["command"], cwd):
                raise ManifestError(
                    f"stage executable unavailable from {cwd}: {unit['command'][0]}"
                )
            previews.append(
                {
                    "name": unit["name"],
                    "argv": unit["command"],
                    "cwd": str(cwd),
                    "timeout_seconds": int(unit.get("timeout_seconds") or 3600),
                }
            )
        preview = {"steps": previews}
        if not execute:
            return {
                "status": "dry_run",
                "stage": normalized,
                "backend": config.get("backend"),
                "reused_existing": False,
                "validation": existing,
                "command_preview": preview,
            }
        if normalized in COMPUTE_STAGES and not confirm:
            return {
                "status": "gated",
                "stage": normalized,
                "error": "compute stage requires confirm=true / --confirm",
                "command_preview": preview,
            }
        for unit in units:
            probe = unit.get("probe")
            if not probe:
                continue
            probe_config = {"command": probe}
            probe_command = _safe_command(probe_config, normalized)
            cwd = resolve_campaign_path(
                manifest, unit.get("cwd") or campaign_root(manifest)
            )
            probe_result = subprocess.run(
                probe_command,
                cwd=cwd,
                env=_clean_environment(unit),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
                check=False,
            )
            if probe_result.returncode != 0:
                return {
                    "status": "blocked",
                    "stage": normalized,
                    "error": f"{unit['name']} capability probe failed with exit {probe_result.returncode}",
                    "probe_output": probe_result.stdout[-4000:],
                    "command_preview": preview,
                }
        attempt = _next_attempt(campaign_root(manifest), normalized)
        started = datetime.now(timezone.utc).isoformat()
        logs = []
        returncode = 0
        timed_out = False
        for index, unit in enumerate(units, start=1):
            command = unit["command"]
            cwd = resolve_campaign_path(
                manifest, unit.get("cwd") or campaign_root(manifest)
            )
            log_path = attempt / f"{index:02d}_{unit['name']}.log"
            logs.append(str(log_path))
            with log_path.open("w", encoding="utf-8") as stream:
                stream.write("ARGV_JSON=" + json.dumps(command, ensure_ascii=False) + "\n")
                stream.write(f"CWD={cwd}\nSTARTED_AT={started}\n")
                stream.flush()
                try:
                    result = subprocess.run(
                        command,
                        cwd=cwd,
                        env=_clean_environment(unit),
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=int(unit.get("timeout_seconds") or 3600),
                        check=False,
                    )
                    returncode = result.returncode
                except subprocess.TimeoutExpired:
                    returncode = 124
                    timed_out = True
            if returncode != 0:
                break
        validation = validate_artifacts(manifest, normalized)
        status = "completed" if returncode == 0 and validation["valid"] else "failed"
        if returncode == 0 and not validation["valid"]:
            status = "submitted_or_incomplete"
        payload = {
            "status": status,
            "stage": normalized,
            "backend": config.get("backend"),
            "reused_existing": False,
            "attempt": str(attempt),
            "logs": logs,
            "exit_code": returncode,
            "timed_out": timed_out,
            "validation": validation,
            "command_preview": preview,
        }
        (attempt / "result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return payload
    except Exception as exc:  # noqa: BLE001
        return _error_payload(exc)


def stage_status(manifest_path: str | Path) -> dict[str, Any]:
    try:
        manifest = load_manifest(manifest_path)
        rows = [validate_artifacts(manifest, stage) for stage in STAGE_ORDER]
        valid = [row["stage"] for row in rows if row["valid"]]
        return {
            "status": "ok",
            "manifest": manifest["_manifest_path"],
            "campaign_root": manifest["_campaign_root"],
            "manifest_current_stage": manifest.get("current_stage"),
            "validated_stages": valid,
            "rows": rows,
        }
    except Exception as exc:  # noqa: BLE001
        return _error_payload(exc)
