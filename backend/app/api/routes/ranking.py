"""Candidate ranking routes."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.orthogonal_scoring import (
    CandidateScoreInput,
    MetricObservation,
    rank_by_orthogonal_rescore,
)

router = APIRouter(prefix="/api/v1/ranking", tags=["Ranking"])


class MetricObservationRequest(BaseModel):
    metric_name: str
    value: float
    model_name: str
    method_family: str
    direction: str = Field(default="lower_is_better", pattern="^(higher_is_better|lower_is_better)$")
    priority: int = Field(default=100, ge=0)


class CandidateRankingRequest(BaseModel):
    molecule_id: str
    name: str | None = None
    metrics: list[MetricObservationRequest]


class OrthogonalRescoreRequest(BaseModel):
    candidates: list[CandidateRankingRequest]
    primary_metric: str = "docking_score"
    orthogonal_metric: str = "orthogonal_score"
    preferred_primary_models: list[str] = Field(default_factory=list)
    preferred_orthogonal_models: list[str] = Field(default_factory=list)
    gap_threshold: float = Field(default=35.0, ge=0, le=100)


@router.post("/orthogonal-rescore")
async def orthogonal_rescore(body: OrthogonalRescoreRequest):
    candidates = [
        CandidateScoreInput(
            molecule_id=item.molecule_id,
            name=item.name,
            metrics=[
                MetricObservation(
                    metric_name=metric.metric_name,
                    value=metric.value,
                    model_name=metric.model_name,
                    method_family=metric.method_family,
                    direction=metric.direction,  # type: ignore[arg-type]
                    priority=metric.priority,
                )
                for metric in item.metrics
            ],
        )
        for item in body.candidates
    ]
    ranked = rank_by_orthogonal_rescore(
        candidates=candidates,
        primary_metric=body.primary_metric,
        orthogonal_metric=body.orthogonal_metric,
        preferred_primary_models=body.preferred_primary_models,
        preferred_orthogonal_models=body.preferred_orthogonal_models,
        gap_threshold=body.gap_threshold,
    )
    return {
        "method": "orthogonal_rescore_v1",
        "selection_rule": "preferred model, otherwise median observed value; never mean",
        "final_score_rule": "orthogonal desirability minus artifact penalty",
        "ranked": [item.__dict__ for item in ranked],
    }


@router.get("/orthogonal-demo")
async def orthogonal_demo():
    demo = OrthogonalRescoreRequest(
        candidates=[
            CandidateRankingRequest(
                molecule_id="aspirin",
                name="Aspirin",
                metrics=[
                    MetricObservationRequest(metric_name="docking_score", value=-7.1, model_name="vina", method_family="empirical_docking"),
                    MetricObservationRequest(metric_name="docking_score", value=-6.8, model_name="gnina", method_family="cnn_docking"),
                    MetricObservationRequest(metric_name="orthogonal_score", value=-28.0, model_name="mmgbsa", method_family="physics_rescore"),
                ],
            ),
            CandidateRankingRequest(
                molecule_id="ibuprofen",
                name="Ibuprofen",
                metrics=[
                    MetricObservationRequest(metric_name="docking_score", value=-7.4, model_name="vina", method_family="empirical_docking"),
                    MetricObservationRequest(metric_name="docking_score", value=-7.0, model_name="gnina", method_family="cnn_docking"),
                    MetricObservationRequest(metric_name="orthogonal_score", value=-31.0, model_name="mmgbsa", method_family="physics_rescore"),
                ],
            ),
            CandidateRankingRequest(
                molecule_id="artifact-001",
                name="Potential scoring artifact",
                metrics=[
                    MetricObservationRequest(metric_name="docking_score", value=-11.5, model_name="vina", method_family="empirical_docking"),
                    MetricObservationRequest(metric_name="docking_score", value=-5.9, model_name="gnina", method_family="cnn_docking"),
                    MetricObservationRequest(metric_name="orthogonal_score", value=-9.0, model_name="mmgbsa", method_family="physics_rescore"),
                ],
            ),
        ]
    )
    return await orthogonal_rescore(demo)
