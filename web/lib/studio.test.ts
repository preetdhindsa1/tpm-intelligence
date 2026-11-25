import { describe, expect, it } from "vitest";
import { leverSettings, mergedLine, poolName, poolsByLoad, scenarioNotes, teamHorizon } from "./studio";

const empty = { reviewers: 0, new_reviewers: 0, ramp_weeks: 0, interruption: 0 };

describe("scenarioNotes", () => {
  it("says nothing when the settings are the measured baseline", () => {
    expect(scenarioNotes({ arrival_multiplier: 1, pools: { "sig/node": empty } })).toEqual([]);
  });

  it("lists only the levers that differ from the baseline", () => {
    expect(
      scenarioNotes({
        arrival_multiplier: 2,
        pools: { "sig/node": { ...empty, reviewers: 2, interruption: 0.1 } },
      }),
    ).toEqual(["New PRs ×2.0", "sig/node: experienced reviewers +2", "sig/node: interruptions 10%"]);
  });
});

describe("Decision Studio layout", () => {
  const pool = (name: string, reviewers: number, open: number) => ({
    pool: name, prs_measured: 100, arrivals_per_week: 3.7, reviewers_per_week_source: 1.9, reviewers_now: reviewers, open_prs_now: open,
    first_wait_median_days: 0.24, follow_wait_median_days: 0.72, first_scale: 1, later_scale: 1,
  });

  it("names pools for people, never per person", () => {
    expect(poolName("sig/storage")).toBe("SIG Storage");
    expect(poolName("sig/api-machinery")).toBe("SIG API Machinery");
    expect(poolName("sig/cluster-lifecycle")).toBe("SIG Cluster Lifecycle");
    expect(poolName("other")).toBe("Other pools");
    expect(poolName("other", true)).toBe("All reviewers");
  });

  it("puts the most loaded pool first and the shared pool last", () => {
    const sorted = poolsByLoad([pool("other", 6, 400), pool("sig/node", 21, 188), pool("sig/testing", 1, 16), pool("sig/storage", 3, 26)]);
    expect(sorted.map((p) => p.pool)).toEqual(["sig/testing", "sig/node", "sig/storage", "other"]);
  });

  it("turns one lever into one scenario", () => {
    expect(leverSettings("reviewers", "sig/storage").pools["sig/storage"].reviewers).toBe(1);
    expect(leverSettings("arrival", "sig/storage")).toEqual({ name: "", pools: {}, arrival_multiplier: 2 });
    expect(leverSettings("new_reviewers", "sig/node").pools["sig/node"]).toMatchObject({ new_reviewers: 1, ramp_weeks: 4 });
    expect(leverSettings("interruption", "sig/node").pools["sig/node"].interruption).toBe(0.2);
  });

  it("words merged PRs from the simulator's ranges", () => {
    const o = { pool: "sig/storage", reviewers: 3, review_wait_days: null, merged: { median: 11.4, low: 9, high: 14 }, not_merged: { median: 14.6, low: 12, high: 17 } };
    expect(mergedLine(o, "release day")).toEqual({ big: "11 of 26", line: "PRs merged by release day · range 9–14" });
    expect(mergedLine({ ...o, merged: null }, "release day")).toBeNull();
  });
});

describe("teamHorizon", () => {
  it("uses the team's word for Code Freeze and leaves other horizons alone", () => {
    expect(teamHorizon({ horizon_label: "Code Freeze" }, "Feature Freeze").horizon_label).toBe("Feature Freeze");
    expect(teamHorizon({ horizon_label: "Code Freeze" }).horizon_label).toBe("Code Freeze");
    expect(teamHorizon({ horizon_label: "release day" }, "Feature Freeze").horizon_label).toBe("release day");
  });
});
