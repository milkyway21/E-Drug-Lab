"""分子生成/管理路由"""
import uuid
from fastapi import APIRouter, Request, Query, status

router = APIRouter(prefix="/api/v1/molecules", tags=["Molecules"])


@router.get("")
async def list_molecules(request: Request, page: int = Query(default=1), page_size: int = Query(default=20)):
    return {"molecules": [], "pagination": {"page": page, "page_size": page_size, "total": 0, "total_pages": 0}}


@router.get("/{molecule_id}")
async def get_molecule(molecule_id: str, request: Request):
    return {"id": molecule_id}


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_molecules(request: Request):
    return {"task_id": str(uuid.uuid4()), "status": "queued"}


@router.post("/{molecule_id}/rank")
async def rank_molecule(molecule_id: str, request: Request):
    return {"molecule_id": molecule_id, "comprehensive_score": 0.0}
