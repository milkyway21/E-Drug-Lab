"""
薛定谔 API 客户端
对接 Glide Dock、Protein Prep Wizard 等 REST API

注意：当前版本为框架代码，API 方法的请求/响应结构基于薛定谔 FEP+ REST API 文档。
实际部署时需要根据获得的 API 文档和许可证调整 endpoint 和参数。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import logging

from httpx import AsyncClient

logger = logging.getLogger(__name__)


# ── 枚举与数据结构 ──────────────────────────────────────────

class GlidePrecision(str, Enum):
    """Glide 对接精度"""
    SP = "SP"       # Standard Precision
    XP = "XP"       # Extra Precision
    HTVS = "HTVS"   # High-Throughput Virtual Screening


class PrepWizardStep(str, Enum):
    """Protein Preparation Wizard 步骤"""
    PREPROCESS = "preprocess"
    HET_STATES = "het_states"
    OPTIMIZE_H = "optimize_h"
    MINIMIZE = "minimize"


class JobStatus(str, Enum):
    """薛定谔任务状态"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SchrodingerConfig:
    api_key: str
    base_url: str = "https://api.schrodinger.com/v1"
    timeout: int = 300
    max_retries: int = 3


@dataclass
class GlideGrid:
    """Glide 对接口袋定义"""
    # 方式 1：从配体自动推断（ligand-based）
    ligand_file: Optional[str] = None
    # 方式 2：手动指定中心点
    center_x: Optional[float] = None
    center_y: Optional[float] = None
    center_z: Optional[float] = None
    # 内框大小 (Å) — 默认 10Å
    inner_box: float = 10.0
    # 外框大小 (Å) — 默认 30Å
    outer_box: float = 30.0


@dataclass
class GlideDockRequest:
    """Glide 对接请求"""
    receptor_file: str            # Maestro 格式受体文件路径 (.mae/.maegz)
    ligands_file: str             # 配体库文件路径 (.sdf/.mae)
    precision: GlidePrecision = GlidePrecision.SP
    grid: Optional[GlideGrid] = None
    # 对接参数
    num_poses: int = 10           # 输出构象数
    post_docking_minimize: bool = True
    use_instrument_precision: bool = False
    # 过滤
    max_lmw: float = 1000.0       # 最大配体分子量
    max_rotatable_bonds: int = 32
    # 项目信息
    project_name: Optional[str] = None
    job_name: Optional[str] = None


@dataclass
class PrepWizardRequest:
    """Protein Preparation Wizard 请求"""
    input_structure: str          # PDB/Maestro 文件路径
    steps: list[PrepWizardStep] = field(default_factory=lambda: list(PrepWizardStep))
    # pH 范围用于质子化状态
    ph_range_low: float = 5.0
    ph_range_high: float = 9.0
    # 是否进行同源建模填补缺失残基
    fill_loops: bool = False
    fill_side_chains: bool = True
    # 最小化参数
    force_field: str = "OPLS4"    # OPLS4 / OPLS3e
    max_iterations: int = 1000
    converge_rms: float = 0.01
    # 项目信息
    project_name: Optional[str] = None
    job_name: Optional[str] = None


@dataclass
class SchrodingerJob:
    """薛定谔任务"""
    job_id: str
    status: JobStatus
    progress: float = 0.0         # 0-100
    result_url: Optional[str] = None
    error_message: Optional[str] = None
    output_files: list[str] = field(default_factory=list)


@dataclass
class GlideDockResult:
    """Glide 对接结果"""
    job_id: str
    status: JobStatus
    output_file: Optional[str] = None   # _pv.maegz 结果文件
    num_hits: int = 0
    best_score: Optional[float] = None
    ligands_file: str = ""
    receptor_file: str = ""
    precision: GlidePrecision = GlidePrecision.SP


@dataclass
class PrepWizardResult:
    """Protein Prep 结果"""
    job_id: str
    status: JobStatus
    output_structure: Optional[str] = None  # 预处理后的 .mae 文件
    warnings: list[str] = field(default_factory=list)
    chains_processed: int = 0
    residues_modified: int = 0


# ── 客户端 ──────────────────────────────────────────────────

class SchrodingerClient:
    """
    薛定谔 REST API 客户端

    提供 Glide Dock 和 Protein Preparation Wizard 的对接接口。
    所有方法均为异步，支持任务提交 → 状态轮询 → 结果下载的工作流。

    API endpoint 结构（基于薛定谔 FEP+ / LiveDesign REST API）：
      POST /projects/{project}/jobs          — 提交任务
      GET  /jobs/{job_id}                    — 查询状态
      GET  /jobs/{job_id}/results            — 获取结果
      POST /tools/glide/dock                 — Glide 对接（简化入口）
      POST /tools/prepwizard                 — 蛋白预处理（简化入口）
    """

    def __init__(self, config: SchrodingerConfig):
        self.config = config
        self._client: Optional[AsyncClient] = None

    async def _get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── 通用任务管理 ────────────────────────────────────────

    async def get_job_status(self, job_id: str) -> SchrodingerJob:
        """
        查询任务状态

        GET /jobs/{job_id}
        Response: { job_id, status, progress, result_url, error }
        """
        client = await self._get_client()
        # TODO: 实际调用
        # resp = await client.get(f"/jobs/{job_id}")
        # resp.raise_for_status()
        # data = resp.json()
        # return SchrodingerJob(
        #     job_id=data["job_id"],
        #     status=JobStatus(data["status"]),
        #     progress=data.get("progress", 0),
        #     result_url=data.get("result_url"),
        #     error_message=data.get("error"),
        #     output_files=data.get("output_files", []),
        # )
        logger.debug(f"Schrodinger.get_job_status({job_id}) — stub")
        return SchrodingerJob(job_id=job_id, status=JobStatus.QUEUED)

    async def wait_for_job(
        self, job_id: str, poll_interval: float = 5.0, timeout: float = 3600
    ) -> SchrodingerJob:
        """轮询等待任务完成"""
        import asyncio
        elapsed = 0.0
        while elapsed < timeout:
            job = await self.get_job_status(job_id)
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                return job
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    # ── Glide Dock ──────────────────────────────────────────

    async def submit_glide_dock(self, request: GlideDockRequest) -> SchrodingerJob:
        """
        提交 Glide 对接任务

        POST /tools/glide/dock
        Request body:
        {
            "receptor": "<mae_file_path>",
            "ligands": "<sdf_file_path>",
            "precision": "SP|XP|HTVS",
            "grid": { "center_x": ..., "center_y": ..., "center_z": ..., "inner_box": ..., "outer_box": ... },
            "num_poses": 10,
            "post_docking_minimize": true,
            "job_name": "..."
        }
        Response: { "job_id": "...", "status": "queued" }
        """
        client = await self._get_client()

        payload: dict[str, Any] = {
            "receptor": request.receptor_file,
            "ligands": request.ligands_file,
            "precision": request.precision.value,
            "num_poses": request.num_poses,
            "post_docking_minimize": request.post_docking_minimize,
            "max_lig_molecular_weight": request.max_lmw,
            "max_rotatable_bonds": request.max_rotatable_bonds,
        }
        if request.grid:
            grid_data: dict[str, Any] = {}
            if request.grid.ligand_file:
                grid_data["ligand"] = request.grid.ligand_file
            if request.grid.center_x is not None:
                grid_data["center_x"] = request.grid.center_x
                grid_data["center_y"] = request.grid.center_y
                grid_data["center_z"] = request.grid.center_z
            grid_data["inner_box"] = request.grid.inner_box
            grid_data["outer_box"] = request.grid.outer_box
            payload["grid"] = grid_data
        if request.job_name:
            payload["job_name"] = request.job_name
        if request.project_name:
            payload["project_name"] = request.project_name

        # TODO: 实际调用
        # resp = await client.post("/tools/glide/dock", json=payload)
        # resp.raise_for_status()
        # data = resp.json()
        # return SchrodingerJob(job_id=data["job_id"], status=JobStatus(data["status"]))
        logger.info(f"Schrodinger.submit_glide_dock — stub, precision={request.precision.value}")
        return SchrodingerJob(job_id="glide-stub-001", status=JobStatus.QUEUED)

    async def get_glide_dock_result(self, job_id: str) -> GlideDockResult:
        """
        获取 Glide 对接结果

        GET /jobs/{job_id}/results
        Response: { output_file, num_hits, best_score, ... }
        """
        # 先查状态
        job = await self.get_job_status(job_id)
        if job.status != JobStatus.COMPLETED:
            return GlideDockResult(job_id=job_id, status=job.status)

        client = await self._get_client()
        # TODO: 实际调用
        # resp = await client.get(f"/jobs/{job_id}/results")
        # resp.raise_for_status()
        # data = resp.json()
        # return GlideDockResult(...)
        logger.info(f"Schrodinger.get_glide_dock_result({job_id}) — stub")
        return GlideDockResult(job_id=job_id, status=JobStatus.COMPLETED)

    async def run_glide_dock(
        self, request: GlideDockRequest, poll_interval: float = 10.0
    ) -> GlideDockResult:
        """一站式 Glide 对接：提交 → 等待 → 获取结果"""
        job = await self.submit_glide_dock(request)
        completed = await self.wait_for_job(job.job_id, poll_interval=poll_interval)
        return await self.get_glide_dock_result(completed.job_id)

    # ── Protein Preparation Wizard ──────────────────────────

    async def submit_prepwizard(self, request: PrepWizardRequest) -> SchrodingerJob:
        """
        提交 Protein Preparation Wizard 任务

        POST /tools/prepwizard
        Request body:
        {
            "input_structure": "<pdb_or_mae_path>",
            "steps": ["preprocess", "het_states", "optimize_h", "minimize"],
            "ph_range": [5.0, 9.0],
            "fill_loops": false,
            "fill_side_chains": true,
            "force_field": "OPLS4",
            "max_iterations": 1000,
            "converge_rms": 0.01,
            "job_name": "..."
        }
        Response: { "job_id": "...", "status": "queued" }
        """
        client = await self._get_client()

        payload: dict[str, Any] = {
            "input_structure": request.input_structure,
            "steps": [s.value for s in request.steps],
            "ph_range": [request.ph_range_low, request.ph_range_high],
            "fill_loops": request.fill_loops,
            "fill_side_chains": request.fill_side_chains,
            "force_field": request.force_field,
            "max_iterations": request.max_iterations,
            "converge_rms": request.converge_rms,
        }
        if request.job_name:
            payload["job_name"] = request.job_name
        if request.project_name:
            payload["project_name"] = request.project_name

        # TODO: 实际调用
        # resp = await client.post("/tools/prepwizard", json=payload)
        # resp.raise_for_status()
        # data = resp.json()
        # return SchrodingerJob(job_id=data["job_id"], status=JobStatus(data["status"]))
        logger.info("Schrodinger.submit_prepwizard — stub")
        return SchrodingerJob(job_id="prepwiz-stub-001", status=JobStatus.QUEUED)

    async def get_prepwizard_result(self, job_id: str) -> PrepWizardResult:
        """获取 Protein Prep 结果"""
        job = await self.get_job_status(job_id)
        if job.status != JobStatus.COMPLETED:
            return PrepWizardResult(job_id=job_id, status=job.status)

        # TODO: 实际调用
        logger.info(f"Schrodinger.get_prepwizard_result({job_id}) — stub")
        return PrepWizardResult(job_id=job_id, status=JobStatus.COMPLETED)

    async def run_prepwizard(
        self, request: PrepWizardRequest, poll_interval: float = 10.0
    ) -> PrepWizardResult:
        """一站式 Protein Prep：提交 → 等待 → 获取结果"""
        job = await self.submit_prepwizard(request)
        completed = await self.wait_for_job(job.job_id, poll_interval=poll_interval)
        return await self.get_prepwizard_result(completed.job_id)

    # ── 健康检查 ────────────────────────────────────────────

    async def health(self) -> dict:
        """
        GET /health 或 /status
        检查 API 连通性和许可证状态
        """
        client = await self._get_client()
        # TODO: 实际调用
        # resp = await client.get("/health")
        # return resp.json()
        logger.debug("Schrodinger.health — stub")
        return {"status": "stub", "api_reachable": False, "license_valid": False}


def get_schrodinger_client(config: SchrodingerConfig) -> SchrodingerClient:
    return SchrodingerClient(config)
