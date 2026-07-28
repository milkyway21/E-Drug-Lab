"""Transparent, configurable target scoring (no LLM-assigned finals)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from masld_agent.models import NoveltyClass, ScoreBreakdown


DEFAULT_WEIGHTS: dict[str, float] = {
    "human_genetics_evidence": 0.20,
    "disease_mechanism_relevance": 0.15,
    "hepatocyte_or_liver_specificity": 0.10,
    "druggability": 0.15,
    "structure_availability": 0.10,
    "ligand_precedent": 0.10,
    "safety_rationale": 0.10,
    "novelty": 0.10,
}


def load_weights(path: Optional[Path] = None) -> dict[str, float]:
    if path is None or not path.exists():
        return dict(DEFAULT_WEIGHTS)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    weights = data.get("weights", data)
    out = dict(DEFAULT_WEIGHTS)
    for k, v in weights.items():
        if k in out and v is not None:
            out[k] = float(v)
    s = sum(out.values())
    if abs(s - 1.0) > 1e-6 and s > 0:
        out = {k: v / s for k, v in out.items()}
    return out


def novelty_score_from_class(cls: NoveltyClass) -> float:
    return {
        NoveltyClass.NOVEL: 0.9,
        NoveltyClass.EMERGING: 0.55,
        NoveltyClass.ESTABLISHED: 0.2,
    }[cls]


def score_target(
    *,
    dimension_scores: dict[str, Optional[float]],
    weights: Optional[dict[str, float]] = None,
    sources: Optional[dict[str, list[str]]] = None,
) -> ScoreBreakdown:
    """Missing dimensions are None and excluded from renormalized total (never treated as 1.0)."""
    w = weights or DEFAULT_WEIGHTS
    missing: list[str] = []
    present_w = 0.0
    weighted = 0.0
    cleaned: dict[str, Optional[float]] = {}

    for dim, weight in w.items():
        val = dimension_scores.get(dim)
        if val is None:
            missing.append(dim)
            cleaned[dim] = None
            continue
        v = max(0.0, min(1.0, float(val)))
        cleaned[dim] = v
        present_w += weight
        weighted += weight * v

    total: Optional[float] = None
    if present_w > 0:
        total = weighted / present_w

    return ScoreBreakdown(
        human_genetics_evidence=cleaned.get("human_genetics_evidence"),
        disease_mechanism_relevance=cleaned.get("disease_mechanism_relevance"),
        hepatocyte_or_liver_specificity=cleaned.get("hepatocyte_or_liver_specificity"),
        druggability=cleaned.get("druggability"),
        structure_availability=cleaned.get("structure_availability"),
        ligand_precedent=cleaned.get("ligand_precedent"),
        safety_rationale=cleaned.get("safety_rationale"),
        novelty=cleaned.get("novelty"),
        total=total,
        missing_dimensions=missing,
        sources=sources or {},
    )


def classify_novelty(
    *,
    has_approved_drug: bool,
    has_late_clinical: bool,
    has_early_clinical_or_strong_preclinical: bool,
) -> NoveltyClass:
    if has_approved_drug or has_late_clinical:
        return NoveltyClass.ESTABLISHED
    if has_early_clinical_or_strong_preclinical:
        return NoveltyClass.EMERGING
    return NoveltyClass.NOVEL


def as_plain_dict(breakdown: ScoreBreakdown) -> dict[str, Any]:
    return breakdown.model_dump()
