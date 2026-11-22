// Pure helpers for the dashboard (ADR-0013). No numbers are computed here beyond
// filtering and layout; every value comes from the API.
import dagre from "@dagrejs/dagre";
import type { ExecUpdate, GraphData, GraphEdge, GraphNode, Outcome, Summary } from "./api";

/** Status colours (dataviz reference palette): reserved for state, always with a label. */
export const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
  neutral: "#a8a7a0",
} as const;
export type Status = keyof typeof STATUS;

export const OUTCOME_META: Record<Outcome, { label: string; status: Status; help: string }> = {
  landed: { label: "Landed", status: "good", help: "Never removed at Code Freeze, in the release 3 days after it, main PR merged" },
  landed_prs_after_freeze: {
    label: "Landed, PRs merged after freeze",
    status: "warning",
    help: "Landed, but a linked PR merged after Code Freeze (check the exception)",
  },
  landed_main_pr_open: { label: "Landed, main PR still open", status: "serious", help: "Still in the release, main PR not merged" },
  readded_after_freeze: { label: "Removed, then re-added", status: "warning", help: "Removed at Code Freeze, then added back (exception)" },
  removed_after_freeze: { label: "Removed after freeze", status: "critical", help: "In the release 3 days after Code Freeze, removed since" },
  removed_at_freeze: { label: "Removed at Code Freeze", status: "critical", help: "Removed within a window after Code Freeze" },
  removed_before_freeze: { label: "Removed before freeze", status: "neutral", help: "Left the release before Code Freeze" },
  too_early: { label: "Too early to tell", status: "neutral", help: "Outcome known 3 days after Code Freeze" },
};

const ORDER: Outcome[] = [
  "landed",
  "landed_prs_after_freeze",
  "landed_main_pr_open",
  "readded_after_freeze",
  "removed_after_freeze",
  "removed_at_freeze",
  "removed_before_freeze",
  "too_early",
];

/** One bar per outcome that occurred, in a fixed order (colour follows the outcome). */
export function outcomeRows(s: Summary): { outcome: Outcome; label: string; count: number; color: string; features: string[] }[] {
  return ORDER.filter((o) => (s.outcomes[o] ?? 0) > 0).map((o) => ({
    outcome: o,
    label: OUTCOME_META[o].label,
    count: s.outcomes[o] ?? 0,
    color: STATUS[OUTCOME_META[o].status],
    features: s.features.filter((f) => f.outcome === o).map((f) => `#${f.number} ${f.title}`),
  }));
}

/** Short labels for rule flags, shown as badges on graph nodes. */
export const FLAG_BADGES: Record<string, string> = {
  main_pr_not_merged: "Main PR missed freeze",
  removed_at_freeze: "Removed at freeze",
  late_main_pr: "Late main PR",
  review_waiting: "Review waiting",
  ci_failing: "CI failing",
  merged_after_freeze: "Merged after freeze",
  readded_after_freeze: "Re-added",
  no_linked_prs: "No linked PRs",
};

const BADGE_ORDER = Object.keys(FLAG_BADGES);

/** The most important flag's badge text, or null. */
export function topBadge(flags: string[]): string | null {
  const first = BADGE_ORDER.find((f) => flags.includes(f));
  return first ? FLAG_BADGES[first] : null;
}

export type GraphFilter = {
  query: string;
  sig: string; // "" = all
  showMerged: boolean; // show merged/closed PRs
  inReleaseOnly: boolean;
  maxFeatures?: number; // dashboard preview: most severe first
  mainOnly?: boolean; // dashboard preview: only each feature's main PR
};

const SEV_RANK: Record<string, number> = { critical: 0, warning: 1, info: 2 };

/** Every SIG on a feature, sorted. */
export function sigsOf(g: GraphData): string[] {
  return [...new Set(g.nodes.filter((n) => n.kind === "feature").flatMap((n) => n.sigs))].sort();
}

/** Features (and their PRs) that match the filter, plus the release node. */
export function filterGraph(g: GraphData, f: GraphFilter): GraphData {
  const q = f.query.trim().toLowerCase();
  let features = g.nodes.filter(
    (n) =>
      n.kind === "feature" &&
      (!f.inReleaseOnly || n.in_release) &&
      (!f.sig || n.sigs.includes(f.sig)),
  );
  if (q) {
    const prHits = new Set(
      g.nodes.filter((n) => n.kind === "pull_request" && (n.label.toLowerCase().includes(q) || n.title.toLowerCase().includes(q))).map((n) => n.feature),
    );
    features = features.filter((n) => n.label.toLowerCase().includes(q) || n.title.toLowerCase().includes(q) || prHits.has(n.id));
  }
  features = [...features].sort((a, b) => (SEV_RANK[a.severity ?? ""] ?? 3) - (SEV_RANK[b.severity ?? ""] ?? 3) || a.id.localeCompare(b.id));
  if (f.maxFeatures !== undefined) features = features.slice(0, f.maxFeatures);
  const keepFeatures = new Set(features.map((n) => n.id));
  const prs = new Set(
    g.edges
      .filter((e) => e.kind === "implemented_by" && keepFeatures.has(e.source))
      .map((e) => e.target)
      .filter((id) => {
        const n = g.nodes.find((x) => x.id === id);
        return !!n && (f.showMerged || n.state === "open") && (!f.mainOnly || !!n.is_main);
      }),
  );
  const keep = new Set([...g.nodes.filter((n) => n.kind === "release").map((n) => n.id), ...keepFeatures, ...prs]);
  return {
    ...g,
    nodes: g.nodes.filter((n) => keep.has(n.id)),
    edges: g.edges.filter((e) => keep.has(e.source) && keep.has(e.target)),
  };
}

export const NODE_SIZE: Record<GraphNode["kind"], { width: number; height: number }> = {
  release: { width: 120, height: 44 },
  feature: { width: 220, height: 56 },
  pull_request: { width: 150, height: 40 },
};

/** Left-to-right layered layout: release -> features -> PRs (PR dependencies inside). */
export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 14, ranksep: 70, marginx: 10, marginy: 10 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) g.setNode(n.id, { ...NODE_SIZE[n.kind] });
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  const out: Record<string, { x: number; y: number }> = {};
  for (const n of nodes) {
    const p = g.node(n.id) as { x: number; y: number };
    const size = NODE_SIZE[n.kind];
    out[n.id] = { x: p.x - size.width / 2, y: p.y - size.height / 2 };
  }
  return out;
}

/** The update the brief panel shows: newest approved, else newest draft. */
export function briefToShow(updates: ExecUpdate[]): ExecUpdate | null {
  const newest = [...updates].sort((a, b) => b.created_at.localeCompare(a.created_at));
  return newest.find((u) => u.status === "approved") ?? newest.find((u) => u.status === "draft") ?? null;
}
