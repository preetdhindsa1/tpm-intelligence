import { describe, expect, it } from "vitest";
import { refChips, refLabel } from "./format";

describe("refLabel", () => {
  it("names the feature and the fact in words", () => {
    expect(refLabel("feature:kubernetes/enhancements#5419::flag.main_pr_not_merged.message").label).toBe("#5419 · main PR not merged");
    expect(refLabel("feature:kubernetes/enhancements#5554::flag.ci_failing.failing_checks").label).toBe("#5554 · CI failing: failing checks");
    expect(refLabel("feature:kubernetes/enhancements#5419::title").label).toBe("#5419 · title");
    expect(refLabel("feature:kubernetes/enhancements#5419::ask.confirm_exception_or_remove").label).toBe("#5419 · ask: confirm exception or remove");
    expect(refLabel("feature:KAFKA-19992::title").label).toBe("KAFKA-19992 · title");
    expect(refLabel("release::code_freeze_at").label).toBe("release · code freeze at");
  });

  it("links PRs to GitHub", () => {
    expect(refLabel("pr:kubernetes/kubernetes#143709::merged_at")).toEqual({
      label: "PR #143709 · merged at",
      href: "https://github.com/kubernetes/kubernetes/pull/143709",
    });
  });
});

describe("refChips", () => {
  it("shows a flag once even when the claim cites its message and severity", () => {
    const chips = refChips([
      "feature:kubernetes/enhancements#5419::flag.main_pr_not_merged.message",
      "feature:kubernetes/enhancements#5419::flag.main_pr_not_merged.severity",
      "feature:kubernetes/enhancements#5419::title",
    ]);
    expect(chips.map((c) => c.label)).toEqual(["#5419 · main PR not merged", "#5419 · title"]);
  });
});
