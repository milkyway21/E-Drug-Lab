"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Play,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Circle,
  Trophy,
  FlaskConical,
  Zap,
  AlertTriangle,
  Upload,
  Download,
  Dna,
  Save,
  Server,
  Monitor,
} from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { useWorkflow } from "@/lib/workflow-context";
import { apiClient, type Target } from "@/lib/api-client";
import { useStepRunner } from "@/hooks/useStepRunner";
import {
  STEP_REGISTRY,
  STEP_ID_TARGET_PREP,
  PRESET_RECIPES,
  defaultRecipe,
  loadRecipeFromStorage,
  saveRecipeToStorage,
  validateRecipe,
  getTool,
  type PipelineRecipe,
  type RecipeStepConfig,
} from "@/lib/tool-registry";
import type { StepRunResult } from "@/lib/pipeline-context";

type StepStatus = "idle" | "loading" | "done" | "error" | "skipped";
type ExecutionMode = "local" | "server";

interface PipelineResultRow {
  rank: number;
  name: string;
  smiles: string;
  admetPassed: boolean;
  hERG: number | null;
  DILI: number | null;
  HIA: number | null;
  dockingAffinity: number | null;
  finalScore: number | null;
  artifact: boolean;
}

export function PipelineRunner() {
  const { t } = useLang();
  const { setTarget, setRecipe, setRunId } = useWorkflow();
  const { executeRecipe, running } = useStepRunner();

  const [recipe, setRecipeState] = useState<PipelineRecipe>(() => loadRecipeFromStorage() || defaultRecipe());
  const [presetId, setPresetId] = useState(recipe.id || "full-7-step");
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("local");
  const [stepStatus, setStepStatus] = useState<Record<string, StepStatus>>({});
  const [stepMessages, setStepMessages] = useState<Record<string, string>>({});
  const [results, setResults] = useState<PipelineResultRow[]>([]);
  const [summary, setSummary] = useState<{ total: number; passed: number; failed: number } | null>(null);
  const [targetInfo, setTargetInfo] = useState<{ pdb_id?: string; name: string; source: string } | null>(null);

  const [pdbId, setPdbId] = useState("8V1T");
  const [targetMode, setTargetMode] = useState<"download" | "upload-protein" | "upload-ligand">("download");
  const [ligandSmiles, setLigandSmiles] = useState("CC(=O)Oc1ccccc1C(=O)O");
  const [ligandName, setLigandName] = useState("Aspirin");
  const proteinFileRef = useRef<HTMLInputElement>(null);
  const ligandFileRef = useRef<HTMLInputElement>(null);
  const [uploadFileName, setUploadFileName] = useState("");
  const [ligandFileName, setLigandFileName] = useState("");

  useEffect(() => {
    setRecipe(recipe);
  }, [recipe, setRecipe]);

  const updateStepConfig = useCallback((stepId: string, patch: Partial<RecipeStepConfig>) => {
    setRecipeState((prev) => ({
      ...prev,
      steps: prev.steps.map((s) => (s.stepId === stepId ? { ...s, ...patch } : s)),
    }));
  }, []);

  const toggleTool = useCallback((stepId: string, toolId: string) => {
    setRecipeState((prev) => ({
      ...prev,
      steps: prev.steps.map((s) => {
        if (s.stepId !== stepId) return s;
        const has = s.toolIds.includes(toolId);
        return {
          ...s,
          toolIds: has ? s.toolIds.filter((id) => id !== toolId) : [...s.toolIds, toolId],
        };
      }),
    }));
  }, []);

  const loadPreset = useCallback((id: string) => {
    const preset = PRESET_RECIPES.find((p) => p.id === id);
    if (preset) {
      const cloned = structuredClone(preset);
      setRecipeState(cloned);
      setPresetId(id);
    }
  }, []);

  const saveRecipe = useCallback(() => {
    saveRecipeToStorage(recipe);
  }, [recipe]);

  const setStatus = useCallback((stepId: string, status: StepStatus, msg?: string) => {
    setStepStatus((prev) => ({ ...prev, [stepId]: status }));
    if (msg !== undefined) setStepMessages((prev) => ({ ...prev, [stepId]: msg }));
  }, []);

  const handleRun = useCallback(async () => {
    const errors = validateRecipe(recipe);
    if (errors.length > 0) {
      alert(errors.join("\n"));
      return;
    }

    setResults([]);
    setSummary(null);
    STEP_REGISTRY.forEach((s) => setStatus(s.id, "idle", ""));

    const params = {
      pdbId: pdbId.trim(),
      targetMode,
      ligandSmiles,
      ligandName,
      proteinFile: proteinFileRef.current?.files?.[0] ?? null,
      ligandFile: ligandFileRef.current?.files?.[0] ?? null,
    };

    if (executionMode === "server") {
      const create = await apiClient.createPipelineRun({
        recipe,
        context: {
          target: null,
          molecules: [],
          round_id: 1,
        },
        execute: true,
      });
      if (!create.ok) {
        alert(create.error);
        return;
      }
      setRunId(create.data.id);
      const runId = create.data.id;
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const status = await apiClient.getPipelineRun(runId);
        if (!status.ok) break;
        for (const sr of status.data.step_runs) {
          setStatus(sr.step_id, sr.status === "completed" ? "done" : sr.status === "failed" ? "error" : "loading", sr.error_message || "");
        }
        if (status.data.status === "completed" || status.data.status === "failed") {
          if (status.data.status === "failed") alert(status.data.error_message || "Pipeline failed");
          break;
        }
      }
      return;
    }

    const onProgress = (stepId: string, result: StepRunResult) => {
      setStatus(stepId, result.ok ? "done" : "error", result.message);
      if (stepId === STEP_ID_TARGET_PREP && result.ok) {
        const pdb = params.pdbId || "4HHB";
        setTargetInfo({
          pdb_id: targetMode === "download" ? pdb : undefined,
          name: targetMode === "download" ? `PDB: ${pdb}` : result.message,
          source: targetMode === "download" ? "RCSB download" : targetMode,
        });
      }
      if (result.rankedRows) {
        setResults(result.rankedRows as unknown as PipelineResultRow[]);
      }
      if (result.summary) setSummary(result.summary);
    };

    recipe.steps.forEach((s) => {
      if (!s.enabled) setStatus(s.stepId, "skipped", "Skipped");
    });

    const outcome = await executeRecipe(recipe, params, onProgress);
    if (!outcome.ok) {
      console.error("Pipeline error:", outcome.error);
    }
  }, [recipe, executionMode, pdbId, targetMode, ligandSmiles, ligandName, executeRecipe, setStatus, setRunId]);

  const statusIcon = (status: StepStatus) => {
    if (status === "done") return <CheckCircle2 size={14} className="text-emerald-500" />;
    if (status === "error") return <XCircle size={14} className="text-red-500" />;
    if (status === "skipped") return <Circle size={14} className="text-slate-300" />;
    if (status === "loading") return <RefreshCw size={14} className="text-amber-500 animate-spin" />;
    return <Circle size={14} className="text-slate-300" />;
  };

  return (
    <div className="panel p-6 mt-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-teal-50 border border-teal-100">
            <Zap size={18} className="text-teal" />
          </span>
          <div>
            <h3 className="font-display text-lg font-bold text-ink">Pipeline Builder</h3>
            <p className="text-xs text-muted">Enable steps, select tools per step, run locally or on server.</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={presetId}
            onChange={(e) => loadPreset(e.target.value)}
            className="select-field h-9 text-xs"
            disabled={running}
          >
            {PRESET_RECIPES.map((p) => (
              <option key={p.id} value={p.id!}>{p.name}</option>
            ))}
          </select>
          <button type="button" onClick={saveRecipe} disabled={running} className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-semibold border border-slate-200 hover:bg-slate-50">
            <Save size={14} /> {t("commonSave")}
          </button>
          <div className="flex rounded-lg border border-slate-200 overflow-hidden">
            <button
              type="button"
              onClick={() => setExecutionMode("local")}
              className={`inline-flex items-center gap-1 px-3 py-2 text-xs font-semibold ${executionMode === "local" ? "bg-teal-50 text-teal" : "bg-white text-muted"}`}
            >
              <Monitor size={14} /> {t("execModeLocal")}
            </button>
            <button
              type="button"
              onClick={() => setExecutionMode("server")}
              className={`inline-flex items-center gap-1 px-3 py-2 text-xs font-semibold ${executionMode === "server" ? "bg-teal-50 text-teal" : "bg-white text-muted"}`}
            >
              <Server size={14} /> {t("execModeServer")}
            </button>
          </div>
          <button onClick={handleRun} disabled={running} className="inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-bold text-white bg-teal hover:bg-teal-600 disabled:opacity-50 transition-all shadow-soft">
            {running ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} />}
            {running ? t("pipelineRunning") : t("pipelineRun")}
          </button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4 mb-5">
        {STEP_REGISTRY.map((stepDef) => {
          const stepCfg = recipe.steps.find((s) => s.stepId === stepDef.id) || {
            stepId: stepDef.id,
            enabled: false,
            toolIds: [],
          };
          const isTarget = stepDef.id === STEP_ID_TARGET_PREP;

          return (
            <div key={stepDef.id} className={`rounded-lg border p-3 ${stepCfg.enabled ? "border-teal-200 bg-teal-50/30" : "border-slate-200 opacity-75"}`}>
              <div className="flex items-center gap-2 mb-2">
                <input
                  type="checkbox"
                  checked={stepCfg.enabled}
                  onChange={(e) => updateStepConfig(stepDef.id, { enabled: e.target.checked })}
                  disabled={running}
                  className="rounded border-slate-300"
                />
                {statusIcon(stepStatus[stepDef.id] || "idle")}
                <span className="text-xs font-bold text-ink">Step {stepDef.step}</span>
                <span className="text-[10px] text-muted truncate">{t(stepDef.titleKey)}</span>
              </div>

              {isTarget && stepCfg.enabled ? (
                <div className="space-y-1.5 mb-2">
                  <div className="flex gap-1">
                    {(["download", "upload-protein", "upload-ligand"] as const).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setTargetMode(mode)}
                        className={`flex-1 rounded px-1 py-0.5 text-[10px] font-semibold border ${targetMode === mode ? "bg-teal-50 text-teal border-teal-200" : "bg-slate-50 text-muted border-slate-200"}`}
                        disabled={running}
                      >
                        {mode === "download" ? "PDB" : mode === "upload-protein" ? "Protein" : "Ligand"}
                      </button>
                    ))}
                  </div>
                  {targetMode === "download" && (
                    <input value={pdbId} onChange={(e) => setPdbId(e.target.value.toUpperCase())} placeholder="PDB ID" className="input-field h-7 w-full text-[11px] font-mono" disabled={running} />
                  )}
                  {targetMode === "upload-protein" && (
                    <input ref={proteinFileRef} type="file" accept=".pdb,.pdbqt,.cif" onChange={(e) => setUploadFileName(e.target.files?.[0]?.name || "")} className="w-full text-[10px]" disabled={running} />
                  )}
                  {targetMode === "upload-ligand" && (
                    <textarea value={ligandSmiles} onChange={(e) => setLigandSmiles(e.target.value)} placeholder="SMILES" className="input-field h-10 w-full text-[10px] font-mono resize-none" disabled={running} />
                  )}
                </div>
              ) : null}

              <div className="flex flex-wrap gap-1">
                {stepDef.toolIds.map((toolId) => {
                  const tool = getTool(toolId);
                  const selected = stepCfg.toolIds.includes(toolId);
                  const disabled = tool.status === "placeholder" || !stepCfg.enabled;
                  return (
                    <button
                      key={toolId}
                      type="button"
                      onClick={() => toggleTool(stepDef.id, toolId)}
                      disabled={running || disabled}
                      className={`rounded px-2 py-0.5 text-[10px] font-semibold border ${
                        selected ? "bg-teal-100 text-teal border-teal-300" : "bg-slate-50 text-muted border-slate-200"
                      } ${tool.status === "placeholder" ? "opacity-40 cursor-not-allowed" : ""}`}
                      title={tool.description}
                    >
                      {tool.name}
                    </button>
                  );
                })}
              </div>
              {stepMessages[stepDef.id] && (
                <p className={`mt-1 text-[10px] leading-tight ${stepStatus[stepDef.id] === "error" ? "text-red-500" : "text-muted"}`}>
                  {stepMessages[stepDef.id]}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {summary && (
        <div className="mb-5 grid gap-3 md:grid-cols-4">
          <div className="rounded-lg bg-slate-50 p-3 text-center">
            <div className="font-mono text-lg font-bold text-ink">{summary.total}</div>
            <div className="text-xs text-muted">Total Ranked</div>
          </div>
          <div className="rounded-lg bg-emerald-50 p-3 text-center">
            <div className="font-mono text-lg font-bold text-emerald-700">{summary.passed}</div>
            <div className="text-xs text-muted">ADMET Passed</div>
          </div>
          <div className="rounded-lg bg-red-50 p-3 text-center">
            <div className="font-mono text-lg font-bold text-red-700">{summary.failed}</div>
            <div className="text-xs text-muted">ADMET Failed</div>
          </div>
        </div>
      )}

      {results.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="bg-slate-50">
                <th className="px-3 py-2 text-xs font-semibold text-muted">#</th>
                <th className="px-3 py-2 text-xs font-semibold text-muted">Name</th>
                <th className="px-3 py-2 text-xs font-semibold text-muted">Final Score</th>
                <th className="px-3 py-2 text-xs font-semibold text-muted">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {results.map((row) => (
                <tr key={`${row.name}-${row.rank}`}>
                  <td className="px-3 py-2 font-bold">{row.rank}</td>
                  <td className="px-3 py-2 truncate max-w-[200px]">{row.name}</td>
                  <td className="px-3 py-2 font-mono">{row.finalScore?.toFixed(1) ?? "-"}</td>
                  <td className="px-3 py-2">
                    {row.artifact ? (
                      <span className="text-red-600 text-xs">Artifact</span>
                    ) : (
                      <span className="text-emerald-600 text-xs">Pass</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!running && results.length === 0 && (
        <div className="py-8 text-center">
          <FlaskConical size={36} className="mx-auto mb-3 text-slate-200" />
          <p className="text-sm text-muted">Configure steps and tools, then run the pipeline.</p>
        </div>
      )}
    </div>
  );
}
