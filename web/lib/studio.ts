// Decision Studio levers. Every value is sent to the simulator API; nothing is invented here.
import type { PoolChange, ScenarioSettings } from "@/lib/api";

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
