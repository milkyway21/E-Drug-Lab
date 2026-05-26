"use client";

import { useEffect, useState } from "react";
import { Cpu, FlaskConical, Wrench } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { apiClient } from "@/lib/api-client";

export default function ModelsPage() {
  const { t } = useLang();
  const [tools, setTools] = useState<any[]>([]);

  useEffect(() => {
    apiClient.readiness().then((r) => {
      if (r.ok) setTools(Object.values(r.data.tools));
    });
  }, []);

  return (
    <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6">
        <div className="stat-label mb-2">Models and tools</div>
        <h1 className="text-3xl font-semibold text-ink">{t("modelsTitle")}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{t("modelsDesc")}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {[
          ["AutoDock Vina", "Docking worker target", Wrench],
          ["Fpocket", "Binding pocket detection", FlaskConical],
          ["External APIs", "Schrodinger, DrugClip, TAME-VS, and DiffDynamic", Cpu]
        ].map(([title, body, Icon]) => (
          <div key={title as string} className="panel p-5">
            <Icon size={20} className="text-teal" />
            <h2 className="mt-4 text-lg font-semibold text-ink">{title as string}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">{body as string}</p>
          </div>
        ))}
      </div>

      <div className="panel mt-6 overflow-hidden">
        <div className="border-b border-slate-200 bg-mist px-4 py-3 text-sm font-medium text-ink">{t("toolsHeader")}</div>
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <tbody className="divide-y divide-slate-100">
            {tools.length === 0 ? (
              <tr><td className="px-4 py-6 text-slate-600">{t("toolsOffline")}</td></tr>
            ) : (
              tools.map((tool) => (
                <tr key={tool.name}>
                  <td className="px-4 py-3 font-medium text-ink">{tool.name}</td>
                  <td className="px-4 py-3 text-slate-600">{tool.executable_path}</td>
                  <td className="px-4 py-3 text-slate-600">{tool.available ? t("toolAvailable") : t("toolMissing")}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
