import { describe, expect, it } from "vitest";
import { daysLabel, errorPct, rangeLabel, simDelta } from "../lib/format";

describe("simulator formatting", () => {
  it("shows waits under a day in hours", () => {
    expect(daysLabel(0.375)).toBe("9 h");
    expect(daysLabel(1.56)).toBe("1.6 d");
  });
  it("always shows a range", () => {
    expect(rangeLabel({ median: 0.388, low: 0.362, high: 0.463 }, "days")).toBe("9 h (9 h–11 h)");
    expect(rangeLabel({ median: 626, low: 600.7, high: 639.4 }, "count")).toBe("626 (601–639)");
    expect(rangeLabel(null, "count")).toBe("—");
  });
  it("marks a longer wait as worse and flags overlapping ranges", () => {
    const d = simDelta({ median: 0.4, low: 0.35, high: 0.45 }, { median: 0.6, low: 0.5, high: 0.7 }, "days", true);
    expect(d).toEqual({ text: "+5 h", tone: "worse", overlaps: false });
    const m = simDelta({ median: 600, low: 580, high: 620 }, { median: 610, low: 590, high: 630 }, "count", false);
    expect(m).toEqual({ text: "+10", tone: "better", overlaps: true });
  });
  it("calls a tiny difference no change", () => {
    expect(simDelta({ median: 0.4, low: 0.3, high: 0.5 }, { median: 0.41, low: 0.3, high: 0.5 }, "days", true)?.tone).toBe("same");
  });
  it("formats validation errors", () => {
    expect(errorPct(2.048)).toBe("+205%");
    expect(errorPct(-0.124)).toBe("−12%");
  });
});
