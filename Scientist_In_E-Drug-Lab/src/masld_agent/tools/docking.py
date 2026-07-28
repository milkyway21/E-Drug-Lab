"""Optional AutoDock Vina docking — never fabricate scores."""
from __future__ import annotations

import shutil
from typing import Optional

from masld_agent.models import DockingResult, EvidenceLevel


def vina_available() -> bool:
    return shutil.which("vina") is not None


def run_docking(
    *,
    receptor_pdbqt: Optional[str] = None,
    ligand_pdbqt: Optional[str] = None,
    center: Optional[tuple[float, float, float]] = None,
    box_size: tuple[float, float, float] = (20.0, 20.0, 20.0),
    crystal_ligand_pdbqt: Optional[str] = None,
) -> DockingResult:
    if not vina_available():
        return DockingResult(
            source="docking",
            evidence_level=EvidenceLevel.U,
            confidence=0.0,
            warnings=[
                "AutoDock Vina binary not found on PATH",
                "Production docking prefers Schrödinger/e-drug-lab "
                "(masld-agent schrodinger-status | schrodinger-dock); see catalog sz.* / ed.svc.schrodinger",
            ],
            provenance={},
            status="skipped_missing_dependency",
            score=None,
            rmsd_redock=None,
            label="computational_prediction",
            details={
                "reason": "vina_not_installed",
                "preferred_production": "schrodinger_service.run_pipeline_dock",
                "catalog_ids": ["sz.glide_sp", "ed.svc.schrodinger", "ed.svc.vina"],
                "cli_hint": "masld-agent schrodinger-dock --receptor … --smiles … --dry-run",
            },
        )

    # Minimal safe path: require explicit inputs; otherwise fail closed.
    if not (receptor_pdbqt and ligand_pdbqt and center):
        return DockingResult(
            source="docking",
            evidence_level=EvidenceLevel.D,
            confidence=0.0,
            warnings=["docking_inputs_incomplete"],
            provenance={},
            status="failed",
            score=None,
            rmsd_redock=None,
            label="computational_prediction",
            details={"note": "Provide receptor/ligand pdbqt and box center to run Vina"},
        )

    # Vina binary exists but full redock+score pipeline is not wired yet.
    # Do not invent scores; require crystal redock RMSD before any production score.
    if not crystal_ligand_pdbqt:
        return DockingResult(
            source="docking",
            evidence_level=EvidenceLevel.D,
            confidence=0.0,
            warnings=["crystal_ligand_required_for_redock_rmsd"],
            provenance={"receptor": receptor_pdbqt, "ligand": ligand_pdbqt, "center": center},
            status="skipped_incomplete_integration",
            score=None,
            rmsd_redock=None,
            label="computational_prediction",
            details={
                "box_size": box_size,
                "redock_required": True,
                "reason": "missing_crystal_ligand_for_rmsd",
            },
        )

    return DockingResult(
        source="docking",
        evidence_level=EvidenceLevel.D,
        confidence=0.0,
        warnings=[
            "vina_present_but_full_pipeline_not_wired_in_mvp; "
            "integrate e-drug-lab vina_service for production runs"
        ],
        provenance={"receptor": receptor_pdbqt, "ligand": ligand_pdbqt, "center": center},
        status="skipped_incomplete_integration",
        score=None,
        rmsd_redock=None,
        label="computational_prediction",
        details={
            "box_size": box_size,
            "crystal_ligand": crystal_ligand_pdbqt,
            "redock_required": True,
            "reason": "vina_cli_not_invoked_in_mvp",
            "preferred_production": "schrodinger_service.run_pipeline_dock",
            "catalog_ids": ["sz.glide_sp", "ed.svc.schrodinger"],
        },
    )
