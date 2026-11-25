// Front-page copy that is allowed to carry a number. Counts come from the caller
// (the API or lib/measured.ts). This file never looks a number up itself.
import type { Measured } from "@/lib/measured";

export type Story = { title: string; detail: string; asOf: string };

export const STAGE_MODULES = [
  { stage: "Plan", module: "Portfolio", status: "Live" },
  { stage: "Build", module: "Live Cockpit", status: "Live" },
  { stage: "Freeze", module: "Live Cockpit", status: "Live" },
  { stage: "Launch", module: "Release readiness", status: "Planned" },
  { stage: "Learn", module: "Retro insights", status: "Planned" },
] as const;

export const DEMO_LENGTH = "2:00";

export const DEMO_CHAPTERS = [
  "Live programs",
  "Live Cockpit",
  "Code Freeze",
  "Decision Studio",
  "What we measured",
] as const;

export function freezeStory(display: string, release: string, removed: number, asOf: string): Story | null {
  if (removed <= 0 || !asOf) return null;
  return {
    title: `${removed} removed at Code Freeze`,
    detail: `${display} ${release}. From the release summary.`,
    asOf,
  };
}

export function reviewStory(display: string, approved: number, merged: number, asOf: string): Story | null {
  if (merged <= 0 || !asOf) return null;
  return {
    title: `${approved} of ${merged} merged pull requests had an approving review`,
    detail: display,
    asOf,
  };
}

export function measuredStory(rows: Measured[], id: string): Story | null {
  const row = rows.find((item) => item.id === id);
  if (!row || !row.measured || row.verdict === "pending") return null;
  return { title: row.value, detail: row.label, asOf: row.measured };
}
