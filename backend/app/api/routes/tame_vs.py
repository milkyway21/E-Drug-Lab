"""TAME-VS 2.0 Docker integration routes."""
from pathlib import Path
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.errors import AppError
from app.services.tame_vs_docker import TameVSDockerRunner

router = APIRouter(prefix="/api/v1/tame-vs", tags=["TAME-VS"])


class BuildImageRequest(BaseModel):
    image_name: Optional[str] = None


class LibraryPreparationRequest(BaseModel):
    input_csv: str
    output_name: str = Field(default="tame_vs_library_morgan_1024_FP")
    smiles_col: int = Field(default=1, ge=1)
    compound_id_col: int = Field(default=2, ge=1)
    auto_ingest: bool = Field(default=True)


class IngestResultsRequest(BaseModel):
    result_csv: str
    sdf_name: Optional[str] = None


class ServiceCommandRequest(BaseModel):
    package_path: Optional[str] = None


class FullScreenRequest(BaseModel):
    top_percent: float = Field(default=1.0, ge=0.1, le=100.0)
    target_pdb_id: Optional[str] = None
    auto_ingest: bool = Field(default=True)


@router.get("/status")
async def tame_vs_status(request: Request):
    return _runner(request).status()


@router.post("/build-image")
async def build_tame_vs_image(body: BuildImageRequest, request: Request):
    runner = _runner(request, image_name=body.image_name)
    result = runner.build_image()
    return {
        "ok": result.returncode == 0,
        "message": "Docker image built" if result.returncode == 0 else "Docker image build failed",
        "result": result.to_dict(),
    }


@router.post("/prepare-library")
async def prepare_library(body: LibraryPreparationRequest, request: Request, db: Session = Depends(get_db)):
    runner = _runner(request)
    result = runner.run_library_preparation(
        input_csv=body.input_csv,
        output_name=body.output_name,
        smiles_col=body.smiles_col,
        compound_id_col=body.compound_id_col,
    )
    fingerprint_csv = Path(runner.output_dir) / f"{body.output_name}.csv"
    ingest = None
    if body.auto_ingest and result.returncode == 0 and fingerprint_csv.exists():
        ingest = runner.ingest_result_csv(db, str(fingerprint_csv), f"{body.output_name}.sdf")
    return {
        "ok": result.returncode == 0,
        "fingerprint_csv": str(fingerprint_csv),
        "result": result.to_dict(),
        "ingest": ingest,
    }


@router.post("/smoke-test")
async def smoke_test(request: Request, db: Session = Depends(get_db)):
    runner = _runner(request)
    result = runner.run_smoke_test(db)
    return result


@router.post("/full-50k-screen")
async def full_50k_screen(body: FullScreenRequest, request: Request, db: Session = Depends(get_db)):
    """Run full virtual screening on Enamine 50K library"""
    runner = _runner(request)
    result = runner.run_full_50k_screen(
        top_percent=body.top_percent,
        target_pdb_id=body.target_pdb_id,
        db=db if body.auto_ingest else None,
    )
    return result


@router.post("/ingest-results")
async def ingest_results(body: IngestResultsRequest, request: Request, db: Session = Depends(get_db)):
    runner = _runner(request)
    return runner.ingest_result_csv(db, body.result_csv, body.sdf_name)


@router.post("/service/start")
async def start_service(request: Request):
    result = _runner(request).start_service()
    return {"ok": result.returncode == 0, "result": result.to_dict()}


@router.post("/service/stop")
async def stop_service(request: Request):
    result = _runner(request).stop_service()
    return {"ok": result.returncode == 0, "result": result.to_dict()}


@router.post("/service/restart")
async def restart_service(request: Request):
    result = _runner(request).restart_service()
    return {"ok": result.returncode == 0, "result": result.to_dict()}


@router.get("/service/health")
async def service_health(request: Request):
    settings = request.app.state.settings
    health_url = settings.tame_vs.service_url.rstrip("/") + "/health"
    try:
        with urlopen(health_url, timeout=5) as response:
            body = response.read().decode("utf-8", errors="replace")
        return {"ok": True, "url": health_url, "body": body}
    except URLError as exc:
        return {"ok": False, "url": health_url, "error": str(exc)}


def _runner(request: Request, image_name: Optional[str] = None) -> TameVSDockerRunner:
    settings = request.app.state.settings
    project_root = Path(__file__).resolve().parents[4]
    repo_path = Path(settings.tame_vs.repo_path)
    output_dir = Path(settings.tame_vs.output_dir)
    package_path = Path(settings.tame_vs.package_path)

    if not repo_path.is_absolute():
        repo_path = (project_root / repo_path).resolve()
    if not output_dir.is_absolute():
        output_dir = (project_root / output_dir).resolve()
    if not package_path.is_absolute():
        package_path = (project_root / package_path).resolve()

    return TameVSDockerRunner(
        repo_path=str(repo_path),
        image_name=image_name or settings.tame_vs.image_name,
        output_dir=str(output_dir),
        package_path=str(package_path),
        service_url=settings.tame_vs.service_url,
        wsl_exe=settings.tame_vs.wsl_exe,
        wsl_distro=settings.tame_vs.wsl_distro,
        timeout=settings.tame_vs.timeout,
    )
