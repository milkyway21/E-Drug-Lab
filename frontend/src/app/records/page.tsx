"use client";

import { useEffect, useState } from "react";
import { History, Inbox, RefreshCw } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { apiClient } from "@/lib/api-client";

type PipelineRunSummary = {
  id: string;
  status: string;
  recipe_json?: { name?: string };
  created_at?: string;
  error_message?: string;
  current_step_id?: string;
};

export default function RecordsPage() {
  const { t } = useLang();
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const loadRuns = () => {
    setLoading(true);
    apiClient.listPipelineRuns(1, 20).then((res) => {
      if (res.ok) setRuns(res.data.runs as PipelineRunSummary[]);
      setLoading(false);
    });
  };

  useEffect(() => {
    loadRuns();
  }, []);

  const runStatusColor: Record<string, string> = {
    completed: "text-emerald-600",
    running: "text-amber-600",
    failed: "text-red-600",
    cancelled: "text-slate-500",
    pending: "text-slate-400",
  };

  return (
    <section className="page-shell">
      <h1 className="mb-6 font-display text-3xl font-bold tracking-tight text-ink">
        {t("recordsTitle")}
      </h1>

      <div className="panel p-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History size={16} className="text-primary" />
            <h2 className="font-display text-sm font-bold text-ink">{t("recordsListTitle")}</h2>
          </div>
          <button
            type="button"
            onClick={loadRuns}
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            <RefreshCw size={12} />
            {t("recordsRefresh")}
          </button>
        </div>

        {loading ? (
          <p className="py-6 text-center text-sm text-muted">{t("recordsLoading")}</p>
        ) : runs.length === 0 ? (
          <div className="py-10 text-center">
            <Inbox size={36} className="mx-auto mb-3 text-slate-200" />
            <h3 className="mb-2 font-display text-lg font-bold text-ink">{t("recordsNoRuns")}</h3>
            <p className="text-sm text-muted">{t("recordsNoRunsDesc")}</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {runs.map((run) => (
              <div
                key={run.id}
                className="flex flex-col gap-2 py-3 md:flex-row md:items-center md:justify-between"
              >
                <div>
                  <p className="text-sm font-semibold text-ink">
                    {run.recipe_json?.name || t("recordsUntitledRun")}
                  </p>
                  <p className="font-mono text-xs text-muted">{run.id.slice(0, 8)}…</p>
                  {run.current_step_id && (
                    <p className="text-[10px] text-slate-400">
                      {t("recordsStep")}: {run.current_step_id}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-semibold capitalize ${
                      runStatusColor[run.status] || "text-slate-500"
                    }`}
                  >
                    {run.status}
                  </span>
                  {run.created_at && (
                    <span className="text-[10px] text-slate-400">
                      {new Date(run.created_at).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
