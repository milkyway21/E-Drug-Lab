"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { Lang, TranslationKey, translations } from "./translations";

type I18nContextValue = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: TranslationKey) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = useState<Lang>("zh");
  const value = useMemo<I18nContextValue>(
    () => ({
      lang,
      setLang,
      t: (key) => translations[lang][key] || translations.zh[key]
    }),
    [lang]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useLang() {
  const value = useContext(I18nContext);
  if (!value) {
    throw new Error("useLang must be used inside I18nProvider");
  }
  return value;
}
