"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import { KnowledgeGraph } from "@/components/provenant/KnowledgeGraph";
import { api, getApiError } from "@/lib/api";
import type { GraphResponse } from "@/lib/types";
import { formatNumber } from "@/lib/economics";

type GraphNode = GraphResponse["nodes"][number];
type ViewMode = "all" | "files" | "entry";

function nodeTitle(node: GraphNode) {
  return node.path || node.name || node.id;
}

function nodeShortName(node: GraphNode) {
  const full = nodeTitle(node);
  return full.split(/[\\/]/).pop() || full;
}

function nodeKind(node: GraphNode) {
  if (node.is_entry_point) return "Entry point";
  return node.type === "FILE" ? "File" : "Symbol";
}

/** Plain-English significance of a node based on its metrics. */
function nodeInsight(node: GraphNode, totalNodes: number, rank: number): string {
  if (node.is_entry_point) {
    return "This is an entry point — where execution or user requests begin.";
  }
  const pr = node.pagerank ?? 0;
  const topPct = totalNodes > 0 ? Math.round((rank / totalNodes) * 100) : 50;
  if (pr > 0.05 || topPct <= 5) {
    return `One of the most referenced files in the codebase — central to the architecture.`;
  }
  if (pr > 0.02 || topPct <= 15) {
    return `A hub file referenced by many others — changes here ripple widely.`;
  }
  if (node.type === "SYMBOL") {
    return "A symbol (function, class, or constant) defined in your codebase.";
  }
  return "A file in the dependency graph.";
}

export default function KnowledgePage() {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("all");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setGraph(await api.graph());
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const files = graph?.nodes.filter((n) => n.type === "FILE") ?? [];
  const symbols = graph?.nodes.filter((n) => n.type === "SYMBOL") ?? [];
  const entryPoints = files.filter((n) => n.is_entry_point);

  // Top hub file by pagerank
  const topHub = useMemo(
    () =>
      files.slice().sort((a, b) => (b.pagerank ?? 0) - (a.pagerank ?? 0))[0] ?? null,
    [files],
  );

  const graphNodes = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (graph?.nodes ?? []).filter((n) => {
      if (viewMode === "files" && n.type !== "FILE") return false;
      if (viewMode === "entry" && !n.is_entry_point) return false;
      if (!q) return true;
      return nodeTitle(n).toLowerCase().includes(q);
    });
  }, [graph, query, viewMode]);

  const visibleIds = useMemo(() => new Set(graphNodes.map((n) => n.id)), [graphNodes]);
  const graphEdges = useMemo(
    () => (graph?.edges ?? []).filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target)),
    [graph, visibleIds],
  );

  // Rank lookup for insight text
  const rankedIds = useMemo(
    () =>
      (graph?.nodes ?? [])
        .slice()
        .sort((a, b) => (b.pagerank ?? 0) - (a.pagerank ?? 0))
        .map((n) => n.id),
    [graph],
  );

  const selectedNode =
    graphNodes.find((n) => n.id === selectedId) ??
    graphNodes.find((n) => n.is_entry_point) ??
    graphNodes.slice().sort((a, b) => (b.pagerank ?? 0) - (a.pagerank ?? 0))[0] ??
    null;

  const neighborsWithEdgeType = useMemo(() => {
    if (!selectedNode || !graph) return [];
    const neighborEdgeType = new Map<string, string>();
    for (const edge of graph.edges) {
      if (edge.source === selectedNode.id) {
        neighborEdgeType.set(edge.target, edge.type);
      } else if (edge.target === selectedNode.id && !neighborEdgeType.has(edge.source)) {
        neighborEdgeType.set(edge.source, edge.type);
      }
    }
    return graph.nodes
      .filter((n) => neighborEdgeType.has(n.id))
      .sort((a, b) => (b.pagerank ?? 0) - (a.pagerank ?? 0))
      .slice(0, 8)
      .map((n) => ({
        node: n,
        edgeType: (neighborEdgeType.get(n.id) ?? "").toLowerCase().replace(/_/g, " "),
      }));
  }, [graph, selectedNode]);

  const selectedRank = selectedNode ? rankedIds.indexOf(selectedNode.id) : -1;

  return (
    <div className="space-y-4">
      {/* ── Header ── */}
      <section>
        <div className="text-sm text-on-surface-subtle">Map</div>
        <h1 className="mt-1 text-4xl font-semibold tracking-normal text-on-surface">
          Repository graph.
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-on-surface-muted">
          Every file and symbol ranked by influence. Larger nodes are more referenced — changes there ripple furthest.
          Amber nodes are entry points.
        </p>
      </section>

      {/* ── Quick stats ── */}
      {graph && (
        <div className="flex flex-wrap gap-3 text-sm text-on-surface-muted">
          <Pill label="Files" value={formatNumber(files.length)} />
          <Pill label="Symbols" value={formatNumber(symbols.length)} />
          <Pill label="Edges" value={formatNumber(graph.edges.length)} />
          <Pill label="Entry points" value={formatNumber(entryPoints.length)} />
          {topHub && (
            <Pill label="Top hub" value={nodeShortName(topHub)} mono />
          )}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-signal-red/20 bg-signal-red/10 px-4 py-3 text-sm text-signal-red">
          {error}
        </div>
      )}

      {/* ── Controls bar — NOT inside the graph, so nothing overlaps ── */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-full border border-white/[0.08] bg-white/[0.035] p-1">
          {(["all", "files", "entry"] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setViewMode(mode)}
              className={`h-8 rounded-full px-3 text-xs capitalize transition ${
                viewMode === mode
                  ? "bg-on-surface text-background"
                  : "text-on-surface-muted hover:text-on-surface"
              }`}
            >
              {mode === "entry" ? "Entry points" : mode.charAt(0).toUpperCase() + mode.slice(1)}
            </button>
          ))}
        </div>
        <label className="relative block w-[220px]">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-on-surface-subtle" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find node…"
            className="h-9 w-full rounded-full border border-white/[0.08] bg-white/[0.035] pl-9 pr-3 text-sm text-on-surface outline-none placeholder:text-on-surface-subtle focus:border-white/20"
          />
        </label>
        <button
          type="button"
          onClick={() => void load()}
          title="Refresh"
          className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.035] text-on-surface-muted transition hover:text-on-surface"
        >
          <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
        </button>
        <span className="ml-auto text-xs text-on-surface-subtle opacity-40">
          drag · scroll to zoom
        </span>
      </div>

      {/* ── Graph + sidebar ── */}
      <div className="flex gap-4">
        {/* Graph */}
        <div className="min-w-0 flex-1 overflow-hidden rounded-[24px] border border-white/[0.08] bg-white/[0.025] shadow-2xl shadow-black/20">
          <KnowledgeGraph
            nodes={graphNodes}
            edges={graphEdges}
            selectedId={selectedNode?.id ?? null}
            onSelect={(node) => setSelectedId(node.id)}
          />
        </div>

        {/* Sidebar */}
        <aside className="w-[280px] shrink-0 rounded-[24px] border border-white/[0.08] bg-white/[0.025] p-5 shadow-2xl shadow-black/20">
          {selectedNode ? (
            <div className="space-y-5">
              {/* Kind + community */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-signal-cyan/10 px-2 py-0.5 text-xs text-signal-cyan">
                  {nodeKind(selectedNode)}
                </span>
                {typeof selectedNode.community_id === "number" && (
                  <span className="rounded-full bg-white/[0.07] px-2 py-0.5 text-xs text-on-surface-muted">
                    cluster {selectedNode.community_id}
                  </span>
                )}
              </div>

              {/* Filename */}
              <div>
                <div className="break-all font-mono text-sm leading-6 text-on-surface">
                  {nodeShortName(selectedNode)}
                </div>
                {selectedNode.path && selectedNode.path !== nodeShortName(selectedNode) && (
                  <div className="mt-0.5 break-all font-mono text-[11px] text-on-surface-subtle">
                    {selectedNode.path}
                  </div>
                )}
              </div>

              {/* Plain-English insight */}
              <p className="text-xs leading-5 text-on-surface-muted">
                {nodeInsight(selectedNode, rankedIds.length, selectedRank)}
              </p>

              {/* Metrics */}
              <div className="grid grid-cols-3 gap-3 rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
                <Micro
                  label="Influence"
                  value={selectedRank >= 0 ? `#${selectedRank + 1}` : "—"}
                  hint="rank by pagerank"
                />
                <Micro
                  label="Symbols"
                  value={formatNumber(selectedNode.symbol_count)}
                  hint="defined here"
                />
                <Micro
                  label="Links"
                  value={formatNumber(neighborsWithEdgeType.length)}
                  hint="connections"
                />
              </div>

              {/* Neighbors */}
              {neighborsWithEdgeType.length > 0 && (
                <div>
                  <div className="mb-2 text-[10px] uppercase tracking-widest text-on-surface-subtle">
                    Connected to
                  </div>
                  <div className="space-y-1">
                    {neighborsWithEdgeType.map(({ node, edgeType }) => (
                      <button
                        key={node.id}
                        type="button"
                        onClick={() => setSelectedId(node.id)}
                        className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-white/[0.05]"
                      >
                        <span className="flex-1 truncate font-mono text-xs text-on-surface-muted hover:text-on-surface">
                          {nodeShortName(node)}
                        </span>
                        {edgeType && (
                          <span className="shrink-0 rounded bg-white/[0.07] px-1.5 py-0.5 text-[10px] text-on-surface-subtle">
                            {edgeType}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-sm font-medium text-on-surface">Click any node to inspect it.</p>
              <div className="space-y-3 text-xs text-on-surface-muted">
                <LegendItem color="#e3c16f" label="Entry points" desc="Where execution or requests begin" />
                <LegendItem color="#8fd5d2" label="Hub files" desc="Heavily referenced, high-impact files" />
                <LegendItem color="#80c66f" label="Files" desc="Source files in the repository" />
                <LegendItem color="#b7a4ff" label="Symbols" desc="Functions, classes, constants" />
              </div>
              <p className="text-[11px] text-on-surface-subtle">
                Node size reflects how many files depend on it. Clusters are modules that import each other.
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function Pill({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1">
      <span className="text-on-surface-subtle">{label}</span>
      <span className={`text-on-surface ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

function Micro({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div title={hint}>
      <div className="text-[10px] uppercase tracking-[0.1em] text-on-surface-subtle">{label}</div>
      <div className="mt-1 truncate font-mono text-sm text-on-surface">{value}</div>
    </div>
  );
}

function LegendItem({ color, label, desc }: { color: string; label: string; desc: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <span
        className="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      <div>
        <div className="font-medium text-on-surface-muted">{label}</div>
        <div className="text-on-surface-subtle">{desc}</div>
      </div>
    </div>
  );
}
