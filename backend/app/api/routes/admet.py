"""ADMET 预测路由
提供基于 admet-ai 的 ADMET 属性预测和药物相似性规则过滤
"""
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.admet_service import (
    predict_single,
    predict_batch,
    apply_druglikeness_filter,
    check_health,
    ADMET_CATEGORIES,
    PROPERTY_LABELS,
)

router = APIRouter(prefix="/api/v1/admet", tags=["ADMET"])


# ── 请求/响应模型 ──────────────────────────────────────────────

class PredictRequest(BaseModel):
    smiles: list[str] = Field(..., min_length=1, max_length=500, description="SMILES 列表")
    names: Optional[list[str]] = Field(default=None, description="分子名称列表（可选）")


class SinglePredictRequest(BaseModel):
    smiles: str = Field(..., description="单个 SMILES 字符串")
    name: Optional[str] = Field(default=None, description="分子名称（可选）")


class FilterRequest(BaseModel):
    smiles: list[str] = Field(..., min_length=1, max_length=500, description="SMILES 列表")
    rules: list[str] = Field(
        default=["lipinski", "veber", "pains"],
        description="要应用的规则: lipinski, veber, pains",
    )
    names: Optional[list[str]] = Field(default=None, description="分子名称列表（可选）")


# ── 路由 ──────────────────────────────────────────────────────

@router.post("/predict")
async def predict_admet(req: PredictRequest):
    """
    批量 ADMET 属性预测
    返回每个分子的 22+ ADMET 属性（吸收、分布、代谢、排泄、毒性）
    """
    results = predict_batch(req.smiles, names=req.names)
    return {
        "status": "completed",
        "count": len(results),
        "predictions": [r.to_dict() for r in results],
    }


@router.post("/predict/single")
async def predict_admet_single(req: SinglePredictRequest):
    """
    单分子 ADMET 属性预测
    """
    result = predict_single(req.smiles, name=req.name)
    return {
        "status": "completed",
        "prediction": result.to_dict(),
    }


@router.post("/filter")
async def filter_admet(req: FilterRequest):
    """
    药物相似性规则过滤
    支持 Lipinski RO5、Veber、PAINS 规则
    """
    results = apply_druglikeness_filter(
        req.smiles, rules=req.rules, names=req.names,
    )
    passed = sum(1 for r in results if r.passed)
    return {
        "status": "completed",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": [r.to_dict() for r in results],
    }


@router.get("/health")
async def admet_health():
    """ADMET-AI 服务健康检查"""
    return check_health()


@router.get("/properties")
async def list_properties():
    """列出所有支持的 ADMET 属性"""
    return {
        "categories": ADMET_CATEGORIES,
        "labels": PROPERTY_LABELS,
    }
