import { apiClient } from "@/lib/api-client";
import { mergeAllMustPass, withStepResult, withStatuses } from "@/lib/merge-strategies";
import type { StepExecutor } from "./types";

export const runAdmetStep: StepExecutor = async (ctx, toolIds, params, actions) => {
  if (toolIds.length === 0) {
    return { ok: true, message: "ADMET skipped", molecules: ctx.molecules };
  }

  if (ctx.molecules.length === 0) {
    return { ok: false, message: "No molecules in pipeline" };
  }

  let updated = ctx.molecules;
  const passedIdsPerTool: string[][] = [];
  const smiles = updated.map((m) => m.smiles);
  const names = updated.map((m) => m.originalName || m.name || m.smiles.slice(0, 20));

  const requestedTools = toolIds.filter((id) => id === "rdkit-descriptors" || id === "admet-ai");
  let toolsAttempted = 0;
  let toolsSucceeded = 0;

  if (toolIds.includes("rdkit-descriptors")) {
    toolsAttempted += 1;
    const filter = await apiClient.filterAdmet({ smiles, names, rules: ["lipinski", "veber"] });
    if (filter.ok) {
      toolsSucceeded += 1;
      const passed: string[] = [];
      const failed: string[] = [];
      const resultsList = filter.data.results as Array<Record<string, unknown>>;
      resultsList.forEach((result, index) => {
        if (index >= updated.length) return;
        actions.updateStepResult(updated[index].id, "rdkit-filter", result);
        updated = withStepResult(updated, updated[index].id, "rdkit-filter", result);
        if (result.passed) passed.push(updated[index].id);
        else failed.push(updated[index].id);
      });
      passedIdsPerTool.push(passed);
    }
  }

  if (toolIds.includes("admet-ai")) {
    toolsAttempted += 1;
    const predict = await apiClient.predictAdmet({ smiles, names });
    if (predict.ok) {
      toolsSucceeded += 1;
      const passed: string[] = [];
      const failed: string[] = [];
      predict.data.predictions.forEach((prediction, index) => {
        if (index >= updated.length) return;
        actions.updateStepResult(updated[index].id, "admet-ai", prediction);
        updated = withStepResult(updated, updated[index].id, "admet-ai", prediction);
        const props = (prediction?.properties || {}) as Record<string, number>;
        const d = props.DILI ?? 0.5;
        const h = props.hERG ?? 0.5;
        const a = props.AMES ?? 0.5;
        const hia = props.HIA_Hou ?? 0.5;
        if (d < 0.7 && h < 0.3 && a < 0.3 && hia > 0.3) passed.push(updated[index].id);
        else failed.push(updated[index].id);
      });
      passedIdsPerTool.push(passed);
    }
  }

  if (toolsAttempted > 0 && toolsSucceeded === 0) {
    return { ok: false, message: "ADMET API failed — no results returned", molecules: ctx.molecules };
  }

  if (requestedTools.length > 0 && passedIdsPerTool.length < requestedTools.length) {
    return {
      ok: false,
      message: `ADMET incomplete (${passedIdsPerTool.length}/${requestedTools.length} tools succeeded)`,
      molecules: ctx.molecules,
    };
  }

  const merged = mergeAllMustPass(updated, passedIdsPerTool);
  actions.filterByStep("admet", merged.passedIds, merged.failedIds);

  return {
    ok: true,
    message: `${merged.passedIds.length}/${updated.length} passed ADMET`,
    molecules: merged.molecules,
  };
};
