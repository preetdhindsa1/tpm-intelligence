"use client";

import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { FeatureRow } from "@/lib/api";

type FeatureNodeData = {
  number: number;
  title: string;
  badge: string | null;
  tone: "critical" | "warning" | "ok";
};

function FeatureNode({ data }: NodeProps & { data: FeatureNodeData }) {
  const border =
    data.tone === "critical"
      ? "border-[var(--tpm-risk)] bg-[#fff5f4]"
      : data.tone === "warning"
        ? "border-[var(--tpm-warn)] bg-[#fff8f1]"
        : "border-[#b7d4c8] bg-[#eef6f3]";
  return (
    <div className={`min-w-[5.5rem] max-w-[9.5rem] rounded-full border-2 px-3 py-2 text-center ${border}`}>
      <Handle type="target" position={Position.Top} className="!bg-[#9aa7b5]" />
      <div className="text-[11px] font-semibold">#{data.number}</div>
      <div className="truncate text-[10px] text-[var(--tpm-muted)]">{data.title}</div>
      {data.badge ? (
        <div className="mt-1 text-[9px] font-medium text-[var(--tpm-risk)]">{data.badge}</div>
      ) : null}
      <Handle type="source" position={Position.Bottom} className="!bg-[#9aa7b5]" />
    </div>
  );
}

const nodeTypes = { feature: FeatureNode };

function riskRank(f: FeatureRow): number {
  if (f.flags.some((x) => x.severity === "critical")) return 0;
  if (f.flags.some((x) => x.severity === "warning")) return 1;
  if (f.odds.status === "forecast" && f.odds.probability !== null && f.odds.probability < 0.4) return 2;
  return 3;
}

function layout(features: FeatureRow[]): { nodes: Node[]; edges: Edge[] } {
  const ranked = [...features].sort((a, b) => riskRank(a) - riskRank(b) || a.number - b.number);
  const shown = ranked.slice(0, 36);
  const byTeam = new Map<string, FeatureRow[]>();
  for (const f of shown) {
    const team = f.teams[0] ?? "untagged";
    const list = byTeam.get(team) ?? [];
    list.push(f);
    byTeam.set(team, list);
  }

  const nodes: Node[] = [];
  const edges: Edge[] = [];
  let col = 0;
  for (const [, members] of byTeam) {
    members.forEach((f, row) => {
      const critical = f.flags.some((x) => x.severity === "critical");
      const warning = f.flags.some((x) => x.severity === "warning");
      nodes.push({
        id: f.key,
        type: "feature",
        position: { x: 40 + col * 220, y: 40 + row * 100 },
        data: {
          number: f.number,
          title: f.title,
          badge: critical ? "Blocker" : warning ? "Delay risk" : null,
          tone: critical ? "critical" : warning ? "warning" : "ok",
        } satisfies FeatureNodeData,
      });
    });
    for (let i = 0; i < members.length - 1; i++) {
      const a = members[i];
      const b = members[i + 1];
      const hot =
        a.flags.some((x) => x.severity === "critical") || b.flags.some((x) => x.severity === "critical");
      edges.push({
        id: `${a.key}->${b.key}`,
        source: a.key,
        target: b.key,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
        style: { stroke: hot ? "var(--tpm-risk)" : "#9aa7b5", strokeWidth: hot ? 2 : 1 },
        animated: hot,
      });
    }
    col += 1;
  }
  return { nodes, edges };
}

export function DependencyGraph({
  features,
  releaseLabel,
}: {
  features: FeatureRow[];
  releaseLabel: string;
}) {
  const { nodes, edges } = useMemo(() => layout(features.filter((f) => f.in_release)), [features]);

  return (
    <section id="dependencies" className="tpm-card flex h-full min-h-[28rem] flex-col overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--tpm-line)] px-4 py-3">
        <div>
          <h2 className="tpm-panel-title">{releaseLabel} dependency graph</h2>
          <p className="text-[11px] text-[var(--tpm-muted)]">
            Features by SIG lane · red edges mark critical-flagged paths · not a full PR dependency graph
          </p>
        </div>
        <span className="rounded-full bg-[var(--tpm-sidebar)] px-2 py-0.5 text-[10px] text-[var(--tpm-muted)]">
          {nodes.length} nodes
        </span>
      </header>
      <div className="relative min-h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.3}
          proOptions={{ hideAttribution: true }}
          nodesDraggable
          nodesConnectable={false}
        >
          <Background gap={18} size={1} color="#e4e9ef" />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeColor="#c5ddd4" maskColor="rgb(244 246 248 / 70%)" />
        </ReactFlow>
      </div>
    </section>
  );
}
