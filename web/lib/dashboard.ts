// Pure helpers for the dashboard (ADR-0013). No numbers are computed here beyond
// filtering and layout; every value comes from the API.
import type { ExecUpdate, Outcome, Summary } from "./api";

/** Status colours (dataviz reference palette): reserved for state, always with a label. */
export const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
  neutral: "#a8a7a0",
} as const;
export type Status = keyof typeof STATUS;

export const OUTCOME_META: Record<Outcome, { label: string; status: Status; help: string }> = {
  landed: { label: "Landed", status: "good", help: "Never removed at Code Freeze, in the release 3 days after it, main PR merged" },
  landed_prs_after_freeze: {
    label: "Landed, PRs merged after freeze",
    status: "warning",
    help: "Landed, but a linked PR merged after Code Freeze (check the exception)",
  },
  landed_main_pr_open: { label: "Landed, main PR still open", status: "serious", help: "Still in the release, main PR not merged" },
  readded_after_freeze: { label: "Removed, then re-added", status: "warning", help: "Removed at Code Freeze, then added back (exception)" },
  removed_after_freeze: { label: "Removed after freeze", status: "critical", help: "In the release 3 days after Code Freeze, removed since" },
  removed_at_freeze: { label: "Removed at Code Freeze", status: "critical", help: "Removed within a window after Code Freeze" },
  removed_before_freeze: { label: "Removed before freeze", status: "neutral", help: "Left the release before Code Freeze" },
  too_early: { label: "Too early to tell", status: "neutral", help: "Outcome known 3 days after Code Freeze" },
};

const ORDER: Outcome[] = [
  "landed",
  "landed_prs_after_freeze",
  "landed_main_pr_open",
  "readded_after_freeze",
  "removed_after_freeze",
  "removed_at_freeze",
  "removed_before_freeze",
  "too_early",
];

/** One bar per outcome that occurred, in a fixed order (colour follows the outcome). */
export function outcomeRows(s: Summary): { outcome: Outcome; label: string; count: number; color: string; features: string[] }[] {
  return ORDER.filter((o) => (s.outcomes[o] ?? 0) > 0).map((o) => ({
    outcome: o,
    label: OUTCOME_META[o].label,
    count: s.outcomes[o] ?? 0,
    color: STATUS[OUTCOME_META[o].status],
    features: s.features.filter((f) => f.outcome === o).map((f) => `#${f.number} ${f.title}`),
  }));
}

/** Short labels for rule flags, shown as badges on graph nodes. */
export const FLAG_BADGES: Record<string, string> = {
  main_pr_not_merged: "Main PR missed freeze",
  removed_at_freeze: "Removed at freeze",
  late_main_pr: "Late main PR",
  review_waiting: "Review waiting",
  ci_failing: "CI failing",
  merged_after_freeze: "Merged after freeze",
  readded_after_freeze: "Re-added",
  no_linked_prs: "No linked PRs",
};

const BADGE_ORDER = Object.keys(FLAG_BADGES);

/** The most important flag's badge text, or null. */
export function topBadge(flags: string[]): string | null {
  const first = BADGE_ORDER.find((f) => flags.includes(f));
  return first ? FLAG_BADGES[first] : null;
}

/** The update the brief panel shows: newest approved, else newest draft. */
export function briefToShow(updates: ExecUpdate[]): ExecUpdate | null {
  const newest = [...updates].sort((a, b) => b.created_at.localeCompare(a.created_at));
  return newest.find((u) => u.status === "approved") ?? newest.find((u) => u.status === "draft") ?? null;
}
