"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BookOpen, ChevronDown, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import type { ProjectResponse } from "@/lib/types";

const primaryNav = [
  { href: "/model", label: "Model" },
  { href: "/wiki", label: "Wiki" },
  { href: "/knowledge", label: "Map" },
  { href: "/repair", label: "Repair" },
] as const;

const secondaryNav = [
  { href: "/risk", label: "Risk" },
  { href: "/blast-radius", label: "Blast Radius" },
  { href: "/decisions", label: "Decisions" },
  { href: "/dead-code", label: "Dead Code" },
  { href: "/operations", label: "Ops" },
  { href: "/agent-interface", label: "API" },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    api.project()
      .then((data) => {
        if (!alive) return;
        setProject(data);
        setApiOk(true);
      })
      .catch(() => {
        if (!alive) return;
        setApiOk(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const current = useMemo(() => {
    const all = [...primaryNav, ...secondaryNav];
    return all.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));
  }, [pathname]);

  return (
    <div className="min-h-screen bg-background text-on-surface">
      <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-background/82 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1240px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <Link href="/model" className="flex min-w-0 items-center gap-3">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-on-surface text-sm font-semibold text-background">
              P
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-on-surface">Provenant</div>
              <div className="truncate text-xs text-on-surface-subtle">
                {project?.name || "Repository model"}
              </div>
            </div>
          </Link>

          <nav className="hidden items-center rounded-full border border-white/[0.08] bg-white/[0.035] p-1 md:flex">
            {primaryNav.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-full px-3 py-1.5 text-sm transition ${
                    active
                      ? "bg-on-surface text-background"
                      : "text-on-surface-muted hover:text-on-surface"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="flex items-center gap-2">
            <div className="hidden items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.035] px-3 py-1.5 text-xs text-on-surface-muted sm:flex">
              <Activity className={apiOk === false ? "h-3.5 w-3.5 text-signal-red" : "h-3.5 w-3.5 text-signal-green"} />
              <span>{apiOk === false ? "Offline" : apiOk ? "Live" : "Checking"}</span>
            </div>
            <div className="relative">
              <button
                type="button"
                onClick={() => setMoreOpen((open) => !open)}
                className="inline-flex h-9 items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.035] px-3 text-sm text-on-surface-muted transition hover:text-on-surface"
              >
                {current?.label || "More"}
                <ChevronDown className="h-3.5 w-3.5" />
              </button>
              {moreOpen && (
                <div className="absolute right-0 mt-2 w-48 rounded-xl border border-white/[0.08] bg-surface-container-lowest p-1 shadow-2xl shadow-black/40">
                  <div className="md:hidden">
                    {primaryNav.map((item) => (
                      <MenuLink key={item.href} href={item.href} label={item.label} pathname={pathname} />
                    ))}
                    <div className="my-1 border-t border-white/[0.06]" />
                  </div>
                  {secondaryNav.map((item) => (
                    <MenuLink key={item.href} href={item.href} label={item.label} pathname={pathname} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1240px] px-4 py-8 sm:px-6 lg:px-8">
        {children}
      </main>

      <a
        href="https://www.shreyashsharma.com/writing/provenant"
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Open the Provenant white paper in a new tab"
        className="fixed bottom-4 left-4 z-30 inline-flex h-10 items-center gap-2 rounded-full border border-white/[0.08] bg-background/76 px-4 text-sm text-on-surface-muted shadow-2xl shadow-black/30 backdrop-blur-xl transition hover:text-on-surface"
      >
        <BookOpen className="h-4 w-4 text-signal-cyan" />
        White Paper
        <ExternalLink className="h-3.5 w-3.5" />
      </a>

    </div>
  );
}

function MenuLink({ href, label, pathname }: { href: string; label: string; pathname: string }) {
  const active = pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      className={`block rounded-lg px-3 py-2 text-sm transition ${
        active ? "bg-white/[0.08] text-on-surface" : "text-on-surface-muted hover:bg-white/[0.05] hover:text-on-surface"
      }`}
    >
      {label}
    </Link>
  );
}
