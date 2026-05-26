"""
e-drug lab SDF 分子库 API 路由
"""
import uuid
import os
from fastapi import APIRouter, Request, Query, Depends, status
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func
from app.repositories.models import SDFMolecule
from app.services.sdf_sync import sync_sdf_library, get_sdf_molecule_count, get_sdf_file_count
from app.core.errors import MoleculeLibraryError, AppError

router = APIRouter(prefix="/api/v1/molecule-db", tags=["Molecule Database"])


async def get_db(request: Request) -> Session:
    db = getattr(request.app.state, "db_session", None)
    if db is None:
        raise AppError(message="数据库未连接", code="DATABASE_NOT_CONNECTED", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return db


class SyncRequest(BaseModel):
    sdf_directory: Optional[str] = Field(None)


@router.get("/molecules")
async def list_molecules(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str = Query(default="molecular_weight"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
    search: Optional[str] = Query(None),
    min_mw: Optional[float] = Query(None),
    max_mw: Optional[float] = Query(None),
    min_logp: Optional[float] = Query(None),
    max_logp: Optional[float] = Query(None),
    min_qed: Optional[float] = Query(None),
    sdf_filename: Optional[str] = Query(None),
):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    db: Session = await get_db(request)
    query = db.query(SDFMolecule)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            SDFMolecule.name.ilike(search_term) | SDFMolecule.smiles.ilike(search_term) |
            SDFMolecule.molecular_formula.ilike(search_term) | SDFMolecule.inchikey.ilike(search_term)
        )
    if min_mw is not None: query = query.filter(SDFMolecule.molecular_weight >= min_mw)
    if max_mw is not None: query = query.filter(SDFMolecule.molecular_weight <= max_mw)
    if min_logp is not None: query = query.filter(SDFMolecule.logp >= min_logp)
    if max_logp is not None: query = query.filter(SDFMolecule.logp <= max_logp)
    if min_qed is not None: query = query.filter(SDFMolecule.qed >= min_qed)
    if sdf_filename: query = query.filter(SDFMolecule.sdf_filename.ilike(f"%{sdf_filename}%"))
    allowed_sort = {
        "molecular_weight": SDFMolecule.molecular_weight, "logp": SDFMolecule.logp,
        "qed": SDFMolecule.qed, "num_heavy_atoms": SDFMolecule.num_heavy_atoms,
        "num_rotatable_bonds": SDFMolecule.num_rotatable_bonds, "tpsa": SDFMolecule.tpsa,
        "created_at": SDFMolecule.created_at, "name": SDFMolecule.name, "molecular_formula": SDFMolecule.molecular_formula,
        "num_h_bond_donors": SDFMolecule.num_h_bond_donors,
    }
    sort_col = allowed_sort.get(sort_by, SDFMolecule.molecular_weight)
    query = query.order_by(desc(sort_col) if sort_order == "desc" else asc(sort_col))
    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    molecules = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "molecules": [{
            "id": str(m.id), "name": m.name, "smiles": m.smiles, "inchi": m.inchi, "inchikey": m.inchikey,
            "molecular_formula": m.molecular_formula, "molecular_weight": m.molecular_weight,
            "num_atoms": m.num_atoms, "num_heavy_atoms": m.num_heavy_atoms,
            "num_rotatable_bonds": m.num_rotatable_bonds, "num_h_bond_donors": m.num_h_bond_donors,
            "num_h_bond_acceptors": m.num_h_bond_acceptors, "logp": m.logp, "tpsa": m.tpsa, "qed": m.qed,
            "sdf_filename": m.sdf_filename, "sdf_file_path": m.sdf_file_path, "sdf_file_hash": m.sdf_file_hash,
            "file_size_bytes": m.file_size_bytes, "conformer_index": m.conformer_index,
            "total_conformers": m.total_conformers, "sdf_properties": m.sdf_properties,
            "tags": m.tags or [], "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in molecules],
        "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": total_pages},
        "request_id": request_id,
    }


@router.get("/molecules/{molecule_id}")
async def get_molecule(molecule_id: str, request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    db: Session = await get_db(request)
    mol = db.query(SDFMolecule).filter(SDFMolecule.id == molecule_id).first()
    if not mol:
        raise MoleculeLibraryError(reason=f"分子不存在：{molecule_id}", library_id=molecule_id)
    return {
        "id": str(mol.id), "name": mol.name, "smiles": mol.smiles, "inchi": mol.inchi, "inchikey": mol.inchikey,
        "molecular_formula": mol.molecular_formula, "molecular_weight": mol.molecular_weight,
        "num_atoms": mol.num_atoms, "num_heavy_atoms": mol.num_heavy_atoms,
        "num_rotatable_bonds": mol.num_rotatable_bonds, "num_h_bond_donors": mol.num_h_bond_donors,
        "num_h_bond_acceptors": mol.num_h_bond_acceptors, "logp": mol.logp, "tpsa": mol.tpsa, "qed": mol.qed,
        "sdf_filename": mol.sdf_filename, "sdf_file_path": mol.sdf_file_path, "sdf_file_hash": mol.sdf_file_hash,
        "file_size_bytes": mol.file_size_bytes, "conformer_index": mol.conformer_index,
        "total_conformers": mol.total_conformers, "sdf_properties": mol.sdf_properties,
        "tags": mol.tags or [], "created_at": mol.created_at.isoformat() if mol.created_at else None,
        "request_id": request_id,
    }


@router.post("/sync")
async def trigger_sync(body: SyncRequest, request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    db: Session = await get_db(request)
    settings = getattr(request.app.state, "settings", None)
    if body.sdf_directory:
        sdf_dir = os.path.abspath(body.sdf_directory)
    elif settings and hasattr(settings, 'sdf_directory'):
        sdf_dir = os.path.abspath(settings.sdf_directory)
    else:
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent.parent
        sdf_dir = os.path.abspath(os.path.join(project_root, "molecules", "sdf"))
    if not os.path.isdir(sdf_dir):
        raise MoleculeLibraryError(reason=f"SDF 目录不存在：{sdf_dir}")
    sync_result = sync_sdf_library(db, sdf_dir)
    return {"status": "completed", "sdf_directory": sdf_dir, "sync_result": sync_result.to_dict(), "request_id": request_id}


@router.get("/sync/status")
async def sync_status(request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    db: Session = await get_db(request)
    total_molecules = get_sdf_molecule_count(db)
    total_files = get_sdf_file_count(db)
    file_stats = db.query(
        SDFMolecule.sdf_filename, SDFMolecule.sdf_file_path,
        func.count(SDFMolecule.id).label("conformer_count"),
        func.max(SDFMolecule.total_conformers).label("total_conformers"),
    ).group_by(SDFMolecule.sdf_filename, SDFMolecule.sdf_file_path).all()
    return {
        "total_molecules": total_molecules, "total_sdf_files": total_files,
        "sdf_files": [{"filename": r.sdf_filename, "file_path": r.sdf_file_path,
                        "conformers_in_db": r.conformer_count, "total_conformers_in_file": r.total_conformers}
                      for r in file_stats],
        "request_id": request_id,
    }


@router.get("/stats")
async def library_statistics(request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    db: Session = await get_db(request)
    stats = db.query(
        func.count(SDFMolecule.id).label("total"),
        func.avg(SDFMolecule.molecular_weight).label("avg_mw"),
        func.min(SDFMolecule.molecular_weight).label("min_mw"),
        func.max(SDFMolecule.molecular_weight).label("max_mw"),
        func.avg(SDFMolecule.logp).label("avg_logp"),
        func.avg(SDFMolecule.qed).label("avg_qed"),
        func.avg(SDFMolecule.tpsa).label("avg_tpsa"),
        func.avg(SDFMolecule.num_rotatable_bonds).label("avg_rotatable_bonds"),
    ).first()
    return {
        "total_molecules": stats.total, "total_sdf_files": get_sdf_file_count(db),
        "statistics": {
            "molecular_weight": {"avg": round(stats.avg_mw,2) if stats.avg_mw else None,
                                 "min": round(stats.min_mw,2) if stats.min_mw else None,
                                 "max": round(stats.max_mw,2) if stats.max_mw else None},
            "logp_avg": round(stats.avg_logp, 2) if stats.avg_logp else None,
            "qed_avg": round(stats.avg_qed, 4) if stats.avg_qed else None,
            "tpsa_avg": round(stats.avg_tpsa, 2) if stats.avg_tpsa else None,
            "rotatable_bonds_avg": round(stats.avg_rotatable_bonds, 2) if stats.avg_rotatable_bonds else None,
        },
        "request_id": request_id,
    }


@router.delete("/molecules/{molecule_id}")
async def delete_molecule(molecule_id: str, request: Request):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    db: Session = await get_db(request)
    mol = db.query(SDFMolecule).filter(SDFMolecule.id == molecule_id).first()
    if not mol:
        raise MoleculeLibraryError(reason=f"分子不存在：{molecule_id}")
    db.delete(mol)
    db.commit()
    return {"status": "deleted", "molecule_id": molecule_id, "message": "分子记录已删除（SDF 源文件未受影响）", "request_id": request_id}
