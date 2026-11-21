import { describe, expect, it } from "vitest";
import type { Odds } from "../lib/api";
import { formatUtc, oddsDisplay, sortFlags, timelineLabel } from "../lib/format";

const odds = (over: Partial<Odds>): Odds => ({
  status: "forecast", validated: false, base_rate: 0.75, raw_probability: 0.3,
  probability: 0.38, low: 0.3, high: 0.46, open_prs: [], pr_on_time: {}, new_pr_needed: null, ...over,
});

describe("oddsDisplay", () => {
  it("shows a range and labels unvalidated odds with the base rate", () => {
    const d = oddsDisplay(odds({}));
    expect(d.headline).toBe("38%");
    expect(d.detail).toBe("likely 30%–46%; base rate 75%; not validated");
    expect(d.tone).toBe("risk");
  });
  it("omits the caveat once validated", () => {
    expect(oddsDisplay(odds({ validated: true, probability: 0.8, low: 0.7, high: 0.9 })).detail).toBe("likely 70%–90%");
  });
  it("never shows a number after freeze", () => {
    expect(oddsDisplay(odds({ status: "after_freeze", probability: null })).headline).toBe("Freeze passed");
  });
});

it("sorts flags by severity", () => {
  const flags = sortFlags([
    { code: "b", severity: "info", message: "", facts: {} },
    { code: "a", severity: "critical", message: "", facts: {} },
  ]);
  expect(flags.map((f) => f.code)).toEqual(["a", "b"]);
});

it("labels timeline kinds and formats UTC", () => {
  expect(timelineLabel("removed_from_release")).toBe("Removed from release");
  expect(formatUtc("2026-11-17T12:05:57Z")).toBe("2026-11-17 12:05 UTC");
});
