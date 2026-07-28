"""
e-drug lab SQLAlchemy 数据库模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey,
    Text, ARRAY, JSON, Index, event
)
from sqlalchemy import String as SAString
from sqlalchemy.orm import relationship, declarative_base, Session
import uuid

Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = 'projects'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)
    description = Column(Text)
    audience = Column(String(100))
    frontend_stack = Column(String(100))
    backend_stack = Column(String(100))
    database_type = Column(String(50))
    style_preference = Column(String(100))
    needs_assets = Column(Boolean, default=False)
    output_path = Column(Text)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    targets = relationship('Target', back_populates='project', cascade='all, delete-orphan')


class Target(Base):
    __tablename__ = 'targets'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    project_id = Column(SAString(36), ForeignKey('projects.id', ondelete='CASCADE'))
    name = Column(String(255))
    pdb_id = Column(String(10))
    source = Column(String(50))
    status = Column(String(20), default='created')
    structure_path = Column(Text)
    resolution = Column(String(20))
    chains = Column(JSON)
    residues = Column(Integer)
    binding_site = Column(JSON)
    preprocessing_params = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    project = relationship('Project', back_populates='targets')
    screening_tasks = relationship('ScreeningTask', back_populates='target')
    __table_args__ = (Index('idx_targets_project', 'project_id'), Index('idx_targets_pdb', 'pdb_id'))


class CompoundLibrary(Base):
    __tablename__ = 'compound_libraries'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False)
    compound_count = Column(Integer)
    file_path = Column(Text)
    filters = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    screening_tasks = relationship('ScreeningTask', back_populates='library')
    __table_args__ = (Index('idx_libraries_source', 'source'),)


class ScreeningTask(Base):
    __tablename__ = 'screening_tasks'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    target_id = Column(SAString(36), ForeignKey('targets.id', ondelete='CASCADE'))
    library_id = Column(SAString(36), ForeignKey('compound_libraries.id', ondelete='CASCADE'))
    tool_name = Column(String(50), nullable=False)
    task_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    progress = Column(Float, default=0.0)
    params = Column(JSON)
    results_path = Column(Text)
    error_message = Column(Text)
    pipeline_step = Column(String(50))
    pipeline_config = Column(JSON)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    target = relationship('Target', back_populates='screening_tasks')
    library = relationship('CompoundLibrary', back_populates='screening_tasks')
    molecules = relationship('CandidateMolecule', back_populates='task', cascade='all, delete-orphan')
    __table_args__ = (Index('idx_tasks_target', 'target_id'), Index('idx_tasks_library', 'library_id'), Index('idx_tasks_status', 'status'))


class CandidateMolecule(Base):
    __tablename__ = 'candidate_molecules'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    task_id = Column(SAString(36), ForeignKey('screening_tasks.id', ondelete='CASCADE'))
    smiles = Column(Text, nullable=False)
    name = Column(String(255))
    standard_name = Column(String(255))
    docking_score = Column(Float)
    admet_profile = Column(JSON)
    binding_energy = Column(Float)
    md_stability = Column(JSON)
    comprehensive_score = Column(Float)
    rank = Column(Integer)
    generation_source = Column(String(50))
    generation_params = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    task = relationship('ScreeningTask', back_populates='molecules')
    __table_args__ = (
        Index('idx_molecules_task', 'task_id'),
        Index('idx_molecules_score', 'comprehensive_score'),
        Index('idx_molecules_rank', 'rank'),
    )


class SDFMolecule(Base):
    """SDF 分子数据库表 - 从 SDF 文件夹自动解析"""
    __tablename__ = 'sdf_molecules'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    sdf_filename = Column(String(500), nullable=False)
    sdf_file_path = Column(Text, nullable=False)
    sdf_file_hash = Column(String(64), nullable=False)
    file_size_bytes = Column(Integer)
    conformer_index = Column(Integer, default=0)
    total_conformers = Column(Integer, default=1)
    name = Column(String(500))
    smiles = Column(Text)
    inchi = Column(Text)
    inchikey = Column(String(27))
    molecular_formula = Column(String(200))
    molecular_weight = Column(Float)
    num_atoms = Column(Integer)
    num_heavy_atoms = Column(Integer)
    num_rotatable_bonds = Column(Integer)
    num_h_bond_donors = Column(Integer)
    num_h_bond_acceptors = Column(Integer)
    logp = Column(Float)
    tpsa = Column(Float)
    qed = Column(Float)
    sa_score = Column(Float)
    sdf_properties = Column(JSON)
    tags = Column(JSON)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        Index('idx_sdf_filename', 'sdf_filename'),
        Index('idx_sdf_inchikey', 'inchikey'),
        Index('idx_sdf_mw', 'molecular_weight'),
        Index('idx_sdf_logp', 'logp'),
        Index('idx_sdf_qed', 'qed'),
        Index('idx_sdf_file_conformer', 'sdf_file_hash', 'conformer_index', unique=True),
    )


class ToolConfiguration(Base):
    __tablename__ = 'tool_configurations'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    tool_name = Column(String(50), nullable=False, unique=True)
    executable_path = Column(Text, nullable=False)
    data_dir = Column(Text)
    version = Column(String(50))
    is_available = Column(Boolean, default=False)
    last_checked = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class APICredential(Base):
    __tablename__ = 'api_credentials'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    service_name = Column(String(50), nullable=False, unique=True)
    api_key = Column(Text, nullable=False)
    base_url = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RLRound(Base):
    __tablename__ = 'rl_rounds'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    round_id = Column(Integer, nullable=False, unique=True, index=True)
    target_id = Column(SAString(36), ForeignKey('targets.id', ondelete='SET NULL'), nullable=True)
    status = Column(String(30), nullable=False, default='created')
    checkpoint_path = Column(Text)
    wetlab_count = Column(Integer, default=0)
    config_json = Column(JSON, default=dict)
    step_log_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    artifacts = relationship('RLRoundArtifact', back_populates='round', cascade='all, delete-orphan')
    __table_args__ = (Index('idx_rl_rounds_status', 'status'),)


class RLRoundArtifact(Base):
    __tablename__ = 'rl_round_artifacts'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    round_id = Column(Integer, ForeignKey('rl_rounds.round_id', ondelete='CASCADE'), nullable=False)
    step = Column(String(50), nullable=False)
    artifact_type = Column(String(30), nullable=False)
    path = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    round = relationship('RLRound', back_populates='artifacts')
    __table_args__ = (Index('idx_rl_artifacts_round', 'round_id'),)


class PipelineRun(Base):
    __tablename__ = 'pipeline_runs'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    project_id = Column(SAString(36), ForeignKey('projects.id', ondelete='SET NULL'), nullable=True)
    target_id = Column(SAString(36), ForeignKey('targets.id', ondelete='SET NULL'), nullable=True)
    recipe_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default='pending')
    current_step_id = Column(String(50))
    context_json = Column(JSON, default=dict)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    step_runs = relationship('PipelineStepRun', back_populates='pipeline_run', cascade='all, delete-orphan')
    __table_args__ = (
        Index('idx_pipeline_runs_status', 'status'),
        Index('idx_pipeline_runs_target', 'target_id'),
    )


class PipelineStepRun(Base):
    __tablename__ = 'pipeline_step_runs'
    id = Column(SAString(36), primary_key=True, default=generate_uuid)
    pipeline_run_id = Column(SAString(36), ForeignKey('pipeline_runs.id', ondelete='CASCADE'), nullable=False)
    step_id = Column(String(50), nullable=False)
    tool_ids = Column(JSON, default=list)
    status = Column(String(20), nullable=False, default='pending')
    progress = Column(Float, default=0.0)
    params_json = Column(JSON, default=dict)
    result_json = Column(JSON)
    error_message = Column(Text)
    screening_task_id = Column(SAString(36), ForeignKey('screening_tasks.id', ondelete='SET NULL'), nullable=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    pipeline_run = relationship('PipelineRun', back_populates='step_runs')
    __table_args__ = (
        Index('idx_pipeline_step_runs_run', 'pipeline_run_id'),
        Index('idx_pipeline_step_runs_status', 'status'),
    )


@event.listens_for(Project, 'before_update')
@event.listens_for(RLRound, 'before_update')
@event.listens_for(PipelineRun, 'before_update')
@event.listens_for(ToolConfiguration, 'before_update')
@event.listens_for(APICredential, 'before_update')
@event.listens_for(SDFMolecule, 'before_update')
def receive_before_update(mapper, connection, target):
    target.updated_at = datetime.utcnow()
