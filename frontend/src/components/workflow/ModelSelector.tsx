"use client";

import { useState } from "react";
import { CheckCircle2, Circle, Loader2, Play, Settings } from "lucide-react";
import type { WorkflowModel } from "@/lib/models-config";
import { useLang } from "@/lib/i18n/i18n-context";

interface ModelSelectorProps {
  models: WorkflowModel[];
  onRun: (selectedIds: string[]) => void;
  running?: boolean;
  defaultSelectedIds?: string[];
}

export function ModelSelector({ models, onRun, running = false, defaultSelectedIds }: ModelSelectorProps) {
  const { t } = useLang();
  const [selected, setSelected] = useState<Set<string>>(() => {
    const init = new Set<string>();
    if (defaultSelectedIds && defaultSelectedIds.length > 0) {
      defaultSelectedIds.forEach((id) => init.add(id));
      return init;
    }
    models.forEach((m) => { if (m.status === "implemented") init.add(m.id); });
    return init;
  });

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const selectedImplemented = models.filter(
    (m) => selected.has(m.id) && m.status !== "placeholder"
  );

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Settings size={16} className="text-primary" />
          <h3 className="font-display text-sm font-bold text-ink">{t("availableModels")}</h3>
        </div>
        <span className="text-xs text-muted">
          {selectedImplemented.length} {t("selectedCount")}
        </span>
      </div>

      <div className="mt-4 space-y-2">
        {models.map((model) => {
          const isSelected = selected.has(model.id);
          const isReady = model.status !== "placeholder";

          return (
            <div
              key={model.id}
              onClick={() => isReady && toggle(model.id)}
              className={`group relative flex items-start gap-3 rounded-lg p-4 transition-all ${
                isReady
                  ? "cursor-pointer border hover:border-primary/20 hover:bg-primary-50/30"
                  : "cursor-not-allowed opacity-40"
              } ${isSelected && isReady ? "border-primary/20 bg-primary-50/50" : "border-slate-150"}`}
            >
              <div className="mt-0.5 shrink-0">
                {isSelected && isReady ? (
                  <CheckCircle2 size={18} className="text-primary" />
                ) : (
                  <Circle size={18} className="text-slate-300" />
                )}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-ink">{model.name}</span>
                  {model.tag && (
                    <span className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                      model.tag === "Docker" ? "bg-blue-50 text-blue-600 border border-blue-100" :
                      model.tag === "API" ? "bg-amber-50 text-amber-700 border border-amber-100" :
                      model.tag === "AI" ? "bg-purple-50 text-purple-600 border border-purple-100" :
                      model.tag === "HPC" ? "bg-orange-50 text-orange-600 border border-orange-100" :
                      "bg-slate-50 text-slate-500 border border-slate-200"
                    }`}>
                      {model.tag}
                    </span>
                  )}
                  <StatusBadge status={model.status} />
                </div>
                <p className="mt-1 text-xs leading-5 text-muted">{model.description}</p>
              </div>
            </div>
          );
        })}
      </div>

      {selectedImplemented.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            onClick={() => onRun(Array.from(selected))}
            disabled={running}
            className="btn-primary"
          >
            {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            {t("runSelected")} ({selectedImplemented.length})
          </button>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const { t } = useLang();
  const available = status === "implemented" || status === "partial";
  if (available) {
    return (
      <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold bg-green-50 text-green-700 border border-green-100">
        <span className="h-1 w-1 rounded-full bg-green-500" />
        {t("commonAvailable")}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold bg-slate-50 text-slate-400 border border-slate-200">
      {t("commonUnavailable")}
    </span>
  );
}
