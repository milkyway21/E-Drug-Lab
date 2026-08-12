"""Portable manifest-driven runner for every canonical project skill.

The runner deliberately accepts argv arrays instead of shell strings. Every
task supplies its own command or ordered steps, so no target-specific workflow
is guessed from a skill name.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "e-drug-lab.skill-manifest/v1"
DEFAULT_TIMEOUT_SECONDS = 172_800
ALLOWED_ENV_PREFIXES = (
    "CUDA_",
    "EDRUG_",
    "HERMES_",
    "MASLD_",
    "MKL_",
    "OMP_",
    "PATH",
    "PYTHONPATH",
    "SCHRODINGER_",
    "SLURM_",
    "TEMP",
    "TMP",
    "TMPDIR",
)

class SkillManifestError(ValueError):
    """Raised when a generic skill manifest cannot be executed safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def load_skill_manifest(path: str | Path, expected_skill: str | None = None) -> dict[str, Any]:
    """Load and validate the generic v1 manifest contract."""
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.is_file():
        raise SkillManifestError(f"manifest not found: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillManifestError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SkillManifestError("manifest root must be an object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SkillManifestError(
            f"schema_version must be {SCHEMA_VERSION!r}; got {data.get('schema_version')!r}"
        )
    required = (
        "task_id",
        "skill",
        "stage",
        "campaign_root",
        "inputs",
        "outputs",
        "resources",
        "validation",
        "reporting",
    )
    missing = [key for key in required if key not in data]
    if missing:
        raise SkillManifestError(f"manifest missing required keys: {', '.join(missing)}")
    for key in ("task_id", "skill", "stage", "campaign_root"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise SkillManifestError(f"manifest.{key} must be non-empty text")
    skill = data["skill"].strip()
    if expected_skill and skill != expected_skill:
        raise SkillManifestError(
            f"manifest skill {skill!r} does not match --skill {expected_skill!r}"
        )
    for key in ("inputs", "resources", "validation", "reporting"):
        if not isinstance(data[key], dict):
            raise SkillManifestError(f"manifest.{key} must be an object")
    language = str(data["reporting"].get("language") or "zh").lower()
    if language not in {"zh", "en"}:
        raise SkillManifestError("manifest.reporting.language must be 'zh' or 'en'")
    if not isinstance(data["outputs"], list) or not data["outputs"]:
        raise SkillManifestError("manifest.outputs must be a non-empty array")
    if "command" in data and data["command"] is not None and not _is_argv(data["command"]):
        raise SkillManifestError("manifest.command must be a non-empty argv array")
    if data.get("command") is not None and "steps" in data:
        raise SkillManifestError("manifest must use command or steps, not both")
    if "steps" in data:
        if not isinstance(data["steps"], list) or not data["steps"]:
            raise SkillManifestError("manifest.steps must be a non-empty array")
        for index, step in enumerate(data["steps"], start=1):
            if not isinstance(step, dict) or not _is_argv(step.get("command")):
                raise SkillManifestError(f"manifest.steps[{index}] must contain an argv command")
    root = _resolve(manifest_path.parent, data["campaign_root"])
    normalized = dict(data)
    normalized["_manifest_path"] = str(manifest_path)
    normalized["_campaign_root"] = str(root)
    return normalized


def _is_argv(command: Any) -> bool:
    return isinstance(command, list) and bool(command) and all(
        isinstance(item, str) and item.strip() for item in command
    )


def _substitute(value: str, manifest: dict[str, Any]) -> str:
    language = str((manifest.get("reporting") or {}).get("language") or "zh").lower()
    language = "en" if language.startswith("en") else "zh"
    replacements = {
        "{manifest}": str(manifest["_manifest_path"]),
        "{campaign_root}": manifest["_campaign_root"],
        "{task_id}": str(manifest["task_id"]),
        "{skill}": str(manifest["skill"]),
        "{stage}": str(manifest["stage"]),
        "{language}": language,
    }
    for token, replacement in replacements.items():
        value = value.replace(token, replacement)
    return value


def _policy_check(command: list[str]) -> None:
    if any("\x00" in item for item in command):
        raise SkillManifestError("command contains a NUL byte")
    executable = Path(command[0]).name.lower()
    if executable in {"bash", "sh", "zsh", "python", "python3", "perl", "ruby"} and "-c" in command:
        raise SkillManifestError("inline shell/interpreter -c programs are forbidden; call a file")
    if executable in {"pkill", "killall"}:
        raise SkillManifestError("pattern-wide process termination is forbidden")


def _command_available(command: list[str], cwd: Path) -> bool:
    executable = Path(command[0]).expanduser()
    if executable.is_absolute():
        return executable.is_file() and os.access(executable, os.X_OK)
    if "/" in command[0]:
        return (_resolve(cwd, executable)).is_file()
    return shutil.which(command[0]) is not None


def _environment(manifest: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, str]:
    values = dict(manifest.get("env") or {})
    values.update(extra or {})
    environment = os.environ.copy()
    for key, value in values.items():
        if not isinstance(key, str) or not key.startswith(ALLOWED_ENV_PREFIXES):
            raise SkillManifestError(f"environment key is not allowed: {key!r}")
        environment[key] = str(value)
    return environment


def _units(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_steps = manifest.get("steps")
    if raw_steps is None:
        command = manifest.get("command")
        if command is None:
            raise SkillManifestError(
                "manifest must declare command or steps; the launcher never guesses a target-specific adapter"
            )
        raw_steps = [{"command": command}]
    units: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict) or not _is_argv(raw.get("command")):
            raise SkillManifestError(f"step {index} must contain an argv command")
        command = [_substitute(item, manifest) for item in raw["command"]]
        _policy_check(command)
        cwd = _resolve(Path(manifest["_campaign_root"]), raw.get("cwd") or ".")
        units.append(
            {
                "name": _clean_name(str(raw.get("name") or f"step_{index:02d}")),
                "command": command,
                "cwd": cwd,
                "timeout_seconds": int(
                    raw.get("timeout_seconds")
                    or (manifest.get("resources") or {}).get("timeout_seconds")
                    or DEFAULT_TIMEOUT_SECONDS
                ),
                "env": dict(raw.get("env") or {}),
            }
        )
    return units


def _output_specs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    raw_outputs = list(manifest.get("outputs") or [])
    raw_outputs.extend((manifest.get("validation") or {}).get("required_outputs") or [])
    seen: set[str] = set()
    for raw in raw_outputs:
        if isinstance(raw, str):
            spec = {"path": raw, "required": True}
        elif isinstance(raw, dict):
            spec = dict(raw)
        else:
            raise SkillManifestError("each output must be a path string or object")
        path_value = spec.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise SkillManifestError("each output must define a non-empty path")
        path_value = _substitute(path_value, manifest)
        if path_value in seen:
            continue
        seen.add(path_value)
        spec["path"] = path_value
        spec["required"] = bool(spec.get("required", True))
        specs.append(spec)
    return specs


def _csv_rows(path: Path) -> int | None:
    if path.suffix.lower() != ".csv":
        return None
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return sum(1 for _ in csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error):
        return None


def _inspect_output(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    path = _resolve(root, spec["path"])
    exists = path.exists()
    nonempty = False
    bytes_count = 0
    if path.is_file():
        bytes_count = path.stat().st_size
        nonempty = bytes_count > 0
    elif path.is_dir():
        nonempty = any(path.iterdir())
    row: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "nonempty": nonempty,
        "required": spec["required"],
    }
    if path.is_file():
        row["bytes"] = bytes_count
        rows = _csv_rows(path)
        if rows is not None:
            row["rows"] = rows
        if spec.get("json") is True:
            try:
                json.loads(path.read_text(encoding="utf-8"))
                row["json_valid"] = True
            except (OSError, UnicodeError, json.JSONDecodeError):
                row["json_valid"] = False
                nonempty = False
        if spec.get("min_records") is not None:
            observed = row.get("rows")
            if observed is not None:
                row["min_records_valid"] = observed >= int(spec["min_records"])
                nonempty = nonempty and row["min_records_valid"]
    row["valid"] = nonempty if spec["required"] else True
    return row


def validate_skill_outputs(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate declared outputs without trusting marker text or chat state."""
    evidence = [_inspect_output(Path(manifest["_campaign_root"]), spec) for spec in _output_specs(manifest)]
    missing = [row["path"] for row in evidence if row["required"] and not row["valid"]]
    return {
        "valid": not missing,
        "missing": missing,
        "evidence": evidence[:50],
        "evidence_total": len(evidence),
    }


def _log_root(manifest: dict[str, Any]) -> Path:
    return Path(manifest["_campaign_root"]) / "logs" / "skills" / _clean_name(manifest["skill"])


def _next_attempt(manifest: dict[str, Any]) -> Path:
    root = _log_root(manifest)
    root.mkdir(parents=True, exist_ok=True)
    numbers = []
    for path in root.glob("attempt_*"):
        try:
            numbers.append(int(path.name.split("_", 1)[1]))
        except (IndexError, ValueError):
            continue
    attempt = root / f"attempt_{max(numbers, default=0) + 1:02d}"
    attempt.mkdir()
    return attempt


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def skill_status(manifest_path: str | Path, expected_skill: str | None = None) -> dict[str, Any]:
    try:
        manifest = load_skill_manifest(manifest_path, expected_skill)
        validation = validate_skill_outputs(manifest)
        latest = _log_root(manifest) / "latest.json"
        previous = None
        if latest.is_file():
            try:
                previous = json.loads(latest.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                previous = {"status": "invalid_status_record"}
        return {
            "status": "completed" if validation["valid"] else "incomplete",
            "skill": manifest["skill"],
            "stage": manifest["stage"],
            "task_id": manifest["task_id"],
            "manifest": manifest["_manifest_path"],
            "campaign_root": manifest["_campaign_root"],
            "last_run": previous,
            "validation": validation,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def run_skill(
    manifest_path: str | Path,
    *,
    expected_skill: str | None = None,
    execute: bool = False,
    confirm: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    """Preview or execute one manifest-defined skill with resume semantics."""
    try:
        manifest = load_skill_manifest(manifest_path, expected_skill)
        validation = validate_skill_outputs(manifest)
        if resume and validation["valid"]:
            return {
                "status": "completed",
                "skill": manifest["skill"],
                "stage": manifest["stage"],
                "task_id": manifest["task_id"],
                "reused_existing": True,
                "validation": validation,
            }
        units = _units(manifest)
        preview = {
            "steps": [
                {
                    "name": unit["name"],
                    "argv": unit["command"],
                    "cwd": str(unit["cwd"]),
                    "timeout_seconds": unit["timeout_seconds"],
                    "command_available": _command_available(unit["command"], unit["cwd"]),
                }
                for unit in units
            ]
        }
        base = {
            "skill": manifest["skill"],
            "stage": manifest["stage"],
            "task_id": manifest["task_id"],
            "manifest": manifest["_manifest_path"],
            "campaign_root": manifest["_campaign_root"],
            "validation": validation,
            "command_preview": preview,
        }
        if not execute:
            base["status"] = "dry_run"
            base["resume_requested"] = resume
            return base
        if not confirm:
            base["status"] = "gated"
            base["error"] = "skill execution requires --confirm"
            return base
        missing_cwds = [str(unit["cwd"]) for unit in units if not unit["cwd"].is_dir()]
        unavailable = [unit["command"][0] for unit in units if not _command_available(unit["command"], unit["cwd"])]
        if missing_cwds:
            base["status"] = "blocked"
            base["error"] = f"working directory does not exist: {missing_cwds[0]}"
            return base
        if unavailable:
            base["status"] = "blocked"
            base["error"] = f"executable unavailable: {unavailable[0]}"
            return base

        attempt = _next_attempt(manifest)
        started = _utc_now()
        logs: list[str] = []
        returncode = 0
        timed_out = False
        for index, unit in enumerate(units, start=1):
            log_path = attempt / f"{index:02d}_{unit['name']}.log"
            logs.append(str(log_path))
            with log_path.open("w", encoding="utf-8") as stream:
                stream.write("ARGV_JSON=" + json.dumps(unit["command"], ensure_ascii=False) + "\n")
                stream.write(f"CWD={unit['cwd']}\nSTARTED_AT={started}\n")
                stream.flush()
                try:
                    result = subprocess.run(
                        unit["command"],
                        cwd=unit["cwd"],
                        env=_environment(manifest, unit["env"]),
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=unit["timeout_seconds"],
                        check=False,
                    )
                    returncode = result.returncode
                except subprocess.TimeoutExpired:
                    returncode = 124
                    timed_out = True
            if returncode != 0:
                break
        validation = validate_skill_outputs(manifest)
        status = "completed" if returncode == 0 and validation["valid"] else "failed"
        if returncode == 0 and not validation["valid"]:
            status = "submitted_or_incomplete"
        payload = {
            **base,
            "status": status,
            "reused_existing": False,
            "attempt": str(attempt),
            "logs": logs,
            "started_at": started,
            "finished_at": _utc_now(),
            "exit_code": returncode,
            "timed_out": timed_out,
            "validation": validation,
        }
        _write_json(attempt / "result.json", payload)
        _write_json(_log_root(manifest) / "latest.json", payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True, help="canonical skill name")
    parser.add_argument("--manifest", required=True, type=Path)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--dry-run", action="store_true", help="preview the resolved argv (default)")
    actions.add_argument("--status", action="store_true", help="read the last run and output validation")
    actions.add_argument("--validate", action="store_true", help="validate declared outputs")
    actions.add_argument("--resume", action="store_true", help="reuse valid outputs or continue execution")
    parser.add_argument("--execute", action="store_true", help="run commands; still requires --confirm")
    parser.add_argument("--confirm", action="store_true", help="authorize external computation")
    args = parser.parse_args(argv)
    if args.confirm and not args.execute:
        parser.error("--confirm requires --execute")
    if args.status:
        payload = skill_status(args.manifest, args.skill)
    elif args.validate:
        status = skill_status(args.manifest, args.skill)
        payload = {key: status[key] for key in ("status", "skill", "stage", "task_id", "manifest", "campaign_root", "validation") if key in status}
        if payload.get("status") == "completed":
            payload["status"] = "ok"
    else:
        payload = run_skill(
            args.manifest,
            expected_skill=args.skill,
            execute=args.execute,
            confirm=args.confirm,
            resume=args.resume,
        )
    _print(payload)
    return 0 if payload.get("status") in {"ok", "dry_run", "completed", "reused", "submitted_or_incomplete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
