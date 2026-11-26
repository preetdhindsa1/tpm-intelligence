// Tracker filters and history wording. Suggested items never pass the filter.
import type { RaidHistoryEntry, RaidItem } from "@/lib/api-raid";

export type TrackerFilter = { type: string; status: string; workstream: string };

const ROLES = new Set(["extractor", "approver"]);

/** Confirmed and edited items matching the filters. Suggested and rejected stay out. */
export function trackerRows(items: RaidItem[], filter: TrackerFilter): RaidItem[] {
  return items.filter((item) => {
    if (item.review !== "confirmed" && item.review !== "edited") return false;
    if (filter.type && item.type !== filter.type) return false;
    if (filter.status && item.status !== filter.status) return false;
    if (filter.workstream && item.workstream !== filter.workstream) return false;
    return true;
  });
}

/** Oldest first, even if a response arrives out of order. */
export function oldestFirst(rows: RaidHistoryEntry[]): RaidHistoryEntry[] {
  return [...rows].sort((a, b) => a.at.localeCompare(b.at));
}

/** A role. Anything else is shown as approver, never as a login. */
export function actorRole(actor: string): string {
  return ROLES.has(actor) ? actor : "approver";
}

export const EMPTY_FILTER: TrackerFilter = { type: "", status: "", workstream: "" };
