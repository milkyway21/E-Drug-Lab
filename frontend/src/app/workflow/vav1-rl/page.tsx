"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Download, FlaskConical, Play, RefreshCw, Table2 } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { apiClient } from "@/lib/api-client";
import { useLang } from "@/lib/i18n/i18n-context";
import { useWorkflow } from "@/lib/workflow-context";

/** Step numbers stay 1–11 for API compatibility; step 9 (similarity) is omitted from UI. */
const STEPS = [
  { n: 1, title: "patent 预处理 + 4 轮 GLARE 预训练", tag: "GLARE GNN+GRPO" },
  { n: 2, title: "DiffGui 生成（60% frag_cond + 40% denovo）", tag: "生成" },
  { n: 3, title: "化学有效性 11 项 + e-drug-lab 22 ADMET", tag: "ADMET" },
  { n: 4, title: "成药性第一轮 QED/SA/MW/LogP/TPSA/Lipinski/Lilly", tag: "成药性" },
  { n: 5, title: "Vina + Glide XP + MM-GBSA 正交（0.1/0.3/0.6）", tag: "对接" },
  { n: 6, title: "去重 vs large_library + known_439", tag: "去重" },
  { n: 7, title: "GLARE 排序", tag: "GLARE" },
  { n: 8, title: "最终排序 0.05/0.15/0.8", tag: "最终排序" },
  { n: 10, title: "排序集 RL 训练", tag: "RL" },
  { n: 11, title: "第二轮生成+筛选+验证 PASS/FAIL", tag: "验证" },
];

type StepStatus = "pending" | "running" | "done" | "error";
type Funnel = Record<string, { total: number; retained: number; rejected: number }>;
type Artifact = { path: string; size: number };

export default function Vav1RLPage() {
  return (
    <WorkflowShell current="/workflow/vav1-rl">
      <Vav1RLContent />
    </WorkflowShell>
  );
}

function Vav1RLContent() {
  const { t } = useLang();
  const { addMolecules } = useWorkflow();
  const [mode, setMode] = useState<"test" | "full">("test");
  const [numMols, setNumMols] = useState(1000);
  const [steps, setSteps] = useState<Record<number, StepStatus>>({});
  const [funnel, setFunnel] = useState<Funnel>({});
  const [running, setRunning] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [showArtifacts, setShowArtifacts] = useState(false);

  const refreshFunnel = useCallback(async () => {
    const r = await apiClient.vav1RlFunnel();
    if (r.ok) {
      setFunnel(r.data.funnel as Funnel);
      const status = r.data.status as { steps_done?: number[]; current_step?: number };
      const done: Record<number, StepStatus> = {};
      (status?.steps_done || []).forEach((s) => (done[s] = "done"));
      if (status?.current_step) done[status.current_step] = "running";
      setSteps(done);
    }
  }, []);

  const checkHealth = useCallback(async () => {
    const r = await apiClient.vav1RlHealth();
    if (r.ok) setHealth(r.data);
  }, []);

  const loadArtifacts = useCallback(async () => {
    const r = await apiClient.vav1RlArtifacts();
    if (r.ok) setArtifacts((r.data.files as Artifact[]) || []);
  }, []);

  useEffect(() => {
    refreshFunnel();
    checkHealth();
    loadArtifacts();
  }, [refreshFunnel, checkHealth, loadArtifacts]);

  // job polling
  useEffect(() => {
    if (!jobId || !running) return;
    const timer = setInterval(async () => {
      const r = await apiClient.vav1RlStatus(jobId);
      if (!r.ok) return;
      const data = r.data as { status?: string; funnel?: Funnel; current_step?: number };
      if (data.funnel) setFunnel(data.funnel);
      if (data.current_step) setSteps((prev) => ({ ...prev, [data.current_step as number]: "running" }));
      if (data.status === "completed" || data.status === "failed") {
        setRunning(false);
        clearInterval(timer);
        refreshFunnel();
        loadArtifacts();
        apiClient.vav1RlReport().then((rr) => rr.ok && setReport((rr.data.content as string) || null));
        apiClient.vav1RlTopMolecules(20).then((tr) => {
          if (tr.ok && tr.data.ok && tr.data.molecules.length > 0) {
            const mols = tr.data.molecules.map((m, idx) => ({
              smiles: m.smiles,
              name: m.name || `rl-top-${idx + 1}`,
              originalName: m.name || `rl-top-${idx + 1}`,
            }));
            addMolecules(mols, "rl-pipeline-top20", { replace: true });
          }
        });
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [jobId, running, refreshFunnel, loadArtifacts, addMolecules]);

  async function runAll() {
    setRunning(true);
    setSteps({});
    setLog((l) => [...l, `[run] mode=${mode} num_mols=${numMols}`]);
    const r = await apiClient.vav1RlRun({ mode, num_mols: numMols });
    if (r.ok) setJobId(r.data.job_id);
    else { setRunning(false); setLog((l) => [...l, `[error] ${r.error}`]); }
  }

  async function runStep(n: number) {
    setSteps((prev) => ({ ...prev, [n]: "running" }));
    setLog((l) => [...l, `[step${n}] 开始`]);
    const r = await apiClient.vav1RlRunStep(n, { mode, num_mols: numMols });
    if (r.ok) {
      setSteps((prev) => ({ ...prev, [n]: "done" }));
      if (r.data.funnel) setFunnel((prev) => ({ ...prev, [n]: r.data.funnel as { total: number; retained: number; rejected: number } }));
      setLog((l) => [...l, `[step${n}] 完成: ${JSON.stringify(r.data.result).slice(0, 120)}`]);
      refreshFunnel();
      loadArtifacts();
    } else {
      setSteps((prev) => ({ ...prev, [n]: "error" }));
      setLog((l) => [...l, `[step${n}] 失败: ${r.error}`]);
    }
  }

  const statusColor: Record<StepStatus, string> = {
    pending: "bg-slate-200 text-slate-500",
    running: "bg-amber-100 text-amber-700 animate-pulse",
    done: "bg-teal-100 text-teal-700",
    error: "bg-rose-100 text-rose-700",
  };

  const maxFunnelTotal = Math.max(1, ...Object.values(funnel).map((f) => f.total || 0));

  return (
    <>
      <WorkflowHeader
        badge={t("vav1RlBadge")}
        title={t("vav1RlTitle")}
        description={t("vav1RlDesc")}
      />

      {/* 模块健康 */}
      <div className="panel p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={16} className="text-cobalt" />
          <h3 className="font-display text-sm font-bold text-ink">{t("vav1RlHealthTitle")}</h3>
          <button onClick={() => { checkHealth(); loadArtifacts(); }} className="ml-auto text-xs text-cobalt hover:underline flex items-center gap-1">
            <RefreshCw size={12} />{t("vav1RlRefresh")}
          </button>
        </div>
        <div className="grid grid-cols-4 gap-3 text-xs">
          <HealthCard label="Schrödinger (Glide/prime_mmgbsa)" data={health?.schrodinger} />
          <HealthCard label="GLARE GNN+GRPO" data={health?.glare_gnn} />
          <HealthCard label="ADMET-AI" data={health?.admet} />
          <HealthCard label="Vina Docker" data={health?.vina} />
        </div>
      </div>

      {/* 运行控制 */}
      <div className="panel p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <FlaskConical size={16} className="text-teal" />
          <h3 className="font-display text-sm font-bold text-ink">{t("vav1RlRunControl")}</h3>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2">
            {t("vav1RlMode")}:
            <select value={mode} onChange={(e) => setMode(e.target.value as "test" | "full")} className="input-field w-44">
              <option value="test">{t("vav1RlModeTest")}</option>
              <option value="full">{t("vav1RlModeFull")}</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            {t("vav1RlNumMols")}:
            <input type="number" value={numMols} onChange={(e) => setNumMols(Number(e.target.value))} className="input-field w-24" />
          </label>
          <button onClick={runAll} disabled={running} className="btn-primary flex items-center gap-1 disabled:opacity-50">
            <Play size={14} /> {running ? t("vav1RlRunning") : t("vav1RlRunAll")}
          </button>
          <span className="text-xs text-muted">{t("vav1RlPocketNote")}</span>
        </div>
      </div>

      {/* 漏斗可视化 */}
      {Object.keys(funnel).length > 0 && (
        <div className="panel p-4 mb-4">
          <h3 className="font-display text-sm font-bold text-ink mb-3">{t("vav1RlFunnelTitle")}</h3>
          <div className="space-y-2">
            {[3, 4, 5, 6, 7, 8].map((n) => {
              const f = funnel[String(n)];
              if (!f) return null;
              const pct = maxFunnelTotal > 0 ? (f.retained / maxFunnelTotal) * 100 : 0;
              const rejPct = maxFunnelTotal > 0 ? (f.rejected / maxFunnelTotal) * 100 : 0;
              return (
                <div key={n} className="flex items-center gap-2 text-xs">
                  <span className="w-14 text-right font-mono text-muted">step{n}</span>
                  <div className="flex-1 h-4 bg-slate-100 rounded overflow-hidden flex">
                    <div className="bg-teal-400 h-full transition-all" style={{ width: `${Math.max(1, pct)}%` }} title={`retained: ${f.retained}`} />
                    <div className="bg-rose-300 h-full transition-all" style={{ width: `${Math.max(0, rejPct)}%` }} title={`rejected: ${f.rejected}`} />
                  </div>
                  <span className="w-20 text-right font-mono">✓{f.retained} / ✗{f.rejected}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 流程步骤（跳过 step9 相似搜索） */}
      <div className="panel p-4 mb-4">
        <h3 className="font-display text-sm font-bold text-ink mb-3">{t("vav1RlStepsTitle")}</h3>
        <div className="space-y-2">
          {STEPS.map((s) => {
            const st = steps[s.n] || "pending";
            const f = funnel[String(s.n)];
            return (
              <div key={s.n} className="flex items-center gap-3 p-2 rounded border border-slate-100">
                <span className={`px-2 py-0.5 rounded text-xs font-mono ${statusColor[st]}`}>step{s.n}</span>
                <span className="text-sm text-ink flex-1">{s.title}</span>
                <span className="text-xs text-muted px-2 py-0.5 bg-slate-50 rounded">{s.tag}</span>
                {f && (
                  <span className="text-xs text-muted font-mono">
                    total={f.total} ✓{f.retained} ✗{f.rejected}
                  </span>
                )}
                {st === "error" ? (
                  <button onClick={() => runStep(s.n)} disabled={running} className="text-xs px-2 py-1 rounded bg-rose-50 text-rose-600 hover:bg-rose-100 disabled:opacity-50">
                    {t("vav1RlStepRetry")}
                  </button>
                ) : (
                  <button onClick={() => runStep(s.n)} disabled={running} className="text-xs px-2 py-1 rounded bg-cobalt-50 text-cobalt hover:bg-cobalt-100 disabled:opacity-50">
                    {t("vav1RlStepVerify")}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 产物文件 */}
      <div className="panel p-4 mb-4">
        <div className="flex items-center gap-2 mb-2">
          <Table2 size={14} className="text-cobalt" />
          <h3 className="font-display text-sm font-bold text-ink">{t("vav1RlArtifactsTitle")}</h3>
          <button onClick={loadArtifacts} className="ml-auto text-xs text-cobalt hover:underline flex items-center gap-1"><RefreshCw size={12} /></button>
          <button onClick={() => setShowArtifacts(!showArtifacts)} className="text-xs text-muted hover:underline">
            {showArtifacts ? "收起" : "展开"} ({artifacts.length})
          </button>
        </div>
        {showArtifacts && (
          <div className="max-h-48 overflow-auto text-xs font-mono bg-slate-50 p-2 rounded">
            {artifacts.length === 0 && <span className="text-muted">（暂无产物文件）</span>}
            {artifacts.map((a) => (
              <div key={a.path} className="flex justify-between py-0.5 hover:bg-slate-100">
                <span className="truncate max-w-md">{a.path}</span>
                <span className="text-muted ml-2">{a.size > 1024 ? `${(a.size / 1024).toFixed(1)}K` : `${a.size}B`}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 导出报告 */}
      <div className="panel p-4 mb-4">
        <div className="flex items-center gap-2">
          <Download size={14} className="text-teal" />
          <h3 className="font-display text-sm font-bold text-ink">{t("vav1RlExportReport")}</h3>
          <button
            onClick={async () => {
              const r = await apiClient.vav1RlReport();
              if (r.ok && r.data.content) {
                const blob = new Blob([r.data.content], { type: "text/markdown" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url; a.download = "rl_pipeline_report.md"; a.click();
                URL.revokeObjectURL(url);
              }
            }}
            className="ml-auto text-xs px-3 py-1 rounded bg-teal-50 text-teal-700 hover:bg-teal-100"
          >
            {t("vav1RlArtifactsDownload")} MD
          </button>
        </div>
      </div>

      {/* 日志 */}
      <div className="panel p-4 mb-4">
        <h3 className="font-display text-sm font-bold text-ink mb-2">{t("vav1RlLogTitle")}</h3>
        <pre className="text-xs font-mono text-muted bg-slate-50 p-3 rounded max-h-48 overflow-auto">
          {log.length ? log.join("\n") : t("vav1RlLogEmpty")}
        </pre>
      </div>

      {/* 报告 */}
      <div className="panel p-4">
        <h3 className="font-display text-sm font-bold text-ink mb-2">{t("vav1RlReportTitle")}</h3>
        <pre className="text-xs font-mono text-ink bg-slate-50 p-3 rounded max-h-96 overflow-auto whitespace-pre-wrap">
          {report || t("vav1RlReportEmpty")}
        </pre>
      </div>
    </>
  );
}

function HealthCard({ label, data }: { label: string; data: unknown }) {
  const d = data as Record<string, unknown> | undefined;
  const ok = d?.ok || d?.installed || d?.available || d?.status === "healthy";
  const version = d?.version ? String(d.version) : null;
  const error = d?.error ? String(d.error) : null;
  return (
    <div className="p-2 rounded border border-slate-100">
      <div className="font-semibold text-ink mb-1">{label}</div>
      <div className={`text-xs ${ok ? "text-teal-600" : "text-rose-600"}`}>{ok ? "✓ 可用" : "✗ 不可用"}</div>
      {version && <div className="text-xs text-muted truncate">{version}</div>}
      {error && <div className="text-xs text-rose-500 truncate">{error}</div>}
    </div>
  );
}
