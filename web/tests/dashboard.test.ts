import { describe, expect, it } from "vitest";
import type { ExecUpdate, GraphData, GraphNode, Summary } from "../lib/api";
import { briefToShow, filterGraph, layoutGraph, outcomeRows, sigsOf, topBadge } from "../lib/dashboard";

function node(id: string, kind: GraphNode["kind"], extra: Partial<GraphNode> = {}): GraphNode {
  return {
    id,
    kind,
    label: id,
    title: id,
    url: null,
    sigs: [],
    in_release: null,
    severity: null,
    flags: [],
    state: null,
    is_main: null,
    on_critical_path: false,
    feature: null,
    ...extra,
  };
}

const GRAPH: GraphData = {
  release: "r",
  as_of: "2026-11-22T00:00:00Z",
  nodes: [
    node("r", "release"),
    node("f1", "feature", { title: "Ephemeral volumes", sigs: ["sig/node", "sig/storage"], in_release: true, severity: "critical" }),
    node("f2", "feature", { title: "Memory QoS", sigs: ["sig/node"], in_release: true, severity: null }),
    node("f3", "feature", { title: "COSI", sigs: ["sig/storage"], in_release: false, severity: "critical" }),
    node("p1", "pull_request", { label: "PR #1", title: "main impl", state: "open", feature: "f1", is_main: true }),
    node("p2", "pull_request", { label: "PR #2", title: "api types", state: "merged", feature: "f1" }),
    node("p3", "pull_request", { label: "PR #3", title: "cgroups v2", state: "open", feature: "f2" }),
  ],
  edges: [
    { source: "r", target: "f1", kind: "contains" },
    { source: "r", target: "f2", kind: "contains" },
    { source: "r", target: "f3", kind: "contains" },
    { source: "f1", target: "p1", kind: "implemented_by" },
    { source: "f1", target: "p2", kind: "implemented_by" },
    { source: "f2", target: "p3", kind: "implemented_by" },
    { source: "p2", target: "p1", kind: "blocks" },
  ],
};

const ids = (g: GraphData) => g.nodes.map((n) => n.id).sort();

describe("filterGraph", () => {
  const all = { query: "", sig: "", showMerged: true, inReleaseOnly: false };
  it("keeps everything with no filter", () => {
    expect(ids(filterGraph(GRAPH, all))).toEqual(ids(GRAPH));
  });
  it("hides merged PRs and removed features", () => {
    expect(ids(filterGraph(GRAPH, { ...all, showMerged: false, inReleaseOnly: true }))).toEqual(["f1", "f2", "p1", "p3", "r"]);
  });
  it("filters by SIG and finds features through their PRs", () => {
    expect(ids(filterGraph(GRAPH, { ...all, sig: "sig/storage" }))).toEqual(["f1", "f3", "p1", "p2", "r"]);
    expect(ids(filterGraph(GRAPH, { ...all, query: "cgroups" }))).toEqual(["f2", "p3", "r"]);
  });
  it("previews the most severe features first", () => {
    expect(ids(filterGraph(GRAPH, { ...all, inReleaseOnly: true, maxFeatures: 1 }))).toEqual(["f1", "p1", "p2", "r"]);
  });
  it("can keep only each feature's main PR", () => {
    expect(ids(filterGraph(GRAPH, { ...all, mainOnly: true }))).toEqual(["f1", "f2", "f3", "p1", "r"]);
  });
  it("drops edges to hidden nodes", () => {
    const g = filterGraph(GRAPH, { ...all, showMerged: false });
    expect(g.edges.some((e) => e.source === "p2" || e.target === "p2")).toBe(false);
  });
  it("lists SIGs", () => {
    expect(sigsOf(GRAPH)).toEqual(["sig/node", "sig/storage"]);
  });
});

describe("layoutGraph", () => {
  it("lays out left to right: release, then features, then PRs", () => {
    const pos = layoutGraph(GRAPH.nodes, GRAPH.edges);
    expect(pos.r.x).toBeLessThan(pos.f1.x);
    expect(pos.f1.x).toBeLessThan(pos.p2.x);
  });
});

describe("outcomes and badges", () => {
  it("orders outcome bars and names their features", () => {
    const s = {
      outcomes: { removed_at_freeze: 2, landed: 5 },
      features: [{ key: "k", number: 1979, title: "COSI", outcome: "removed_at_freeze", sigs: [] }],
    } as unknown as Summary;
    const rows = outcomeRows(s);
    expect(rows.map((r) => r.outcome)).toEqual(["landed", "removed_at_freeze"]);
    expect(rows[1].features).toEqual(["#1979 COSI"]);
    expect(rows[1].color).toBe("#d03b3b");
  });
  it("picks the most important flag", () => {
    expect(topBadge(["ci_failing", "main_pr_not_merged"])).toBe("Main PR missed freeze");
    expect(topBadge([])).toBeNull();
  });
});

describe("briefToShow", () => {
  const u = (id: number, status: ExecUpdate["status"], created_at: string) => ({ id, status, created_at }) as ExecUpdate;
  it("prefers the newest approved update, else the newest draft", () => {
    expect(briefToShow([u(1, "approved", "2026-11-20"), u(2, "draft", "2026-11-22")])?.id).toBe(1);
    expect(briefToShow([u(1, "draft", "2026-11-20"), u(2, "draft", "2026-11-22"), u(3, "rejected", "2026-11-23")])?.id).toBe(2);
    expect(briefToShow([u(3, "rejected", "2026-11-23")])).toBeNull();
  });
});
