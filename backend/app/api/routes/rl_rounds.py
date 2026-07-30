"""RL round management routes."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.errors import AppError
from app.services.rl_round_service import (
    create_round,
    get_round,
    list_rounds,
    read_step_log,
    serialize_round,
    update_round,
)

router = APIRouter(prefix="/api/v1/rl-rounds", tags=["RL Rounds"])


class CreateRoundRequest(BaseModel):
    round_id: int = Field(ge=1)
    target_id: Optional[str] = None
    config_snapshot: Optional[dict[str, Any]] = None


class AdvanceRoundRequest(BaseModel):
    step: str
    status: str = "done"
    metadata: Optional[dict[str, Any]] = None


@router.get("")
async def list_all_rounds(db: Session = Depends(get_db), limit: int = 50):
    rows = list_rounds(db, limit=limit)
    return {"rounds": [serialize_round(r) for r in rows], "total": len(rows)}


@router.post("")
async def create_new_round(body: CreateRoundRequest, db: Session = Depends(get_db)):
    row = create_round(db, round_id=body.round_id, target_id=body.target_id, config=body.config_snapshot)
    return serialize_round(row)


@router.get("/{round_id}")
async def get_round_detail(round_id: int, db: Session = Depends(get_db)):
    row = get_round(db, round_id)
    if not row:
        raise AppError(message="Round not found", code="ROUND_NOT_FOUND", status_code=404)
    data = serialize_round(row)
    data["step_log"] = read_step_log(round_id)
    return data


@router.post("/{round_id}/advance")
async def advance_round(round_id: int, body: AdvanceRoundRequest, db: Session = Depends(get_db)):
    row = get_round(db, round_id)
    if not row:
        raise AppError(message="Round not found", code="ROUND_NOT_FOUND", status_code=404)
    from app.services.rl_round_service import write_step_log
    write_step_log(round_id, body.step, body.status, **(body.metadata or {}))
    log = read_step_log(round_id)
    update_round(db, round_id, step_log_json=log, status=body.status)
    return {"ok": True, "round_id": round_id, "step_log": log}
