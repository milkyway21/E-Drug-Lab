"""RL closed-loop pipeline API routes (legacy path prefix /api/v1/vav1-rl).

端点：
- POST /api/v1/vav1-rl/run          启动全流程（async job）
- GET  /api/v1/vav1-rl/status/{job_id}
- POST /api/v1/vav1-rl/steps/{step}/run   单步验证
- GET  /api/v1/vav1-rl/funnel               当前漏斗计数
- GET  /api/v1/vav1-rl/artifacts             列出 project_root 产物
- GET  /api/v1/vav1-rl/report                最终报告路径
- GET  /api/v1/vav1-rl/health                各模块健康（Schrödinger/GLARE GNN/ADMET）
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.core.paths import ensure_safe_path
from app.pipelines.vav1_rl.orchestrator import VAV1RLOrchestrator
from app.services.job_store import job_store

router = APIRouter(prefix="/api/v1/vav1-rl", tags=["RL-Pipeline"])

# 进程级单例：保存最近一次 orchestrator 实例（供 status/funnel 查询）
_LAST_ORCH: Optional[VAV1RLOrchestrator] = None


class RunRequest(BaseModel):
    mode: str = Field(default="test", description="test | full")
    num_mols: int = Field(default=1000, ge=1)
    reuse_sdf_dir: Optional[str] = None
    project_root: Optional[str] = None
    steps: Optional[list[int]] = Field(
        default=None,
        description="指定步骤子集；None=默认跳过 step9（相似搜索已移除）",
    )

def _get_orch(req: Optional[RunRequest] = None) -> VAV1RLOrchestrator:
    global _LAST_ORCH
    if req and req.project_root:
        safe_root = str(ensure_safe_path(req.project_root, must_exist=False))
        _LAST_ORCH = VAV1RLOrchestrator(
            project_root=safe_root, mode=req.mode, num_mols=req.num_mols, reuse_sdf_dir=req.reuse_sdf_dir
        )
    elif req:
        _LAST_ORCH = VAV1RLOrchestrator(mode=req.mode, num_mols=req.num_mols, reuse_sdf_dir=req.reuse_sdf_dir)
    elif _LAST_ORCH is None:
        _LAST_ORCH = VAV1RLOrchestrator(mode="test")
    return _LAST_ORCH


@router.post("/run")
async def run_pipeline(body: RunRequest):
    """启动全流程（异步 job）。"""
    orch = _get_orch(body)
    job_id = job_store.create("vav1_rl_pipeline", params=body.model_dump())

    async def _task():
        job_store.update(job_id, status="running")
        try:
            # 在线程里跑（pandas/RDKit/PyTorch 阻塞调用）
            results = await asyncio.to_thread(orch.run_all, body.steps)
            job_store.update(job_id, status="completed", result={"steps": results, "funnel": orch.funnel, "status": orch.status})
        except Exception as exc:
            job_store.update(job_id, status="failed", error=str(exc))

    asyncio.create_task(_task())
    return {"ok": True, "job_id": job_id, "mode": body.mode, "num_mols": body.num_mols}


@router.get("/status/{job_id}")
async def pipeline_status(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise AppError(message="Job not found", code="JOB_NOT_FOUND", status_code=404)
    orch = _LAST_ORCH
    job["funnel"] = orch.funnel if orch else {}
    job["current_step"] = orch.status.get("current_step") if orch else None
    return job


@router.post("/steps/{step}/run")
async def run_single_step(step: int, body: RunRequest = RunRequest()):
    """单步验证（同步返回结果）。step ∈ 1..11。"""
    orch = _get_orch(body)
    step_map = {
        1: orch.step1_pretrain, 2: orch.step2_generate, 3: orch.step3_validity_admet,
        4: orch.step4_druglikeness, 5: orch.step5_affinity, 6: orch.step6_dedup,
        7: orch.step7_glare_rank, 8: orch.step8_final_rank, 9: orch.step9_similarity,
        10: orch.step10_rl_train, 11: orch.step11_round2,
    }
    if step not in step_map:
        raise AppError(message=f"Invalid step {step}", code="INVALID_STEP", status_code=400)
    result = await asyncio.to_thread(step_map[step])
    return {"ok": True, "step": step, "result": result, "funnel": orch.funnel.get(step)}


@router.get("/funnel")
async def get_funnel():
    orch = _get_orch()
    return {"funnel": orch.funnel, "status": orch.status}


@router.get("/artifacts")
async def list_artifacts():
    """列出 project_root 下所有产物文件。"""
    orch = _get_orch()
    root = Path(orch.project_root)
    files = []
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                files.append({"path": str(p.relative_to(root)), "size": p.stat().st_size})
    return {"project_root": str(root), "files": files, "count": len(files)}


@router.get("/report")
async def get_report():
    orch = _get_orch()
    report_path = Path(orch.project_root) / "reports" / "final_project_plan_execution_report.md"
    if report_path.is_file():
        return {"ok": True, "report_path": str(report_path), "content": report_path.read_text()}
    return {"ok": False, "report_path": str(report_path), "content": None}


@router.get("/top-molecules")
async def get_top_molecules(limit: int = 20):
    """从 step8 最终排序结果读取 top 分子（供 workflow 导入）。"""
    import csv

    orch = _get_orch()
    root = Path(orch.project_root)
    candidates = [
        root / "screening" / "step8_final_top20.csv",
        root / "screening" / "step8_final_top50.csv",
        root / "screening" / "step8_final_top100.csv",
        root / "screening" / "step8_final_ranked_all.csv",
    ]
    csv_path = next((p for p in candidates if p.is_file()), None)
    if csv_path is None:
        return {"ok": False, "molecules": [], "source": None, "message": "No step8 ranking output found"}

    molecules: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        smiles_key = "generated_smiles" if reader.fieldnames and "generated_smiles" in reader.fieldnames else None
        if not smiles_key and reader.fieldnames:
            for key in reader.fieldnames:
                if "smiles" in key.lower():
                    smiles_key = key
                    break
        if not smiles_key:
            return {"ok": False, "molecules": [], "source": str(csv_path), "message": "No SMILES column in ranking CSV"}

        for idx, row in enumerate(reader):
            if idx >= limit:
                break
            smiles = (row.get(smiles_key) or "").strip()
            if not smiles:
                continue
            name = row.get("name") or row.get("compound_id") or f"rl-top-{idx + 1}"
            mol: dict = {"smiles": smiles, "name": name}
            if row.get("final_score"):
                mol["final_score"] = row.get("final_score")
            molecules.append(mol)

    return {"ok": True, "molecules": molecules, "source": str(csv_path), "count": len(molecules)}


@router.get("/health")
async def health():
    """各核心模块健康检查（每项独立 try/except，单点失败不影响其他）。"""
    from app.pipelines.vav1_rl import schrodinger_local

    # Schrödinger
    try:
        schrod = schrodinger_local.health()
    except Exception as e:
        schrod = {"ok": False, "installed": False, "error": str(e)}

    # GLARE GNN (fast check: conda env exists + import only, no model load)
    try:
        from app.pipelines.vav1_rl import glare_gnn_adapter
        glare = glare_gnn_adapter.smoke_test()
    except Exception as e:
        glare = {"ok": False, "error": str(e)}

    # ADMET-AI
    try:
        from app.services.admet_service import check_health
        admet = check_health()
        # 标准化返回格式（保证 ok 字段）
        if "ok" not in admet:
            admet["ok"] = admet.get("status") == "healthy"
    except Exception as e:
        admet = {"ok": False, "error": str(e)}

    # Vina (轻量检查：查找 autodock_vina 二进制)
    try:
        vina = _vina_health()
    except Exception as e:
        vina = {"ok": False, "available": False, "error": str(e)}

    return {"schrodinger": schrod, "glare_gnn": glare, "admet": admet, "vina": vina}


def _vina_health() -> dict:
    """检查 AutoDock Vina 是否可用。"""
    import shutil
    import subprocess as _sp
    vina_path = shutil.which("vina") or shutil.which("vina1.2.3")
    if not vina_path:
        # 也检查常见安装路径
        for p in ["/usr/bin/vina", "/usr/local/bin/vina", "/opt/vina/vina"]:
            from pathlib import Path
            if Path(p).is_file():
                vina_path = p
                break
    if not vina_path:
        return {"ok": False, "available": False, "path": None, "version": None}
    try:
        proc = _sp.run([vina_path, "--version"], capture_output=True, text=True, timeout=10)
        version = (proc.stdout or proc.stderr).strip().splitlines()[0] if (proc.stdout or proc.stderr) else "unknown"
    except Exception:
        version = "unknown"
    return {"ok": True, "available": True, "path": vina_path, "version": version}
