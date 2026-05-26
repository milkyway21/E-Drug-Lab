"use client";

import Link from "next/link";
import { BookOpen, Database, Server } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";

export default function DocsPage() {
  const { t } = useLang();
  return (
    <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6">
        <div className="stat-label mb-2">Documentation</div>
        <h1 className="text-3xl font-semibold text-ink">{t("docsTitle")}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{t("docsDesc")}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Link href="/" className="panel block p-5 transition hover:border-teal">
          <BookOpen size={20} className="text-teal" />
          <h2 className="mt-4 text-lg font-semibold text-ink">{t("docsOverview")}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">{t("docsOverviewDesc")}</p>
        </Link>
        <Link href="/database" className="panel block p-5 transition hover:border-teal">
          <Database size={20} className="text-cobalt" />
          <h2 className="mt-4 text-lg font-semibold text-ink">{t("docsMoleculeAPI")}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">{t("docsMoleculeAPIDesc")}</p>
        </Link>
        <Link href="/models" className="panel block p-5 transition hover:border-teal">
          <Server size={20} className="text-amber" />
          <h2 className="mt-4 text-lg font-semibold text-ink">{t("docsToolConfig")}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">{t("docsToolConfigDesc")}</p>
        </Link>
      </div>
    </section>
  );
}
