"use client";

import { Languages } from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";

export default function LanguageToggle() {
  const { lang, setLang } = useLang();

  return (
    <button
      type="button"
      title="切换语言"
      onClick={() => setLang(lang === "zh" ? "en" : "zh")}
      className="inline-flex h-9 w-9 items-center justify-center border border-transparent bg-transparent text-slate-600 transition hover:border-slate-200 hover:bg-white hover:text-ink"
    >
      <Languages size={17} />
    </button>
  );
}
