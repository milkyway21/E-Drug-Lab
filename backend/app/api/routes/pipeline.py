"""Modular pipeline orchestration API."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.tool_registry import list_steps, list_tools
from app.db import get_db, get_sessionmaker
from app.schemas.pipeline import CreatePipelineRunRequest, RunStepRequest
from app.services.pipeline_orchestrator import PipelineOrchestrator, get_preset_recipes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pipeline", tags=["Pipeline"])


async def _run_pipeline_background(run_id: str) -> None:
    """后台流水线使用独立 DB session，避免请求结束后 session 失效。"""
    db = get_sessionmaker()()
    try:
        orch = PipelineOrchestrator(db)
        await orch.run_all(run_id)
    except Exception:
        logger.exception("Pipeline run %s failed in background", run_id)
    finally:
        db.close()


@router.get("/tools")
async def get_tools():
    return {"tools": list_tools()}


@router.get("/steps")
async def get_steps():
    return {"steps": list_steps()}


@router.get("/presets")
async def get_presets():
    return {"presets": get_preset_recipes()}


@router.get("/runs")
async def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    orch = PipelineOrchestrator(db)
    runs, total = orch.list_runs(page=page, page_size=page_size)
    return {
        "runs": [r.model_dump() for r in runs],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        },
    }


@router.post("/runs")
async def create_run(body: CreatePipelineRunRequest, db: Session = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    run = orch.create_run(body)
    if body.execute:
        asyncio.create_task(_run_pipeline_background(run.id))
    return orch.get_status(run.id).model_dump()


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: Session = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    return orch.get_status(run_id).model_dump()


@router.post("/runs/{run_id}/steps/{step_id}/run")
async def run_single_step(
    run_id: str,
    step_id: str,
    body: RunStepRequest | None = None,
    db: Session = Depends(get_db),
):
    orch = PipelineOrchestrator(db)
    step_run = await orch.run_step(run_id, step_id, (body.params if body else None))
    return {
        "id": step_run.id,
        "step_id": step_run.step_id,
        "status": step_run.status,
        "result_json": step_run.result_json,
    }


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    from_step_id: str | None = None,
    db: Session = Depends(get_db),
):
    orch = PipelineOrchestrator(db)
    run = await orch.resume(run_id, from_step_id)
    return orch.get_status(run.id).model_dump()


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str, db: Session = Depends(get_db)):
    orch = PipelineOrchestrator(db)
    run = orch.cancel(run_id)
    return {"id": run.id, "status": run.status}
