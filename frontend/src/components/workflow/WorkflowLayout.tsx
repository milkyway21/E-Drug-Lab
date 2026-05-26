"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, Circle, FlaskConical } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";

export const workflowStepKeys = [
  { href: "/workflow/target-prep", titleKey: "workflowStep1", descKey: "workflowStep1Desc", status: "stub" },
  { href: "/workflow/library-build", titleKey: "workflowStep2", descKey: "workflowStep2Desc", status: "stub" },
  { href: "/workflow/virtual-screening", titleKey: "workflowStep3", descKey: "workflowStep3Desc", status: "planned" },
  { href: "/workflow/admet-filter", titleKey: "workflowStep4", descKey: "workflowStep4Desc", status: "planned" },
  { href: "/workflow/affinity-eval", titleKey: "workflowStep5", descKey: "workflowStep5Desc", status: "planned" },
  { href: "/workflow/candidate-rank", titleKey: "workflowStep6", descKey: "workflowStep6Desc", status: "planned" }
] as const;

export function WorkflowShell({
  current,
  children
}: {
  current?: string;
  children: React.ReactNode;
}) {
  const { t } = useLang();
  return (
    <section className="page-shell grid gap-6 lg:grid-cols-[320px_1fr]">
      <aside className="panel p-4 lg:sticky lg:top-24 lg:self-start">
        <div className="mb-4 flex items-center gap-3 border-b border-slate-200 pb-4">
          <span className="inline-flex h-9 w-9 items-center justify-center bg-mist text-teal">
            <FlaskConical size={18} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-ink">{t("workflowTitle")}</h2>
            <p className="text-xs text-slate-500">{t("workflowDesc")}</p>
          </div>
        </div>
        <div className="space-y-2.5">
          {workflowStepKeys.map((step) => {
            const active = current === step.href;
            const Icon = step.status === "stub" ? CheckCircle2 : Circle;
            return (
              <Link
                key={step.href}
                href={step.href}
                className={`block border p-3 transition ${
                  active ? "border-ink bg-ink text-white shadow-soft" : "border-slate-200 bg-white hover:border-teal hover:shadow-soft"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className={`flex items-center gap-2 text-sm font-semibold ${active ? "text-white" : "text-ink"}`}>
                    <Icon size={15} className={active ? "text-white" : step.status === "stub" ? "text-teal" : "text-slate-400"} />
                    {t(step.titleKey)}
                  </span>
                  <ArrowRight size={14} className={active ? "text-white/70" : "text-slate-400"} />
                </div>
                <p className={`mt-1 text-xs leading-5 ${active ? "text-white/70" : "text-slate-600"}`}>{t(step.descKey)}</p>
              </Link>
            );
          })}
        </div>
      </aside>
      <div>{children}</div>
    </section>
  );
}

export function WorkflowHeader({
  title,
  description,
  badge
}: {
  title: string;
  description: string;
  badge?: string;
}) {
  return (
    <div className="mb-6 border-b border-slate-200 pb-5">
      {badge ? <div className="badge mb-3">{badge}</div> : null}
      <h1 className="text-3xl font-semibold leading-tight text-ink">{title}</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{description}</p>
    </div>
  );
}
