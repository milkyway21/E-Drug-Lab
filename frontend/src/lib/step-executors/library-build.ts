import { apiClient } from "@/lib/api-client";
import { withStepResult } from "@/lib/merge-strategies";
import type { PipelineMolecule } from "@/lib/workflow-context";
import type { StepExecutor } from "./types";
import { loadMoleculesFromDb, pollJob } from "./helpers";

export const runLibraryBuildStep: StepExecutor = async (ctx, toolIds, params, actions) => {
  if (toolIds.length === 0) {
    return { ok: true, message: "Library build skipped", molecules: ctx.molecules };
  }

  let molecules = ctx.molecules;
  const messages: string[] = [];

  for (const toolId of toolIds) {
    if (toolId === "diffgui") {
      const gen = await apiClient.diffguiGenerate({
        target_id: ctx.target?.id,
        round_id: ctx.roundId,
        num_mols: params.numMols ?? 5,
        batch_size: 5,
        require_achiral: true,
      });
      if (!gen.ok) return { ok: false, message: gen.error };
      const jobId = gen.data.job_id;
      if (jobId) {
        await pollJob(() => apiClient.diffguiJob(jobId));
        await apiClient.diffguiIngest({ round_id: ctx.roundId });
        molecules = await loadMoleculesFromDb("diffgui", actions, `diffgui_round_${ctx.roundId}.sdf`);
        actions.setLibrarySource("diffgui");
        messages.push(`${molecules.length} molecules from DiffGUI`);
      }
    } else if (toolId === "diffdynamic") {
      const gen = await apiClient.diffdynamicGenerate({
        target_id: ctx.target?.id,
        round_id: ctx.roundId,
        mode: ctx.target ? "custom" : "dynamic",
        data_id: (params.dataId as number | undefined) ?? 0,
        batch_size: 5,
        auto_extract: true,
        max_samples: 5,
        remove_fragments: true,
      });
      if (!gen.ok) return { ok: false, message: gen.error };
      const jobId = gen.data.job_id;
      if (jobId) {
        const jobResult = await pollJob(() => apiClient.diffdynamicJob(jobId));
        const sdfPath =
          (jobResult as { sdf_path?: string } | null)?.sdf_path ||
          (jobResult as { extract?: { sdf_path?: string } } | null)?.extract?.sdf_path;
        await apiClient.diffdynamicIngest({ round_id: ctx.roundId, sdf_path: sdfPath });
        molecules = await loadMoleculesFromDb("diffdynamic", actions, `diffdynamic_round_${ctx.roundId}.sdf`);
        actions.setLibrarySource("diffdynamic");
        messages.push(`${molecules.length} molecules from DiffDynamic`);
      }
    } else if (toolId === "sdf-upload") {
      const sync = await apiClient.syncMolecules();
      if (!sync.ok) return { ok: false, message: sync.error };
      const loaded = await loadMoleculesFromDb("sdf-upload", actions);
      molecules = loaded;
      actions.setLibrarySource("sdf");
      messages.push(`${loaded.length} molecules from SDF`);
    } else if (toolId === "scaffold-extract") {
      const smiles = ctx.molecules.map((m) => m.smiles);
      if (smiles.length === 0) return { ok: false, message: "No molecules for scaffold extraction" };
      const result = await apiClient.extractScaffolds({
        smiles_list: smiles,
        names: ctx.molecules.map((m) => m.name || m.originalName || ""),
      });
      if (!result.ok) return { ok: false, message: result.error };
      messages.push(`Scaffolds extracted: ${result.data.stats?.unique_generic ?? "done"}`);
    }
  }

  return { ok: true, message: messages.join("; ") || "Library build complete", molecules };
};
