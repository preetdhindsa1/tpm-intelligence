import { describe, expect, it } from "vitest";
import { metricValue, ruleValue, stageDetail, stageValue, type PodStage } from "./api-pdlc";

// Shapes and values from the contract example (this repository, 2026-11-25).
const stage = (s: Partial<PodStage> & { stage: string }): PodStage => ({
  rules: "", status: "broken", value: null, reason: null, ...s,
});

describe("pod facts wording", () => {
  it("words each stage from the API values", () => {
    expect(stageValue(stage({ stage: "cross_review", value: { cross_reviewed: 6, agent_merged: 38 } }))).toBe("6 of 38");
    expect(stageValue(stage({ stage: "human_review", value: { human_reviewed: 11, merged: 52 } }))).toBe("11 of 52");
    expect(stageValue(stage({ stage: "merge", status: "held", value: { median_minutes_to_merge: 11 } }))).toBe("11 min median");
    expect(stageValue(stage({ stage: "contract", status: "not_measured" }))).toBe("Not measured");
    const kept = stage({ stage: "kept", status: "not_measured", value: { kept: 0, eligible: 0 },
      reason: "No merged pull request is 30 days old yet (the first is on 2026-12-22)" });
    expect(stageValue(kept)).toBe("TBD");
    expect(stageDetail(kept)).toContain("2026-12-22");
  });

  it("never invents a number when the API has none", () => {
    expect(metricValue({ metric: "open_to_merge", target: "same day", value: null, unit: "minutes",
      reason: "Not enough data yet: fewer than 5 merged pull requests" })).toBe("Not enough data yet: fewer than 5 merged pull requests");
    expect(metricValue({ metric: "human_review_load", target: "60-80%", value: null, unit: "share", reason: null }))
      .toBe("TBD (not yet measured)");
    expect(metricValue({ metric: "three_plus_rounds", target: "below 10%", value: 0.125, unit: "share", reason: null })).toBe("13%");
  });

  it("states rule results with their denominator", () => {
    expect(ruleValue({ rule: "R13", title: "", status: "broken", count: 32, of: 38 })).toBe("32 of 38 break it");
    expect(ruleValue({ rule: "R5", title: "", status: "not_measured", count: null, of: null })).toBe("Not measured yet");
    expect(ruleValue({ rule: "R8", title: "", status: "held", count: 0, of: 12 })).toBe("Held · 0 of 12");
  });
});
