"use client";

import { useLang } from "@/lib/i18n/i18n-context";

export default function LanguageToggle() {
  const { lang, setLang } = useLang();

  return (
    <button
      type="button"
      title={lang === "zh" ? "Switch to English" : "切换到中文"}
      onClick={() => setLang(lang === "zh" ? "en" : "zh")}
      className="relative inline-flex h-8 items-center rounded-full px-1 text-xs font-semibold transition-all bg-slate-50 border border-slate-200"
      style={{ minWidth: '72px' }}
    >
      <span
        className="absolute h-6 w-8 rounded-md transition-all duration-300 ease-out bg-white shadow-sm border border-slate-200"
        style={{ left: lang === "zh" ? '4px' : '36px' }}
      />
      <span className={`relative z-10 flex-1 text-center transition-colors ${lang === "zh" ? "text-primary font-bold" : "text-muted"}`}>
        中文
      </span>
      <span className={`relative z-10 flex-1 text-center transition-colors ${lang === "en" ? "text-primary font-bold" : "text-muted"}`}>
        EN
      </span>
    </button>
  );
}
