// RAID client (docs/api/raid-contract.md). The contract has no confidence number:
// a link's method and status are the confidence. The quote cannot be edited.
import { act, serverGet } from "@/lib/api-http";

export type RaidType = "risk" | "action" | "issue" | "decision" | "question";
export type RaidStatus = "open" | "in_progress" | "closed" | "superseded";
export type RaidReview = "suggested" | "confirmed" | "edited" | "rejected";

export type RaidSource = { kind: "meeting" | "ticket" | "pr" | "retro"; title: string; url: string | null; date: string; synthetic: boolean };
export type RaidLink = { kind: "feature" | "issue" | "pr"; ref: string; method: "explicit_key" | "ai_suggested"; status: "verified" | "suggested" };
export type MergeSuggestion = { into_item_id: number; reason: string };

export type RaidItem = {
  item_id: number;
  raid_id: string | null;
  workstream: string;
  type: RaidType;
  title: string;
  quote: string;
  source: RaidSource;
  owner: string | null;
  status: RaidStatus;
  review: RaidReview;
  links: RaidLink[];
  merge_suggestion: MergeSuggestion | null;
  created_at: string;
  updated_at: string;
};

export type RaidList = { project: string; release: string; as_of: string; synthetic: boolean; items: RaidItem[] };
export type RaidHistoryEntry = {
  at: string;
  actor: "extractor" | "approver";
  action: "suggested" | "confirmed" | "edited" | "rejected" | "status_changed";
  changes: Record<string, unknown>;
  reason: string | null;
};
export type RaidHistory = { item_id: number; raid_id: string | null; synthetic: boolean; history: RaidHistoryEntry[] };
export type RaidCount = { type: RaidType; suggested: number; open: number; in_progress: number; closed: number; superseded: number; rejected: number };
export type RaidSummary = {
  project: string; release: string; as_of: string; synthetic: boolean;
  by_type: RaidCount[]; risks_without_owner: number; waiting_for_review: number;
};
export type RaidEdit = { title?: string; type?: RaidType; owner?: string; status?: RaidStatus; note?: string };

function scope(project: string, release: string): string {
  return new URLSearchParams({ project, release }).toString();
}

/** Confirmed and edited items. Suggested items stay on the queue. */
export function fetchRaid(project: string, release: string): Promise<RaidList> {
  return serverGet(`/raid?${scope(project, release)}`);
}

/** Suggested items waiting for a person. */
export function fetchRaidQueue(project: string, release: string): Promise<RaidList> {
  return serverGet(`/raid/queue?${scope(project, release)}`);
}

export function fetchRaidSummary(project: string, release: string): Promise<RaidSummary> {
  return serverGet(`/raid/summary?${scope(project, release)}`);
}

/** Every change, oldest first. The actor is a role, never a login. */
export function fetchRaidHistory(itemId: number): Promise<RaidHistory> {
  return serverGet(`/raid/${itemId}/history`);
}

/** Confirm. A note is sent only when the person wrote one. The response carries the new RAID ID. */
export function confirmRaid(itemId: number, note?: string): Promise<RaidItem> {
  return act(`/raid/${itemId}/confirm`, note ? { note } : {});
}

/** Correct and confirm. The body has no quote: the API keeps the source's words. */
export function editRaid(itemId: number, edit: RaidEdit): Promise<RaidItem> {
  return act(`/raid/${itemId}/edit`, edit);
}

/** Reject. The reason is required (3+ characters). A rejected item gets no RAID ID. */
export function rejectRaid(itemId: number, reason: string): Promise<RaidItem> {
  return act(`/raid/${itemId}/reject`, { reason });
}
