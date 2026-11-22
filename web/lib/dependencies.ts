// Pure helpers for the feature dependencies page (ADR-0013 addendum). Every fact comes
// from the API (engine/graph.py feature_dependencies); this file only lays it out.
import type { Coupling, DepFeature, Dependencies } from "@/lib/api";

export const PR_NUM = (key: string) => `#${key.split("#")[1]}`;
export const shortSig = (s: string) => s.replace("sig/", "");

export type DepStats = {
  features: number;
  coupled: number;
  clusters: number[];
  waiting: number;
  waitingOnClosed: number;
  multiSig: number;
  stated: number;
};

export function depStats(d: Dependencies): DepStats {
  return {
    features: d.features.length,
    coupled: d.features.filter((f) => f.cluster !== null).length,
    clusters: d.clusters.map((c) => c.length),
    waiting: d.waiting.length,
    waitingOnClosed: d.waiting.filter((w) => w.waits_on_state === "closed").length,
    multiSig: d.features.filter((f) => f.sigs.length > 1).length,
    stated: d.couplings.filter((c) => c.stated.length > 0).length,
  };
}

/** The SIGs most members of a cluster belong to (a name for the group, from facts). */
export function clusterName(members: DepFeature[], top = 2): string {
  const counts = new Map<string, number>();
  for (const f of members) for (const s of f.sigs) counts.set(s, (counts.get(s) ?? 0) + 1);
  const sigs = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, top);
  return sigs.length ? sigs.map(([s]) => shortSig(s)).join(" · ") : "no SIG label";
}

/** Couplings of one feature, stated dependencies first, then by shared PRs. */
export function partnersOf(featureKey: string, couplings: Coupling[]) {
  return couplings
    .filter((c) => c.a === featureKey || c.b === featureKey)
    .map((c) => ({
      partner: c.a === featureKey ? c.b : c.a,
      shared: c.shared_prs.length,
      blocks: c.stated.filter((s) => s.upstream === featureKey),
      blockedBy: c.stated.filter((s) => s.downstream === featureKey),
    }))
    .sort((x, y) => y.blockedBy.length + y.blocks.length - (x.blockedBy.length + x.blocks.length) || y.shared - x.shared);
}

/** "Depends on" edges that touch this feature's PRs, unmerged work first. */
export function prChainsOf(f: DepFeature, d: Dependencies) {
  const own = new Set(f.prs.map((p) => p.key));
  const state = new Map<string, string>();
  for (const g of d.features) for (const p of g.prs) state.set(p.key, p.state);
  const rank = (s?: string) => (s === "open" ? 0 : s === "closed" ? 1 : 2);
  return d.pr_edges
    .filter((e) => own.has(e.target) || own.has(e.source))
    .map((e) => ({ from: e.source, to: e.target, fromState: state.get(e.source) ?? "unknown", toState: state.get(e.target) ?? "unknown" }))
    .sort((a, b) => rank(a.toState) - rank(b.toState) || a.to.localeCompare(b.to));
}

// --- Map layout: each cluster as rings around its most connected feature --------------

export const MAP_NODE = { width: 210, height: 66 };
const RING_STEP = 110;
const H_GAP = 26;

type Point = { x: number; y: number };

const touches = (a: Point, b: Point) =>
  Math.abs(a.x - b.x) < MAP_NODE.width + 8 && Math.abs(a.y - b.y) < MAP_NODE.height + 8;

function adjacency(members: string[], couplings: Coupling[]) {
  const inside = new Set(members);
  const adj = new Map<string, Map<string, number>>(members.map((m) => [m, new Map()]));
  for (const c of couplings) {
    if (!inside.has(c.a) || !inside.has(c.b)) continue;
    const w = c.shared_prs.length + 3 * c.stated.length;
    adj.get(c.a)!.set(c.b, w);
    adj.get(c.b)!.set(c.a, w);
  }
  return adj;
}

/**
 * Positions (top-left corners) for one cluster, centred on (0, 0): the most connected
 * feature in the middle, then rings by distance, each node placed near its parents.
 * Rings are ellipses (nodes are wide and short) sized so neighbours do not overlap.
 */
export function clusterLayout(members: string[], couplings: Coupling[]): Record<string, Point> {
  const adj = adjacency(members, couplings);
  const degree = (k: string) => [...adj.get(k)!.values()].reduce((a, b) => a + b, 0);
  const hub = [...members].sort((a, b) => degree(b) - degree(a) || a.localeCompare(b))[0];
  const ring = new Map<string, number>([[hub, 0]]);
  const rings: string[][] = [[hub]];
  for (let i = 0; rings[i]?.length; i++) {
    const next: string[] = [];
    for (const k of rings[i])
      for (const n of [...adj.get(k)!.keys()].sort())
        if (!ring.has(n)) {
          ring.set(n, i + 1);
          next.push(n);
        }
    if (next.length) rings.push(next);
  }
  const angle = new Map<string, number>([[hub, 0]]);
  const pos: Record<string, Point> = { [hub]: { x: -MAP_NODE.width / 2, y: -MAP_NODE.height / 2 } };
  let rx = 0;
  let ry = 0;
  for (let i = 1; i < rings.length; i++) {
    const nodes = rings[i];
    // Each ring clears the previous one by a full node width (sideways) and height
    // (up/down), and is long enough that its n nodes fit around it without touching.
    rx = Math.max(rx + MAP_NODE.width + H_GAP, (nodes.length * (MAP_NODE.width + H_GAP)) / (2 * Math.PI) / 0.8);
    ry = Math.max(rx * 0.55, ry + RING_STEP);
    const desired = nodes.map((k) => {
      if (i === 1) return { k, a: 0 };
      const parents = [...adj.get(k)!.keys()].filter((p) => ring.get(p) === i - 1);
      const sx = parents.reduce((s, p) => s + Math.cos(angle.get(p)!), 0);
      const sy = parents.reduce((s, p) => s + Math.sin(angle.get(p)!), 0);
      return { k, a: Math.atan2(sy, sx) };
    });
    const step = (2 * Math.PI) / nodes.length;
    const base = new Map(desired.map((d) => [d.k, d.a]));
    // Spread a ring's nodes around it (keeping them near their parents) at a given
    // minimum angular gap; ring 1 is always spread evenly.
    const spread = (gapScale: number) => {
      if (i === 1) {
        desired.forEach((d, j) => (d.a = -Math.PI / 2 + j * step));
        return;
      }
      desired.forEach((d) => (d.a = base.get(d.k)!));
      desired.sort((x, y) => x.a - y.a || x.k.localeCompare(y.k));
      const gap = Math.min(step, (gapScale * (MAP_NODE.width + H_GAP)) / rx);
      for (let j = 1; j < desired.length; j++) desired[j].a = Math.max(desired[j].a, desired[j - 1].a + gap);
      // Centre the run on where its parents are, so it does not drift one way.
      const shift = desired.reduce((t, d) => t + d.a - base.get(d.k)!, 0) / desired.length;
      desired.forEach((d) => (d.a -= shift));
    };
    // A squarish ring (superellipse) rather than an ellipse, because nodes are
    // rectangles.
    const place = (sx: number, sy: number) =>
      desired.map(({ k, a }) => {
        const c = Math.cos(a);
        const sn = Math.sin(a);
        return {
          k,
          p: {
            x: sx * Math.sign(c) * Math.sqrt(Math.abs(c)) - MAP_NODE.width / 2,
            y: sy * Math.sign(sn) * Math.sqrt(Math.abs(sn)) - MAP_NODE.height / 2,
          },
        };
      });
    const placedBefore = Object.values(pos);
    let gapScale = 1;
    spread(gapScale);
    let ringPos = place(rx, ry);
    // If nodes still touch: spread them further around the ring first (keeps the map
    // compact), and only grow the ring when they touch the ring inside it.
    for (let tries = 0; tries < 60; tries++) {
      const pts = ringPos.map((r) => r.p);
      const inner = pts.some((p) => placedBefore.some((q) => touches(p, q)));
      const own = pts.some((p, j) => pts.slice(j + 1).some((q) => touches(p, q)));
      if (!inner && !own) break;
      if (own && !inner && gapScale < 3 && i > 1) gapScale *= 1.15;
      else {
        rx *= 1.06;
        ry *= 1.03;
      }
      spread(gapScale);
      ringPos = place(rx, ry);
    }
    for (const { k, p } of ringPos) pos[k] = p;
    for (const { k, a } of desired) angle.set(k, a);
  }
  return pos;
}

export type PlacedCluster = { index: number; x: number; y: number; width: number; height: number; positions: Record<string, Point> };

const CLUSTER_PAD = 28;
const CLUSTER_TITLE = 30;

/** Lays clusters out in rows (largest first), each in its own labelled box. */
export function packClusters(d: Dependencies, only?: number[], maxWidth = 1500, gap = 36): PlacedCluster[] {
  const out: PlacedCluster[] = [];
  let x = 0;
  let y = 0;
  let rowHeight = 0;
  d.clusters.forEach((members, index) => {
    if (only && !only.includes(index)) return;
    const rel = clusterLayout(members, d.couplings);
    const xs = Object.values(rel).map((p) => p.x);
    const ys = Object.values(rel).map((p) => p.y);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    const width = Math.max(...xs) - minX + MAP_NODE.width + 2 * CLUSTER_PAD;
    const height = Math.max(...ys) - minY + MAP_NODE.height + 2 * CLUSTER_PAD + CLUSTER_TITLE;
    if (x > 0 && x + width > maxWidth) {
      x = 0;
      y += rowHeight + gap;
      rowHeight = 0;
    }
    const positions: Record<string, Point> = {};
    for (const [k, p] of Object.entries(rel))
      positions[k] = { x: x + CLUSTER_PAD + p.x - minX, y: y + CLUSTER_PAD + CLUSTER_TITLE + p.y - minY };
    out.push({ index, x, y, width, height, positions });
    x += width + gap;
    rowHeight = Math.max(rowHeight, height);
  });
  return out;
}

/** Features shown at full strength when one is selected: itself and its partners. */
export function focusSet(selected: string | null, couplings: Coupling[]): Set<string> | null {
  if (!selected) return null;
  const s = new Set([selected]);
  for (const c of couplings) {
    if (c.a === selected) s.add(c.b);
    if (c.b === selected) s.add(c.a);
  }
  return s;
}

/** Stated cross-feature dependencies inside a group, as "upstream -> downstream" pairs. */
export function statedPairs(members: string[], couplings: Coupling[]): [string, string][] {
  const inside = new Set(members);
  const out: [string, string][] = [];
  for (const c of couplings)
    if (inside.has(c.a) && inside.has(c.b))
      for (const s of c.stated) if (!out.some(([u, d]) => u === s.upstream && d === s.downstream)) out.push([s.upstream, s.downstream]);
  return out;
}
