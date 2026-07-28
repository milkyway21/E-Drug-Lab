"""DiffDynamic 分子生成路由 — 对接 /data/ye/DiffDynamic。"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.core.paths import resolve_repo_path, ensure_safe_path
from app.db import get_db, get_sessionmaker
from app.repositories.models import Target
from app.services.diffdynamic_runner import DiffDynamicRunner
from app.services.job_store import job_store
from app.services.rl_round_service import add_artifact, create_round, update_round, write_step_log
from app.services.sdf_sync import sync_sdf_library

router = APIRouter(prefix="/api/v1/diffdynamic", tags=["DiffDynamic"])


class GenerateRequest(BaseModel):
    mode: Literal["dynamic", "prudent", "custom"] = "dynamic"
    target_id: Optional[str] = None
    protein_path: Optional[str] = None
    ligand_path: Optional[str] = None
    data_id: Optional[int] = Field(default=None, ge=0)
    round_id: int = Field(default=1, ge=1)
    batch_size: int = Field(default=5, ge=1, le=1000)
    sample_only: bool = True
    auto_extract: bool = False
    remove_fragments: bool = True
    max_samples: int = Field(default=5, ge=1, le=100)
    gpus: Optional[str] = None
    async_run: bool = True


class EvaluateRequest(BaseModel):
    pt_file: str
    visualize: bool = False
    gpus: Optional[str] = None
    async_run: bool = True


class ExtractRequest(BaseModel):
    pt_file: str
    output_dir: Optional[str] = None
    protein_root: Optional[str] = None
    remove_fragments: bool = True
    max_samples: int = Field(default=5, ge=1, le=100)
    async_run: bool = True


class IngestRequest(BaseModel):
    round_id: int
    sdf_path: Optional[str] = None
    pt_file: Optional[str] = None


def _runner(request: Request) -> DiffDynamicRunner:
    return DiffDynamicRunner(get_settings().diffdynamic)


def _safe_optional_path(path: Optional[str], *, must_exist: bool = False) -> Optional[str]:
    if not path:
        return None
    return str(ensure_safe_path(path, must_exist=must_exist))


def _resolve_protein(db: Session, body: GenerateRequest) -> Optional[str]:
    if body.protein_path:
        safe = _safe_optional_path(body.protein_path, must_exist=True)
        if safe:
            return safe
    if body.target_id:
        target = db.query(Target).filter(Target.id == body.target_id).first()
        if target:
            if target.structure_path and Path(target.structure_path).is_file():
                return target.structure_path
            if target.pdb_id:
                pdb_path = Path("data/targets") / f"{target.pdb_id.lower().strip()}.pdb"
                if pdb_path.is_file():
                    return str(pdb_path.resolve())
    return None


@router.get("/status")
async def diffdynamic_status(request: Request):
    return _runner(request).status()


@router.post("/generate")
async def diffdynamic_generate(body: GenerateRequest, request: Request, db: Session = Depends(get_db)):
    runner = _runner(request)
    body = body.model_copy(update={
        "ligand_path": _safe_optional_path(body.ligand_path, must_exist=True),
    })
    protein = _resolve_protein(db, body)
    if body.mode == "custom" or protein:
        if not protein:
            raise AppError(
                message="Custom generation requires protein_path or valid target_id",
                code="DIFFDYNAMIC_NO_PROTEIN",
                status_code=400,
            )
        body = body.model_copy(update={"protein_path": protein, "mode": "custom"})
    elif body.data_id is None:
        body = body.model_copy(update={"data_id": 0})

    create_round(db, round_id=body.round_id, target_id=body.target_id)

    def _do_generate() -> dict:
        if body.auto_extract:
            return runner.auto_chain(
                data_id=body.data_id,
                protein_path=body.protein_path,
                ligand_path=body.ligand_path,
                batch_size=body.batch_size,
                mode="prudent" if body.mode == "prudent" else "dynamic",
                max_samples=body.max_samples,
                remove_fragments=body.remove_fragments,
            )
        return runner.run_generate(
            mode=body.mode,
            data_id=body.data_id,
            protein_path=body.protein_path,
            ligand_path=body.ligand_path,
            batch_size=body.batch_size,
            sample_only=body.sample_only,
            gpus=body.gpus,
        )

    if not body.async_run:
        result = await asyncio.to_thread(_do_generate)
        if result.get("ok"):
            sdf_path = result.get("sdf_path") or (result.get("extract") or {}).get("sdf_path")
            pt_path = result.get("pt_path") or (result.get("generate") or {}).get("pt_path")
            write_step_log(
                body.round_id,
                "generation",
                "done",
                sdf_path=sdf_path,
                pt_path=pt_path,
            )
            update_round(db, body.round_id, status="generated")
        return result

    job_id = job_store.create("diffdynamic_generate", params=body.model_dump())

    async def _task():
        job_store.update(job_id, status="running", message="DiffDynamic generation in progress")
        db_task = get_sessionmaker()()
        try:
            result = await asyncio.to_thread(_do_generate)
            if result.get("ok"):
                sdf_path = result.get("sdf_path") or (result.get("extract") or {}).get("sdf_path")
                pt_path = result.get("pt_path") or (result.get("generate") or {}).get("pt_path")
                write_step_log(
                    body.round_id,
                    "generation",
                    "done",
                    sdf_path=sdf_path,
                    pt_path=pt_path,
                )
                if sdf_path:
                    add_artifact(db_task, body.round_id, "generation", "sdf", sdf_path)
                if pt_path:
                    add_artifact(db_task, body.round_id, "generation", "pt", pt_path)
                update_round(db_task, body.round_id, status="generated")
                job_store.update(job_id, status="completed", progress=1.0, result=result)
            else:
                err = (
                    result.get("error")
                    or (result.get("generate") or {}).get("stderr")
                    or (result.get("extract") or {}).get("stderr")
                    or (result.get("generate") or {}).get("error")
                    or (result.get("extract") or {}).get("error")
                    or "DiffDynamic generation failed"
                )
                job_store.update(job_id, status="failed", error=err)
        except Exception as exc:
            job_store.update(job_id, status="failed", error=str(exc))
        finally:
            db_task.close()

    asyncio.create_task(_task())
    return {"ok": True, "job_id": job_id, "message": "DiffDynamic generation started"}


@router.post("/evaluate")
async def diffdynamic_evaluate(body: EvaluateRequest, request: Request):
    runner = _runner(request)
    pt_file = _safe_optional_path(body.pt_file, must_exist=True)
    if not pt_file:
        raise AppError(message="pt_file required", code="DIFFDYNAMIC_NO_PT", status_code=400)

    if not body.async_run:
        return await asyncio.to_thread(
            runner.evaluate,
            pt_file=pt_file,
            visualize=body.visualize,
            gpus=body.gpus,
        )

    job_id = job_store.create("diffdynamic_evaluate", params=body.model_dump())

    async def _task():
        job_store.update(job_id, status="running", message="DiffDynamic evaluation in progress")
        try:
            result = await asyncio.to_thread(
                runner.evaluate,
                pt_file=pt_file,
                visualize=body.visualize,
                gpus=body.gpus,
            )
            if result.get("ok"):
                job_store.update(job_id, status="completed", progress=1.0, result=result)
            else:
                job_store.update(job_id, status="failed", error=result.get("stderr") or "Evaluation failed")
        except Exception as exc:
            job_store.update(job_id, status="failed", error=str(exc))

    asyncio.create_task(_task())
    return {"ok": True, "job_id": job_id, "message": "DiffDynamic evaluation started"}


@router.post("/extract")
async def diffdynamic_extract(body: ExtractRequest, request: Request):
    runner = _runner(request)
    pt_file = _safe_optional_path(body.pt_file, must_exist=True)
    if not pt_file:
        raise AppError(message="pt_file required", code="DIFFDYNAMIC_NO_PT", status_code=400)
    output_dir = _safe_optional_path(body.output_dir)
    protein_root = _safe_optional_path(body.protein_root, must_exist=True)

    if not body.async_run:
        return await asyncio.to_thread(
            runner.extract_pt,
            pt_file=pt_file,
            output_dir=output_dir,
            protein_root=protein_root,
            remove_fragments=body.remove_fragments,
            max_samples=body.max_samples,
        )

    job_id = job_store.create("diffdynamic_extract", params=body.model_dump())

    async def _task():
        job_store.update(job_id, status="running", message="DiffDynamic extract in progress")
        try:
            result = await asyncio.to_thread(
                runner.extract_pt,
                pt_file=pt_file,
                output_dir=output_dir,
                protein_root=protein_root,
                remove_fragments=body.remove_fragments,
                max_samples=body.max_samples,
            )
            if result.get("ok"):
                job_store.update(job_id, status="completed", progress=1.0, result=result)
            else:
                job_store.update(job_id, status="failed", error=result.get("stderr") or result.get("error"))
        except Exception as exc:
            job_store.update(job_id, status="failed", error=str(exc))

    asyncio.create_task(_task())
    return {"ok": True, "job_id": job_id, "message": "DiffDynamic extract started"}


@router.get("/jobs/{job_id}")
async def diffdynamic_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise AppError(message="Job not found", code="JOB_NOT_FOUND", status_code=404)
    return job


@router.post("/ingest")
async def diffdynamic_ingest(body: IngestRequest, request: Request, db: Session = Depends(get_db)):
    runner = _runner(request)
    sdf: Optional[str] = body.sdf_path

    if not sdf and body.pt_file:
        extract = await asyncio.to_thread(runner.extract_pt, pt_file=body.pt_file)
        if not extract.get("ok"):
            raise AppError(
                message=extract.get("error") or extract.get("stderr") or "Extract failed",
                code="DIFFDYNAMIC_EXTRACT_FAILED",
                status_code=500,
            )
        sdf = extract.get("sdf_path")

    if not sdf:
        round_dir = runner.round_output_dir(body.round_id)
        candidates = runner.find_sdf_files(round_dir)
        if candidates:
            merged = round_dir / f"round_{body.round_id}_all.sdf"
            runner.merge_sdf_files(candidates, merged)
            sdf = str(merged)

    if not sdf or not Path(sdf).is_file():
        raise AppError(message=f"SDF not found: {sdf}", code="DIFFDYNAMIC_SDF_MISSING", status_code=404)

    molecules_dir = resolve_repo_path("molecules/sdf/diffdynamic").resolve()
    molecules_dir.mkdir(parents=True, exist_ok=True)
    dest = molecules_dir / f"diffdynamic_round_{body.round_id}.sdf"
    shutil.copy2(sdf, dest)

    sync_result = await asyncio.to_thread(sync_sdf_library, db, str(molecules_dir.parent))
    add_artifact(db, body.round_id, "ingest", "sdf", str(dest))
    return {"ok": True, "sdf_path": str(dest), "sync": sync_result.to_dict()}
