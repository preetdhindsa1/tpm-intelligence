// Readiness and retro client (docs/api/readiness-retro-contract.md).
// Real retros add planned, warned_landed and moved_to; the synthetic example omits them.
// replay_day arrives as a showed fact named "replay_day". Said items have no quote in the contract.
import { act, serverGet } from "@/lib/api-http";
import type { RaidReview, RaidType } from "@/lib/api-raid";

export type CriterionStatus = "pass" | "fail" | "unknown";
export type CriterionId = "code_merged" | "no_critical_flags" | "ci_green" | "risks_owned" | "docs_merged";
export type Verdict = "ready" | "not_ready" | "unknown";
export type Decision = "go" | "no_go" | "defer";
export type Evidence = { text: string; ref: string; url: string | null };
export type Criterion = { id: CriterionId; name: string; status: CriterionStatus; detail: string; count: number | null; evidence: Evidence[] };
export type ReadinessDecision = { decision: Decision; note: string; decided_by: "approver"; decided_at: string; facts_as_of: string };
export type Claim = { text: string; refs: string[] };
export type Readiness = {
  project: string; release: string; as_of: string; synthetic: boolean; verdict: Verdict;
  criteria: Criterion[]; decisions: ReadinessDecision[]; summary: Claim[] | null;
  validated: boolean; validation_note: string;
};

export type SlipKind = "dropped" | "moved" | "late_exception";
export type Slip = {
  feature_key: string; title: string; pool: string | null; slip: SlipKind; slipped_at: string;
  first_warning_at: string | null; first_warning_flag: string | null; lead_time_days: number | null;
  moved_to?: string | null;
};
export type RetroSource = { kind: "retro" | "meeting" | "snapshots" | "pull_requests"; title: string; url: string | null; synthetic: boolean };
export type RetroTotals = {
  slips: number; warned: number; average_lead_time_days: number | null; median_lead_time_days: number | null;
  planned?: number | null; warned_landed?: number | null;
};
export type Retro = {
  project: string; release: string; label: string; as_of: string; synthetic: boolean;
  sources: RetroSource[]; totals: RetroTotals; slips: Slip[];
};
export type SaidItem = { item_id: number; raid_id: string | null; type: RaidType; title: string; review: RaidReview; quote?: string };
export type ShowedFact = { name: string; value: number | string | null };
export type SaidRow = { date: string; said: SaidItem[]; showed: ShowedFact[] };
export type SaidVsShowed = { project: string; release: string; synthetic: boolean; rows: SaidRow[] };
export type Pattern = { pool: string; pattern: string; text: string; value: number; n: number; releases: string[] };
export type Patterns = { project: string; synthetic: boolean; min_group: number; suppressed_groups: number; patterns: Pattern[] };

function q(params: Record<string, string>): string {
  return new URLSearchParams(params).toString();
}

export function fetchReadiness(release: string): Promise<Readiness> {
  return serverGet(`/readiness?${q({ release })}`);
}

/** Append a go, no-go or defer. The note is required (3+ characters). */
export function postDecision(release: string, decision: Decision, note: string): Promise<Readiness> {
  return act(`/readiness/${encodeURIComponent(release)}/decision`, { decision, note });
}

/** 404 until the retro job has run for this release. The synthetic fixture does not 404. */
export function fetchRetro(project: string, release: string): Promise<Retro> {
  return serverGet(`/retro?${q({ project, release })}`);
}

export function fetchSaidVsShowed(project: string, release: string): Promise<SaidVsShowed> {
  return serverGet(`/retro/said-vs-showed?${q({ project, release })}`);
}

export function fetchPatterns(project: string): Promise<Patterns> {
  return serverGet(`/retro/patterns?${q({ project })}`);
}

/** The replay day named inside `showed`, when the API sent one. */
export function replayDay(row: SaidRow): string | null {
  const fact = row.showed.find((f) => f.name === "replay_day");
  return typeof fact?.value === "string" ? fact.value : null;
}
