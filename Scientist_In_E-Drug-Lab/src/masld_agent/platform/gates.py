"""Safety gates for platform compute jobs."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from masld_agent.platform.paths import LARGE_BATCH_THRESHOLD


class GateError(ValueError):
    """Raised when a hard gate blocks a job."""


def require_files(*paths: Optional[str | Path], label: str = "input") -> list[Path]:
    out: list[Path] = []
    missing: list[str] = []
    for p in paths:
        if p is None:
            continue
        path = Path(p)
        if not path.is_file():
            missing.append(str(path))
        else:
            out.append(path.resolve())
    if missing:
        raise GateError(f"{label} missing files: {missing}")
    return out


def require_confirm(confirm: bool, *, reason: str) -> None:
    if not confirm:
        raise GateError(
            f"Refusing large/expensive job without confirm=true ({reason}). "
            "Re-run with --confirm / confirm=true after reviewing inputs."
        )


def gate_diffdynamic_generate(
    *,
    mode: str,
    protein_path: Optional[str],
    ligand_path: Optional[str],
    molecule_path: Optional[str],
    batch_size: int,
    confirm: bool,
) -> dict[str, Any]:
    mode_l = (mode or "denovo_fast").lower()
    warnings: list[str] = []
    catalog_ids = ["dd.inputs", "dd.gpu.policy"]

    if not protein_path or not ligand_path:
        raise GateError("protein_path and ligand_path are required for DiffDynamic generate")
    require_files(protein_path, ligand_path, label="diffdynamic")

    if mode_l in {"scaffold", "scaffold_fast", "dd.mode.scaffold_fast"}:
        catalog_ids.append("dd.mode.scaffold_fast")
        if not molecule_path:
            raise GateError("scaffold mode requires molecule_path (scaffold SDF)")
        require_files(molecule_path, label="scaffold")
    elif mode_l in {"prudent", "dd.mode.prudent"}:
        catalog_ids.append("dd.mode.prudent")
        warnings.append("prudent embeds Vina selection — expect longer runtime")
    else:
        catalog_ids.append("dd.mode.denovo_fast")
        if molecule_path:
            warnings.append(
                "denovo_fast normally omits molecule_path (Murcko from ligand); "
                "you passed molecule_path — double-check intent"
            )

    if batch_size >= LARGE_BATCH_THRESHOLD:
        require_confirm(
            confirm,
            reason=f"batch_size={batch_size} >= {LARGE_BATCH_THRESHOLD}",
        )
        catalog_ids.append("dd.script.batch")

    return {"catalog_ids": catalog_ids, "warnings": warnings, "mode": mode_l}


def gate_schrodinger_dock(
    *,
    receptor_pdb: Optional[str],
    n_ligands: int,
    confirm: bool,
    precision: str = "SP",
) -> dict[str, Any]:
    if not receptor_pdb:
        raise GateError("receptor_pdb required")
    require_files(receptor_pdb, label="schrodinger receptor")
    warnings: list[str] = []
    catalog_ids = ["sz.prepwizard", "sz.ligprep", "sz.glide_sp" if precision.upper() == "SP" else "sz.glide_xp"]
    if n_ligands <= 0:
        raise GateError("need at least one ligand (SMILES or SDF)")
    if n_ligands > 20 or precision.upper() == "XP":
        require_confirm(
            confirm,
            reason=f"n_ligands={n_ligands} precision={precision} (Schrödinger queue)",
        )
    warnings.append("DiffDynamic uses ORIGINAL PDB; PrepWizard mae is for Glide only (sz.prepwizard)")
    return {"catalog_ids": catalog_ids, "warnings": warnings}
