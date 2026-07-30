import { apiClient } from "@/lib/api-client";
import type { PipelineMolecule, PipelineMoleculeInput } from "@/lib/workflow-context";
import type { WorkflowActions } from "./types";

export async function loadMoleculesFromDb(
  sourceLabel: string,
  actions: WorkflowActions,
  sdfFilename?: string
): Promise<PipelineMolecule[]> {
  const moleculesResponse = await apiClient.listMolecules({
    page_size: 200,
    sort_by: "created_at",
    sort_order: "desc",
    sdf_filename: sdfFilename,
  });
  if (!moleculesResponse.ok) {
    throw new Error(moleculesResponse.error);
  }

  const entries: PipelineMoleculeInput[] = moleculesResponse.data.molecules
    .filter((molecule) => molecule.smiles)
    .map((molecule) => ({
      smiles: molecule.smiles!,
      name: molecule.name || undefined,
      originalName: molecule.name || undefined,
      sourceMoleculeId: molecule.id,
      properties: {
        molecular_weight: molecule.molecular_weight,
        logp: molecule.logp,
        tpsa: molecule.tpsa,
        qed: molecule.qed,
        sa_score: molecule.sa_score,
      },
    }));

  if (entries.length === 0) {
    throw new Error("No molecules found in database");
  }

  actions.clearPipeline();
  return actions.addMolecules(entries, sourceLabel, { replace: true });
}

export async function pollJob<T>(
  fetchJob: () => Promise<{ ok: boolean; data?: { status: string; error?: unknown; result?: T }; error?: string }>,
  maxAttempts = 120,
  intervalMs = 3000
): Promise<T | null> {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const job = await fetchJob();
    if (!job.ok) break;
    const data = job.data!;
    if (data.status === "failed") {
      throw new Error(String(data.error || "Job failed"));
    }
    if (data.status === "completed") {
      return (data.result as T) ?? null;
    }
  }
  throw new Error("Job timeout");
}
