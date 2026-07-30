"use client";

import { useState } from "react";
import { Upload, Dna } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { ModelSelector } from "@/components/workflow/ModelSelector";
import { ResultCard, type StepResult } from "@/components/workflow/ResultCard";
import { getStepByHref, STEP_ID_LIBRARY_BUILD } from "@/lib/tool-registry";
import { apiClient } from "@/lib/api-client";
import { useLang } from "@/lib/i18n/i18n-context";
import { useStepRunner } from "@/hooks/useStepRunner";

export default function LibraryBuildPage() {
  return (
    <WorkflowShell current="/workflow/library-build">
      <LibraryBuildContent />
    </WorkflowShell>
  );
}

function LibraryBuildContent() {
  const { t } = useLang();
  const stepConfig = getStepByHref("/workflow/library-build")!;
  const { executeStep, running, workflow } = useStepRunner();
  const { molecules } = workflow;
  const [name, setName] = useState("DiffGUI generated library");
  const [source, setSource] = useState("diffgui");
  const [numMols, setNumMols] = useState(5);
  const [results, setResults] = useState<Record<string, StepResult>>({});
  const [scaffoldData, setScaffoldData] = useState<{
    stats: { total: number; success: number; failed: number; unique_generic: number; unique_framework: number };
    unique_scaffolds: Array<{ scaffold_smiles: string; member_count: number; representative_name: string; representative_smiles: string }>;
  } | null>(null);

  function setModelResult(modelId: string, result: StepResult) {
    setResults((prev) => ({ ...prev, [modelId]: result }));
  }

  async function handleRun(selectedIds: string[]) {
    const scaffoldOnly = selectedIds.filter((id) => id === "scaffold-extract");
    const pipelineTools = selectedIds.filter((id) => id !== "scaffold-extract");

    if (scaffoldOnly.length > 0) await runScaffoldExtract();

    if (pipelineTools.length > 0) {
      for (const id of pipelineTools) {
        setModelResult(id, { status: "loading", message: `Running ${id}...` });
      }
      const result = await executeStep(STEP_ID_LIBRARY_BUILD, pipelineTools, { numMols });
      for (const id of pipelineTools) {
        setModelResult(id, { status: result.ok ? "done" : "error", message: result.message });
      }
    }
  }

  async function runScaffoldExtract() {
    setModelResult("scaffold-extract", { status: "loading", message: "Extracting Murcko scaffolds..." });
    // Collect SMILES from pipeline molecules
    const smilesList = molecules.map((m) => m.smiles).filter(Boolean);
    if (smilesList.length === 0) {
      setModelResult("scaffold-extract", {
        status: "error",
        message: "Pipeline contains no molecules. Please load molecules first (SDF upload or DiffGUI).",
      });
      return;
    }
    const result = await apiClient.extractScaffolds({
      smiles_list: smilesList,
      names: molecules.map((m) => m.name || m.originalName || ""),
    });
    if (!result.ok) {
      setModelResult("scaffold-extract", { status: "error", message: result.error });
      return;
    }
    const data = result.data;
    setScaffoldData(data);
    setModelResult("scaffold-extract", {
      status: "done",
      message: `Extracted ${data.stats.unique_generic} unique generic scaffolds from ${data.stats.success}/${data.stats.total} molecules.`,
      data: {
        "Unique Generic": String(data.stats.unique_generic),
        "Unique Framework": String(data.stats.unique_framework),
        "Molecules Processed": `${data.stats.success}/${data.stats.total}`,
        "Failed": String(data.stats.failed),
      },
    });
  }

  return (
    <>
      <WorkflowHeader badge={t("libraryBuildBadge")} title={t("libraryBuildTitle")} description={t("libraryBuildDesc")} />
      <div className="panel p-6">
        <div className="flex items-center gap-2 mb-4">
          <Dna size={16} className="text-primary" />
          <h3 className="font-display text-sm font-bold text-ink">{t("compoundSourcingLibSettings")}</h3>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <label>
            <span className="stat-label">{t("compoundSourcingLibName")}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} className="input-field mt-2" />
          </label>
          <label>
            <span className="stat-label">Round ID</span>
            <input type="number" min={1} value={workflow.roundId} readOnly className="input-field mt-2 opacity-70" />
          </label>
          <label>
            <span className="stat-label">DiffGUI num_mols (test=5)</span>
            <input type="number" min={1} max={10000} value={numMols} onChange={(e) => setNumMols(Number(e.target.value))} className="input-field mt-2" />
          </label>
        </div>
      </div>
      {scaffoldData && scaffoldData.unique_scaffolds.length > 0 && (
        <div className="panel mt-4 p-6">
          <div className="flex items-center gap-2 mb-4">
            <Dna size={16} className="text-primary" />
            <h3 className="font-display text-sm font-bold text-ink">
              Unique Scaffolds ({scaffoldData.stats.unique_generic})
            </h3>
            <span className="stat-label ml-auto">
              {scaffoldData.stats.success} molecules → {scaffoldData.stats.unique_generic} scaffolds
            </span>
          </div>
          <div className="overflow-auto max-h-96">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted border-b border-mist">
                  <th className="text-left py-1 pr-2 w-12">#</th>
                  <th className="text-left py-1 pr-2">Scaffold SMILES</th>
                  <th className="text-right py-1 pr-2 w-16">Count</th>
                  <th className="text-left py-1 w-32">Representative</th>
                </tr>
              </thead>
              <tbody>
                {scaffoldData.unique_scaffolds.slice(0, 30).map((s, i) => (
                  <tr key={s.scaffold_smiles} className="border-b border-mist/50 hover:bg-mist/20">
                    <td className="py-1 pr-2 text-muted">{i + 1}</td>
                    <td className="py-1 pr-2 font-mono truncate max-w-xs" title={s.scaffold_smiles}>
                      {s.scaffold_smiles}
                    </td>
                    <td className="py-1 pr-2 text-right font-bold">{s.member_count}</td>
                    <td className="py-1 truncate max-w-[8rem]" title={s.representative_name}>
                      {s.representative_name}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {scaffoldData.unique_scaffolds.length > 30 && (
            <p className="text-xs text-muted mt-2">
              Showing top 30 of {scaffoldData.unique_scaffolds.length} unique scaffolds
            </p>
          )}
        </div>
      )}
      <div className="mt-4">
        <ModelSelector models={stepConfig.models} onRun={handleRun} running={running} defaultSelectedIds={["diffgui"]} />
      </div>
      {Object.entries(results).map(([modelId, result]) => {
        const model = stepConfig.models.find((m) => m.id === modelId);
        return <ResultCard key={modelId} result={result} title={model?.name} />;
      })}
    </>
  );
}
