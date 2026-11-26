// When a meeting raised a risk, compared with the days the platform showed a warning.
// The API sends the items and the facts. This only classifies them.
import { replayDay, type SaidItem, type SaidRow } from "@/lib/api-readiness";

export type RiskWhen = "before" | "after" | "never";

const WARNINGS = new Set(["features_at_risk", "critical_flags"]);

function showedWarning(row: SaidRow): boolean {
  return row.showed.some((fact) => WARNINGS.has(fact.name) && typeof fact.value === "number" && fact.value > 0);
}

/** The earliest replay day the API named, or null when none was sent. */
export function firstReplay(rows: SaidRow[]): string | null {
  const days = rows.map(replayDay).filter((day): day is string => day !== null).sort();
  return days[0] ?? null;
}

/**
 * Before: the meeting is earlier than the first replay day, and a later day shows a warning.
 * After: the platform already had a replay day on or before the meeting, and showed a warning.
 * Never: no day shows features at risk or a critical flag.
 * Other RAID types are not highlighted.
 */
export function riskWhen(rows: SaidRow[], row: SaidRow, item: SaidItem): RiskWhen | null {
  if (item.type !== "risk") return null;
  if (!rows.some(showedWarning)) return "never";
  const first = firstReplay(rows);
  const meeting = row.date.slice(0, 10);
  if (first && meeting < first) return "before";
  return "after";
}

export function riskWhenLabel(when: RiskWhen): string {
  if (when === "before") return "Raised before the platform";
  if (when === "after") return "Raised after the platform";
  return "The platform never showed it";
}

export function byMeetingDate(rows: SaidRow[]): SaidRow[] {
  return [...rows].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}
