import { describe, expect, it } from "vitest";
import type { Coupling, DepFeature, Dependencies } from "@/lib/api";
import { clusterLayout, clusterName, depStats, focusSet, MAP_NODE, packClusters, partnersOf, prChainsOf, statedPairs } from "@/lib/dependencies";

const feat = (n: number, sigs: string[], prs: [number, string][] = [], cluster: number | null = 0): DepFeature => ({
  key: `k#${n}`,
  number: n,
  title: `F${n}`,
  url: null,
  sigs,
  in_release: true,
  severity: null,
  flags: [],
  outcome: "landed",
  cluster,
  prs: prs.map(([p, state]) => ({ key: `kk#${p}`, number: p, title: "", url: "", state, is_main: false, freeze_status: "merged_before_freeze" })),
});

const shared = (a: number, b: number, n: number): Coupling => ({
  a: `k#${a}`,
  b: `k#${b}`,
  shared_prs: Array.from({ length: n }, (_, i) => `kk#${a * 100 + i}`),
  stated: [],
});

// Real v1.38 shape: #5075 is the hub of the DRA group; #6268 -> #3157 is a stated dependency.
const DATA: Dependencies = {
  release: "kubernetes:v1.38",
  as_of: "2026-11-22T00:00:00Z",
  include_removed: false,
  features: [
    feat(5075, ["sig/node", "sig/scheduling"], [[1, "open"]]),
    feat(4815, ["sig/node", "sig/scheduling"], [[2, "merged"]]),
    feat(5007, ["sig/scheduling"]),
    feat(5419, ["sig/node"]),
    feat(3157, ["sig/api-machinery"], [[143270, "merged"], [141452, "open"]], 1),
    feat(6268, ["sig/api-machinery"], [[143232, "merged"], [141450, "closed"]], 1),
    feat(6395, ["sig/node", "sig/storage"], [], null),
  ],
  pr_edges: [
    { source: "kk#143232", target: "kk#143270", kind: "blocks" },
    { source: "kk#141450", target: "kk#141452", kind: "blocks" },
  ],
  couplings: [
    shared(4815, 5075, 10),
    shared(5007, 5075, 3),
    shared(5075, 5419, 2),
    shared(4815, 5419, 2),
    { a: "k#3157", b: "k#6268", shared_prs: [], stated: [{ upstream: "k#6268", downstream: "k#3157", blocker: "kk#143232", dependent: "kk#143270" }] },
  ],
  clusters: [
    ["k#4815", "k#5007", "k#5075", "k#5419"],
    ["k#3157", "k#6268"],
  ],
  waiting: [{ pr: "kk#141452", pr_title: "", waits_on: "kk#141450", waits_on_title: "", waits_on_state: "closed", features: ["k#3157"] }],
  sig_pairs: [{ a: "sig/node", b: "sig/scheduling", features: 2 }],
};

const overlap = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  Math.abs(a.x - b.x) < MAP_NODE.width && Math.abs(a.y - b.y) < MAP_NODE.height;

describe("dependencies page helpers", () => {
  it("counts tiles from the API facts", () => {
    expect(depStats(DATA)).toEqual({ features: 7, coupled: 6, clusters: [4, 2], waiting: 1, waitingOnClosed: 1, multiSig: 3, stated: 1 });
  });

  it("puts the most connected feature in the middle, with no overlaps", () => {
    const pos = clusterLayout(DATA.clusters[0], DATA.couplings);
    expect(pos["k#5075"]).toEqual({ x: -MAP_NODE.width / 2, y: -MAP_NODE.height / 2 });
    const all = Object.values(pos);
    for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) expect(overlap(all[i], all[j])).toBe(false);
  });

  it("does not overlap nodes even in a 17-feature hub", () => {
    const members = Array.from({ length: 17 }, (_, i) => `k#${i}`);
    const couplings = [
      ...members.slice(1, 10).map((m) => ({ a: "k#0", b: m, shared_prs: ["x"], stated: [] })),
      ...members.slice(10).map((m, i) => ({ a: members[1 + (i % 9)], b: m, shared_prs: ["x"], stated: [] })),
    ];
    const all = Object.values(clusterLayout(members, couplings));
    expect(all).toHaveLength(17);
    for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) expect(overlap(all[i], all[j])).toBe(false);
  });

  it("packs clusters into separate boxes", () => {
    const [a, b] = packClusters(DATA);
    expect(b.x).toBeGreaterThanOrEqual(a.x + a.width);
    for (const p of Object.values(b.positions)) expect(p.x).toBeGreaterThanOrEqual(b.x);
    expect(packClusters(DATA, [1]).map((c) => c.index)).toEqual([1]);
  });

  it("lists stated dependencies inside a group with their direction", () => {
    expect(statedPairs(DATA.clusters[1], DATA.couplings)).toEqual([["k#6268", "k#3157"]]);
    expect(statedPairs(DATA.clusters[0], DATA.couplings)).toEqual([]);
  });

  it("names a group by its most common SIGs", () => {
    expect(clusterName(DATA.features.slice(0, 4))).toBe("node · scheduling");
  });

  it("lists partners with stated dependencies first and their direction", () => {
    const p = partnersOf("k#3157", DATA.couplings);
    expect(p[0].partner).toBe("k#6268");
    expect(p[0].blockedBy).toHaveLength(1);
    expect(partnersOf("k#5075", DATA.couplings).map((x) => x.shared)).toEqual([10, 3, 2]);
  });

  it("shows a feature's PR chains, open work first", () => {
    const chains = prChainsOf(DATA.features[4], DATA);
    expect(chains[0]).toMatchObject({ from: "kk#141450", to: "kk#141452", fromState: "closed", toState: "open" });
  });

  it("focuses a feature and its partners", () => {
    expect([...focusSet("k#4815", DATA.couplings)!].sort()).toEqual(["k#4815", "k#5075", "k#5419"]);
    expect(focusSet(null, DATA.couplings)).toBeNull();
  });
});
