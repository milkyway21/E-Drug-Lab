"use client";

import { useState } from "react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { ModelSelector } from "@/components/workflow/ModelSelector";
import { ResultCard, type StepResult } from "@/components/workflow/ResultCard";
import { getStepByHref, STEP_ID_ADMET } from "@/lib/tool-registry";
import { useLang } from "@/lib/i18n/i18n-context";
import { useStepRunner } from "@/hooks/useStepRunner";

export default function AdmetFilterPage() {
  return (
    <WorkflowShell current="/workflow/admet-filter">
      <AdmetFilterContent />
    </WorkflowShell>
  );
}

function AdmetFilterContent() {
  const { t } = useLang();
  const stepConfig = getStepByHref("/workflow/admet-filter")!;
  const { executeStep, running, workflow } = useStepRunner();
  const [results, setResults] = useState<Record<string, StepResult>>({});

  function setModelResult(modelId: string, result: StepResult) {
    setResults((prev) => ({ ...prev, [modelId]: result }));
  }

  async function handleRun(selectedIds: string[]) {
    if (selectedIds.length === 0) return;
    setModelResult("batch", { status: "loading", message: "Running ADMET..." });
    const result = await executeStep(STEP_ID_ADMET, selectedIds);
    setModelResult("batch", {
      status: result.ok ? "done" : "error",
      message: result.message,
    });
    for (const id of selectedIds) {
      setModelResult(id, {
        status: result.ok ? "done" : "error",
        message: result.message,
      });
    }
  }

  const counts = workflow.getCounts();

  return (
    <>
      <WorkflowHeader
        badge={t("workflowStep4")}
        title={t("workflowStep4")}
        description={t("workflowStep4Desc")}
      />
      <ModelSelector models={stepConfig.models} onRun={handleRun} running={running} />
      <div className="mt-4 grid gap-3">
        {Object.entries(results).map(([modelId, result]) => (
          <ResultCard key={modelId} title={modelId} result={result} />
        ))}
      </div>
      {counts.total > 0 && (
        <p className="mt-3 text-xs text-muted">
          Pipeline: {counts.pass} pass / {counts.fail} fail / {counts.pending} pending
        </p>
      )}
    </>
  );
}
