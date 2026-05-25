"use client";

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api, getApiError } from "@/lib/api";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { RiskDetail } from "@/components/risk/RiskDetail";
import { RiskTable } from "@/components/risk/RiskTable";
import { useRiskOverview } from "@/hooks/useProvenant";
import type { RiskHeatmapFile, RiskHeatmapResponse, RiskResponse } from "@/lib/types";

// ── Heatmap helpers ───────────────────────────────────────────────────────────

function ChurnBar({ value }: { value: number }) {
  const pct = Math.min(100, Math.max(0, value * 100));
  const color =
    pct > 80 ? "bg-signal-red" : pct > 50 ? "bg-signal-yellow" : "bg-signal-green";
  return (
    <div className="mt-1 h-1 w-full rounded-full bg-white/[0.08]">
      <div className={`h-1 rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function HeatmapStatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.035] p-4">
      <div className="text-2xl font-bold text-on-surface">{value}</div>
      <div className="mt-1 text-xs text-on-surface-muted">{label}</div>
    </div>
  );
}

function FileCard({ f }: { f: RiskHeatmapFile }) {
  const basename = f.file.split("/").pop() ?? f.file;
  return (
    <div className="relative rounded-lg border border-white/[0.08] bg-white/[0.025] p-3">
      {f.is_hotspot && (
        <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-signal-red" title="Hotspot" />
      )}
      <div className="truncate pr-4 text-xs font-medium text-on-surface" title={f.file}>
        {basename}
      </div>
      <ChurnBar value={f.churn_percentile} />
      <div className="mt-1.5 text-[10px] text-on-surface-muted">
        {f.commit_count_90d} commits (90d)
      </div>
    </div>
  );
}

function ByChurnView({ files }: { files: RiskHeatmapFile[] }) {
  const sorted = [...files]
    .sort((a, b) => b.churn_percentile - a.churn_percentile)
    .slice(0, 100);

  if (sorted.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-on-surface-muted">
        No git history data available. Run{" "}
        <code className="rounded bg-white/[0.06] px-1 font-mono text-xs">provenant init</code> with
        git analysis enabled.
      </p>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      {sorted.map((f) => (
        <FileCard key={f.file} f={f} />
      ))}
    </div>
  );
}

function ByOwnerView({ files }: { files: RiskHeatmapFile[] }) {
  const ownerMap = new Map<string, RiskHeatmapFile[]>();
  for (const f of files) {
    const key = f.primary_owner ?? "Unowned";
    if (!ownerMap.has(key)) ownerMap.set(key, []);
    ownerMap.get(key)!.push(f);
  }

  const entries = Array.from(ownerMap.entries()).sort((a, b) => b[1].length - a[1].length);

  if (entries.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-on-surface-muted">
        No git history data available. Run{" "}
        <code className="rounded bg-white/[0.06] px-1 font-mono text-xs">provenant init</code> with
        git analysis enabled.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {entries.map(([owner, ownerFiles]) => {
        const sorted = [...ownerFiles].sort((a, b) => b.churn_percentile - a.churn_percentile);
        const avgBf =
          ownerFiles.reduce((s, f) => s + f.bus_factor, 0) / ownerFiles.length;
        return (
          <div key={owner}>
            <div className="mb-2 flex items-center gap-3">
              <span className="text-sm font-medium text-on-surface">{owner}</span>
              <span className="text-xs text-on-surface-muted">{ownerFiles.length} files</span>
              <span className="text-xs text-on-surface-muted">
                avg bus factor {avgBf.toFixed(1)}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {sorted.map((f) => (
                <FileCard key={f.file} f={f} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function HeatmapTab() {
  const [data, setData] = useState<RiskHeatmapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"churn" | "owner">("churn");

  useEffect(() => {
    api
      .riskHeatmap()
      .then(setData)
      .catch((err) => setError(getApiError(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner size={8} />
      </div>
    );
  }
  if (error) return <ErrorBanner message={error} />;
  if (!data) return null;

  const { files, stats } = data;

  return (
    <div className="space-y-5">
      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <HeatmapStatCard label="Hotspots" value={stats.hotspot_count} />
        <HeatmapStatCard label="Solo-owned (bus factor ≤ 1)" value={stats.solo_owned_count} />
        <HeatmapStatCard label="Avg bus factor" value={stats.avg_bus_factor.toFixed(1)} />
        <HeatmapStatCard label="Total files" value={stats.total_files} />
      </div>

      {/* View toggle */}
      <div className="flex gap-2">
        {(["churn", "owner"] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={`rounded-full px-4 py-1.5 text-sm transition ${
              view === v
                ? "bg-on-surface text-background"
                : "border border-white/[0.08] text-on-surface-muted hover:text-on-surface"
            }`}
          >
            {v === "churn" ? "By Churn" : "By Owner"}
          </button>
        ))}
      </div>

      {/* View content */}
      {view === "churn" ? <ByChurnView files={files} /> : <ByOwnerView files={files} />}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = "files" | "heatmap";

export default function RiskPage() {
  const overview = useRiskOverview();
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<RiskResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("files");

  const loadDetail = async (path: string) => {
    setSelected(path);
    setDetailLoading(true);
    setError(null);
    try {
      setDetail(await api.risk([path]));
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setDetailLoading(false);
    }
  };

  if (overview.isLoading) {
    return (
      <div className="flex justify-center py-20">
        <LoadingSpinner size={8} />
      </div>
    );
  }

  const files = overview.data?.files || [];

  return (
    <div className="space-y-4">
      {overview.error && <ErrorBanner message={getApiError(overview.error)} />}
      {error && <ErrorBanner message={error} />}

      {/* Tab bar */}
      <div className="flex gap-1 rounded-full border border-white/[0.08] bg-white/[0.035] p-1 w-fit">
        {(["files", "heatmap"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-full px-4 py-1.5 text-sm capitalize transition ${
              tab === t
                ? "bg-on-surface text-background"
                : "text-on-surface-muted hover:text-on-surface"
            }`}
          >
            {t === "files" ? "Files" : "Heatmap"}
          </button>
        ))}
      </div>

      {tab === "files" && (
        <div className="grid grid-cols-[24rem_1fr] gap-6">
          <RiskTable files={files} selected={selected} onSelect={loadDetail} />
          <div className="min-h-96 rounded-lg border border-gray-800 bg-gray-900 p-5">
            {!selected && (
              <div className="flex h-64 flex-col items-center justify-center gap-2 text-gray-600">
                <AlertTriangle className="h-8 w-8 opacity-40" />
                <p className="text-sm">Select a file to inspect risk.</p>
              </div>
            )}
            {selected && detailLoading && (
              <div className="flex justify-center py-20">
                <LoadingSpinner size={6} />
              </div>
            )}
            {selected && !detailLoading && detail && (
              <RiskDetail data={detail} path={selected} />
            )}
          </div>
        </div>
      )}

      {tab === "heatmap" && <HeatmapTab />}
    </div>
  );
}
