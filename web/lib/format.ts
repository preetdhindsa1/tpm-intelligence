// Pure display helpers. Wording follows CLAUDE.md: ranges, never certainties.
import type { Flag, Odds, SimRange } from "./api";

const pct = (x: number) => `${Math.round(x * 100)}%`;

export type OddsDisplay = { headline: string; detail: string; tone: "good" | "watch" | "risk" | "none"; validated: boolean };

export function oddsDisplay(odds: Odds): OddsDisplay {
  if (odds.status === "after_freeze") return { headline: "Freeze passed", detail: "Outcome is known; see flags", tone: "none", validated: odds.validated };
  if (odds.status === "not_in_release") return { headline: "—", detail: "Not in the release", tone: "none", validated: odds.validated };
  if (odds.status === "no_freeze_date")
    return { headline: "—", detail: "No Code Freeze date, so no odds", tone: "none", validated: odds.validated };
  if (odds.status === "insufficient_history")
    return { headline: "—", detail: "Not enough history to forecast: no earlier release to measure", tone: "none", validated: odds.validated };
  if (odds.status !== "forecast" || odds.probability === null || odds.low === null || odds.high === null) {
    return { headline: "—", detail: "No forecast", tone: "none", validated: odds.validated };
  }
  const tone = odds.probability >= 0.7 ? "good" : odds.probability >= 0.4 ? "watch" : "risk";
  const range = `likely ${pct(odds.low)}–${pct(odds.high)}`;
  const base = odds.base_rate !== null ? `; base rate ${pct(odds.base_rate)}` : "";
  return {
    headline: pct(odds.probability),
    detail: odds.validated ? range : `${range}${base}; not validated`,
    tone,
    validated: odds.validated,
  };
}

const SEVERITY_ORDER: Record<Flag["severity"], number> = { critical: 0, warning: 1, info: 2 };

export function sortFlags(flags: Flag[]): Flag[] {
  return [...flags].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] || a.code.localeCompare(b.code));
}

export const TIMELINE_LABELS: Record<string, string> = {
  opted_in: "Opted in",
  added_to_release: "Added to release",
  removed_from_release: "Removed from release",
  tracked: "Tracked",
  untracked: "Untracked",
  pr_opened: "PR opened",
  pr_merged: "PR merged",
  pr_closed: "PR closed (not merged)",
  enhancements_freeze: "Enhancements Freeze",
  code_freeze: "Code Freeze",
  release: "Release",
};

export function timelineLabel(kind: string): string {
  return TIMELINE_LABELS[kind] ?? kind.replaceAll("_", " ");
}

export function formatUtc(iso: string): string {
  return new Date(iso).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

/** A short, human label and optional link for a fact key a claim cites. */
export function refLabel(ref: string): { label: string; href?: string } {
  const [subject, field = ""] = ref.split("::");
  const prMatch = subject.match(/^pr:(.+)#(\d+)$/);
  if (prMatch) {
    return { label: `PR #${prMatch[2]} · ${field.replaceAll("_", " ")}`, href: `https://github.com/${prMatch[1]}/pull/${prMatch[2]}` };
  }
  if (subject.startsWith("feature:")) {
    // "feature:kubernetes/enhancements#5419::flag.main_pr_not_merged.message" → "#5419 · main PR not merged"
    const id = subject.slice(8).match(/#\d+$/)?.[0] ?? subject.slice(8);
    const [kind, name = "", detail = ""] = field.split(".");
    const words = (x: string) => x.replaceAll("_", " ").replace(/\bpr\b/g, "PR").replace(/\bci\b/g, "CI");
    const what =
      kind === "flag" ? `${words(name)}${detail && detail !== "message" && detail !== "severity" ? `: ${words(detail)}` : ""}`
      : kind === "ask" ? `ask: ${words(name)}`
      : words(field);
    return { label: `${id} · ${what}` };
  }
  if (subject === "release") return { label: `release · ${field.replaceAll("_", " ")}` };
  if (subject.startsWith("sig:")) return { label: `${subject.slice(4)} · ${field.replaceAll("_", " ")}` };
  return { label: field.replaceAll("_", " ") };
}

/** One chip per distinct label, in order (a flag's message and severity read the same). */
export function refChips(refs: string[]): { ref: string; label: string; href?: string }[] {
  const seen = new Set<string>();
  return refs.map((ref) => ({ ref, ...refLabel(ref) })).filter((c) => !seen.has(c.label) && (seen.add(c.label), true));
}

/** One line under the claims: what the fact checker removed. */
export function removedSummary(removed: number, byReason: Record<string, number>): string {
  if (removed === 0) return "No claims were removed by the fact checker.";
  const parts = Object.entries(byReason).map(([reason, n]) => `${n} ${reason.replaceAll("_", " ")}`);
  return `${removed} claim${removed === 1 ? "" : "s"} removed by the fact checker (${parts.join(", ")}).`;
}

/** "104 waiting · 3 confirmed · 1 rejected · 1,636 no match · 11 dropped by checks". */
export function suggestionCounts(counts: Record<string, number>): string {
  const parts: [string, string][] = [
    ["suggested", "waiting"],
    ["confirmed", "confirmed"],
    ["rejected", "rejected"],
    ["none", "no match"],
    ["dropped", "dropped by checks"],
  ];
  return parts
    .filter(([k]) => (counts[k] ?? 0) > 0)
    .map(([k, label]) => `${(counts[k] ?? 0).toLocaleString("en-US")} ${label}`)
    .join(" · ");
}

/** A duration in days: minutes under an hour, hours under a day ("29 min", "9 h", "1.6 d"). */
export function daysLabel(d: number): string {
  if (d * 24 < 1) return `${Math.round(d * 24 * 60)} min`;
  if (d < 1) return `${Math.round(d * 24)} h`;
  return `${d.toFixed(1)} d`;
}

/** "9 h (8–11 h)" for waits, "626 (601–639)" for counts. */
export function rangeLabel(r: SimRange | null, kind: "days" | "count"): string {
  if (!r) return "—";
  if (kind === "count") return `${Math.round(r.median)} (${Math.round(r.low)}–${Math.round(r.high)})`;
  return `${daysLabel(r.median)} (${daysLabel(r.low)}–${daysLabel(r.high)})`;
}

export type SimDelta = { text: string; tone: "better" | "worse" | "same"; overlaps: boolean };

/** Scenario minus baseline on the medians. ``overlaps``: the two ranges overlap, so the
 *  difference may be noise. */
export function simDelta(
  base: SimRange | null,
  scen: SimRange | null,
  kind: "days" | "count",
  lowerIsBetter: boolean,
): SimDelta | null {
  if (!base || !scen) return null;
  const diff = scen.median - base.median;
  const overlaps = scen.low <= base.high && base.low <= scen.high;
  const small = kind === "days" ? Math.abs(diff) * 24 < 0.5 : Math.abs(diff) < 0.5;
  if (small) return { text: "no change", tone: "same", overlaps: true };
  const sign = diff > 0 ? "+" : "−";
  const abs = Math.abs(diff);
  const text = kind === "days" ? `${sign}${daysLabel(abs)}` : `${sign}${Math.round(abs)}`;
  const better = lowerIsBetter ? diff < 0 : diff > 0;
  return { text, tone: better ? "better" : "worse", overlaps };
}

/** "+205%" for a validation error. */
export function errorPct(e: number | null): string {
  if (e === null) return "—";
  return `${e > 0 ? "+" : "−"}${Math.round(Math.abs(e) * 100)}%`;
}
