"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw, Download, AlertCircle, Terminal, TrendingDown } from "lucide-react";
import { PageHeader, MetricCard, Panel, DataTable, StatusBadge } from "@/components/provenant/console";
import { api, getApiError } from "@/lib/api";
import { formatCompact, formatCurrency, formatNumber, pct } from "@/lib/economics";
import type { UsageGroup, UsageResponse, UsageSavings, UsageStatusResponse } from "@/lib/types";

type View = "daily" | "project" | "agent" | "model" | "session";

const views: { key: View; label: string }[] = [
  { key: "daily", label: "Daily" },
  { key: "project", label: "Project" },
  { key: "agent", label: "Agent" },
  { key: "model", label: "Model" },
  { key: "session", label: "Session" },
];

const installCommand = "npm install -g ccusage";
const syncCommand = "provenant usage sync";

export default function UsagePage() {
  const [status, setStatus] = useState<UsageStatusResponse | null>(null);
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [view, setView] = useState<View>("daily");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusData, usageData] = await Promise.all([
        api.usageStatus(),
        api.usage(),
      ]);
      setStatus(statusData);
      setUsage(usageData);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const sync = async () => {
    setSyncing(true);
    setError(null);
    try {
      await api.usageSync({
        include_sessions: true,
        include_blocks: false,
        use_npx: false,
        offline: true,
      });
      await load();
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setSyncing(false);
    }
  };

  const totals = usage?.snapshot?.totals;
  const rows = useMemo(() => usage?.groups?.[view] ?? [], [usage, view]);
  const cost = totals?.total_cost;
  const ccusageMissing = status?.available === false;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Agent Usage"
        title="Token and Cost Telemetry"
        description="Persisted ccusage snapshots for local coding-agent activity across supported agent CLIs."
        actions={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-outline-variant bg-surface-container px-3 text-sm text-on-surface-muted transition hover:text-on-surface"
            >
              <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
              Refresh
            </button>
            <button
              type="button"
              onClick={() => void sync()}
              disabled={syncing || ccusageMissing}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-signal-cyan/30 bg-signal-cyan/10 px-3 text-sm text-signal-cyan transition hover:bg-signal-cyan/15 disabled:opacity-50"
              title={ccusageMissing ? "Install ccusage first" : "Sync local ccusage reports"}
            >
              <Download className={syncing ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
              Sync
            </button>
          </div>
        }
      />

      {error && (
        <Panel>
          <div className="flex items-start gap-3 text-sm text-signal-red">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        </Panel>
      )}

      {ccusageMissing && <MissingCcusagePanel />}
      {!ccusageMissing && <SavingsPanel savings={usage?.savings ?? null} hasSnapshot={Boolean(usage?.snapshot)} />}

      <Panel title="ccusage Status" description="Provenant reads persisted snapshots; Sync imports fresh local ccusage JSON.">
        <DataTable
          columns={["Item", "Value", "State"]}
          rows={[
            [
              <span key="ccusage" className="font-medium text-on-surface">ccusage</span>,
              <span key="path" className="font-mono">{status?.ccusage_path || "not found"}</span>,
              <StatusBadge key="state" tone={status?.available ? "good" : "warn"}>
                {status?.available ? "available" : "missing"}
              </StatusBadge>,
            ],
            [
              <span key="snap" className="font-medium text-on-surface">Snapshot</span>,
              <span key="time" className="font-mono">{usage?.snapshot?.created_at || status?.last_sync_at || "-"}</span>,
              <StatusBadge key="state" tone={usage?.snapshot ? "good" : "neutral"}>
                {usage?.snapshot ? "loaded" : "none"}
              </StatusBadge>,
            ],
          ]}
        />
      </Panel>

      {!ccusageMissing && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <MetricCard label="Total Tokens" value={formatCompact(totals?.total_tokens)} detail={formatNumber(totals?.total_tokens)} tone="info" />
          <MetricCard label="Input" value={formatCompact(totals?.input_tokens)} detail="prompt tokens" />
          <MetricCard label="Output" value={formatCompact(totals?.output_tokens)} detail="completion tokens" />
          <MetricCard label="Cache" value={formatCompact((totals?.cache_creation_tokens ?? 0) + (totals?.cache_read_tokens ?? 0))} detail="create + read" />
          <MetricCard label="Cost" value={cost == null ? "-" : formatCurrency(cost)} detail="ccusage estimate" tone="good" />
        </div>
      )}

      {!ccusageMissing && (
        <Panel
          title="Breakdown"
          description="Grouped from the latest persisted ccusage snapshot."
          action={
            <div className="flex rounded-md border border-outline-variant bg-surface-container p-0.5">
              {views.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setView(item.key)}
                  className={`rounded px-2.5 py-1 text-xs transition ${
                    view === item.key
                      ? "bg-on-surface text-background"
                      : "text-on-surface-muted hover:text-on-surface"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          }
        >
          <UsageTable rows={rows} empty={usage?.snapshot ? "No rows for this breakdown." : `No usage snapshots yet. Install with '${installCommand}', then run '${syncCommand}' or click Sync.`} />
        </Panel>
      )}
    </div>
  );
}

function SavingsPanel({ savings, hasSnapshot }: { savings: UsageSavings | null; hasSnapshot: boolean }) {
  const assistedSessions = savings?.assisted?.sessions ?? 0;
  const unassistedSessions = savings?.unassisted?.sessions ?? 0;
  const eventCount = savings?.event_count ?? 0;

  if (!hasSnapshot) {
    return (
      <Panel>
        <div className="flex items-start gap-3">
          <TrendingDown className="mt-0.5 h-5 w-5 shrink-0 text-signal-cyan" />
          <div>
            <h2 className="text-sm font-medium text-on-surface">No savings estimate yet</h2>
            <p className="mt-1 text-sm leading-6 text-on-surface-muted">
              Use your coding agent with Provenant MCP, then run <code className="rounded border border-outline-variant bg-surface-container px-1.5 py-0.5 font-mono text-on-surface">provenant usage sync</code> to correlate ccusage sessions with Provenant activity.
            </p>
          </div>
        </div>
      </Panel>
    );
  }

  if (!eventCount) {
    return (
      <Panel title="Observed Provenant-Assisted Savings" description="No Provenant MCP events have been recorded yet.">
        <div className="text-sm leading-6 text-on-surface-muted">
          Start the MCP server with <code className="rounded border border-outline-variant bg-surface-container px-1.5 py-0.5 font-mono text-on-surface">provenant mcp .</code>, use the agent against this repo, then sync usage again.
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Observed Provenant-Assisted Savings"
      description={`Automatic estimate: sessions with Provenant tool calls inside the ccusage session window are compared against sessions without them. Window tolerance: ${savings?.tolerance_minutes ?? 5} minutes.`}
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <MetricCard label="Token Reduction" value={pct(savings?.observed_delta?.avg_token_reduction_pct)} detail="avg per session" tone="good" />
        <MetricCard label="Cost Reduction" value={pct(savings?.observed_delta?.avg_cost_reduction_pct)} detail="avg per session" tone="good" />
        <MetricCard label="Assisted" value={formatNumber(assistedSessions)} detail={`${formatCompact(savings?.assisted?.total_tokens)} tokens`} tone="info" />
        <MetricCard label="Unassisted" value={formatNumber(unassistedSessions)} detail={`${formatCompact(savings?.unassisted?.total_tokens)} tokens`} />
        <MetricCard label="Provenant Calls" value={formatNumber(eventCount)} detail={`${formatCompact(savings?.estimated_context_tokens)} context tokens`} />
      </div>
      <div className="mt-4">
        <DataTable
          columns={["Group", "Sessions", "Avg Tokens", "Avg Cost", "Total Tokens", "Total Cost"]}
          rows={[
            [
              <span key="group" className="font-medium text-on-surface">Provenant-assisted</span>,
              <span key="sessions" className="font-mono">{formatNumber(assistedSessions)}</span>,
              <span key="avg-tokens" className="font-mono">{formatCompact(savings?.assisted?.avg_tokens_per_session)}</span>,
              <span key="avg-cost" className="font-mono">{formatCurrency(savings?.assisted?.avg_cost_per_session ?? 0)}</span>,
              <span key="tokens" className="font-mono">{formatCompact(savings?.assisted?.total_tokens)}</span>,
              <span key="cost" className="font-mono text-signal-green">{formatCurrency(savings?.assisted?.total_cost ?? 0)}</span>,
            ],
            [
              <span key="group" className="font-medium text-on-surface">Unassisted</span>,
              <span key="sessions" className="font-mono">{formatNumber(unassistedSessions)}</span>,
              <span key="avg-tokens" className="font-mono">{formatCompact(savings?.unassisted?.avg_tokens_per_session)}</span>,
              <span key="avg-cost" className="font-mono">{formatCurrency(savings?.unassisted?.avg_cost_per_session ?? 0)}</span>,
              <span key="tokens" className="font-mono">{formatCompact(savings?.unassisted?.total_tokens)}</span>,
              <span key="cost" className="font-mono text-signal-green">{formatCurrency(savings?.unassisted?.total_cost ?? 0)}</span>,
            ],
          ]}
        />
      </div>
      {savings?.uncorrelated_sessions ? (
        <p className="mt-3 text-xs text-on-surface-subtle">
          {savings.uncorrelated_sessions} ccusage sessions were excluded because they did not include usable timestamps.
        </p>
      ) : null}
    </Panel>
  );
}

function MissingCcusagePanel() {
  return (
    <Panel>
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="flex min-w-0 gap-3">
          <Terminal className="mt-0.5 h-5 w-5 shrink-0 text-signal-amber" />
          <div className="min-w-0">
            <h2 className="text-sm font-medium text-on-surface">Install ccusage to measure Provenant savings</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-on-surface-muted">
              The Usage tab uses ccusage to import local coding-agent token and cost logs, then Provenant can show whether indexed repo context is reducing agent spend over time.
            </p>
            <div className="mt-3 grid gap-2 text-xs text-on-surface-muted">
              <CommandLine label="Install" command={installCommand} />
              <CommandLine label="Import" command={syncCommand} />
            </div>
          </div>
        </div>
        <StatusBadge tone="warn">ccusage missing</StatusBadge>
      </div>
    </Panel>
  );
}

function CommandLine({ label, command }: { label: string; command: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="w-14 text-on-surface-subtle">{label}</span>
      <code className="rounded border border-outline-variant bg-surface-container px-2 py-1 font-mono text-on-surface">
        {command}
      </code>
    </div>
  );
}

function UsageTable({ rows, empty }: { rows: UsageGroup[]; empty: string }) {
  return (
    <DataTable
      columns={["Group", "Rows", "Input", "Output", "Cache", "Total", "Cost"]}
      empty={empty}
      rows={rows.map((row) => {
        const cacheTokens = (row.cache_creation_tokens || 0) + (row.cache_read_tokens || 0);
        return [
          <span key="key" className="font-medium text-on-surface">{row.key}</span>,
          <span key="rows" className="font-mono">{row.rows}</span>,
          <span key="input" className="font-mono">{formatCompact(row.input_tokens)}</span>,
          <span key="output" className="font-mono">{formatCompact(row.output_tokens)}</span>,
          <span key="cache" className="font-mono">{formatCompact(cacheTokens)}</span>,
          <span key="total" className="font-mono text-on-surface">{formatCompact(row.total_tokens)}</span>,
          <span key="cost" className="font-mono text-signal-green">{formatCurrency(row.total_cost || 0)}</span>,
        ];
      })}
    />
  );
}
