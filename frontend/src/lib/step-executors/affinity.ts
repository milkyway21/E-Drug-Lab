import { apiClient, type SchrodingerDockResult } from "@/lib/api-client";
import { withStepResult } from "@/lib/merge-strategies";
import { pollJob } from "./helpers";
import type { StepExecutor } from "./types";

function schrodingerParams(params: Record<string, unknown>) {
  return {
    precision: (params.schrodingerPrecision as "HTVS" | "SP" | "XP") || "SP",
    ph: Number(params.schrodingerPh ?? 7.2),
    ph_threshold: Number(params.schrodingerPhThreshold ?? 0.2),
    outer_box: Number(params.schrodingerOuterBox ?? 20),
    poses_per_lig: Number(params.schrodingerPoses ?? 5),
    postdock_minimize: params.schrodingerPostMinimize !== false,
    center_x: params.schrodingerCenterX != null ? Number(params.schrodingerCenterX) : undefined,
    center_y: params.schrodingerCenterY != null ? Number(params.schrodingerCenterY) : undefined,
    center_z: params.schrodingerCenterZ != null ? Number(params.schrodingerCenterZ) : undefined,
    async_run: params.schrodingerAsync !== false,
  };
}

function applySchrodingerResults(
  updated: Parameters<typeof withStepResult>[0],
  result: SchrodingerDockResult,
  actions: { updateStepResult: (id: string, key: string, data: Record<string, unknown>) => void },
  runMmgbsa: boolean
) {
  const outputFiles = result.output_files || {};
  let next = updated;
  let succeeded = 0;

  for (const item of result.molecule_results || []) {
    const glideData = {
      glide_score: item.glide_score,
      glide_rmsd: item.glide_rmsd,
      precision: result.precision,
      success: item.success,
      pose_maegz: outputFiles.poses_maegz,
      receptor_maegz: outputFiles.receptor_maegz,
      output_dir: result.output_dir,
      timestamp: new Date().toISOString(),
    };
    actions.updateStepResult(item.molecule_id, "glide-dock", glideData);
    next = withStepResult(next, item.molecule_id, "glide-dock", glideData);

    if (runMmgbsa && item.mmgbsa_dg != null) {
      const mmgbsaData = {
        mmgbsa_dg: item.mmgbsa_dg,
        pose_maegz: outputFiles.poses_maegz,
        receptor_maegz: outputFiles.receptor_maegz,
        success: true,
        timestamp: new Date().toISOString(),
      };
      actions.updateStepResult(item.molecule_id, "mm-gbsa", mmgbsaData);
      next = withStepResult(next, item.molecule_id, "mm-gbsa", mmgbsaData);
    }

    if (item.success) succeeded += 1;
  }

  return { next, succeeded };
}

export const runAffinityStep: StepExecutor = async (ctx, toolIds, params, actions) => {
  if (toolIds.length === 0) {
    return { ok: true, message: "Affinity eval skipped", molecules: ctx.molecules };
  }

  if (ctx.molecules.length === 0) {
    return { ok: false, message: "No molecules in pipeline" };
  }

  let updated = ctx.molecules;
  const messages: string[] = [];
  const targetPdbId = params.pdbId || ctx.target?.pdbId;
  const wantsGlide = toolIds.includes("glide-dock");
  const wantsMmgbsa = toolIds.includes("mm-gbsa");

  if (toolIds.includes("vina-dock")) {
    const vinaVersion = await apiClient.vinaVersion();
    const dock = await apiClient.dockSmilesBatch({
      molecules: updated.map((molecule) => ({
        molecule_id: molecule.id,
        smiles: molecule.smiles,
        name: molecule.originalName || molecule.name || molecule.smiles.slice(0, 20),
      })),
      target_id: ctx.target?.id,
      target_pdb_id: targetPdbId,
      exhaustiveness: 4,
      timeout_per_molecule: 20,
      concurrency: 2,
    });

    if (!dock.ok) return { ok: false, message: dock.error };

    if (!dock.data.vina_available || dock.data.method === "unavailable") {
      return {
        ok: false,
        message: "Vina unavailable — install AutoDock Vina or use VS scores for ranking",
      };
    }

    let succeeded = 0;
    for (const item of dock.data.results) {
      const result = {
        name: item.name,
        smiles: item.smiles,
        affinity_kcal_mol: item.affinity_kcal_mol,
        model: item.model,
        method: item.method,
        success: item.success,
        error: item.error,
        poses_count: item.poses_count,
        version: vinaVersion.ok ? vinaVersion.data.version : null,
        timestamp: new Date().toISOString(),
      };
      actions.updateStepResult(item.molecule_id, "vina-dock", result);
      updated = withStepResult(updated, item.molecule_id, "vina-dock", result);
      if (item.success) succeeded += 1;
    }

    if (succeeded === 0) {
      return { ok: false, message: `Vina docking failed for all ${updated.length} molecules` };
    }
    messages.push(`${succeeded}/${updated.length} docked with Vina`);
  }

  if (wantsGlide || wantsMmgbsa) {
    const status = await apiClient.schrodingerStatus();
    if (!status.ok || !status.data.available) {
      return {
        ok: false,
        message: status.ok ? status.data.message : status.error || "Schrödinger not available",
      };
    }
  }

  if (wantsGlide) {
    const schParams = schrodingerParams(params);
    const runMmgbsa = wantsMmgbsa || params.schrodingerRunMmgbsa === true;
    const dock = await apiClient.schrodingerPipelineDock({
      molecules: updated.map((molecule) => ({
        molecule_id: molecule.id,
        smiles: molecule.smiles,
        name: molecule.originalName || molecule.name || molecule.smiles.slice(0, 20),
      })),
      target_id: ctx.target?.id,
      target_pdb_id: targetPdbId,
      ...schParams,
      run_mmgbsa: runMmgbsa,
    });

    if (!dock.ok) return { ok: false, message: dock.error };

    let result: SchrodingerDockResult | null;
    if (schParams.async_run && dock.data.job_id) {
      result = await pollJob(
        () => apiClient.schrodingerJob(dock.data.job_id),
        400,
        5000
      );
    } else {
      result = dock.data as unknown as SchrodingerDockResult;
    }

    if (!result) {
      return { ok: false, message: "Schrödinger dock job returned no result" };
    }
    if (!result.ok && !(result.molecule_results?.length)) {
      return { ok: false, message: result.error || "Schrödinger Glide dock failed" };
    }

    const applied = applySchrodingerResults(updated, result, actions, runMmgbsa);
    updated = applied.next;
    messages.push(
      `${applied.succeeded}/${updated.length} scored with Glide ${result.precision || schParams.precision}` +
        (runMmgbsa ? " (+ MM-GBSA)" : "")
    );
  } else if (wantsMmgbsa) {
    const glideResult = updated
      .map((m) => m.stepResults?.["glide-dock"] as Record<string, unknown> | undefined)
      .find((r) => r?.pose_maegz);
    const poseMaegz = glideResult?.pose_maegz as string | undefined;
    if (!poseMaegz) {
      return { ok: false, message: "MM-GBSA 需要先运行 Glide 对接，或勾选「对接后自动 MM-GBSA」" };
    }

    const mmgbsa = await apiClient.mmgbsa({
      pose_maegz: poseMaegz,
      receptor_maegz: glideResult?.receptor_maegz as string | undefined,
    });
    if (!mmgbsa.ok) return { ok: false, message: mmgbsa.error };
    if (mmgbsa.data.status !== "completed") {
      return { ok: false, message: mmgbsa.data.message || "MM-GBSA failed" };
    }

    const scoresByTitle = new Map(
      (mmgbsa.data.scores || []).map((s) => [s.title, s.mmgbsa_dg])
    );
    let scored = 0;
    for (const molecule of updated) {
      const title =
        (molecule.originalName || molecule.name || molecule.id) as string;
      const dg = scoresByTitle.get(title) ?? mmgbsa.data.scores?.[0]?.mmgbsa_dg ?? null;
      if (dg == null) continue;
      const mmgbsaData = {
        mmgbsa_dg: dg,
        pose_maegz: poseMaegz,
        success: true,
        timestamp: new Date().toISOString(),
      };
      actions.updateStepResult(molecule.id, "mm-gbsa", mmgbsaData);
      updated = withStepResult(updated, molecule.id, "mm-gbsa", mmgbsaData);
      scored += 1;
    }
    messages.push(`MM-GBSA scored ${scored}/${updated.length} molecules`);
  }

  return { ok: true, message: messages.join("; ") || "Affinity complete", molecules: updated };
};
