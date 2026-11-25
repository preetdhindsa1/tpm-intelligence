import { describe, expect, it } from "vitest";
import { storyStops } from "./cockpit";

describe("storyStops", () => {
  it("keeps the feature's real timeline events and drops anything else", () => {
    const stops = storyStops([
      { at: "2026-09-21T00:00:00Z", kind: "opted_in", ref: null },
      { at: "2026-11-06T00:00:00Z", kind: "note", ref: "kubernetes/kubernetes#143644" },
      { at: "2026-11-17T12:05:00Z", kind: "removed_from_release", ref: null },
      { at: "2026-11-20T23:28:00Z", kind: "pr_merged", ref: "kubernetes/kubernetes#143709" },
    ]);
    expect(stops.map((s) => s.kind)).toEqual(["opted_in", "removed_from_release", "pr_merged"]);
  });
});
