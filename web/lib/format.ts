// Pure display helpers. Wording follows CLAUDE.md: ranges, never certainties.
import type { Flag, Odds } from "./api";

const pct = (x: number) => `${Math.round(x * 100)}%`;

export type OddsDisplay = { headline: string; detail: string; tone: "good" | "watch" | "risk" | "none"; validated: boolean };

export function oddsDisplay(odds: Odds): OddsDisplay {
  if (odds.status === "after_freeze") return { headline: "Freeze passed", detail: "Outcome is known; see flags", tone: "none", validated: odds.validated };
  if (odds.status === "not_in_release") return { headline: "—", detail: "Not in the release", tone: "none", validated: odds.validated };
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
  if (subject.startsWith("feature:")) return { label: field.replace(/^flag\./, "flag: ").replaceAll("_", " ") };
  if (subject.startsWith("sig:")) return { label: `${subject.slice(4)} · ${field.replaceAll("_", " ")}` };
  return { label: field.replaceAll("_", " ") };
}

/** One line under the claims: what the fact checker removed. */
export function removedSummary(removed: number, byReason: Record<string, number>): string {
  if (removed === 0) return "No claims were removed by the fact checker.";
  const parts = Object.entries(byReason).map(([reason, n]) => `${n} ${reason.replaceAll("_", " ")}`);
  return `${removed} claim${removed === 1 ? "" : "s"} removed by the fact checker (${parts.join(", ")}).`;
}
