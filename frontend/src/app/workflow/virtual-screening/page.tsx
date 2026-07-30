"use client";

import { useState } from "react";
import { Filter } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { ModelSelector } from "@/components/workflow/ModelSelector";
import { ResultCard, type StepResult } from "@/components/workflow/ResultCard";
import { getStepByHref, STEP_ID_VIRTUAL_SCREEN } from "@/lib/tool-registry";
import { useLang } from "@/lib/i18n/i18n-context";
import { useStepRunner } from "@/hooks/useStepRunner";

export default function VirtualScreeningPage() {
  return (
    <WorkflowShell current="/workflow/virtual-screening">
      <VirtualScreeningContent />
    </WorkflowShell>
  );
}

function VirtualScreeningContent() {
  const { t } = useLang();
  const stepConfig = getStepByHref("/workflow/virtual-screening")!;
  const { executeStep, running, workflow } = useStepRunner();
  const [results, setResults] = useState<Record<string, StepResult>>({});
  const [pdbId, setPdbId] = useState("8V1T");

  function setModelResult(modelId: string, result: StepResult) {
    setResults((prev) => ({ ...prev, [modelId]: result }));
  }

  async function handleRun(selectedIds: string[]) {
    if (selectedIds.length === 0) return;
    for (const modelId of selectedIds) {
      setModelResult(modelId, { status: "loading", message: `Running ${modelId}...` });
    }
    const result = await executeStep(STEP_ID_VIRTUAL_SCREEN, selectedIds, { pdbId, topK: 10 });
    for (const modelId of selectedIds) {
      setModelResult(modelId, { status: result.ok ? "done" : "error", message: result.message });
    }
  }

  return (
    <>
      <WorkflowHeader badge={t("virtualScreenBadge")} title={t("virtualScreenTitle")} description={t("virtualScreenDesc")} />
      <div className="panel p-6">
        <div className="flex items-center gap-2 mb-4">
          <Filter size={16} className="text-amber" />
          <h3 className="font-display text-sm font-bold text-ink">Screening parameters</h3>
        </div>
        <label>
          <span className="stat-label">Target PDB (DrugCLIP)</span>
          <input value={pdbId} onChange={(e) => setPdbId(e.target.value.toUpperCase())} className="input-field mt-2 w-40 font-mono" />
        </label>
        {workflow.glareCheckpoint && <p className="text-xs text-muted mt-2">GLARE checkpoint: {workflow.glareCheckpoint}</p>}
      </div>
      <div className="mt-4">
        <ModelSelector models={stepConfig.models} onRun={handleRun} running={running} defaultSelectedIds={["glare-screen"]} />
      </div>
      {Object.entries(results).map(([modelId, result]) => {
        const model = stepConfig.models.find((m) => m.id === modelId);
        return <ResultCard key={modelId} result={result} title={model?.name} />;
      })}
    </>
  );
}
