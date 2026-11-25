import { describe, expect, it } from "vitest";
import { scenarioNotes } from "./studio";

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
