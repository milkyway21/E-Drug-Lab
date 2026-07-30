"""Pipeline orchestration service."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.tool_registry import list_steps, list_tools
from app.repositories.models import PipelineRun, PipelineStepRun, generate_uuid
from app.schemas.pipeline import (
    CreatePipelineRunRequest,
    PipelineContextDTO,
    PipelineRecipe,
    PipelineRunDTO,
    PipelineStepRunDTO,
)
from app.services.job_store import job_store
from app.services.tool_adapters import ToolAdapterError, execute_tool

logger = logging.getLogger(__name__)


def _step_run_to_dto(step: PipelineStepRun) -> PipelineStepRunDTO:
    return PipelineStepRunDTO(
        id=step.id,
        step_id=step.step_id,
        tool_ids=step.tool_ids or [],
        status=step.status,
        progress=step.progress or 0.0,
        params_json=step.params_json or {},
        result_json=step.result_json,
        error_message=step.error_message,
        started_at=step.started_at,
        completed_at=step.completed_at,
    )


def _run_to_dto(run: PipelineRun) -> PipelineRunDTO:
    return PipelineRunDTO(
        id=run.id,
        status=run.status,
        recipe_json=run.recipe_json or {},
        context_json=run.context_json or {},
        current_step_id=run.current_step_id,
        error_message=run.error_message,
        step_runs=[_step_run_to_dto(s) for s in (run.step_runs or [])],
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


class PipelineOrchestrator:
    def __init__(self, db: Session):
        self.db = db

    def create_run(self, request: CreatePipelineRunRequest) -> PipelineRun:
        ctx = request.context.model_dump()
        target = ctx.get("target") or {}
        run = PipelineRun(
            id=generate_uuid(),
            target_id=target.get("id"),
            recipe_json=request.recipe.model_dump(),
            context_json=ctx,
            status="pending",
        )
        self.db.add(run)

        for step_cfg in request.recipe.steps:
            if not step_cfg.enabled:
                continue
            step_run = PipelineStepRun(
                id=generate_uuid(),
                pipeline_run_id=run.id,
                step_id=step_cfg.step_id,
                tool_ids=step_cfg.tool_ids,
                params_json=step_cfg.params,
                status="pending",
            )
            self.db.add(step_run)

        self.db.commit()
        self.db.refresh(run)
        return run

    async def run_all(self, run_id: str) -> PipelineRun:
        run = self.db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            raise ValueError(f"Pipeline run not found: {run_id}")

        run.status = "running"
        run.started_at = datetime.utcnow()
        self.db.commit()

        job_id = job_store.create("pipeline_run", params={"run_id": run_id}, pipeline_run_id=run_id)

        try:
            recipe = PipelineRecipe.model_validate(run.recipe_json)
            context = dict(run.context_json or {})

            for step_cfg in recipe.steps:
                if not step_cfg.enabled:
                    continue

                run.current_step_id = step_cfg.step_id
                self.db.commit()

                step_run = (
                    self.db.query(PipelineStepRun)
                    .filter(
                        PipelineStepRun.pipeline_run_id == run_id,
                        PipelineStepRun.step_id == step_cfg.step_id,
                    )
                    .first()
                )
                if not step_run:
                    continue

                step_run.status = "running"
                step_run.started_at = datetime.utcnow()
                self.db.commit()

                try:
                    results = []
                    for tool_id in step_cfg.tool_ids:
                        result = await execute_tool(tool_id, context, step_cfg.params)
                        results.append(result)

                    step_run.result_json = {"tools": results}
                    step_run.status = "completed"
                    step_run.progress = 1.0
                    step_run.completed_at = datetime.utcnow()
                    run.context_json = context
                except ToolAdapterError as exc:
                    step_run.status = "failed"
                    step_run.error_message = str(exc)
                    step_run.completed_at = datetime.utcnow()
                    run.status = "failed"
                    run.error_message = str(exc)
                    self.db.commit()
                    job_store.update(job_id, status="failed", error=str(exc))
                    return run
                except Exception as exc:
                    logger.exception("Step %s failed", step_cfg.step_id)
                    step_run.status = "failed"
                    step_run.error_message = str(exc)
                    step_run.completed_at = datetime.utcnow()
                    run.status = "failed"
                    run.error_message = str(exc)
                    self.db.commit()
                    job_store.update(job_id, status="failed", error=str(exc))
                    return run

                self.db.commit()

            if run.status != "failed":
                run.status = "completed"
                run.completed_at = datetime.utcnow()
                job_store.update(job_id, status="completed", progress=1.0)

            self.db.commit()
            self.db.refresh(run)
            return run
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.utcnow()
            self.db.commit()
            job_store.update(job_id, status="failed", error=str(exc))
            raise

    async def run_step(self, run_id: str, step_id: str, params: Optional[dict] = None) -> PipelineStepRun:
        run = self.db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            raise ValueError(f"Pipeline run not found: {run_id}")

        step_run = (
            self.db.query(PipelineStepRun)
            .filter(PipelineStepRun.pipeline_run_id == run_id, PipelineStepRun.step_id == step_id)
            .first()
        )
        if not step_run:
            raise ValueError(f"Step run not found: {step_id}")

        context = dict(run.context_json or {})
        step_run.status = "running"
        step_run.started_at = datetime.utcnow()
        self.db.commit()

        results = []
        for tool_id in step_run.tool_ids or []:
            result = await execute_tool(tool_id, context, {**(step_run.params_json or {}), **(params or {})})
            results.append(result)

        step_run.result_json = {"tools": results}
        step_run.status = "completed"
        step_run.progress = 1.0
        step_run.completed_at = datetime.utcnow()
        run.context_json = context
        self.db.commit()
        self.db.refresh(step_run)
        return step_run

    def get_status(self, run_id: str) -> PipelineRunDTO:
        run = self.db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            raise ValueError(f"Pipeline run not found: {run_id}")
        return _run_to_dto(run)

    def list_runs(self, page: int = 1, page_size: int = 20) -> tuple[list[PipelineRunDTO], int]:
        q = self.db.query(PipelineRun).order_by(PipelineRun.created_at.desc())
        total = q.count()
        runs = q.offset((page - 1) * page_size).limit(page_size).all()
        return [_run_to_dto(r) for r in runs], total

    async def resume(self, run_id: str, from_step_id: Optional[str] = None) -> PipelineRun:
        run = self.db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            raise ValueError(f"Pipeline run not found: {run_id}")

        recipe = PipelineRecipe.model_validate(run.recipe_json)
        start = False if from_step_id else True
        run.status = "running"
        self.db.commit()

        for step_cfg in recipe.steps:
            if not step_cfg.enabled:
                continue
            if from_step_id and step_cfg.step_id == from_step_id:
                start = True
            if not start:
                continue

            step_run = (
                self.db.query(PipelineStepRun)
                .filter(
                    PipelineStepRun.pipeline_run_id == run_id,
                    PipelineStepRun.step_id == step_cfg.step_id,
                )
                .first()
            )
            if step_run and step_run.status == "completed":
                continue

            await self.run_step(run_id, step_cfg.step_id)

        run = self.db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if run:
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            self.db.commit()
        return run

    def cancel(self, run_id: str) -> PipelineRun:
        run = self.db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            raise ValueError(f"Pipeline run not found: {run_id}")
        run.status = "cancelled"
        run.completed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(run)
        return run


def get_preset_recipes() -> list[dict]:
    presets = [
        {
            "id": "full-7-step",
            "name": "Full 7-Step Pipeline",
            "description": "Default end-to-end virtual screening workflow.",
            "steps": [
                {"step_id": "target_prep", "enabled": True, "tool_ids": ["pdb-fetch"]},
                {"step_id": "library_build", "enabled": True, "tool_ids": ["diffgui"]},
                {"step_id": "virtual_screen", "enabled": True, "tool_ids": ["drugclip"]},
                {"step_id": "admet", "enabled": True, "tool_ids": ["rdkit-descriptors", "admet-ai"]},
                {"step_id": "affinity", "enabled": True, "tool_ids": ["vina-dock"]},
                {"step_id": "ranking", "enabled": True, "tool_ids": ["orthogonal-rank"]},
                {"step_id": "rl_train", "enabled": True, "tool_ids": ["glare-train"]},
                {"step_id": "vav1_rl", "enabled": False, "tool_ids": []},
            ],
        },
        {
            "id": "quick-screen",
            "name": "Quick Screen",
            "description": "Target → screen → rank.",
            "steps": [
                {"step_id": "target_prep", "enabled": True, "tool_ids": ["pdb-fetch"]},
                {"step_id": "library_build", "enabled": False, "tool_ids": []},
                {"step_id": "virtual_screen", "enabled": True, "tool_ids": ["drugclip"]},
                {"step_id": "admet", "enabled": False, "tool_ids": []},
                {"step_id": "affinity", "enabled": False, "tool_ids": []},
                {"step_id": "ranking", "enabled": True, "tool_ids": ["orthogonal-rank"]},
                {"step_id": "rl_train", "enabled": False, "tool_ids": []},
                {"step_id": "vav1_rl", "enabled": False, "tool_ids": []},
            ],
        },
        {
            "id": "admet-dock-rank",
            "name": "ADMET + Dock + Rank",
            "description": "Filter existing library molecules, dock, and rank.",
            "steps": [
                {"step_id": "target_prep", "enabled": True, "tool_ids": ["pdb-fetch"]},
                {"step_id": "library_build", "enabled": True, "tool_ids": ["sdf-upload"]},
                {"step_id": "virtual_screen", "enabled": False, "tool_ids": []},
                {"step_id": "admet", "enabled": True, "tool_ids": ["rdkit-descriptors", "admet-ai"]},
                {"step_id": "affinity", "enabled": True, "tool_ids": ["vina-dock"]},
                {"step_id": "ranking", "enabled": True, "tool_ids": ["orthogonal-rank"]},
                {"step_id": "rl_train", "enabled": False, "tool_ids": []},
                {"step_id": "vav1_rl", "enabled": False, "tool_ids": []},
            ],
        },
        {
            "id": "vav1-11-step",
            "name": "VAV1 11-Step RL",
            "description": "VAV1 molecular glue RL closed loop.",
            "steps": [
                {"step_id": "target_prep", "enabled": True, "tool_ids": ["pdb-fetch"]},
                {"step_id": "vav1_rl", "enabled": True, "tool_ids": ["vav1-pipeline"]},
            ],
        },
    ]
    return presets
