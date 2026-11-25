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
  planning_tool?: string;
  code_tools?: string[];
  has_lab?: boolean;
  dates?: { cycle_start_at: string | null; enhancements_freeze_at: string | null; code_freeze_at: string | null; release_at: string | null };
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

const TOOL: Record<string, string> = { github: "GitHub", jira: "Jira", gitlab: "GitLab", linear: "Linear" };

/** "Jira + GitHub" from the program's planning tool and code tools, each named once. */
export function toolsLabel(p: Pick<PortfolioProgram, "planning_tool" | "code_tools">): string {
  const names = [p.planning_tool, ...(p.code_tools ?? [])].filter((t): t is string => Boolean(t)).map((t) => TOOL[t] ?? t);
  return [...new Set(names)].join(" + ");
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const day = (iso: string) => `${new Date(iso).getUTCDate()} ${MONTHS[new Date(iso).getUTCMonth()]}`;
const dayYear = (iso: string) => `${day(iso)} ${new Date(iso).getUTCFullYear()}`;

/** "GitHub · release 16 Dec 2026": the program's tools and its release date. */
export function programSubline(p: PortfolioProgram): string {
  const tools = toolsLabel(p);
  const release = p.dates?.release_at ? `release ${dayYear(p.dates.release_at)}` : "";
  return [tools, release].filter(Boolean).join(" · ");
}

/** One line under the stage bar, from the stage and the release dates the API sent. */
export function stageLine(p: PortfolioProgram): string {
  const d = p.dates;
  const days = p.stage.days_to_next_milestone;
  switch (p.stage.current) {
    case "plan":
      return d?.cycle_start_at ? `Planning · cycle starts ${day(d.cycle_start_at)}` : "Planning";
    case "build":
      return d?.code_freeze_at ? `Building · Code Freeze ${dayYear(d.code_freeze_at)}` : "Building";
    case "freeze": {
      const past = d?.code_freeze_at ? `Past Code Freeze (${day(d.code_freeze_at)})` : "Past Code Freeze";
      return days !== null && p.stage.next_milestone?.name === "release" ? `${past} · release in ${days} day${days === 1 ? "" : "s"}` : past;
    }
    case "launch":
      return d?.release_at ? `Launching · released ${day(d.release_at)}` : "Launching";
    case "learn":
      return d?.release_at ? `Released ${dayYear(d.release_at)} · retro` : "Released · retro";
    default:
      return "Stage unknown";
  }
}

/** Short tag for the bottleneck; the API's headline when there is no shorter name. */
export function bottleneckTag(b: PortfolioProgram["bottleneck"]): string {
  if (b.kind === "linking_gap") return "Linking";
  if (b.kind === "review_gap") return "Review gap";
  return b.headline;
}

/** The text under the tag: the API's detail, or its headline when the tag is shortened. */
export function bottleneckText(b: PortfolioProgram["bottleneck"]): string | null {
  return bottleneckTag(b) === b.headline ? b.detail : (b.detail ?? b.headline);
}

const VERB: Record<string, string> = { approve_exec_update: "Review", review_link_suggestions: "Confirm", classify_prs: "Classify" };

/** The action word on a waiting row. */
export function waitingVerb(kind: string): string {
  return VERB[kind] ?? "Open";
}

export const STAGE_NAMES = ["plan", "build", "freeze", "launch", "learn"] as const;
