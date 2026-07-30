"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle, CheckCircle2, Download, FlaskConical, Loader2, Package, RefreshCw, TestTube2,
} from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { apiClient } from "@/lib/api-client";
import { useLang } from "@/lib/i18n/i18n-context";
import { getPipelineMoleculeDisplayName, useWorkflow } from "@/lib/workflow-context";

type WetlabPrep = {
  compound_id: string;
  smiles: string;
  name?: string;
  rank?: number;
  molecular_weight?: number;
  sa_score?: number;
  synthesis_risk: string;
  chiral_centers: number;
  wetlab_ready: boolean;
  blockers: string[];
  notes: string[];
  structural_alerts: string[];
  structural_warnings: string[];
  dmso_stock_mg_10mm_1ml?: number;
  dmso_note?: string;
  pubchem_cid?: number;
  pubchem_url?: string;
  sourcing_hint?: string;
};

const RISK_COLORS: Record<string, string> = {
  low: "bg-emerald-50 text-emerald-700 border-emerald-100",
  medium: "bg-amber-50 text-amber-700 border-amber-100",
  high: "bg-red-50 text-red-700 border-red-100",
};

export default function WetlabHandoffPage() {
  return (
    <WorkflowShell current="/workflow/wetlab-handoff">
      <WetlabHandoffContent />
    </WorkflowShell>
  );
}

function WetlabHandoffContent() {
  const { t } = useLang();
  const { molecules, target, roundId } = useWorkflow();
  const [preps, setPreps] = useState<WetlabPrep[]>([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topN, setTopN] = useState(10);
  const [checkPubchem, setCheckPubchem] = useState(true);
  const [assayType, setAssayType] = useState("BRET / pDC50");
  const [cellLine, setCellLine] = useState("");

  const candidates = useMemo(() => {
    return molecules.slice(0, Math.max(1, topN)).map((m, i) => ({
      smiles: m.smiles,
      name: getPipelineMoleculeDisplayName(m),
      rank: i + 1,
    }));
  }, [molecules, topN]);

  const targetCode = (target?.pdbId || target?.name || "UNK").replace(/\s+/g, "").slice(0, 12);

  const runAnalyze = useCallback(async () => {
    if (candidates.length === 0) {
      setError(t("wetlabNoMolecules"));
      return;
    }
    setLoading(true);
    setError(null);
    const res = await apiClient.analyzeWetlab({
      molecules: candidates,
      target_code: targetCode,
      batch_id: `R${roundId || 1}`,
      check_pubchem: checkPubchem,
    });
    setLoading(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    setPreps(res.data.molecules as WetlabPrep[]);
  }, [candidates, targetCode, roundId, checkPubchem, t]);

  async function handleExport() {
    if (candidates.length === 0) return;
    setExporting(true);
    const res = await apiClient.exportWetlabOrderPack({
      molecules: candidates,
      target_code: targetCode,
      batch_id: `R${roundId || 1}`,
      target_name: target?.name || "",
      target_protein: target?.name || "",
      assay_type: assayType,
      cell_line: cellLine,
      round_id: roundId || 1,
      check_pubchem: checkPubchem,
    });
    setExporting(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `wetlab_order_pack_r${roundId || 1}_${targetCode}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const readyCount = preps.filter((p) => p.wetlab_ready).length;

  return (
    <>
      <WorkflowHeader
        badge={t("wetlabBadge")}
        title={t("wetlabTitle")}
        description={t("wetlabDesc")}
      />

      <div className="panel p-4 mb-4 border-l-4 border-l-teal">
        <div className="flex items-start gap-3">
          <TestTube2 size={20} className="text-teal shrink-0 mt-0.5" />
          <div className="text-sm leading-6 text-muted">
            <p className="font-semibold text-ink mb-1">{t("wetlabGapTitle")}</p>
            <p>{t("wetlabGapDesc")}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 mb-4">
        <div className="panel p-4">
          <div className="stat-label mb-3">{t("wetlabParams")}</div>
          <div className="space-y-3 text-sm">
            <label className="block">
              <span className="text-muted">{t("wetlabTopN")}</span>
              <input
                type="number"
                min={1}
                max={50}
                value={topN}
                onChange={(e) => setTopN(Number(e.target.value))}
                className="mt-1 w-full rounded border border-slate-200 px-3 py-2"
              />
            </label>
            <label className="block">
              <span className="text-muted">{t("wetlabAssayType")}</span>
              <input
                value={assayType}
                onChange={(e) => setAssayType(e.target.value)}
                className="mt-1 w-full rounded border border-slate-200 px-3 py-2"
              />
            </label>
            <label className="block">
              <span className="text-muted">{t("wetlabCellLine")}</span>
              <input
                value={cellLine}
                onChange={(e) => setCellLine(e.target.value)}
                placeholder="e.g. HEK293"
                className="mt-1 w-full rounded border border-slate-200 px-3 py-2"
              />
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={checkPubchem} onChange={(e) => setCheckPubchem(e.target.checked)} />
              <span className="text-muted">{t("wetlabCheckPubchem")}</span>
            </label>
          </div>
        </div>

        <div className="panel p-4">
          <div className="stat-label mb-3">{t("wetlabSource")}</div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted">{t("wetlabPipelineMols")}</span>
              <b className="text-ink">{molecules.length}</b>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">{t("wetlabSelected")}</span>
              <b className="text-ink">{candidates.length}</b>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">{t("wetlabTarget")}</span>
              <b className="text-ink font-mono">{targetCode}</b>
            </div>
            {molecules.length === 0 && (
              <p className="text-xs text-amber-700 bg-amber-50 rounded p-2 mt-2">
                {t("wetlabNoMoleculesHint")}{" "}
                <Link href="/workflow/candidate-rank" className="underline font-semibold">
                  {t("workflowStep6")}
                </Link>
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 mb-4">
        <button onClick={runAnalyze} disabled={loading || candidates.length === 0} className="btn-primary">
          {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          {t("wetlabAnalyze")}
        </button>
        <button onClick={handleExport} disabled={exporting || candidates.length === 0} className="btn-secondary">
          {exporting ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
          {t("wetlabExportPack")}
        </button>
      </div>

      {error && (
        <div className="panel p-3 mb-4 text-sm text-red-700 bg-red-50 border border-red-100">{error}</div>
      )}

      {preps.length > 0 && (
        <>
          <div className="grid gap-3 md:grid-cols-4 mb-4">
            {[
              { label: t("wetlabStatTotal"), value: preps.length, icon: Package },
              { label: t("wetlabStatReady"), value: readyCount, icon: CheckCircle2 },
              { label: t("wetlabStatBlocked"), value: preps.length - readyCount, icon: AlertTriangle },
              { label: t("wetlabStatChiral"), value: preps.filter((p) => p.chiral_centers > 0).length, icon: FlaskConical },
            ].map(({ label, value, icon: Icon }) => (
              <div key={label} className="panel p-4 flex items-center gap-3">
                <Icon size={18} className="text-teal" />
                <div>
                  <div className="text-xs text-muted">{label}</div>
                  <div className="text-xl font-bold text-ink">{value}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="panel overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    {[t("wetlabColId"), t("wetlabColName"), "SA", t("wetlabColRisk"), t("wetlabColChiral"), "DMSO (mg)", t("wetlabColSourcing"), t("wetlabColStatus")].map((h) => (
                      <th key={h} className="px-4 py-3 text-xs font-semibold text-muted whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {preps.map((p) => (
                    <tr key={p.compound_id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-mono text-xs text-ink">{p.compound_id}</td>
                      <td className="px-4 py-3">
                        <div className="font-semibold text-ink">{p.name}</div>
                        <div className="text-xs text-muted font-mono truncate max-w-[180px]">{p.smiles}</div>
                      </td>
                      <td className="px-4 py-3 font-mono">{p.sa_score?.toFixed(1) ?? "—"}</td>
                      <td className="px-4 py-3">
                        <span className={`rounded px-2 py-0.5 text-xs font-semibold border ${RISK_COLORS[p.synthesis_risk] || RISK_COLORS.medium}`}>
                          {p.synthesis_risk}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono">{p.chiral_centers}</td>
                      <td className="px-4 py-3 font-mono text-xs">{p.dmso_stock_mg_10mm_1ml ?? "—"}</td>
                      <td className="px-4 py-3 text-xs">
                        {p.pubchem_url ? (
                          <a href={p.pubchem_url} target="_blank" rel="noopener noreferrer" className="text-teal underline">
                            CID {p.pubchem_cid}
                          </a>
                        ) : (
                          <span className="text-muted">{p.sourcing_hint}</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {p.wetlab_ready ? (
                          <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
                            <CheckCircle2 size={12} /> OK
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs font-semibold text-red-700" title={p.blockers.join("; ")}>
                            <AlertTriangle size={12} /> {p.blockers[0]?.slice(0, 30)}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel mt-4 p-4 text-sm text-muted">
            <p className="font-semibold text-ink mb-2">{t("wetlabNextSteps")}</p>
            <ol className="list-decimal list-inside space-y-1">
              <li>{t("wetlabStep1")}</li>
              <li>{t("wetlabStep2")}</li>
              <li>
                {t("wetlabStep3")}{" "}
                <Link href="/workflow/rl-training" className="text-teal underline font-semibold">
                  {t("workflowStep7")}
                </Link>
              </li>
            </ol>
          </div>
        </>
      )}
    </>
  );
}
