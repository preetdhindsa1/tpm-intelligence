// Stops for the #6395 time machine. Dates come from the feature timeline, never from this file.
export type TimelineStop = { at: string; kind: string; ref: string | null };

const STORY = new Set([
  "opted_in",
  "tracked",
  "untracked",
  "added_to_release",
  "removed_from_release",
  "enhancements_freeze",
  "code_freeze",
  "pr_opened",
  "pr_merged",
  "pr_closed",
]);

export function storyStops(events: TimelineStop[]): TimelineStop[] {
  const seen = new Set<string>();
  const stops: TimelineStop[] = [];
  for (const event of events) {
    if (!STORY.has(event.kind)) continue;
    const key = `${event.at}\0${event.kind}\0${event.ref ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    stops.push(event);
  }
  return stops;
}

// ---- Live Cockpit (UX vision p.4) -------------------------------------------------------
const DAY = 86_400_000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "17 Nov" in UTC. */
export function dayMonth(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

/** Whole days from `from` to `to`, rounded to the nearest day. */
export function daysFrom(from: string, to: string): number {
  return Math.round((new Date(to).getTime() - new Date(from).getTime()) / DAY);
}

const prNum = (ref: string | null) => (ref ? `#${ref.split("#")[1]}` : "");
const list = (refs: string[]) => (refs.length <= 1 ? refs.join("") : `${refs.slice(0, -1).join(", ")} and ${refs[refs.length - 1]}`);

export type KeyStop = {
  key: string;
  at: string;
  label: string;
  tone: "normal" | "critical";
  /** "As of 2 Nov · 15 days to Code Freeze" */
  when: string;
  headline: string;
  /** What the data said on that day: only events at or before `at`. */
  knew: string;
  why: string;
};

type Ev = { at: string; kind: string; ref: string | null };
type Pr = { key: string; is_main: boolean; created_at: string; merged_at: string | null };

/**
 * The eight moments of a feature's release story, from its real timeline: opted in, tracked,
 * Enhancements Freeze, main PR opened, supporting PRs merged, removed at Code Freeze, main PR
 * merged, re-added. A moment the data does not have is left out.
 */
export function keyStops(timeline: Ev[], prs: Pr[], teams: string[]): KeyStop[] {
  const ev = [...timeline].sort((a, b) => a.at.localeCompare(b.at));
  const freeze = ev.find((e) => e.kind === "code_freeze")?.at ?? null;
  const main = prs.find((p) => p.is_main) ?? null;
  const mainRef = main?.key ?? null;
  const when = (at: string) => {
    if (!freeze) return `As of ${dayMonth(at)}`;
    const d = daysFrom(at, freeze);
    if (d > 0) return `As of ${dayMonth(at)} · ${d} day${d === 1 ? "" : "s"} to Code Freeze`;
    if (d === 0) return `As of ${dayMonth(at)} · Code Freeze day`;
    return `As of ${dayMonth(at)} · ${-d} day${d === -1 ? "" : "s"} after Code Freeze`;
  };
  const mergedBy = (at: string, exceptMain = true) =>
    ev.filter((e) => e.kind === "pr_merged" && e.at <= at && (!exceptMain || e.ref !== mainRef)).map((e) => prNum(e.ref));
  const openedBy = (at: string) => ev.filter((e) => e.kind === "pr_opened" && e.at <= at).length;
  const sig = teams.map((t) => t.replace(/^sig\//, "SIG ").replace(/\b\w/g, (c) => c.toUpperCase()));
  const out: KeyStop[] = [];
  const push = (s: Omit<KeyStop, "when">) => out.push({ ...s, when: when(s.at) });

  const opted = ev.find((e) => e.kind === "opted_in");
  if (opted) push({ key: "opted", at: opted.at, label: "Opted in", tone: "normal", headline: "Opted in",
    knew: `The feature is opted in to the release${sig.length ? ` by ${list(sig)}` : ""}. ${openedBy(opted.at) ? `${openedBy(opted.at)} pull requests so far.` : "No pull request yet."}`,
    why: "Scope is set here. From now on the platform watches for the work that will deliver it." });

  const tracked = ev.find((e) => e.kind === "tracked" && (!freeze || e.at < freeze));
  if (tracked) push({ key: "tracked", at: tracked.at, label: "Tracked", tone: "normal", headline: "Tracked by the release team",
    knew: `The release team tracks it. ${openedBy(tracked.at) ? `${openedBy(tracked.at)} pull requests so far.` : "No pull request yet."}`,
    why: "It now counts toward the release's odds and flags." });

  const ef = ev.find((e) => e.kind === "enhancements_freeze");
  if (ef) push({ key: "ef", at: ef.at, label: "Enhancements Freeze", tone: "normal", headline: "Enhancements Freeze passes",
    knew: `The feature is still in the release at Enhancements Freeze. ${openedBy(ef.at) ? `${openedBy(ef.at)} pull requests so far.` : "No pull request yet."}`,
    why: "The design is locked; what is left is code and review." });

  const mainOpen = mainRef ? ev.find((e) => e.kind === "pr_opened" && e.ref === mainRef) : undefined;
  if (mainOpen) {
    const merged = mergedBy(mainOpen.at);
    const d = freeze ? daysFrom(mainOpen.at, freeze) : null;
    push({ key: "main-open", at: mainOpen.at, label: "Main PR opened", tone: "normal", headline: "Main PR opened",
      knew: `The main implementation, PR ${prNum(mainRef)}, opens${d !== null && d > 0 ? ` ${d} days before Code Freeze` : ""}. ${merged.length ? `${merged.length === 1 ? "One supporting PR" : `${merged.length} supporting PRs`}, ${list(merged)}, merged so far.` : "No supporting PR has merged yet."}`,
      why: `This is the moment to act: add a reviewer${sig.length ? ` from ${sig[sig.length - 1]}` : ""}, or cut scope, while there is still time.` });
  }

  const support = ev.filter((e) => e.kind === "pr_merged" && e.ref !== mainRef && (!freeze || e.at < freeze) && (!mainOpen || e.at > mainOpen.at));
  const lastSupport = support[support.length - 1];
  if (lastSupport) push({ key: "support", at: lastSupport.at, label: "Support PRs merge", tone: "normal", headline: "Supporting PRs merge",
    knew: `Supporting PR${support.length === 1 ? "" : "s"} ${list(support.map((e) => prNum(e.ref)))} merge${support.length === 1 ? "s" : ""}.${mainRef ? ` The main PR ${prNum(mainRef)} is still open.` : ""}`,
    why: "The supporting work is done; review of the main PR is now the critical path." });

  const removed = freeze ? ev.find((e) => e.kind === "removed_from_release" && e.at >= freeze) : undefined;
  if (removed && freeze) {
    const mins = Math.round((new Date(removed.at).getTime() - new Date(freeze).getTime()) / 60000);
    push({ key: "removed", at: removed.at, label: "Removed at freeze", tone: "critical", headline: "Removed at Code Freeze",
      knew: `Code Freeze passes with${mainRef ? ` the main PR ${prNum(mainRef)}` : " the work"} still open. The feature is removed from the release ${mins < 60 ? `${mins} minutes` : `${Math.round(mins / 60)} hours`} later.`,
      why: "The flag fired at the freeze. The same facts were visible weeks earlier, when the call could still be made on time." });
  }

  const mainMerge = mainRef ? ev.find((e) => e.kind === "pr_merged" && e.ref === mainRef) : undefined;
  if (mainMerge) {
    const late = freeze ? daysFrom(freeze, mainMerge.at) : null;
    push({ key: "main-merge", at: mainMerge.at, label: "Main PR merges", tone: "normal", headline: "Main PR merges",
      knew: `The main PR ${prNum(mainRef)} merges${late !== null && late > 0 ? ` ${late} day${late === 1 ? "" : "s"} after Code Freeze` : ""}.`,
      why: "The code was days late, not missing: a review-capacity problem more than a scope problem." });
  }

  const readded = removed ? ev.find((e) => e.kind === "added_to_release" && e.at > removed.at) : undefined;
  if (readded) push({ key: "readded", at: readded.at, label: "Re-added", tone: "normal", headline: "Re-added by exception",
    knew: "The feature is added back to the release by exception after its main PR merged.",
    why: "Late code can still ship. The platform records both the slip and the recovery." });

  return out;
}

export type LifeStep = { name: string; note: string; fill: number; here: boolean };

/** The lifecycle card: each stage's date line and how much of it has passed as of `asOf`.
 * Verify starts on the team's code-freeze date, named by `freezeLabel` (ADR-0025 addendum). */
export function lifecycle(
  d: { cycle_start_at: string | null; enhancements_freeze_at: string | null; code_freeze_at: string | null; release_at: string | null },
  asOf: string,
  stage: string,
  freezeLabel = "Code Freeze",
): LifeStep[] {
  const t = (s: string | null) => (s ? new Date(s).getTime() : NaN);
  const now = new Date(asOf).getTime();
  const LAUNCH = 7 * DAY;
  const spans: [string, number, number, string][] = [
    ["Plan", t(d.cycle_start_at) - 30 * DAY, t(d.cycle_start_at), d.cycle_start_at ? `Cycle start ${dayMonth(d.cycle_start_at)}` : "Cycle start not known"],
    ["Build", t(d.cycle_start_at), t(d.code_freeze_at), d.enhancements_freeze_at ? `Enhancements Freeze ${dayMonth(d.enhancements_freeze_at)}` : "Building"],
    ["Verify", t(d.code_freeze_at), t(d.release_at), d.code_freeze_at ? `${freezeLabel} ${dayMonth(d.code_freeze_at)}, ${new Date(d.code_freeze_at).toISOString().slice(11, 16)} UTC` : `${freezeLabel} not known`],
    ["Launch", t(d.release_at), t(d.release_at) + LAUNCH, d.release_at ? `Release ${dayMonth(d.release_at)}${now < t(d.release_at) ? ` · in ${daysFrom(asOf, d.release_at)} days` : ""}` : "Release not known"],
    ["Learn", t(d.release_at) + LAUNCH, t(d.release_at) + 60 * DAY, "Retro after release"],
  ];
  return spans.map(([name, a, b, note]) => {
    const fill = Number.isNaN(a) || Number.isNaN(b) ? 0 : Math.max(0, Math.min(1, (now - a) / (b - a)));
    return { name, note, fill, here: name === stage };
  });
}

type SimCheckLite = { name: string; real: number | null; simulated: number | null; passed: boolean };
type SimValidationLite = { passed: boolean; tolerance?: number; reason?: string; releases: { release: string; passed: boolean; checks: SimCheckLite[] }[] };

const short = (name: string) => name.replace(/^median /, "").replace(/ \(days\)$/, "");
const days = (v: number | null) => (v === null ? "not measured" : `${v.toFixed(2)} days`);

/**
 * One sentence on the simulator's replay check, from the validation the API stores. Prefers
 * the given release's replay, else the newest one.
 */
export function simValidationText(v: SimValidationLite | null | undefined, releaseKey: string): string | null {
  if (!v) return null;
  const tol = v.tolerance != null ? `±${Math.round(v.tolerance * 100)}%` : "the allowed range";
  const replay = v.releases.find((r) => r.release === releaseKey) ?? v.releases[v.releases.length - 1];
  if (!replay) return v.passed ? null : (v.reason ?? "The simulator has not been validated.");
  const name = replay.release.split(":").pop();
  const parts = replay.checks.map((c) => `${short(c.name)} ${days(c.simulated)} vs ${c.real === null ? "not measured" : c.real.toFixed(2)} real (${c.passed ? "passes" : `fails ${tol}`})`);
  return `Replay of ${name}: simulated ${parts.join("; ")}.`;
}
