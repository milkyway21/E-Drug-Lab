"use client";

import { useLang } from "@/lib/i18n/i18n-context";

export default function Footer() {
  const { t } = useLang();
  return (
    <footer className="border-t border-slate-150 bg-white/80 backdrop-blur-sm">
      <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 text-sm sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <div className="flex items-center gap-3">
          <span className="font-display font-bold text-ink">e-drug lab</span>
          <span className="rounded bg-primary-50 px-1.5 py-0.5 text-[10px] font-medium text-primary">
            {t("leadGenWorkspace")}
          </span>
          <span className="text-xs text-slate-400">v0.1.0</span>
        </div>
        <span className="text-xs text-muted">{t("footerText")}</span>
      </div>
    </footer>
  );
}
