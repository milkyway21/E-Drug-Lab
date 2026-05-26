"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Database, FileText, FlaskConical, History, Hexagon, Workflow } from "lucide-react";
import LanguageToggle from "./LanguageToggle";
import { useLang } from "@/lib/i18n/i18n-context";

const navItems = [
  { href: "/", key: "navHome", icon: Activity },
  { href: "/workflow", key: "navWorkflow", icon: Workflow },
  { href: "/database", key: "navDatabase", icon: Database },
  { href: "/models", key: "navModels", icon: FlaskConical },
  { href: "/records", key: "navRecords", icon: History },
  { href: "/docs", key: "navDocs", icon: FileText }
] as const;

export default function NavBar() {
  const pathname = usePathname();
  const { t } = useLang();

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <Link href="/" className="group flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center bg-ink text-white shadow-soft transition group-hover:bg-teal">
            <Hexagon size={20} />
          </span>
          <span>
            <span className="block text-base font-semibold leading-5 text-ink">{t("product")}</span>
            <span className="block text-xs leading-5 text-slate-500">{t("tagline")}</span>
          </span>
        </Link>

        <nav className="flex flex-wrap items-center gap-1.5">
          {navItems.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex h-9 items-center gap-2 border px-3 text-sm font-medium transition ${
                  active
                    ? "border-ink bg-ink text-white shadow-soft"
                    : "border-transparent bg-transparent text-slate-600 hover:border-slate-200 hover:bg-white hover:text-ink"
                }`}
              >
                <Icon size={16} />
                <span>{t(item.key)}</span>
              </Link>
            );
          })}
          <LanguageToggle />
        </nav>
      </div>
    </header>
  );
}
