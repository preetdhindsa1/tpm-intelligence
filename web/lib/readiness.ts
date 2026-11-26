// Display rules for GET /readiness. The API computes the verdict; this only words it.
import type { CriterionStatus, Decision, ReadinessDecision, Verdict } from "@/lib/api-readiness";

export const UNKNOWN_REASON = "no data to decide";

export function verdictLabel(verdict: Verdict): string {
  if (verdict === "ready") return "Ready";
  if (verdict === "not_ready") return "Not ready";
  return "Unknown";
}

export function criterionLabel(status: CriterionStatus): string {
  if (status === "pass") return "Pass";
  if (status === "fail") return "Fail";
  return "Unknown";
}

/** Null when the note is long enough to send. */
export function noteError(note: string): string | null {
  return note.trim().length >= 3 ? null : "A note needs at least 3 characters.";
}

export function decisionLabel(decision: Decision): string {
  if (decision === "go") return "Go";
  if (decision === "no_go") return "No go";
  return "Defer";
}

/** Newest decision first. The log is append-only; this only sorts for display. */
export function newestDecisions(items: ReadinessDecision[]): ReadinessDecision[] {
  return [...items].sort((a, b) => (a.decided_at < b.decided_at ? 1 : a.decided_at > b.decided_at ? -1 : 0));
}
