export type ToolStatus = {
  name: string;
  executable_path: string;
  available: boolean;
  last_checked: string | null;
};

export type ReadinessResponse = {
  status: "ready" | "degraded";
  tools_available: number;
  tools_total: number;
  tools: Record<string, ToolStatus>;
};

export type Pagination = {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type Target = {
  id: string;
  project_id: string | null;
  name: string | null;
  pdb_id: string | null;
  source: string | null;
  status: string | null;
  structure_path: string | null;
  resolution: string | null;
  chains: unknown;
  residues: number | null;
  binding_site: unknown;
  preprocessing_params: unknown;
  created_at: string | null;
};

export type Library = {
  id: string;
  name: string;
  source: string;
  compound_count: number | null;
  file_path: string | null;
  filters: unknown;
  created_at: string | null;
};

export type Molecule = {
  id: string;
  name: string | null;
  smiles: string | null;
  molecular_formula: string | null;
  molecular_weight: number | null;
  logp: number | null;
  qed: number | null;
  tpsa: number | null;
  sdf_filename: string;
  created_at: string | null;
};

export type SDFMolecule = {
  id: string;
  name: string | null;
  smiles: string | null;
  inchi: string | null;
  inchikey: string | null;
  molecular_formula: string | null;
  molecular_weight: number | null;
  num_atoms: number | null;
  num_heavy_atoms: number | null;
  num_rotatable_bonds: number | null;
  num_h_bond_donors: number | null;
  num_h_bond_acceptors: number | null;
  logp: number | null;
  tpsa: number | null;
  qed: number | null;
  sa_score: number | null;
  sdf_filename: string;
  sdf_file_path: string;
  sdf_file_hash: string;
  file_size_bytes: number | null;
  conformer_index: number;
  total_conformers: number;
  sdf_properties: Record<string, unknown> | null;
  tags: string[];
  created_at: string | null;
};

export type MoleculeListResponse = {
  molecules: SDFMolecule[];
  pagination: Pagination;
};

export type SyncStatusResponse = {
  total_molecules: number;
  total_sdf_files: number;
  sdf_files: Array<{
    filename: string;
    file_path: string;
    conformers_in_db: number;
    total_conformers_in_file: number;
  }>;
};

export type OrthogonalRankedCandidate = {
  molecule_id: string;
  name: string | null;
  standard_name?: string | null;
  primary_value: number;
  orthogonal_value: number;
  primary_desirability: number;
  orthogonal_desirability: number;
  consistency_gap: number;
  final_score: number;
  artifact_flag: boolean;
  artifact_reason: string | null;
  selected_primary_model: string;
  selected_orthogonal_model: string;
};

export type RankingMoleculeRecord = {
  molecule_id: string;
  name?: string;
  smiles?: string;
  source?: string;
  source_db_id?: string;
  status?: "pending" | "pass" | "fail";
  sa_score?: number | null;
  molecular_weight?: number | null;
  logp?: number | null;
  tpsa?: number | null;
  qed?: number | null;
  herg?: number | null;
  dili?: number | null;
  ames?: number | null;
  hia?: number | null;
  docking_affinity?: number | null;
  step_results?: Record<string, unknown>;
};

export type OrthogonalRescoreResponse = {
  method: string;
  selection_rule: string;
  final_score_rule: string;
  ranked: OrthogonalRankedCandidate[];
  task_id?: string | null;
  saved_molecules?: number;
  report_download_url?: string | null;
};

export type SyncResultResponse = {
  status: string;
  sdf_directory: string;
  sync_result: {
    total_files: number;
    new_files: number;
    updated_files: number;
    unchanged_files: number;
    deleted_records: number;
    total_conformers_added: number;
    errors: Array<{ file: string; error: string; conformer?: number }>;
    files_processed: string[];
  };
};

export type MoleculeFilterParams = {
  search?: string;
  min_mw?: number; max_mw?: number;
  min_logp?: number; max_logp?: number;
  min_qed?: number; max_qed?: number;
  min_sa_score?: number; max_sa_score?: number;
  min_tpsa?: number; max_tpsa?: number;
  min_rotatable_bonds?: number; max_rotatable_bonds?: number;
  min_hbd?: number; max_hbd?: number;
  min_hba?: number; max_hba?: number;
  min_heavy_atoms?: number; max_heavy_atoms?: number;
  lipinski_pass?: boolean;
  sdf_filename?: string;
};

export type DistributionBucket = {
  min: number;
  max: number | null;
  count: number;
};

export type MoleculeDistributions = {
  molecular_weight: DistributionBucket[];
  logp: DistributionBucket[];
  qed: DistributionBucket[];
  sa_score: DistributionBucket[];
  tpsa: DistributionBucket[];
  rotatable_bonds: DistributionBucket[];
  hbd: DistributionBucket[];
  hba: DistributionBucket[];
  heavy_atoms: DistributionBucket[];
};

export type MoleculeDBStats = {
  total_molecules: number;
  total_sdf_files: number;
  filtered: boolean;
  statistics: {
    molecular_weight: { avg: number | null; min: number | null; max: number | null };
    logp_avg: number | null;
    qed_avg: number | null;
    sa_score_avg: number | null;
    tpsa_avg: number | null;
    rotatable_bonds_avg: number | null;
    hbd_avg: number | null;
    hba_avg: number | null;
    heavy_atoms_avg: number | null;
    lipinski: { pass_count: number; fail_count: number; total_evaluated: number } | null;
  };
};

export type ScreeningTask = {
  task_id: string;
  status: string;
  progress?: number;
};

export type ScreeningResults = {
  results: unknown[];
  pagination: Pagination;
};

export type TaskItem = {
  id: string;
  status: string;
};

export type TaskListResponse = {
  tasks: TaskItem[];
  pagination: Pagination;
};

export type MetricObservationRequest = {
  metric_name: string;
  value: number;
  model_name: string;
  method_family: string;
  direction?: "higher_is_better" | "lower_is_better";
  priority?: number;
};

export type CandidateRankingRequest = {
  molecule_id: string;
  name?: string;
  metrics: MetricObservationRequest[];
};

export type OrthogonalRescoreRequestBody = {
  candidates: CandidateRankingRequest[];
  primary_metric?: string;
  orthogonal_metric?: string;
  preferred_primary_models?: string[];
  preferred_orthogonal_models?: string[];
  gap_threshold?: number;
  target_id?: string;
  target_pdb_id?: string;
  library_id?: string;
  molecule_records?: RankingMoleculeRecord[];
};


// ── Affinity / Docking 类型 ────────────────────────────────

export type VinaBox = {
  center_x: number;
  center_y: number;
  center_z: number;
  size_x?: number;
  size_y?: number;
  size_z?: number;
};

export type VinaDockPayload = {
  receptor_path: string;
  ligand_path: string;
  box: VinaBox;
  exhaustiveness?: number;
  num_modes?: number;
  energy_range?: number;
  cpu?: number;
  seed?: number;
};

export type VinaBatchPayload = {
  receptor_path: string;
  ligand_paths: string[];
  box: VinaBox;
  exhaustiveness?: number;
  num_modes?: number;
  energy_range?: number;
  concurrency?: number;
};

export type VinaPose = {
  mode: number;
  affinity: number;
  rmsd_lb: number;
  rmsd_ub: number;
};

export type VinaDockResponse = {
  task_id: string;
  status: string;
  receptor_path: string;
  ligand_path: string;
  output_pdbqt: string | null;
  best_affinity: number | null;
  poses: VinaPose[];
  command: string[];
  error: string | null;
};

export type VinaBatchResponse = {
  task_id: string;
  status: string;
  total: number;
  results: VinaDockResponse[];
};

export type GlideDockPayload = {
  receptor_file: string;
  ligands_file: string;
  precision?: "HTVS" | "SP" | "XP";
  center_x?: number;
  center_y?: number;
  center_z?: number;
  inner_box?: number;
  outer_box?: number;
  num_poses?: number;
  postdock_minimize?: boolean;
  ph?: number;
  ph_threshold?: number;
  job_name?: string;
};

export type GlideDockResponse = {
  task_id: string;
  status: string;
  job_id: string | null;
  message: string;
  precision?: string;
  scores?: Array<{ title: string; glide_xp_score: number | null; glide_rmsd: number | null }>;
  pose_maegz?: string;
  receptor_maegz?: string;
};

export type GlideStatusResponse = {
  available: boolean;
  api_key_set?: boolean;
  base_url?: string;
  local_ok?: boolean;
  install_path?: string;
  tools?: Record<string, { installed?: boolean; version?: string; path?: string }>;
  message: string;
};

export type SchrodingerPipelineDockPayload = {
  molecules: Array<{ molecule_id: string; smiles: string; name?: string }>;
  target_id?: string;
  target_pdb_id?: string;
  receptor_path?: string;
  precision?: "HTVS" | "SP" | "XP";
  ph?: number;
  ph_threshold?: number;
  center_x?: number;
  center_y?: number;
  center_z?: number;
  outer_box?: number;
  poses_per_lig?: number;
  postdock_minimize?: boolean;
  run_mmgbsa?: boolean;
  async_run?: boolean;
};

export type SchrodingerMoleculeResult = {
  molecule_id: string;
  title: string;
  glide_score: number | null;
  glide_rmsd: number | null;
  mmgbsa_dg: number | null;
  success: boolean;
};

export type SchrodingerDockResult = {
  ok: boolean;
  run_id?: string;
  output_dir?: string;
  precision?: string;
  molecule_results?: SchrodingerMoleculeResult[];
  output_files?: Record<string, string>;
  steps_log?: Array<Record<string, unknown>>;
  error?: string;
};

export type SchrodingerJobResponse = {
  id: string;
  type: string;
  status: string;
  progress: number;
  message: string;
  result?: SchrodingerDockResult;
  error?: string | null;
};

export type VinaVersionResponse = {
  available: boolean;
  version: string | null;
  path: string | null;
};

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string; status?: number };

/** 与 backend APP_PORT=8001 对齐；浏览器端按当前 hostname 自动拼接。 */
export function getApiBaseUrl(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8001`;
  }
  return "http://127.0.0.1:8001";
}

async function request<T>(
  path: string,
  init?: RequestInit,
  fallback: T | null = null
): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {})
      },
      cache: "no-store"
    });

    if (!response.ok) {
      const text = await response.text();
      return {
        ok: false,
        status: response.status,
        error: text || `Request failed with ${response.status}`
      };
    }

    return { ok: true, data: (await response.json()) as T };
  } catch (error) {
    if (fallback !== null) {
      return { ok: true, data: fallback };
    }

    return {
      ok: false,
      error: error instanceof Error ? error.message : "Unknown request error"
    };
  }
}

export const apiClient = {
  get apiBaseUrl() {
    return getApiBaseUrl();
  },

  // ===== Health =====
  health() {
    return request<{ status: string }>("/health");
  },

  readiness() {
    return request<ReadinessResponse>("/ready");
  },

  // ===== Targets =====
  listTargets(page = 1, page_size = 20, source?: string) {
    const params = new URLSearchParams({ page: String(page), page_size: String(page_size) });
    if (source) params.set("source", source);
    return request<{ targets: Target[]; pagination: Pagination }>(`/api/v1/targets?${params}`);
  },

  getTarget(target_id: string) {
    return request<Target>(`/api/v1/targets/${target_id}`);
  },

  createTarget(payload: { pdb_id?: string; name?: string; fasta_sequence?: string; source?: string; project_id?: string }) {
    return request<Target>("/api/v1/targets", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  downloadTarget(pdb_id: string) {
    return request<{ status: string; pdb_id: string }>("/api/v1/targets/download", {
      method: "POST",
      body: JSON.stringify({ pdb_id })
    });
  },

  preprocessTarget(target_id: string) {
    return request<{ status: string; target_id: string }>(`/api/v1/targets/${target_id}/preprocess`, {
      method: "POST"
    });
  },

  predictStructure(payload: { fasta_sequence?: string; model_type?: string }) {
    return request<{ status: string; model_type: string; message: string }>("/api/v1/targets/predict", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  async uploadProtein(file: File, name?: string): Promise<ApiResult<{ status: string; target_id: string; filename: string; file_path: string; size_bytes: number }>> {
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/v1/targets/upload-protein`, { method: "POST", body: form });
      if (!response.ok) {
        const text = await response.text();
        return { ok: false, status: response.status, error: text };
      }
      return { ok: true, data: await response.json() };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : "Upload failed" };
    }
  },

  async uploadLigand(fileOrSmiles: File | string, name?: string): Promise<ApiResult<Record<string, unknown>>> {
    const form = new FormData();
    if (typeof fileOrSmiles === "string") {
      form.append("smiles", fileOrSmiles);
    } else {
      form.append("file", fileOrSmiles);
    }
    if (name) form.append("name", name);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/v1/targets/upload-ligand`, { method: "POST", body: form });
      if (!response.ok) {
        const text = await response.text();
        return { ok: false, status: response.status, error: text };
      }
      return { ok: true, data: await response.json() };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : "Upload failed" };
    }
  },

  // ===== Libraries =====
  listLibraries(page = 1, page_size = 20, source?: string) {
    const params = new URLSearchParams({ page: String(page), page_size: String(page_size) });
    if (source) params.set("source", source);
    return request<{ libraries: Library[]; pagination: Pagination }>(`/api/v1/libraries?${params}`);
  },

  createLibrary(payload: { name: string; source: string; description?: string; filters?: unknown }) {
    return request<Library>("/api/v1/libraries", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  getLibrary(library_id: string) {
    return request<Library>(`/api/v1/libraries/${library_id}`);
  },

  filterLibrary(library_id: string, filters: Record<string, unknown>) {
    return request<{ library_id: string; status: string; filters_applied: unknown }>(
      `/api/v1/libraries/${library_id}/filter`,
      { method: "POST", body: JSON.stringify(filters) }
    );
  },

  // ===== Molecule DB =====
  listMolecules(params: Record<string, string | number | boolean | undefined> = {}) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") search.set(key, String(value));
    });
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return request<MoleculeListResponse>(`/api/v1/molecule-db/molecules${suffix}`);
  },

  getMolecule(molecule_id: string) {
    return request<SDFMolecule>(`/api/v1/molecule-db/molecules/${molecule_id}`);
  },

  deleteMolecule(molecule_id: string) {
    return request<{ status: string; molecule_id: string }>(
      `/api/v1/molecule-db/molecules/${molecule_id}`,
      { method: "DELETE" }
    );
  },

  syncStatus() {
    return request<SyncStatusResponse>("/api/v1/molecule-db/sync/status");
  },

  syncMolecules(sdf_directory?: string) {
    return request<SyncResultResponse>("/api/v1/molecule-db/sync", {
      method: "POST",
      body: JSON.stringify({ sdf_directory })
    });
  },

  moleculeStats(filters?: MoleculeFilterParams) {
    const params = new URLSearchParams();
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== "") params.set(key, String(value));
      });
    }
    const qs = params.toString();
    return request<MoleculeDBStats>(`/api/v1/molecule-db/stats${qs ? `?${qs}` : ""}`);
  },

  moleculeDistributions(filters?: MoleculeFilterParams) {
    const params = new URLSearchParams();
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== "") params.set(key, String(value));
      });
    }
    const qs = params.toString();
    return request<MoleculeDistributions>(`/api/v1/molecule-db/distributions${qs ? `?${qs}` : ""}`);
  },

  // ===== Ranking =====
  orthogonalRescore(body: OrthogonalRescoreRequestBody) {
    return request<OrthogonalRescoreResponse>("/api/v1/ranking/orthogonal-rescore", {
      method: "POST",
      body: JSON.stringify(body)
    });
  },

  orthogonalDemo() {
    return request<OrthogonalRescoreResponse>("/api/v1/ranking/orthogonal-demo");
  },

  // ===== Screening =====
  startScreening(payload: { recipe: Record<string, unknown>; context?: Record<string, unknown> } | Record<string, unknown>) {
    return request<{ task_id: string; run_id: string; status: string }>("/api/v1/screening/start", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getScreeningProgress(task_id: string) {
    return request<{ task_id: string; progress: number; status: string; current_step_id?: string; error_message?: string }>(
      `/api/v1/screening/${task_id}/progress`
    );
  },

  getScreeningResults(task_id: string, page = 1, page_size = 20) {
    return request<{ results: unknown[]; context?: Record<string, unknown>; pagination: Pagination }>(
      `/api/v1/screening/${task_id}/results?page=${page}&page_size=${page_size}`
    );
  },

  cancelScreening(task_id: string) {
    return request<{ task_id: string; status: string }>(`/api/v1/screening/${task_id}/cancel`, {
      method: "POST"
    });
  },

  // ===== ADMET =====
  predictAdmet(payload: { smiles: string[]; names?: string[] }) {
    return request<{ status: string; count: number; predictions: Record<string, unknown>[] }>("/api/v1/admet/predict", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  filterAdmet(payload: { smiles: string[]; rules?: string[]; names?: string[] }) {
    return request<{ status: string; total: number; passed: number; failed: number; results: Record<string, unknown>[] }>("/api/v1/admet/filter", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  // ===== Affinity / Docking =====
  vinaDock(payload: VinaDockPayload) {
    return request<VinaDockResponse>("/api/v1/affinity/docking/vina", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  vinaBatchDock(payload: VinaBatchPayload) {
    return request<VinaBatchResponse>("/api/v1/affinity/docking/vina/batch", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  vinaVersion() {
    return request<VinaVersionResponse>("/api/v1/affinity/docking/vina/version");
  },

  glideDock(payload: GlideDockPayload) {
    return request<GlideDockResponse>("/api/v1/affinity/docking/glide", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  glideStatus() {
    return request<GlideStatusResponse>("/api/v1/affinity/docking/glide/status");
  },

  schrodingerStatus() {
    return request<GlideStatusResponse>("/api/v1/affinity/schrodinger/status");
  },

  schrodingerPipelineDock(payload: SchrodingerPipelineDockPayload) {
    return request<{ ok: boolean; job_id: string; message: string; precision?: string }>(
      "/api/v1/affinity/schrodinger/dock",
      { method: "POST", body: JSON.stringify(payload) }
    );
  },

  schrodingerJob(job_id: string) {
    return request<SchrodingerJobResponse>(`/api/v1/affinity/schrodinger/jobs/${job_id}`);
  },

  optimizeAffinity(payload: Record<string, unknown>) {
    return request<{ status: string }>("/api/v1/affinity/optimize", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  mmgbsa(payload: {
    pose_maegz?: string;
    receptor_maegz?: string;
    trajectory_path?: string;
  } = {}) {
    return request<{
      task_id: string;
      status: string;
      message: string;
      scores?: Array<{ title: string; mmgbsa_dg: number | null }>;
      csv_path?: string;
    }>("/api/v1/affinity/mmgbsa", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  runMd(payload: {
    structure_path?: string;
    mode?: "dry_prep" | "smoke" | "short";
    confirm?: boolean;
    simulation_time_ns?: number;
    host?: string;
    molecule_id?: string;
    target_id?: string;
  } = {}) {
    return request<{
      task_id: string;
      status: string;
      message: string;
      job_dir?: string;
      mode?: string;
      engine?: string;
      stub?: boolean;
      completion?: Record<string, unknown>;
    }>("/api/v1/affinity/md", {
      method: "POST",
      body: JSON.stringify({
        mode: "dry_prep",
        confirm: false,
        ...payload,
      }),
    });
  },

  mdStatus(taskId: string) {
    return request<{
      task_id: string;
      status: string;
      message?: string;
      job_dir?: string;
      mode?: string;
      markers?: Record<string, boolean>;
      completion?: Record<string, unknown>;
      log_tail?: string;
    }>(`/api/v1/affinity/md/${encodeURIComponent(taskId)}`);
  },

  dockSmiles(payload: {
    smiles: string;
    target_id?: string;
    target_pdb_id?: string;
    name?: string;
    exhaustiveness?: number;
    timeout?: number;
  }) {
    return request<{
      smiles: string;
      target_id?: string;
      target_pdb_id?: string;
      affinity_kcal_mol: number | null;
      best_affinity: number | null;
      method: string;
      model: string | null;
      success: boolean;
      error?: string;
      poses_count: number;
    }>("/api/v1/affinity/dock", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  dockSmilesBatch(payload: {
    molecules: Array<{ molecule_id: string; smiles: string; name?: string }>;
    target_id?: string;
    target_pdb_id?: string;
    exhaustiveness?: number;
    timeout_per_molecule?: number;
    concurrency?: number;
  }) {
    return request<{
      vina_available: boolean;
      method: string;
      total: number;
      succeeded: number;
      failed: number;
      results: Array<{
        molecule_id: string;
        smiles: string;
        name: string;
        affinity_kcal_mol: number | null;
        method: string;
        model: string | null;
        success: boolean;
        error?: string;
        poses_count: number;
      }>;
    }>("/api/v1/affinity/dock/batch", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  // ===== TAME-VS =====
  tameVsStatus() {
    return request<{
      status: string;
      version?: string;
      docker_available: boolean;
      service_healthy?: boolean;
      service_status?: Record<string, unknown>;
    }>("/api/v1/tame-vs/status");
  },

  tameVsBuildImage() {
    return request<{ ok: boolean; message: string; result: Record<string, unknown> }>("/api/v1/tame-vs/build-image", { method: "POST" });
  },

  tameVsStartService() {
    return request<{ ok: boolean; result: Record<string, unknown> }>("/api/v1/tame-vs/service/start", { method: "POST" });
  },

  tameVsStopService() {
    return request<{ ok: boolean; result: Record<string, unknown> }>("/api/v1/tame-vs/service/stop", { method: "POST" });
  },

  tameVsRestartService() {
    return request<{ ok: boolean; result: Record<string, unknown> }>("/api/v1/tame-vs/service/restart", { method: "POST" });
  },

  tameVsServiceHealth() {
    return request<{ ok: boolean; url: string; body?: string; error?: string }>("/api/v1/tame-vs/service/health");
  },

  tameVsSmokeTest() {
    return request<{
      request_id?: string;
      task?: string;
      input_csv?: string;
      fingerprint_csv?: string;
      score_csv?: string;
      preview?: Array<Record<string, unknown>>;
      compounds_count?: number;
      ingest?: { sdf_path?: string; converted_molecules?: number };
      fallback?: string;
    }>("/api/v1/tame-vs/smoke-test", { method: "POST" });
  },

  tameVsFull50kScreen(payload: { top_percent?: number; target_pdb_id?: string; auto_ingest?: boolean }) {
    return request<{
      request_id?: string;
      task?: string;
      input_csv?: string;
      fingerprint_csv?: string;
      score_csv?: string;
      top_csv?: string;
      top_count?: number;
      total_count?: number;
      top_percent?: number;
      preview?: Array<Record<string, unknown>>;
      ingest?: { sdf_path?: string; converted_molecules?: number };
    }>("/api/v1/tame-vs/full-50k-screen", { method: "POST", body: JSON.stringify(payload) });
  },

  tameVsPrepareLibrary(payload: { library_id: string; target_id?: string }) {
    return request<{ status: string; task_id: string; library_id: string }>("/api/v1/tame-vs/prepare-library", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  tameVsIngestResults(payload: { task_id: string; results_csv_path: string; library_id: string }) {
    return request<{ status: string; molecules_ingested: number }>("/api/v1/tame-vs/ingest-results", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  // ===== DrugCLIP =====
  drugclipStatus() {
    return request<{
      status: string;
      docker_available: boolean;
      service_healthy: boolean;
      package_exists: boolean;
      service_url: string;
      package_path: string;
    }>("/api/v1/drugclip/status");
  },

  drugclipStartService() {
    return request<{ ok: boolean }>("/api/v1/drugclip/service/start", { method: "POST", body: JSON.stringify({}) });
  },

  drugclipStopService() {
    return request<{ ok: boolean }>("/api/v1/drugclip/service/stop", { method: "POST", body: JSON.stringify({}) });
  },

  drugclipSmokeTest() {
    return request<{
      ok: boolean;
      screening?: { returned?: number };
      ingest?: { sdf_path?: string; converted_molecules?: number };
    }>("/api/v1/drugclip/smoke-test", { method: "POST" });
  },

  drugclipPipelineScreen(payload: { target_pdb_id: string; top_k?: number; auto_ingest?: boolean }) {
    return request<{
      ok: boolean;
      target_pdb_id?: string;
      screening?: { returned?: number; results?: Array<{ name?: string; smiles?: string; score?: number }> };
      ingest?: { sdf_path?: string; converted_molecules?: number };
    }>("/api/v1/drugclip/pipeline-screen", { method: "POST", body: JSON.stringify(payload) });
  },

  drugclipScreen(payload: { sdf_path: string; pocket_pdb_path: string; pocket_center?: number[]; pocket_radius?: number; top_k?: number; ingest?: boolean }) {
    return request<{ ok: boolean; screening: { results: Array<{ name: string; score: number }> }; ingest?: { sdf_path?: string; converted_molecules?: number } }>("/api/v1/drugclip/screen", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  // ===== Tasks =====
  listTasks(page = 1, page_size = 20) {
    return request<TaskListResponse>(`/api/v1/tasks?page=${page}&page_size=${page_size}`);
  },

  getTask(task_id: string) {
    return request<TaskItem>(`/api/v1/tasks/${task_id}`);
  },

  cancelTask(task_id: string) {
    return request<{ task_id: string; status: string }>(`/api/v1/tasks/${task_id}/cancel`, {
      method: "POST"
    });
  },

  retryTask(task_id: string) {
    return request<{ task_id: string; status: string }>(`/api/v1/tasks/${task_id}/retry`, {
      method: "POST"
    });
  },

  // ===== DiffGUI =====
  diffguiStatus() {
    return request<{
      ok: boolean;
      root: string;
      conda_env: string;
      conda_available?: boolean;
      gpu_available?: boolean;
    }>("/api/v1/diffgui/status");
  },

  diffguiGenerate(payload: {
    target_id?: string;
    protein_path?: string;
    round_id?: number;
    num_mols?: number;
    batch_size?: number;
    require_achiral?: boolean;
    pocket_file?: string;
    async_run?: boolean;
  }) {
    return request<{ ok?: boolean; job_id?: string; message?: string; sdf_path?: string }>(
      "/api/v1/diffgui/generate",
      { method: "POST", body: JSON.stringify(payload) }
    );
  },

  diffguiJob(job_id: string) {
    return request<{
      job_id: string;
      status: string;
      progress?: number;
      message?: string;
      error?: string;
      result?: Record<string, unknown>;
    }>(`/api/v1/diffgui/jobs/${job_id}`);
  },

  diffguiIngest(payload: { round_id: number; sdf_path?: string }) {
    return request<{ ok: boolean; sdf_path?: string; sync?: Record<string, unknown> }>(
      "/api/v1/diffgui/ingest",
      { method: "POST", body: JSON.stringify(payload) }
    );
  },

  // ===== DiffDynamic =====
  diffdynamicStatus() {
    return request<{
      conda_env: string;
      conda_env_exists?: boolean;
      root: string;
      root_exists?: boolean;
      runtime?: string;
      sampling_config?: string;
      sampling_config_exists?: boolean;
      protein_root?: string;
      protein_root_exists?: boolean;
      device?: string;
      scripts?: Record<string, boolean>;
    }>("/api/v1/diffdynamic/status");
  },

  diffdynamicGenerate(payload: {
    mode?: "dynamic" | "prudent" | "custom";
    target_id?: string;
    protein_path?: string;
    ligand_path?: string;
    data_id?: number;
    round_id?: number;
    batch_size?: number;
    sample_only?: boolean;
    auto_extract?: boolean;
    remove_fragments?: boolean;
    max_samples?: number;
    gpus?: string;
    async_run?: boolean;
  }) {
    return request<{
      ok?: boolean;
      job_id?: string;
      message?: string;
      sdf_path?: string;
      pt_path?: string;
      output_dir?: string;
    }>("/api/v1/diffdynamic/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  diffdynamicJob(job_id: string) {
    return request<{
      job_id: string;
      status: string;
      progress?: number;
      message?: string;
      error?: string;
      result?: Record<string, unknown>;
    }>(`/api/v1/diffdynamic/jobs/${job_id}`);
  },

  diffdynamicExtract(payload: {
    pt_file: string;
    output_dir?: string;
    remove_fragments?: boolean;
    max_samples?: number;
    async_run?: boolean;
  }) {
    return request<{ ok?: boolean; job_id?: string; sdf_path?: string }>(
      "/api/v1/diffdynamic/extract",
      { method: "POST", body: JSON.stringify(payload) }
    );
  },

  diffdynamicIngest(payload: { round_id: number; sdf_path?: string; pt_file?: string }) {
    return request<{ ok: boolean; sdf_path?: string; sync?: Record<string, unknown> }>(
      "/api/v1/diffdynamic/ingest",
      { method: "POST", body: JSON.stringify(payload) }
    );
  },

  // ===== GLARE =====
  glareStatus() {
    return request<{
      ok: boolean;
      root: string;
      checkpoints?: string[];
      checkpoint_count?: number;
      wetlab_count?: number;
    }>("/api/v1/glare/status");
  },

  glareScreen(payload: {
    round_id: number;
    evaluated_file?: string;
    pipeline_molecules?: Array<Record<string, unknown>>;
    checkpoint?: string;
    top_n?: number;
    wetlab_sample_count?: number;
    auto_ingest?: boolean;
    async_run?: boolean;
  }) {
    return request<{ ok?: boolean; job_id?: string; checkpoint?: string; evaluated_file?: string }>(
      "/api/v1/glare/screen",
      { method: "POST", body: JSON.stringify(payload) }
    );
  },

  glareTrain(payload: {
    round_id: number;
    evaluated_file?: string;
    pipeline_molecules?: Array<Record<string, unknown>>;
    run_seed_reinforce?: boolean;
    run_train?: boolean;
    wetlab_file?: string;
    previous_checkpoint?: string;
    async_run?: boolean;
  }) {
    return request<{ ok?: boolean; job_id?: string; evaluated_file?: string }>(
      "/api/v1/glare/train",
      { method: "POST", body: JSON.stringify(payload) }
    );
  },

  glareJob(job_id: string) {
    return request<{
      job_id: string;
      status: string;
      progress?: number;
      error?: string;
      result?: Record<string, unknown>;
    }>(`/api/v1/glare/jobs/${job_id}`);
  },

  async importWetlab(round_id: number, file: File): Promise<ApiResult<{ ok: boolean; wetlab_file?: string; wetlab_count?: number }>> {
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(`${getApiBaseUrl()}/api/v1/glare/import-wetlab?round_id=${round_id}`, {
        method: "POST",
        body: form,
        cache: "no-store",
      });
      if (!response.ok) {
        const text = await response.text();
        return { ok: false, status: response.status, error: text || `Request failed with ${response.status}` };
      }
      return { ok: true, data: (await response.json()) as { ok: boolean; wetlab_file?: string; wetlab_count?: number } };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : "Unknown request error" };
    }
  },

  // ===== RL Rounds =====
  listRLRounds(limit = 50) {
    return request<{ rounds: Array<Record<string, unknown>>; total: number }>(`/api/v1/rl-rounds?limit=${limit}`);
  },

  getRLRound(round_id: number) {
    return request<Record<string, unknown>>(`/api/v1/rl-rounds/${round_id}`);
  },

  createRLRound(payload: { round_id: number; target_id?: string; config_snapshot?: Record<string, unknown> }) {
    return request<Record<string, unknown>>("/api/v1/rl-rounds", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // ===== Scaffold extraction =====
  extractScaffolds(payload: { smiles_list?: string[]; library_id?: string; names?: string[] }) {
    return request<{
      stats: { total: number; success: number; failed: number; unique_generic: number; unique_framework: number };
      unique_scaffolds: Array<{ scaffold_smiles: string; member_count: number; representative_name: string; representative_smiles: string }>;
      molecule_count: number;
    }>("/api/v1/libraries/scaffolds/extract", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listScaffolds(library_id: string, min_members?: number) {
    const params = new URLSearchParams({ library_id });
    if (min_members) params.set("min_members", String(min_members));
    return request<{
      library_id: string;
      library_name: string;
      stats: { total: number; success: number; failed: number; unique_generic: number; unique_framework: number };
      scaffolds: Array<{ scaffold_smiles: string; member_count: number; representative_name: string; representative_smiles: string }>;
    }>(`/api/v1/libraries/scaffolds?${params}`);
  },

  getScaffoldMembers(library_id: string, scaffold_smiles: string) {
    return request<{
      scaffold_smiles: string;
      member_count: number;
      members: Array<{ idx: number; name: string; smiles: string }>;
    }>(`/api/v1/libraries/scaffolds/${encodeURIComponent(scaffold_smiles)}?library_id=${encodeURIComponent(library_id)}`);
  },

  // ===== RL closed-loop pipeline (legacy route /api/v1/vav1-rl) =====
  vav1RlRun(payload: { mode?: string; num_mols?: number; reuse_sdf_dir?: string; project_root?: string; steps?: number[] }) {
    return request<{ ok: boolean; job_id: string; mode: string; num_mols: number }>("/api/v1/vav1-rl/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  vav1RlStatus(job_id: string) {
    return request<Record<string, unknown>>(`/api/v1/vav1-rl/status/${job_id}`);
  },

  vav1RlRunStep(step: number, payload: { mode?: string; num_mols?: number; reuse_sdf_dir?: string; project_root?: string }) {
    return request<{ ok: boolean; step: number; result: Record<string, unknown>; funnel: Record<string, number> | null }>(
      `/api/v1/vav1-rl/steps/${step}/run`,
      { method: "POST", body: JSON.stringify(payload) }
    );
  },

  vav1RlFunnel() {
    return request<{ funnel: Record<string, Record<string, number>>; status: Record<string, unknown> }>("/api/v1/vav1-rl/funnel");
  },

  vav1RlArtifacts() {
    return request<{ project_root: string; files: Array<{ path: string; size: number }>; count: number }>("/api/v1/vav1-rl/artifacts");
  },

  vav1RlReport() {
    return request<{ ok: boolean; report_path: string; content: string | null }>("/api/v1/vav1-rl/report");
  },

  vav1RlTopMolecules(limit = 20) {
    return request<{
      ok: boolean;
      molecules: Array<{ smiles: string; name?: string; final_score?: string }>;
      source: string | null;
      count?: number;
      message?: string;
    }>(`/api/v1/vav1-rl/top-molecules?limit=${limit}`);
  },

  vav1RlHealth() {
    return request<{ schrodinger: Record<string, unknown>; glare_gnn: Record<string, unknown>; admet: Record<string, unknown> }>("/api/v1/vav1-rl/health");
  },

  // ===== Pipeline =====
  listPipelineTools() {
    return request<{ tools: Array<Record<string, unknown>> }>("/api/v1/pipeline/tools");
  },

  listPipelinePresets() {
    return request<{ presets: Array<Record<string, unknown>> }>("/api/v1/pipeline/presets");
  },

  listPipelineRuns(page = 1, pageSize = 20) {
    return request<{
      runs: Array<{
        id: string;
        status: string;
        recipe_json: Record<string, unknown>;
        context_json: Record<string, unknown>;
        current_step_id?: string;
        error_message?: string;
        created_at?: string;
        step_runs?: Array<Record<string, unknown>>;
      }>;
      pagination: Pagination;
    }>(`/api/v1/pipeline/runs?page=${page}&page_size=${pageSize}`);
  },

  createPipelineRun(payload: {
    recipe: { id?: string; name: string; description?: string; steps: unknown[] };
    context?: Record<string, unknown>;
    execute?: boolean;
  }) {
    return request<{
      id: string;
      status: string;
      recipe_json: Record<string, unknown>;
      context_json: Record<string, unknown>;
      step_runs: Array<Record<string, unknown>>;
    }>("/api/v1/pipeline/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getPipelineRun(runId: string) {
    return request<{
      id: string;
      status: string;
      recipe_json: Record<string, unknown>;
      context_json: Record<string, unknown>;
      current_step_id?: string;
      error_message?: string;
      step_runs: Array<{
        id: string;
        step_id: string;
        tool_ids: string[];
        status: string;
        progress: number;
        error_message?: string;
      }>;
    }>(`/api/v1/pipeline/runs/${runId}`);
  },

  resumePipelineRun(runId: string, fromStepId?: string) {
    const qs = fromStepId ? `?from_step_id=${encodeURIComponent(fromStepId)}` : "";
    return request<Record<string, unknown>>(`/api/v1/pipeline/runs/${runId}/resume${qs}`, { method: "POST" });
  },

  cancelPipelineRun(runId: string) {
    return request<{ id: string; status: string }>(`/api/v1/pipeline/runs/${runId}`, { method: "DELETE" });
  },

  analyzeWetlab(payload: {
    molecules: Array<{ smiles: string; name?: string; rank?: number }>;
    target_code?: string;
    batch_id?: string;
    check_pubchem?: boolean;
    dmso_concentration_mm?: number;
    dmso_volume_ml?: number;
  }) {
    return request<{
      status: string;
      total: number;
      wetlab_ready: number;
      blocked: number;
      molecules: Array<{
        compound_id: string;
        smiles: string;
        name?: string;
        rank?: number;
        molecular_weight?: number;
        sa_score?: number;
        synthesis_risk: string;
        chiral_centers: number;
        wetlab_ready: boolean;
        blockers: string[];
        notes: string[];
        structural_alerts: string[];
        structural_warnings: string[];
        dmso_stock_mg_10mm_1ml?: number;
        dmso_note?: string;
        pubchem_cid?: number;
        pubchem_url?: string;
        sourcing_hint?: string;
      }>;
    }>("/api/v1/wetlab/analyze", { method: "POST", body: JSON.stringify(payload) });
  },

  async exportWetlabOrderPack(payload: {
    molecules: Array<{ smiles: string; name?: string; rank?: number }>;
    target_code?: string;
    batch_id?: string;
    target_name?: string;
    assay_type?: string;
    cell_line?: string;
    target_protein?: string;
    round_id?: number;
    check_pubchem?: boolean;
  }): Promise<ApiResult<Blob>> {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/v1/wetlab/export-order-pack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({ message: response.statusText }));
        return { ok: false, error: (err as { message?: string }).message || "Export failed" };
      }
      return { ok: true, data: await response.blob() };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : "Network error" };
    }
  },
};
