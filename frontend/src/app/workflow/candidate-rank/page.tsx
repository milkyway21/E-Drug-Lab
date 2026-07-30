"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, Trophy, Info, Download, TestTube2 } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { ModelSelector } from "@/components/workflow/ModelSelector";
import { ResultCard, type StepResult } from "@/components/workflow/ResultCard";
import { getStepByHref } from "@/lib/tool-registry";
import { apiClient, type OrthogonalRankedCandidate, type RankingMoleculeRecord } from "@/lib/api-client";
import {
  computeAdmetComposite,
  hasRankablePrimaryMetric,
  isRealVinaDock,
  resolvePrimaryMetric,
} from "@/lib/docking-metrics";
import { useLang } from "@/lib/i18n/i18n-context";
import { getPipelineMoleculeDisplayName, useWorkflow } from "@/lib/workflow-context";

export default function CandidateRankPage() {
  return (
    <WorkflowShell current="/workflow/candidate-rank">
      <CandidateRankContent />
    </WorkflowShell>
  );
}

/** Compute a composite ADMET score from real stepResults data.
 *  Higher = more drug-like. Uses: 1-DILI, 1-hERG, HIA, -|logP-3| */
function computeAdmetScore(stepResults: Record<string, unknown>): number {
  return computeAdmetComposite(stepResults);
}

function CandidateRankContent() {
  const { t } = useLang();
  const stepConfig = getStepByHref("/workflow/candidate-rank")!;
  const { molecules, target, updateMoleculeNames } = useWorkflow();
  const [results, setResults] = useState<Record<string, StepResult>>({});
  const [running, setRunning] = useState(false);
  const [ranked, setRanked] = useState<OrthogonalRankedCandidate[]>([]);
  const [meta, setMeta] = useState<{ selection_rule: string; final_score_rule: string } | null>(null);
  const [dataSource, setDataSource] = useState<"pipeline" | "demo">("demo");
  const [reportUrl, setReportUrl] = useState<string | null>(null);
  const [savedCount, setSavedCount] = useState(0);

  function setModelResult(modelId: string, result: StepResult) {
    setResults((prev) => ({ ...prev, [modelId]: result }));
  }

  async function handleRun(selectedIds: string[]) {
    setRunning(true);
    for (const modelId of selectedIds) {
      if (modelId === "orthogonal-rank") await runOrthogonalRank();
      else setModelResult(modelId, { status: "error", message: t("statusNotImplemented") });
    }
    setRunning(false);
  }

  async function runOrthogonalRank() {
    setModelResult("orthogonal-rank", { status: "loading", message: "Building candidates from pipeline..." });
    setReportUrl(null);
    setSavedCount(0);

    if (molecules.length > 0) {
      setDataSource("pipeline");
      // Build from REAL stepResults — no random mock data
      const hasAdmet = molecules.some((m) => m.stepResults?.["admet-ai"]);
      const hasDocking = molecules.some((m) => hasRankablePrimaryMetric(m.stepResults));

      if (!hasDocking) {
        setModelResult("orthogonal-rank", {
          status: "error",
          message: "No rankable primary metric. Run real Vina docking (Step 5) or VS screening with DrugCLIP/TAME-VS (Step 3).",
        });
        return;
      }

      setModelResult("orthogonal-rank", {
        status: "loading",
        message: `Rescoring ${molecules.length} pipeline molecules${hasAdmet ? " (ADMET data)" : ""}${hasDocking ? " (primary metric ready)" : ""}...`,
      });

      const rankableMolecules = molecules.filter((m) => hasRankablePrimaryMetric(m.stepResults));
      const primaryMetricForApi = rankableMolecules.some((m) => isRealVinaDock(m.stepResults["vina-dock"]))
        ? "docking_affinity"
        : "vs_screen_score";

      const candidates = rankableMolecules.map((mol) => {
        const primary = resolvePrimaryMetric(mol.stepResults)!;
        const primaryMetricName = primary.kind === "vina" ? "docking_affinity" : "vs_screen_score";
        const primaryModel = primary.kind === "vina" ? "vina" : primary.model;
        const primaryFamily = primary.kind === "vina" ? "docking" : primary.methodFamily;
        return {
          molecule_id: mol.id,
          name: mol.originalName || mol.name || mol.smiles.slice(0, 20),
          metrics: [
            {
              metric_name: primaryMetricName,
              value: primary.value,
              model_name: primaryModel,
              method_family: primaryFamily,
              direction: "lower_is_better" as const,
              priority: 1,
            },
            {
              metric_name: "admet_composite_score",
              value: computeAdmetScore(mol.stepResults),
              model_name: "admet-ai",
              method_family: "admet",
              direction: "higher_is_better" as const,
              priority: 2,
            },
          ],
        };
      });

      const moleculeRecords: RankingMoleculeRecord[] = molecules.map((mol) => {
        const admetData = mol.stepResults?.["admet-ai"] as Record<string, unknown> | undefined;
        const props = (admetData?.properties || {}) as Record<string, number>;
        const vinaData = mol.stepResults?.["vina-dock"] as Record<string, unknown> | undefined;
        return {
          molecule_id: mol.id,
          name: mol.originalName || mol.name || mol.smiles.slice(0, 20),
          smiles: mol.smiles,
          source: mol.source,
          source_db_id: mol.sourceMoleculeId,
          status: mol.status,
          sa_score: mol.properties?.sa_score ?? null,
          molecular_weight: mol.properties?.molecular_weight ?? null,
          logp: mol.properties?.logp ?? null,
          tpsa: mol.properties?.tpsa ?? null,
          qed: mol.properties?.qed ?? null,
          herg: props.hERG ?? null,
          dili: props.DILI ?? null,
          ames: props.AMES ?? null,
          hia: props.HIA_Hou ?? null,
          docking_affinity: typeof vinaData?.affinity_kcal_mol === "number" ? (vinaData.affinity_kcal_mol as number) : null,
          step_results: mol.stepResults,
        };
      });

      const result = await apiClient.orthogonalRescore({
        candidates,
        primary_metric: primaryMetricForApi,
        orthogonal_metric: "admet_composite_score",
        gap_threshold: 35.0,
        target_id: target?.id,
        target_pdb_id: target?.pdbId,
        molecule_records: moleculeRecords,
      });

      if (result.ok) {
        updateMoleculeNames(
          result.data.ranked.map((item) => ({
            id: item.molecule_id,
            standardName: item.standard_name,
          }))
        );
        setRanked(result.data.ranked);
        setMeta({ selection_rule: result.data.selection_rule, final_score_rule: result.data.final_score_rule });
        setSavedCount(result.data.saved_molecules ?? 0);
        setReportUrl(result.data.report_download_url ? `${apiClient.apiBaseUrl}${result.data.report_download_url}` : null);
        setModelResult("orthogonal-rank", {
          status: "done",
          message: `${result.data.ranked.length} pipeline candidates ranked using real step data. ${result.data.saved_molecules ?? 0} molecules saved.`,
          data: {
            Source: "Pipeline stepResults",
            "ADMET data": hasAdmet ? "yes" : "no (estimated)",
            "Docking data": hasDocking ? "yes" : "no (estimated)",
            "Pipeline molecules": String(molecules.length),
          },
        });
      } else {
        setModelResult("orthogonal-rank", { status: "error", message: result.error });
      }
    } else {
      // Pipeline empty — fallback to demo
      setDataSource("demo");
      setModelResult("orthogonal-rank", { status: "loading", message: "Pipeline empty — loading demo data..." });
      const result = await apiClient.orthogonalDemo();
      if (result.ok) {
        setRanked(result.data.ranked);
        setMeta({ selection_rule: result.data.selection_rule, final_score_rule: result.data.final_score_rule });
        setReportUrl(null);
        setModelResult("orthogonal-rank", {
          status: "done",
          message: `${result.data.ranked.length} demo candidates ranked. Add molecules to pipeline for real scoring.`,
          data: { Source: "Demo (no pipeline molecules)" },
        });
      } else {
        setModelResult("orthogonal-rank", { status: "error", message: result.error });
      }
    }
  }

  const rankColors = ["#F57F17", "#90A4AE", "#CD7F32"];

  return (
    <>
      <WorkflowHeader badge={t("rankBadge")} title={t("rankTitle")} description={t("rankDesc")} />

      {/* Pipeline data status */}
      <div className="panel p-4 mb-4">
        <div className="flex items-center gap-2 mb-2">
          <Info size={14} className="text-teal" />
          <span className="text-sm font-bold text-ink">Ranking Data Source</span>
          <span className={`ml-auto rounded px-2 py-0.5 text-xs font-bold ${dataSource === "pipeline" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
            {dataSource === "pipeline" ? "Pipeline Data" : "Demo Data"}
          </span>
        </div>
        <div className="grid gap-2 md:grid-cols-3 text-xs">
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-300" />
            <span className="text-muted">Pipeline molecules: <b className="text-ink">{molecules.length}</b></span>
          </div>
          <div className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${molecules.some((m) => m.stepResults?.["admet-ai"]) ? "bg-emerald-500" : "bg-slate-300"}`} />
            <span className="text-muted">ADMET results: <b className="text-ink">{molecules.filter((m) => m.stepResults?.["admet-ai"]).length}/{molecules.length}</b></span>
          </div>
          <div className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${molecules.some((m) => m.stepResults?.["vina-dock"]) ? "bg-emerald-500" : "bg-slate-300"}`} />
            <span className="text-muted">Docking results: <b className="text-ink">{molecules.filter((m) => m.stepResults?.["vina-dock"]).length}/{molecules.length}</b></span>
          </div>
        </div>
      </div>

      <ModelSelector models={stepConfig.models} onRun={handleRun} running={running} />

      {Object.entries(results).map(([modelId, result]) => {
        const model = stepConfig.models.find((m) => m.id === modelId);
        return <ResultCard key={modelId} result={result} title={model?.name} />;
      })}

      {ranked.length > 0 && (
        <>
          {(reportUrl || savedCount > 0) && (
            <div className="panel mt-4 flex items-center justify-between gap-3 p-4">
              <div>
                <div className="text-sm font-bold text-ink">Ranking report ready</div>
                <p className="text-xs text-muted">{savedCount} molecules were saved to the backend database for this ranking run.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link href="/workflow/wetlab-handoff" className="btn-secondary">
                  <TestTube2 size={16} />
                  {t("wetlabGoHandoff")}
                </Link>
                {reportUrl && (
                  <button
                    onClick={() => window.open(reportUrl, "_blank", "noopener,noreferrer")}
                    className="btn-primary"
                  >
                    <Download size={16} />
                    Export XLSX
                  </button>
                )}
              </div>
            </div>
          )}

          {ranked.length > 0 && !reportUrl && savedCount === 0 && (
            <div className="panel mt-4 flex items-center justify-between gap-3 p-4">
              <p className="text-sm text-muted">{t("wetlabGapDesc").slice(0, 80)}…</p>
              <Link href="/workflow/wetlab-handoff" className="btn-secondary shrink-0">
                <TestTube2 size={16} />
                {t("wetlabGoHandoff")}
              </Link>
            </div>
          )}

          <div className="mt-5 grid gap-4 md:grid-cols-3">
            {[
              { title: t("rankMetricRule"), body: meta?.selection_rule || t("rankMetricRuleDesc"), color: "#1565C0" },
              { title: t("rankFinalRule"), body: meta?.final_score_rule || t("rankFinalRuleDesc"), color: "#00897B" },
              { title: t("rankArtifactSignal"), body: t("rankArtifactSignalDesc"), color: "#C62828" },
            ].map((card) => (
              <div key={card.title} className="panel p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Info size={14} style={{ color: card.color }} />
                  <span className="stat-label">{card.title}</span>
                </div>
                <p className="text-sm leading-6 text-muted">{card.body}</p>
              </div>
            ))}
          </div>

          <div className="panel mt-4 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    {[t("rankHeader"), t("rankCandidate"), t("rankPrimary"), t("rankOrthogonal"), t("rankGap"), t("rankFinal"), t("rankFlag")].map((h) => (
                      <th key={h} className="px-4 py-3 text-xs font-semibold text-muted whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {ranked.map((c, index) => (
                    <tr key={c.molecule_id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-2">
                          {index < 3 ? <Trophy size={15} style={{ color: rankColors[index] }} /> : <span className="w-[15px]" />}
                          <span className="font-bold text-ink">{index + 1}</span>
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-semibold text-ink">
                          {c.standard_name || getPipelineMoleculeDisplayName(molecules.find((mol) => mol.id === c.molecule_id) || { smiles: c.molecule_id })}
                        </div>
                        <div className="mt-0.5 text-xs text-muted font-mono">{c.selected_primary_model} / {c.selected_orthogonal_model}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-ink">{c.primary_value.toFixed(2)}</span>
                        <span className="ml-2 text-xs text-muted">(d={c.primary_desirability.toFixed(1)})</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-ink">{c.orthogonal_value.toFixed(3)}</span>
                        <span className="ml-2 text-xs text-muted">(d={c.orthogonal_desirability.toFixed(1)})</span>
                      </td>
                      <td className="px-4 py-3 font-mono text-muted">{c.consistency_gap.toFixed(1)}</td>
                      <td className="px-4 py-3"><span className="font-mono font-bold text-lg text-ink">{c.final_score.toFixed(1)}</span></td>
                      <td className="px-4 py-3">
                        {c.artifact_flag ? (
                          <span className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs font-semibold bg-red-50 text-red-700 border border-red-100">
                            <AlertTriangle size={12} />{t("rankArtifact")}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs font-semibold bg-green-50 text-green-700 border border-green-100">
                            <CheckCircle2 size={12} />{t("rankPass")}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}
