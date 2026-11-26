// Live Cockpit facts from GET /raid/summary. Every count is a field the API returned.
import type { RaidSummary } from "@/lib/api-raid";

/** Confirmed risks whose status is open. In progress, closed and suggested are other fields. */
export function openRisks(summary: RaidSummary): number {
  return summary.by_type.reduce((n, row) => n + (row.type === "risk" ? row.open : 0), 0);
}

export type RaidFact = { label: string; count: number };

/** The three cockpit lines, in display order. */
export function raidFacts(summary: RaidSummary): RaidFact[] {
  return [
    { label: "Open risks", count: openRisks(summary) },
    { label: "Risks without an owner", count: summary.risks_without_owner },
    { label: "Waiting for review", count: summary.waiting_for_review },
  ];
}
