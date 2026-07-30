"""任务管理路由 — backed by JobStore + PipelineRun."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories.models import PipelineRun
from app.services.job_store import job_store
from app.services.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


@router.get("")
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    jobs, total = job_store.list_all(pipeline_run_id=run_id, page=page, page_size=page_size)

    pipeline_tasks = []
    if not run_id:
        runs = db.query(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(page_size).all()
        pipeline_tasks = [
            {
                "id": r.id,
                "type": "pipeline_run",
                "status": r.status,
                "progress": 1.0 if r.status == "completed" else 0.5 if r.status == "running" else 0.0,
                "pipeline_run_id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]

    tasks = jobs + pipeline_tasks
    return {
        "tasks": tasks[:page_size],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total + len(pipeline_tasks),
            "total_pages": max(1, (total + len(pipeline_tasks) + page_size - 1) // page_size),
        },
    }


@router.get("/{task_id}")
async def get_task(task_id: str, db: Session = Depends(get_db)):
    job = job_store.get(task_id)
    if job:
        return job

    try:
        orch = PipelineOrchestrator(db)
        status = orch.get_status(task_id)
        return status.model_dump()
    except ValueError:
        return {"id": task_id, "status": "not_found"}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, db: Session = Depends(get_db)):
    job = job_store.get(task_id)
    if job:
        job_store.update(task_id, status="cancelled")
        return {"task_id": task_id, "status": "cancelled"}

    orch = PipelineOrchestrator(db)
    run = orch.cancel(task_id)
    return {"task_id": task_id, "status": run.status}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str, db: Session = Depends(get_db)):
    import asyncio

    orch = PipelineOrchestrator(db)
    run = await orch.resume(task_id)
    return {"task_id": task_id, "run_id": run.id, "status": run.status}
