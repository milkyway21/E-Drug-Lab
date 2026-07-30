"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  Database,
  FlaskConical,
  Server,
  Workflow,
  Beaker,
  GitBranch,
  BarChart3,
  Sparkles,
} from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { apiClient } from "@/lib/api-client";
import { TOOL_REGISTRY } from "@/lib/tool-registry";

export default function HomePage() {
  const { t } = useLang();
  const [backendStatus, setBackendStatus] = useState("checking");
  const [localBins, setLocalBins] = useState<{ available: number; total: number } | null>(null);

  const registryTools = Object.values(TOOL_REGISTRY);
  const modelsImplemented = registryTools.filter((m) => m.status === "implemented").length;
  const modelsTotal = registryTools.length;

  useEffect(() => {
    apiClient.health().then((r) => {
      if (r.ok) setBackendStatus(r.data.status);
      else setBackendStatus("offline");
    });
    apiClient.readiness().then((r) => {
      if (r.ok) {
        setLocalBins({
          available: r.data.tools_available,
          total: r.data.tools_total,
        });
      }
    });
  }, []);

  const featureCards = [
    { title: t("homeCard1Title"), body: t("homeCard1Body"), icon: Workflow, href: "/workflow", color: "primary" },
    { title: t("homeCard2Title"), body: t("homeCard2Body"), icon: Database, href: "/database", color: "teal" },
    { title: t("homeCard3Title"), body: t("homeCard3Body"), icon: FlaskConical, href: "/models", color: "amber" },
  ];

  const pipelineSteps = [
    { icon: Beaker, label: t("homeItem1"), color: "#1565C0" },
    { icon: GitBranch, label: t("homeItem2"), color: "#00897B" },
    { icon: BarChart3, label: t("homeItem3"), color: "#F9A825" },
  ];

  const statusLabel =
    backendStatus === "healthy"
      ? t("ready")
      : backendStatus === "degraded"
        ? t("degraded")
        : backendStatus === "checking"
          ? "..."
          : t("homeOffline");

  return (
    <section className="page-shell relative">
      {/* Soft lab atmosphere */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-8 h-[420px] overflow-hidden"
      >
        <div className="absolute left-1/2 top-0 h-[360px] w-[720px] -translate-x-1/2 rounded-full bg-[radial-gradient(ellipse_at_center,rgba(21,101,192,0.10),transparent_70%)]" />
        <div className="absolute right-0 top-16 h-48 w-48 rounded-full bg-[radial-gradient(circle,rgba(0,137,123,0.08),transparent_70%)]" />
      </div>

      <div className="relative grid gap-6 lg:grid-cols-[1.55fr_0.85fr]">
        {/* Hero — brand first */}
        <div className="panel relative overflow-hidden p-8 sm:p-10 accent-line-primary animate-fade-in">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-[radial-gradient(circle,rgba(21,101,192,0.08),transparent_70%)]"
          />

          <div className="mb-5 inline-flex items-center gap-2 rounded-md border border-primary-100 bg-primary-50 px-3 py-1 text-xs font-semibold tracking-wide text-primary">
            <Sparkles size={13} />
            {t("leadGenWorkspace")}
          </div>

          <h1 className="font-display text-4xl font-extrabold leading-none tracking-tight text-ink sm:text-5xl">
            e-drug lab
          </h1>
          <p className="mt-3 max-w-xl text-base font-medium text-primary/80">
            {t("homeHeroTitle")}
          </p>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-muted sm:text-base">
            {t("homeHeroDesc")}
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-2.5">
            {pipelineSteps.map((step, i) => (
              <div key={step.label} className="flex items-center gap-2.5">
                <div className="flex items-center gap-2 rounded-lg border border-slate-150 bg-slate-50 px-3 py-2 text-sm text-ink">
                  <step.icon size={14} style={{ color: step.color }} />
                  <span className="font-medium">{step.label}</span>
                </div>
                {i < pipelineSteps.length - 1 && (
                  <div className="hidden h-px w-5 bg-slate-200 sm:block" />
                )}
              </div>
            ))}
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/workflow" className="btn-primary">
              {t("homeStartWorkflow")}
              <ArrowRight size={16} />
            </Link>
            <Link href="/database" className="btn-secondary">
              {t("homeOpenDatabase")}
              <Database size={16} />
            </Link>
          </div>
        </div>

        {/* Runtime status */}
        <div className="panel flex flex-col p-6 animate-slide-up">
          <div
            className="flex items-center justify-between gap-3 pb-4"
            style={{ borderBottom: "1px solid #e5ebf0" }}
          >
            <div className="flex items-center gap-2">
              <Server size={17} className="text-primary" />
              <h2 className="font-display text-base font-bold text-ink">
                {t("homeRuntimeStatus")}
              </h2>
            </div>
            <span className="badge font-mono text-[10px]">{apiClient.apiBaseUrl}</span>
          </div>

          <div className="mt-5 flex flex-1 flex-col gap-3">
            <div className="surface p-4">
              <div className="stat-label">{t("homeBackend")}</div>
              <div className="mt-2 flex items-center gap-3">
                <span
                  className={
                    backendStatus === "healthy"
                      ? "status-dot-online"
                      : backendStatus === "checking"
                        ? "status-dot-warning"
                        : "status-dot-offline"
                  }
                />
                <span className="font-display text-xl font-bold text-ink">{statusLabel}</span>
              </div>
            </div>

            <div className="surface flex-1 p-4">
              <div className="stat-label">{t("homeTools")}</div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="font-display text-2xl font-bold text-ink">
                  {modelsImplemented}
                </span>
                <span className="text-sm text-muted">/ {modelsTotal}</span>
              </div>
              <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-1000"
                  style={{
                    width: `${modelsTotal > 0 ? (modelsImplemented / modelsTotal) * 100 : 0}%`,
                  }}
                />
              </div>
              <p className="mt-2 text-xs text-muted">{t("homeToolsHint")}</p>
              {localBins && (
                <p className="mt-1 text-[11px] text-slate-400">
                  {t("homeLocalBins")}: {localBins.available}/{localBins.total}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Feature cards */}
      <div className="relative mt-6 grid gap-4 md:grid-cols-3">
        {featureCards.map((area, idx) => {
          const Icon = area.icon;
          const colorMap: Record<string, { bg: string; border: string; text: string }> = {
            primary: { bg: "#e3f2fd", border: "#bbdefb", text: "#1565C0" },
            teal: { bg: "#e0f2f1", border: "#b2dfdb", text: "#00897B" },
            amber: { bg: "#fff8e1", border: "#ffecb3", text: "#F57F17" },
          };
          const c = colorMap[area.color] || colorMap.primary;
          return (
            <Link
              key={area.title}
              href={area.href}
              className={`group block panel p-5 card-hover animate-slide-up stagger-${idx + 1}`}
              style={{ opacity: 0 }}
            >
              <span
                className="inline-flex h-11 w-11 items-center justify-center rounded-lg transition-transform group-hover:scale-105"
                style={{ background: c.bg, border: `1px solid ${c.border}` }}
              >
                <Icon size={20} style={{ color: c.text }} />
              </span>
              <h2 className="mt-4 font-display text-lg font-bold text-ink">{area.title}</h2>
              <p className="mt-2 text-sm leading-6 text-muted">{area.body}</p>
              <div
                className="mt-4 flex items-center gap-1 text-xs font-semibold transition-all group-hover:gap-2"
                style={{ color: c.text }}
              >
                <span>{t("commonExplore")}</span>
                <ArrowRight size={14} />
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
