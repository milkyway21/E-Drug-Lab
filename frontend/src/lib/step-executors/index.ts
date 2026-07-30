import {
  STEP_ID_ADMET,
  STEP_ID_AFFINITY,
  STEP_ID_LIBRARY_BUILD,
  STEP_ID_RANKING,
  STEP_ID_RL_TRAIN,
  STEP_ID_TARGET_PREP,
  STEP_ID_VAV1_RL,
  STEP_ID_VIRTUAL_SCREEN,
  getStep,
  getTool,
} from "@/lib/tool-registry";
import type { PipelineContext, StepRunParams, StepRunResult } from "@/lib/pipeline-context";
import { validateStepContext } from "@/lib/pipeline-context";
import type { WorkflowActions } from "./types";
import { runTargetPrepStep } from "./target-prep";
import { runLibraryBuildStep } from "./library-build";
import { runVirtualScreenStep } from "./virtual-screen";
import { runAdmetStep } from "./admet";
import { runAffinityStep } from "./affinity";
import { runRankingStep } from "./ranking";
import { runRlTrainStep, runVav1Step } from "./rl-train";

const STEP_EXECUTORS: Record<string, typeof runTargetPrepStep> = {
  [STEP_ID_TARGET_PREP]: runTargetPrepStep,
  [STEP_ID_LIBRARY_BUILD]: runLibraryBuildStep,
  [STEP_ID_VIRTUAL_SCREEN]: runVirtualScreenStep,
  [STEP_ID_ADMET]: runAdmetStep,
  [STEP_ID_AFFINITY]: runAffinityStep,
  [STEP_ID_RANKING]: runRankingStep,
  [STEP_ID_RL_TRAIN]: runRlTrainStep,
  [STEP_ID_VAV1_RL]: runVav1Step,
};

export async function runStep(
  stepId: string,
  toolIds: string[],
  ctx: PipelineContext,
  params: StepRunParams,
  actions: WorkflowActions
): Promise<StepRunResult> {
  const validationError = validateStepContext(stepId, toolIds, ctx);
  if (validationError) {
    return { ok: false, message: validationError };
  }

  const executor = STEP_EXECUTORS[stepId];
  if (!executor) {
    return { ok: false, message: `No executor for step: ${stepId}` };
  }

  const stepSpec = getStep(stepId);
  const implementedTools = toolIds.filter((id) => {
    try {
      const tool = getTool(id);
      return tool.status === "implemented" || tool.status === "partial";
    } catch {
      return false;
    }
  });

  if (implementedTools.length === 0 && toolIds.length > 0) {
    return { ok: false, message: `No runnable tools selected for ${stepSpec?.titleKey || stepId}` };
  }

  return executor(ctx, implementedTools, params, actions);
}

export async function runRecipe(
  recipe: { steps: Array<{ stepId: string; enabled: boolean; toolIds: string[]; params?: Record<string, unknown> }> },
  initialCtx: PipelineContext,
  params: StepRunParams,
  actions: WorkflowActions,
  onStepProgress?: (stepId: string, result: StepRunResult) => void
): Promise<{ ok: boolean; ctx: PipelineContext; error?: string }> {
  let ctx = { ...initialCtx };

  for (const step of recipe.steps) {
    if (!step.enabled) continue;

    const result = await runStep(step.stepId, step.toolIds, ctx, { ...params, ...step.params }, actions);
    onStepProgress?.(step.stepId, result);

    if (!result.ok) {
      return { ok: false, ctx, error: result.message };
    }

    if (result.molecules) {
      ctx = { ...ctx, molecules: result.molecules };
    }
    if (result.contextUpdates) {
      ctx = { ...ctx, ...result.contextUpdates };
      if (result.contextUpdates.target) actions.setTarget(result.contextUpdates.target);
      if (result.contextUpdates.glareCheckpoint) actions.setGlareCheckpoint(result.contextUpdates.glareCheckpoint);
    }
  }

  return { ok: true, ctx };
}

export { STEP_EXECUTORS };
