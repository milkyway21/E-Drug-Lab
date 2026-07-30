"""
e-drug lab 靶点管理路由
"""
import asyncio
import shutil
import uuid
import os
from pathlib import Path
from urllib.request import urlopen

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, status
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from rdkit import Chem

from app.db import get_db
from app.repositories.models import Target
from app.core.errors import TargetNotFoundError
from app.core.paths import safe_upload_filename, validate_pdb_id

router = APIRouter(prefix="/api/v1/targets", tags=["Targets"])

UPLOAD_DIR = Path("data/targets")


class TargetCreateRequest(BaseModel):
    pdb_id: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    fasta_sequence: Optional[str] = Field(None)
    source: str = Field(default="pdb")
    project_id: Optional[str] = Field(None)


class TargetDownloadRequest(BaseModel):
    pdb_id: str


class TargetPredictRequest(BaseModel):
    fasta_sequence: str
    model_type: Optional[str] = Field(default="alphafold3")


def _serialize_target(t: Target) -> dict:
    return {
        "id": str(t.id),
        "project_id": str(t.project_id) if t.project_id else None,
        "name": t.name,
        "pdb_id": t.pdb_id,
        "source": t.source,
        "status": t.status,
        "structure_path": t.structure_path,
        "resolution": t.resolution,
        "chains": t.chains,
        "residues": t.residues,
        "binding_site": t.binding_site,
        "preprocessing_params": t.preprocessing_params,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("")
async def list_targets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Target)
    if source:
        query = query.filter(Target.source == source)
    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    targets = query.order_by(Target.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "targets": [_serialize_target(t) for t in targets],
        "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": total_pages},
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_target(body: TargetCreateRequest, db: Session = Depends(get_db)):
    target = Target(
        name=body.name,
        pdb_id=body.pdb_id,
        source=body.source,
        project_id=body.project_id,
        status="created",
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return _serialize_target(target)


@router.get("/{target_id}")
async def get_target(target_id: str, db: Session = Depends(get_db)):
    target = db.query(Target).filter(Target.id == target_id).first()
    if not target:
        raise TargetNotFoundError(target_id)
    return _serialize_target(target)


def _fetch_url(url: str, timeout: int) -> bytes:
    """同步下载 PDB 文件。"""
    return urlopen(url, timeout=timeout).read()


def _is_local_sample_available(pdb_id: str) -> bool:
    """检查本地是否存在 PDB 样本文件（用于无网络环境）。"""
    sample_dir = Path(__file__).parents[4] / "molecules" / "pdb"
    return (sample_dir / f"{pdb_id}.pdb").exists()


@router.post("/download")
async def download_target(body: TargetDownloadRequest, db: Session = Depends(get_db)):
    """从 RCSB PDB 下载结构文件。"""
    pdb_id = validate_pdb_id(body.pdb_id)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / f"{pdb_id}.pdb"

    # 尝试从网络下载
    for protocol in ("https", "http"):
        url = f"{protocol}://files.rcsb.org/download/{pdb_id}.pdb"
        try:
            data = await asyncio.to_thread(_fetch_url, url, 30)
            file_path.write_bytes(data)
            return {"status": "downloaded", "pdb_id": pdb_id, "file_path": str(file_path)}
        except Exception:
            continue

    # 网络失败，尝试本地样本
    if _is_local_sample_available(pdb_id):
        import shutil
        shutil.copy(Path(__file__).parents[4] / "molecules" / "pdb" / f"{pdb_id}.pdb", file_path)
        return {"status": "downloaded", "pdb_id": pdb_id, "file_path": str(file_path), "source": "local_sample"}

    return {"status": "failed", "pdb_id": pdb_id, "error": "Cannot download PDB file. No network access and no local sample available."}


@router.post("/predict")
async def predict_structure(body: TargetPredictRequest):
    """AlphaFold 结构预测占位（后续接入 Celery 队列）。"""
    return {"status": "queued", "model_type": body.model_type, "message": "结构预测任务已入队（占位接口）"}


@router.post("/{target_id}/preprocess")
async def preprocess_target(target_id: str, db: Session = Depends(get_db)):
    target = db.query(Target).filter(Target.id == target_id).first()
    if not target:
        raise TargetNotFoundError(target_id)

    # 将已下载的 PDB 关联到靶点（download 与 create 分步调用时 structure_path 为空）
    if not target.structure_path and target.pdb_id:
        pdb_path = UPLOAD_DIR / f"{target.pdb_id.lower().strip()}.pdb"
        if pdb_path.is_file():
            target.structure_path = str(pdb_path.resolve())

    target.status = "ready" if target.structure_path else "preprocessing"
    db.commit()
    db.refresh(target)
    return {
        "status": target.status,
        "target_id": target_id,
        "structure_path": target.structure_path,
    }


PROTEIN_DIR = Path("data/proteins")
LIGAND_DIR = Path("data/ligands")


@router.post("/upload-protein")
async def upload_protein(
    file: UploadFile = File(...),
    name: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Upload a protein PDB file. Accepts .pdb, .pdbqt, .cif files."""
    PROTEIN_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = safe_upload_filename(file.filename, "protein.pdb")
    dest = PROTEIN_DIR / safe_name
    # Avoid overwrite by appending suffix
    counter = 1
    while dest.exists():
        stem, ext = os.path.splitext(safe_name)
        dest = PROTEIN_DIR / f"{stem}_{counter}{ext}"
        counter += 1

    content = await file.read()
    dest.write_bytes(content)

    # Create target entry
    target = Target(
        name=name or safe_name,
        pdb_id=safe_name.rsplit(".", 1)[0],
        source="upload",
        status="uploaded",
        structure_path=str(dest.resolve()),
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    return {
        "status": "uploaded",
        "target_id": str(target.id),
        "filename": safe_name,
        "file_path": str(dest.resolve()),
        "size_bytes": len(content),
    }


@router.post("/upload-ligand")
async def upload_ligand(
    file: UploadFile = File(default=None),
    smiles: str = Form(default=""),
    name: str = Form(default=""),
):
    """Upload a ligand (PDB/MOL2/SDF file) or provide SMILES string.
    Returns the validated molecule data for docking reference."""
    LIGAND_DIR.mkdir(parents=True, exist_ok=True)

    if smiles:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"status": "error", "message": f"Invalid SMILES: {smiles}"}
        # Write minimal SDF for the ligand
        safe_name = (name or "ligand").replace(" ", "_") + ".sdf"
        dest = LIGAND_DIR / safe_name
        writer = Chem.SDWriter(str(dest))
        mol.SetProp("_Name", name or "ligand")
        writer.write(mol)
        writer.close()
        return {
            "status": "ok",
            "smiles": smiles,
            "name": name or "ligand",
            "file_path": str(dest.resolve()),
            "molecular_weight": round(Chem.Descriptors.MolWt(mol), 2),
            "logP": round(Chem.Descriptors.MolLogP(mol), 2),
        }

    if file:
        safe_name = safe_upload_filename(file.filename, "ligand.pdb")
        dest = LIGAND_DIR / safe_name
        counter = 1
        while dest.exists():
            stem, ext = os.path.splitext(safe_name)
            dest = LIGAND_DIR / f"{stem}_{counter}{ext}"
            counter += 1
        content = await file.read()
        dest.write_bytes(content)
        # Try to parse as molecule
        mol = None
        for supplier_fn in [Chem.SDMolSupplier, Chem.MolFromPDBFile, Chem.MolFromMol2File]:
            try:
                mol = supplier_fn(str(dest)) if supplier_fn != Chem.MolFromPDBFile else supplier_fn(str(dest))
                if mol and (hasattr(mol, "__len__") and len(mol) > 0):
                    mol = mol[0] if hasattr(mol, "__len__") else mol
                if mol:
                    break
            except Exception:
                continue
        return {
            "status": "ok",
            "filename": safe_name,
            "file_path": str(dest.resolve()),
            "size_bytes": len(content),
            "parsed": mol is not None,
        }

    return {"status": "error", "message": "Provide a SMILES string or upload a ligand file."}
