"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { WorkflowHeader, workflowStepKeys } from "@/components/workflow/WorkflowLayout";

export default function WorkflowPage() {
  const { t } = useLang();
  return (
    <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <WorkflowHeader
        badge="Pipeline"
        title={t("workflowTitle")}
        description={t("workflowDesc")}
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {workflowStepKeys.map((step, index) => (
          <Link key={step.href} href={step.href} className="panel block p-5 transition hover:border-teal">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="stat-label">Step {index + 1}</div>
                <h2 className="mt-2 text-lg font-semibold text-ink">{t(step.titleKey)}</h2>
              </div>
              <ArrowRight size={18} className="text-slate-500" />
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-600">{t(step.descKey)}</p>
            <span className="mt-4 inline-flex border border-slate-200 px-2 py-1 text-xs text-slate-600">
              {step.status === "stub" ? "API stub ready" : "planned"}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
