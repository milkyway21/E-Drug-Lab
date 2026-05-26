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
  id?: string;
  pdb_id?: string;
  name?: string;
  source?: string;
  status?: string;
};

export type Library = {
  id?: string;
  name?: string;
  source?: string;
  status?: string;
  filename?: string;
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

export type MoleculeListResponse = {
  molecules: SDFMolecule[];
  pagination: Pagination;
  request_id: string;
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
  request_id: string;
};

export type OrthogonalRankedCandidate = {
  molecule_id: string;
  name: string | null;
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

export type OrthogonalRescoreResponse = {
  method: string;
  selection_rule: string;
  final_score_rule: string;
  ranked: OrthogonalRankedCandidate[];
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

export type SyncResultResponse = {
  status: string;
  sdf_directory: string;
  sync_result: {
    total_files_found: number;
    new_files: number;
    updated_files: number;
    unchanged_files: number;
    deleted_records: number;
    total_conformers_added: number;
    errors: Array<{ file: string; error: string; conformer?: number }>;
    files_processed: string[];
  };
};

export type MoleculeDBStats = {
  total_molecules: number;
  total_sdf_files: number;
  statistics: {
    molecular_weight: { avg: number | null; min: number | null; max: number | null };
    logp_avg: number | null;
    qed_avg: number | null;
    tpsa_avg: number | null;
    rotatable_bonds_avg: number | null;
  };
};

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string; status?: number };

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

async function request<T>(
  path: string,
  init?: RequestInit,
  fallback: T | null = null
): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
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
  apiBaseUrl: API_BASE_URL,

  health() {
    return request<{ status: string }>("/health", undefined, { status: "offline" });
  },

  readiness() {
    return request<ReadinessResponse>("/ready", undefined, {
      status: "degraded",
      tools_available: 0,
      tools_total: 0,
      tools: {}
    });
  },

  listTargets(page = 1) {
    return request<{ targets: Target[]; pagination: Pagination }>(
      `/api/v1/targets?page=${page}`
    );
  },

  createTarget(payload: { pdb_id?: string; name?: string; fasta_sequence?: string }) {
    return request<Target>("/api/v1/targets", {
      method: "POST",
      body: JSON.stringify({ ...payload, source: payload.pdb_id ? "pdb" : "sequence" })
    });
  },

  downloadTarget(pdb_id: string) {
    return request<{ status: string; pdb_id: string }>("/api/v1/targets/download", {
      method: "POST",
      body: JSON.stringify({ pdb_id })
    });
  },

  listLibraries(page = 1) {
    return request<{ libraries: Library[]; pagination: Pagination }>(
      `/api/v1/libraries?page=${page}`
    );
  },

  createLibrary(payload: { name: string; source: string; description?: string }) {
    return request<Library>("/api/v1/libraries", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  listMolecules(params: Record<string, string | number | undefined> = {}) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") search.set(key, String(value));
    });
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return request<MoleculeListResponse>(`/api/v1/molecule-db/molecules${suffix}`);
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

  moleculeStats() {
    return request<MoleculeDBStats>("/api/v1/molecule-db/stats");
  },

  orthogonalDemo() {
    return request<OrthogonalRescoreResponse>("/api/v1/ranking/orthogonal-demo", undefined, {
      method: "orthogonal_rescore_v1",
      selection_rule: "preferred model, otherwise median observed value; never mean",
      final_score_rule: "orthogonal desirability minus artifact penalty",
      ranked: [
        {
          molecule_id: "ibuprofen",
          name: "Ibuprofen",
          primary_value: -7.4,
          orthogonal_value: -31.0,
          primary_desirability: 50,
          orthogonal_desirability: 83.3333,
          consistency_gap: -33.3333,
          final_score: 83.3333,
          artifact_flag: false,
          artifact_reason: null,
          selected_primary_model: "vina",
          selected_orthogonal_model: "mmgbsa"
        },
        {
          molecule_id: "aspirin",
          name: "Aspirin",
          primary_value: -7.1,
          orthogonal_value: -28.0,
          primary_desirability: 16.6667,
          orthogonal_desirability: 50,
          consistency_gap: -33.3333,
          final_score: 50,
          artifact_flag: false,
          artifact_reason: null,
          selected_primary_model: "vina",
          selected_orthogonal_model: "mmgbsa"
        },
        {
          molecule_id: "artifact-001",
          name: "Potential scoring artifact",
          primary_value: -11.5,
          orthogonal_value: -9.0,
          primary_desirability: 83.3333,
          orthogonal_desirability: 16.6667,
          consistency_gap: 66.6666,
          final_score: 0,
          artifact_flag: true,
          artifact_reason: "Primary score is strong, but orthogonal rescoring is weak; treat as a possible scoring-function artifact.",
          selected_primary_model: "vina",
          selected_orthogonal_model: "mmgbsa"
        }
      ]
    });
  }
};
