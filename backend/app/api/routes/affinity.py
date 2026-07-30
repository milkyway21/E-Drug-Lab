"""
亲和力评估路由
- /docking/vina          — AutoDock Vina 1.2.x 对接
- /docking/glide         — 薛定谔 Glide Dock（HTVS/SP/XP，本地 subprocess）
- /schrodinger/status    — 本地 Schrödinger 健康检查
- /schrodinger/dock      — 流水线 SMILES 批量 Glide (+ 可选 MM-GBSA)
- /mmgbsa                — Prime MM-GBSA 重打分
- /md                    — Schrödinger Desmond MD（dry_prep 默认；生产需 confirm）
- /md/{task_id}          — Desmond MD 任务状态
"""
import asyncio
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.errors import AppError
from app.core.paths import ensure_safe_path
from app.services.job_store import job_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/affinity", tags=["Affinity"])
SCHRODINGER_WORK_DIR = Path("data/schrodinger")


def _safe_file(path: str, *, must_exist: bool = True) -> str:
    return str(ensure_safe_path(path, must_exist=must_exist))


# ── Pydantic 模型 ──────────────────────────────────────────

class VinaBoxRequest(BaseModel):
    """对接口袋定义"""
    center_x: float = Field(..., description="口袋中心 X 坐标 (Å)")
    center_y: float = Field(..., description="口袋中心 Y 坐标 (Å)")
    center_z: float = Field(..., description="口袋中心 Z 坐标 (Å)")
    size_x: float = Field(default=20.0, ge=1.0, le=100.0, description="口袋 X 方向大小 (Å)")
    size_y: float = Field(default=20.0, ge=1.0, le=100.0, description="口袋 Y 方向大小 (Å)")
    size_z: float = Field(default=20.0, ge=1.0, le=100.0, description="口袋 Z 方向大小 (Å)")


class VinaDockRequest(BaseModel):
    """AutoDock Vina 对接请求"""
    receptor_path: str = Field(..., description="受体 PDBQT 文件路径")
    ligand_path: str = Field(..., description="配体 PDBQT 文件路径")
    box: VinaBoxRequest
    exhaustiveness: int = Field(default=8, ge=1, le=256, description="搜索穷尽度")
    num_modes: int = Field(default=10, ge=1, le=100, description="输出构象数")
    energy_range: float = Field(default=3.0, ge=0.1, le=10.0, description="能量范围 (kcal/mol)")
    cpu: int = Field(default=0, ge=0, description="CPU 核心数（0=自动）")
    seed: int = Field(default=0, ge=0, description="随机种子（0=随机）")


class VinaBatchRequest(BaseModel):
    """Vina 批量对接请求"""
    receptor_path: str = Field(..., description="受体 PDBQT 文件路径")
    ligand_paths: list[str] = Field(..., min_length=1, max_length=1000, description="配体 PDBQT 文件路径列表")
    box: VinaBoxRequest
    exhaustiveness: int = Field(default=8, ge=1, le=256)
    num_modes: int = Field(default=10, ge=1, le=100)
    energy_range: float = Field(default=3.0, ge=0.1, le=10.0)
    cpu: int = Field(default=0, ge=0)
    concurrency: int = Field(default=4, ge=1, le=16, description="并发任务数")


class GlideDockRequest(BaseModel):
    """Glide Dock 对接请求"""
    receptor_file: str = Field(..., description="受体 PDB 或 Maestro (.mae/.maegz) 路径")
    ligands_file: str = Field(..., description="配体库文件路径 (.sdf/.mae)")
    precision: str = Field(default="SP", description="对接精度: HTVS / SP / XP")
    center_x: Optional[float] = Field(default=None, description="口袋中心 X")
    center_y: Optional[float] = Field(default=None, description="口袋中心 Y")
    center_z: Optional[float] = Field(default=None, description="口袋中心 Z")
    inner_box: float = Field(default=10.0, description="内框大小 (Å)")
    outer_box: float = Field(default=20.0, description="外框大小 (Å)")
    num_poses: int = Field(default=10, ge=1, le=100)
    postdock_minimize: bool = Field(default=True, description="对接后最小化")
    ph: float = Field(default=7.2, ge=0.0, le=14.0)
    ph_threshold: float = Field(default=0.2, ge=0.0, le=2.0)
    job_name: Optional[str] = None


class MmgbsaRequest(BaseModel):
    """Prime MM-GBSA 请求"""
    pose_maegz: Optional[str] = Field(default=None, description="Glide pose .maegz 路径")
    receptor_maegz: Optional[str] = Field(default=None, description="受体 .maegz（receptor-ligand 模式更准）")
    trajectory_path: Optional[str] = Field(default=None, description="兼容旧字段：同 pose_maegz")
    topology_path: Optional[str] = Field(default=None, description="保留字段")
    receptor_mask: str = Field(default=":1-9999", description="保留字段")
    ligand_mask: str = Field(default=":LIG", description="保留字段")


class SchrodingerPipelineLigand(BaseModel):
    molecule_id: str
    smiles: str
    name: Optional[str] = None


class SchrodingerPipelineDockRequest(BaseModel):
    """流水线友好：SMILES 批量 → Glide (+ 可选 MM-GBSA)"""
    molecules: list[SchrodingerPipelineLigand] = Field(..., min_length=1, max_length=200)
    target_id: Optional[str] = None
    target_pdb_id: Optional[str] = None
    receptor_path: Optional[str] = None
    precision: str = Field(default="SP", description="HTVS / SP / XP")
    ph: float = Field(default=7.2, ge=0.0, le=14.0)
    ph_threshold: float = Field(default=0.2, ge=0.0, le=2.0)
    center_x: Optional[float] = None
    center_y: Optional[float] = None
    center_z: Optional[float] = None
    outer_box: int = Field(default=20, ge=10, le=40, description="对接盒边长 (Å)")
    poses_per_lig: int = Field(default=5, ge=1, le=50)
    postdock_minimize: bool = True
    run_mmgbsa: bool = Field(default=False, description="Glide 完成后自动跑 Prime MM-GBSA")
    async_run: bool = Field(default=True, description="后台异步执行（推荐）")


class MdSimulationRequest(BaseModel):
    """Schrödinger Desmond MD 请求。

    默认 mode=dry_prep：只检查环境并写 job_dir/msj，不提交生产 MD。
    mode=smoke|short 需 confirm=true 才会调用 multisim。
    """
    structure_path: Optional[str] = Field(default=None, description="复合物 .cms/.mae/.maegz 路径")
    mode: str = Field(default="dry_prep", description="dry_prep | smoke | short")
    confirm: bool = Field(default=False, description="smoke/short 真实提交必须为 true")
    simulation_time_ns: Optional[float] = Field(
        default=None, ge=0.01, le=1000.0, description="可选覆盖提示（ns）；协议以 mode 模板为准"
    )
    host: Optional[str] = Field(default=None, description="JobDJ host（默认 localhost）")
    molecule_id: Optional[str] = None
    target_id: Optional[str] = None


# ── 响应模型 ────────────────────────────────────────────────

class VinaPoseResponse(BaseModel):
    """单个对接构象"""
    mode: int
    affinity: float = Field(description="结合亲和力 (kcal/mol)")
    rmsd_lb: float
    rmsd_ub: float


class VinaDockResponse(BaseModel):
    """Vina 对接响应"""
    task_id: str
    status: str
    receptor_path: str
    ligand_path: str
    output_pdbqt: Optional[str] = None
    best_affinity: Optional[float] = None
    poses: list[VinaPoseResponse] = []
    command: list[str] = []
    error: Optional[str] = None


class VinaBatchResponse(BaseModel):
    """Vina 批量对接响应"""
    task_id: str
    status: str
    total: int
    results: list[VinaDockResponse] = []


class GlideDockResponse(BaseModel):
    """Glide Dock 响应"""
    task_id: str
    status: str
    job_id: Optional[str] = None
    message: str = "Glide Dock is not yet configured. Set SCHRODINGER__API_KEY to enable."


# ── 路由 ────────────────────────────────────────────────────

@router.post("/docking/vina", response_model=VinaDockResponse, summary="AutoDock Vina 单分子对接")
async def vina_docking(request: Request, body: VinaDockRequest):
    """
    使用 AutoDock Vina 1.2.x 执行单分子对接。
    需要提供受体和配体的 PDBQT 文件路径以及对接口袋参数。
    """
    tool_manager = request.app.state.tool_manager
    vina_tool = tool_manager.get_tool("autodock_vina")
    if not vina_tool or not vina_tool.is_available:
        raise HTTPException(
            status_code=503,
            detail="AutoDock Vina is not available. Check TOOL__AUTODOCK_VINA path in .env"
        )

    from app.services.vina_service import VinaService, VinaParams, VinaBox

    service = VinaService(tool_manager)
    receptor = _safe_file(body.receptor_path)
    ligand = _safe_file(body.ligand_path)
    params = VinaParams(
        receptor_path=receptor,
        ligand_path=ligand,
        box=VinaBox(
            center_x=body.box.center_x,
            center_y=body.box.center_y,
            center_z=body.box.center_z,
            size_x=body.box.size_x,
            size_y=body.box.size_y,
            size_z=body.box.size_z,
        ),
        exhaustiveness=body.exhaustiveness,
        num_modes=body.num_modes,
        energy_range=body.energy_range,
        cpu=body.cpu,
        seed=body.seed,
    )

    job_id = str(uuid.uuid4())[:8]
    result = await service.run_docking(params, job_id=job_id)

    return VinaDockResponse(
        task_id=job_id,
        status="completed" if result.success else "failed",
        receptor_path=result.receptor_path,
        ligand_path=result.ligand_path,
        output_pdbqt=result.output_pdbqt_path,
        best_affinity=result.best_affinity,
        poses=[VinaPoseResponse(mode=p.mode, affinity=p.affinity, rmsd_lb=p.rmsd_lb, rmsd_ub=p.rmsd_ub) for p in result.poses],
        command=result.command,
        error=result.stderr if not result.success else None,
    )


@router.post("/docking/vina/batch", response_model=VinaBatchResponse, summary="Vina 批量对接")
async def vina_batch_docking(request: Request, body: VinaBatchRequest):
    """
    使用 AutoDock Vina 批量对接多个配体到同一受体。
    """
    tool_manager = request.app.state.tool_manager
    vina_tool = tool_manager.get_tool("autodock_vina")
    if not vina_tool or not vina_tool.is_available:
        raise HTTPException(status_code=503, detail="AutoDock Vina is not available")

    from app.services.vina_service import VinaService, VinaBox

    service = VinaService(tool_manager)
    box = VinaBox(
        center_x=body.box.center_x,
        center_y=body.box.center_y,
        center_z=body.box.center_z,
        size_x=body.box.size_x,
        size_y=body.box.size_y,
        size_z=body.box.size_z,
    )

    task_id = str(uuid.uuid4())[:8]
    receptor = _safe_file(body.receptor_path)
    ligand_paths = [_safe_file(p) for p in body.ligand_paths]
    results = await service.run_batch_docking(
        receptor_path=receptor,
        ligand_paths=ligand_paths,
        box=box,
        concurrency=body.concurrency,
    )

    responses = []
    for r in results:
        responses.append(VinaDockResponse(
            task_id=task_id,
            status="completed" if r.success else "failed",
            receptor_path=r.receptor_path,
            ligand_path=r.ligand_path,
            output_pdbqt=r.output_pdbqt_path,
            best_affinity=r.best_affinity,
            poses=[VinaPoseResponse(mode=p.mode, affinity=p.affinity, rmsd_lb=p.rmsd_lb, rmsd_ub=p.rmsd_ub) for p in r.poses],
            command=r.command,
            error=r.stderr if not r.success else None,
        ))

    return VinaBatchResponse(
        task_id=task_id,
        status="completed",
        total=len(responses),
        results=responses,
    )


@router.post("/docking/glide", summary="Glide Dock 对接（本地 Schrödinger）")
async def glide_docking(request: Request, body: GlideDockRequest):
    """
    薛定谔 Glide 分子对接（HTVS / SP / XP）。
    需本地安装 Schrödinger（默认 /opt/schrodinger2023-3）。
    """
    task_id = str(uuid.uuid4())[:8]
    precision = body.precision.upper().strip()
    if precision not in {"HTVS", "SP", "XP"}:
        precision = "SP"

    try:
        from app.pipelines.vav1_rl.schrodinger_local import (
            glide_grid, glide_dock, parse_glide_xp_scores,
            _compute_pdb_centroid, prepwizard,
        )
        from app.config import get_settings

        s = get_settings().schrodinger
        install_path = s.install_path
        out_dir = SCHRODINGER_WORK_DIR / f"glide_{task_id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        receptor_file = _safe_file(body.receptor_file)
        ligands_file = _safe_file(body.ligands_file)
        receptor_maegz = receptor_file
        if receptor_file.endswith(".pdb"):
            receptor_maegz = str(out_dir / "receptor_prep.maegz")
            r = prepwizard(
                receptor_file, receptor_maegz,
                install_path=install_path, ph=body.ph, ph_threshold=body.ph_threshold,
            )
            if not r.ok:
                return {"task_id": task_id, "status": "failed", "message": f"PrepWizard failed: {r.stderr[-500:]}"}

        if body.center_x is not None:
            box_center = (body.center_x, body.center_y or 0.0, body.center_z or 0.0)
        else:
            box_center = _compute_pdb_centroid(receptor_file)

        grid_zip = str(out_dir / "grid.zip")
        r = glide_grid(
            receptor_maegz, grid_zip, box_center,
            box_size=(int(body.outer_box), int(body.outer_box), int(body.outer_box)),
            install_path=install_path,
        )
        if not r.ok:
            return {"task_id": task_id, "status": "failed", "message": f"Glide grid failed: {r.stderr[-500:]}"}

        pose_maegz = str(out_dir / f"poses_{precision.lower()}.maegz")
        r = glide_dock(
            ligands_file, grid_zip, pose_maegz,
            install_path=install_path, precision=precision,
            poses_per_lig=body.num_poses, postdock_minimize=body.postdock_minimize,
        )
        if not r.ok:
            return {"task_id": task_id, "status": "failed", "message": f"Glide {precision} failed: {r.stderr[-500:]}"}

        scores = parse_glide_xp_scores(pose_maegz, install_path=install_path)
        return {
            "task_id": task_id, "status": "completed", "job_id": str(out_dir),
            "precision": precision,
            "message": f"Glide {precision} finished. {len(scores)} ligands scored.",
            "scores": scores[:50], "pose_maegz": pose_maegz, "grid_zip": grid_zip,
            "receptor_maegz": receptor_maegz,
        }
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Glide local failed: %s", e)
        return {"task_id": task_id, "status": "failed", "message": str(e)}

    return GlideDockResponse(
        task_id=task_id, status="stub", job_id=f"glide-stub-{task_id}",
        message="Glide Dock stub. Install Schrödinger locally for real execution.",
    )


@router.get("/schrodinger/status", summary="薛定谔本地安装状态")
async def schrodinger_status():
    from app.services.schrodinger_service import local_health
    return local_health()


@router.post("/schrodinger/dock", summary="流水线 Schrödinger Glide (+ 可选 MM-GBSA)")
async def schrodinger_pipeline_dock(
    body: SchrodingerPipelineDockRequest,
    db: Session = Depends(get_db),
):
    """SMILES 批量对接：LigPrep → PrepWizard → Glide (HTVS/SP/XP) → 可选 Prime MM-GBSA。"""
    from app.services.schrodinger_service import PipelineLigand, resolve_receptor_for_target, run_pipeline_dock

    try:
        receptor = resolve_receptor_for_target(
            target_id=body.target_id,
            target_pdb_id=body.target_pdb_id,
            receptor_path=body.receptor_path,
            db=db,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    precision = body.precision.upper().strip()
    if precision not in {"HTVS", "SP", "XP"}:
        precision = "SP"

    box_center = None
    if body.center_x is not None:
        box_center = (body.center_x, body.center_y or 0.0, body.center_z or 0.0)

    ligands = [
        PipelineLigand(molecule_id=m.molecule_id, smiles=m.smiles, name=m.name or m.molecule_id)
        for m in body.molecules
    ]
    params = body.model_dump()

    def _execute() -> dict:
        return run_pipeline_dock(
            ligands=ligands,
            receptor_pdb=str(receptor),
            precision=precision,
            ph=body.ph,
            ph_threshold=body.ph_threshold,
            box_center=box_center,
            box_size=(body.outer_box, body.outer_box, body.outer_box),
            poses_per_lig=body.poses_per_lig,
            postdock_minimize=body.postdock_minimize,
            run_mmgbsa=body.run_mmgbsa,
        )

    if not body.async_run:
        return await asyncio.to_thread(_execute)

    job_id = job_store.create("schrodinger_dock", params=params)

    async def _task():
        job_store.update(job_id, status="running", message=f"Glide {precision} in progress")
        try:
            result = await asyncio.to_thread(_execute)
            if result.get("ok") or result.get("molecule_results"):
                job_store.update(job_id, status="completed", progress=1.0, result=result)
            else:
                job_store.update(job_id, status="failed", error=result.get("error") or "Schrödinger dock failed")
        except Exception as exc:
            job_store.update(job_id, status="failed", error=str(exc))

    asyncio.create_task(_task())
    return {"ok": True, "job_id": job_id, "message": f"Schrödinger Glide {precision} started", "precision": precision}


@router.get("/schrodinger/jobs/{job_id}")
async def schrodinger_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/mmgbsa", summary="Prime MM-GBSA 重打分")
async def mmgbsa(body: MmgbsaRequest = MmgbsaRequest()):
    """Prime MM-GBSA 结合自由能（本地 Schrödinger）。"""
    task_id = str(uuid.uuid4())[:8]
    pose_path = body.pose_maegz or body.trajectory_path

    if pose_path and pose_path.endswith((".maegz", ".mae")):
        from app.services.schrodinger_service import run_mmgbsa_on_pose
        result = await asyncio.to_thread(
            run_mmgbsa_on_pose,
            pose_path,
            receptor_maegz=body.receptor_maegz,
        )
        if result.get("ok"):
            return {
                "task_id": task_id, "status": "completed",
                "message": f"Prime MM-GBSA finished. {len(result.get('scores', []))} molecules scored.",
                "scores": result.get("scores", [])[:50],
                "csv_path": result.get("csv_path"),
            }
        return {"task_id": task_id, "status": "failed", "message": result.get("error") or result.get("stderr")}

    return {
        "task_id": task_id, "status": "unavailable",
        "message": "请提供 Glide pose .maegz 路径（pose_maegz），或先运行 /schrodinger/dock 并设置 run_mmgbsa=true。",
    }


@router.post("/md", summary="Schrödinger Desmond MD（dry_prep 默认）")
async def md_simulation(body: MdSimulationRequest = MdSimulationRequest()):
    """提交 / 准备 Desmond MD。

    - 默认 ``mode=dry_prep``：检查 $SCHRODINGER + multisim，写 job_dir + md.msj，**不**提交生产。
    - ``smoke`` / ``short`` 须 ``confirm=true``，否则返回 ``gated``。
    - 缺少 Schrödinger 时返回 ``unavailable``（绝非 stub/假 completed）。
    """
    from app.services.desmond_md_service import submit_desmond_md
    from app.config import get_settings

    structure = None
    if body.structure_path:
        try:
            structure = _safe_file(body.structure_path, must_exist=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    install = get_settings().schrodinger.install_path
    result = await asyncio.to_thread(
        submit_desmond_md,
        structure_path=structure,
        mode=body.mode,
        confirm=body.confirm,
        simulation_time_ns=body.simulation_time_ns,
        host=body.host,
        install_path=install,
        molecule_id=body.molecule_id,
        target_id=body.target_id,
    )
    # Never advertise stub success
    if result.get("status") == "stub":
        result["status"] = "failed"
        result["message"] = "Internal error: stub status is forbidden for Desmond MD"
    return result


@router.get("/md/{task_id}", summary="Desmond MD 任务状态")
async def md_status(task_id: str):
    from app.services.desmond_md_service import get_task

    job = get_task(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"MD task not found: {task_id}")
    return job


@router.get("/docking/vina/version", summary="获取 Vina 版本信息")
async def vina_version(request: Request):
    """返回 AutoDock Vina 版本信息（如果可用）。"""
    from app.services.docking_prep import ensure_vina_tool

    tool_manager = request.app.state.tool_manager
    settings = request.app.state.settings
    ensure_vina_tool(tool_manager, settings.tool_paths.autodock_vina)
    vina_tool = tool_manager.get_tool("autodock_vina")
    if not vina_tool or not vina_tool.is_available:
        return {"available": False, "version": None, "path": None}

    # 使用 async_execute 避免在事件循环中阻塞
    try:
        proc = await tool_manager.async_execute("autodock_vina", ["--version"], timeout=10)
        version = (proc.stdout or "").strip() or (proc.stderr or "").strip() or None
        logger.info(f"Vina version check: rc={proc.returncode}, stdout={repr(proc.stdout[:100])}, version={repr(version)}")
    except Exception as e:
        logger.error(f"Vina version check failed: {e}")
        version = None

    return {
        "available": True,
        "version": version,
        "path": vina_tool.executable_path,
    }


@router.get("/docking/glide/status", summary="Glide / Schrödinger 本地状态")
async def glide_status(request: Request):
    """检查薛定谔本地安装（glide / ligprep / prime_mmgbsa / prepwizard）。"""
    from app.services.schrodinger_service import local_health
    h = local_health()
    return {
        "available": h.get("available", False),
        "local_ok": h.get("ok", False),
        "install_path": h.get("install_path"),
        "tools": h.get("tools", {}),
        "api_key_set": bool(request.app.state.settings.schrodinger.api_key),
        "message": "Schrödinger local ready" if h.get("available") else "Schrödinger not installed or tools missing",
    }


# ── SMILES-based docking (pipeline-friendly) ──────────────────

class SmilesDockRequest(BaseModel):
    smiles: str = Field(..., description="SMILES string of the ligand")
    target_id: Optional[str] = Field(None, description="Target UUID from /targets")
    target_pdb_id: Optional[str] = Field(None, description="PDB ID e.g. 8V1T")
    name: Optional[str] = Field(None, description="Molecule name")
    exhaustiveness: int = Field(default=4, ge=1, le=32)
    timeout: int = Field(default=20, ge=5, le=600, description="Per-molecule timeout (seconds)")


class SmilesDockMoleculeItem(BaseModel):
    molecule_id: str
    smiles: str
    name: Optional[str] = None


class SmilesBatchDockRequest(BaseModel):
    molecules: list[SmilesDockMoleculeItem] = Field(..., min_length=1, max_length=100)
    target_id: Optional[str] = None
    target_pdb_id: Optional[str] = None
    exhaustiveness: int = Field(default=4, ge=1, le=32)
    timeout_per_molecule: int = Field(default=20, ge=5, le=600)
    concurrency: int = Field(default=2, ge=1, le=8)


class SmilesDockResultItem(BaseModel):
    molecule_id: str
    smiles: str
    name: str
    affinity_kcal_mol: Optional[float] = None
    method: str
    model: Optional[str] = None
    success: bool
    error: Optional[str] = None
    poses_count: int = 0


class SmilesDockResponse(BaseModel):
    smiles: str
    target_id: Optional[str] = None
    target_pdb_id: Optional[str] = None
    affinity_kcal_mol: Optional[float] = None
    best_affinity: Optional[float] = None
    method: str
    model: Optional[str] = None
    success: bool
    error: Optional[str] = None
    poses_count: int = 0


class SmilesBatchDockResponse(BaseModel):
    vina_available: bool
    method: str
    total: int
    succeeded: int
    failed: int
    results: list[SmilesDockResultItem]


def _outcome_to_item(outcome) -> SmilesDockResultItem:
    return SmilesDockResultItem(
        molecule_id=outcome.molecule_id,
        smiles=outcome.smiles,
        name=outcome.name,
        affinity_kcal_mol=outcome.affinity_kcal_mol,
        method=outcome.method,
        model=outcome.model,
        success=outcome.success,
        error=outcome.error,
        poses_count=outcome.poses_count,
    )


@router.post("/dock", response_model=SmilesDockResponse, summary="SMILES-based docking (real Vina)")
async def smiles_docking(request: Request, body: SmilesDockRequest, db: Session = Depends(get_db)):
    """
    Pipeline-friendly docking endpoint.
    Runs real AutoDock Vina when available; returns method=unavailable otherwise.
    Never returns property-based estimates labeled as Vina.
    """
    from app.services.docking_prep import (
        SmilesDockItem,
        dock_smiles_batch,
        ensure_vina_tool,
    )

    tool_manager = request.app.state.tool_manager
    settings = request.app.state.settings
    ensure_vina_tool(tool_manager, settings.tool_paths.autodock_vina)

    mol_id = body.name or body.smiles[:16]
    vina_available, batch_method, outcomes = await dock_smiles_batch(
        tool_manager,
        molecules=[SmilesDockItem(molecule_id=mol_id, smiles=body.smiles, name=body.name or mol_id)],
        target_pdb_id=body.target_pdb_id,
        target_id=body.target_id,
        db=db,
        exhaustiveness=body.exhaustiveness,
        timeout_per_molecule=body.timeout,
        concurrency=1,
    )
    outcome = outcomes[0]
    return SmilesDockResponse(
        smiles=body.smiles,
        target_id=body.target_id,
        target_pdb_id=body.target_pdb_id,
        affinity_kcal_mol=outcome.affinity_kcal_mol,
        best_affinity=outcome.affinity_kcal_mol,
        method=outcome.method if vina_available else batch_method,
        model=outcome.model,
        success=outcome.success,
        error=outcome.error,
        poses_count=outcome.poses_count,
    )


@router.post("/dock/batch", response_model=SmilesBatchDockResponse, summary="SMILES batch docking (real Vina)")
async def smiles_batch_docking(request: Request, body: SmilesBatchDockRequest, db: Session = Depends(get_db)):
    """Batch dock pipeline molecules with real Vina. No property-estimate fallback."""
    from app.services.docking_prep import SmilesDockItem, dock_smiles_batch, ensure_vina_tool

    tool_manager = request.app.state.tool_manager
    settings = request.app.state.settings
    ensure_vina_tool(tool_manager, settings.tool_paths.autodock_vina)

    items = [
        SmilesDockItem(
            molecule_id=item.molecule_id,
            smiles=item.smiles,
            name=item.name or item.molecule_id,
        )
        for item in body.molecules
    ]
    vina_available, batch_method, outcomes = await dock_smiles_batch(
        tool_manager,
        molecules=items,
        target_pdb_id=body.target_pdb_id,
        target_id=body.target_id,
        db=db,
        exhaustiveness=body.exhaustiveness,
        timeout_per_molecule=body.timeout_per_molecule,
        concurrency=body.concurrency,
    )
    succeeded = sum(1 for o in outcomes if o.success)
    return SmilesBatchDockResponse(
        vina_available=vina_available,
        method=batch_method if vina_available else "unavailable",
        total=len(outcomes),
        succeeded=succeeded,
        failed=len(outcomes) - succeeded,
        results=[_outcome_to_item(o) for o in outcomes],
    )
