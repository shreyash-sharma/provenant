"use client";

import { useState } from "react";
import { FileX2, Layers } from "lucide-react";
import { getApiError } from "@/lib/api";
import type { DeadCodeFinding, DeadCodeResponse } from "@/lib/types";
import { useDeadCode } from "@/hooks/useProvenant";
import { RefreshCw } from "lucide-react";

// ── tier config ───────────────────────────────────────────────────────────────

const TIER_CONFIG: Record<string, { label: string; dot: string; text: string; badge: string }> = {
  high:   { label: "High confidence",   dot: "bg-signal-red",   text: "text-signal-red",   badge: "bg-signal-red/10 text-signal-red border-signal-red/20" },
  medium: { label: "Medium confidence", dot: "bg-signal-amber", text: "text-signal-amber", badge: "bg-signal-amber/10 text-signal-amber border-signal-amber/20" },
  low:    { label: "Low confidence",    dot: "bg-on-surface-subtle", text: "text-on-surface-subtle", badge: "bg-white/[0.06] text-on-surface-subtle border-white/[0.06]" },
};

const KIND_LABEL: Record<string, string> = {
  unused_export:   "unused export",
  unreachable_file: "unreachable file",
  dead_symbol:     "dead symbol",
};

// ── page ──────────────────────────────────────────────────────────────────────

export default function DeadCodePage() {
  const [safeOnly, setSafeOnly] = useState(false);
  const query = useDeadCode(safeOnly);
  const data = query.data as DeadCodeResponse | undefined;

  const tiers = (["high", "medium", "low"] as const).map((tier) => ({
    tier,
    meta: data?.tiers?.[tier],
    findings: (data?.tiers?.[tier]?.findings ?? []) as DeadCodeFinding[],
  }));

  const totalFindings = data?.summary?.filtered_findings ??
    tiers.reduce((s, t) => s + t.findings.length, 0);
  const safeLines = data?.impact?.safe_lines_reclaimable ?? 0;
  const safeCount = data?.summary?.safe_to_delete_count ?? 0;

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <section>
        <div className="text-sm text-on-surface-subtle">Analysis</div>
        <div className="mt-1 flex items-end justify-between gap-4">
          <h1 className="text-4xl font-semibold tracking-normal text-on-surface">
            Dead code.
          </h1>
          <button
            type="button"
            onClick={() => void query.refetch()}
            className="mb-1 inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.035] text-on-surface-muted transition hover:text-on-surface"
            title="Refresh"
          >
            <RefreshCw className={query.isLoading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          </button>
        </div>
        <p className="mt-2 max-w-2xl text-sm text-on-surface-muted">
          Symbols and files that appear unreachable from entry points. Review before removing — static analysis may miss dynamic patterns.
        </p>
      </section>

      {/* ── Stats + filter ── */}
      {data && (
        <div className="flex flex-wrap items-center gap-3">
          <StatPill label="Findings" value={String(totalFindings)} />
          <StatPill label="Safe to remove" value={String(safeCount)} />
          {safeLines > 0 && <StatPill label="Reclaimable lines" value={String(safeLines)} />}
          <div className="ml-auto">
            <label className="flex cursor-pointer items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.035] px-3 py-1.5 text-xs text-on-surface-muted transition hover:text-on-surface">
              <input
                type="checkbox"
                checked={safeOnly}
                onChange={(e) => setSafeOnly(e.target.checked)}
                className="h-3.5 w-3.5 accent-white/80"
              />
              Safe to remove only
            </label>
          </div>
        </div>
      )}

      {/* ── Error ── */}
      {query.error && (
        <div className="rounded-xl border border-signal-red/20 bg-signal-red/10 px-4 py-3 text-sm text-signal-red">
          {getApiError(query.error)}
        </div>
      )}
      {data?.limit_note && (
        <div className="rounded-xl border border-signal-amber/20 bg-signal-amber/10 px-4 py-3 text-sm text-signal-amber">
          {data.limit_note}
        </div>
      )}

      {/* ── Loading ── */}
      {query.isLoading && (
        <div className="flex items-center justify-center py-24 text-on-surface-subtle">
          <RefreshCw className="h-5 w-5 animate-spin" />
        </div>
      )}

      {/* ── Empty ── */}
      {!query.isLoading && !query.error && totalFindings === 0 && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-[24px] border border-white/[0.08] bg-white/[0.025] py-24 text-on-surface-subtle">
          <FileX2 className="h-8 w-8 opacity-40" />
          <p className="text-sm">No dead code findings at this confidence level.</p>
        </div>
      )}

      {/* ── Tier sections ── */}
      {!query.isLoading && (
        <div className="space-y-8">
          {tiers.map(({ tier, meta, findings }) => {
            if (!findings.length && !meta?.count) return null;
            const cfg = TIER_CONFIG[tier];
            return (
              <section key={tier}>
                {/* Tier header */}
                <div className="mb-3 flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${cfg.dot}`} />
                  <span className={`text-xs font-semibold uppercase tracking-widest ${cfg.text}`}>
                    {cfg.label}
                  </span>
                  <span className="text-xs text-on-surface-subtle">
                    — {meta?.count ?? findings.length} findings
                    {meta?.lines !== undefined && `, ${meta.lines} lines`}
                    {meta?.safe_count !== undefined && `, ${meta.safe_count} safe`}
                  </span>
                  {meta?.truncated && (
                    <span className="ml-1 rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-on-surface-subtle">
                      truncated
                    </span>
                  )}
                </div>

                {/* Finding cards */}
                <div className="space-y-2">
                  {findings.map((f, i) => (
                    <FindingCard key={`${f.file_path}-${f.name ?? f.symbol_name}-${i}`} finding={f} tierCfg={cfg} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}

      {/* ── Directory rollup ── */}
      {!query.isLoading && data?.by_directory && data.by_directory.length > 0 && (
        <section className="rounded-[24px] border border-white/[0.08] bg-white/[0.025] p-5">
          <div className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-on-surface-subtle">
            <Layers className="h-3.5 w-3.5" />
            By directory
          </div>
          <div className="space-y-2">
            {data.by_directory.slice(0, 10).map((row) => (
              <div key={row.directory} className="flex items-center gap-4 text-sm">
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-on-surface-muted">
                  {row.directory}
                </span>
                <span className="shrink-0 font-mono text-xs text-on-surface-subtle">
                  {row.count} findings
                </span>
                <span className="shrink-0 rounded-full border border-white/[0.06] bg-white/[0.035] px-2 py-0.5 font-mono text-[10px] text-on-surface-subtle">
                  {row.safe_count} safe
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1 text-sm">
      <span className="text-on-surface-subtle">{label}</span>
      <span className="font-mono text-on-surface">{value}</span>
    </div>
  );
}

function FindingCard({
  finding,
  tierCfg,
}: {
  finding: DeadCodeFinding;
  tierCfg: (typeof TIER_CONFIG)[string];
}) {
  const safe = finding.safe_to_remove ?? finding.safe_to_delete ?? false;
  const name = finding.name || finding.symbol_name || finding.file_path;
  const isFile = finding.kind === "unreachable_file";
  const kindLabel = KIND_LABEL[finding.kind] ?? finding.kind.replace(/_/g, " ");
  const shortPath = finding.file_path.split(/[\\/]/).pop() ?? finding.file_path;

  return (
    <div className="group flex items-start gap-4 rounded-[18px] border border-white/[0.06] bg-white/[0.02] px-4 py-3.5 transition hover:bg-white/[0.04]">
      {/* Left — name + path + reason */}
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {/* Name (bold for symbols, monospace for files) */}
          <span className={`truncate font-mono text-sm font-medium text-on-surface ${isFile ? "text-[13px]" : ""}`}>
            {name}
          </span>
          {/* Kind badge */}
          <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${tierCfg.badge}`}>
            {kindLabel}
          </span>
        </div>

        {/* File path — only show if different from name */}
        {!isFile && (
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[11px] text-on-surface-subtle">{shortPath}</span>
            {finding.line !== undefined && (
              <span className="font-mono text-[11px] text-on-surface-subtle opacity-60">:{finding.line}</span>
            )}
          </div>
        )}

        {/* Reason */}
        <p className="text-xs text-on-surface-subtle">{finding.reason}</p>
      </div>

      {/* Right — safe badge */}
      {safe && (
        <span className="mt-0.5 shrink-0 rounded-full border border-signal-green/20 bg-signal-green/10 px-2.5 py-0.5 text-xs text-signal-green">
          Safe
        </span>
      )}
    </div>
  );
}
