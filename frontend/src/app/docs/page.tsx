"use client";

import Link from "next/link";
import { BookOpen, Database, Server, Workflow, Code2, ExternalLink, ChevronRight } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";

export default function DocsPage() {
  const { t, lang } = useLang();

  const sections = [
    {
      title: t("docsGettingStarted"), icon: BookOpen, color: "#1565C0",
      items: [
        { label: t("docsQuickStart"), desc: t("docsQuickStartDesc"), status: "available" },
        { label: t("docsArchitecture"), desc: t("docsArchitectureDesc"), status: "available" },
        { label: t("docsEnvConfig"), desc: t("docsEnvConfigDesc"), status: "available" },
      ]
    },
    {
      title: t("docsWorkflowPipeline"), icon: Workflow, color: "#00897B",
      items: [
        { label: t("docsTargetPrep"), desc: t("docsTargetPrepDesc"), href: "/workflow/target-prep" },
        { label: t("docsCompoundSourcing"), desc: t("docsCompoundSourcingDesc"), href: "/workflow/library-build" },
        { label: t("docsAdmetFilter"), desc: t("docsAdmetFilterDesc"), href: "/workflow/admet-filter" },
        { label: t("docsAffinityEval"), desc: t("docsAffinityEvalDesc"), href: "/workflow/affinity-eval" },
        { label: t("docsCandidateRanking"), desc: t("docsCandidateRankingDesc"), href: "/workflow/candidate-rank" },
      ]
    },
    {
      title: t("docsApiRef"), icon: Code2, color: "#F57F17",
      items: [
        { label: "GET /health", desc: t("docsHealthEndpoint"), status: "available" },
        { label: "GET /ready", desc: t("docsReadyEndpoint"), status: "available" },
        { label: "POST /api/v1/targets/download", desc: t("docsTargetDownload"), status: "available" },
        { label: "GET /api/v1/molecule-db/molecules", desc: t("docsMolDbList"), status: "available" },
        { label: "POST /api/v1/ranking/orthogonal-rescore", desc: t("docsOrthoRescore"), status: "available" },
      ]
    },
    {
      title: t("docsIntegrations"), icon: Server, color: "#7B1FA2",
      items: [
        { label: t("docsTameVsDocker"), desc: t("docsTameVsDockerDesc"), status: "available" },
        { label: t("docsDrugclipService"), desc: t("docsDrugclipServiceDesc"), status: "partial" },
        { label: t("docsSchrodinger"), desc: t("docsSchrodingerDesc"), status: "planned" },
        { label: t("docsDiffDynamic"), desc: t("docsDiffDynamicDesc"), status: "available" },
      ]
    },
  ];

  return (
    <section className="page-shell">
      <div className="mb-8">
        <div className="stat-label mb-2 flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          {t("commonDocumentation")}
        </div>
        <h1 className="font-display text-3xl font-bold text-ink tracking-tight">{t("docsTitle")}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">{t("docsDesc")}</p>
      </div>

      <div className="grid gap-3 mb-8 md:grid-cols-3">
        {[
          { title: t("docsOverview"), desc: t("docsOverviewDesc"), icon: BookOpen, href: "/", color: "#1565C0" },
          { title: t("docsMoleculeAPI"), desc: t("docsMoleculeAPIDesc"), icon: Database, href: "/database", color: "#00897B" },
          { title: t("docsToolConfig"), desc: t("docsToolConfigDesc"), icon: Server, href: "/models", color: "#F57F17" },
        ].map((card) => {
          const Icon = card.icon;
          return (
            <Link key={card.title} href={card.href} className="group panel p-5 card-hover">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg" style={{
                background: `${card.color}10`, border: `1px solid ${card.color}20`,
              }}>
                <Icon size={20} style={{ color: card.color }} />
              </span>
              <h2 className="mt-3 font-display text-base font-bold text-ink">{card.title}</h2>
              <p className="mt-1 text-sm text-muted">{card.desc}</p>
              <div className="mt-3 flex items-center gap-1 text-xs font-semibold transition-all group-hover:gap-2" style={{ color: card.color }}>
                <span>{t("commonView")}</span><ChevronRight size={14} />
              </div>
            </Link>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {sections.map((section) => {
          const Icon = section.icon;
          return (
            <div key={section.title} className="panel overflow-hidden">
              <div className="flex items-center gap-2.5 px-5 py-4 bg-slate-50 border-b border-slate-100">
                <Icon size={16} style={{ color: section.color }} />
                <h3 className="font-display text-sm font-bold text-ink">{section.title}</h3>
              </div>
              <div className="divide-y divide-slate-100">
                {section.items.map((item) => {
                  const content = (
                    <div className="flex items-center justify-between px-5 py-3 hover:bg-slate-50 transition-colors">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-ink">{item.label}</span>
                          {"status" in item && item.status === "partial" && (
                            <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-100">{t("commonPartial")}</span>
                          )}
                          {"status" in item && item.status === "planned" && (
                            <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold bg-slate-50 text-slate-400 border border-slate-200">{t("commonPlanned")}</span>
                          )}
                        </div>
                        <p className="mt-0.5 text-xs text-muted">{item.desc}</p>
                      </div>
                      {"href" in item && item.href && <ExternalLink size={14} className="shrink-0 text-slate-400" />}
                    </div>
                  );
                  if ("href" in item && item.href) return <Link key={item.label} href={item.href}>{content}</Link>;
                  return <div key={item.label}>{content}</div>;
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="panel mt-6 p-6">
        <h3 className="font-display text-sm font-bold text-ink mb-4">{t("docsTechStack")}</h3>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            { name: "FastAPI", desc: t("docsTechFastapi"), version: "0.110+" },
            { name: "Next.js", desc: t("docsTechNextjs"), version: "14.x" },
            { name: "RDKit", desc: t("docsTechRdkit"), version: "2024.03" },
            { name: "PostgreSQL", desc: t("docsTechPg"), version: "15+" },
          ].map((tech) => (
            <div key={tech.name} className="rounded-lg p-3 bg-slate-50 border border-slate-100">
              <div className="text-sm font-semibold text-ink">{tech.name}</div>
              <div className="text-xs text-muted">{tech.desc}</div>
              <div className="mt-1 font-mono text-[10px] text-slate-400">{tech.version}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
