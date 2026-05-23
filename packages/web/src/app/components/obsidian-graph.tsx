"use client";

import { useEffect, useRef, useState } from "react";
import type { GraphEdge, GraphNode } from "../types/graph";

interface ObsidianGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeSelect?: (node: GraphNode) => void;
  centerNodeId?: string;
}

export function ObsidianGraph({
  nodes,
  edges,
  onNodeSelect,
  centerNodeId,
}: ObsidianGraphProps) {
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map());
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const velocitiesRef = useRef<Map<string, { vx: number; vy: number }>>(new Map());

  useEffect(() => {
    const newPositions = new Map<string, { x: number; y: number }>();
    const newVelocities = new Map<string, { vx: number; vy: number }>();
    const centerX = 600;
    const centerY = 400;

    nodes.forEach((node, index) => {
      const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2;
      const radius = node.id === centerNodeId ? 0 : 300;
      newPositions.set(node.id, {
        x: centerX + Math.cos(angle) * radius + (Math.random() - 0.5) * 60,
        y: centerY + Math.sin(angle) * radius + (Math.random() - 0.5) * 60,
      });
      newVelocities.set(node.id, { vx: 0, vy: 0 });
    });

    setPositions(newPositions);
    velocitiesRef.current = newVelocities;
  }, [nodes, centerNodeId]);

  useEffect(() => {
    if (positions.size === 0) return;

    let animationFrameId: number;
    const simulate = () => {
      setPositions((prevPositions) => {
        const next = new Map(prevPositions);
        const velocities = velocitiesRef.current;
        const forces = new Map<string, { fx: number; fy: number }>();
        nodes.forEach((node) => forces.set(node.id, { fx: 0, fy: 0 }));

        nodes.forEach((nodeA) => {
          const posA = next.get(nodeA.id);
          if (!posA) return;
          nodes.forEach((nodeB) => {
            if (nodeA.id === nodeB.id) return;
            const posB = next.get(nodeB.id);
            if (!posB) return;
            const dx = posB.x - posA.x;
            const dy = posB.y - posA.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const force = 500 / (dist * dist);
            const f = forces.get(nodeA.id)!;
            f.fx -= (dx / dist) * force;
            f.fy -= (dy / dist) * force;
          });
        });

        edges.forEach((edge) => {
          const source = next.get(edge.source);
          const target = next.get(edge.target);
          if (!source || !target) return;
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = dist * 0.04;
          const sf = forces.get(edge.source)!;
          const tf = forces.get(edge.target)!;
          sf.fx += (dx / dist) * force;
          sf.fy += (dy / dist) * force;
          tf.fx -= (dx / dist) * force;
          tf.fy -= (dy / dist) * force;
        });

        nodes.forEach((node) => {
          const pos = next.get(node.id);
          const force = forces.get(node.id);
          const velocity = velocities.get(node.id);
          if (!pos || !force || !velocity) return;
          force.fx += (600 - pos.x) * 0.01;
          force.fy += (400 - pos.y) * 0.01;
          velocity.vx = (velocity.vx + force.fx * 0.016) * 0.94;
          velocity.vy = (velocity.vy + force.fy * 0.016) * 0.94;
          pos.x = Math.max(50, Math.min(1150, pos.x + velocity.vx));
          pos.y = Math.max(50, Math.min(750, pos.y + velocity.vy));
        });

        return next;
      });
      animationFrameId = requestAnimationFrame(simulate);
    };

    animationFrameId = requestAnimationFrame(simulate);
    return () => cancelAnimationFrame(animationFrameId);
  }, [nodes, edges, positions.size]);

  return (
    <div className="h-full w-full overflow-hidden bg-[#0d0d0d]">
      <svg viewBox="0 0 1200 800" className="h-full w-full" style={{ background: "#0d0d0d" }}>
        <g>
          {edges.map((edge, index) => {
            const source = positions.get(edge.source);
            const target = positions.get(edge.target);
            if (!source || !target) return null;
            return (
              <line
                key={`${edge.source}-${edge.target}-${index}`}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke={edge.type === "vulnerability" ? "#ffb4ab" : "#555"}
                strokeWidth={edge.type === "vulnerability" ? 1.5 : 0.5}
                opacity="0.6"
              />
            );
          })}
        </g>
        <g>
          {nodes.map((node) => {
            const pos = positions.get(node.id);
            if (!pos) return null;
            const isCenter = node.id === centerNodeId;
            const isHovered = hoveredNode === node.id;
            const radius = isCenter ? 10 : node.type === "MODULE" ? 7 : 5;
            const fill = node.riskScore && node.riskScore > 0.7
              ? "#ff6b6b"
              : node.type === "SYMBOL"
                ? "#c084fc"
                : node.type === "FILE"
                  ? "#4dabf7"
                  : "#d4af37";

            return (
              <g key={node.id}>
                {isHovered && (
                  <circle cx={pos.x} cy={pos.y} r={radius + 5} fill="none" stroke={fill} opacity="0.4" />
                )}
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r={radius}
                  fill={fill}
                  opacity={isHovered ? 1 : 0.85}
                  className="cursor-pointer transition-opacity"
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  onClick={() => onNodeSelect?.(node)}
                />
                {(isCenter || isHovered || node.type === "MODULE") && (
                  <text
                    x={pos.x}
                    y={pos.y - radius - 10}
                    textAnchor="middle"
                    fontSize="11"
                    fill="#ccc"
                    fontFamily="monospace"
                    pointerEvents="none"
                    fontWeight={isCenter ? "bold" : "normal"}
                  >
                    {node.name}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
