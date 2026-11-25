// Connect your tools (UX vision p.7). A connector is "Available" only when a live program
// in GET /portfolio already reads it; everything else is "Planned". No customer counts.

export const STEPS = [
  { n: 1, title: "Connect your tools" },
  { n: 2, title: "Describe your releases" },
  { n: 3, title: "See your first program" },
] as const;

export type Connector = { id: string; name: string; reads: string; tools: string[] };

/** Every source the platform has or plans, with the portfolio tool ids that mean it is live. */
export const CONNECTORS: Connector[] = [
  { id: "github", name: "GitHub", reads: "Issues, PRs, reviews, CI · webhooks in seconds", tools: ["github"] },
  { id: "jira", name: "Jira", reads: "Epics, stories, fix versions, links, history", tools: ["jira"] },
  { id: "notes", name: "Meeting notes", reads: "Risks, actions and decisions for the RAID tracker", tools: ["notes"] },
  { id: "gitlab-linear", name: "GitLab · Linear", reads: "Same model, new connectors", tools: ["gitlab", "linear"] },
  { id: "slack-confluence", name: "Slack · Confluence", reads: "Context and decisions from conversations", tools: ["slack", "confluence"] },
  { id: "incidents", name: "Incidents", reads: "Launch risk from on-call signals", tools: ["incidents"] },
];

export type ProgramTools = { display_name: string; planning_tool?: string; code_tools?: string[] };

/** Live programs that read this connector, by display name. Empty means Planned. */
export function usedBy(connector: Connector, programs: ProgramTools[]): string[] {
  return programs
    .filter((p) => [p.planning_tool, ...(p.code_tools ?? [])].some((t) => t && connector.tools.includes(t)))
    .map((p) => p.display_name);
}

/** The release fields a team gives, in the order the stage uses them. */
export const RELEASE_FIELDS = [
  { key: "cycle_start_at", name: "Cycle start", why: "Plan ends and Build starts" },
  { key: "enhancements_freeze_at", name: "Enhancements Freeze", why: "Scope is locked" },
  { key: "code_freeze_at", name: "Code Freeze", why: "Build ends; only approved exceptions after" },
  { key: "release_at", name: "Release", why: "Launch starts; Learn a week later" },
] as const;

export const PROMISES = [
  { title: "Read-only, least access", body: "GitHub and Jira are read with read-only access, never written. Nothing is posted back." },
  { title: "Flow, not people", body: "Bottlenecks by team and reviewer pool. No individual productivity rankings." },
  { title: "You approve what leaves", body: "Exec updates and decisions are drafted, fact-checked, then approved by a TPM." },
] as const;
