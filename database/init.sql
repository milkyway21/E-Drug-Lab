-- e-drug lab PostgreSQL schema
-- Mirrors backend/app/repositories/models.py and provides a clean bootstrap for local development.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(255) NOT NULL,
  type VARCHAR(50) NOT NULL,
  description TEXT,
  audience VARCHAR(100),
  frontend_stack VARCHAR(100),
  backend_stack VARCHAR(100),
  database_type VARCHAR(50),
  style_preference VARCHAR(100),
  needs_assets BOOLEAN DEFAULT FALSE,
  output_path TEXT,
  config JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS targets (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  pdb_id VARCHAR(10),
  source VARCHAR(50),
  structure_path TEXT NOT NULL,
  resolution VARCHAR(20),
  chains TEXT[],
  residues INTEGER,
  binding_site JSONB,
  preprocessing_params JSONB,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compound_libraries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(255) NOT NULL,
  source VARCHAR(50) NOT NULL,
  compound_count INTEGER,
  file_path TEXT,
  filters JSONB,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS screening_tasks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  target_id UUID REFERENCES targets(id) ON DELETE CASCADE,
  library_id UUID REFERENCES compound_libraries(id) ON DELETE CASCADE,
  tool_name VARCHAR(50) NOT NULL,
  task_type VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  progress DOUBLE PRECISION DEFAULT 0.0,
  params JSONB,
  results_path TEXT,
  error_message TEXT,
  pipeline_step VARCHAR(50),
  pipeline_config JSONB,
  started_at TIMESTAMP WITHOUT TIME ZONE,
  completed_at TIMESTAMP WITHOUT TIME ZONE,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS candidate_molecules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID REFERENCES screening_tasks(id) ON DELETE CASCADE,
  smiles TEXT NOT NULL,
  name VARCHAR(255),
  docking_score DOUBLE PRECISION,
  admet_profile JSONB,
  binding_energy DOUBLE PRECISION,
  md_stability JSONB,
  comprehensive_score DOUBLE PRECISION,
  rank INTEGER,
  generation_source VARCHAR(50),
  generation_params JSONB,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS candidate_metric_values (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  molecule_id UUID NOT NULL REFERENCES candidate_molecules(id) ON DELETE CASCADE,
  metric_name VARCHAR(100) NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  model_name VARCHAR(100) NOT NULL,
  method_family VARCHAR(100) NOT NULL,
  direction VARCHAR(20) NOT NULL DEFAULT 'lower_is_better',
  units VARCHAR(50),
  uncertainty DOUBLE PRECISION,
  priority INTEGER DEFAULT 100,
  selected BOOLEAN DEFAULT FALSE,
  selection_reason TEXT,
  raw_payload JSONB,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orthogonal_scores (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  molecule_id UUID NOT NULL REFERENCES candidate_molecules(id) ON DELETE CASCADE,
  scoring_version VARCHAR(100) NOT NULL DEFAULT 'orthogonal_rescore_v1',
  primary_metric VARCHAR(100) NOT NULL,
  orthogonal_metric VARCHAR(100) NOT NULL,
  primary_selected_value DOUBLE PRECISION,
  orthogonal_selected_value DOUBLE PRECISION,
  primary_desirability DOUBLE PRECISION,
  orthogonal_desirability DOUBLE PRECISION,
  consistency_gap DOUBLE PRECISION,
  final_score DOUBLE PRECISION NOT NULL,
  artifact_flag BOOLEAN DEFAULT FALSE,
  artifact_reason TEXT,
  details JSONB,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sdf_molecules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  sdf_filename VARCHAR(500) NOT NULL,
  sdf_file_path TEXT NOT NULL,
  sdf_file_hash VARCHAR(64) NOT NULL,
  file_size_bytes INTEGER,
  conformer_index INTEGER DEFAULT 0,
  total_conformers INTEGER DEFAULT 1,
  name VARCHAR(500),
  smiles TEXT,
  inchi TEXT,
  inchikey VARCHAR(27),
  molecular_formula VARCHAR(200),
  molecular_weight DOUBLE PRECISION,
  num_atoms INTEGER,
  num_heavy_atoms INTEGER,
  num_rotatable_bonds INTEGER,
  num_h_bond_donors INTEGER,
  num_h_bond_acceptors INTEGER,
  logp DOUBLE PRECISION,
  tpsa DOUBLE PRECISION,
  qed DOUBLE PRECISION,
  sdf_properties JSONB,
  tags TEXT[],
  notes TEXT,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tool_configurations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tool_name VARCHAR(50) NOT NULL UNIQUE,
  executable_path TEXT NOT NULL,
  data_dir TEXT,
  version VARCHAR(50),
  is_available BOOLEAN DEFAULT FALSE,
  last_checked TIMESTAMP WITHOUT TIME ZONE,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_credentials (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  service_name VARCHAR(50) NOT NULL UNIQUE,
  api_key TEXT NOT NULL,
  base_url TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_targets_project ON targets(project_id);
CREATE INDEX IF NOT EXISTS idx_targets_pdb ON targets(pdb_id);
CREATE INDEX IF NOT EXISTS idx_libraries_source ON compound_libraries(source);
CREATE INDEX IF NOT EXISTS idx_tasks_target ON screening_tasks(target_id);
CREATE INDEX IF NOT EXISTS idx_tasks_library ON screening_tasks(library_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON screening_tasks(status);
CREATE INDEX IF NOT EXISTS idx_molecules_task ON candidate_molecules(task_id);
CREATE INDEX IF NOT EXISTS idx_molecules_score ON candidate_molecules(comprehensive_score);
CREATE INDEX IF NOT EXISTS idx_molecules_rank ON candidate_molecules(rank);
CREATE INDEX IF NOT EXISTS idx_candidate_metric_molecule ON candidate_metric_values(molecule_id);
CREATE INDEX IF NOT EXISTS idx_candidate_metric_name ON candidate_metric_values(metric_name);
CREATE INDEX IF NOT EXISTS idx_candidate_metric_model ON candidate_metric_values(model_name);
CREATE INDEX IF NOT EXISTS idx_candidate_metric_method ON candidate_metric_values(method_family);
CREATE INDEX IF NOT EXISTS idx_orthogonal_score_molecule ON orthogonal_scores(molecule_id);
CREATE INDEX IF NOT EXISTS idx_orthogonal_score_final ON orthogonal_scores(final_score);
CREATE INDEX IF NOT EXISTS idx_orthogonal_score_flag ON orthogonal_scores(artifact_flag);
CREATE INDEX IF NOT EXISTS idx_sdf_filename ON sdf_molecules(sdf_filename);
CREATE INDEX IF NOT EXISTS idx_sdf_inchikey ON sdf_molecules(inchikey);
CREATE INDEX IF NOT EXISTS idx_sdf_mw ON sdf_molecules(molecular_weight);
CREATE INDEX IF NOT EXISTS idx_sdf_logp ON sdf_molecules(logp);
CREATE INDEX IF NOT EXISTS idx_sdf_qed ON sdf_molecules(qed);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sdf_file_conformer ON sdf_molecules(sdf_file_hash, conformer_index);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_projects_updated_at ON projects;
CREATE TRIGGER trg_projects_updated_at
BEFORE UPDATE ON projects
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_sdf_molecules_updated_at ON sdf_molecules;
CREATE TRIGGER trg_sdf_molecules_updated_at
BEFORE UPDATE ON sdf_molecules
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tool_configurations_updated_at ON tool_configurations;
CREATE TRIGGER trg_tool_configurations_updated_at
BEFORE UPDATE ON tool_configurations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_api_credentials_updated_at ON api_credentials;
CREATE TRIGGER trg_api_credentials_updated_at
BEFORE UPDATE ON api_credentials
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO projects (name, type, description, frontend_stack, backend_stack, database_type, needs_assets)
VALUES (
  'e-drug lab demo',
  'drug-discovery',
  'Local bootstrap project for lead generation and virtual screening workflows.',
  'Next.js, React, TypeScript, Tailwind CSS',
  'FastAPI, SQLAlchemy, Celery, RDKit',
  'PostgreSQL',
  FALSE
)
ON CONFLICT DO NOTHING;
