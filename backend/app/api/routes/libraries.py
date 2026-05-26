"""
e-drug lab 分子库管理路由
"""
import uuid
from fastapi import APIRouter, Request, Query, UploadFile, File, Form, status
from pydantic import BaseModel, Field
from typing import Optional
from app.core.errors import MoleculeLibraryError

router = APIRouter(prefix="/api/v1/libraries", tags=["Libraries"])


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


@router.get("")
async def list_libraries(request: Request, page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), source: Optional[str] = Query(None)):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return {"libraries": [], "pagination": {"page": page, "page_size": page_size, "total": 0, "total_pages": 0}, "request_id": request_id}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_library(body: LibraryCreateRequest, request: Request):
    return {"id": str(uuid.uuid4()), "name": body.name, "source": body.source, "status": "created", "request_id": getattr(request.state, "request_id", str(uuid.uuid4()))}


@router.post("/upload")
async def upload_library(request: Request, file: UploadFile = File(...), name: str = Form(...), source: str = Form(default="custom")):
    return {"id": str(uuid.uuid4()), "name": name, "filename": file.filename, "status": "uploaded", "request_id": getattr(request.state, "request_id", str(uuid.uuid4()))}


@router.get("/{library_id}")
async def get_library(library_id: str, request: Request):
    return {"id": library_id, "request_id": getattr(request.state, "request_id", str(uuid.uuid4()))}


@router.post("/{library_id}/filter")
async def filter_library(library_id: str, body: LibraryFilterRequest, request: Request):
    return {"library_id": library_id, "status": "completed", "request_id": getattr(request.state, "request_id", str(uuid.uuid4()))}
