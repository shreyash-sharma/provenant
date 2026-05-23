"use client";

import { useState } from "react";
import { FolderOpen } from "lucide-react";
import { api, getApiError } from "@/lib/api";
import { ExplorerEntry } from "@/components/explorer/ExplorerEntry";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import type { ContextResponse, ContextTarget } from "@/lib/types";

export default function ExplorerPage() {
  const [target, setTarget] = useState("");
  const [data, setData] = useState<ContextResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    const value = target.trim();
    if (!value) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.context([value], ["docs", "full_doc", "freshness", "source"]);
      setData(response);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const entry: ContextTarget | null = data?.targets ? Object.values(data.targets)[0] : null;

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex gap-2">
        <input
          value={target}
          onChange={(event) => setTarget(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && load()}
          placeholder="src/package/file.py or path::symbol"
          className="flex-1 rounded-lg border border-gray-700 bg-gray-900 px-4 py-2.5 font-mono text-sm text-gray-100 outline-none placeholder:text-gray-600 focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
        />
        <button
          onClick={load}
          disabled={loading || !target.trim()}
          className="flex min-w-24 items-center justify-center rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-500 disabled:opacity-40"
        >
          {loading ? <LoadingSpinner size={4} /> : "Explore"}
        </button>
      </div>
      {error && <ErrorBanner message={error} />}
      {entry && <ExplorerEntry entry={entry} />}
      {!entry && !loading && !error && (
        <div className="flex flex-col items-center justify-center gap-2 py-20 text-gray-600">
          <FolderOpen className="h-8 w-8 opacity-40" />
          <p className="text-sm">Enter a file path or symbol name.</p>
        </div>
      )}
    </div>
  );
}
