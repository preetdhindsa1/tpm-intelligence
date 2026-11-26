import { describe, expect, it } from "vitest";
import type { RetroTotals } from "./api-readiness";
import { NOT_COMPUTED, NO_WARNING, isMissingRetro, slipLabel, suppressedText, totalLines, warningLine } from "./retro";

const totals: RetroTotals = { slips: 2, warned: 1, average_lead_time_days: 12, median_lead_time_days: 12 };

describe("retro wording", () => {
  it("treats a 404 as a retro that has not been computed", () => {
    expect(isMissingRetro(404)).toBe(true);
    expect(isMissingRetro(500)).toBe(false);
    expect(NOT_COMPUTED).toBe("Retro not computed yet for this release");
  });

  it("shows planned and warned-and-landed only when the API sends them", () => {
    expect(totalLines(totals).map((line) => line.label)).toEqual(["Slipped", "Warned"]);
    const live = totalLines({ ...totals, planned: 98, warned_landed: 47 });
    expect(live.map((line) => `${line.label} ${line.value}`)).toEqual([
      "Planned 98",
      "Slipped 2",
      "Warned 1",
      "Warned and landed 47",
    ]);
  });

  it("names a move, a drop, a late exception, and a slip with no warning", () => {
    expect(slipLabel("moved", "v1.38")).toBe("Moved to v1.38");
    expect(slipLabel("dropped", null)).toBe("Dropped");
    expect(slipLabel("late_exception", null)).toBe("Late exception");
    expect(warningLine({ first_warning_at: null, first_warning_flag: null, lead_time_days: null })).toBe(NO_WARNING);
    expect(warningLine({ first_warning_at: "2026-11-05T12:00:00Z", first_warning_flag: "late_main_pr", lead_time_days: 12 })).toBe(
      "First warning 2026-11-05 (late main pr, 12 days of lead time)",
    );
  });

  it("says how many groups are too small to show", () => {
    expect(suppressedText(0)).toBeNull();
    expect(suppressedText(4)).toBe("4 groups too small to show");
  });
});
