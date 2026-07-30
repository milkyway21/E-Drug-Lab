import type { PipelineMolecule, PipelineMoleculeInput } from "@/lib/workflow-context";
import type { PipelineContext, StepRunParams, StepRunResult } from "@/lib/pipeline-context";

export interface WorkflowActions {
  addMolecules: (mols: PipelineMoleculeInput[], source: string, options?: { replace?: boolean }) => PipelineMolecule[];
  clearPipeline: () => void;
  updateStepResult: (id: string, stepKey: string, result: unknown) => void;
  updateMoleculeNames: (names: Array<{ id: string; standardName?: string | null; originalName?: string | null }>) => void;
  filterByStep: (stepKey: string, passedIds: string[], failedIds: string[]) => void;
  setTarget: (target: PipelineContext["target"]) => void;
  setGlareCheckpoint: (checkpoint: string) => void;
  setLibrarySource: (source: "diffgui" | "diffdynamic" | "sdf" | "screen" | null) => void;
}

export type ToolExecutor = (
  ctx: PipelineContext,
  params: StepRunParams,
  actions: WorkflowActions
) => Promise<StepRunResult>;

export type StepExecutor = (
  ctx: PipelineContext,
  toolIds: string[],
  params: StepRunParams,
  actions: WorkflowActions
) => Promise<StepRunResult>;
