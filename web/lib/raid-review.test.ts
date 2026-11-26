import { describe, expect, it } from "vitest";
import type { RaidSummary } from "./api-raid";
import { keyAction, linkLine, moveIndex, ownerText, progressText, reasonError, reviewedCount, typingTarget } from "./raid-review";

const summary: RaidSummary = {
  project: "kubernetes", release: "v1.38", as_of: "2026-11-25T21:00:00Z", synthetic: true,
  by_type: [
    { type: "risk", suggested: 2, open: 1, in_progress: 0, closed: 0, superseded: 0, rejected: 0 },
    { type: "action", suggested: 0, open: 0, in_progress: 0, closed: 1, superseded: 0, rejected: 0 },
    { type: "question", suggested: 0, open: 0, in_progress: 0, closed: 0, superseded: 0, rejected: 1 },
  ],
  risks_without_owner: 0, waiting_for_review: 2, sources: 1,
};

describe("RAID review queue", () => {
  it("counts reviewed items and words the progress", () => {
    expect(reviewedCount(summary)).toBe(3);
    expect(progressText(4, 19)).toBe("4 of 23 reviewed");
    expect(progressText(reviewedCount(summary), summary.waiting_for_review)).toBe("3 of 5 reviewed");
  });

  it("moves with j and k and maps the action keys", () => {
    expect(moveIndex(0, -1, 3)).toBe(0);
    expect(moveIndex(1, 1, 3)).toBe(2);
    expect(moveIndex(0, 1, 0)).toBe(0);
    expect(keyAction("j")).toBe("next");
    expect(keyAction("k")).toBe("prev");
    expect(keyAction("c")).toBe("confirm");
    expect(keyAction("e")).toBe("edit");
    expect(keyAction("r")).toBe("reject");
    expect(keyAction("x")).toBeNull();
    expect(typingTarget({ tagName: "TEXTAREA", isContentEditable: false })).toBe(true);
    expect(typingTarget({ tagName: "DIV", isContentEditable: false })).toBe(false);
  });

  it("shows link method as confidence, a role as owner, and rejects a short reason", () => {
    expect(linkLine([])).toBe("No linked feature");
    expect(linkLine([{ kind: "feature", ref: "kubernetes/enhancements#6395", method: "explicit_key", status: "verified" }]))
      .toBe("kubernetes/enhancements#6395 · explicit key, verified");
    expect(ownerText("SIG Storage")).toBe("SIG Storage");
    expect(ownerText(null)).toBe("No owner");
    expect(reasonError("no")).toBe("A reason needs at least 3 characters.");
    expect(reasonError("not a risk")).toBeNull();
  });
});
