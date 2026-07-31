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
    uniprot_id: Optional[str] = None
    entity_id: Optional[str] = None
    sequence_coverage: Optional[float] = Field(None, ge=0.0, le=1.0)
    mutations: list[str] = Field(default_factory=list)
    biological_assembly: Optional[str] = None
    release_date: Optional[str] = None
    quality_score: Optional[float] = Field(None, ge=0.0, le=100.0)


class BindingPocket(ProvenanceMixin):
    pocket_type: str  # catalytic|substrate|allosteric|ppi
    key_residues: list[str] = Field(default_factory=list)
    structure_pdb_id: Optional[str] = None
    selection_reason: str = ""


class TargetEvidenceCard(ProvenanceMixin):
    gene_symbol: str
    disease: str
    uniprot_id: Optional[str] = None
    ensembl_id: Optional[str] = None
    organism: str = "Homo sapiens"
    biological_function: str = ""
    tissue_context: list[str] = Field(default_factory=list)
    pathways: list[str] = Field(default_factory=list)
    mechanism_directions: list[str] = Field(default_factory=list)
    supporting_evidence: list[EvidenceRecord] = Field(default_factory=list)
    opposing_evidence: list[EvidenceRecord] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class StructureCandidate(ProteinStructure):
    target_gene: Optional[str] = None
    relevant_ligand: bool = False
    construct_notes: list[str] = Field(default_factory=list)


class PocketQualification(ProvenanceMixin):
    target_gene: str
    structure_id: Optional[str] = None
    applicable: bool = False
    qualified: bool = False
    pocket_type: Optional[str] = None
    key_residues: list[str] = Field(default_factory=list)
    evidence_basis: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    docking_recommendation: str = "do_not_dock"


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


class ActivityEvidence(ProvenanceMixin):
    target: Optional[str] = None
    assay_id: Optional[str] = None
    assay_type: Optional[str] = None
    assay_description: Optional[str] = None
    organism: Optional[str] = None
    standard_type: Optional[str] = None
    standard_relation: Optional[str] = None
    standard_value: Optional[float] = None
    standard_units: Optional[str] = None
    pchembl_value: Optional[float] = None
    document_id: Optional[str] = None


class SafetyEvidence(ProvenanceMixin):
    endpoint: str
    result: str
    severity: str = "unknown"
    observed: bool = False
    prediction: bool = False
    reference_id: Optional[str] = None
    applicability: str = "unknown"


class MechanismHypothesis(BaseModel):
    intervention: str
    direct_action: str
    target_or_pathway: str
    expected_direction: str
    lipid_phenotype: str
    evidence_refs: list[str] = Field(default_factory=list)
    alternative_mechanisms: list[str] = Field(default_factory=list)
    falsifiers: list[str] = Field(default_factory=list)
    validation_readouts: list[str] = Field(default_factory=list)


class NominationScoreBreakdown(BaseModel):
    lipid_evidence: float = Field(0.0, ge=0.0, le=100.0)
    mechanism_relevance: float = Field(0.0, ge=0.0, le=100.0)
    activity_quality: float = Field(0.0, ge=0.0, le=100.0)
    safety: float = Field(0.0, ge=0.0, le=100.0)
    structure_developability: float = Field(0.0, ge=0.0, le=100.0)
    diversity: float = Field(0.0, ge=0.0, le=100.0)
    uncertainty_penalty: float = Field(0.0, ge=0.0, le=20.0)
    weighted_total: float = Field(0.0, ge=0.0, le=100.0)
    final_score: float = Field(0.0, ge=0.0, le=100.0)
    weights: dict[str, float] = Field(default_factory=dict)


class CompoundEvidenceCard(ProvenanceMixin):
    library_id: str
    library_source: str
    name: Optional[str] = None
    canonical_smiles: Optional[str] = None
    parent_inchikey: Optional[str] = None
    pubchem_cid: Optional[int] = None
    chembl_id: Optional[str] = None
    molecular_properties: dict[str, Optional[float]] = Field(default_factory=dict)
    structure_alerts: list[str] = Field(default_factory=list)
    target_or_pathway: list[str] = Field(default_factory=list)
    lipid_rationale: str = ""
    toxicity_rationale: str = ""
    activity_evidence: list[ActivityEvidence] = Field(default_factory=list)
    safety_evidence: list[SafetyEvidence] = Field(default_factory=list)
    literature_evidence: list[EvidenceRecord] = Field(default_factory=list)
    mechanism_hypotheses: list[MechanismHypothesis] = Field(default_factory=list)
    score: NominationScoreBreakdown = Field(default_factory=NominationScoreBreakdown)
    structure_applicability: str = "not_assessed"
    identity_valid: bool = False


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
