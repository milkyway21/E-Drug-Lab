"""虚拟筛选路由 — backed by PipelineOrchestrator."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.routes.pipeline import _run_pipeline_background
from app.db import get_db
from app.schemas.pipeline import CreatePipelineRunRequest, ScreeningStartRequest
from app.services.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/api/v1/screening", tags=["Screening"])


@router.post("/start")
async def start_screening(body: ScreeningStartRequest, db: Session = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    request = CreatePipelineRunRequest(recipe=body.recipe, context=body.context, execute=False)
    run = orch.create_run(request)
    asyncio.create_task(_run_pipeline_background(run.id))
    return {"task_id": run.id, "run_id": run.id, "status": "queued"}


@router.get("/{task_id}/progress")
async def screening_progress(task_id: str, db: Session = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    status = orch.get_status(task_id)
    completed = sum(1 for s in status.step_runs if s.status == "completed")
    total = len(status.step_runs) or 1
    return {
        "task_id": task_id,
        "run_id": task_id,
        "progress": completed / total,
        "status": status.status,
        "current_step_id": status.current_step_id,
        "error_message": status.error_message,
    }


@router.get("/{task_id}/results")
async def screening_results(
    task_id: str,
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    db: Session = Depends(get_db),
):
    orch = PipelineOrchestrator(db)
    status = orch.get_status(task_id)
    molecules = (status.context_json or {}).get("molecules") or []
    total = len(molecules)
    start = (page - 1) * page_size
    return {
        "run_id": task_id,
        "results": molecules[start : start + page_size],
        "context": status.context_json,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        },
    }


@router.post("/{task_id}/cancel")
async def cancel_screening(task_id: str, db: Session = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    run = orch.cancel(task_id)
    return {"task_id": task_id, "run_id": run.id, "status": run.status}
