"""Competition requirement parser."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from masld_agent.config import SCOPE_WARNING, load_competition_config
from masld_agent.models import CompetitionProfile, DiseaseScope, EvidenceLevel


def parse_competition(
    config_path: Optional[Path] = None,
    *,
    disease: DiseaseScope = DiseaseScope.MASLD,
) -> CompetitionProfile:
    cfg = load_competition_config(config_path)
    warning = cfg.get("competition_scope_warning") or SCOPE_WARNING
    return CompetitionProfile(
        source="competition_config",
        retrieved_at=datetime.now(timezone.utc),
        evidence_level=EvidenceLevel.A,
        confidence=0.9,
        warnings=[warning],
        provenance={"config_keys": list(cfg.keys())},
        competition_url=cfg.get("competition_url", ""),
        competition_name=cfg.get("competition_name", "AI4S Life Science"),
        disease_default=DiseaseScope(cfg.get("disease_default", "MASLD")),
        disease_active=disease,
        scraped_at=datetime.now(timezone.utc),
        verbatim_excerpts=list(cfg.get("verbatim_excerpts") or []),
        scope_conflicts=list(cfg.get("scope_conflicts") or []),
        competition_scope_warning=warning,
        hard_constraints=dict(cfg.get("hard_constraints") or {}),
        structured={
            "agent_role": cfg.get("agent_role"),
            "mechanisms_of_interest": cfg.get("mechanisms_of_interest"),
            "hermes_eval_mode": cfg.get("hermes_eval_mode"),
            "compound_nomination_pipeline": cfg.get("compound_nomination_pipeline"),
            "scoring_dimensions": cfg.get("scoring_dimensions"),
            "submission_artifacts": cfg.get("submission_artifacts"),
            "experimental_readouts": cfg.get("experimental_readouts"),
            "resources": cfg.get("resources"),
            "schedule_notes": cfg.get("schedule_notes"),
            "top10_csv_columns": cfg.get("top10_csv_columns"),
        },
    )
