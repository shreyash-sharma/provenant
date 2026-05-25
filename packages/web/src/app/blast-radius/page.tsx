"use client";

import { useState } from "react";
import { Zap } from "lucide-react";
import { api, getApiError } from "@/lib/api";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import type { BlastRadiusResponse } from "@/lib/types";

function DepthBadge({ depth }: { depth: number }) {
  const cls =
    depth === 1
      ? "bg-signal-red/30 text-signal-red"
      : depth === 2
      ? "bg-signal-yellow/20 text-signal-yellow"
      : "bg-white/10 text-on-surface-muted";
  return (
    <span className={`inline-flex h-5 w-5 items-center justify-center rounded text-xs font-semibold ${cls}`}>
      {depth}
    </span>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.035] p-4">
      <div className="text-2xl font-bold text-on-surface">{value}</div>
      <div className="mt-1 text-xs text-on-surface-muted">{label}</div>
    </div>
  );
}

export default function BlastRadiusPage() {
  const [textarea, setTextarea] = useState("");
  const [maxDepth, setMaxDepth] = useState(3);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BlastRadiusResponse | null>(null);

  const handleAnalyze = async () => {
    const files = textarea
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (!files.length) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.blastRadius(files, maxDepth);
      setResult(data);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const sorted = result
    ? [...result.affected].sort((a, b) => a.depth - b.depth || a.file.localeCompare(b.file))
    : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-signal-yellow" />
          <h1 className="text-xl font-semibold text-on-surface">Blast Radius</h1>
        </div>
        <p className="mt-1 text-sm text-on-surface-muted">
          See which files are affected when you change a set of files.
        </p>
      </div>

      {/* Input area */}
      <div className="rounded-xl border border-white/[0.08] bg-white/[0.035] p-5 space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-on-surface-muted">
            File paths (one per line)
          </label>
          <textarea
            value={textarea}
            onChange={(e) => setTextarea(e.target.value)}
            placeholder={"Enter file paths, one per line\nsrc/auth.py\nsrc/models.py"}
            rows={5}
            className="w-full rounded-lg border border-white/[0.08] bg-background px-3 py-2 text-sm text-on-surface placeholder:text-on-surface-muted focus:outline-none focus:ring-1 focus:ring-white/20 font-mono"
          />
        </div>
        <div className="flex items-center gap-6">
          <div>
            <span className="mr-3 text-xs font-medium text-on-surface-muted">Max depth</span>
            {[1, 2, 3, 4, 5].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setMaxDepth(d)}
                className={`mr-1 h-8 w-8 rounded-lg text-sm font-medium transition ${
                  maxDepth === d
                    ? "bg-on-surface text-background"
                    : "border border-white/[0.08] text-on-surface-muted hover:text-on-surface"
                }`}
              >
                {d}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={loading || !textarea.trim()}
            className="ml-auto inline-flex items-center gap-2 rounded-lg bg-on-surface px-5 py-2 text-sm font-medium text-background transition hover:opacity-90 disabled:opacity-40"
          >
            {loading ? <LoadingSpinner size={4} /> : <Zap className="h-4 w-4" />}
            Analyze
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Stat cards */}
          <div className="grid grid-cols-3 gap-4">
            <StatCard label="Total affected files" value={result.stats.total_affected} />
            <StatCard label="Max depth reached" value={result.stats.max_depth_reached} />
            <StatCard label="Seed files" value={result.seed_files.length} />
          </div>

          {/* Table */}
          {sorted.length === 0 ? (
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.035] p-8 text-center text-sm text-on-surface-muted">
              No affected files found.
            </div>
          ) : (
            <div className="rounded-xl border border-white/[0.08] overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/[0.08] bg-white/[0.02]">
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-on-surface-muted">
                      File
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-on-surface-muted w-24">
                      Depth
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {sorted.map((item) => (
                    <tr key={item.file} className="hover:bg-white/[0.02]">
                      <td className="px-4 py-2.5 font-mono text-xs text-on-surface">{item.file}</td>
                      <td className="px-4 py-2.5">
                        <DepthBadge depth={item.depth} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
