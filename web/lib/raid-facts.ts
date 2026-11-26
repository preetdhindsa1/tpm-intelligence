// Live Cockpit facts from GET /raid/summary. Every count is a field the API returned.
import type { RaidSummary } from "@/lib/api-raid";

/** Confirmed risks whose status is open. In progress, closed and suggested are other fields. */
export function openRisks(summary: RaidSummary): number {
  return summary.by_type.reduce((n, row) => n + (row.type === "risk" ? row.open : 0), 0);
}

export type RaidFact = { label: string; count: number };

/** Shown instead of counts when the release has no notes source. Zeros would read as "no risks". */
export const NO_MEETING_NOTES = "No meeting notes are connected for this release";

/** The three cockpit lines, in display order. Null when nothing is connected. */
export function raidFacts(summary: RaidSummary): RaidFact[] | null {
  if (summary.sources === 0) return null;
  return [
    { label: "Open risks", count: openRisks(summary) },
    { label: "Risks without an owner", count: summary.risks_without_owner },
    { label: "Waiting for review", count: summary.waiting_for_review },
  ];
}
