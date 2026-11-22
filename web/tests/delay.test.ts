import { describe, expect, it } from "vitest";
import type { MergeDates } from "@/lib/api";
import { dateOf, delayRows, expectedOn, likelyLate, mergeRangeLabel, relDay } from "@/lib/delay";

const M: MergeDates = {
  release: "kubernetes:v1.38",
  as_of: "2026-11-22T00:00:00Z",
  code_freeze_at: "2026-11-17T12:00:00Z",
  release_at: "2026-12-16T00:00:00Z",
  as_of_day: 4.5,
  release_day: 28.5,
  features: 3,
  done_now: 1,
  forecast: [
    [4, 1, 1, 1],
    [5, 1.4, 1, 2],
    [6, 2.1, 1, 3],
  ],
  actual: [
    [3, 1],
    [4, 1],
  ],
  items: [
    { key: "a", number: 6395, title: "A", status: "done", done_day: 3.48, p10: null, p50: null, p90: null, by_release: null },
    { key: "b", number: 5419, title: "B", status: "forecast", done_day: null, p10: 4.8, p50: 5.2, p90: 9, by_release: 0.95 },
    { key: "c", number: 2570, title: "C", status: "forecast", done_day: null, p10: 6, p50: null, p90: null, by_release: 0.3 },
  ],
  validation: { validated: false },
  note: "",
};

describe("days-of-delay helpers", () => {
  it("labels days relative to Code Freeze and as dates", () => {
    expect(relDay(0)).toBe("Code Freeze");
    expect(relDay(4)).toBe("freeze +4 d");
    expect(relDay(-3)).toBe("freeze −3 d");
    expect(dateOf(4, M.code_freeze_at)).toBe("Nov 21");
  });

  it("joins actual counts and the forecast band by day", () => {
    expect(delayRows(M)).toEqual([
      { day: 3, actual: 1 },
      { day: 4, actual: 1, expected: 1, band: [1, 1] },
      { day: 5, expected: 1.4, band: [1, 2] },
      { day: 6, expected: 2.1, band: [1, 3] },
    ]);
  });

  it("starts the chart 28 days before Code Freeze", () => {
    const early: MergeDates = { ...M, actual: [[-200, 3], [-28, 5], [3, 6]] };
    expect(delayRows(early).map((r) => r.day)).toEqual([-28, 3, 4, 5, 6]);
  });

  it("lists features expected on a day and the likeliest to be late", () => {
    expect(expectedOn(M.items, 5).map((f) => f.number)).toEqual([5419]);
    expect(likelyLate(M.items).map((f) => f.number)).toEqual([2570, 5419]);
  });

  it("describes a range honestly when it runs past the chart", () => {
    expect(mergeRangeLabel(4.8, 5.2, 9)).toBe("median freeze +5 d, likely freeze +5 d to freeze +9 d");
    expect(mergeRangeLabel(6, null, null)).toBe("median after the chart ends (or never)");
  });
});
