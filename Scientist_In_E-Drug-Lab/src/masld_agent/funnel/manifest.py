"""Load backward-compatible funnel campaign manifests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STAGE_ORDER = ("H0", "H1A", "H1B", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10")
STAGE_ALIASES = {
    "H1": "H1B",
    "H1a": "H1A",
    "H1b": "H1B",
    "H1A": "H1A",
    "H1B": "H1B",
}


class ManifestError(ValueError):
    """Raised when a campaign manifest cannot safely drive a stage."""


def normalize_stage(stage: str) -> str:
    value = (stage or "").strip()
    normalized = STAGE_ALIASES.get(value, value.upper())
    if normalized not in STAGE_ORDER:
        raise ManifestError(f"unknown funnel stage: {stage!r}; expected one of {STAGE_ORDER}")
    return normalized


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.is_file():
        raise ManifestError(f"manifest not found: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be an object")
    inputs = data.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
        data["inputs"] = inputs
    legacy_inputs = {
        "receptor_pdb": data.get("receptor_pdb"),
        "reference_ligand_sdf": data.get("reference_ligand_sdf") or data.get("ligand_sdf"),
        "prepwizard_mae": data.get("prepwizard_mae"),
        "grid_zip": data.get("grid_zip"),
    }
    for key, value in legacy_inputs.items():
        if value and key not in inputs:
            inputs[key] = value
    campaign_root = Path(data.get("campaign_root") or manifest_path.parents[1]).expanduser()
    if not campaign_root.is_absolute():
        campaign_root = (manifest_path.parent / campaign_root).resolve()
    data["_manifest_path"] = str(manifest_path)
    data["_campaign_root"] = str(campaign_root.resolve())
    data.setdefault("campaign_id", data.get("target_name") or campaign_root.name)
    data.setdefault("target_id", data.get("target_name") or "UNSET")
    return data


def campaign_root(manifest: dict[str, Any]) -> Path:
    return Path(manifest["_campaign_root"])


def resolve_campaign_path(manifest: dict[str, Any], value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = campaign_root(manifest) / path
    return path.resolve()


def stage_config(manifest: dict[str, Any], stage: str) -> dict[str, Any]:
    normalized = normalize_stage(stage)
    stages = manifest.get("stages") or {}
    if not isinstance(stages, dict):
        raise ManifestError("manifest stages must be an object")
    value = stages.get(normalized, stages.get(normalized.lower(), {})) or {}
    if not isinstance(value, dict):
        raise ManifestError(f"stages.{normalized} must be an object")
    return value
