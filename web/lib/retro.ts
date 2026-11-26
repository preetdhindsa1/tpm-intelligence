// Display rules for GET /retro and GET /retro/patterns. Counts stay the API's.
import type { RetroTotals, Slip, SlipKind } from "@/lib/api-readiness";

export const NOT_COMPUTED = "Retro not computed yet for this release";
export const NO_WARNING = "no warning before the slip";

export function isMissingRetro(status: number): boolean {
  return status === 404;
}

export type TotalLine = { label: string; value: number };

/** Optional totals are omitted until the API sends a number. */
export function totalLines(totals: RetroTotals): TotalLine[] {
  const lines: TotalLine[] = [];
  if (typeof totals.planned === "number") lines.push({ label: "Planned", value: totals.planned });
  lines.push({ label: "Slipped", value: totals.slips }, { label: "Warned", value: totals.warned });
  if (typeof totals.warned_landed === "number") lines.push({ label: "Warned and landed", value: totals.warned_landed });
  return lines;
}

export function slipLabel(kind: SlipKind, movedTo: string | null): string {
  if (kind === "dropped") return "Dropped";
  if (kind === "late_exception") return "Late exception";
  return movedTo ? `Moved to ${movedTo}` : "Moved";
}

export function warningLine(slip: Pick<Slip, "first_warning_at" | "first_warning_flag" | "lead_time_days">): string {
  if (!slip.first_warning_at) return NO_WARNING;
  const flag = slip.first_warning_flag ? slip.first_warning_flag.replaceAll("_", " ") : "a flag";
  const lead = slip.lead_time_days === null ? "" : `, ${slip.lead_time_days} days of lead time`;
  return `First warning ${slip.first_warning_at.slice(0, 10)} (${flag}${lead})`;
}

/** Null when every group is large enough to show. */
export function suppressedText(count: number): string | null {
  if (count <= 0) return null;
  return count === 1 ? "1 group too small to show" : `${count} groups too small to show`;
}
