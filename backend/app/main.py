"""
e-drug lab FastAPI 应用入口
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import uuid

from app.config import get_settings, Settings
from app.core.errors import AppError, app_error_handler, generic_error_handler, validation_error_handler
from app.db import init_engine, get_engine
from app.services.tool_manager import ToolManager
from app.repositories.models import Base

from app.api.routes import targets as targets_routes
from app.api.routes import libraries as libraries_routes
from app.api.routes import molecule_db as molecule_db_routes
from app.api.routes import ranking as ranking_routes
from app.api.routes import tame_vs as tame_vs_routes
from app.api.routes import drugclip as drugclip_routes
from app.api.routes import diffgui as diffgui_routes
from app.api.routes import diffdynamic as diffdynamic_routes
from app.api.routes import glare as glare_routes
from app.api.routes import rl_rounds as rl_rounds_routes
from app.api.routes import vav1_rl as vav1_rl_routes
from app.api.routes.screening import router as screening_router
from app.api.routes.admet import router as admet_router
from app.api.routes.affinity import router as affinity_router
from app.api.routes.molecules import router as molecules_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.pipeline import router as pipeline_router
from app.api.routes.wetlab import router as wetlab_router
from app.api.routes.agent import router as agent_router

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)


def _redact_db_url(url: str) -> str:
    """Hide credentials in database URLs for logs."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    creds, hostpart = rest.rsplit("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{hostpart}"
    return f"{scheme}://***@{hostpart}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 e-drug lab 启动中...")
    settings = get_settings()

    tool_manager = ToolManager({
        "autodock_vina": settings.tool_paths.autodock_vina,
        "fpocket": settings.tool_paths.fpocket,
        "gromacs": settings.tool_paths.gromacs,
        "rdkit_data": settings.tool_paths.rdkit_data,
    })
    from app.services.docking_prep import ensure_vina_tool
    if ensure_vina_tool(tool_manager, settings.tool_paths.autodock_vina):
        logger.info("AutoDock Vina auto-discovered and registered")

    app.state.settings = settings
    app.state.tool_manager = tool_manager
    app.state.request_counter = 0

    # 初始化数据库引擎（每请求通过 get_db() 获取 session）
    db_url = settings.database.url
    init_engine(db_url, echo=settings.database.echo)
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info(f"✅ 数据库已连接: {_redact_db_url(db_url)}")

    logger.info("✅ 初始化完成")
    yield
    logger.info("👋 e-drug lab 关闭中...")
    engine = get_engine()
    if engine:
        engine.dispose()
    logger.info("✅ 已关闭所有连接")


app = FastAPI(
    title="e-drug lab",
    description="先导化合物生成与虚拟筛选一体化平台",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_settings = get_settings()
_cors_origins = ["*"] if _cors_settings.debug else _cors_settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False if _cors_settings.debug else True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    app.state.request_counter += 1
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def log_request(request: Request, call_next):
    import time
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s",
                extra={"request_id": getattr(request.state, "request_id", None)})
    return response


app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, generic_error_handler)

app.include_router(targets_routes.router)
app.include_router(libraries_routes.router)
app.include_router(molecule_db_routes.router)
app.include_router(ranking_routes.router)
app.include_router(tame_vs_routes.router)
app.include_router(drugclip_routes.router)
app.include_router(diffgui_routes.router)
app.include_router(diffdynamic_routes.router)
app.include_router(glare_routes.router)
app.include_router(rl_rounds_routes.router)
app.include_router(vav1_rl_routes.router)
app.include_router(screening_router)
app.include_router(admet_router)
app.include_router(affinity_router)
app.include_router(molecules_router)
app.include_router(tasks_router)
app.include_router(pipeline_router)
app.include_router(wetlab_router)
app.include_router(agent_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}


@app.get("/ready", tags=["Health"])
async def readiness_check(request: Request):
    tool_manager = request.app.state.tool_manager
    tool_status = tool_manager.get_tool_status()
    available_tools = sum(1 for t in tool_status.values() if t["available"])
    return {"status": "ready" if available_tools > 0 else "degraded", "tools_available": available_tools, "tools_total": len(tool_status), "tools": tool_status}


@app.get("/api/v1/tools/status", tags=["Tools"])
async def get_tools_status(request: Request):
    return request.app.state.tool_manager.get_tool_status()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug, log_level=settings.log_level.lower())
