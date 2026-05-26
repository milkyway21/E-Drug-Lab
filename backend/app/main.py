"""
e-drug lab FastAPI 应用入口
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings, Settings
from app.core.errors import AppError, app_error_handler, generic_error_handler
from app.services.tool_manager import ToolManager
from app.repositories.models import Base

from app.api.routes import targets as targets_routes
from app.api.routes import libraries as libraries_routes
from app.api.routes import molecule_db as molecule_db_routes
from app.api.routes import ranking as ranking_routes
from app.api.routes import tame_vs as tame_vs_routes
from app.api.routes.combined_routes import (
    admet_router,
    affinity_router,
    molecules_router,
    screening_router,
    tasks_router,
)

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)


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

    app.state.settings = settings
    app.state.tool_manager = tool_manager
    app.state.request_counter = 0

    # 初始化 SQLite 数据库
    db_url = settings.database.url
    if db_url.startswith('sqlite'):
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(bind=engine)
        Base.metadata.create_all(bind=engine)
        app.state.db_session = SessionLocal()
        logger.info(f"✅ 数据库已连接: {db_url}")
    else:
        app.state.db_session = None
        logger.warning("非 SQLite 数据库需手动配置连接")

    logger.info("✅ 初始化完成")
    yield
    logger.info("👋 e-drug lab 关闭中...")
    logger.info("✅ 已关闭所有连接")


app = FastAPI(
    title="e-drug lab",
    description="先导化合物生成与虚拟筛选一体化平台",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_settings.cors_origins_list,
    allow_credentials=True,
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
app.add_exception_handler(Exception, generic_error_handler)

app.include_router(targets_routes.router)
app.include_router(libraries_routes.router)
app.include_router(molecule_db_routes.router)
app.include_router(ranking_routes.router)
app.include_router(tame_vs_routes.router)
app.include_router(screening_router)
app.include_router(admet_router)
app.include_router(affinity_router)
app.include_router(molecules_router)
app.include_router(tasks_router)


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
