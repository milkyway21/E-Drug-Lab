"""Gated Schrödinger tools via e-drug-lab schrodinger_service."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence

from masld_agent.platform.edrug_bridge import try_import_schrodinger
from masld_agent.platform.gates import GateError, gate_schrodinger_dock
from masld_agent.platform.health import check_schrodinger


def schrodinger_status() -> dict[str, Any]:
    probe = check_schrodinger()
    return {
        "status": "ok" if probe["ok"] else "unavailable",
        "health": probe,
        "catalog_ids_used": probe.get("catalog_ids", []),
        "warnings": [
            "Production docking prefers Schrödinger/e-drug-lab over Vina stub.",
        ],
        "command_preview": None,
        "output_dir": None,
    }


def schrodinger_dock(
    *,
    receptor_pdb: str,
    smiles: Optional[Sequence[str]] = None,
    ligand_sdf: Optional[str] = None,
    precision: str = "SP",
    confirm: bool = False,
    output_dir: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    smiles_list = [s for s in (smiles or []) if s and str(s).strip()]
    n = len(smiles_list)
    if ligand_sdf and Path(ligand_sdf).is_file() and not smiles_list:
        # Count ligands roughly from SDF if RDKit available; else treat as multi
        try:
            from rdkit import Chem

            suppl = Chem.SDMolSupplier(str(ligand_sdf), removeHs=False)
            n = sum(1 for m in suppl if m is not None)
        except Exception:  # noqa: BLE001
            n = max(n, 1)

    try:
        gate = gate_schrodinger_dock(
            receptor_pdb=receptor_pdb,
            n_ligands=n if n > 0 else 0,
            confirm=confirm,
            precision=precision,
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

    out = Path(output_dir) if output_dir else Path("runs") / "platform" / "schrodinger"
    out.mkdir(parents=True, exist_ok=True)
    preview = {
        "receptor_pdb": receptor_pdb,
        "n_smiles": len(smiles_list),
        "ligand_sdf": ligand_sdf,
        "precision": precision,
        "output_dir": str(out),
        "runner_api": "schrodinger_service.run_pipeline_dock",
    }
    if dry_run:
        return {
            "status": "dry_run",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": gate["catalog_ids"],
            "warnings": gate["warnings"],
        }

    sch, err = try_import_schrodinger()
    if sch is None:
        return {
            "status": "error",
            "error": f"schrodinger_service unavailable: {err}",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": gate["catalog_ids"],
            "warnings": gate["warnings"],
        }

    PipelineLigand = getattr(sch, "PipelineLigand")
    ligands = []
    if smiles_list:
        for i, smi in enumerate(smiles_list):
            ligands.append(
                PipelineLigand(molecule_id=f"lig_{i}", smiles=smi, name=f"lig_{i}")
            )
    elif ligand_sdf:
        # Convert SDF → SMILES via RDKit for pipeline
        try:
            from rdkit import Chem

            suppl = Chem.SDMolSupplier(str(ligand_sdf), removeHs=False)
            for i, mol in enumerate(suppl):
                if mol is None:
                    continue
                smi = Chem.MolToSmiles(mol)
                name = mol.GetProp("_Name") if mol.HasProp("_Name") else f"lig_{i}"
                ligands.append(
                    PipelineLigand(molecule_id=f"lig_{i}", smiles=smi, name=name)
                )
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "error": f"Failed to read ligand_sdf: {exc}",
                "command_preview": preview,
                "output_dir": str(out),
                "catalog_ids_used": gate["catalog_ids"],
                "warnings": gate["warnings"],
            }

    if not ligands:
        return {
            "status": "blocked",
            "error": "need at least one valid SMILES or SDF ligand",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": gate["catalog_ids"],
            "warnings": gate["warnings"],
        }

    try:
        result = sch.run_pipeline_dock(
            ligands=ligands,
            receptor_pdb=receptor_pdb,
            output_dir=str(out),
            precision=precision,
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
    return {
        "status": "ok" if result_dict.get("ok", True) else "error",
        "result": result_dict,
        "command_preview": preview,
        "output_dir": result_dict.get("output_dir") or str(out),
        "catalog_ids_used": gate["catalog_ids"] + ["ed.svc.schrodinger"],
        "warnings": gate["warnings"],
    }


def schrodinger_mmgbsa(
    *,
    pose_path: str,
    confirm: bool = False,
    output_dir: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    pose = Path(pose_path)
    if not pose.is_file():
        return {
            "status": "blocked",
            "error": f"pose not found: {pose}",
            "catalog_ids_used": ["sz.mmgbsa"],
            "warnings": [],
            "command_preview": None,
            "output_dir": None,
        }
    out = Path(output_dir) if output_dir else pose.parent / "mmgbsa"
    out.mkdir(parents=True, exist_ok=True)
    csv_path = str(out / f"mmgbsa_{pose.stem}.csv")
    preview = {"pose_maegz": str(pose), "output_csv": csv_path, "output_dir": str(out)}
    if dry_run:
        return {
            "status": "dry_run",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": ["sz.mmgbsa"],
            "warnings": [],
        }
    if not confirm:
        return {
            "status": "blocked",
            "error": "MMGBSA requires confirm=true",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": ["sz.mmgbsa"],
            "warnings": [],
        }
    sch, err = try_import_schrodinger()
    if sch is None:
        return {
            "status": "error",
            "error": f"schrodinger_service unavailable: {err}",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": ["sz.mmgbsa"],
            "warnings": [],
        }
    try:
        result = sch.run_mmgbsa_on_pose(str(pose), output_csv=csv_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "command_preview": preview,
            "output_dir": str(out),
            "catalog_ids_used": ["sz.mmgbsa"],
            "warnings": [],
        }
    result_dict = result if isinstance(result, dict) else {"raw": str(result)}
    return {
        "status": "ok" if result_dict.get("ok", True) else "error",
        "result": result_dict,
        "command_preview": preview,
        "output_dir": str(out),
        "catalog_ids_used": ["sz.mmgbsa"],
        "warnings": [],
    }
