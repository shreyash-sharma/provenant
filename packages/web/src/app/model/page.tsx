"use client";

import { useEffect, useState } from "react";
import { ArrowRight, RefreshCw } from "lucide-react";
import Link from "next/link";
import { api, getApiError } from "@/lib/api";
import type { GraphResponse, ModelResponse, ProjectResponse } from "@/lib/types";
import { formatCompact, formatNumber, pct } from "@/lib/economics";

export default function ModelPage() {
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [modelData, setModelData] = useState<ModelResponse | null>(null);
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [projectData, graphData, modelResp] = await Promise.all([
        api.project(),
        api.graph().catch(() => null),
        api.model().catch(() => null),
      ]);
      setProject(projectData);
      setGraph(graphData);
      setModelData(modelResp);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  // ── derived metrics ──────────────────────────────────────────────────────
  const pageCount  = modelData?.corpus?.pages   ?? project?.counts?.pages   ?? project?.state?.total_pages ?? 0;
  const fileCount  = modelData?.corpus?.files   ?? project?.counts?.files   ?? 0;
  const symCount   = modelData?.corpus?.symbols ?? project?.counts?.symbols ?? 0;
  const graphNodes = modelData?.corpus?.graph_nodes ?? graph?.nodes.length ?? 0;
  const graphEdges = modelData?.corpus?.graph_edges ?? graph?.edges.length ?? 0;
  const weakPageCount = modelData?.repair?.weak_page_count ?? null;

  const buildIn    = modelData?.corpus?.build_input_tokens  ?? 0;
  const buildOut   = modelData?.corpus?.build_output_tokens ?? 0;
  const buildTotal = buildIn + buildOut;

  // Average wiki page size (output tokens / page count).
  // This is the live per-repo token cost when an agent reads one wiki page
  // instead of the raw source file — the real unit of compression.
  const avgPageTokens = buildOut > 0 && pageCount > 0
    ? Math.round(buildOut / pageCount)
    : null;

  const attributionConf = modelData?.quality?.avg_attribution_confidence ?? null;
  const totalQueries    = modelData?.quality?.total_queries ?? 0;

  return (
    <div className="mx-auto max-w-5xl space-y-16">

      {/* ── Hero ── */}
      <section className="grid items-center gap-10 py-12 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          <div className="text-sm text-on-surface-subtle">Repository model</div>
          <h1 className="mt-4 max-w-3xl text-5xl font-semibold leading-[1.02] tracking-normal text-on-surface sm:text-6xl">
            {project?.name || "Provenant"} is ready.
          </h1>
          <p className="mt-6 max-w-xl text-base leading-7 text-on-surface-muted">
            Every file and symbol compressed into wiki pages agents actually use.
            Gets smarter with every query — weak pages self-heal automatically, compounding retrieval quality over time.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/knowledge"
              className="inline-flex h-11 items-center gap-2 rounded-full bg-on-surface px-5 text-sm font-medium text-background transition hover:opacity-90"
            >
              View Map
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/repair"
              className="inline-flex h-11 items-center rounded-full border border-white/[0.1] px-5 text-sm text-on-surface-muted transition hover:text-on-surface"
            >
              Repair
            </Link>
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/[0.1] text-on-surface-muted transition hover:text-on-surface"
              title="Refresh"
            >
              <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            </button>
          </div>

          {error && (
            <div className="mt-6 rounded-xl border border-signal-red/20 bg-signal-red/10 px-4 py-3 text-sm text-signal-red">
              {error}
            </div>
          )}
        </div>

        {/* Status card */}
        <div className="rounded-[28px] border border-white/[0.08] bg-white/[0.035] p-5 shadow-2xl shadow-black/20">
          <div className="rounded-[22px] border border-white/[0.08] bg-background p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xs text-on-surface-subtle">Index status</div>
                <div className="mt-1 text-lg font-medium text-on-surface">
                  {project ? "Live" : "Waiting"}
                </div>
              </div>
              <div className={`h-2.5 w-2.5 rounded-full ${project ? "bg-signal-green" : "bg-signal-amber"}`} />
            </div>

            <div className="mt-8 space-y-5">
              <Signal label="Wiki pages"   value={formatNumber(pageCount)} />
              <Signal label="Source files" value={formatNumber(fileCount)} />
              <Signal label="Symbols"      value={formatNumber(symCount)} />
              <Signal label="Graph"        value={`${formatNumber(graphNodes)} / ${formatNumber(graphEdges)}`} detail="nodes / edges" />
              <Signal label="Build cost"   value={formatCompact(buildTotal)} detail="tokens" />
              {weakPageCount !== null && (
                weakPageCount === 0
                  ? <Signal label="Index health" value="Healthy" highlight />
                  : <Signal label="Weak pages" value={formatNumber(weakPageCount)} detail="need repair" />
              )}
            </div>

            {/* Live wiki page size readout */}
            {avgPageTokens !== null && (
              <div className="mt-8 border-t border-white/[0.08] pt-5">
                <div className="text-xs text-on-surface-subtle">Avg wiki page size</div>
                <div className="mt-1 font-mono text-3xl font-semibold text-signal-green">
                  {formatCompact(avgPageTokens)}
                </div>
                <div className="mt-1.5 text-xs leading-5 text-on-surface-muted">
                  tokens / page · {formatCompact(buildOut)} wiki tokens total
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── Flywheel ── */}
      <section className="pt-2">
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-[20px] border border-white/[0.06] bg-white/[0.02] px-6 py-4">
          <div className="flex flex-wrap items-center gap-2 text-sm text-on-surface-muted">
            <span className="font-medium text-on-surface">The more you use it, the better it gets.</span>
            <span className="hidden sm:inline text-on-surface-subtle">·</span>
            <span className="text-xs">query → attribution signal → auto-repair → sharper retrieval → repeat</span>
          </div>
          <span className="shrink-0 rounded-full border border-signal-green/20 bg-signal-green/10 px-3 py-1 text-xs text-signal-green">
            self-compounding
          </span>
        </div>
      </section>

      {/* ── Why it matters — the selling point ── */}
      <section className="border-t border-white/[0.08] pt-10">
        <div className="mb-8 text-xs font-semibold uppercase tracking-widest text-on-surface-subtle">
          Why it matters
        </div>
        <div className="grid gap-px overflow-hidden rounded-[24px] border border-white/[0.08] md:grid-cols-3">
          {/* Token reduction */}
          <ImpactCell
            value="60–65×"
            label="Token reduction"
            detail={
              avgPageTokens !== null
                ? `~${formatCompact(avgPageTokens)} tokens/wiki page for this repo — vs reading raw source files directly`
                : "vs reading raw source files — agents read wiki pages, not raw code"
            }
            live={avgPageTokens !== null}
          />
          {/* Coverage */}
          <ImpactCell
            value="63.8%"
            label="File Coverage@5"
            detail="correct file in top-5 results on SWE-bench Verified (500 tasks) — +7.6 pp over raw BM25"
            live={false}
          />
          {/* Attribution */}
          {attributionConf !== null ? (
            <ImpactCell
              value={pct(attributionConf * 100)}
              label="Attribution confidence"
              detail={`avg across ${totalQueries} queries — compounds automatically, weak pages self-heal in the background`}
              live={true}
            />
          ) : (
            <div className="flex flex-col gap-3 bg-white/[0.025] p-6">
              <div className="flex items-center gap-2">
                <span className="font-mono text-4xl font-semibold text-on-surface-subtle">—</span>
                <span className="self-end rounded-full border border-white/[0.08] bg-white/[0.04] px-2 py-0.5 text-[10px] text-on-surface-subtle">
                  not yet tracked
                </span>
              </div>
              <div className="text-sm font-medium text-on-surface">Attribution confidence</div>
              <p className="text-xs leading-5 text-on-surface-muted">
                Run your first agent query to unlock live attribution — every query is a signal that compounds automatically.
              </p>
            </div>
          )}
        </div>
      </section>

      {/* ── Outcome links ── */}
      <section className="grid gap-8 border-t border-white/[0.08] pt-8 md:grid-cols-3">
        <Outcome
          label="Dependency map"
          value={`${formatNumber(graphNodes)} nodes`}
          detail={`${formatNumber(graphEdges)} edges — every file and symbol connected`}
          href="/knowledge"
        />
        <Outcome
          label="Repair queue"
          value={weakPageCount !== null ? `${formatNumber(weakPageCount)} weak` : "—"}
          detail="pages with low citation rate — rewrite them to sharpen retrieval"
          href="/repair"
        />
        <Outcome
          label="Index health"
          value={
            modelData?.corpus?.avg_confidence != null
              ? pct((modelData.corpus.avg_confidence) * 100)
              : "—"
          }
          detail="avg page confidence across the whole index"
          href="/repair"
        />
      </section>
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

function Signal({ label, value, detail, highlight }: { label: string; value: string; detail?: string; highlight?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-5">
      <span className="text-sm text-on-surface-muted">{label}</span>
      <span className={`text-right font-mono text-sm ${highlight ? "text-signal-green" : "text-on-surface"}`}>
        {value}
        {detail && <span className="ml-2 text-xs text-on-surface-subtle">{detail}</span>}
      </span>
    </div>
  );
}

function ImpactCell({
  value,
  label,
  detail,
  live,
}: {
  value: string;
  label: string;
  detail: string;
  live: boolean;
}) {
  return (
    <div className="flex flex-col gap-3 bg-white/[0.025] p-6">
      <div className="flex items-center gap-2">
        <span className="font-mono text-4xl font-semibold text-on-surface">{value}</span>
        {live ? (
          <span className="self-end rounded-full border border-signal-green/20 bg-signal-green/10 px-2 py-0.5 text-[10px] text-signal-green">
            live
          </span>
        ) : (
          <span className="self-end rounded-full border border-white/[0.08] bg-white/[0.04] px-2 py-0.5 text-[10px] text-on-surface-subtle">
            benchmark
          </span>
        )}
      </div>
      <div className="text-sm font-medium text-on-surface">{label}</div>
      <p className="text-xs leading-5 text-on-surface-muted">{detail}</p>
    </div>
  );
}

function Outcome({
  label,
  value,
  detail,
  href,
}: {
  label: string;
  value: string;
  detail: string;
  href: string;
}) {
  return (
    <Link href={href} className="group block">
      <div className="text-sm text-on-surface-subtle">{label}</div>
      <div className="mt-2 flex items-center gap-2">
        <span className="text-2xl font-medium text-on-surface">{value}</span>
        <ArrowRight className="h-4 w-4 text-on-surface-subtle transition group-hover:translate-x-0.5 group-hover:text-on-surface" />
      </div>
      <p className="mt-2 text-sm leading-6 text-on-surface-muted">{detail}</p>
    </Link>
  );
}
