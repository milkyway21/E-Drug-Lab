"""SMILES-based AutoDock Vina docking preparation and execution."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rdkit import Chem
from rdkit.Chem import AllChem
from sqlalchemy.orm import Session

from app.repositories.models import Target
from app.services.tool_manager import ToolManager
from app.services.vina_service import VinaBox, VinaParams, VinaResult, VinaService

logger = logging.getLogger(__name__)

TARGETS_DIR = Path("data/targets")
PROTEINS_DIR = Path("data/proteins")
DOCKING_WORK_DIR = Path("data/docking")

WATER_RESNAMES = {"HOH", "WAT", "DOD", "H2O"}
SKIP_HETATM = WATER_RESNAMES | {
    "NA", "CL", "K", "MG", "CA", "ZN", "FE", "MN", "SO4", "PO4",
    "GOL", "EDO", "ACT", "PEG", "BME", "DMS", "TRS",
}


def resolve_vina_executable(configured: Optional[str]) -> Optional[str]:
    if configured and os.path.isfile(configured):
        return configured
    found = shutil.which("vina")
    if found:
        return found
    for path in (
        "/home/user/anaconda3/envs/diffgui_new/bin/vina",
        "/home/user/anaconda3/envs/ed_gui/bin/vina",
        "/home/user/anaconda3/envs/diffdynamic/bin/vina",
    ):
        if os.path.isfile(path):
            return path
    return None


def ensure_vina_tool(tool_manager: ToolManager, configured_path: Optional[str]) -> bool:
    """Register or refresh autodock_vina tool entry with auto-discovered path."""
    resolved = resolve_vina_executable(configured_path)
    if not resolved:
        return False
    existing = tool_manager.get_tool("autodock_vina")
    if existing is None:
        from app.services.tool_manager import ToolInfo
        tool_manager.tools["autodock_vina"] = ToolInfo("autodock_vina", resolved)
    else:
        existing.executable_path = resolved
        existing.check()
    return bool(tool_manager.get_tool("autodock_vina") and tool_manager.get_tool("autodock_vina").is_available)


def is_vina_available(tool_manager: ToolManager) -> bool:
    tool = tool_manager.get_tool("autodock_vina")
    return bool(tool and tool.is_available)


def resolve_receptor_pdb(
    target_pdb_id: Optional[str] = None,
    structure_path: Optional[str] = None,
    target_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Path:
    if target_id and db is not None:
        target = db.query(Target).filter(Target.id == target_id).first()
        if target and target.structure_path:
            path = Path(target.structure_path)
            if path.is_file():
                return path.resolve()
        if target and target.pdb_id:
            target_pdb_id = target.pdb_id

    if structure_path:
        path = Path(structure_path)
        if path.is_file():
            return path.resolve()

    if target_pdb_id:
        pdb_id = target_pdb_id.lower().strip()
        for candidate in (
            TARGETS_DIR / f"{pdb_id}.pdb",
            TARGETS_DIR / f"{pdb_id.upper()}.pdb",
            PROTEINS_DIR / f"{pdb_id}.pdb",
        ):
            if candidate.is_file():
                return candidate.resolve()
        for pattern in (f"*{pdb_id}*.pdb", f"*{pdb_id}*.pdbqt", f"*{pdb_id}*.cif"):
            for candidate in PROTEINS_DIR.glob(pattern):
                if candidate.is_file():
                    return candidate.resolve()

    raise FileNotFoundError(
        f"Receptor structure not found (target_id={target_id}, pdb_id={target_pdb_id})"
    )


def estimate_pocket_box(pdb_path: Path) -> VinaBox:
    """Estimate docking box from co-crystallized ligand or protein centroid."""
    ligand_atoms: list[tuple[float, float, float]] = []
    protein_atoms: list[tuple[float, float, float]] = []

    with open(pdb_path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.startswith("HETATM"):
                resname = line[17:20].strip().upper()
                if resname in SKIP_HETATM:
                    continue
                try:
                    ligand_atoms.append((
                        float(line[30:38]),
                        float(line[38:46]),
                        float(line[46:54]),
                    ))
                except ValueError:
                    continue
            elif line.startswith("ATOM"):
                try:
                    protein_atoms.append((
                        float(line[30:38]),
                        float(line[38:46]),
                        float(line[46:54]),
                    ))
                except ValueError:
                    continue

    atoms = ligand_atoms if len(ligand_atoms) >= 3 else protein_atoms
    if not atoms:
        return VinaBox(center_x=0.0, center_y=0.0, center_z=0.0, size_x=20.0, size_y=20.0, size_z=20.0)

    cx = sum(a[0] for a in atoms) / len(atoms)
    cy = sum(a[1] for a in atoms) / len(atoms)
    cz = sum(a[2] for a in atoms) / len(atoms)
    box_size = 15.0 if ligand_atoms else 22.0
    return VinaBox(center_x=cx, center_y=cy, center_z=cz, size_x=box_size, size_y=box_size, size_z=box_size)


def _run_obabel(args: list[str], timeout: int = 60) -> None:
    obabel = shutil.which("obabel")
    if not obabel:
        raise RuntimeError("Open Babel (obabel) not found in PATH")
    proc = subprocess.run([obabel, *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "obabel failed").strip())


def pdb_to_pdbqt(pdb_path: Path, out_path: Path) -> None:
    if pdb_path.suffix.lower() == ".pdbqt":
        shutil.copy2(pdb_path, out_path)
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run_obabel([str(pdb_path), "-O", str(out_path), "-xr"], timeout=120)


def smiles_to_pdbqt(smiles: str, out_path: Path) -> None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")

    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise ValueError("3D conformer embedding failed")

    try:
        AllChem.MMFFOptimizeMolecule(mol)
    except Exception:
        pass

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sdf_path = out_path.with_suffix(".sdf")
    writer = Chem.SDWriter(str(sdf_path))
    writer.write(mol)
    writer.close()
    _run_obabel([str(sdf_path), "-O", str(out_path), "-h"], timeout=60)
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RuntimeError("Ligand PDBQT conversion produced empty file")


@dataclass
class SmilesDockItem:
    molecule_id: str
    smiles: str
    name: str = ""


@dataclass
class SmilesDockOutcome:
    molecule_id: str
    smiles: str
    name: str
    affinity_kcal_mol: Optional[float]
    method: str
    model: Optional[str]
    success: bool
    error: Optional[str] = None
    poses_count: int = 0


async def dock_smiles_molecule(
    tool_manager: ToolManager,
    receptor_pdbqt: str,
    box: VinaBox,
    item: SmilesDockItem,
    work_dir: Path,
    exhaustiveness: int = 4,
    timeout: int = 20,
) -> SmilesDockOutcome:
    job_dir = work_dir / item.molecule_id
    job_dir.mkdir(parents=True, exist_ok=True)
    ligand_pdbqt = job_dir / "ligand.pdbqt"

    try:
        smiles_to_pdbqt(item.smiles, ligand_pdbqt)
    except Exception as exc:
        return SmilesDockOutcome(
            molecule_id=item.molecule_id,
            smiles=item.smiles,
            name=item.name,
            affinity_kcal_mol=None,
            method="failed",
            model=None,
            success=False,
            error=f"ligand prep: {exc}",
        )

    service = VinaService(tool_manager, work_dir=str(work_dir))
    params = VinaParams(
        receptor_path=receptor_pdbqt,
        ligand_path=str(ligand_pdbqt),
        box=box,
        exhaustiveness=exhaustiveness,
        num_modes=5,
        energy_range=3.0,
    )
    result: VinaResult = await service.run_docking(params, job_id=item.molecule_id, timeout=timeout)

    if result.success and result.best_affinity is not None:
        return SmilesDockOutcome(
            molecule_id=item.molecule_id,
            smiles=item.smiles,
            name=item.name,
            affinity_kcal_mol=round(result.best_affinity, 2),
            method="vina",
            model="vina",
            success=True,
            poses_count=len(result.poses),
        )

    return SmilesDockOutcome(
        molecule_id=item.molecule_id,
        smiles=item.smiles,
        name=item.name,
        affinity_kcal_mol=None,
        method="failed",
        model=None,
        success=False,
        error=(result.stderr or "Vina docking failed")[:500],
        poses_count=len(result.poses),
    )


async def dock_smiles_batch(
    tool_manager: ToolManager,
    molecules: list[SmilesDockItem],
    target_pdb_id: Optional[str] = None,
    target_id: Optional[str] = None,
    structure_path: Optional[str] = None,
    db: Optional[Session] = None,
    exhaustiveness: int = 4,
    timeout_per_molecule: int = 20,
    concurrency: int = 2,
) -> tuple[bool, str, list[SmilesDockOutcome]]:
    """
    Batch dock SMILES molecules with real Vina.
    Returns (vina_available, batch_method, results).
    batch_method is 'vina' when Vina ran, 'unavailable' when Vina binary missing.
    """
    if not is_vina_available(tool_manager):
        unavailable = [
            SmilesDockOutcome(
                molecule_id=item.molecule_id,
                smiles=item.smiles,
                name=item.name,
                affinity_kcal_mol=None,
                method="unavailable",
                model=None,
                success=False,
                error="AutoDock Vina is not available",
            )
            for item in molecules
        ]
        return False, "unavailable", unavailable

    receptor_pdb = resolve_receptor_pdb(
        target_pdb_id=target_pdb_id,
        structure_path=structure_path,
        target_id=target_id,
        db=db,
    )
    box = estimate_pocket_box(receptor_pdb)

    batch_id = uuid.uuid4().hex[:8]
    work_dir = DOCKING_WORK_DIR / batch_id
    work_dir.mkdir(parents=True, exist_ok=True)
    receptor_pdbqt = work_dir / "receptor.pdbqt"
    pdb_to_pdbqt(receptor_pdb, receptor_pdbqt)

    semaphore_limit = max(1, min(concurrency, 8))

    async def _dock_one(item: SmilesDockItem) -> SmilesDockOutcome:
        return await dock_smiles_molecule(
            tool_manager,
            str(receptor_pdbqt),
            box,
            item,
            work_dir,
            exhaustiveness=exhaustiveness,
            timeout=timeout_per_molecule,
        )

    if semaphore_limit == 1:
        outcomes = []
        for item in molecules:
            outcomes.append(await _dock_one(item))
    else:
        import asyncio
        semaphore = asyncio.Semaphore(semaphore_limit)

        async def _limited(item: SmilesDockItem) -> SmilesDockOutcome:
            async with semaphore:
                return await _dock_one(item)

        outcomes = await asyncio.gather(*[_limited(item) for item in molecules])

    return True, "vina", list(outcomes)
