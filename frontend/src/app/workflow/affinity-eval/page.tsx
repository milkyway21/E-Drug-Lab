"use client";

import { useEffect, useState } from "react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { ModelSelector } from "@/components/workflow/ModelSelector";
import { ResultCard, type StepResult } from "@/components/workflow/ResultCard";
import { getStepByHref, STEP_ID_AFFINITY } from "@/lib/tool-registry";
import { apiClient, type GlideStatusResponse } from "@/lib/api-client";
import { isRealVinaDock } from "@/lib/docking-metrics";
import { useLang } from "@/lib/i18n/i18n-context";
import { getPipelineMoleculeDisplayName } from "@/lib/workflow-context";
import { useStepRunner } from "@/hooks/useStepRunner";
import { Atom, Waves, Crosshair, FlaskConical, Dna, Settings2 } from "lucide-react";

type SchrodingerPrecision = "HTVS" | "SP" | "XP";

export default function AffinityEvalPage() {
  return (
    <WorkflowShell current="/workflow/affinity-eval">
      <AffinityEvalContent />
    </WorkflowShell>
  );
}

function AffinityEvalContent() {
  const { t } = useLang();
  const stepConfig = getStepByHref("/workflow/affinity-eval")!;
  const { executeStep, running, workflow } = useStepRunner();
  const { molecules, updateStepResult } = workflow;
  const [results, setResults] = useState<Record<string, StepResult>>({});
  const [ligandsPrepared, setLigandsPrepared] = useState(false);
  const [schrodingerStatus, setSchrodingerStatus] = useState<GlideStatusResponse | null>(null);
  const [schrodingerPrecision, setSchrodingerPrecision] = useState<SchrodingerPrecision>("SP");
  const [schrodingerPh, setSchrodingerPh] = useState(7.2);
  const [schrodingerPhThreshold, setSchrodingerPhThreshold] = useState(0.2);
  const [schrodingerOuterBox, setSchrodingerOuterBox] = useState(20);
  const [schrodingerPoses, setSchrodingerPoses] = useState(5);
  const [schrodingerPostMinimize, setSchrodingerPostMinimize] = useState(true);
  const [schrodingerRunMmgbsa, setSchrodingerRunMmgbsa] = useState(false);
  const [schrodingerCenterX, setSchrodingerCenterX] = useState("");
  const [schrodingerCenterY, setSchrodingerCenterY] = useState("");
  const [schrodingerCenterZ, setSchrodingerCenterZ] = useState("");
  const [showSchrodingerParams, setShowSchrodingerParams] = useState(true);

  useEffect(() => {
    apiClient.schrodingerStatus().then((res) => {
      if (res.ok) setSchrodingerStatus(res.data);
    });
  }, []);

  function schrodingerRunParams() {
    return {
      pdbId: workflow.target?.pdbId,
      schrodingerPrecision,
      schrodingerPh,
      schrodingerPhThreshold,
      schrodingerOuterBox,
      schrodingerPoses,
      schrodingerPostMinimize,
      schrodingerRunMmgbsa,
      schrodingerCenterX: schrodingerCenterX.trim() ? Number(schrodingerCenterX) : undefined,
      schrodingerCenterY: schrodingerCenterY.trim() ? Number(schrodingerCenterY) : undefined,
      schrodingerCenterZ: schrodingerCenterZ.trim() ? Number(schrodingerCenterZ) : undefined,
    };
  }

  function setModelResult(modelId: string, result: StepResult) {
    setResults((prev) => ({ ...prev, [modelId]: result }));
  }

  async function handleRun(selectedIds: string[]) {
    const vinaTools = selectedIds.filter((id) => id === "vina-dock");
    const glideTools = selectedIds.filter((id) => id === "glide-dock");
    const mmgbsaOnly = selectedIds.filter((id) => id === "mm-gbsa" && !glideTools.includes("glide-dock"));
    const otherTools = selectedIds.filter((id) => !["vina-dock", "glide-dock", "mm-gbsa"].includes(id));

    if (vinaTools.length > 0) {
      setModelResult("vina-dock", { status: "loading", message: "Docking with Vina..." });
      const result = await executeStep(STEP_ID_AFFINITY, vinaTools, {
        pdbId: workflow.target?.pdbId,
      });
      setModelResult("vina-dock", { status: result.ok ? "done" : "error", message: result.message });
    }

    if (glideTools.length > 0 || mmgbsaOnly.length > 0) {
      const combined = [...glideTools, ...mmgbsaOnly];
      for (const modelId of combined) {
        setModelResult(modelId, { status: "loading", message: "Running Schrödinger pipeline..." });
      }
      const result = await executeStep(STEP_ID_AFFINITY, combined, schrodingerRunParams());
      for (const modelId of combined) {
        setModelResult(modelId, {
          status: result.ok ? "done" : "error",
          message: result.message,
          data: schrodingerStatus
            ? {
                precision: schrodingerPrecision,
                install_path: schrodingerStatus.install_path || "—",
                run_mmgbsa: schrodingerRunMmgbsa || mmgbsaOnly.length > 0,
              }
            : undefined,
        });
      }
    }

    for (const modelId of otherTools) {
      if (modelId === "md-simulation") await runMd();
      else setModelResult(modelId, { status: "error", message: t("statusNotImplemented") });
    }
  }

  async function runVinaDock() {
    if (molecules.length === 0) {
      setModelResult("vina-dock", { status: "error", message: "No molecules in pipeline. Run Compound Sourcing and ADMET Filter first." });
      return;
    }
    if (!workflow.target?.pdbId && !workflow.target?.id) {
      setModelResult("vina-dock", { status: "error", message: "No target selected. Complete Target Prep first." });
      return;
    }

    setModelResult("vina-dock", { status: "loading", message: "Checking AutoDock Vina..." });
    const versionResult = await apiClient.vinaVersion();

    setModelResult("vina-dock", {
      status: "loading",
      message: `Docking ${molecules.length} pipeline molecules with real Vina...`,
    });

    const dock = await apiClient.dockSmilesBatch({
      molecules: molecules.map((mol) => ({
        molecule_id: mol.id,
        smiles: mol.smiles,
        name: mol.originalName || mol.name || mol.smiles.slice(0, 20),
      })),
      target_id: workflow.target?.id,
      target_pdb_id: workflow.target?.pdbId,
      exhaustiveness: 4,
      timeout_per_molecule: 20,
      concurrency: 2,
    });

    if (!dock.ok) {
      setModelResult("vina-dock", { status: "error", message: dock.error });
      return;
    }

    if (!dock.data.vina_available) {
      setModelResult("vina-dock", {
        status: "error",
        message: "AutoDock Vina is not available. Install Vina or use DrugCLIP/TAME-VS scores for ranking.",
      });
      return;
    }

    const dockResults: Array<{ name: string; affinity: number | null; status: string }> = [];
    for (const item of dock.data.results) {
      const dockData = {
        name: item.name,
        smiles: item.smiles,
        affinity_kcal_mol: item.affinity_kcal_mol,
        model: item.model,
        method: item.method,
        success: item.success,
        error: item.error,
        timestamp: new Date().toISOString(),
      };
      updateStepResult(item.molecule_id, "vina-dock", dockData);
      dockResults.push({
        name: item.name,
        affinity: item.affinity_kcal_mol,
        status: item.success ? "docked" : "failed",
      });
    }

    const successful = dockResults.filter((r) => r.affinity !== null);
    successful.sort((a, b) => (a.affinity ?? 0) - (b.affinity ?? 0));
    setLigandsPrepared(successful.length > 0);

    if (successful.length === 0) {
      setModelResult("vina-dock", { status: "error", message: "Vina docking failed for all molecules." });
      return;
    }

    setModelResult("vina-dock", {
      status: "done",
      message: `${successful.length}/${molecules.length} molecules docked. Best: ${successful[0]?.name} (${successful[0]?.affinity} kcal/mol)`,
      data: {
        "Pipeline molecules": String(molecules.length),
        "Vina version": versionResult.ok ? (versionResult.data.version || "installed") : "unavailable",
        "Top 3": successful.slice(0, 3).map((r) => `${r.name}: ${r.affinity} kcal/mol`).join(" | "),
        "Results stored in": "pipeline stepResults['vina-dock']",
      },
    });
  }

  async function runMd() {
    setModelResult("md-simulation", {
      status: "loading",
      message: "Submitting Schrödinger Desmond MD (dry_prep)...",
    });
    const result = await apiClient.runMd({
      mode: "dry_prep",
      confirm: false,
      target_id: workflow.target?.id || workflow.target?.pdbId || undefined,
    });
    if (!result.ok) {
      setModelResult("md-simulation", { status: "error", message: result.error });
      return;
    }

    const badStatuses = new Set(["stub", "unavailable", "failed", "gated"]);
    const initialStatus = String(result.data.status || "");
    if (badStatuses.has(initialStatus) || result.data.stub === true) {
      setModelResult("md-simulation", {
        status: "error",
        message:
          result.data.message ||
          `Desmond MD not successful (status=${initialStatus}). Stub/unavailable is never treated as success.`,
        data: {
          Status: initialStatus,
          TaskID: result.data.task_id,
          JobDir: result.data.job_dir || "—",
          Mode: result.data.mode || "dry_prep",
        },
      });
      return;
    }

    const taskId = result.data.task_id;
    setModelResult("md-simulation", {
      status: "loading",
      message: result.data.message || `Desmond MD ${initialStatus}… polling status`,
      data: {
        Status: initialStatus,
        TaskID: taskId,
        JobDir: result.data.job_dir || "—",
        Mode: result.data.mode || "dry_prep",
      },
    });

    const terminal = new Set(["completed", "failed", "gated", "unavailable", "stub"]);
    let lastStatus = initialStatus;
    let lastMessage = result.data.message || "";
    let lastJobDir = result.data.job_dir || "";

    for (let i = 0; i < 30; i++) {
      if (terminal.has(lastStatus) && lastStatus !== "queued" && lastStatus !== "running") {
        break;
      }
      await new Promise((r) => setTimeout(r, 800));
      const st = await apiClient.mdStatus(taskId);
      if (!st.ok) {
        setModelResult("md-simulation", {
          status: "error",
          message: st.error || "Failed to poll MD status",
          data: { TaskID: taskId, Status: lastStatus, JobDir: lastJobDir || "—" },
        });
        return;
      }
      lastStatus = String(st.data.status || "");
      lastMessage = st.data.message || lastMessage;
      lastJobDir = st.data.job_dir || lastJobDir;
      if (["queued", "running"].includes(lastStatus)) {
        setModelResult("md-simulation", {
          status: "loading",
          message: lastMessage || `Desmond MD ${lastStatus}…`,
          data: { Status: lastStatus, TaskID: taskId, JobDir: lastJobDir || "—" },
        });
        continue;
      }
      break;
    }

    if (lastStatus === "completed") {
      setModelResult("md-simulation", {
        status: "done",
        message: lastMessage || "Desmond MD dry_prep completed.",
        data: {
          Status: lastStatus,
          TaskID: taskId,
          JobDir: lastJobDir || "—",
          Mode: result.data.mode || "dry_prep",
          Engine: "schrodinger_desmond",
          Note: "dry_prep gate ≠ production PASS",
        },
      });
      return;
    }

    setModelResult("md-simulation", {
      status: "error",
      message:
        lastMessage ||
        `Desmond MD ended with status=${lastStatus}. Never treat stub/unavailable as success.`,
      data: {
        Status: lastStatus,
        TaskID: taskId,
        JobDir: lastJobDir || "—",
        Mode: result.data.mode || "dry_prep",
      },
    });
  }

  // Count pipeline molecules with ADMET results (ready for docking)
  const admetReady = molecules.filter((m) => m.stepResults?.["admet-ai"]).length;
  const dockedCount = molecules.filter((m) => isRealVinaDock(m.stepResults?.["vina-dock"])).length;

  return (
    <>
      <WorkflowHeader
        badge={t("affinityBadge")}
        title={t("affinityTitle")}
        description={t("affinityDesc")}
      />

      {/* Pipeline molecule status bar */}
      <div className="panel p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Dna size={16} className="text-teal" />
          <span className="text-sm font-bold text-ink">Pipeline Ligands</span>
        </div>
        <div className="flex gap-4 text-sm">
          <div className="flex-1 rounded-lg bg-slate-50 p-3 text-center">
            <div className="font-mono text-lg font-bold text-ink">{molecules.length}</div>
            <div className="text-xs text-muted">Total from pipeline</div>
          </div>
          <div className="flex-1 rounded-lg bg-blue-50 p-3 text-center">
            <div className="font-mono text-lg font-bold text-blue-700">{admetReady}</div>
            <div className="text-xs text-muted">ADMET profiled</div>
          </div>
          <div className="flex-1 rounded-lg bg-emerald-50 p-3 text-center">
            <div className="font-mono text-lg font-bold text-emerald-700">{dockedCount}</div>
            <div className="text-xs text-muted">Docked (Vina)</div>
          </div>
        </div>
        {molecules.length > 0 && (
          <div className="mt-3 max-h-32 overflow-y-auto">
            {molecules.map((mol) => {
              const vinaResult = mol.stepResults?.["vina-dock"] as Record<string, unknown> | undefined;
              const admetResult = mol.stepResults?.["admet-ai"] as Record<string, unknown> | undefined;
              return (
                <div key={mol.id} className="flex items-center gap-2 px-2 py-1 text-xs border-b border-slate-50 hover:bg-slate-50">
                  <span className={`w-1.5 h-1.5 rounded-full ${mol.status === "pass" ? "bg-emerald-500" : mol.status === "fail" ? "bg-red-500" : "bg-slate-300"}`} />
                  <span className="flex-1 font-mono truncate text-ink">{getPipelineMoleculeDisplayName(mol)}</span>
                  {admetResult ? (
                    <span className="text-blue-600">ADMET done</span>
                  ) : (
                    <span className="text-amber-600">Needs ADMET</span>
                  )}
                  <span className="text-slate-300">→</span>
                  {vinaResult ? (
                    <span className="text-emerald-600 font-mono">{(vinaResult.affinity_kcal_mol as number)?.toFixed(1)} kcal</span>
                  ) : (
                    <span className="text-muted">pending</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-4">
        {[
          { title: "AutoDock Vina", desc: "Fast molecular docking. Reads pipeline ligands, stores affinity in stepResults.", icon: Crosshair, color: "#2E7D32", tag: "Local" },
          { title: "Glide Dock", desc: "Schrödinger Glide 本地对接（HTVS / SP / XP），可选对接后 Prime MM-GBSA。", icon: FlaskConical, color: "#6A1B9A", tag: "Local" },
          { title: t("affinityMmgbsa"), desc: t("affinityMmgbsaDesc"), icon: Atom, color: "#1565C0", tag: "HPC" },
          { title: t("affinityMd"), desc: t("affinityMdDesc"), icon: Waves, color: "#00897B", tag: "Schrödinger" },
        ].map((method) => {
          const Icon = method.icon;
          return (
            <div key={method.title} className="panel p-5">
              <div className="flex items-center gap-3 mb-3">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg" style={{ background: `${method.color}10`, border: `1px solid ${method.color}20` }}>
                  <Icon size={20} style={{ color: method.color }} />
                </span>
                <div>
                  <span className="text-sm font-bold text-ink">{method.title}</span>
                  <div className="mt-0.5">
                    <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold bg-slate-50 text-muted border border-slate-200">{method.tag}</span>
                  </div>
                </div>
              </div>
              <p className="text-xs text-muted leading-5">{method.desc}</p>
            </div>
          );
        })}
      </div>

      {/* Schrödinger 参数面板 */}
      <div className="panel p-4 mb-4">
        <button
          type="button"
          className="flex w-full items-center justify-between text-left"
          onClick={() => setShowSchrodingerParams((v) => !v)}
        >
          <div className="flex items-center gap-2">
            <Settings2 size={16} className="text-cobalt" />
            <span className="text-sm font-bold text-ink">Schrödinger 参数（Glide / MM-GBSA）</span>
          </div>
          <span className="text-xs text-muted">{showSchrodingerParams ? "收起" : "展开"}</span>
        </button>

        {showSchrodingerParams && (
          <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="text-xs font-semibold text-muted">对接精度</label>
              <select
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
                value={schrodingerPrecision}
                onChange={(e) => setSchrodingerPrecision(e.target.value as SchrodingerPrecision)}
              >
                <option value="HTVS">HTVS — 高通量初筛</option>
                <option value="SP">SP — 标准精度（推荐）</option>
                <option value="XP">XP — 超高精度</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-muted">pH（LigPrep / PrepWizard）</label>
              <input
                type="number"
                step="0.1"
                min={0}
                max={14}
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
                value={schrodingerPh}
                onChange={(e) => setSchrodingerPh(Number(e.target.value))}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted">pH 阈值</label>
              <input
                type="number"
                step="0.05"
                min={0}
                max={2}
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
                value={schrodingerPhThreshold}
                onChange={(e) => setSchrodingerPhThreshold(Number(e.target.value))}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted">对接盒边长 (Å)</label>
              <input
                type="number"
                min={10}
                max={40}
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
                value={schrodingerOuterBox}
                onChange={(e) => setSchrodingerOuterBox(Number(e.target.value))}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted">每分子构象数</label>
              <input
                type="number"
                min={1}
                max={50}
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm"
                value={schrodingerPoses}
                onChange={(e) => setSchrodingerPoses(Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col justify-end gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={schrodingerPostMinimize}
                  onChange={(e) => setSchrodingerPostMinimize(e.target.checked)}
                />
                对接后最小化
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={schrodingerRunMmgbsa}
                  onChange={(e) => setSchrodingerRunMmgbsa(e.target.checked)}
                />
                Glide 完成后自动 MM-GBSA
              </label>
            </div>
            <div>
              <label className="text-xs font-semibold text-muted">口袋中心 X（留空=自动）</label>
              <input
                type="text"
                placeholder="auto"
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm font-mono"
                value={schrodingerCenterX}
                onChange={(e) => setSchrodingerCenterX(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted">口袋中心 Y</label>
              <input
                type="text"
                placeholder="auto"
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm font-mono"
                value={schrodingerCenterY}
                onChange={(e) => setSchrodingerCenterY(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted">口袋中心 Z</label>
              <input
                type="text"
                placeholder="auto"
                className="mt-1 w-full rounded border border-slate-200 px-2 py-1.5 text-sm font-mono"
                value={schrodingerCenterZ}
                onChange={(e) => setSchrodingerCenterZ(e.target.value)}
              />
            </div>
          </div>
        )}

        {schrodingerStatus && (
          <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-muted">
            <span
              className={`mr-2 inline-block h-2 w-2 rounded-full ${schrodingerStatus.available ? "bg-emerald-500" : "bg-rose-500"}`}
            />
            {schrodingerStatus.message}
            {schrodingerStatus.install_path ? ` · ${schrodingerStatus.install_path}` : ""}
          </div>
        )}
      </div>

      <ModelSelector models={stepConfig.models} onRun={handleRun} running={running} />
      {Object.entries(results).map(([modelId, result]) => {
        const model = stepConfig.models.find((m) => m.id === modelId);
        return <ResultCard key={modelId} result={result} title={model?.name} />;
      })}
    </>
  );
}
