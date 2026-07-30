"""DiffGUI library generation routes."""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.db import get_db, get_sessionmaker
from app.repositories.models import Target
from app.services.diffgui_runner import DiffGuiRunner
from app.services.job_store import job_store
from app.services.rl_round_service import add_artifact, create_round, update_round, write_step_log
from app.core.paths import resolve_repo_path
from app.services.sdf_sync import sync_sdf_library

router = APIRouter(prefix="/api/v1/diffgui", tags=["DiffGUI"])


class GenerateRequest(BaseModel):
    target_id: Optional[str] = None
    protein_path: Optional[str] = None
    round_id: int = Field(default=1, ge=1)
    num_mols: int = Field(default=5, ge=1, le=100000)
    batch_size: int = Field(default=5, ge=1, le=1000)
    require_achiral: bool = True
    pocket_file: Optional[str] = None
    device: Optional[str] = None
    config: Optional[str] = None
    async_run: bool = True


class IngestRequest(BaseModel):
    round_id: int
    sdf_path: Optional[str] = None


def _runner(request: Request) -> DiffGuiRunner:
    return DiffGuiRunner(get_settings().diffgui)


def _resolve_protein(db: Session, body: GenerateRequest) -> str:
    if body.protein_path and Path(body.protein_path).is_file():
        return body.protein_path
    if body.target_id:
        target = db.query(Target).filter(Target.id == body.target_id).first()
        if target and target.structure_path and Path(target.structure_path).is_file():
            return target.structure_path
    raise AppError(message="Protein file not found; provide protein_path or valid target_id", code="DIFFGUI_NO_PROTEIN", status_code=400)


@router.get("/status")
async def diffgui_status(request: Request):
    return _runner(request).status()


@router.post("/generate")
async def diffgui_generate(body: GenerateRequest, request: Request, db: Session = Depends(get_db)):
    runner = _runner(request)
    protein = _resolve_protein(db, body)
    create_round(db, round_id=body.round_id, target_id=body.target_id)

    if not body.async_run:
        result = await asyncio.to_thread(
            runner.run_generate,
            protein_file=protein,
            round_id=body.round_id,
            num_mols=body.num_mols,
            batch_size=body.batch_size,
            require_achiral=body.require_achiral,
            pocket_file=body.pocket_file,
            device=body.device,
            config=body.config,
        )
        if result.get("sdf_path"):
            write_step_log(body.round_id, "generation", "done", sdf_path=result["sdf_path"])
            update_round(db, body.round_id, status="generated", step_log_json=__import__("app.services.rl_round_service", fromlist=["read_step_log"]).read_step_log(body.round_id))
        return result

    job_id = job_store.create("diffgui_generate", params=body.model_dump())

    async def _task():
        job_store.update(job_id, status="running", message="DiffGUI generation in progress")
        db_task = get_sessionmaker()()
        try:
            result = await asyncio.to_thread(
                runner.run_generate,
                protein_file=protein,
                round_id=body.round_id,
                num_mols=body.num_mols,
                batch_size=body.batch_size,
                require_achiral=body.require_achiral,
                pocket_file=body.pocket_file,
                device=body.device,
                config=body.config,
            )
            if result.get("ok"):
                write_step_log(body.round_id, "generation", "done", **{k: v for k, v in result.items() if k in ("sdf_path", "output_dir")})
                if result.get("sdf_path"):
                    add_artifact(db_task, body.round_id, "generation", "sdf", result["sdf_path"])
                update_round(db_task, body.round_id, status="generated")
                job_store.update(job_id, status="completed", progress=1.0, result=result)
            else:
                job_store.update(job_id, status="failed", error=result.get("stderr") or result.get("error"))
        except Exception as exc:
            job_store.update(job_id, status="failed", error=str(exc))
        finally:
            db_task.close()

    asyncio.create_task(_task())
    return {"ok": True, "job_id": job_id, "message": "DiffGUI generation started"}


@router.get("/jobs/{job_id}")
async def diffgui_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise AppError(message="Job not found", code="JOB_NOT_FOUND", status_code=404)
    return job


@router.post("/ingest")
async def diffgui_ingest(body: IngestRequest, request: Request, db: Session = Depends(get_db)):
    runner = _runner(request)
    sdf = body.sdf_path or str(runner.round_output_dir(body.round_id) / f"round_{body.round_id}_all.sdf")
    sdf_path = Path(sdf)
    if not sdf_path.is_file():
        raise AppError(message=f"SDF not found: {sdf}", code="DIFFGUI_SDF_MISSING", status_code=404)

    molecules_dir = (resolve_repo_path("molecules/sdf/diffgui")).resolve()
    molecules_dir.mkdir(parents=True, exist_ok=True)
    dest = molecules_dir / f"diffgui_round_{body.round_id}.sdf"
    shutil.copy2(sdf_path, dest)

    sync_result = await asyncio.to_thread(sync_sdf_library, db, str(molecules_dir.parent))
    add_artifact(db, body.round_id, "ingest", "sdf", str(dest))
    return {"ok": True, "sdf_path": str(dest), "sync": sync_result.to_dict()}
