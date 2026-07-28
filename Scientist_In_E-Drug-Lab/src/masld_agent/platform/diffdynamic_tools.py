"""Gated DiffDynamic tools via e-drug-lab DiffDynamicRunner."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from masld_agent.platform.edrug_bridge import try_import_diffdynamic_runner
from masld_agent.platform.gates import GateError, gate_diffdynamic_generate
from masld_agent.platform.health import check_diffdynamic
from masld_agent.platform.paths import DEFAULT_GPUS, HSVPOL_TEMPLATES


def diffdynamic_status() -> dict[str, Any]:
    probe = check_diffdynamic()
    runner, err = try_import_diffdynamic_runner()
    payload: dict[str, Any] = {
        "status": "ok" if probe["ok"] else "unavailable",
        "health": probe,
        "catalog_ids_used": probe.get("catalog_ids", []),
        "warnings": [],
        "command_preview": None,
        "output_dir": None,
    }
    if err:
        payload["warnings"].append(f"DiffDynamicRunner import: {err}")
    if runner is not None:
        try:
            payload["runner_status"] = runner.status()
        except Exception as exc:  # noqa: BLE001
            payload["warnings"].append(f"runner.status: {exc}")
    return payload


def diffdynamic_generate(
    *,
    protein_path: str,
    ligand_path: str,
    mode: str = "denovo_fast",
    molecule_path: Optional[str] = None,
    target_name: str = "target",
    pocket: Optional[str] = None,
    batch_size: int = 20,
    sample_only: bool = True,
    confirm: bool = False,
    output_dir: Optional[str] = None,
    gpus: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    try:
        gate = gate_diffdynamic_generate(
            mode=mode,
            protein_path=protein_path,
            ligand_path=ligand_path,
            molecule_path=molecule_path,
            batch_size=batch_size,
            confirm=confirm,
        )
    except GateError as exc:
        return {
            "status": "blocked",
            "error": str(exc),
            "catalog_ids_used": [],
            "warnings": [],
            "command_preview": None,
            "output_dir": None,
        }

    runner, err = try_import_diffdynamic_runner()
    if runner is None:
        return {
            "status": "error",
            "error": f"DiffDynamicRunner unavailable: {err}",
            "catalog_ids_used": gate["catalog_ids"],
            "warnings": gate["warnings"],
            "command_preview": None,
            "output_dir": None,
        }

    mode_l = gate["mode"]
    out = Path(output_dir) if output_dir else Path("runs") / "platform" / "diffdynamic"
    out.mkdir(parents=True, exist_ok=True)
    gpu_spec = gpus or DEFAULT_GPUS

    fast_cfg = HSVPOL_TEMPLATES / "sampling_web_default_fast.yml"
    scaffold_cfg = HSVPOL_TEMPLATES / "sampling_web_default_fast_scaffold20k.yml"

    preview: dict[str, Any] = {
        "mode": mode_l,
        "protein_path": protein_path,
        "ligand_path": ligand_path,
        "molecule_path": molecule_path,
        "target_name": target_name,
        "pocket": pocket,
        "batch_size": batch_size,
        "sample_only": sample_only,
        "gpus": gpu_spec,
        "output_dir": str(out),
        "fast_cfg": str(fast_cfg) if fast_cfg.is_file() else None,
        "scaffold_cfg": str(scaffold_cfg) if scaffold_cfg.is_file() else None,
        "runner_api": "DiffDynamicRunner.run_custom / run_generate",
        "note": (
            "Runner.run_custom uses protein/ligand + rendered sampling config; "
            "hsvpol fast YAML / scaffold molecule_path are documented in catalog "
            "(dd.cfg.fast_*); full CLI may need sample_diffusion.py when extending."
        ),
    }

    if mode_l in {"prudent", "dd.mode.prudent"}:
        preview["runner_api"] = "DiffDynamicRunner.run_prudent(data_id=...)"
        preview["note"] = (
            "Backend run_prudent requires CrossDock data_id, not free protein/ligand. "
            "For pocket-local prudent, use DiffDynamic CLI per dd.mode.prudent."
        )
        return {
            "status": "blocked",
            "error": (
                "prudent via free protein/ligand is not exposed on DiffDynamicRunner; "
                "use catalog dd.mode.prudent / DiffDynamic CLI, or pass data_id via backend."
            ),
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": gate["catalog_ids"],
            "warnings": gate["warnings"],
        }

    if mode_l in {"scaffold", "scaffold_fast", "dd.mode.scaffold_fast"}:
        preview["catalog_hint"] = "dd.mode.scaffold_fast requires --molecule_path on sample CLI"
        if not dry_run and not confirm:
            # scaffold still allowed for small batches; large already gated
            pass

    if dry_run:
        return {
            "status": "dry_run",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": gate["catalog_ids"],
            "warnings": gate["warnings"],
        }

    try:
        # DiffDynamicRunner.run_custom owns output under its protein_root runs/;
        # we still pass batch/gpus/sample_only. molecule_path is recorded for catalog alignment.
        result = runner.run_custom(
            protein_path=protein_path,
            ligand_path=ligand_path,
            batch_size=batch_size,
            sample_only=sample_only,
            gpus=gpu_spec,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": gate["catalog_ids"],
            "warnings": gate["warnings"],
        }

    result_dict = result if isinstance(result, dict) else {"raw": str(result)}
    warnings = list(gate["warnings"])
    if molecule_path:
        warnings.append(
            "molecule_path recorded but DiffDynamicRunner.run_custom does not forward "
            "--molecule_path; for scaffold Fast use sample_diffusion.py (dd.cfg.fast_scaffold)."
        )
    return {
        "status": "ok" if result_dict.get("ok", True) else "error",
        "result": result_dict,
        "command_preview": preview,
        "output_dir": result_dict.get("output_dir") or str(out),
        "catalog_ids_used": gate["catalog_ids"] + ["dd.outputs", "ed.svc.diffdynamic"],
        "warnings": warnings,
    }


def diffdynamic_extract(
    *,
    pt_path: str,
    vina_modes: str = "none",
    output_dir: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    pt = Path(pt_path)
    if not pt.is_file():
        return {
            "status": "blocked",
            "error": f"pt not found: {pt}",
            "catalog_ids_used": ["dd.script.extract"],
            "warnings": [],
            "command_preview": None,
            "output_dir": None,
        }
    out = Path(output_dir) if output_dir else pt.parent / "extract"
    preview = {
        "pt_file": str(pt),
        "vina_modes": vina_modes,
        "output_dir": str(out),
        "runner_api": "DiffDynamicRunner.extract_pt(pt_file=...)",
        "note": (
            "Runner extract uses evaluate reconstruct script; "
            "vina_modes=none maps to catalog dd.script.extract guidance "
            "(prefer extract_pt_to_sdf_excel.py --vina-modes none for no-Vina)."
        ),
    }
    if dry_run:
        return {
            "status": "dry_run",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": ["dd.script.extract", "dd.outputs"],
            "warnings": [],
        }
    runner, err = try_import_diffdynamic_runner()
    if runner is None:
        return {
            "status": "error",
            "error": f"DiffDynamicRunner unavailable: {err}",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": ["dd.script.extract"],
            "warnings": [],
        }
    try:
        result = runner.extract_pt(
            pt_file=str(pt),
            output_dir=str(out),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": ["dd.script.extract"],
            "warnings": [],
        }
    result_dict = result if isinstance(result, dict) else {"raw": str(result)}
    warnings = []
    if vina_modes and vina_modes.lower() != "none":
        warnings.append(
            f"vina_modes={vina_modes} requested; Runner.extract_pt may still invoke Vina — "
            "use DiffDynamic extract_pt_to_sdf_excel.py --vina-modes none for strict no-Vina."
        )
    return {
        "status": "ok" if result_dict.get("ok", True) else "error",
        "result": result_dict,
        "command_preview": preview,
        "output_dir": result_dict.get("output_dir") or str(out),
        "catalog_ids_used": ["dd.script.extract", "dd.outputs"],
        "warnings": warnings,
    }
