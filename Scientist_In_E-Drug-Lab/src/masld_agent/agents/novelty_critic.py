"""Novelty critic — classify established / emerging / novel."""
from __future__ import annotations

from typing import Any

from masld_agent.models import NoveltyClass
from masld_agent.scoring import classify_novelty


def assess_novelty(meta: dict[str, Any]) -> tuple[NoveltyClass, list[str]]:
    """meta keys: has_approved_drug, has_late_clinical, has_early_clinical_or_strong_preclinical."""
    cls = classify_novelty(
        has_approved_drug=bool(meta.get("has_approved_drug")),
        has_late_clinical=bool(meta.get("has_late_clinical")),
        has_early_clinical_or_strong_preclinical=bool(
            meta.get("has_early_clinical_or_strong_preclinical")
        ),
    )
    warnings: list[str] = []
    if cls == NoveltyClass.ESTABLISHED:
        warnings.append(
            "Do not label as 'new target' — clinical/approved development already exists."
        )
    return cls, warnings


# Offline priors for demo fixtures (transparent, not LLM memory).
OFFLINE_NOVELTY_PRIORS: dict[str, dict[str, bool]] = {
    "HSD17B13": {
        "has_approved_drug": False,
        "has_late_clinical": False,
        "has_early_clinical_or_strong_preclinical": True,
    },
    "KHK": {
        "has_approved_drug": False,
        "has_late_clinical": True,
        "has_early_clinical_or_strong_preclinical": True,
    },
}
