import { describe, expect, it } from "vitest";
import { refLabel, removedSummary } from "../lib/format";

describe("refLabel", () => {
  it("links PR facts to GitHub", () => {
    expect(refLabel("pr:kubernetes/kubernetes#143709::merged_at")).toEqual({
      label: "PR #143709 · merged at",
      href: "https://github.com/kubernetes/kubernetes/pull/143709",
    });
  });
  it("labels feature flags and SIG load", () => {
    expect(refLabel("feature:kubernetes/enhancements#6395::flag.late_main_pr").label).toBe("#6395 · late main PR");
    expect(refLabel("sig:sig/node::unlinked_open_prs").label).toBe("sig/node · unlinked open prs");
  });
});

describe("removedSummary", () => {
  it("says when nothing was removed", () => {
    expect(removedSummary(0, {})).toBe("No claims were removed by the fact checker.");
  });
  it("lists removal reasons", () => {
    expect(removedSummary(2, { wrong_value: 1, no_supporting_data: 1 })).toBe(
      "2 claims removed by the fact checker (1 wrong value, 1 no supporting data).",
    );
  });
});
