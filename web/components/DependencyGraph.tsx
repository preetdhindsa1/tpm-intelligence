"use client";

// Release dependency graph (engine/graph.py): release -> features -> verified PRs, plus
// "blocks" edges stated in PR text. Red = a feature with a critical rule flag.
import "@xyflow/react/dist/style.css";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { GraphData, GraphNode } from "@/lib/api";
import { filterGraph, layoutGraph, NODE_SIZE, sigsOf, STATUS, topBadge } from "@/lib/dashboard";
import { releasePath } from "@/lib/routes";

type Data = { node: GraphNode };

const SEVERITY_STYLE: Record<string, string> = {
  critical: "border-[#d03b3b] bg-rose-50",
  warning: "border-[#fab219] bg-amber-50",
  info: "border-slate-300 bg-white",
  none: "border-slate-300 bg-white",
};

function FeatureNode({ data }: NodeProps<Node<Data>>) {
  const n = data.node;
  const badge = topBadge(n.flags);
  const style = SEVERITY_STYLE[n.severity ?? "none"];
  return (
    <div
      className={`relative rounded-md border-2 px-2 py-1 text-xs shadow-sm ${style} ${n.in_release ? "" : "opacity-60"}`}
      style={NODE_SIZE.feature}
      title={`${n.label} ${n.title}${n.flags.length ? `\nFlags: ${n.flags.join(", ")}` : ""}`}
    >
      <Handle type="target" position={Position.Left} className="!bg-slate-300" />
      {badge && (
        <span
          className={`absolute -top-2.5 right-1 rounded px-1 text-[10px] font-medium ${
            n.severity === "critical" ? "bg-[#d03b3b] text-white" : "bg-[#fab219] text-slate-900"
          }`}
        >
          ⚠ {badge}
        </span>
      )}
      <div className="font-semibold text-slate-800">
        {n.label}
        {!n.in_release && <span className="ml-1 font-normal text-slate-500">(removed)</span>}
      </div>
      <div className="truncate text-slate-600">{n.title}</div>
      <Handle type="source" position={Position.Right} className="!bg-slate-300" />
    </div>
  );
}

function PRNode({ data }: NodeProps<Node<Data>>) {
  const n = data.node;
  const tone =
    n.state === "merged"
      ? "border-emerald-300 bg-emerald-50 text-emerald-900"
      : n.state === "closed"
        ? "border-slate-200 bg-slate-100 text-slate-500"
        : n.on_critical_path
          ? "border-[#d03b3b] bg-white text-slate-800"
          : "border-slate-300 bg-white text-slate-800";
  return (
    <div className={`rounded-full border px-3 py-1 text-xs ${tone}`} style={NODE_SIZE.pull_request} title={`${n.label} ${n.title} (${n.state})`}>
      <Handle type="target" position={Position.Left} className="!bg-slate-300" />
      <div className="truncate">
        {n.is_main ? "★ " : ""}
        {n.label} · {n.state}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-slate-300" />
    </div>
  );
}

function ReleaseNode({ data }: NodeProps<Node<Data>>) {
  return (
    <div className="flex items-center justify-center rounded-md border-2 border-indigo-300 bg-indigo-50 text-sm font-semibold text-indigo-800" style={NODE_SIZE.release}>
      {data.node.label}
      <Handle type="source" position={Position.Right} className="!bg-indigo-300" />
    </div>
  );
}

const NODE_TYPES = { feature: FeatureNode, pull_request: PRNode, release: ReleaseNode };

export function DependencyGraph({
  project,
  release,
  data,
  preview = false,
}: {
  project: string;
  release: string;
  data: GraphData;
  preview?: boolean;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [sig, setSig] = useState("");
  const [showMerged, setShowMerged] = useState(true);
  const [inReleaseOnly, setInReleaseOnly] = useState(true);
  const [allPrs, setAllPrs] = useState(false);
  const sigs = useMemo(() => sigsOf(data), [data]);

  const { nodes, edges, shownFeatures, totalFeatures } = useMemo(() => {
    const g = filterGraph(data, {
      query,
      sig,
      showMerged,
      inReleaseOnly,
      maxFeatures: preview ? 8 : undefined,
      mainOnly: preview || !allPrs,
    });
    const pos = layoutGraph(g.nodes, g.edges);
    const nodes: Node<Data>[] = g.nodes.map((n) => ({
      id: n.id,
      type: n.kind,
      position: pos[n.id],
      data: { node: n },
      draggable: false,
      connectable: false,
    }));
    const edges: Edge[] = g.edges.map((e) => ({
      id: `${e.source}->${e.target}:${e.kind}`,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      animated: e.kind === "blocks",
      style: { stroke: e.kind === "blocks" ? STATUS.critical : e.kind === "contains" ? "#d6d4cc" : "#a8a7a0", strokeWidth: e.kind === "blocks" ? 2 : 1 },
      markerEnd: { type: MarkerType.ArrowClosed, color: e.kind === "blocks" ? STATUS.critical : "#a8a7a0", width: 14, height: 14 },
    }));
    const all = filterGraph(data, { query, sig, showMerged, inReleaseOnly });
    return {
      nodes,
      edges,
      shownFeatures: g.nodes.filter((n) => n.kind === "feature").length,
      totalFeatures: all.nodes.filter((n) => n.kind === "feature").length,
    };
  }, [data, query, sig, showMerged, inReleaseOnly, allPrs, preview]);

  function open(n: GraphNode) {
    if (n.kind === "feature") router.push(releasePath(project, release, `/features/${n.label.replace("#", "")}`));
    else if (n.kind === "pull_request" && n.url) window.open(n.url, "_blank", "noopener");
  }

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <input
          type="search"
          placeholder="Search features or PRs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="min-w-40 flex-1 rounded-md border px-2 py-1"
          aria-label="Search the graph"
        />
        <select value={sig} onChange={(e) => setSig(e.target.value)} className="rounded-md border px-2 py-1" aria-label="Filter by SIG">
          <option value="">All SIGs</option>
          {sigs.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        {!preview && (
          <>
            <label className="flex items-center gap-1 text-slate-600">
              <input type="checkbox" checked={allPrs} onChange={(e) => setAllPrs(e.target.checked)} /> All linked PRs
            </label>
            <label className="flex items-center gap-1 text-slate-600">
              <input type="checkbox" checked={showMerged} onChange={(e) => setShowMerged(e.target.checked)} /> Merged PRs
            </label>
            <label className="flex items-center gap-1 text-slate-600">
              <input type="checkbox" checked={!inReleaseOnly} onChange={(e) => setInReleaseOnly(!e.target.checked)} /> Removed features
            </label>
          </>
        )}
      </div>
      <div className="min-h-0 flex-1 rounded-md border bg-[#fcfcfb]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          // The preview fits; the full graph is too big to fit readably, so it opens at a
          // readable zoom from the top and is panned.
          fitView={preview}
          fitViewOptions={{ maxZoom: 1, padding: 0.12 }}
          defaultViewport={{ x: 16, y: 16, zoom: 0.8 }}
          minZoom={0.1}
          nodesConnectable={false}
          onNodeClick={(_, n) => open((n.data as Data).node)}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#e1e0d9" gap={20} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
        <span>
          {preview && shownFeatures < totalFeatures
            ? `${shownFeatures} of ${totalFeatures} features, most severe first, main PR only. `
            : `${shownFeatures} features${allPrs ? "" : ", main PR only"}. Drag to pan, scroll to zoom. `}
          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: STATUS.critical }} /> critical flag ·{" "}
          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: STATUS.warning }} /> warning · ★ main PR · red
          edge = stated &quot;depends on&quot;. Verified links only.
        </span>
        {preview && (
          <Link href={releasePath(project, release, "/dependencies")} className="font-medium text-indigo-700 hover:underline">
            Full graph →
          </Link>
        )}
      </div>
    </div>
  );
}
