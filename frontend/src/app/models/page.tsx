"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, Wrench } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { apiClient } from "@/lib/api-client";
import {
  workflowSteps,
  implementedCount,
  type ModelStatus,
} from "@/lib/tool-registry";

function isAvailable(status: ModelStatus): boolean {
  return status === "implemented" || status === "partial";
}

export default function ModelsPage() {
  const { t } = useLang();
  const [tools, setTools] = useState<
    { name: string; executable_path?: string; available?: boolean }[]
  >([]);

  useEffect(() => {
    apiClient.readiness().then((r) => {
      if (r.ok) setTools(Object.values(r.data.tools));
    });
  }, []);

  return (
    <section className="page-shell">
      <h1 className="mb-6 font-display text-3xl font-bold tracking-tight text-ink">
        {t("modelsTitle")}
      </h1>

      <div className="space-y-4">
        {workflowSteps.map((step) => {
          const available = implementedCount(step);
          const total = step.models.length;
          return (
            <div key={step.href} className="panel overflow-hidden">
              <div className="flex items-center justify-between gap-3 border-b border-slate-100 bg-slate-50 px-5 py-3">
                <h2 className="font-display text-sm font-bold text-ink">{t(step.titleKey)}</h2>
                <span className="text-xs text-muted">
                  {available}/{total} {t("commonModelsReady")}
                </span>
              </div>
              <ul className="divide-y divide-slate-100">
                {step.models.map((model) => {
                  const ok = isAvailable(model.status);
                  return (
                    <li
                      key={model.id}
                      className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50/80"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-ink">{model.name}</span>
                          {model.tag && (
                            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                              {model.tag}
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 truncate text-xs text-muted">{model.description}</p>
                      </div>
                      <span
                        className={`inline-flex shrink-0 items-center rounded px-2 py-0.5 text-[11px] font-semibold border ${
                          ok
                            ? "bg-green-50 text-green-700 border-green-100"
                            : "bg-slate-50 text-slate-400 border-slate-200"
                        }`}
                      >
                        {ok ? t("commonAvailable") : t("commonUnavailable")}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>

      <div className="panel mt-6 overflow-hidden">
        <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50 px-5 py-3">
          <Wrench size={14} className="text-primary" />
          <span className="font-display text-sm font-bold text-ink">{t("toolsLocalBinaries")}</span>
        </div>
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100">
              <th className="px-5 py-3 text-xs font-semibold text-muted">{t("commonTool")}</th>
              <th className="px-5 py-3 text-xs font-semibold text-muted">{t("toolPath")}</th>
              <th className="px-5 py-3 text-xs font-semibold text-muted">{t("commonStatus")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {tools.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-5 py-8 text-center text-muted">
                  {t("toolsOffline")}
                </td>
              </tr>
            ) : (
              tools.map((tool) => (
                <tr key={tool.name} className="transition-colors hover:bg-slate-50">
                  <td className="px-5 py-3 font-semibold text-ink">{tool.name}</td>
                  <td className="px-5 py-3 font-mono text-xs text-muted">
                    {tool.executable_path || "—"}
                  </td>
                  <td className="px-5 py-3">
                    {tool.available ? (
                      <span className="inline-flex items-center gap-1.5 rounded border border-green-100 bg-green-50 px-2 py-1 text-xs font-semibold text-green-700">
                        <CheckCircle2 size={12} />
                        {t("toolAvailable")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-semibold text-slate-400">
                        <XCircle size={12} />
                        {t("toolMissing")}
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
