"use client";

import { CheckCircle2, Clock, ListChecks } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";

const records = [
  { titleKey: "", bodyKey: "", statusKey: "recordsStatusStub" },
  { titleKey: "", bodyKey: "", statusKey: "recordsStatusDb" },
  { titleKey: "", bodyKey: "", statusKey: "recordsStatusPlanned" },
];

export default function RecordsPage() {
  const { t } = useLang();
  return (
    <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6">
        <div className="stat-label mb-2">Execution records</div>
        <h1 className="text-3xl font-semibold text-ink">{t("recordsTitle")}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{t("recordsDesc")}</p>
      </div>
      <div className="grid gap-4">
        {[
          { title: t("recordsTargetSetup"), body: t("recordsTargetSetupBody"), status: t("recordsStatusStub") },
          { title: t("recordsSdfSync"), body: t("recordsSdfSyncBody"), status: t("recordsStatusDb") },
          { title: t("recordsDocking"), body: t("recordsDockingBody"), status: t("recordsStatusPlanned") }
        ].map(({ title, body, status }) => (
          <div key={title} className="panel flex flex-col gap-3 p-5 md:flex-row md:items-center md:justify-between">
            <div className="flex items-start gap-3">
              <ListChecks size={20} className="mt-1 text-teal" />
              <div>
                <h2 className="text-lg font-semibold text-ink">{title}</h2>
                <p className="mt-1 text-sm text-slate-600">{body}</p>
              </div>
            </div>
            <span className="inline-flex items-center gap-2 border border-slate-200 px-3 py-1 text-sm text-slate-600">
              {status === t("recordsStatusStub") ? <CheckCircle2 size={15} /> : <Clock size={15} />}
              {status}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
