"""Pydantic data models for Scientist_In_E-Drug-Lab."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceLevel(str, Enum):
    A = "A"  # human genetics / clinical
    B = "B"  # strong preclinical / human tissue
    C = "C"  # cellular / animal
    D = "D"  # computational / hypothesis
    U = "U"  # unverified / missing


class NoveltyClass(str, Enum):
    ESTABLISHED = "established_target"
    EMERGING = "emerging_target"
    NOVEL = "novel_hypothesis"


class LigandRole(str, Enum):
    CRYSTALLOGRAPHIC = "crystallographic_reference"
    BIOCHEMICAL = "biochemical_positive_control"
    CELLULAR = "cellular_positive_control"
    COMPUTATIONAL = "computational_candidate"


class DiseaseScope(str, Enum):
    MASLD = "MASLD"
    HCC = "HCC"


class ProvenanceMixin(BaseModel):
    source: str = Field(..., description="Data origin, e.g. uniprot|fixture|europepmc")
    retrieved_at: datetime = Field(default_factory=utc_now)
    evidence_level: EvidenceLevel = EvidenceLevel.U
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class CompetitionProfile(ProvenanceMixin):
    competition_url: str
    competition_name: str = "AI4S Life Science"
    disease_default: DiseaseScope = DiseaseScope.MASLD
    disease_active: DiseaseScope = DiseaseScope.MASLD
    scraped_at: Optional[datetime] = None
    verbatim_excerpts: list[str] = Field(default_factory=list)
    scope_conflicts: list[str] = Field(default_factory=list)
    competition_scope_warning: str = Field(
        ...,
        description="Mandatory warning: confirm MASLD vs HCC scope with organizers",
    )
    hard_constraints: dict[str, str] = Field(default_factory=dict)
    structured: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(ProvenanceMixin):
    pmid: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    abstract_excerpt: Optional[str] = None
    supports_claim: Optional[str] = None
    verified: bool = False


class TargetCandidate(ProvenanceMixin):
    gene_symbol: str
    uniprot_id: Optional[str] = None
    organism: str = "Homo sapiens"
    rationale: str = ""
    mechanisms: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ProteinStructure(ProvenanceMixin):
    pdb_id: str
    organism: Optional[str] = None
    resolution_A: Optional[float] = None
    method: Optional[str] = None
    chains: list[str] = Field(default_factory=list)
    cofactors: list[str] = Field(default_factory=list)
    bound_ligands: list[str] = Field(default_factory=list)
    is_alphafold: bool = False
    preferred: bool = False
    selection_reason: str = ""


class BindingPocket(ProvenanceMixin):
    pocket_type: str  # catalytic|substrate|allosteric|ppi
    key_residues: list[str] = Field(default_factory=list)
    structure_pdb_id: Optional[str] = None
    selection_reason: str = ""


class ReferenceLigand(ProvenanceMixin):
    name: str
    pubchem_cid: Optional[int] = None
    chembl_id: Optional[str] = None
    smiles: Optional[str] = None
    inchikey: Optional[str] = None
    role: LigandRole = LigandRole.COMPUTATIONAL
    activity_type: Optional[str] = None
    activity_value: Optional[str] = None
    assay_source: Optional[str] = None


class DockingResult(ProvenanceMixin):
    status: str  # ok|skipped_missing_dependency|failed
    score: Optional[float] = None
    rmsd_redock: Optional[float] = None
    label: str = "computational_prediction"
    details: dict[str, Any] = Field(default_factory=dict)


class SafetyConcern(ProvenanceMixin):
    concern: str
    severity: str = "moderate"  # low|moderate|high
    mitigation: Optional[str] = None


class ValidationExperiment(ProvenanceMixin):
    system: str  # cell|organoid|animal
    readout: str
    controls: list[str] = Field(default_factory=list)
    notes: str = ""


class ScoreBreakdown(BaseModel):
    human_genetics_evidence: Optional[float] = None
    disease_mechanism_relevance: Optional[float] = None
    hepatocyte_or_liver_specificity: Optional[float] = None
    druggability: Optional[float] = None
    structure_availability: Optional[float] = None
    ligand_precedent: Optional[float] = None
    safety_rationale: Optional[float] = None
    novelty: Optional[float] = None
    total: Optional[float] = None
    missing_dimensions: list[str] = Field(default_factory=list)
    sources: dict[str, list[str]] = Field(default_factory=dict)


class TargetHypothesis(ProvenanceMixin):
    gene_symbol: str
    uniprot_id: Optional[str] = None
    novelty_class: NoveltyClass = NoveltyClass.EMERGING
    scores: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    structures: list[ProteinStructure] = Field(default_factory=list)
    pockets: list[BindingPocket] = Field(default_factory=list)
    ligands: list[ReferenceLigand] = Field(default_factory=list)
    docking: list[DockingResult] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    opposing_evidence: list[EvidenceRecord] = Field(default_factory=list)
    safety_concerns: list[SafetyConcern] = Field(default_factory=list)
    validation_plan: list[ValidationExperiment] = Field(default_factory=list)
    scientific_significance: str = ""
    clinical_significance: str = ""
    uncertainty: str = ""


class AgentRunManifest(ProvenanceMixin):
    run_id: str
    disease: DiseaseScope
    modality: str = "small_molecule_inhibitor"
    top_targets: int = 10
    offline: bool = False
    competition_scope_warning: str = ""
    config_snapshot_path: Optional[str] = None
    output_dir: Optional[str] = None
    hermes_eval_mode: bool = True
    tool_versions: dict[str, str] = Field(default_factory=dict)
    events_path: Optional[str] = None
