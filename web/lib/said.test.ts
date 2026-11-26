import { describe, expect, it } from "vitest";
import type { SaidRow } from "./api-readiness";
import { byMeetingDate } from "./said";

function row(date: string): SaidRow {
  return { date, said: [], showed: [] };
}

describe("said versus showed order", () => {
  it("sorts meetings by date and leaves the input alone", () => {
    const later = row("2026-11-17T12:00:00Z");
    const early = row("2026-11-01T12:00:00Z");
    const rows = [later, early];
    expect(byMeetingDate(rows).map((r) => r.date)).toEqual([early.date, later.date]);
    expect(rows.map((r) => r.date)).toEqual([later.date, early.date]);
  });
});
