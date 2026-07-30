"""Candidate ranking routes."""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.workflow_steps import PIPELINE_STEP_RANKING
from app.repositories.models import CandidateMolecule, ScreeningTask, Target
from app.services.orthogonal_scoring import (
    CandidateScoreInput,
    MetricObservation,
    rank_by_orthogonal_rescore,
)
from app.services.xlsx_report import build_xlsx_bytes

router = APIRouter(prefix="/api/v1/ranking", tags=["Ranking"])
REPORT_DIR = Path("outputs/ranking_reports")


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


class MoleculePersistenceRecord(BaseModel):
    molecule_id: str
    name: str | None = None
    smiles: str | None = None
    source: str | None = None
    source_db_id: str | None = None
    status: str | None = None
    sa_score: float | None = None
    molecular_weight: float | None = None
    logp: float | None = None
    tpsa: float | None = None
    qed: float | None = None
    herg: float | None = None
    dili: float | None = None
    ames: float | None = None
    hia: float | None = None
    docking_affinity: float | None = None
    step_results: dict[str, Any] = Field(default_factory=dict)


class OrthogonalRescoreRequest(BaseModel):
    candidates: list[CandidateRankingRequest]
    primary_metric: str = "docking_score"
    orthogonal_metric: str = "orthogonal_score"
    preferred_primary_models: list[str] = Field(default_factory=list)
    preferred_orthogonal_models: list[str] = Field(default_factory=list)
    gap_threshold: float = Field(default=35.0, ge=0, le=100)
    target_id: str | None = None
    target_pdb_id: str | None = None
    library_id: str | None = None
    molecule_records: list[MoleculePersistenceRecord] = Field(default_factory=list)


def _normalize_source_label(source: str | None) -> str:
    if not source:
        return "workflow"
    compact = re.sub(r"[^a-z0-9]+", "", source.lower())
    return compact or "workflow"


def _format_score_token(score: float | None) -> str:
    if score is None:
        return "0p00"
    rounded = f"{score:.2f}"
    negative = "m" if rounded.startswith("-") else ""
    numeric = rounded.lstrip("-").replace(".", "p")
    return f"{negative}{numeric}"


def _build_standard_name(
    pdb_id: str | None,
    final_score: float | None,
    source: str | None,
    timestamp: datetime,
) -> str:
    prefix = (pdb_id or "unknown").strip().lower() or "unknown"
    return f"{prefix}_{_format_score_token(final_score)}_{_normalize_source_label(source)}_{timestamp.strftime('%Y%m%d%H%M')}"


def _resolve_target_pdb_id(db: Session, body: OrthogonalRescoreRequest) -> str | None:
    if body.target_pdb_id:
        return body.target_pdb_id
    if not body.target_id:
        return None
    target = db.query(Target).filter(Target.id == body.target_id).first()
    return target.pdb_id if target else None


def _is_excellent_molecule(row: dict[str, Any]) -> bool:
    herg = row.get("hERG")
    dili = row.get("DILI")
    ames = row.get("AMES")
    hia = row.get("HIA")
    docking = row.get("docking_affinity")
    final_score = row.get("final_score")
    qed = row.get("qed")
    sa_score = row.get("sa_score")
    artifact_flag = row.get("artifact_flag")

    return bool(
        herg is not None and herg <= 0.3 and
        dili is not None and dili <= 0.3 and
        ames is not None and ames <= 0.3 and
        hia is not None and hia >= 0.7 and
        docking is not None and docking <= -7.0 and
        final_score is not None and final_score >= 70 and
        qed is not None and qed >= 0.67 and
        sa_score is not None and sa_score <= 3.0 and
        not artifact_flag
    )


def _build_report_rows(
    ranked: list[Any],
    records_by_id: dict[str, MoleculePersistenceRecord],
    target_pdb_id: str | None,
    generated_at: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for position, item in enumerate(ranked, start=1):
        source = records_by_id.get(item.molecule_id)
        standard_name = _build_standard_name(
            target_pdb_id,
            item.final_score,
            source.source if source else None,
            generated_at,
        )
        rows.append(
            {
                "rank": position,
                "molecule_id": item.molecule_id,
                "name": item.name,
                "original_name": item.name,
                "standard_name": standard_name,
                "smiles": source.smiles if source else None,
                "source": source.source if source else None,
                "source_db_id": source.source_db_id if source else None,
                "status": source.status if source else None,
                "molecular_weight": source.molecular_weight if source else None,
                "logp": source.logp if source else None,
                "tpsa": source.tpsa if source else None,
                "qed": source.qed if source else None,
                "sa_score": source.sa_score if source else None,
                "hERG": source.herg if source else None,
                "DILI": source.dili if source else None,
                "AMES": source.ames if source else None,
                "HIA": source.hia if source else None,
                "docking_affinity": source.docking_affinity if source else item.primary_value,
                "primary_value": item.primary_value,
                "orthogonal_value": item.orthogonal_value,
                "primary_desirability": item.primary_desirability,
                "orthogonal_desirability": item.orthogonal_desirability,
                "consistency_gap": item.consistency_gap,
                "final_score": item.final_score,
                "artifact_flag": item.artifact_flag,
                "artifact_reason": item.artifact_reason,
                "selected_primary_model": item.selected_primary_model,
                "selected_orthogonal_model": item.selected_orthogonal_model,
                "step_results": source.step_results if source else {},
            }
        )
    return rows


def _write_report(task: ScreeningTask, rows: list[dict[str, Any]]) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"candidate-ranking-{task.id}.xlsx"

    excellent_rows = [row for row in rows if _is_excellent_molecule(row)]
    top_count = max(1, math.ceil(len(rows) * 0.1)) if rows else 0
    top_rows = rows[:top_count]
    artifact_count = sum(1 for row in rows if row["artifact_flag"])
    admet_pass_count = sum(1 for row in rows if row.get("status") != "fail")

    overall_sheet = [
        ["Metric", "Value"],
        ["Report generated at", datetime.now().isoformat()],
        ["Total molecules", len(rows)],
        ["Excellent molecules", len(excellent_rows)],
        ["Top 10% count", len(top_rows)],
        ["Artifact-flagged molecules", artifact_count],
        ["ADMET pass or pending molecules", admet_pass_count],
        ["Average final score", round(sum(row["final_score"] for row in rows) / len(rows), 4) if rows else None],
        ["Average docking affinity", round(sum(row["docking_affinity"] for row in rows if row["docking_affinity"] is not None) / max(1, sum(1 for row in rows if row["docking_affinity"] is not None)), 4) if rows else None],
        ["Excellent criteria", "hERG<=0.3; DILI<=0.3; AMES<=0.3; HIA>=0.7; docking<=-7.0; final_score>=70; QED>=0.67; SA<=3.0; no artifact"],
    ]

    table_headers = [
        "rank", "molecule_id", "standard_name", "original_name", "smiles", "source", "source_db_id", "status",
        "molecular_weight", "logp", "tpsa", "qed", "sa_score", "hERG", "DILI", "AMES", "HIA",
        "docking_affinity", "primary_value", "orthogonal_value", "primary_desirability",
        "orthogonal_desirability", "consistency_gap", "final_score", "artifact_flag",
        "artifact_reason", "selected_primary_model", "selected_orthogonal_model",
    ]

    def make_sheet(row_items: list[dict[str, Any]]) -> list[list[object]]:
        return [table_headers] + [[row.get(header) for header in table_headers] for row in row_items]

    workbook = build_xlsx_bytes(
        [
            ("overall_analysis", overall_sheet),
            ("all_molecules", make_sheet(rows)),
            ("excellent_molecules", make_sheet(excellent_rows)),
            ("top_10_percent", make_sheet(top_rows)),
        ]
    )
    report_path.write_bytes(workbook)
    return str(report_path.resolve())


def _persist_ranking_run(
    db: Session,
    body: OrthogonalRescoreRequest,
    rows: list[dict[str, Any]],
) -> tuple[str, int, str]:
    task = ScreeningTask(
        target_id=body.target_id,
        library_id=body.library_id,
        tool_name="orthogonal-rank",
        task_type="candidate_ranking",
        status="completed",
        progress=100.0,
        params={
            "primary_metric": body.primary_metric,
            "orthogonal_metric": body.orthogonal_metric,
            "gap_threshold": body.gap_threshold,
            "preferred_primary_models": body.preferred_primary_models,
            "preferred_orthogonal_models": body.preferred_orthogonal_models,
        },
        pipeline_step=PIPELINE_STEP_RANKING,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        pipeline_config={
            "total_molecules": len(rows),
            "artifact_count": sum(1 for row in rows if row["artifact_flag"]),
        },
    )
    db.add(task)
    db.flush()

    for row in rows:
        db.add(
            CandidateMolecule(
                task_id=task.id,
                smiles=row.get("smiles") or "",
                name=row.get("original_name"),
                standard_name=row.get("standard_name"),
                docking_score=row.get("primary_value"),
                admet_profile={
                    "hERG": row.get("hERG"),
                    "DILI": row.get("DILI"),
                    "AMES": row.get("AMES"),
                    "HIA": row.get("HIA"),
                    "qed": row.get("qed"),
                    "sa_score": row.get("sa_score"),
                    "status": row.get("status"),
                },
                binding_energy=row.get("docking_affinity"),
                md_stability={
                    "orthogonal_value": row.get("orthogonal_value"),
                    "primary_desirability": row.get("primary_desirability"),
                    "orthogonal_desirability": row.get("orthogonal_desirability"),
                    "consistency_gap": row.get("consistency_gap"),
                    "artifact_flag": row.get("artifact_flag"),
                    "artifact_reason": row.get("artifact_reason"),
                },
                comprehensive_score=row.get("final_score"),
                rank=row.get("rank"),
                generation_source=row.get("source") or "workflow",
                generation_params={
                    "source_db_id": row.get("source_db_id"),
                    "molecule_id": row.get("molecule_id"),
                    "original_name": row.get("original_name"),
                    "standard_name": row.get("standard_name"),
                    "selected_primary_model": row.get("selected_primary_model"),
                    "selected_orthogonal_model": row.get("selected_orthogonal_model"),
                    "step_results": row.get("step_results", {}),
                },
            )
        )

    report_path = _write_report(task, rows)
    task.results_path = report_path
    db.commit()
    return str(task.id), len(rows), report_path


@router.post("/orthogonal-rescore")
async def orthogonal_rescore(body: OrthogonalRescoreRequest, db: Session = Depends(get_db)):
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

    task_id = None
    saved_molecules = 0
    report_download_url = None
    response_ranked = [item.__dict__.copy() for item in ranked]
    if body.molecule_records:
        records_by_id = {record.molecule_id: record for record in body.molecule_records}
        generated_at = datetime.now()
        target_pdb_id = _resolve_target_pdb_id(db, body)
        report_rows = _build_report_rows(ranked, records_by_id, target_pdb_id, generated_at)
        standard_names = {row["molecule_id"]: row["standard_name"] for row in report_rows}
        for item in response_ranked:
            item["standard_name"] = standard_names.get(item["molecule_id"])
        task_id, saved_molecules, _report_path = _persist_ranking_run(db, body, report_rows)
        report_download_url = f"/api/v1/ranking/reports/{task_id}/download"

    return {
        "method": "orthogonal_rescore_v1",
        "selection_rule": "preferred model, otherwise median observed value; never mean",
        "final_score_rule": "orthogonal desirability minus artifact penalty",
        "ranked": response_ranked,
        "task_id": task_id,
        "saved_molecules": saved_molecules,
        "report_download_url": report_download_url,
    }


@router.get("/orthogonal-demo")
async def orthogonal_demo(db: Session = Depends(get_db)):
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
    return await orthogonal_rescore(demo, db)


@router.get("/reports/{task_id}/download")
async def download_ranking_report(task_id: str, db: Session = Depends(get_db)):
    task = db.query(ScreeningTask).filter(ScreeningTask.id == task_id).first()
    if not task or not task.results_path:
        raise HTTPException(status_code=404, detail="Ranking report not found")

    report_path = Path(task.results_path)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Ranking report file is missing")

    return FileResponse(
        report_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=report_path.name,
    )
