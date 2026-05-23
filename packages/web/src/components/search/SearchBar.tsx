"use client";

import { Search } from "lucide-react";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";

const PAGE_TYPES = ["", "file_page", "symbol_spotlight", "module_page", "cross_package"];

export function SearchBar({
  query,
  pageType,
  loading,
  onQueryChange,
  onPageTypeChange,
  onSubmit,
}: {
  query: string;
  pageType: string;
  loading: boolean;
  onQueryChange: (value: string) => void;
  onPageTypeChange: (value: string) => void;
  onSubmit: () => void;
}) {
  return (
    <div className="flex gap-2">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && onSubmit()}
          placeholder="Search the codebase wiki"
          className="w-full rounded-lg border border-gray-700 bg-gray-900 py-2.5 pl-10 pr-4 text-sm text-gray-100 outline-none placeholder:text-gray-600 focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
        />
      </div>
      <select
        value={pageType}
        onChange={(event) => onPageTypeChange(event.target.value)}
        className="rounded-lg border border-gray-700 bg-gray-900 px-3 text-sm text-gray-300 outline-none focus:border-brand-500"
      >
        {PAGE_TYPES.map((type) => (
          <option key={type} value={type}>
            {type || "All types"}
          </option>
        ))}
      </select>
      <button
        onClick={onSubmit}
        disabled={loading || !query.trim()}
        className="flex min-w-24 items-center justify-center rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-500 disabled:opacity-40"
      >
        {loading ? <LoadingSpinner size={4} /> : "Search"}
      </button>
    </div>
  );
}
