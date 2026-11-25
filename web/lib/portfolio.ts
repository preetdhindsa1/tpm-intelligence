// Display helpers for GET /portfolio (docs/api/ux-v1-contract.md). No numbers are created here.
import { releasePath } from "@/lib/routes";

export type StageStep = { name: string; status: string };
export type Milestone = { name: string; at: string };

export type PortfolioProgram = {
  key: string;
  project: string;
  display_name: string;
  release: string;
  as_of: string;
  stage: {
    current: string | null;
    stages: StageStep[];
    days_to_next_milestone: number | null;
    next_milestone: Milestone | null;
  };
  scope: { features_in_release: number; features_ever: number };
  bottleneck: { kind: string; severity: string; headline: string; detail: string | null };
  next_decision: { kind: string; label: string; count: number } | null;
};

export type WaitingItem = { kind: string; program_key: string; label: string; count: number };
export type AcrossItem = { kind: string; title: string; text: string; program_key: string };
export type ComingNext = { module: string; name: string; status: string };

export type Skipped = { team: string; reason: string };

export type Portfolio = {
  as_of: string;
  totals: { programs: number; planning_tools: string[]; waiting_on_you: number };
  programs: PortfolioProgram[];
  waiting_on_you: WaitingItem[];
  across_programs: AcrossItem[];
  coming_next: ComingNext[];
  skipped: Skipped[];
};

/** These reasons mean the team has no program row. A store failure keeps the row. */
const MISSING_ROW = new Set(["no release yet", "release could not be computed"]);

const STAGE_LABEL: Record<string, string> = {
  plan: "Plan",
  build: "Build",
  freeze: "Freeze",
  launch: "Launch",
  learn: "Learn",
};

/** The contract's stage name, or "Stage unknown" when current is null. */
export function stageLabel(current: string | null): string {
  if (!current) return "Stage unknown";
  return STAGE_LABEL[current] ?? current;
}

/** Locked word for a planned module. Any other status is shown as the API sent it. */
export function statusLabel(status: string): string {
  return status === "planned" ? "Planned" : status;
}

export function severityClass(severity: string): string {
  if (severity === "critical") return "bg-critical-bg text-critical";
  if (severity === "warning") return "bg-warning-bg text-warning";
  return "bg-slate-100 text-slate-700";
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** Header counts from `totals`. The tool count is the length of the API's list. */
export function portfolioSummary(totals: Portfolio["totals"]): string {
  return `${plural(totals.programs, "program")} · ${plural(totals.planning_tools.length, "planning tool")} · ${plural(totals.waiting_on_you, "decision")} waiting on you`;
}

export function missingRows(skipped: Skipped[]): Skipped[] {
  return skipped.filter((s) => MISSING_ROW.has(s.reason));
}

/** Store failures for this program. `team` is the connector id, matched to `project`. */
export function approvalNotes(project: string, skipped: Skipped[]): string[] {
  const id = project.toLowerCase();
  return skipped
    .filter((s) => !MISSING_ROW.has(s.reason) && s.team.toLowerCase() === id)
    .map((s) => `Approvals may be missing: ${s.reason}`);
}

/** Where a waiting item goes. Unknown kinds stay plain text. */
export function decisionHref(project: string, release: string, kind: string): string | null {
  if (kind === "approve_exec_update") return releasePath(project, release, "/update");
  if (kind === "review_link_suggestions") return releasePath(project, release, "/links");
  if (kind === "classify_prs") return "/lab";
  return null;
}
