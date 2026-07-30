"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Activity, Database, FileText, FlaskConical, History, Workflow, Menu, X } from "lucide-react";
import LanguageToggle from "./LanguageToggle";
import { useLang } from "@/lib/i18n/i18n-context";
import Image from "next/image";

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
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-slate-150 bg-white/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
        {/* Logo */}
        <Link href="/" className="group flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center overflow-hidden rounded-full border border-slate-200 bg-white transition-colors group-hover:border-primary-200">
            <Image
              src="/brand/atom-scientist-fab.png"
              alt="e-drug lab"
              width={40}
              height={40}
              className="h-10 w-10 object-cover"
              priority
            />
          </span>
          <span>
            <span className="block font-display text-base font-bold leading-5 tracking-tight text-ink">{t("product")}</span>
            <span className="block text-[11px] font-medium leading-4 text-muted">{t("tagline")}</span>
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden items-center gap-1 lg:flex">
          {navItems.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`relative inline-flex h-9 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-all ${
                  active
                    ? "bg-primary-50 text-primary"
                    : "text-muted hover:text-ink hover:bg-slate-50"
                }`}
              >
                <Icon size={16} />
                <span>{t(item.key)}</span>
                {active && (
                  <span className="absolute inset-x-2 -bottom-[13px] h-[2px] rounded-full bg-primary" />
                )}
              </Link>
            );
          })}
          <div className="ml-2">
            <LanguageToggle />
          </div>
        </nav>

        {/* Mobile hamburger */}
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-muted lg:hidden hover:bg-slate-50"
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="border-t border-slate-100 px-4 py-3 lg:hidden bg-white">
          <nav className="flex flex-col gap-1">
            {navItems.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  className={`inline-flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-all ${
                    active
                      ? "bg-primary-50 text-primary"
                      : "text-muted hover:text-ink hover:bg-slate-50"
                  }`}
                >
                  <Icon size={16} />
                  <span>{t(item.key)}</span>
                </Link>
              );
            })}
            <div className="mt-2 border-t border-slate-100 pt-2">
              <LanguageToggle />
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
