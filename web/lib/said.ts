// Order the said-versus-showed rows. The API owns the items and the facts.
// Showed is a release-wide count for that day, so this does not compare a risk
// with a platform warning.
import type { SaidRow } from "@/lib/api-readiness";

export function byMeetingDate(rows: SaidRow[]): SaidRow[] {
  return [...rows].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}
