"""Artifact discovery and hard validation for funnel stages."""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path
from typing import Any

from masld_agent.funnel.manifest import campaign_root, normalize_stage, resolve_campaign_path, stage_config


DEFAULT_PATTERNS: dict[str, tuple[str, ...]] = {
    "H1A": ("diffdynamic/denovo*/**/result_*.pt",),
    "H1B": ("dedup/unique.csv", "dedup/denovo/unique.csv", "dedup/merged/merged_unique.csv"),
    "H2": ("glide/sp/top*_parents_manifest.csv", "glide/sp/*_sp.csv", "glide/sp/sp_results.csv"),
    "H3": ("expand/exact*_manifest.csv", "expand/expanded_library_manifest.csv"),
    "H4": ("admet/exact*_manifest.csv", "admet/admet_pass_summary.csv", "admet/hepg2_pass.csv"),
    "H5": ("glide/sp_refine_h5/*selection_manifest.csv", "glide/refine/*results.csv"),
    "H6": ("glide/xp/xp_results.csv", "glide/xp/*_results.csv"),
    "H7": ("glide/refine/mmgbsa_results.csv", "**/mmgbsa_results.csv"),
    "H8": ("md/short*/**/attempt_validation.json", "md/short*/**/PL_RMSD.dat"),
    "H9": ("md/long*/**/attempt_validation.json", "md/**/final_200ns/*decision*.csv"),
    "H10": ("curation/final_top10_candidates.csv", "curation/FINAL_TOP10.md"),
}

RESULT_FIELDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "H1B": (("h1b_results", "dedup_csv"),),
    "H2": (("h2_results", "top10_manifest"), ("h2_results", "sp_csv")),
    "H3": (("h3_results", "exact30_manifest"), ("h3_results", "exact30_sdf")),
    "H4": (("h4_results", "exact5_manifest"), ("h4_results", "exact5_sdf")),
    "H8": (("h5_results", "h5_report"),),
}


def _nested(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _nonempty(path: Path) -> bool:
    if path.is_file():
        return path.stat().st_size > 0
    if path.is_dir():
        try:
            next(path.iterdir())
        except StopIteration:
            return False
        return True
    return False


def _csv_rows(path: Path) -> int | None:
    if path.suffix.lower() != ".csv":
        return None
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return sum(1 for _ in csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error):
        return None


def _json_valid(path: Path) -> bool | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return True


def inspect_path(path: Path) -> dict[str, Any]:
    row = {"path": str(path), "exists": path.exists(), "nonempty": _nonempty(path)}
    if path.is_file():
        row["bytes"] = path.stat().st_size
        csv_rows = _csv_rows(path)
        if csv_rows is not None:
            row["rows"] = csv_rows
            row["nonempty"] = row["nonempty"] and csv_rows > 0
        json_valid = _json_valid(path)
        if json_valid is not None:
            row["json_valid"] = json_valid
            row["nonempty"] = row["nonempty"] and json_valid
            if json_valid and path.name == "attempt_validation.json":
                data = json.loads(path.read_text(encoding="utf-8"))
                row["hard_validation"] = bool(data.get("valid"))
                row["nonempty"] = row["nonempty"] and row["hard_validation"]
        if path.name.lower().endswith((".sdf", ".sdfgz", ".sdf.gz")):
            try:
                row["records"] = count_sdf_records(path)
            except OSError:
                row["records"] = None
    return row


def count_sdf_records(path: Path) -> int:
    opener = gzip.open if path.suffix.lower() in {".gz", ".sdfgz"} else open
    with opener(path, "rb") as stream:
        return sum(chunk.count(b"$$$$") for chunk in iter(lambda: stream.read(1024 * 1024), b""))


def _declared_outputs(manifest: dict[str, Any], stage: str) -> list[Path]:
    values = stage_config(manifest, stage).get("outputs") or []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [resolve_campaign_path(manifest, value) for value in values if isinstance(value, str)]


def _manifest_outputs(manifest: dict[str, Any], stage: str) -> list[Path]:
    paths = []
    for keys in RESULT_FIELDS.get(stage, ()):
        value = _nested(manifest, keys)
        if isinstance(value, str) and value:
            paths.append(resolve_campaign_path(manifest, value))
    return paths


def _pattern_outputs(manifest: dict[str, Any], stage: str) -> list[Path]:
    root = campaign_root(manifest)
    matches: list[Path] = []
    for pattern in DEFAULT_PATTERNS.get(stage, ()):
        matches.extend(sorted(root.glob(pattern)))
    return list(dict.fromkeys(matches))


def _validate_h0(manifest: dict[str, Any]) -> dict[str, Any]:
    inputs = manifest.get("inputs") or {}
    required = ("receptor_pdb", "reference_ligand_sdf", "prepwizard_mae", "grid_zip")
    evidence = []
    missing = []
    for key in required:
        value = inputs.get(key) if isinstance(inputs, dict) else None
        if not value:
            missing.append(key)
            continue
        item = inspect_path(resolve_campaign_path(manifest, value))
        item["input"] = key
        evidence.append(item)
        if not item["nonempty"]:
            missing.append(key)
    return {"valid": not missing, "missing": missing, "evidence": evidence}


def _validate_md_from_manifest(manifest: dict[str, Any]) -> dict[str, Any] | None:
    results = manifest.get("h5_results")
    if not isinstance(results, dict):
        return None
    ids = results.get("exact2_molecules") or []
    if not isinstance(ids, list) or not ids:
        return None
    evidence = []
    missing = []
    for molecule_id in ids:
        row = results.get(str(molecule_id)) or {}
        for key in ("prod_cms", "trajectory", "sea_dir"):
            value = row.get(key) if isinstance(row, dict) else None
            if not value:
                missing.append(f"{molecule_id}.{key}")
                continue
            path = resolve_campaign_path(manifest, value)
            if key == "trajectory" and path.name == "clickme.dtr":
                path = path.parent
            item = inspect_path(path)
            item.update({"molecule_id": molecule_id, "kind": key})
            evidence.append(item)
            if not item["nonempty"]:
                missing.append(f"{molecule_id}.{key}")
        if not row.get("normal_exit") or float(row.get("production_time_ps") or 0) <= 0:
            missing.append(f"{molecule_id}.completion_evidence")
    return {"valid": not missing, "missing": missing, "evidence": evidence}


def validate_artifacts(manifest: dict[str, Any], stage: str) -> dict[str, Any]:
    normalized = normalize_stage(stage)
    if normalized == "H0":
        result = _validate_h0(manifest)
    elif normalized == "H8" and (md := _validate_md_from_manifest(manifest)) is not None:
        result = md
    else:
        declared = _declared_outputs(manifest, normalized)
        manifest_paths = _manifest_outputs(manifest, normalized)
        candidates = declared or manifest_paths or _pattern_outputs(manifest, normalized)
        all_evidence = [inspect_path(path) for path in candidates]
        evidence = all_evidence[:25]
        if declared or manifest_paths:
            valid = bool(all_evidence) and all(item["nonempty"] for item in all_evidence)
        elif normalized == "H10":
            valid = len(all_evidence) >= 2 and all(item["nonempty"] for item in all_evidence)
        else:
            valid = any(item["nonempty"] for item in all_evidence)
        config = stage_config(manifest, normalized)
        if config.get("enforce_exact_count"):
            target_count = int(config.get("target_count") or 0)
            observed_counts = [
                int(item[key])
                for item in all_evidence
                for key in ("rows", "records")
                if item.get(key) is not None
            ]
            exact_count_valid = bool(observed_counts) and all(
                count == target_count for count in observed_counts
            )
            valid = valid and exact_count_valid
        else:
            target_count = None
            observed_counts = []
            exact_count_valid = None
        result = {
            "valid": valid,
            "missing": [] if valid else ["validated stage outputs"],
            "evidence": evidence,
            "evidence_total": len(all_evidence),
            "evidence_truncated": len(all_evidence) > len(evidence),
            "target_count": target_count,
            "observed_counts": observed_counts,
            "exact_count_valid": exact_count_valid,
        }
    return {"stage": normalized, **result}
