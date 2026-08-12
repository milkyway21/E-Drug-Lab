"""Target-profile driven molecule generation contract.

The orchestrator owns validation and artifact naming while a target profile
owns the external generator command.  Commands are argv lists and are always
executed without a shell.
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from .target_profile import TargetProfile


def _replace_placeholders(value: str, replacements: dict[str, str]) -> str:
    result = str(value)
    for name, replacement in replacements.items():
        result = result.replace("{" + name + "}", replacement)
    return result


def _smiles_column(columns: list[Any]) -> Any:
    for column in columns:
        if str(column).strip().lower() == "generated_smiles":
            return column
    for column in columns:
        if "smiles" in str(column).strip().lower():
            return column
    raise ValueError("target generator output must contain a generated_smiles or smiles column")


def run_target_generator(
    profile: TargetProfile,
    *,
    output_dir: Path | str,
    project_root: Path | str,
    pocket_file: Path | str | None,
    num_mols: int,
) -> dict[str, Any]:
    """Run the configured target generator and normalize its CSV output."""
    if not profile.generation_command:
        raise ValueError(
            f"target '{profile.target_id}' has no generation_command; "
            "full generation requires an explicit profile command"
        )
    if num_mols <= 0:
        raise ValueError("num_mols must be positive")

    root = Path(project_root).expanduser().resolve()
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    request_path = out_dir / f"generation_request_{token}.json"
    output_path = out_dir / f"generation_output_{token}.csv"
    num_frag = round(num_mols * 0.6)
    num_denovo = num_mols - num_frag
    request = {
        "target_id": profile.target_id,
        "pocket_file": str(Path(pocket_file).expanduser().resolve()) if pocket_file else None,
        "num_mols": num_mols,
        "num_frag": num_frag,
        "num_denovo": num_denovo,
        "output_csv": str(output_path),
        "generation_modes": {"frag_cond": num_frag, "denovo": num_denovo},
    }
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    replacements = {
        "request_json": str(request_path),
        "output_csv": str(output_path),
        "target_id": profile.target_id,
        "pocket_file": request["pocket_file"] or "",
        "num_mols": str(num_mols),
        "num_frag": str(num_frag),
        "num_denovo": str(num_denovo),
    }
    command = [
        _replace_placeholders(argument, replacements)
        for argument in profile.generation_command
    ]
    env = os.environ.copy()
    env.update(profile.generation_env)
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=profile.generation_timeout_seconds,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"target generator timed out after {profile.generation_timeout_seconds}s"
        ) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"target generator exited with code {completed.returncode}: {detail[-2000:]}"
        )
    if not output_path.is_file():
        raise RuntimeError(
            f"target generator completed without creating output_csv: {output_path}"
        )

    frame = pd.read_csv(output_path)
    if frame.empty:
        raise ValueError("target generator output CSV is empty")
    smiles_column = _smiles_column(list(frame.columns))
    frame = frame.rename(columns={smiles_column: "generated_smiles"})
    frame["generated_smiles"] = frame["generated_smiles"].astype(str).str.strip()
    frame = frame[frame["generated_smiles"].ne("")].reset_index(drop=True)
    if frame.empty:
        raise ValueError("target generator output contains no non-empty SMILES")
    if "generation_id" not in frame.columns:
        frame["generation_id"] = [
            f"GEN_{profile.target_id}_{index:05d}"
            for index in range(len(frame))
        ]
    frame["generation_id"] = frame["generation_id"].astype(str)
    if "molecule_id" not in frame.columns:
        frame["molecule_id"] = frame["generation_id"]
    if "generation_mode" not in frame.columns:
        frame["generation_mode"] = "mixed"
    if "pocket_file" not in frame.columns:
        frame["pocket_file"] = request["pocket_file"]
    return {
        "frame": frame,
        "request_json": str(request_path),
        "raw_output_csv": str(output_path),
        "command": command,
        "num_frag": num_frag,
        "num_denovo": num_denovo,
    }
