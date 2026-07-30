"""GLARE screening and RL training routes."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.db import get_db, get_sessionmaker
from app.repositories.models import RLRoundArtifact
from app.services.glare_runner import GlareRunner
from app.services.job_store import job_store
from app.services.pipeline_eval_bridge import resolve_evaluated_path
from app.services.rl_round_service import (
    add_artifact,
    get_round,
    read_step_log,
    round_dir,
    update_round,
    write_step_log,
)
from app.core.workflow_steps import PIPELINE_STEP_GLARE_SCREEN, PIPELINE_STEP_RL_TRAIN

router = APIRouter(prefix="/api/v1/glare", tags=["GLARE"])


class ScreenRequest(BaseModel):
    round_id: int = Field(ge=1)
    evaluated_file: Optional[str] = None
    pipeline_molecules: Optional[list[dict[str, Any]]] = None
    checkpoint: Optional[str] = None
    top_n: int = Field(default=200, ge=1, le=5000)
    wetlab_sample_count: int = 0
    auto_ingest: bool = True
    async_run: bool = True
    use_gnn_grpo: bool = Field(default=False, description="Use GNN+GRPO adapter (diffgui_new env) instead of legacy GlareRunner")


class TrainRequest(BaseModel):
    round_id: int = Field(ge=1)
    evaluated_file: Optional[str] = None
    pipeline_molecules: Optional[list[dict[str, Any]]] = None
    run_seed_reinforce: bool = True
    run_train: bool = True
    wetlab_file: Optional[str] = None
    previous_checkpoint: Optional[str] = None
    async_run: bool = True
    use_gnn_grpo: bool = Field(default=False, description="Use GNN+GRPO adapter (diffgui_new env) instead of legacy GlareRunner")


class RankedMolecule(BaseModel):
    smiles: str
    canonical_smiles: Optional[str] = None
    predicted_pdc50: Optional[float] = None
    final_selection_score: Optional[float] = None
    oracle_score: Optional[float] = None
    predicted_functional_activity_score: Optional[float] = None
    rank: Optional[int] = None


def _runner(request: Request) -> GlareRunner:
    return GlareRunner(get_settings().glare)


def _find_ranked_csv(round_id: int, db: Session) -> Optional[str]:
    """定位某轮 GLARE ranked CSV：artifacts 表 → step_log → 默认路径。"""
    art = (
        db.query(RLRoundArtifact)
        .filter(RLRoundArtifact.round_id == round_id)
        .filter(RLRoundArtifact.step == PIPELINE_STEP_GLARE_SCREEN)
        .filter(RLRoundArtifact.artifact_type == "csv")
        .order_by(RLRoundArtifact.created_at.desc())
        .first()
    )
    if art and Path(art.path).is_file():
        return art.path
    log = read_step_log(round_id)
    step = log.get(PIPELINE_STEP_GLARE_SCREEN) or {}
    csv = step.get("ranked_csv") if isinstance(step, dict) else None
    if csv and Path(csv).is_file():
        return csv
    default = round_dir(round_id) / "glare_results" / f"round_{round_id}_glare_ranked_all.csv"
    if default.is_file():
        return str(default)
    return None


@router.get("/status")
async def glare_status(request: Request):
    status = _runner(request).status()
    # 附加 GNN+GRPO 可用性信息
    try:
        from app.pipelines.vav1_rl.glare_gnn_adapter import smoke_test
        gnn = smoke_test()
        status["gnn_grpo"] = {"available": gnn.get("ok", False), "env": gnn.get("env"), "error": gnn.get("error")}
    except Exception:
        status["gnn_grpo"] = {"available": False, "error": "glare_gnn_adapter import failed"}
    return status


@router.get("/ranked/{round_id}")
async def get_ranked_molecules(round_id: int, db: Session = Depends(get_db)):
    """读取某轮 GLARE ranked CSV，返回每分子分数（供前端回灌 stepResults）。"""
    csv_path = _find_ranked_csv(round_id, db)
    if not csv_path:
        raise AppError(
            message=f"No ranked CSV for round {round_id}; run GLARE screen first",
            code="GLARE_RANKED_NOT_FOUND",
            status_code=404,
        )
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        raise AppError(message=f"Failed to read ranked CSV: {exc}", code="GLARE_RANKED_READ_FAILED", status_code=500)

    def _col(name: str) -> Optional[Any]:
        for c in df.columns:
            if str(c).strip().lower() == name:
                return df[c]
        return None

    smi_col = _col("smiles") or _col("canonical_smiles")
    if smi_col is None:
        raise AppError(message="ranked CSV has no smiles column", code="GLARE_RANKED_NO_SMILES", status_code=500)

    ranked: list[dict[str, Any]] = []
    for idx in range(len(df)):
        smiles = smi_col.iloc[idx]
        if smiles is None or (isinstance(smiles, float) and pd.isna(smiles)):
            continue

        def _val(name: str) -> Optional[float]:
            col = _col(name)
            if col is None:
                return None
            v = col.iloc[idx]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        ranked.append({
            "smiles": str(smiles),
            "canonical_smiles": _val("canonical_smiles"),
            "predicted_pdc50": _val("predicted_pdc50"),
            "final_selection_score": _val("final_selection_score"),
            "oracle_score": _val("oracle_score"),
            "predicted_functional_activity_score": _val("predicted_functional_activity_score"),
            "rank": idx + 1,
        })
    return {"round_id": round_id, "ranked": ranked, "csv_path": csv_path}


@router.post("/screen")
async def glare_screen(body: ScreenRequest, request: Request, db: Session = Depends(get_db)):
    # GNN+GRPO path
    if body.use_gnn_grpo:
        return await _gnn_grpo_screen(body, db)
    # Legacy GlareRunner path
    runner = _runner(request)
    evaluated = resolve_evaluated_path(body.round_id, body.evaluated_file, body.pipeline_molecules)
    checkpoint = body.checkpoint or runner.latest_checkpoint(body.round_id)
    if not checkpoint or not Path(checkpoint).is_file():
        raise AppError(message="No GLARE checkpoint available; run RL training first", code="GLARE_NO_CHECKPOINT", status_code=400)

    if not body.async_run:
        result = await asyncio.to_thread(
            runner.run_screen,
            evaluated_file=evaluated,
            round_id=body.round_id,
            checkpoint=checkpoint,
            top_n=body.top_n,
            wetlab_sample_count=body.wetlab_sample_count,
        )
        return result

    job_id = job_store.create("glare_screen", params=body.model_dump())

    async def _task():
        job_store.update(job_id, status="running")
        db_task = get_sessionmaker()()
        try:
            result = await asyncio.to_thread(
                runner.run_screen,
                evaluated_file=evaluated,
                round_id=body.round_id,
                checkpoint=checkpoint,
                top_n=body.top_n,
                wetlab_sample_count=body.wetlab_sample_count,
            )
            if result.get("ok"):
                write_step_log(body.round_id, PIPELINE_STEP_GLARE_SCREEN, "done", ranked_csv=result.get("ranked_csv"))
                if result.get("ranked_csv"):
                    add_artifact(db_task, body.round_id, PIPELINE_STEP_GLARE_SCREEN, "csv", result["ranked_csv"])
                update_round(db_task, body.round_id, status="screened", checkpoint_path=checkpoint)
                job_store.update(job_id, status="completed", result=result)
            else:
                job_store.update(job_id, status="failed", error=result.get("stderr"))
        except Exception as exc:
            job_store.update(job_id, status="failed", error=str(exc))
        finally:
            db_task.close()

    asyncio.create_task(_task())
    return {"ok": True, "job_id": job_id, "checkpoint": checkpoint, "evaluated_file": evaluated}


@router.post("/train")
async def glare_train(body: TrainRequest, request: Request, db: Session = Depends(get_db)):
    # GNN+GRPO path
    if body.use_gnn_grpo:
        return await _gnn_grpo_train(body, db)
    # Legacy GlareRunner path
    runner = _runner(request)
    evaluated = resolve_evaluated_path(body.round_id, body.evaluated_file, body.pipeline_molecules)

    if not body.async_run:
        results = {}
        if body.run_seed_reinforce:
            results["seed_reinforce"] = await asyncio.to_thread(
                runner.run_seed_reinforce, evaluated_file=evaluated, round_id=body.round_id,
            )
        if body.wetlab_file:
            results["wetlab_reinforce"] = await asyncio.to_thread(
                runner.run_wetlab_reinforce,
                evaluated_file=evaluated,
                round_id=body.round_id,
                wetlab_file=body.wetlab_file,
                previous_checkpoint=body.previous_checkpoint,
            )
        if body.run_train:
            results["train"] = await asyncio.to_thread(
                runner.run_train, evaluated_file=evaluated, round_id=body.round_id,
            )
        ckpt = (results.get("wetlab_reinforce") or {}).get("checkpoint") or (results.get("train") or {}).get("checkpoint") or (results.get("seed_reinforce") or {}).get("checkpoint")
        if ckpt:
            update_round(db, body.round_id, status="trained", checkpoint_path=ckpt)
        return results

    job_id = job_store.create("glare_train", params=body.model_dump())

    async def _task():
        job_store.update(job_id, status="running")
        db_task = get_sessionmaker()()
        try:
            results: dict[str, Any] = {}
            if body.run_seed_reinforce:
                results["seed_reinforce"] = await asyncio.to_thread(
                    runner.run_seed_reinforce, evaluated_file=evaluated, round_id=body.round_id,
                )
            if body.wetlab_file:
                results["wetlab_reinforce"] = await asyncio.to_thread(
                    runner.run_wetlab_reinforce,
                    evaluated_file=evaluated,
                    round_id=body.round_id,
                    wetlab_file=body.wetlab_file,
                    previous_checkpoint=body.previous_checkpoint,
                )
            if body.run_train:
                results["train"] = await asyncio.to_thread(
                    runner.run_train, evaluated_file=evaluated, round_id=body.round_id,
                )
            ckpt = (results.get("wetlab_reinforce") or {}).get("checkpoint") or (results.get("train") or {}).get("checkpoint") or (results.get("seed_reinforce") or {}).get("checkpoint")
            write_step_log(body.round_id, PIPELINE_STEP_RL_TRAIN, "done", checkpoint=ckpt)
            if ckpt:
                update_round(db_task, body.round_id, status="trained", checkpoint_path=ckpt)
                add_artifact(db_task, body.round_id, PIPELINE_STEP_RL_TRAIN, "checkpoint", ckpt)
            job_store.update(job_id, status="completed", result=results)
        except Exception as exc:
            job_store.update(job_id, status="failed", error=str(exc))
        finally:
            db_task.close()

    asyncio.create_task(_task())
    return {"ok": True, "job_id": job_id, "evaluated_file": evaluated}


@router.post("/import-wetlab")
async def import_wetlab(
    request: Request,
    round_id: int,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    auto_reinforce: bool = False,
    evaluated_file: Optional[str] = None,
):
    """导入湿实验 pDC50 数据；可选 auto_reinforce 自动触发 wetlab_reinforce。"""
    runner = _runner(request)
    upload_dir = round_dir(round_id) / "wetlab"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)

    from app.services.conda_runner import conda_run
    pool = str(runner.rl_rounds_root() / "labeled_pool_master.xlsx")
    proc = await asyncio.to_thread(
        conda_run,
        runner.settings.conda_env,
        ["python", "glare_selector/import_wetlab_pdc50.py",
         "--round_id", str(round_id),
         "--wetlab_file", str(dest),
         "--labeled_pool", pool],
        cwd=runner.root,
        timeout=600,
    )
    if proc.returncode != 0:
        raise AppError(message=proc.stderr or "wetlab import failed", code="WETLAB_IMPORT_FAILED", status_code=500)

    row = get_round(db, round_id)
    count = (row.wetlab_count if row else 0) + 1
    update_round(db, round_id, wetlab_count=count, status="wetlab_imported")

    response: dict[str, Any] = {"ok": True, "wetlab_file": str(dest), "wetlab_count": count}

    if not auto_reinforce:
        return response

    # 自动触发 wetlab_reinforce：需要 evaluated.xlsx + checkpoint
    try:
        evaluated = resolve_evaluated_path(round_id, evaluated_file, None)
    except AppError as exc:
        response["reinforce_skipped"] = f"no evaluated.xlsx: {exc.message}"
        return response

    prev_ckpt = (row.checkpoint_path if row else None) or runner.latest_checkpoint(round_id)
    if not prev_ckpt or not Path(prev_ckpt).is_file():
        response["reinforce_skipped"] = "no checkpoint available; run GLARE train first"
        return response

    job_id = job_store.create("glare_wetlab_reinforce", params={"round_id": round_id, "wetlab_file": str(dest)})

    async def _task():
        job_store.update(job_id, status="running")
        db_task = get_sessionmaker()()
        try:
            result = await asyncio.to_thread(
                runner.run_wetlab_reinforce,
                evaluated_file=evaluated,
                round_id=round_id,
                wetlab_file=str(dest),
                previous_checkpoint=prev_ckpt,
            )
            if result.get("ok") and result.get("checkpoint"):
                update_round(db_task, round_id, status="trained", checkpoint_path=result["checkpoint"])
                add_artifact(db_task, round_id, PIPELINE_STEP_RL_TRAIN, "checkpoint", result["checkpoint"])
                write_step_log(round_id, "wetlab_reinforce", "done", checkpoint=result["checkpoint"])
                job_store.update(job_id, status="completed", result=result)
            else:
                job_store.update(job_id, status="failed", error=result.get("stderr"))
        except Exception as exc:
            job_store.update(job_id, status="failed", error=str(exc))
        finally:
            db_task.close()

    asyncio.create_task(_task())
    response["reinforce_job_id"] = job_id
    return response


@router.get("/jobs/{job_id}")
async def glare_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise AppError(message="Job not found", code="JOB_NOT_FOUND", status_code=404)
    return job


# ---------------------------------------------------------------------------
# GNN+GRPO helpers (use glare_gnn_adapter instead of legacy GlareRunner)
# ---------------------------------------------------------------------------
async def _gnn_grpo_screen(body: ScreenRequest, db: Session) -> dict:
    """Run GLARE screening via GNN+GRPO adapter (real GIN+ECFP encoder + GRPO policy)."""
    from app.pipelines.vav1_rl.glare_gnn_adapter import query, smoke_test

    # Verify availability
    health = smoke_test()
    if not health.get("ok"):
        raise AppError(
            message=f"GNN+GRPO not available: {health.get('error', 'unknown')}",
            code="GLARE_GNN_GRPO_UNAVAILABLE", status_code=503,
        )

    # Resolve input molecules
    if body.pipeline_molecules:
        smiles_list = [m.get("smiles", "") for m in body.pipeline_molecules if m.get("smiles")]
    elif body.evaluated_file:
        import pandas as pd
        df = pd.read_excel(body.evaluated_file) if body.evaluated_file.endswith(".xlsx") else pd.read_csv(body.evaluated_file)
        smi_col = next((c for c in df.columns if "smiles" in c.lower()), df.columns[0])
        smiles_list = df[smi_col].astype(str).tolist()
    else:
        raise AppError(message="GNN+GRPO screen requires pipeline_molecules or evaluated_file", code="GLARE_NO_INPUT", status_code=400)

    if not body.async_run:
        result = await asyncio.to_thread(query, checkpoint_path=body.checkpoint, smiles_list=smiles_list, top_n=body.top_n)
        return result

    job_id = job_store.create("glare_screen_gnn_grpo", params=body.model_dump())

    async def _task():
        job_store.update(job_id, status="running")
        db_task = get_sessionmaker()()
        try:
            result = await asyncio.to_thread(query, checkpoint_path=body.checkpoint, smiles_list=smiles_list, top_n=body.top_n)
            if result.get("ok"):
                write_step_log(body.round_id, PIPELINE_STEP_GLARE_SCREEN, "done", gnn_grpo=True, top_n=body.top_n)
                update_round(db_task, body.round_id, status="screened", checkpoint_path=body.checkpoint)
                job_store.update(job_id, status="completed", result=result)
            else:
                job_store.update(job_id, status="failed", error=result.get("error"))
        except Exception as exc:
            job_store.update(job_id, status="failed", error=str(exc))
        finally:
            db_task.close()

    asyncio.create_task(_task())
    return {"ok": True, "job_id": job_id, "backend": "gnn_grpo", "num_molecules": len(smiles_list)}


async def _gnn_grpo_train(body: TrainRequest, db: Session) -> dict:
    """Run GLARE training via GNN+GRPO adapter."""
    from app.pipelines.vav1_rl.glare_gnn_adapter import train, smoke_test

    health = smoke_test()
    if not health.get("ok"):
        raise AppError(
            message=f"GNN+GRPO not available: {health.get('error', 'unknown')}",
            code="GLARE_GNN_GRPO_UNAVAILABLE", status_code=503,
        )

    # Resolve training data
    if body.pipeline_molecules:
        smiles_list = [m.get("smiles", "") for m in body.pipeline_molecules if m.get("smiles")]
        labels = [int(m.get("label_active", m.get("label", 0))) for m in body.pipeline_molecules if m.get("smiles")]
    elif body.evaluated_file:
        import pandas as pd
        df = pd.read_excel(body.evaluated_file) if body.evaluated_file.endswith(".xlsx") else pd.read_csv(body.evaluated_file)
        smi_col = next((c for c in df.columns if "smiles" in c.lower()), df.columns[0])
        smiles_list = df[smi_col].astype(str).tolist()
        label_col = next((c for c in df.columns if "label" in c.lower() or "active" in c.lower()), None)
        labels = df[label_col].astype(int).tolist() if label_col else [0] * len(smiles_list)
    else:
        raise AppError(message="GNN+GRPO train requires pipeline_molecules or evaluated_file", code="GLARE_NO_INPUT", status_code=400)

    if not body.run_train:
        return {"ok": True, "message": "GNN+GRPO training skipped (run_train=False)"}

    ckpt = body.previous_checkpoint or str(Path(round_dir(body.round_id)) / f"gnn_grpo_round{body.round_id}.pt")
    Path(ckpt).parent.mkdir(parents=True, exist_ok=True)

    result = await asyncio.to_thread(
        train,
        checkpoint_path=ckpt,
        train_smiles=smiles_list,
        train_labels=labels,
        prev_checkpoint=body.previous_checkpoint if body.previous_checkpoint else None,
    )
    if result.get("ok"):
        write_step_log(body.round_id, PIPELINE_STEP_RL_TRAIN, "done", checkpoint=ckpt, gnn_grpo=True)
        update_round(db, body.round_id, status="trained", checkpoint_path=ckpt)
        add_artifact(db, body.round_id, PIPELINE_STEP_RL_TRAIN, "checkpoint", ckpt)
    return {**result, "backend": "gnn_grpo", "checkpoint": ckpt}
