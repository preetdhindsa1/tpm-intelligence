// Decision Studio levers. Every value is sent to the simulator API; nothing is invented here.
import type { PoolChange, PoolOutcome, ScenarioSettings, SimPool, SimRange } from "@/lib/api";

export const LEVERS = [
  { id: "arrival", label: "New PRs vs measured rate" },
  { id: "reviewers", label: "Add or remove experienced reviewers" },
  { id: "new_reviewers", label: "New reviewers" },
  { id: "interruption", label: "Time lost to interruptions" },
] as const;

export type LeverId = (typeof LEVERS)[number]["id"];

/** Plain-language list of settings that differ from the measured baseline. */
export function scenarioNotes(settings: Pick<ScenarioSettings, "arrival_multiplier" | "pools">): string[] {
  const notes: string[] = [];
  if (settings.arrival_multiplier !== 1) notes.push(`New PRs ×${settings.arrival_multiplier.toFixed(1)}`);
  for (const [pool, change] of Object.entries(settings.pools)) notes.push(...poolNotes(pool, change));
  return notes;
}

function poolNotes(pool: string, change: PoolChange): string[] {
  const notes: string[] = [];
  if (change.reviewers !== 0) {
    notes.push(`${pool}: experienced reviewers ${change.reviewers > 0 ? "+" : ""}${change.reviewers}`);
  }
  if (change.new_reviewers !== 0) {
    notes.push(`${pool}: ${change.new_reviewers} new reviewers, ramp ${change.ramp_weeks} weeks`);
  }
  if (change.interruption !== 0) notes.push(`${pool}: interruptions ${Math.round(change.interruption * 100)}%`);
  return notes;
}

// ---- Decision Studio layout (UX vision p.5) ----------------------------------------------

const ACRONYM: Record<string, string> = { api: "API", cli: "CLI", ui: "UI", k8s: "K8s" };

/** "sig/api-machinery" → "SIG API Machinery"; "other" → "Other pools", or "All reviewers"
 * when it is the program's only pool (a team without sig/* labels, such as Kafka). */
export function poolName(pool: string, only = false): string {
  if (pool === "other") return only ? "All reviewers" : "Other pools";
  const words = pool.replace(/^sig\//, "").split(/[-_]/).map((w) => ACRONYM[w] ?? w.charAt(0).toUpperCase() + w.slice(1));
  return pool.startsWith("sig/") ? `SIG ${words.join(" ")}` : words.join(" ");
}

/** Open PRs per reviewer now; a pool with no reviewers counts as one. */
export function load(p: SimPool): number {
  return p.open_prs_now / Math.max(p.reviewers_now, 1);
}

/** Named pools, most loaded first, with the shared "other" pool last. */
export function poolsByLoad(pools: SimPool[]): SimPool[] {
  return [...pools].sort((a, b) => Number(a.pool === "other") - Number(b.pool === "other") || load(b) - load(a) || a.pool.localeCompare(b.pool));
}

/** The four levers the simulator models, each as one preset the person can adjust. */
export const STUDIO_LEVERS = [
  { id: "reviewers", label: "+1 reviewer", scenario: "+1 reviewer" },
  { id: "arrival", label: "AI doubles PR volume", scenario: "PR volume ×2" },
  { id: "new_reviewers", label: "New reviewer, ramping up", scenario: "+1 new reviewer" },
  { id: "interruption", label: "Interruptions take 20%", scenario: "20% interruptions" },
] as const satisfies readonly { id: LeverId; label: string; scenario: string }[];

/** The scenario settings for one lever pulled on one pool. */
export function leverSettings(lever: LeverId, pool: string): ScenarioSettings {
  const none = { reviewers: 0, new_reviewers: 0, ramp_weeks: 0, interruption: 0 };
  if (lever === "arrival") return { name: "", pools: {}, arrival_multiplier: 2 };
  if (lever === "reviewers") return { name: "", pools: { [pool]: { ...none, reviewers: 1 } }, arrival_multiplier: 1 };
  if (lever === "new_reviewers") return { name: "", pools: { [pool]: { ...none, new_reviewers: 1, ramp_weeks: 4 } }, arrival_multiplier: 1 };
  return { name: "", pools: { [pool]: { ...none, interruption: 0.2 } }, arrival_multiplier: 1 };
}

const n = (r: SimRange) => Math.round(r.median);

/** "412 of 760 open PRs merged by release day" and its range, from one pool's outcome. */
export function mergedLine(o: PoolOutcome, horizon: string): { big: string; line: string } | null {
  if (!o.merged || !o.not_merged) return null;
  const total = n(o.merged) + n(o.not_merged);
  return {
    big: `${n(o.merged)} of ${total}`,
    line: `PRs merged by ${horizon} · range ${Math.round(o.merged.low)}–${Math.round(o.merged.high)}`,
  };
}

/** The simulator names its horizon "Code Freeze"; show the team's own word for it (Kafka: "Feature Freeze"). */
export function teamHorizon<T extends { horizon_label: string }>(x: T, freezeLabel?: string): T {
  return freezeLabel && x.horizon_label === "Code Freeze" ? { ...x, horizon_label: freezeLabel } : x;
}
