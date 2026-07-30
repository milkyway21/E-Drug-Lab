import { apiClient } from "@/lib/api-client";
import { withStepResult } from "@/lib/merge-strategies";
import type { PipelineMolecule } from "@/lib/workflow-context";
import type { StepExecutor } from "./types";
import { loadMoleculesFromDb, pollJob } from "./helpers";

export const runVirtualScreenStep: StepExecutor = async (ctx, toolIds, params, actions) => {
  if (toolIds.length === 0) {
    return { ok: true, message: "Virtual screen skipped", molecules: ctx.molecules };
  }

  let molecules = ctx.molecules;
  const messages: string[] = [];
  const pdbId = params.pdbId || ctx.target?.pdbId || "4HHB";

  for (const toolId of toolIds) {
    if (toolId === "tame-vs") {
      const smoke = await apiClient.tameVsSmokeTest();
      if (!smoke.ok) return { ok: false, message: smoke.error };
      const sdfFilename = (smoke.data.ingest as { sdf_path?: string })?.sdf_path?.split(/[\\/]/).pop();
      molecules = await loadMoleculesFromDb("tame-vs", actions, sdfFilename);
      actions.setLibrarySource("screen");
      messages.push(`TAME-VS: ${molecules.length} molecules`);
    } else if (toolId === "drugclip") {
      const screen = await apiClient.drugclipPipelineScreen({
        target_pdb_id: pdbId,
        top_k: params.topK ?? 10,
        auto_ingest: true,
      });
      if (!screen.ok) return { ok: false, message: screen.error };
      const loaded = await loadMoleculesFromDb(
        "drugclip",
        actions,
        screen.data.ingest?.sdf_path?.split(/[\\/]/).pop()
      );
      const scoreBySmiles = new Map<string, number>();
      const scoreByName = new Map<string, number>();
      for (const item of screen.data.screening?.results || []) {
        if (typeof item.score === "number") {
          if (item.smiles) scoreBySmiles.set(item.smiles, item.score);
          if (item.name) scoreByName.set(item.name, item.score);
        }
      }
      molecules = loaded.map((molecule) => {
        const score = scoreBySmiles.get(molecule.smiles) ?? (molecule.name ? scoreByName.get(molecule.name) : undefined);
        if (score === undefined) return molecule;
        const vsResult = { score, method: "drugclip", model: "drugclip" };
        actions.updateStepResult(molecule.id, "drugclip", vsResult);
        return withStepResult([molecule], molecule.id, "drugclip", vsResult)[0];
      });
      actions.setLibrarySource("screen");
      messages.push(`DrugCLIP: ${molecules.length} molecules`);
    } else if (toolId === "glare-screen") {
      const glareStatus = await apiClient.glareStatus();
      const hasCheckpoint = Boolean(
        ctx.glareCheckpoint || (glareStatus.ok && (glareStatus.data.checkpoint_count ?? 0) > 0)
      );
      if (!hasCheckpoint) {
        messages.push("GLARE screen skipped (no checkpoint)");
        continue;
      }
      const pipelineMols = molecules.map((m) => ({
        id: m.id,
        smiles: m.smiles,
        name: m.name,
        properties: m.properties,
        stepResults: m.stepResults,
      }));
      const screen = await apiClient.glareScreen({
        round_id: ctx.roundId,
        pipeline_molecules: pipelineMols,
        checkpoint: ctx.glareCheckpoint || undefined,
        top_n: 50,
      });
      if (!screen.ok) return { ok: false, message: screen.error };
      const jobId = screen.data.job_id;
      if (jobId) {
        await pollJob(() => apiClient.glareJob(jobId), 60);
      }
      messages.push("GLARE screening complete");
    }
  }

  return { ok: true, message: messages.join("; "), molecules };
};
