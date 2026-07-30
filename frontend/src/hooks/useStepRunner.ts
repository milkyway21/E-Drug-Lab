"use client";

import { useCallback, useState } from "react";
import { runStep, runRecipe } from "@/lib/step-executors";
import type { WorkflowActions } from "@/lib/step-executors/types";
import {
  contextFromWorkflow,
  type PipelineContext,
  type StepRunParams,
  type StepRunResult,
} from "@/lib/pipeline-context";
import type { PipelineRecipe } from "@/lib/tool-registry";
import { useWorkflow } from "@/lib/workflow-context";

export function useStepRunner() {
  const workflow = useWorkflow();
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<StepRunResult | null>(null);

  const actions: WorkflowActions = {
    addMolecules: workflow.addMolecules,
    clearPipeline: workflow.clearPipeline,
    updateStepResult: workflow.updateStepResult,
    updateMoleculeNames: workflow.updateMoleculeNames,
    filterByStep: workflow.filterByStep,
    setTarget: workflow.setTarget,
    setGlareCheckpoint: workflow.setGlareCheckpoint,
    setLibrarySource: workflow.setLibrarySource,
  };

  const getContext = useCallback(
    (runId?: string): PipelineContext =>
      contextFromWorkflow(
        workflow.molecules,
        workflow.target,
        workflow.roundId,
        workflow.glareCheckpoint,
        workflow.librarySource,
        runId
      ),
    [workflow.molecules, workflow.target, workflow.roundId, workflow.glareCheckpoint, workflow.librarySource]
  );

  const executeStep = useCallback(
    async (stepId: string, toolIds: string[], params: StepRunParams = {}): Promise<StepRunResult> => {
      setRunning(true);
      try {
        const ctx = getContext();
        const result = await runStep(stepId, toolIds, ctx, params, actions);
        setLastResult(result);
        if (result.contextUpdates?.target) workflow.setTarget(result.contextUpdates.target);
        if (result.contextUpdates?.glareCheckpoint) workflow.setGlareCheckpoint(result.contextUpdates.glareCheckpoint);
        return result;
      } finally {
        setRunning(false);
      }
    },
    [actions, getContext, workflow]
  );

  const executeRecipe = useCallback(
    async (
      recipe: PipelineRecipe,
      params: StepRunParams = {},
      onStepProgress?: (stepId: string, result: StepRunResult) => void
    ) => {
      setRunning(true);
      try {
        const ctx = getContext();
        const outcome = await runRecipe(recipe, ctx, params, actions, onStepProgress);
        return outcome;
      } finally {
        setRunning(false);
      }
    },
    [actions, getContext]
  );

  return {
    running,
    lastResult,
    executeStep,
    executeRecipe,
    getContext,
    actions,
    workflow,
  };
}
