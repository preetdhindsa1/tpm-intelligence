// Front-page text that carries a number. Every number comes from the caller: the API
// (portfolio, release summary, feature timeline, pod facts) or lib/measured.ts.
import type { Measured } from "@/lib/measured";

const DAY = 86_400_000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "4 Feb 2027" in UTC, the design's short date. */
export function shortDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export type Tag = { text: string; tone: "live" | "warn" | "next" | "planned" };

/** The five stages and the module that covers each. Status is the product's own state. */
export const STAGES: { n: string; stage: string; title: string; body: string; tags: Tag[] }[] = [
  { n: "01", stage: "Plan", title: "Program setup", body: "Workstreams, owners, milestones and dependencies from GitHub or Jira.", tags: [{ text: "Live", tone: "live" }] },
  { n: "02", stage: "Build", title: "Live tracking + AI-native PDLC", body: "Plan vs real work, and how the pod of people, agents and bots builds and checks code.", tags: [{ text: "Live", tone: "live" }] },
  { n: "03", stage: "Freeze", title: "Forecast + Decision Studio", body: "Odds per feature, and what-ifs before you move people.", tags: [{ text: "Live · not validated", tone: "warn" }] },
  { n: "04", stage: "Launch", title: "Verified updates + readiness", body: "Fact-checked exec updates today; go/no-go from real signals next.", tags: [{ text: "Live", tone: "live" }, { text: "Next", tone: "next" }] },
  { n: "05", stage: "Learn", title: "Retros + RAID", body: "What slipped and when it was first visible; risks and decisions from meetings.", tags: [{ text: "Planned", tone: "planned" }] },
];

export const DEMO_LENGTH = "2:00";

/** Chapters of the recorded demo. Each one links to the live screen it shows. */
export const DEMO_CHAPTERS = [
  { at: "0:00", title: "The problem: code is cheap, certainty isn't", target: "front" },
  { at: "0:20", title: "Live Cockpit: replay Kubernetes v1.38", target: "cockpit" },
  { at: "0:50", title: "Decision Studio: test a fix", target: "studio" },
  { at: "1:15", title: "AI-native PDLC: the pod of 4", target: "pdlc" },
  { at: "1:40", title: "Trust: every number checked", target: "trust" },
] as const;

/** Days between two timestamps, rounded to the nearest day; null when either is missing. */
export function daysBetween(from: string | null | undefined, to: string | null | undefined): number | null {
  if (!from || !to) return null;
  return Math.round((new Date(to).getTime() - new Date(from).getTime()) / DAY);
}

/**
 * The replay sentence for a feature that missed Code Freeze, from its main PR's real dates.
 * Null unless the main PR opened before the freeze and merged after it.
 */
export function freezeReplay(
  feature: number,
  mainOpened: string | null | undefined,
  mainMerged: string | null | undefined,
  codeFreeze: string | null | undefined,
  readded: boolean,
): string | null {
  const before = daysBetween(mainOpened, codeFreeze);
  const late = daysBetween(codeFreeze, mainMerged);
  if (before === null || late === null || before < 0 || late < 0) return null;
  const back = readded ? ", and was re-added after" : "";
  return `Feature #${feature}'s main PR opened ${before} days before the freeze, missed it by ${late} day${late === 1 ? "" : "s"}${back}.`;
}

/** "21 / 26" → [21, 26], or null for a value that is not a fraction. */
export function fraction(value: string): [number, number] | null {
  const m = value.match(/^\s*(\d+)\s*\/\s*(\d+)\s*$/);
  if (!m || Number(m[2]) === 0) return null;
  return [Number(m[1]), Number(m[2])];
}

export type TrustTile = { value: string; label: string; warn: boolean };

/** The four headline scorecard tiles, taken from the measured list. Missing rows are skipped. */
export function trustTiles(rows: Measured[]): TrustTile[] {
  const pick = (id: string) => rows.find((r) => r.id === id && r.verdict !== "pending");
  const out: TrustTile[] = [];
  const fc = pick("fact-checker");
  if (fc) out.push({ value: fc.value, label: "fact-checker test claims judged correctly", warn: false });
  const vp = pick("vp-summary");
  if (vp) out.push({ value: vp.value, label: "VP-summary claims removed in live evals", warn: false });
  const link = pick("linking");
  if (link) {
    const f = fraction(link.value);
    out.push({ value: f ? `${((f[0] / f[1]) * 100).toFixed(1)}%` : link.value, label: "v1.38 features linked to a verified PR", warn: false });
  }
  const fo = pick("forecast");
  if (fo) out.push({ value: fo.value, label: 'backtests where the forecast beats the base rate: labeled "not validated"', warn: fo.verdict !== "pass" });
  return out;
}

/** The three trust rules (UX: Trust by design). `proof` is filled from data by trustRules(). */
export const TRUST_RULES = [
  {
    id: "facts",
    title: "AI never computes facts",
    body: "Counts, dates, links, critical paths and odds come from code and statistics. AI is used for messy text and explanation only.",
  },
  {
    id: "verified",
    title: "Every AI sentence is verified",
    body: "Agents return structured claims. The fact checker keeps a claim only if the database supports it, and publishes how many it removed.",
  },
  {
    id: "suggestions",
    title: "Suggestions stay suggestions",
    body: "When AI proposes that a PR belongs to a feature, it is stored as suggested and never counts until a rule or a person confirms it.",
  },
] as const;

export type WaitingLite = { kind: string; count: number; label: string };

/** The proof line under each rule: a measured result or a live count, never a stand-in. */
export function trustProof(id: (typeof TRUST_RULES)[number]["id"], rows: Measured[], waiting: WaitingLite[]): string {
  if (id === "facts") return "Every number on every page comes from a rule, a count or a statistical model.";
  if (id === "verified") {
    const fc = rows.find((r) => r.id === "fact-checker" && r.verdict !== "pending");
    return fc ? `${fc.value} agreement with labelled claims (measured ${fc.measured}).` : "Fact-checker accuracy: TBD (not yet measured).";
  }
  const live = waiting.find((w) => w.kind === "review_link_suggestions" && w.count > 0);
  if (live) {
    const release = live.label.split("·").pop()?.trim();
    return `${live.count.toLocaleString("en-US")}${release ? ` ${release}` : ""} suggestions are waiting for review now; none of them count yet.`;
  }
  const ls = rows.find((r) => r.id === "link-suggester" && r.verdict !== "pending");
  return ls ? `Link suggester precision ${ls.value}; no suggestion counts until confirmed (measured ${ls.measured}).` : "No suggestions are waiting for review.";
}

/** "7 pass · 3 partly · 2 fail · 1 not measured yet" over the measured list. */
export function verdictSummary(rows: Measured[]): string {
  const n = (v: Measured["verdict"]) => rows.filter((r) => r.verdict === v).length;
  return [
    [n("pass"), "pass"],
    [n("partial"), "partly"],
    [n("fail"), "fail"],
    [n("pending"), "not measured yet"],
  ]
    .filter(([c]) => Number(c) > 0)
    .map(([c, w]) => `${c} ${w}`)
    .join(" · ");
}

export type StepKind = "deterministic" | "ai" | "human";

/** How it works: raw events to an update a VP can trust. Who does each step is a fixed design rule. */
export const PIPELINE: { n: string; title: string; body: string; kind: StepKind }[] = [
  { n: "01", title: "Collect", body: "Issues, PRs, reviews, CI and history as timestamped events. Nothing is overwritten.", kind: "deterministic" },
  { n: "02", title: "Link", body: "PR → feature → release from explicit keys and tracking lists. AI only suggests the rest.", kind: "deterministic" },
  { n: "03", title: "Facts", body: "Freeze status, review rounds, critical path, rule flags. Counted, never guessed.", kind: "deterministic" },
  { n: "04", title: "Forecast", body: "Monte Carlo odds per feature, shown as ranges next to the base rate.", kind: "deterministic" },
  { n: "05", title: "Explain", body: "Agents turn facts into risk notes and a VP summary, one claim at a time.", kind: "ai" },
  { n: "06", title: "Verify", body: "Each claim is checked against the database. Wrong or unsupported claims are removed and counted.", kind: "deterministic" },
  { n: "07", title: "Approve", body: "A TPM edits and approves. The platform never sends anything on its own.", kind: "human" },
];

export const STEP_TAG: Record<StepKind, { text: string; tone: string }> = {
  deterministic: { text: "Deterministic", tone: "bg-slate-100 text-slate-700" },
  ai: { text: "AI, then fact-checked", tone: "bg-violet-50 text-violet-700" },
  human: { text: "Human", tone: "bg-healthy-bg text-healthy" },
};

/** What each connected team plugs in. The card is Live only when GET /portfolio serves the project. */
export const TEAM_SOURCES: { project: string; name: string; body: string }[] = [
  { project: "kubernetes", name: "Kubernetes", body: "GitHub enhancement issues (KEPs) + kubernetes/kubernetes PRs" },
  { project: "kafka", name: "Apache Kafka", body: "Jira fix versions (New Features, umbrellas, KIPs) + apache/kafka PRs" },
  { project: "tpm-intelligence", name: "Program Intelligence Platform", body: "Tracks its own development: GitHub issues and the PRs that close them, delivered by GitHub webhooks in seconds" },
];

export type TeamCard = { name: string; body: string; live: boolean; href: string | null };

/** Team cards: the API's display name and Live state for connected teams, then "Your team". */
export function teamCards(programs: { project: string; release: string; display_name: string }[], path: (project: string, release: string) => string): TeamCard[] {
  const cards = TEAM_SOURCES.map((t) => {
    const p = programs.find((x) => x.project.toLowerCase() === t.project);
    return { name: p?.display_name ?? t.name, body: t.body, live: Boolean(p), href: p ? path(p.project, p.release) : null };
  });
  return [...cards, { name: "Your team", body: "Copy a connector file: where the plan lives, where the code lives, the release calendar", live: false, href: "/connect" }];
}
