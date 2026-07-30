"""湿实验交接 API — 分析候选分子、导出合成订单包。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.wetlab_prep_service import analyze_batch, build_order_pack_xlsx

router = APIRouter(prefix="/api/v1/wetlab", tags=["WetLab"])


class WetlabMoleculeInput(BaseModel):
    smiles: str
    name: Optional[str] = None
    rank: Optional[int] = None


class WetlabAnalyzeRequest(BaseModel):
    molecules: list[WetlabMoleculeInput] = Field(..., min_length=1, max_length=200)
    target_code: str = Field(default="UNK", description="靶点缩写，用于化合物注册号")
    batch_id: str = Field(default="B1", description="批次号")
    check_pubchem: bool = Field(default=True, description="是否查询 PubChem 现货线索")
    dmso_concentration_mm: float = Field(default=10.0, ge=0.1, le=100.0)
    dmso_volume_ml: float = Field(default=1.0, ge=0.1, le=50.0)


class WetlabExportRequest(WetlabAnalyzeRequest):
    target_name: str = ""
    assay_type: str = "BRET / pDC50"
    cell_line: str = ""
    target_protein: str = ""
    round_id: int = 1


@router.post("/analyze")
async def analyze_wetlab(req: WetlabAnalyzeRequest) -> dict[str, Any]:
    """批量分析候选分子的可合成性、结构警报、DMSO 配制与采购线索。"""
    preps = analyze_batch(
        [m.model_dump() for m in req.molecules],
        target_code=req.target_code,
        batch_id=req.batch_id,
        check_pubchem=req.check_pubchem,
        dmso_concentration_mm=req.dmso_concentration_mm,
        dmso_volume_ml=req.dmso_volume_ml,
    )
    ready = sum(1 for p in preps if p.wetlab_ready)
    return {
        "status": "completed",
        "total": len(preps),
        "wetlab_ready": ready,
        "blocked": len(preps) - ready,
        "molecules": [p.to_dict() for p in preps],
    }


@router.post("/export-order-pack")
async def export_order_pack(req: WetlabExportRequest) -> Response:
    """导出多 Sheet XLSX：合成订单 + DMSO 配制 + 活性回填模板 + 检查清单。"""
    preps = analyze_batch(
        [m.model_dump() for m in req.molecules],
        target_code=req.target_code,
        batch_id=req.batch_id,
        check_pubchem=req.check_pubchem,
        dmso_concentration_mm=req.dmso_concentration_mm,
        dmso_volume_ml=req.dmso_volume_ml,
    )
    xlsx_bytes = build_order_pack_xlsx(
        preps,
        target_name=req.target_name,
        assay_type=req.assay_type,
        cell_line=req.cell_line,
        target_protein=req.target_protein,
        round_id=req.round_id,
    )
    filename = f"wetlab_order_pack_r{req.round_id}_{req.target_code}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
