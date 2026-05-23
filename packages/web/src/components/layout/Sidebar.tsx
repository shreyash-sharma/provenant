"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { AlertTriangle, FileSearch, LayoutDashboard, Search, Trash2 } from "lucide-react";

const items = [
  { href: "/", label: "Ask", icon: LayoutDashboard },
  { href: "/search", label: "Search", icon: Search },
  { href: "/explorer", label: "Explorer", icon: FileSearch },
  { href: "/risk", label: "Risk", icon: AlertTriangle },
  { href: "/dead-code", label: "Dead Code", icon: Trash2 },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 w-64 border-r border-gray-800 bg-gray-950 px-4 py-5">
      <div className="mb-8">
        <div className="text-lg font-semibold text-white">Provenant</div>
        <div className="mt-1 text-xs text-gray-500">Repository model</div>
      </div>
      <nav className="space-y-1">
        {items.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition",
                active
                  ? "bg-brand-600 text-white"
                  : "text-gray-400 hover:bg-gray-900 hover:text-gray-100",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
