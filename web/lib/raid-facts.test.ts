import { describe, expect, it } from "vitest";
import type { RaidSummary } from "./api-raid";
import { NO_MEETING_NOTES, openRisks, raidFacts } from "./raid-facts";

const summary: RaidSummary = {
  project: "kubernetes", release: "v1.38", as_of: "2026-11-25T21:00:00Z", synthetic: true,
  by_type: [
    { type: "risk", suggested: 2, open: 1, in_progress: 4, closed: 0, superseded: 0, rejected: 0 },
    { type: "action", suggested: 0, open: 7, in_progress: 0, closed: 1, superseded: 0, rejected: 0 },
  ],
  risks_without_owner: 0,
  waiting_for_review: 2,
  sources: 1,
};

describe("RAID cockpit facts", () => {
  it("counts open risks only, and shows the summary's other two counts", () => {
    expect(openRisks(summary)).toBe(1);
    expect(raidFacts(summary)).toEqual([
      { label: "Open risks", count: 1 },
      { label: "Risks without an owner", count: 0 },
      { label: "Waiting for review", count: 2 },
    ]);
  });

  it("does not show zero counts when no meeting notes are connected", () => {
    expect(raidFacts({ ...summary, sources: 0, risks_without_owner: 0, waiting_for_review: 0 })).toBeNull();
    expect(NO_MEETING_NOTES).toBe("No meeting notes are connected for this release");
  });
});
