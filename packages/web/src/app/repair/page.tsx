"use client";

import { useEffect, useState } from "react";
import { RefreshCw, Wrench, CheckCircle2 } from "lucide-react";
import { pct, formatCompact } from "@/lib/economics";
import { api, getApiError } from "@/lib/api";
import type { RepairCandidatesResponse, RepairRunResponse } from "@/lib/types";

export default function RepairPage() {
  const [candidates, setCandidates] = useState<RepairCandidatesResponse | null>(null);
  const [runResult, setRunResult] = useState<RepairRunResponse | null>(null);
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const loadCandidates = async () => {
    setLoadingCandidates(true);
    setError(null);
    try {
      setCandidates(await api.repairCandidates());
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoadingCandidates(false);
    }
  };

  useEffect(() => { void loadCandidates(); }, []);

  const handleRunRepair = async () => {
    setRunning(true);
    setRunError(null);
    setRunResult(null);
    try {
      const result = await api.repairRun({ dry_run: false, top_n: 10 });
      setRunResult(result);
      void loadCandidates();
    } catch (err) {
      setRunError(getApiError(err));
    } finally {
      setRunning(false);
    }
  };

  const totalWeak      = candidates?.summary.total_weak_pages ?? 0;
  const avgCitationRate = candidates?.summary.avg_citation_rate ?? null;
  const totalAffected  = candidates?.summary.total_affected_queries ?? 0;
  const isHealthy      = !loadingCandidates && !error && totalWeak === 0;

  return (
    <div className="space-y-6">

      {/* ── Header ── */}
      <section>
        <div className="text-sm text-on-surface-subtle">Repair</div>
        <div className="mt-1 flex items-end justify-between gap-4">
          <h1 className="text-4xl font-semibold tracking-normal text-on-surface">
            Index health.
          </h1>
          <div className="mb-1 flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadCandidates()}
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.035] text-on-surface-muted transition hover:text-on-surface"
              title="Refresh"
            >
              <RefreshCw className={loadingCandidates ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            </button>
            {totalWeak > 0 && (
              <button
                type="button"
                onClick={() => void handleRunRepair()}
                disabled={running || loadingCandidates}
                className="inline-flex h-8 items-center gap-2 rounded-full bg-on-surface px-4 text-sm font-medium text-background transition hover:opacity-90 disabled:opacity-40"
              >
                <Wrench className="h-3.5 w-3.5" />
                {running ? "Repairing…" : "Run Repair"}
              </button>
            )}
          </div>
        </div>
        <p className="mt-2 max-w-2xl text-sm text-on-surface-muted">
          Pages with low citation rates are identified automatically and rewritten to sharpen retrieval.
          Every repair compounds index quality over time.
        </p>
      </section>

      {/* ── Errors ── */}
      {error && (
        <div className="rounded-xl border border-signal-red/20 bg-signal-red/10 px-4 py-3 text-sm text-signal-red">
          {error}
        </div>
      )}
      {runError && (
        <div className="rounded-xl border border-signal-red/20 bg-signal-red/10 px-4 py-3 text-sm text-signal-red">
          {runError}
        </div>
      )}

      {/* ── Loading ── */}
      {loadingCandidates && (
        <div className="flex items-center justify-center py-24 text-on-surface-subtle">
          <RefreshCw className="h-5 w-5 animate-spin" />
        </div>
      )}

      {/* ── Healthy state ── */}
      {isHealthy && (
        <div className="flex flex-col items-center justify-center gap-4 rounded-[28px] border border-signal-green/20 bg-signal-green/5 py-20">
          <CheckCircle2 className="h-10 w-10 text-signal-green opacity-80" />
          <div className="text-center">
            <div className="text-xl font-semibold text-on-surface">Fully optimized.</div>
            <p className="mt-1.5 text-sm text-on-surface-muted">
              No weak pages detected — index is healthy.
              {totalAffected > 0 && ` ${totalAffected} queries tracked.`}
            </p>
          </div>
          {avgCitationRate !== null && (
            <div className="flex items-center gap-2 rounded-full border border-signal-green/20 bg-signal-green/10 px-4 py-1.5 text-sm text-signal-green">
              {pct(avgCitationRate * 100)} avg citation rate
            </div>
          )}
        </div>
      )}

      {/* ── Stats + queue ── */}
      {!loadingCandidates && totalWeak > 0 && (
        <>
          {/* Stats row */}
          <div className="flex flex-wrap items-center gap-3">
            <StatPill label="Weak pages"       value={String(totalWeak)}       tone="bad" />
            <StatPill label="Affected queries" value={String(totalAffected)}   tone="warn" />
            {avgCitationRate !== null && (
              <StatPill label="Avg citation rate" value={pct(avgCitationRate * 100)} />
            )}
          </div>

          {/* Candidate cards */}
          <div className="space-y-2">
            {(candidates?.candidates ?? []).map((c) => (
              <CandidateCard key={c.page_id} candidate={c} />
            ))}
          </div>
        </>
      )}

      {/* ── Repair run result ── */}
      {runResult && (
        <div className="rounded-[24px] border border-white/[0.08] bg-white/[0.025] p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium text-on-surface">Last repair run</div>
            <div className="flex items-center gap-2 text-xs text-on-surface-subtle">
              <span className="text-signal-green font-mono">{runResult.repaired} repaired</span>
              {runResult.skipped > 0 && <span>· {runResult.skipped} skipped</span>}
              <span>· {formatCompact(runResult.total_output_tokens)} tokens</span>
            </div>
          </div>
          <div className="space-y-2">
            {runResult.pages.map((p) => (
              <div
                key={p.page_id}
                className="flex items-center gap-4 rounded-[14px] border border-white/[0.06] bg-white/[0.02] px-4 py-2.5"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-on-surface">{p.title}</div>
                  <div className="truncate font-mono text-[11px] text-on-surface-subtle">{p.path}</div>
                </div>
                <span
                  className={`shrink-0 rounded-full border px-2.5 py-0.5 text-xs ${
                    p.status === "repaired"
                      ? "border-signal-green/20 bg-signal-green/10 text-signal-green"
                      : p.error
                      ? "border-signal-red/20 bg-signal-red/10 text-signal-red"
                      : "border-white/[0.08] bg-white/[0.04] text-on-surface-subtle"
                  }`}
                >
                  {p.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

function StatPill({ label, value, tone }: { label: string; value: string; tone?: "bad" | "warn" }) {
  const color =
    tone === "bad"  ? "text-signal-red" :
    tone === "warn" ? "text-signal-amber" :
    "text-on-surface";
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1 text-sm">
      <span className="text-on-surface-subtle">{label}</span>
      <span className={`font-mono ${color}`}>{value}</span>
    </div>
  );
}

function CandidateCard({ candidate }: { candidate: RepairCandidatesResponse["candidates"][number] }) {
  const rate = candidate.citation_rate;
  const rateColor =
    rate < 0.1  ? "text-signal-red" :
    rate < 0.2  ? "text-signal-amber" :
    "text-on-surface-subtle";

  return (
    <div className="flex items-start gap-4 rounded-[18px] border border-white/[0.06] bg-white/[0.02] px-4 py-3.5 transition hover:bg-white/[0.04]">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-mono text-sm font-medium text-on-surface">
            {candidate.title}
          </span>
          <span className="shrink-0 rounded-full border border-signal-amber/20 bg-signal-amber/10 px-2 py-0.5 text-[10px] text-signal-amber">
            weak
          </span>
        </div>
        <div className="font-mono text-[11px] text-on-surface-subtle">{candidate.path}</div>
      </div>
      <div className="shrink-0 text-right">
        <div className={`font-mono text-sm font-medium ${rateColor}`}>
          {pct(rate * 100)}
        </div>
        <div className="text-[11px] text-on-surface-subtle">
          {candidate.cited_count}/{candidate.retrieval_count} cited
        </div>
      </div>
    </div>
  );
}
