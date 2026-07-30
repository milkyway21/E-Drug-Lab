import { apiClient } from "@/lib/api-client";
import type { StepExecutor } from "./types";
import { pollJob } from "./helpers";

export const runRlTrainStep: StepExecutor = async (ctx, toolIds, params, actions) => {
  if (toolIds.length === 0) {
    return { ok: true, message: "RL training skipped", molecules: ctx.molecules };
  }

  if (ctx.molecules.length === 0) {
    return { ok: false, message: "No molecules for RL training" };
  }

  const toolId = toolIds[0];
  const pipelineMols = ctx.molecules.map((m) => ({
    id: m.id,
    smiles: m.smiles,
    name: m.name,
    properties: m.properties,
    stepResults: m.stepResults,
  }));

  if (toolId === "wetlab-reinforce") {
    return { ok: false, message: "Wet-lab reinforce requires wet-lab data import (use RL training page)" };
  }

  const train = await apiClient.glareTrain({
    round_id: ctx.roundId,
    pipeline_molecules: pipelineMols,
    run_seed_reinforce: toolId === "seed-reinforce" || toolId === "glare-train",
    run_train: toolId === "glare-train",
  });

  if (!train.ok) return { ok: false, message: train.error };

  const jobId = train.data.job_id;
  if (jobId) {
    const result = await pollJob<{
      train?: { checkpoint?: string };
      seed_reinforce?: { checkpoint?: string };
    }>(() => apiClient.glareJob(jobId));
    const ckpt = result?.train?.checkpoint || result?.seed_reinforce?.checkpoint;
    if (ckpt) actions.setGlareCheckpoint(ckpt);
    return {
      ok: true,
      message: ckpt ? `Checkpoint: ${ckpt.split("/").pop()}` : "RL training complete",
      molecules: ctx.molecules,
      contextUpdates: ckpt ? { glareCheckpoint: ckpt } : undefined,
    };
  }

  return { ok: true, message: "RL training submitted", molecules: ctx.molecules };
};

export const runVav1Step: StepExecutor = async (ctx, toolIds) => {
  if (toolIds.length === 0) {
    return { ok: true, message: "RL pipeline skipped", molecules: ctx.molecules };
  }

  const run = await apiClient.vav1RlRun({});
  if (!run.ok) return { ok: false, message: run.error };

  const jobId = run.data.job_id;
  if (jobId) {
    for (let i = 0; i < 180; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      const status = await apiClient.vav1RlStatus(jobId);
      if (!status.ok) break;
      const state = String((status.data as Record<string, unknown>).status ?? "");
      if (state === "failed") {
        return { ok: false, message: String((status.data as Record<string, unknown>).error || "RL pipeline failed") };
      }
      if (state === "completed") break;
    }
  }

  return { ok: true, message: "RL pipeline submitted", molecules: ctx.molecules };
};
