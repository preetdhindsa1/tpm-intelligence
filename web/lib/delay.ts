// Pure helpers for the days-of-delay chart (M7). Every number comes from the API.
import type { CurveFeature, MergeDates } from "@/lib/api";

const DAY_MS = 86_400_000;

/** "Code Freeze", "freeze +4 d", "freeze −3 d". */
export function relDay(d: number): string {
  if (d === 0) return "Code Freeze";
  return `freeze ${d > 0 ? "+" : "−"}${Math.abs(d)} d`;
}

/** Calendar date for a day relative to Code Freeze, e.g. "Nov 21". */
export function dateOf(d: number, freezeIso: string | null): string {
  if (!freezeIso) return relDay(d);
  const t = new Date(new Date(freezeIso).getTime() + d * DAY_MS);
  return t.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

export type DelayRow = {
  day: number;
  expected?: number;
  band?: [number, number];
  actual?: number;
};

/** The chart starts this many days before Code Freeze (earlier merges are counted in). */
export const CHART_START = -28;

/** Chart rows: actual count up to today, forecast from today on, from ``start`` on. */
export function delayRows(m: MergeDates, start = CHART_START): DelayRow[] {
  const rows = new Map<number, DelayRow>();
  for (const [day, count] of m.actual) if (day >= start) rows.set(day, { day, actual: count });
  for (const [day, e, lo, hi] of m.forecast) rows.set(day, { ...(rows.get(day) ?? { day }), expected: e, band: [lo, hi] });
  return [...rows.values()].sort((a, b) => a.day - b.day);
}

/** Features whose median merge day falls on ``day`` (open ones only), likeliest first. */
export function expectedOn(items: CurveFeature[], day: number): CurveFeature[] {
  return items.filter((f) => f.status === "forecast" && f.p50 !== null && Math.floor(f.p50) === day);
}

/** Open features whose required code likely misses release day, worst first. */
export function likelyLate(items: CurveFeature[]): CurveFeature[] {
  return items
    .filter((f) => f.status === "forecast" && f.by_release !== null)
    .sort((a, b) => (a.by_release ?? 0) - (b.by_release ?? 0));
}

/** "median freeze +4 d, likely +1 to +12 d" / "not likely within the chart". */
export function mergeRangeLabel(p10: number | null, p50: number | null, p90: number | null): string {
  const f = (x: number | null) => (x === null ? "after the chart ends" : relDay(Math.round(x)));
  if (p50 === null) return "median after the chart ends (or never)";
  return `median ${f(p50)}, likely ${f(p10)} to ${f(p90)}`;
}
