"use client";

import { useRef, useState } from "react";
import { Brain } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { ModelSelector } from "@/components/workflow/ModelSelector";
import { ResultCard, type StepResult } from "@/components/workflow/ResultCard";
import { getStepByHref, STEP_ID_RL_TRAIN } from "@/lib/tool-registry";
import { apiClient } from "@/lib/api-client";
import { useLang } from "@/lib/i18n/i18n-context";
import { useStepRunner } from "@/hooks/useStepRunner";

export default function RLTrainingPage() {
  return (
    <WorkflowShell current="/workflow/rl-training">
      <RLTrainingContent />
    </WorkflowShell>
  );
}

function RLTrainingContent() {
  const { t } = useLang();
  const stepConfig = getStepByHref("/workflow/rl-training")!;
  const { executeStep, running, workflow } = useStepRunner();
  const { molecules, roundId } = workflow;
  const [results, setResults] = useState<Record<string, StepResult>>({});
  const wetlabRef = useRef<HTMLInputElement>(null);

  function setModelResult(modelId: string, result: StepResult) {
    setResults((prev) => ({ ...prev, [modelId]: result }));
  }

  async function pollGlareTrain(jobId: string, modelId: string) {
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      const job = await apiClient.glareJob(jobId);
      if (!job.ok) break;
      if (job.data.status === "completed") {
        const result = job.data.result as { train?: { checkpoint?: string }; seed_reinforce?: { checkpoint?: string } } | undefined;
        const ckpt = result?.train?.checkpoint || result?.seed_reinforce?.checkpoint;
        if (ckpt) workflow.setGlareCheckpoint(ckpt);
        setModelResult(modelId, { status: "done", message: "GLARE training complete", data: { Checkpoint: ckpt || "—" } });
        return;
      }
      if (job.data.status === "failed") {
        setModelResult(modelId, { status: "error", message: String(job.data.error) });
        return;
      }
    }
    setModelResult(modelId, { status: "error", message: "Training timeout" });
  }

  async function handleRun(selectedIds: string[]) {
    const trainTools = selectedIds.filter((id) => id === "seed-reinforce" || id === "glare-train");
    const wetlabTools = selectedIds.filter((id) => id === "wetlab-reinforce");

    if (trainTools.length > 0) {
      for (const id of trainTools) {
        setModelResult(id, { status: "loading", message: "Running GLARE training..." });
      }
      const result = await executeStep(STEP_ID_RL_TRAIN, [trainTools[0]]);
      for (const id of trainTools) {
        setModelResult(id, { status: result.ok ? "done" : "error", message: result.message });
      }
    }

    const pipelineMols = molecules.map((m) => ({
      id: m.id,
      smiles: m.smiles,
      name: m.name,
      properties: m.properties,
      stepResults: m.stepResults,
    }));

    for (const modelId of wetlabTools) {
        const file = wetlabRef.current?.files?.[0];
        if (!file) {
          setModelResult(modelId, { status: "error", message: "Upload wet-lab xlsx first" });
          continue;
        }
        setModelResult(modelId, { status: "loading", message: "Importing wet-lab data..." });
        const imp = await apiClient.importWetlab(roundId, file);
        if (!imp.ok) {
          setModelResult(modelId, { status: "error", message: imp.error });
          continue;
        }
        const train = await apiClient.glareTrain({
          round_id: roundId,
          pipeline_molecules: pipelineMols,
          run_seed_reinforce: false,
          run_train: false,
          wetlab_file: imp.data.wetlab_file,
        });
        if (train.ok && train.data.job_id) await pollGlareTrain(train.data.job_id, modelId);
        else setModelResult(modelId, { status: "error", message: train.ok ? "No job" : train.error });
    }
  }

  return (
    <>
      <WorkflowHeader badge={t("rlTrainingBadge")} title={t("rlTrainingTitle")} description={t("rlTrainingDesc")} />
      <div className="panel p-6">
        <div className="flex items-center gap-2 mb-4">
          <Brain size={16} className="text-purple-600" />
          <h3 className="font-display text-sm font-bold text-ink">RL round settings</h3>
        </div>
        <p className="text-sm text-muted mb-3">Round {roundId} · Pipeline molecules: {molecules.length}</p>
        <label className="block">
          <span className="stat-label">Wet-lab pDC50 feedback (xlsx)</span>
          <input ref={wetlabRef} type="file" accept=".xlsx,.xls" className="mt-2 text-sm" />
        </label>
      </div>
      <div className="mt-4">
        <ModelSelector models={stepConfig.models} onRun={handleRun} running={running} defaultSelectedIds={["glare-train"]} />
      </div>
      {Object.entries(results).map(([modelId, result]) => {
        const model = stepConfig.models.find((m) => m.id === modelId);
        return <ResultCard key={modelId} result={result} title={model?.name} />;
      })}
    </>
  );
}
