"use client";

import { useLang } from "@/lib/i18n/i18n-context";

export default function Footer() {
  const { t } = useLang();
  return (
    <footer className="border-t border-slate-200/80 bg-white/80">
      <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 text-sm text-slate-500 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <span className="font-medium text-ink">e-drug lab</span>
        <span>{t("footerText")}</span>
      </div>
    </footer>
  );
}
