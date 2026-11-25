"use client";

import { featureLabel } from "@/lib/vocab";
// Feature dependency map (ADR-0013 addendum): only features, only those tied to another
// feature, one group at a time. Grey line = the features share verified PRs (shared code, not proof of a
// block); red arrow A -> B = a PR of B says it depends on a PR of A. Click a feature to
// focus it and see why it is tied to the others.
import "@xyflow/react/dist/style.css";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  getStraightPath,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  useInternalNode,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { DepFeature, Dependencies } from "@/lib/api";
import { OUTCOME_META, STATUS, topBadge } from "@/lib/dashboard";
import { clusterName, focusSet, MAP_NODE, packClusters, partnersOf, prChainsOf, PR_NUM, shortSig } from "@/lib/dependencies";
import { releasePath } from "@/lib/routes";

type FeatureData = { f: DepFeature; dim: boolean; selected: boolean };
type GroupData = { title: string; count: number };

const CENTER = { left: "50%", top: "50%", opacity: 0, pointerEvents: "none" as const };

function FeatureNode({ data }: NodeProps<Node<FeatureData>>) {
  const { f, dim, selected } = data;
  const badge = topBadge(f.flags);
  const border = f.severity === "critical" ? STATUS.critical : f.severity === "warning" ? STATUS.warning : "#c3c2b7";
  return (
    <div
      className={`cursor-pointer rounded-md border-2 bg-white px-2 py-1 text-[13px] leading-tight shadow-sm transition-opacity ${dim ? "opacity-25" : ""} ${
        selected ? "ring-2 ring-indigo-400 ring-offset-1" : ""
      } ${f.in_release ? "" : "border-dashed"}`}
      style={{ ...MAP_NODE, borderColor: border }}
      title={`#${f.number} ${f.title}\n${OUTCOME_META[f.outcome].label}${f.flags.length ? `\nFlags: ${f.flags.join(", ")}` : ""}`}
    >
      <Handle type="target" position={Position.Left} style={CENTER} />
      <div className="flex items-center justify-between gap-1">
        <span className="font-semibold text-slate-800">{featureLabel(f)}</span>
        {badge && (
          <span
            className={`truncate rounded px-1 text-[10px] font-medium ${
              f.severity === "critical" ? "bg-[#d03b3b] text-white" : "bg-[#fab219] text-slate-900"
            }`}
          >
            {badge}
          </span>
        )}
      </div>
      <div className="truncate text-slate-700">{f.title}</div>
      <div className="mt-0.5 truncate text-[11px] text-slate-500">{f.sigs.map(shortSig).join(" · ") || "no team label"}</div>
      <Handle type="source" position={Position.Right} style={CENTER} />
    </div>
  );
}

function GroupNode({ data }: NodeProps<Node<GroupData>>) {
  return (
    <div className="h-full w-full rounded-xl border border-slate-200 bg-slate-50/70">
      <p className="px-3 pt-2 text-sm font-medium text-slate-500">
        {data.title} · {data.count} features
      </p>
    </div>
  );
}

const NODE_TYPES = { feature: FeatureNode, group: GroupNode };

type EdgeData = { color: string };

/** Where the line from a node's centre towards (tx, ty) leaves the node's box. */
function borderPoint(cx: number, cy: number, w: number, h: number, tx: number, ty: number) {
  const dx = tx - cx;
  const dy = ty - cy;
  if (!dx && !dy) return { x: cx, y: cy };
  const s = Math.min(dx ? Math.abs(w / 2 / dx) : Infinity, dy ? Math.abs(h / 2 / dy) : Infinity);
  return { x: cx + dx * s, y: cy + dy * s };
}

/** A straight edge between node borders, so arrowheads are not hidden under the boxes. */
function BorderEdge({ id, source, target, markerEnd, style, label, data }: EdgeProps<Edge<EdgeData>>) {
  const s = useInternalNode(source);
  const t = useInternalNode(target);
  if (!s || !t) return null;
  const box = (n: NonNullable<typeof s>) => {
    const w = n.measured.width ?? MAP_NODE.width;
    const h = n.measured.height ?? MAP_NODE.height;
    return { w, h, cx: n.internals.positionAbsolute.x + w / 2, cy: n.internals.positionAbsolute.y + h / 2 };
  };
  const a = box(s);
  const b = box(t);
  const p = borderPoint(a.cx, a.cy, a.w, a.h, b.cx, b.cy);
  const q = borderPoint(b.cx, b.cy, b.w + 6, b.h + 6, a.cx, a.cy);
  const [path, lx, ly] = getStraightPath({ sourceX: p.x, sourceY: p.y, targetX: q.x, targetY: q.y });
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />
      {label && (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-none absolute rounded bg-[#fcfcfb] px-1 text-[11px] font-medium"
            style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly}px)`, color: data?.color, opacity: style?.opacity }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const EDGE_TYPES = { border: BorderEdge };

export function DependencyMap({
  project,
  release,
  data,
  initialSelected = null,
}: {
  project: string;
  release: string;
  data: Dependencies;
  initialSelected?: string | null;
}) {
  const byKey = useMemo(() => new Map(data.features.map((f) => [f.key, f])), [data]);
  const [selected, setSelected] = useState<string | null>(initialSelected);
  // One group at a time so the text stays readable; the largest group opens first.
  const [group, setGroup] = useState<number | "all">(
    initialSelected ? (byKey.get(initialSelected)?.cluster ?? 0) : 0,
  );
  const placed = useMemo(
    () => packClusters(data, group === "all" ? undefined : [group]),
    [data, group],
  );
  const groups = useMemo(
    () => data.clusters.map((m) => clusterName(m.map((k) => byKey.get(k)!).filter(Boolean))),
    [data, byKey],
  );

  const { nodes, edges } = useMemo(() => {
    const focus = focusSet(selected, data.couplings);
    const shown = new Set<string>();
    const nodes: Node[] = [];
    for (const c of placed) {
      const members = data.clusters[c.index];
      nodes.push({
        id: `cluster-${c.index}`,
        type: "group",
        position: { x: c.x, y: c.y },
        data: { title: groups[c.index], count: members.length },
        style: { width: c.width, height: c.height },
        selectable: false,
        draggable: false,
        zIndex: -1,
      });
      for (const [k, p] of Object.entries(c.positions)) {
        const f = byKey.get(k);
        if (!f) continue;
        shown.add(k);
        nodes.push({
          id: k,
          type: "feature",
          position: p,
          data: { f, dim: !!focus && !focus.has(k), selected: k === selected },
          draggable: false,
          connectable: false,
        });
      }
    }
    const edges: Edge<EdgeData>[] = data.couplings
      .filter((c) => shown.has(c.a) && shown.has(c.b))
      .map((c) => {
        const stated = c.stated.length > 0;
        const touches = !!selected && (c.a === selected || c.b === selected);
        const dim = !!selected && !touches;
        // Arrow from the feature that must merge first to the one that depends on it.
        const [source, target] = stated ? [c.stated[0].upstream, c.stated[0].downstream] : [c.a, c.b];
        const n = c.shared_prs.length;
        const label = stated
          ? `blocks${n ? ` · ${n} shared` : ""}`
          : touches || (!selected && n >= 5)
            ? `${n} shared PR${n === 1 ? "" : "s"}`
            : undefined;
        return {
          id: `${c.a}--${c.b}`,
          source,
          target,
          type: "border",
          label,
          data: { color: stated ? STATUS.critical : "#475569" },
          style: {
            stroke: stated ? STATUS.critical : "#a8a7a0",
            strokeWidth: stated ? 2.5 : 1 + Math.min(n, 8) * 0.4,
            opacity: dim ? 0.1 : 0.9,
          },
          zIndex: touches || stated ? 1 : 0,
          markerEnd: stated ? { type: MarkerType.ArrowClosed, color: STATUS.critical, width: 18, height: 18 } : undefined,
        };
      });
    return { nodes, edges };
  }, [placed, data, byKey, selected, groups]);

  const sel = selected ? byKey.get(selected) : undefined;
  function switchGroup(g: number | "all") {
    setGroup(g);
    if (g !== "all" && sel && sel.cluster !== g) setSelected(null);
  }
  // Picking a partner in the side panel stays inside its group (partners share a group).
  const chip = (active: boolean) =>
    `rounded-full border px-3 py-1 text-xs ${active ? "border-indigo-300 bg-indigo-50 font-medium text-indigo-800" : "bg-white text-slate-600 hover:bg-slate-50"}`;

  return (
    <div className="grid h-full gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex min-h-0 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Group of features">
          {groups.map((name, i) => (
            <button key={i} type="button" className={chip(group === i)} onClick={() => switchGroup(i)} aria-pressed={group === i}>
              {name} · {data.clusters[i].length}
            </button>
          ))}
          {groups.length > 1 && (
            <button type="button" className={chip(group === "all")} onClick={() => switchGroup("all")} aria-pressed={group === "all"}>
              All groups
            </button>
          )}
        </div>
        <div className="min-h-0 flex-1 rounded-md border bg-[#fcfcfb]">
          {groups.length ? (
            <ReactFlow
              key={String(group)}
              nodes={nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              edgeTypes={EDGE_TYPES}
              fitView
              fitViewOptions={{ padding: 0.08, maxZoom: 1 }}
              minZoom={0.15}
              nodesConnectable={false}
              elementsSelectable={false}
              onNodeClick={(_, n) => {
                if (n.type === "feature") setSelected((cur) => (cur === n.id ? null : n.id));
              }}
              onPaneClick={() => setSelected(null)}
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#e1e0d9" gap={20} />
              <Controls showInteractive={false} />
            </ReactFlow>
          ) : (
            <p className="p-4 text-sm text-slate-500">No feature is tied to another feature.</p>
          )}
        </div>
        <Legend />
      </div>
      <aside className="min-h-0 overflow-y-auto rounded-md border bg-white p-3 text-sm">
        {sel ? (
          <FeatureDetail
            f={sel}
            data={data}
            byKey={byKey}
            project={project}
            release={release}
            onSelect={setSelected}
          />
        ) : (
          <div className="space-y-2 text-slate-600">
            <p className="font-medium text-slate-800">Click a feature</p>
            <p>
              See which features it shares code with, which of its PRs wait on another PR, and what has not merged yet. The
              features it is tied to stay highlighted.
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}

function Legend() {
  return (
    <p className="text-xs text-slate-500">
      <span className="mr-1 inline-block h-0.5 w-5 align-middle" style={{ background: "#a8a7a0" }} /> shares verified PRs (shared
      code, thicker = more) ·{" "}
      <span className="mr-1 inline-block h-0.5 w-5 align-middle" style={{ background: STATUS.critical }} />
      A → B: a PR of B says it depends on a PR of A · border: <span style={{ color: STATUS.critical }}>critical</span> /{" "}
      <span style={{ color: "#b88a0e" }}>warning</span> flag · dashed = removed from the release
    </p>
  );
}

const STATE_CHIP: Record<string, string> = {
  open: "bg-sky-50 text-sky-800",
  merged: "bg-emerald-50 text-emerald-800",
  closed: "bg-slate-100 text-slate-600",
};

function State({ s }: { s: string }) {
  return <span className={`rounded px-1 text-[10px] ${STATE_CHIP[s] ?? "bg-slate-100 text-slate-600"}`}>{s}</span>;
}

function FeatureDetail({
  f,
  data,
  byKey,
  project,
  release,
  onSelect,
}: {
  f: DepFeature;
  data: Dependencies;
  byKey: Map<string, DepFeature>;
  project: string;
  release: string;
  onSelect: (k: string) => void;
}) {
  const partners = partnersOf(f.key, data.couplings);
  const chains = prChainsOf(f, data);
  const counts = { open: 0, merged: 0, closed: 0 } as Record<string, number>;
  for (const p of f.prs) counts[p.state] = (counts[p.state] ?? 0) + 1;
  const late = f.prs.filter((p) => p.freeze_status === "merged_after_freeze");
  const open = f.prs.filter((p) => p.state === "open");
  const main = f.prs.find((p) => p.is_main);
  const name = (k: string) => {
    const g = byKey.get(k);
    return g ? `#${g.number} ${g.title}` : k;
  };
  return (
    <div className="space-y-4">
      <div>
        <p className="font-semibold text-slate-900">
          {featureLabel(f)} {f.title}
        </p>
        <p className="text-xs text-slate-500">
          {OUTCOME_META[f.outcome].label} · {f.sigs.map(shortSig).join(", ") || "no team label"}
        </p>
        <Link href={releasePath(project, release, `/features/${f.number}`)} className="text-xs font-medium text-action hover:underline">
          Open feature page →
        </Link>
      </div>

      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Tied to {partners.length} features</h3>
        <ul className="space-y-1.5">
          {partners.map((p) => (
            <li key={p.partner}>
              <button type="button" onClick={() => onSelect(p.partner)} className="text-left text-slate-800 hover:underline">
                {name(p.partner)}
              </button>
              <div className="text-xs text-slate-500">
                {p.blockedBy.map((s) => (
                  <div key={s.dependent + s.blocker} className="text-[#b02a2a]">
                    this feature waits on it: {PR_NUM(s.dependent)} needs {PR_NUM(s.blocker)}
                  </div>
                ))}
                {p.blocks.map((s) => (
                  <div key={s.dependent + s.blocker} className="text-[#b02a2a]">
                    it waits on this feature: {PR_NUM(s.dependent)} needs {PR_NUM(s.blocker)}
                  </div>
                ))}
                {p.shared > 0 && `${p.shared} shared PR${p.shared === 1 ? "" : "s"}`}
              </div>
            </li>
          ))}
          {!partners.length && <li className="text-xs text-slate-500">None: this feature stands alone.</li>}
        </ul>
      </section>

      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">PRs</h3>
        <p className="text-xs text-slate-600">
          {f.prs.length} verified: {counts.merged} merged, {counts.open} open, {counts.closed} closed
          {late.length ? ` · ${late.length} merged after Code Freeze` : ""}
        </p>
        {main && (
          <p className="mt-1 text-xs">
            Main PR:{" "}
            <a href={main.url} target="_blank" rel="noopener" className="text-action hover:underline">
              #{main.number}
            </a>{" "}
            <State s={main.state} /> {main.freeze_status === "merged_after_freeze" && <span className="text-[#b02a2a]">merged after freeze</span>}
          </p>
        )}
        {open.length > 0 && (
          <ul className="mt-1 space-y-0.5 text-xs">
            {open.slice(0, 8).map((p) => (
              <li key={p.key} className="truncate">
                <a href={p.url} target="_blank" rel="noopener" className="text-action hover:underline">
                  #{p.number}
                </a>{" "}
                <State s="open" /> <span className="text-slate-600">{p.title}</span>
              </li>
            ))}
            {open.length > 8 && <li className="text-slate-500">and {open.length - 8} more open</li>}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Stated &quot;depends on&quot; between PRs</h3>
        {chains.length ? (
          <ul className="space-y-1 text-xs">
            {chains.map((c) => (
              <li key={c.from + c.to} className="flex flex-wrap items-center gap-1">
                {PR_NUM(c.to)} <State s={c.toState} /> <span className="text-slate-400">needs</span> {PR_NUM(c.from)} <State s={c.fromState} />
                {c.toState === "open" && c.fromState === "closed" && <span className="font-medium text-[#b02a2a]">blocker closed unmerged</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-500">None stated in PR text.</p>
        )}
      </section>
    </div>
  );
}
