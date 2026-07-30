"use client";

import Link from "next/link";
import { ArrowRight, Beaker, Database, FlaskConical, BarChart3, Award, ChevronRight, Brain, Filter } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { WorkflowHeader } from "@/components/workflow/WorkflowLayout";
import { PipelineRunner } from "@/components/workflow/PipelineRunner";
import { workflowSteps, implementedCount } from "@/lib/models-config";
import type { TranslationKey } from "@/lib/i18n/translations";

const stepIcons = [Beaker, Database, Filter, FlaskConical, BarChart3, Award, Brain];
const stepColors = ["#1565C0", "#00897B", "#F57F17", "#7B1FA2", "#5E35B1", "#C62828", "#AD1457"];

export default function WorkflowPage() {
  const { t } = useLang();
  return (
    <section className="page-shell">
      <WorkflowHeader badge={t("commonPipeline")} title={t("workflowTitle")} description={t("workflowDesc")} />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {workflowSteps.map((step, idx) => {
          const ready = implementedCount(step);
          const total = step.models.length;
          const Icon = stepIcons[idx] || FlaskConical;
          const color = stepColors[idx] || "#1565C0";
          const progress = total > 0 ? (ready / total) * 100 : 0;

          return (
            <Link key={step.href} href={step.href} className="group panel p-5 card-hover">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-11 w-11 items-center justify-center rounded-lg" style={{
                    background: `${color}10`, border: `1px solid ${color}20`,
                  }}>
                    <Icon size={20} style={{ color }} />
                  </span>
                  <div>
                    <div className="stat-label">{t("commonPipeline")} {step.step}</div>
                    <h2 className="mt-1 font-display text-lg font-bold text-ink">{t(step.titleKey as TranslationKey)}</h2>
                  </div>
                </div>
                <ArrowRight size={18} className="shrink-0 text-slate-300 transition-all group-hover:text-primary group-hover:translate-x-1" />
              </div>
              <p className="mt-3 text-sm leading-6 text-muted">{t(step.descKey as TranslationKey)}</p>
              <div className="mt-4 flex items-center gap-3">
                <div className="relative h-10 w-10 shrink-0">
                  <svg className="h-10 w-10 -rotate-90" viewBox="0 0 40 40">
                    <circle cx="20" cy="20" r="16" fill="none" stroke="#e5ebf0" strokeWidth="3" />
                    <circle cx="20" cy="20" r="16" fill="none" stroke={color} strokeWidth="3"
                      strokeDasharray={`${progress * 1.005} 100.5`} strokeLinecap="round" />
                  </svg>
                  <span className="absolute inset-0 flex items-center justify-center font-mono text-[10px] font-bold text-ink">{ready}</span>
                </div>
                <div>
                  <div className="text-xs text-muted">{ready}/{total} {t("commonModelsReady")}</div>
                  {ready > 0 && (
                    <span className="mt-1 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{
                      background: `${color}10`, color, border: `1px solid ${color}20`,
                    }}>
                      <span className="h-1 w-1 rounded-full" style={{ background: color }} />
                      {t("commonRunnable")}
                    </span>
                  )}
                </div>
              </div>
            </Link>
          );
        })}
      </div>

      <div className="panel mt-6 p-6">
        <h3 className="font-display text-sm font-bold text-ink mb-4">{t("workflowPipelineFlow")}</h3>
        <div className="flex items-center justify-between gap-2 overflow-x-auto pb-2">
          {workflowSteps.map((step, idx) => (
            <div key={step.href} className="flex items-center gap-2">
              <Link href={step.href} className="group flex flex-col items-center gap-1.5">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-50 border border-slate-200 transition-all group-hover:border-primary/30 group-hover:bg-primary-50">
                  {(() => { const I = stepIcons[idx] || FlaskConical; return <I size={18} style={{ color: stepColors[idx] }} />; })()}
                </span>
                <span className="text-[10px] font-semibold text-muted whitespace-nowrap">{t(step.titleKey as TranslationKey)}</span>
              </Link>
              {idx < workflowSteps.length - 1 && (
                <div className="flex items-center">
                  <div className="h-px w-8 bg-slate-200" />
                  <ChevronRight size={12} className="text-slate-300" />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <PipelineRunner />
    </section>
  );
}
