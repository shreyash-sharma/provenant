"use client";

import { usePathname } from "next/navigation";

const titles: Record<string, string> = {
  "/": "Ask",
  "/search": "Search",
  "/explorer": "Explorer",
  "/risk": "Risk",
  "/dead-code": "Dead Code",
};

export function TopBar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-10 border-b border-gray-800 bg-gray-950/95 px-8 py-4 backdrop-blur">
      <div className="flex items-center justify-between">
        <h1 className="text-base font-semibold text-white">
          {titles[pathname] ?? "Provenant"}
        </h1>
        <div className="font-mono text-xs text-gray-500">
          {process.env.NEXT_PUBLIC_API_URL || "http://localhost:7337"}
        </div>
      </div>
    </header>
  );
}
