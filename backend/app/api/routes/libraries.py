"""
e-drug lab 分子库管理路由
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, status
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories.models import CompoundLibrary
from app.core.errors import MoleculeLibraryError

router = APIRouter(prefix="/api/v1/libraries", tags=["Libraries"])

UPLOAD_DIR = Path("data/libraries")


class LibraryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source: str = Field(...)
    description: Optional[str] = Field(None, max_length=1000)
    filters: Optional[dict] = Field(None)


class LibraryFilterRequest(BaseModel):
    molecular_weight: Optional[dict] = Field(None)
    logp: Optional[dict] = Field(None)
    h_bond_donors: Optional[dict] = Field(None)
    h_bond_acceptors: Optional[dict] = Field(None)
    rotatable_bonds: Optional[dict] = Field(None)
    tpsa: Optional[dict] = Field(None)
    lipinski_violations: Optional[dict] = Field(None)
    qed_min: Optional[float] = Field(None, ge=0, le=1)
    sas_max: Optional[float] = Field(None, ge=0, le=10)


def _serialize_library(lib: CompoundLibrary) -> dict:
    return {
        "id": str(lib.id),
        "name": lib.name,
        "source": lib.source,
        "compound_count": lib.compound_count,
        "file_path": lib.file_path,
        "filters": lib.filters,
        "created_at": lib.created_at.isoformat() if lib.created_at else None,
    }


@router.get("")
async def list_libraries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(CompoundLibrary)
    if source:
        query = query.filter(CompoundLibrary.source == source)
    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    libraries = query.order_by(CompoundLibrary.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "libraries": [_serialize_library(lib) for lib in libraries],
        "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": total_pages},
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_library(body: LibraryCreateRequest, db: Session = Depends(get_db)):
    library = CompoundLibrary(
        name=body.name,
        source=body.source,
        filters=body.filters,
    )
    db.add(library)
    db.commit()
    db.refresh(library)
    return _serialize_library(library)


@router.post("/upload")
async def upload_library(
    file: UploadFile = File(...),
    name: str = Form(...),
    source: str = Form(default="custom"),
    db: Session = Depends(get_db),
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = UPLOAD_DIR / safe_name
    # 流式写入，避免大文件撑爆内存
    with open(file_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    compound_count = None
    if file.filename and file.filename.lower().endswith('.sdf'):
        try:
            from rdkit import Chem
            supplier = Chem.SDMolSupplier(str(file_path))
            compound_count = sum(1 for mol in supplier if mol is not None)
        except Exception:
            pass

    library = CompoundLibrary(
        name=name,
        source=source,
        compound_count=compound_count,
        file_path=str(file_path),
    )
    db.add(library)
    db.commit()
    db.refresh(library)
    return _serialize_library(library)


@router.get("/{library_id}")
async def get_library(library_id: str, db: Session = Depends(get_db)):
    library = db.query(CompoundLibrary).filter(CompoundLibrary.id == library_id).first()
    if not library:
        raise MoleculeLibraryError(reason=f"分子库不存在：{library_id}", library_id=library_id)
    return _serialize_library(library)


@router.post("/{library_id}/filter")
async def filter_library(library_id: str, body: LibraryFilterRequest, db: Session = Depends(get_db)):
    library = db.query(CompoundLibrary).filter(CompoundLibrary.id == library_id).first()
    if not library:
        raise MoleculeLibraryError(reason=f"分子库不存在：{library_id}", library_id=library_id)
    library.filters = body.model_dump(exclude_none=True)
    db.commit()
    return {"library_id": library_id, "status": "completed", "filters_applied": library.filters}


# ── Scaffold extraction ────────────────────────────────────────

class ScaffoldExtractRequest(BaseModel):
    smiles_list: Optional[list[str]] = Field(None, description="SMILES 列表（直接提交）")
    library_id: Optional[str] = Field(None, description="已有化合物库 ID（从库中提取）")
    names: Optional[list[str]] = Field(None, description="分子名列表，与 SMILES 等长")


@router.post("/scaffolds/extract")
async def extract_scaffolds(body: ScaffoldExtractRequest, db: Session = Depends(get_db)):
    """提取 Bemis-Murcko 骨架并返回去重分组结果。"""
    from app.services.scaffold_service import extract_scaffolds as _extract, extract_from_library_sdf

    if body.smiles_list:
        result = _extract(body.smiles_list, body.names)
    elif body.library_id:
        library = db.query(CompoundLibrary).filter(CompoundLibrary.id == body.library_id).first()
        if not library:
            raise MoleculeLibraryError(reason=f"分子库不存在：{body.library_id}", library_id=body.library_id)
        if not library.file_path:
            raise MoleculeLibraryError(
                reason=f"分子库 {body.library_id} 尚未上传文件", library_id=body.library_id
            )
        result = extract_from_library_sdf(library.file_path)
    else:
        raise MoleculeLibraryError(reason="请提供 smiles_list 或 library_id", library_id="")

    return {
        "stats": result["stats"],
        "unique_scaffolds": result["unique_scaffolds"],
        # 不返回全量 molecules，仅返回前 20 唯一骨架，避免 payload 过大
        "molecule_count": len(result["molecules"]),
    }


@router.get("/scaffolds")
async def list_scaffolds(
    library_id: str = Query(..., description="化合物库 ID"),
    min_members: int = Query(default=1, ge=1, description="最少包含分子数"),
    db: Session = Depends(get_db),
):
    """列出指定库的所有唯一骨架（按成员数降序）。"""
    from app.services.scaffold_service import extract_from_library_sdf

    library = db.query(CompoundLibrary).filter(CompoundLibrary.id == library_id).first()
    if not library:
        raise MoleculeLibraryError(reason=f"分子库不存在：{library_id}", library_id=library_id)
    if not library.file_path:
        raise MoleculeLibraryError(
            reason=f"分子库 {library_id} 尚未上传文件", library_id=library_id
        )

    result = extract_from_library_sdf(library.file_path)
    scaffolds = [s for s in result["unique_scaffolds"] if s["member_count"] >= min_members]

    return {
        "library_id": library_id,
        "library_name": library.name,
        "stats": result["stats"],
        "scaffolds": scaffolds,
    }


@router.get("/scaffolds/{scaffold_smiles:path}")
async def get_scaffold_members(
    library_id: str = Query(..., description="化合物库 ID"),
    scaffold_smiles: str = "",
    db: Session = Depends(get_db),
):
    """获取指定骨架下的所有成员分子。"""
    from app.services.scaffold_service import extract_from_library_sdf

    library = db.query(CompoundLibrary).filter(CompoundLibrary.id == library_id).first()
    if not library:
        raise MoleculeLibraryError(reason=f"分子库不存在：{library_id}", library_id=library_id)
    if not library.file_path:
        raise MoleculeLibraryError(
            reason=f"分子库 {library_id} 尚未上传文件", library_id=library_id
        )

    result = extract_from_library_sdf(library.file_path)
    groups = result.get("scaffold_groups", {})

    # scaffold_smiles from path param may be URL-encoded
    from urllib.parse import unquote
    key = unquote(scaffold_smiles or "")
    members = groups.get(key, [])

    return {
        "scaffold_smiles": key,
        "member_count": len(members),
        "members": members,
    }
