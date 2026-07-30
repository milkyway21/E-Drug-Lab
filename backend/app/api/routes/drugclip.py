"""DrugCLIP virtual screening Docker integration routes."""
import asyncio
import json as _json
from pathlib import Path
from typing import Optional
from urllib.request import Request as UrllibRequest, urlopen
from urllib.error import URLError

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.errors import AppError
from app.core.paths import resolve_repo_path

router = APIRouter(prefix="/api/v1/drugclip", tags=["DrugCLIP"])


class ServiceCommandRequest(BaseModel):
    package_path: Optional[str] = None


class ScreenRequest(BaseModel):
    sdf_path: str = Field(..., description="SDF file path inside the DrugCLIP container (e.g. /app/work/lib.sdf)")
    pocket_pdb_path: str = Field(..., description="PDB pocket file path inside the DrugCLIP container")
    pocket_center: Optional[list[float]] = Field(None, description="Pocket center [x,y,z] Angstrom")
    pocket_radius: float = Field(10.0, description="Pocket extraction radius Angstrom")
    top_k: int = Field(1000, ge=1, le=100000)
    ingest: bool = Field(True, description="Sync results into molecule DB")


class PipelineScreenRequest(BaseModel):
    target_pdb_id: str = Field(..., description="RCSB PDB ID for the target pocket")
    top_k: int = Field(default=10, ge=1, le=1000)
    auto_ingest: bool = Field(default=True)


@router.get("/status")
async def drugclip_status(request: Request):
    return _runner(request).status()


@router.post("/service/start")
async def start_service(body: ServiceCommandRequest, request: Request):
    runner = _runner(request, package_override=body.package_path)
    result = runner.start_service()
    return {
        "ok": result.returncode == 0,
        "package_path": str(runner.package_path),
        "result": result.to_dict(),
    }


@router.post("/service/stop")
async def stop_service(body: ServiceCommandRequest, request: Request):
    runner = _runner(request, package_override=body.package_path)
    result = runner.stop_service()
    return {
        "ok": result.returncode == 0,
        "package_path": str(runner.package_path),
        "result": result.to_dict(),
    }


@router.get("/service/health")
async def service_health(request: Request):
    return await _check_service_health(request)


@router.post("/smoke-test")
async def smoke_test(request: Request, db: Session = Depends(get_db)):
    runner = _runner(request)
    result = await asyncio.to_thread(runner.run_smoke_test, db)
    if not result.get("ok"):
        raise AppError(
            message=f"DrugCLIP smoke test failed: {result}",
            code="DRUGCLIP_SMOKE_TEST_FAILED",
            status_code=500,
            details={"result": result},
        )
    return result


@router.post("/pipeline-screen")
async def pipeline_screen(body: PipelineScreenRequest, request: Request, db: Session = Depends(get_db)):
    runner = _runner(request)
    result = await asyncio.to_thread(
        runner.run_pipeline_screen,
        body.target_pdb_id,
        body.top_k,
        db,
        body.auto_ingest,
    )
    if not result.get("ok"):
        raise AppError(
            message=f"DrugCLIP pipeline screen failed: {result}",
            code="DRUGCLIP_PIPELINE_SCREEN_FAILED",
            status_code=500,
        )
    return result


@router.post("/screen")
async def screen(body: ScreenRequest, request: Request, db: Session = Depends(get_db)):
    """Run DrugCLIP virtual screening via the Docker service."""
    settings = request.app.state.settings
    runner = _runner(request)

    try:
        data = await asyncio.to_thread(
            runner.screen,
            body.sdf_path,
            body.pocket_pdb_path,
            body.top_k,
            body.pocket_center,
            body.pocket_radius,
        )
    except URLError as exc:
        raise AppError(
            message=f"DrugCLIP service unreachable: {exc}",
            code="DRUGCLIP_UNAVAILABLE",
            status_code=503,
        )

    if not data.get("ok"):
        raise AppError(
            message=f"DrugCLIP screening failed: {data}",
            code="DRUGCLIP_SCREEN_FAILED",
            status_code=500,
        )

    ingest_result = None
    if body.ingest and data.get("results"):
        ingest_result = runner.ingest_results(
            db,
            data["results"],
            f"drugclip_screen_{Path(body.sdf_path).stem}.sdf",
        )

    return {
        "ok": True,
        "screening": data,
        "ingest": ingest_result,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _urlopen_text(url: str, timeout: int) -> str:
    """同步 HTTP GET，返回文本。通过 asyncio.to_thread 调用。"""
    with urlopen(url, timeout=timeout) as resp:
        return resp.read().decode()


async def _check_service_health(request: Request) -> dict:
    settings = request.app.state.settings
    url = settings.drugclip.service_url.rstrip("/") + "/health"
    try:
        body = await asyncio.to_thread(_urlopen_text, url, 5)
        return {"ok": True, "url": url, "body": body}
    except (URLError, OSError) as exc:
        return {"ok": False, "url": url, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def _runner(request: Request, package_override: Optional[str] = None):
    from app.services.drugclip_docker import DrugClipDockerRunner
    settings = request.app.state.settings
    pkg = resolve_repo_path(package_override or settings.drugclip.package_path)
    out = resolve_repo_path(settings.drugclip.output_dir)
    return DrugClipDockerRunner(
        package_path=str(pkg),
        image_name=settings.drugclip.image_name,
        service_url=settings.drugclip.service_url,
        output_dir=str(out),
        wsl_exe=settings.drugclip.wsl_exe,
        wsl_distro=settings.drugclip.wsl_distro,
        timeout=settings.drugclip.timeout,
    )

