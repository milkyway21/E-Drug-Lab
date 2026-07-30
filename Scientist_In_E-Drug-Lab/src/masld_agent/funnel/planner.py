"""Deterministic stage-count planning and local resource allocation."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from masld_agent.config import PKG_ROOT
from masld_agent.funnel.manifest import STAGE_ORDER, campaign_root, load_manifest


PROFILE_DIR = PKG_ROOT / "config" / "funnel_profiles"
PROFILE_IDS = ("test", "full")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_manifest(
    manifest_path: str | Path | None = None,
    *,
    target_id: str | None = None,
) -> Path:
    if manifest_path:
        return Path(manifest_path).expanduser().resolve()
    configured = os.environ.get("EDRUG_FUNNEL_MANIFEST")
    if configured:
        return Path(configured).expanduser().resolve()
    target = (target_id or "HSD17B13").strip()
    session_path = PKG_ROOT / "memory" / "targets" / target / "session.json"
    if session_path.is_file():
        data = json.loads(session_path.read_text(encoding="utf-8"))
        root = data.get("workspace_root")
        if root:
            candidate = Path(root).expanduser() / "inputs" / "manifest.json"
            if candidate.is_file():
                return candidate.resolve()
    raise FileNotFoundError(
        "campaign manifest unresolved; pass manifest, set EDRUG_FUNNEL_MANIFEST, "
        f"or configure memory/targets/{target}/session.json"
    )


def load_funnel_profile(profile: str = "full") -> dict[str, Any]:
    profile_id = (profile or "full").strip().lower()
    if profile_id not in PROFILE_IDS:
        raise ValueError(f"unknown funnel profile: {profile!r}; expected one of {PROFILE_IDS}")
    path = PROFILE_DIR / f"{profile_id}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("profile_id") != profile_id:
        raise ValueError(f"invalid funnel profile: {path}")
    stages = data.get("stages")
    if not isinstance(stages, dict) or set(stages) != set(STAGE_ORDER):
        raise ValueError(f"profile must define exactly {STAGE_ORDER}: {path}")
    data["_path"] = str(path)
    return data


def _profile_target(stage: dict[str, Any], final_count: int) -> int:
    target = stage.get("target") or {}
    mode = target.get("mode")
    value = target.get("value")
    if mode == "fixed":
        result = float(value)
    elif mode == "per_final":
        result = float(value) * final_count
    else:
        raise ValueError(f"invalid target rule: {target!r}")
    if result < 0:
        raise ValueError(f"target cannot be negative: {target!r}")
    rounding = target.get("rounding", "ceil")
    if rounding != "ceil":
        raise ValueError(f"unsupported target rounding: {rounding!r}")
    return math.ceil(result)


def plan_counts(final_count: int, *, profile: str = "full") -> dict[str, Any]:
    if final_count <= 0:
        raise ValueError("final_count must be positive")
    config = load_funnel_profile(profile)
    counts = {
        stage: _profile_target(config["stages"][stage], final_count)
        for stage in STAGE_ORDER
    }
    reference_final = int(config["reference_final_count"])
    for stage in STAGE_ORDER:
        expected = int(config["stages"][stage]["reference_target"])
        actual = _profile_target(config["stages"][stage], reference_final)
        if actual != expected:
            raise ValueError(
                f"profile reference mismatch for {stage}: computed {actual}, configured {expected}"
            )
    return {
        "profile": config["profile_id"],
        "profile_label": config["label"],
        "profile_path": config["_path"],
        "profile_source": config["source"],
        "final_stage": config["final_stage"],
        "final_count": final_count,
        "stage_targets": {stage: counts[stage] for stage in STAGE_ORDER},
        "stage_plan": config["stages"],
        "rules": {
            "default_profile": "full",
            "test_profile_requires_explicit_selection": True,
            "h3_is_library_expansion": True,
            "counts_are_targets_not_completion": True,
            "prudent_analysis_vina_modes": "none",
        },
    }


def _gpu_inventory() -> list[dict[str, Any]]:
    if shutil.which("nvidia-smi") is None:
        return []
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    if result.returncode:
        return []
    rows = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            continue
        try:
            index, name, used, total, utilization = parts
            used_i, total_i, utilization_i = int(used), int(total), int(utilization)
        except ValueError:
            continue
        free = used_i <= max(1024, int(total_i * 0.1)) and utilization_i <= 20
        rows.append(
            {
                "index": int(index),
                "name": name,
                "memory_used_mb": used_i,
                "memory_total_mb": total_i,
                "utilization_pct": utilization_i,
                "available": free,
            }
        )
    return rows


def resource_inventory(campaign: Path) -> dict[str, Any]:
    cpu_total = os.cpu_count() or 1
    memory_kb = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                memory_kb = int(line.split()[1])
                break
    except (OSError, ValueError):
        pass
    disk = shutil.disk_usage(campaign if campaign.exists() else campaign.parent)
    gpus = _gpu_inventory()
    return {
        "captured_at": _utc(),
        "cpu_total": cpu_total,
        "cpu_jobs": max(1, math.floor(cpu_total * 0.75)),
        "memory_available_gb": round(memory_kb / 1024 / 1024, 2),
        "disk_free_gb": round(disk.free / 1024**3, 2),
        "gpus": gpus,
        "available_gpu_ids": [row["index"] for row in gpus if row["available"]],
    }


def allocate_resources(
    inventory: dict[str, Any],
    final_count: int,
    stage_targets: dict[str, int] | None = None,
) -> dict[str, Any]:
    free_gpus = list(inventory.get("available_gpu_ids") or [])
    cpu_jobs = int(inventory.get("cpu_jobs") or 1)
    allocations: dict[str, dict[str, Any]] = {}
    gpu_stages = {"H1A", "H1B", "H3", "H8", "H9"}
    for stage in STAGE_ORDER:
        allocation: dict[str, Any] = {"cpu_jobs": cpu_jobs}
        if stage_targets is not None and stage_targets[stage] == 0:
            allocations[stage] = {"disabled_by_profile": True, "cpu_jobs": 0}
            continue
        if stage in gpu_stages:
            if stage in {"H8", "H9"}:
                allocation["gpu_ids"] = free_gpus[: max(1, min(final_count, len(free_gpus)))]
                allocation["one_job_per_gpu"] = True
            else:
                allocation["gpu_ids"] = free_gpus
            allocation["gated_no_free_gpu"] = not bool(allocation["gpu_ids"])
        allocations[stage] = allocation
    return allocations


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def plan_campaign(
    final_count: int,
    *,
    manifest_path: str | Path | None = None,
    target_id: str | None = None,
    profile: str = "full",
    write: bool = True,
) -> dict[str, Any]:
    resolved = resolve_manifest(manifest_path, target_id=target_id)
    manifest = load_manifest(resolved)
    root = campaign_root(manifest)
    scale = plan_counts(final_count, profile=profile)
    inventory = resource_inventory(root)
    allowed_gpu_ids = (manifest.get("resource_policy") or {}).get("allowed_gpu_ids")
    if allowed_gpu_ids is not None:
        allowed = {int(gpu_id) for gpu_id in allowed_gpu_ids}
        inventory["available_gpu_ids"] = [
            gpu_id for gpu_id in inventory["available_gpu_ids"] if gpu_id in allowed
        ]
        inventory["allowed_gpu_ids"] = sorted(allowed)
    allocations = allocate_resources(inventory, final_count, scale["stage_targets"])
    plan = {
        "status": "planned",
        "generated_at": _utc(),
        "manifest": str(resolved),
        "campaign_root": str(root),
        "campaign_id": manifest.get("campaign_id"),
        "target_id": manifest.get("target_id"),
        **scale,
        "resource_inventory": inventory,
        "resource_allocations": allocations,
        "execution_policy": {
            "reuse_valid_artifacts_first": True,
            "execute_default": False,
            "compute_requires_confirm": True,
            "stop_on_failed_validation": True,
            "report_every_stage": True,
        },
    }
    if write:
        plan_path = resolved.parent / f"funnel_plan_{scale['profile']}.json"
        _atomic_json(plan_path, plan)
        raw_manifest = json.loads(resolved.read_text(encoding="utf-8"))
        raw_manifest["funnel_profile"] = {
            "id": scale["profile"],
            "source": scale["profile_path"],
            "final_stage": scale["final_stage"],
            "final_count": final_count,
        }
        raw_manifest["pipeline_targets"] = scale["stage_targets"]
        raw_manifest["resource_plan"] = {
            "source": str(plan_path),
            "captured_at": inventory["captured_at"],
            "allocations": allocations,
        }
        stages = raw_manifest.setdefault("stages", {})
        for stage, target_count in scale["stage_targets"].items():
            config = stages.setdefault(stage, {})
            profile_stage = scale["stage_plan"][stage]
            config["target_count"] = target_count
            config["skill"] = profile_stage["skill"]
            config["quantity_role"] = profile_stage["quantity_role"]
            if profile_stage.get("backend_policy"):
                config["required_backend_policy"] = profile_stage["backend_policy"]
            if profile_stage.get("protocol"):
                config["protocol"] = profile_stage["protocol"]
            allocation = allocations[stage]
            config["resources"] = allocation
            gpu_ids = allocation.get("gpu_ids") or []
            if gpu_ids:
                environment = config.setdefault("env", {})
                environment.setdefault("CUDA_VISIBLE_DEVICES", ",".join(map(str, gpu_ids)))
                environment.setdefault("SCHRODINGER_CUDA_VISIBLE_DEVICES", ",".join(map(str, gpu_ids)))
        h1b = stages.setdefault("H1B", {})
        if not (h1b.get("command") or h1b.get("steps")):
            h1b.setdefault("backend", "diffdynamic_prudent_then_physchem_no_vina")
            h1b.setdefault("outputs", ["dedup/unique.csv"])
            h1b["steps"] = [
                        {
                            "name": "prudent_generate",
                            "command": [
                                sys.executable,
                                "-m",
                                "masld_agent.cli",
                                "funnel",
                                "prudent-generate",
                                "--manifest",
                                str(resolved),
                                "--execute",
                                "--confirm",
                            ],
                            "timeout_seconds": 172800,
                        },
                        {
                            "name": "physchem_no_vina_and_dedup",
                            "command": [
                                sys.executable,
                                "-m",
                                "masld_agent.cli",
                                "funnel",
                                "prudent-physchem",
                                "--manifest",
                                str(resolved),
                                "--execute",
                                "--confirm",
                            ],
                            "timeout_seconds": 28800,
                        },
                    ]
        _atomic_json(resolved, raw_manifest)
        plan["plan_path"] = str(plan_path)
    return plan
