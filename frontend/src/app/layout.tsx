import type { Metadata } from "next";
import "./globals.css";
import NavBar from "@/components/NavBar";
import Footer from "@/components/Footer";
import AppShell from "@/components/agent/AppShell";
import { I18nProvider } from "@/lib/i18n/i18n-context";

export const metadata: Metadata = {
  title: "e-drug lab — 药物发现工作台",
  description: "Drug discovery workspace: target prep, virtual screening, ADMET, and affinity evaluation"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen font-body antialiased">
        <I18nProvider>
          <AppShell>
            <div className="flex min-h-screen flex-col">
              <NavBar />
              <main className="flex-1">{children}</main>
              <Footer />
            </div>
          </AppShell>
        </I18nProvider>
      </body>
    </html>
  );
}
