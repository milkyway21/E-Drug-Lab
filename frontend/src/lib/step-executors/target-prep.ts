import { apiClient } from "@/lib/api-client";
import type { StepRunParams, StepRunResult } from "@/lib/pipeline-context";
import type { StepExecutor } from "./types";

export const runTargetPrepStep: StepExecutor = async (ctx, toolIds, params) => {
  if (toolIds.length === 0) {
    return { ok: true, message: "Target prep skipped" };
  }

  const toolId = toolIds[0];
  if (toolId !== "pdb-fetch") {
    return { ok: false, message: `Target tool ${toolId} not supported in pipeline executor` };
  }

  const mode = params.targetMode || "download";
  let target = ctx.target;
  let message = "";

  if (mode === "download") {
    const pdb = (params.pdbId || "4HHB").trim();
    const download = await apiClient.downloadTarget(pdb);
    if (!download.ok || download.data.status !== "downloaded") {
      return { ok: false, message: "Failed to download target" };
    }
    const created = await apiClient.createTarget({ pdb_id: pdb, name: `Pipeline ${pdb}` });
    if (created.ok) {
      await apiClient.preprocessTarget(created.data.id);
      target = { id: created.data.id, pdbId: pdb, name: created.data.name || `Pipeline ${pdb}`, source: "RCSB download" };
    } else {
      target = { pdbId: pdb, name: `Pipeline ${pdb}`, source: "RCSB download" };
    }
    message = `Downloaded: ${pdb}`;
  } else if (mode === "upload-protein") {
    const file = params.proteinFile;
    if (!file) return { ok: false, message: "No protein file selected" };
    const upload = await apiClient.uploadProtein(file, file.name);
    if (!upload.ok || upload.data.status !== "uploaded") {
      return { ok: false, message: upload.ok ? "Upload failed" : upload.error };
    }
    await apiClient.preprocessTarget(upload.data.target_id);
    target = { id: upload.data.target_id, name: upload.data.filename, source: "file upload" };
    message = `Uploaded: ${upload.data.filename}`;
  } else {
    const ligandFile = params.ligandFile;
    const ligandResult = ligandFile
      ? await apiClient.uploadLigand(ligandFile, params.ligandName || ligandFile.name)
      : params.ligandSmiles?.trim()
        ? await apiClient.uploadLigand(params.ligandSmiles.trim(), params.ligandName || "ligand")
        : null;
    if (!ligandResult?.ok || (ligandResult.data as Record<string, unknown>).status === "error") {
      return { ok: false, message: ligandResult?.ok ? "Invalid ligand" : ligandResult?.error || "No ligand" };
    }
    target = { name: params.ligandName || "reference", source: "ligand input" };
    message = "Ligand ready";
  }

  return {
    ok: true,
    message,
    molecules: ctx.molecules,
    contextUpdates: { target },
  };
};
