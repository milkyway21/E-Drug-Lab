"use client";

import { useState } from "react";
import { Cpu } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { ModelSelector } from "@/components/workflow/ModelSelector";
import { ResultCard, type StepResult } from "@/components/workflow/ResultCard";
import { getStepByHref } from "@/lib/tool-registry";
import { apiClient, type Target } from "@/lib/api-client";
import { useLang } from "@/lib/i18n/i18n-context";
import { useWorkflow } from "@/lib/workflow-context";

export default function TargetPrepPage() {
  const { t } = useLang();
  const { setTarget: setWorkflowTarget } = useWorkflow();
  const stepConfig = getStepByHref("/workflow/target-prep")!;
  const [pdbId, setPdbId] = useState("8v1t");
  const [name, setName] = useState("8V1T pipeline target");
  const [target, setTarget] = useState<Target | null>(null);
  const [results, setResults] = useState<Record<string, StepResult>>({});
  const [running, setRunning] = useState(false);

  function setModelResult(modelId: string, result: StepResult) {
    setResults((prev) => ({ ...prev, [modelId]: result }));
  }

  async function handleRun(selectedIds: string[]) {
    setRunning(true);
    for (const modelId of selectedIds) {
      if (modelId === "pdb-fetch") await runRcsbDownload();
      else if (modelId === "alphafold") await runAlphaFold();
      else setModelResult(modelId, { status: "error", message: t("statusNotImplemented") });
    }
    setRunning(false);
  }

  async function runAlphaFold() {
    setModelResult("alphafold", { status: "loading", message: t("statusCreating") });
    const result = await apiClient.predictStructure({ fasta_sequence: "", model_type: "alphafold3" });
    if (result.ok) {
      setModelResult("alphafold", { status: "done", message: "AlphaFold prediction queued.", data: result.data as Record<string, unknown> });
    } else {
      setModelResult("alphafold", { status: "error", message: result.error });
    }
  }

  async function runRcsbDownload() {
    setModelResult("pdb-fetch", { status: "loading", message: t("statusCreating") });
    const createResult = await apiClient.createTarget({ pdb_id: pdbId, name });
    if (!createResult.ok) { setModelResult("pdb-fetch", { status: "error", message: createResult.error }); return; }
    setTarget(createResult.data);

    setModelResult("pdb-fetch", { status: "loading", message: `${t("statusDownloading")} PDB ${pdbId}...` });
    const downloadResult = await apiClient.downloadTarget(pdbId);
    if (!downloadResult.ok) { setModelResult("pdb-fetch", { status: "error", message: downloadResult.error }); return; }

    setModelResult("pdb-fetch", { status: "loading", message: t("statusPreprocessing") });
    const preprocessResult = await apiClient.preprocessTarget(createResult.data.id);
    if (preprocessResult.ok) {
      setWorkflowTarget({
        id: createResult.data.id,
        pdbId: createResult.data.pdb_id || pdbId,
        name: createResult.data.name || name,
        source: "RCSB download",
      });
      setModelResult("pdb-fetch", {
        status: "done", message: `PDB ${pdbId} ${t("commonReady")}.`,
        data: { ID: createResult.data.id, "PDB ID": createResult.data.pdb_id ?? "—", Name: createResult.data.name ?? "—", Status: preprocessResult.data.status },
      });
    } else { setModelResult("pdb-fetch", { status: "error", message: preprocessResult.error }); }
  }

  return (
    <WorkflowShell current="/workflow/target-prep">
      <WorkflowHeader badge={t("targetPrepBadge")} title={t("targetPrepTitle")} description={t("targetPrepDesc")} />

      <div className="panel p-6">
        <div className="flex items-center gap-2 mb-4">
          <Cpu size={16} className="text-primary" />
          <h3 className="font-display text-sm font-bold text-ink">{t("targetPrepParams")}</h3>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="stat-label">{t("targetPrepPdbId")}</span>
            <input value={pdbId} onChange={(e) => setPdbId(e.target.value)} placeholder="e.g. 4HHB" className="input-field mt-2 font-mono" />
          </label>
          <label className="block">
            <span className="stat-label">{t("targetPrepName")}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Hemoglobin" className="input-field mt-2" />
          </label>
        </div>
      </div>

      <div className="mt-4"><ModelSelector models={stepConfig.models} onRun={handleRun} running={running} /></div>
      {Object.entries(results).map(([modelId, result]) => {
        const model = stepConfig.models.find((m) => m.id === modelId);
        return <ResultCard key={modelId} result={result} title={model?.name} />;
      })}
    </WorkflowShell>
  );
}
