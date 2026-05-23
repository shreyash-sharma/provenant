"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import type { GraphResponse } from "@/lib/types";

type GraphNode = GraphResponse["nodes"][number];
type GraphEdge = GraphResponse["edges"][number];

type Pos = { x: number; y: number };
type VisualNode = GraphNode & { degree: number; rank: number };

const W = 1100;
const H = 700;
const CX = W / 2;
const CY = H / 2;
const MAX_NODES = 220;
const MAX_EDGES = 500;

// ── helpers ──────────────────────────────────────────────────────────────────

function stableHash(s: string) {
  let v = 2166136261;
  for (let i = 0; i < s.length; i++) { v ^= s.charCodeAt(i); v = Math.imul(v, 16777619); }
  return Math.abs(v);
}

function shortName(node: GraphNode) {
  const name = node.path || node.name || node.id;
  if (node.type === "SYMBOL") return name;
  return name.split(/[\\/]/).pop() || name;
}

function nodeColor(node: VisualNode) {
  if (node.is_entry_point) return "#e3c16f";
  if (node.type === "SYMBOL") return "#b7a4ff";
  if ((node.pagerank ?? 0) > 0.02 || node.degree > 8) return "#8fd5d2";
  return "#80c66f";
}

function nodeRadius(node: VisualNode) {
  const base = node.type === "SYMBOL" ? 2.6 : 3.8;
  return Math.max(base, Math.min(10, base + Math.sqrt(node.degree + (node.symbol_count ?? 0) / 5)));
}

// ── graph preparation ─────────────────────────────────────────────────────────

function prepareGraph(rawNodes: GraphNode[], rawEdges: GraphEdge[]) {
  const degree = new Map<string, number>();
  for (const e of rawEdges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  const ranked = rawNodes
    .slice()
    .sort((a, b) => {
      const sa = (a.pagerank ?? 0) * 100 + (degree.get(a.id) ?? 0) + (a.is_entry_point ? 20 : 0);
      const sb = (b.pagerank ?? 0) * 100 + (degree.get(b.id) ?? 0) + (b.is_entry_point ? 20 : 0);
      return sb - sa;
    })
    .slice(0, MAX_NODES);

  const ids = new Set(ranked.map(n => n.id));
  const edges = rawEdges.filter(e => ids.has(e.source) && ids.has(e.target)).slice(0, MAX_EDGES);

  const communities = new Map<number, GraphNode[]>();
  for (const n of ranked) {
    const c = typeof n.community_id === "number" ? n.community_id : -1;
    communities.set(c, [...(communities.get(c) ?? []), n]);
  }
  const communityIds = [...communities.keys()].sort((a, b) => a === -1 ? 1 : b === -1 ? -1 : a - b);

  const visualNodes: VisualNode[] = [];
  const initPos = new Map<string, Pos>();

  for (const [ci, cid] of communityIds.entries()) {
    const members = communities.get(cid) ?? [];
    const clusterAngle = (ci / Math.max(communityIds.length, 1)) * Math.PI * 2 - Math.PI / 2;
    const clusterR = communityIds.length > 1 ? 210 : 0;
    const cx = CX + Math.cos(clusterAngle) * clusterR;
    const cy = CY + Math.sin(clusterAngle) * clusterR;
    for (const [i, node] of members.entries()) {
      const h = stableHash(node.id);
      const angle = (i / Math.max(members.length, 1)) * Math.PI * 2 + (h % 90) / 90;
      const r = 28 + Math.sqrt(i + 1) * 20 + (h % 40);
      visualNodes.push({
        ...node,
        degree: degree.get(node.id) ?? 0,
        rank: ranked.indexOf(node),
      });
      initPos.set(node.id, {
        x: Math.max(40, Math.min(W - 40, cx + Math.cos(angle) * r)),
        y: Math.max(40, Math.min(H - 40, cy + Math.sin(angle) * r)),
      });
    }
  }

  return { visualNodes, edges: edges.map((e, i) => ({ ...e, key: `${e.source}-${e.target}-${i}` })), communityIds, initPos };
}

// ── physics tick ──────────────────────────────────────────────────────────────

function tick(
  nodes: VisualNode[],
  edges: Array<GraphEdge & { key: string }>,
  pos: Map<string, Pos>,
  vel: Map<string, Pos>,
  communityIds: number[],
  cooling: number,
) {
  const forces = new Map<string, Pos>(nodes.map(n => [n.id, { x: 0, y: 0 }]));

  // Repulsion
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i]; const ap = pos.get(a.id); if (!ap) continue;
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j]; const bp = pos.get(b.id); if (!bp) continue;
      const dx = bp.x - ap.x; const dy = bp.y - ap.y;
      const dist = Math.max(16, Math.sqrt(dx * dx + dy * dy));
      const f = 700 / (dist * dist);
      const fx = (dx / dist) * f; const fy = (dy / dist) * f;
      forces.get(a.id)!.x -= fx; forces.get(a.id)!.y -= fy;
      forces.get(b.id)!.x += fx; forces.get(b.id)!.y += fy;
    }
  }

  // Spring attraction along edges
  for (const e of edges) {
    const sp = pos.get(e.source); const tp = pos.get(e.target);
    if (!sp || !tp) continue;
    const dx = tp.x - sp.x; const dy = tp.y - sp.y;
    const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
    const rest = e.type?.toLowerCase().includes("symbol") ? 70 : 110;
    const f = (dist - rest) * 0.009;
    const fx = (dx / dist) * f; const fy = (dy / dist) * f;
    forces.get(e.source)!.x += fx; forces.get(e.source)!.y += fy;
    forces.get(e.target)!.x -= fx; forces.get(e.target)!.y -= fy;
  }

  // Cluster anchor pull + integrate
  for (const node of nodes) {
    const p = pos.get(node.id); const f = forces.get(node.id); const v = vel.get(node.id);
    if (!p || !f || !v) continue;
    const c = typeof node.community_id === "number" ? node.community_id : -1;
    const ci = Math.max(0, communityIds.indexOf(c));
    const angle = (ci / Math.max(communityIds.length, 1)) * Math.PI * 2 - Math.PI / 2;
    const aR = communityIds.length > 1 ? 210 : 0;
    f.x += (CX + Math.cos(angle) * aR - p.x) * 0.004;
    f.y += (CY + Math.sin(angle) * aR - p.y) * 0.004;
    v.x = (v.x + f.x * cooling) * 0.74;
    v.y = (v.y + f.y * cooling) * 0.74;
    p.x = Math.max(28, Math.min(W - 28, p.x + v.x));
    p.y = Math.max(28, Math.min(H - 28, p.y + v.y));
  }
}

// ── component ─────────────────────────────────────────────────────────────────

export function KnowledgeGraph({
  nodes: rawNodes,
  edges: rawEdges,
  selectedId,
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId?: string | null;
  onSelect: (node: GraphNode) => void;
}) {
  const { visualNodes, edges, communityIds, initPos } = useMemo(
    () => prepareGraph(rawNodes, rawEdges),
    [rawNodes, rawEdges],
  );

  // Live positions stored as a ref (mutated in-place) + a render-trigger counter
  const posRef = useRef<Map<string, Pos>>(new Map());
  const velRef = useRef<Map<string, Pos>>(new Map());
  const tickRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const [, rerender] = useState(0);

  useEffect(() => {
    // Reset physics when graph changes
    const pos = new Map<string, Pos>();
    const vel = new Map<string, Pos>(visualNodes.map(n => [n.id, { x: 0, y: 0 }]));
    for (const n of visualNodes) {
      const init = initPos.get(n.id) ?? { x: CX, y: CY };
      pos.set(n.id, { ...init });
    }
    posRef.current = pos;
    velRef.current = vel;
    tickRef.current = 0;

    const animate = () => {
      tickRef.current++;
      const cooling = Math.max(0.15, 1 - tickRef.current / 240);
      tick(visualNodes, edges, posRef.current, velRef.current, communityIds, cooling);
      rerender(c => c + 1);
      if (tickRef.current < 300) {
        rafRef.current = requestAnimationFrame(animate);
      }
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [visualNodes, edges, communityIds, initPos]);

  // Zoom + pan
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const dragging = useRef<{ startX: number; startY: number; ox: number; oy: number } | null>(null);

  const zoom = useCallback((factor: number) => {
    setView(v => ({ ...v, scale: Math.max(0.25, Math.min(4, v.scale * factor)) }));
  }, []);

  const resetView = useCallback(() => {
    setView({ x: 0, y: 0, scale: 1 });
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    dragging.current = { startX: e.clientX, startY: e.clientY, ox: view.x, oy: view.y };
  }, [view]);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging.current) return;
    const dx = e.clientX - dragging.current.startX;
    const dy = e.clientY - dragging.current.startY;
    setView(v => ({ ...v, x: dragging.current!.ox + dx, y: dragging.current!.oy + dy }));
  }, []);

  const onMouseUp = useCallback(() => { dragging.current = null; }, []);

  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const activeId = hoveredId || selectedId || null;
  const activeNeighbors = useMemo(() => {
    if (!activeId) return new Set<string>();
    const ids = new Set<string>([activeId]);
    for (const e of edges) {
      if (e.source === activeId) ids.add(e.target);
      if (e.target === activeId) ids.add(e.source);
    }
    return ids;
  }, [activeId, edges]);

  const pos = posRef.current;

  if (rawNodes.length === 0) {
    return (
      <div className="flex min-h-[480px] items-center justify-center rounded-md border border-dashed border-outline-variant text-sm text-on-surface-subtle">
        No graph data.
      </div>
    );
  }

  return (
    <div
      className="relative min-h-[calc(100vh-230px)] cursor-grab overflow-hidden rounded-[22px] bg-[#08090b] active:cursor-grabbing"
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
    >
      <style>{`
        @keyframes pulse-ring {
          0%   { transform: scale(1);   opacity: 0.5; }
          50%  { transform: scale(1.35); opacity: 0.15; }
          100% { transform: scale(1);   opacity: 0.5; }
        }
        .entry-pulse { animation: pulse-ring 2.4s ease-in-out infinite; transform-box: fill-box; transform-origin: center; }
      `}</style>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="absolute inset-0 h-full w-full"
        style={{ userSelect: "none" }}
      >
        <defs>
          <radialGradient id="kg-vignette" cx="50%" cy="45%" r="72%">
            <stop offset="0%" stopColor="#171a20" />
            <stop offset="70%" stopColor="#0b0c0f" />
            <stop offset="100%" stopColor="#07080a" />
          </radialGradient>
        </defs>
        <rect width={W} height={H} fill="url(#kg-vignette)" />

        {/* Everything that should move/scale with pan+zoom lives in this group.
            Zoom formula: translate(CX*(1-s)+px, CY*(1-s)+py) scale(s)
            guarantees that (CX, CY) – the graph centre – stays fixed on screen
            no matter what scale is applied. */}
        <g transform={`translate(${CX * (1 - view.scale) + view.x} ${CY * (1 - view.scale) + view.y}) scale(${view.scale})`}>
        {/* Grid rings — inside the transform so they stay centred on the graph */}
        <g opacity="0.22">
          {Array.from({ length: 11 }).map((_, i) => (
            <circle key={i} cx={CX} cy={CY} r={55 + i * 50} fill="none" stroke="#303139" strokeWidth="1" />
          ))}
        </g>
          {/* Edges — curved quadratic bezier */}
          <g>
            {edges.map((e) => {
              const s = pos.get(e.source); const t = pos.get(e.target);
              if (!s || !t) return null;
              const isActive = activeId ? activeNeighbors.has(e.source) && activeNeighbors.has(e.target) : false;
              // midpoint with slight perpendicular offset for curve
              const mx = (s.x + t.x) / 2 + (t.y - s.y) * 0.08;
              const my = (s.y + t.y) / 2 - (t.x - s.x) * 0.08;
              return (
                <path
                  key={e.key}
                  d={`M ${s.x} ${s.y} Q ${mx} ${my} ${t.x} ${t.y}`}
                  fill="none"
                  stroke={isActive ? "#f2f0e8" : "#4a4d56"}
                  strokeOpacity={activeId ? (isActive ? 0.65 : 0.07) : 0.22}
                  strokeWidth={isActive ? 1.3 : 0.7}
                />
              );
            })}
          </g>

          {/* Nodes */}
          <g>
            {visualNodes.map((node) => {
              const p = pos.get(node.id);
              if (!p) return null;
              const color = nodeColor(node);
              const r = nodeRadius(node);
              const selected = selectedId === node.id;
              const active = activeId ? activeNeighbors.has(node.id) : true;
              const showLabel = selected || hoveredId === node.id || node.is_entry_point || node.rank < 12;

              return (
                <g key={node.id}>
                  {node.is_entry_point && (
                    <circle
                      cx={p.x} cy={p.y} r={r + 9}
                      fill="none"
                      stroke={color}
                      strokeOpacity="0.45"
                      strokeWidth="1.2"
                      className="entry-pulse"
                    />
                  )}
                  {selected && (
                    <circle cx={p.x} cy={p.y} r={r + 11} fill="none" stroke={color} strokeOpacity="0.3" strokeWidth="1" />
                  )}
                  <circle
                    cx={p.x} cy={p.y} r={r}
                    fill={color}
                    fillOpacity={active ? 0.96 : 0.15}
                    stroke={selected ? "#f2f0e8" : "transparent"}
                    strokeWidth="1.5"
                    className="cursor-pointer"
                    onMouseEnter={() => setHoveredId(node.id)}
                    onMouseLeave={() => setHoveredId(null)}
                    onClick={() => onSelect(node)}
                  />
                  {showLabel && (
                    <text
                      x={p.x + r + 7} y={p.y + 4}
                      fill="#c8c3b7"
                      fillOpacity={active ? 0.9 : 0.18}
                      fontSize="10.5"
                      fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
                      pointerEvents="none"
                    >
                      {shortName(node).slice(0, 44)}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </g>
      </svg>

      {/* Node / edge count */}
      <div className="pointer-events-none absolute bottom-3 right-4 text-[11px] text-on-surface-subtle">
        {visualNodes.length} nodes · {edges.length} edges
      </div>

      {/* Zoom controls */}
      <div className="absolute bottom-3 left-3 flex items-center gap-1">
        <button
          type="button"
          onClick={() => zoom(1.25)}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-white/[0.08] bg-black/60 text-sm text-on-surface-muted backdrop-blur transition hover:text-on-surface"
          title="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          onClick={() => zoom(0.8)}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-white/[0.08] bg-black/60 text-sm text-on-surface-muted backdrop-blur transition hover:text-on-surface"
          title="Zoom out"
        >
          −
        </button>
        <button
          type="button"
          onClick={resetView}
          className="inline-flex h-7 items-center justify-center rounded-md border border-white/[0.08] bg-black/60 px-2 text-[11px] text-on-surface-subtle backdrop-blur transition hover:text-on-surface"
          title="Reset view"
        >
          reset
        </button>
      </div>
    </div>
  );
}
