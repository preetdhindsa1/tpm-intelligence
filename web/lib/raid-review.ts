// Pure helpers for the RAID review queue. No counts are invented: progress is
// reviewed items plus the ones still suggested.
import type { RaidLink, RaidSummary, RaidType } from "@/lib/api-raid";

export const TYPE_LABEL: Record<RaidType, string> = {
  risk: "Risk", action: "Action", issue: "Issue", decision: "Decision", question: "Question",
};

const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/** Items a person has already confirmed, edited or rejected. */
export function reviewedCount(summary: RaidSummary): number {
  return summary.by_type.reduce(
    (n, row) => n + row.open + row.in_progress + row.closed + row.superseded + row.rejected,
    0,
  );
}

/** "4 of 23 reviewed". */
export function progressText(reviewed: number, waiting: number): string {
  return `${reviewed} of ${reviewed + waiting} reviewed`;
}

export function moveIndex(index: number, dir: 1 | -1, length: number): number {
  if (length === 0) return 0;
  return Math.min(length - 1, Math.max(0, index + dir));
}

export type QueueKey = "next" | "prev" | "confirm" | "edit" | "reject";

/** j/k move, c confirm, e edit, r reject. Other keys do nothing. */
export function keyAction(key: string): QueueKey | null {
  if (key === "j") return "next";
  if (key === "k") return "prev";
  if (key === "c") return "confirm";
  if (key === "e") return "edit";
  if (key === "r") return "reject";
  return null;
}

export function typingTarget(el: { tagName: string; isContentEditable: boolean }): boolean {
  return el.isContentEditable || TYPING.has(el.tagName);
}

/** The contract has no confidence number. This is the link method and its status. */
export function linkLine(links: RaidLink[]): string {
  if (links.length === 0) return "No linked feature";
  return links
    .map((l) => `${l.ref} · ${l.method === "explicit_key" ? "explicit key" : "AI suggested"}, ${l.status}`)
    .join("; ");
}

export function ownerText(owner: string | null): string {
  return owner && owner.trim() ? owner : "No owner";
}

/** Null when a reject reason is long enough to send. */
export function reasonError(reason: string): string | null {
  return reason.trim().length >= 3 ? null : "A reason needs at least 3 characters.";
}
