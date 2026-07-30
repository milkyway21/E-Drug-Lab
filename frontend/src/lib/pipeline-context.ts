import type { PipelineMolecule, WorkflowTarget } from "@/lib/workflow-context";

export interface PipelineContext {
  runId?: string;
  target: WorkflowTarget | null;
  molecules: PipelineMolecule[];
  roundId: number;
  glareCheckpoint: string;
  librarySource: string | null;
}

export interface StepRunParams {
  pdbId?: string;
  targetMode?: "download" | "upload-protein" | "upload-ligand";
  ligandSmiles?: string;
  ligandName?: string;
  proteinFile?: File | null;
  ligandFile?: File | null;
  numMols?: number;
  topK?: number;
  [key: string]: unknown;
}

export interface StepRunResult {
  ok: boolean;
  message: string;
  molecules?: PipelineMolecule[];
  contextUpdates?: Partial<PipelineContext>;
  rankedRows?: Array<Record<string, unknown>>;
  summary?: { total: number; passed: number; failed: number };
}

export function validateStepContext(
  stepId: string,
  toolIds: string[],
  ctx: PipelineContext
): string | null {
  if (toolIds.length === 0) return null;

  const needsTarget = toolIds.some((id) => {
    const requires = ["target"];
    if (id === "drugclip" || id === "diffgui" || id === "diffdynamic" || id === "pdb-fetch") return true;
    if (id === "glide-dock") return true;
    return requires.length > 0 && (id === "pdb-fetch");
  });

  const needsMolecules = toolIds.some((id) =>
    ["rdkit-descriptors", "admet-ai", "vina-dock", "orthogonal-rank", "glare-train", "seed-reinforce", "wetlab-reinforce", "glare-screen"].includes(id)
  );

  if (stepId !== "target_prep" && needsMolecules && ctx.molecules.length === 0) {
    return "Pipeline has no molecules";
  }

  if ((stepId === "target_prep" || needsTarget) && !ctx.target && stepId !== "library_build") {
    return "Workflow target is required for this step";
  }

  return null;
}

export function contextFromWorkflow(
  molecules: PipelineMolecule[],
  target: WorkflowTarget | null,
  roundId: number,
  glareCheckpoint: string,
  librarySource: string | null,
  runId?: string
): PipelineContext {
  return { runId, target, molecules, roundId, glareCheckpoint, librarySource };
}

export function toApiContext(ctx: PipelineContext): Record<string, unknown> {
  return {
    run_id: ctx.runId,
    target: ctx.target,
    molecules: ctx.molecules.map((m) => ({
      id: m.id,
      smiles: m.smiles,
      name: m.name,
      originalName: m.originalName,
      standardName: m.standardName,
      source: m.source,
      sourceMoleculeId: m.sourceMoleculeId,
      status: m.status,
      properties: m.properties,
      stepResults: m.stepResults,
    })),
    round_id: ctx.roundId,
    glare_checkpoint: ctx.glareCheckpoint,
    library_source: ctx.librarySource,
  };
}
