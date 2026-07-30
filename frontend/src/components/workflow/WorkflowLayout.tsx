"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, Circle, FlaskConical, TestTube2 } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { MoleculePanel } from "./MoleculePanel";
import { workflowSteps } from "@/lib/models-config";
import type { TranslationKey } from "@/lib/i18n/translations";

export const workflowStepKeys = workflowSteps.map((step) => ({
  href: step.href,
  titleKey: step.titleKey,
  descKey: step.descKey,
  status: "stub" as const,
}));

const extraWorkflowLinks: Array<{ href: string; titleKey: TranslationKey; descKey: TranslationKey; afterHref: string }> = [
  {
    href: "/workflow/wetlab-handoff",
    titleKey: "workflowWetlabHandoff",
    descKey: "workflowWetlabHandoffDesc",
    afterHref: "/workflow/candidate-rank",
  },
];

export function WorkflowShell({ current, children }: { current?: string; children: React.ReactNode }) {
  const { t } = useLang();
  return (
    <section className="page-shell grid gap-6 lg:grid-cols-[280px_1fr_280px]">
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
          {workflowStepKeys.flatMap((step) => {
            const extras = extraWorkflowLinks.filter((e) => e.afterHref === step.href);
            const items = [
              <WorkflowNavLink key={step.href} step={step} current={current} t={t} />,
              ...extras.map((extra) => (
                <WorkflowNavLink
                  key={extra.href}
                  step={{ href: extra.href, titleKey: extra.titleKey, descKey: extra.descKey, status: "stub" }}
                  current={current}
                  t={t}
                  icon={TestTube2}
                />
              )),
            ];
            return items;
          })}
        </div>
      </aside>
      <div>{children}</div>
      <MoleculePanel />
    </section>
  );
}

export function WorkflowHeader({ title, description, badge }: { title: string; description: string; badge?: string }) {
  return (
    <div className="mb-6 border-b border-slate-200 pb-5">
      {badge ? <div className="badge mb-3">{badge}</div> : null}
      <h1 className="text-3xl font-semibold leading-tight text-ink">{title}</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{description}</p>
    </div>
  );
}

function WorkflowNavLink({
  step,
  current,
  t,
  icon: CustomIcon,
}: {
  step: { href: string; titleKey: TranslationKey; descKey: TranslationKey; status: string };
  current?: string;
  t: (key: TranslationKey) => string;
  icon?: typeof TestTube2;
}) {
  const active = current === step.href;
  const Icon = CustomIcon || (step.status === "stub" ? CheckCircle2 : Circle);
  const cls = ["block border p-3 transition", active ? "border-ink bg-ink text-white shadow-soft" : "border-slate-200 bg-white hover:border-teal hover:shadow-soft"].join(" ");
  return (
    <Link href={step.href} className={cls}>
      <div className="flex items-center justify-between gap-3">
        <span className={["flex items-center gap-2 text-sm font-semibold", active ? "text-white" : "text-ink"].join(" ")}>
          <Icon size={15} className={active ? "text-white" : step.status === "stub" ? "text-teal" : "text-slate-400"} />
          {t(step.titleKey)}
        </span>
        <ArrowRight size={14} className={active ? "text-white/70" : "text-slate-400"} />
      </div>
      <p className={["mt-1 text-xs leading-5", active ? "text-white/70" : "text-slate-600"].join(" ")}>{t(step.descKey)}</p>
    </Link>
  );
}
