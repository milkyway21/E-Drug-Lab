"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, ArrowRight, Database, FlaskConical, Server, ShieldCheck, Workflow, Zap } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { apiClient } from "@/lib/api-client";

export default function HomePage() {
  const { t } = useLang();
  const [backendStatus, setBackendStatus] = useState("offline");
  const [tools, setTools] = useState<any>(null);

  useEffect(() => {
    apiClient.health().then((r) => { if (r.ok) setBackendStatus(r.data.status); });
    apiClient.readiness().then((r) => { if (r.ok) setTools(r.data); });
  }, []);

  return (
    <section className="page-shell">
      <div className="grid gap-6 lg:grid-cols-[1.45fr_0.9fr]">
        <div className="relative overflow-hidden bg-ink px-6 py-8 text-white shadow-panel sm:px-8">
          <div className="absolute right-8 top-8 hidden h-40 w-40 border border-white/10 lg:block" />
          <div className="absolute right-20 top-20 hidden h-20 w-20 border border-teal/50 lg:block" />
          <div className="mb-6 inline-flex items-center gap-2 border border-white/20 bg-white/5 px-3 py-1 text-sm text-white/80">
            <ShieldCheck size={16} />
            Lead generation workspace
          </div>
          <h1 className="max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">e-drug lab</h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-white/75">{t("homeHeroDesc")}</p>
          <div className="mt-6 grid max-w-2xl gap-3 sm:grid-cols-3">
            {[t("homeItem1"), t("homeItem2"), t("homeItem3")].map((item) => (
              <div key={item} className="border border-white/15 bg-white/5 px-3 py-3 text-sm text-white/80">
                <Zap size={14} className="mb-2 text-teal" />
                {item}
              </div>
            ))}
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/workflow" className="btn-primary">
              {t("homeStartWorkflow")}
              <ArrowRight size={16} />
            </Link>
            <Link href="/database" className="inline-flex h-10 items-center gap-2 border border-white/25 bg-white/5 px-4 text-sm font-semibold text-white transition hover:bg-white/10">
              {t("homeOpenDatabase")}
              <Database size={16} />
            </Link>
          </div>
        </div>

        <div className="panel p-6">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 pb-4">
            <div className="flex items-center gap-2">
              <Server size={18} className="text-cobalt" />
              <h2 className="text-lg font-semibold text-ink">{t("homeRuntimeStatus")}</h2>
            </div>
            <span className="badge">{apiClient.apiBaseUrl}</span>
          </div>
          <div className="mt-5 grid gap-3">
            <div className="surface p-4">
              <div className="stat-label">{t("homeBackend")}</div>
              <div className="mt-1 flex items-center gap-2 text-xl font-semibold text-ink">
                <Activity size={18} className={backendStatus === "healthy" ? "text-teal" : "text-rose"} />
                {backendStatus === "healthy" ? t("ready") : backendStatus === "degraded" ? t("degraded") : t("homeOffline")}
              </div>
            </div>
            <div className="surface p-4">
              <div className="stat-label">{t("homeTools")}</div>
              <div className="mt-1 text-xl font-semibold text-ink">
                {tools ? `${tools.tools_available}/${tools.tools_total}` : "0/0"}
              </div>
              <p className="mt-2 text-sm text-slate-600">
                {tools?.status === "ready" ? t("homeToolStatus") : t("homeToolOffline")}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        {[
          { title: t("homeCard1Title"), body: t("homeCard1Body"), icon: Workflow, href: "/workflow" },
          { title: t("homeCard2Title"), body: t("homeCard2Body"), icon: Database, href: "/database" },
          { title: t("homeCard3Title"), body: t("homeCard3Body"), icon: FlaskConical, href: "/models" }
        ].map((area) => {
          const Icon = area.icon;
          return (
            <Link key={area.title} href={area.href} className="panel group block p-5 transition hover:-translate-y-0.5 hover:border-teal">
              <span className="inline-flex h-10 w-10 items-center justify-center bg-mist text-teal transition group-hover:bg-teal group-hover:text-white">
                <Icon size={21} />
              </span>
              <h2 className="mt-4 text-lg font-semibold text-ink">{area.title}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">{area.body}</p>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
