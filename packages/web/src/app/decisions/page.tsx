"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Scale } from "lucide-react";
import { api, getApiError } from "@/lib/api";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import type { DecisionRecord } from "@/lib/types";

const STATUS_FILTERS = ["All", "Proposed", "Active", "Deprecated", "Superseded"];

function statusBadgeClass(status: string): string {
  switch (status.toLowerCase()) {
    case "proposed":
      return "bg-signal-yellow/20 text-signal-yellow";
    case "active":
      return "bg-signal-green/20 text-signal-green";
    case "deprecated":
      return "bg-white/10 text-on-surface-muted";
    case "superseded":
      return "bg-signal-red/20 text-signal-red";
    default:
      return "bg-white/10 text-on-surface-muted";
  }
}

function TagChip({ tag }: { tag: string }) {
  return (
    <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-on-surface-muted">
      {tag}
    </span>
  );
}

function FilePill({ file }: { file: string }) {
  return (
    <span className="rounded border border-white/[0.08] bg-white/[0.035] px-2 py-0.5 font-mono text-[10px] text-on-surface-muted">
      {file}
    </span>
  );
}

function DecisionRow({ record }: { record: DecisionRecord }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <tr
        className="cursor-pointer hover:bg-white/[0.02]"
        onClick={() => setOpen((v) => !v)}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-on-surface">
            {open ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-on-surface-muted" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-on-surface-muted" />
            )}
            {record.title}
          </div>
        </td>
        <td className="px-4 py-3">
          <span
            className={`rounded px-2 py-0.5 text-[11px] font-medium capitalize ${statusBadgeClass(record.status)}`}
          >
            {record.status}
          </span>
        </td>
        <td className="px-4 py-3">
          <div className="flex flex-wrap gap-1">
            {record.tags.slice(0, 4).map((t) => (
              <TagChip key={t} tag={t} />
            ))}
          </div>
        </td>
        <td className="px-4 py-3 text-sm text-on-surface-muted">
          {record.confidence != null ? `${(record.confidence * 100).toFixed(0)}%` : "—"}
        </td>
        <td className="px-4 py-3 text-sm text-on-surface-muted">{record.source || "—"}</td>
        <td className="px-4 py-3 text-sm text-on-surface-muted">
          {record.created_at ? new Date(record.created_at).toLocaleDateString() : "—"}
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={6} className="border-t border-white/[0.04] bg-white/[0.015] px-8 py-5">
            <div className="grid gap-5 text-sm md:grid-cols-2">
              {record.context && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-on-surface-muted">
                    Context
                  </h4>
                  <p className="text-on-surface">{record.context}</p>
                </div>
              )}
              {record.decision && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-on-surface-muted">
                    Decision
                  </h4>
                  <p className="text-on-surface">{record.decision}</p>
                </div>
              )}
              {record.rationale && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-on-surface-muted">
                    Rationale
                  </h4>
                  <p className="text-on-surface">{record.rationale}</p>
                </div>
              )}
              {record.alternatives.length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-on-surface-muted">
                    Alternatives
                  </h4>
                  <ul className="list-disc space-y-1 pl-4 text-on-surface">
                    {record.alternatives.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </div>
              )}
              {record.consequences.length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-on-surface-muted">
                    Consequences
                  </h4>
                  <ul className="list-disc space-y-1 pl-4 text-on-surface">
                    {record.consequences.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
              {record.affected_files.length > 0 && (
                <div className="md:col-span-2">
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-on-surface-muted">
                    Affected Files
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {record.affected_files.map((f) => (
                      <FilePill key={f} file={f} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function DecisionsPage() {
  const [records, setRecords] = useState<DecisionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState("All");

  useEffect(() => {
    setLoading(true);
    api
      .decisions()
      .then((data) => setRecords(data.decisions))
      .catch((err) => setError(getApiError(err)))
      .finally(() => setLoading(false));
  }, []);

  const filtered =
    activeFilter === "All"
      ? records
      : records.filter((r) => r.status.toLowerCase() === activeFilter.toLowerCase());

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <Scale className="h-5 w-5 text-signal-cyan" />
          <h1 className="text-xl font-semibold text-on-surface">Architectural Decisions</h1>
        </div>
        <p className="mt-1 text-sm text-on-surface-muted">
          Why the codebase is built the way it is — constraints, tradeoffs, rejected alternatives.
        </p>
      </div>

      {/* Filter buttons */}
      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setActiveFilter(f)}
            className={`rounded-full px-4 py-1.5 text-sm transition ${
              activeFilter === f
                ? "bg-on-surface text-background"
                : "border border-white/[0.08] text-on-surface-muted hover:text-on-surface"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {error && <ErrorBanner message={error} />}

      {loading && (
        <div className="flex justify-center py-16">
          <LoadingSpinner size={8} />
        </div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.035] p-10 text-center">
          <Scale className="mx-auto mb-3 h-8 w-8 opacity-30 text-on-surface-muted" />
          <p className="text-sm text-on-surface-muted">
            No architectural decisions recorded yet. Use the MCP tool{" "}
            <code className="rounded bg-white/[0.06] px-1 font-mono text-xs">provenant_decisions</code>{" "}
            to record them.
          </p>
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-white/[0.08]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.08] bg-white/[0.02]">
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-on-surface-muted">
                  Title
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-on-surface-muted w-28">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-on-surface-muted">
                  Tags
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-on-surface-muted w-24">
                  Confidence
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-on-surface-muted w-24">
                  Source
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-on-surface-muted w-28">
                  Date
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {filtered.map((rec) => (
                <DecisionRow key={rec.id} record={rec} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
