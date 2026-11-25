import { describe, expect, it } from "vitest";
import { dayMonth, keyStops, lifecycle, simValidationText, storyStops } from "./cockpit";

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

  it("keeps Enhancements Freeze and drops a repeated untracked row and a future release", () => {
    const untracked = { at: "2026-11-17T12:05:58Z", kind: "untracked", ref: null };
    const stops = storyStops([
      untracked,
      { ...untracked },
      { at: "2026-09-30T12:00:00Z", kind: "enhancements_freeze", ref: null },
      { at: "2026-12-16T00:00:00Z", kind: "release", ref: null },
    ]);
    expect(stops).toEqual([untracked, { at: "2026-09-30T12:00:00Z", kind: "enhancements_freeze", ref: null }]);
  });
});

describe("Live Cockpit key stops for #6395", () => {
  // Trimmed from GET /releases/v1.38/features/6395 (live API, 2026-11-25).
  const timeline = [
    { at: "2026-09-21T20:34:30Z", kind: "opted_in", ref: null },
    { at: "2026-09-21T20:34:45Z", kind: "added_to_release", ref: null },
    { at: "2026-09-23T06:41:32Z", kind: "tracked", ref: null },
    { at: "2026-09-30T12:00:00Z", kind: "enhancements_freeze", ref: null },
    { at: "2026-10-26T21:34:09Z", kind: "pr_opened", ref: "kubernetes/kubernetes#143445" },
    { at: "2026-10-27T21:57:16Z", kind: "pr_merged", ref: "kubernetes/kubernetes#143445" },
    { at: "2026-11-02T16:44:28Z", kind: "pr_opened", ref: "kubernetes/kubernetes#143709" },
    { at: "2026-11-04T23:07:12Z", kind: "pr_merged", ref: "kubernetes/kubernetes#143522" },
    { at: "2026-11-06T18:17:47Z", kind: "pr_merged", ref: "kubernetes/kubernetes#143474" },
    { at: "2026-11-17T12:00:00Z", kind: "code_freeze", ref: null },
    { at: "2026-11-17T12:05:57Z", kind: "removed_from_release", ref: null },
    { at: "2026-11-20T23:28:24Z", kind: "pr_merged", ref: "kubernetes/kubernetes#143709" },
    { at: "2026-11-21T00:33:55Z", kind: "added_to_release", ref: null },
    { at: "2026-11-21T00:33:55Z", kind: "tracked", ref: null },
  ];
  const prs = [
    { key: "kubernetes/kubernetes#143709", is_main: true, created_at: "2026-11-02T16:44:28Z", merged_at: "2026-11-20T23:28:24Z" },
    { key: "kubernetes/kubernetes#143445", is_main: false, created_at: "2026-10-26T21:34:09Z", merged_at: "2026-10-27T21:57:16Z" },
  ];
  const stops = keyStops(timeline, prs, ["sig/node", "sig/storage"]);

  it("finds the eight moments in order, with real dates", () => {
    expect(stops.map((s) => s.label)).toEqual([
      "Opted in", "Tracked", "Enhancements Freeze", "Main PR opened", "Support PRs merge", "Removed at freeze", "Main PR merges", "Re-added",
    ]);
    expect(stops.map((s) => dayMonth(s.at))).toEqual(["21 Sep", "23 Sep", "30 Sep", "2 Nov", "6 Nov", "17 Nov", "20 Nov", "21 Nov"]);
    expect(stops.find((s) => s.key === "removed")?.tone).toBe("critical");
  });

  it("says only what was known on that day", () => {
    const open = stops.find((s) => s.key === "main-open")!;
    expect(open.when).toBe("As of 2 Nov · 15 days to Code Freeze");
    expect(open.knew).toBe("The main implementation, PR #143709, opens 15 days before Code Freeze. One supporting PR, #143445, merged so far.");
    expect(open.why).toContain("SIG Storage");
    expect(stops.find((s) => s.key === "support")!.knew).toBe("Supporting PRs #143522 and #143474 merge. The main PR #143709 is still open.");
    expect(stops.find((s) => s.key === "removed")!.knew).toContain("removed from the release 6 minutes later");
    expect(stops.find((s) => s.key === "main-merge")!.knew).toBe("The main PR #143709 merges 3 days after Code Freeze.");
  });

  it("leaves out moments the data does not have", () => {
    const early = keyStops(timeline.slice(0, 4), [], ["sig/node"]);
    expect(early.map((s) => s.key)).toEqual(["opted", "tracked", "ef"]);
  });

  it("fills the lifecycle up to the as-of date", () => {
    const d = { cycle_start_at: "2026-08-31T00:00:00Z", enhancements_freeze_at: "2026-09-30T12:00:00Z", code_freeze_at: "2026-11-17T12:00:00Z", release_at: "2026-12-16T00:00:00Z" };
    const steps = lifecycle(d, "2026-11-25T00:00:00Z", "Verify");
    expect(steps.map((s) => s.fill === 1)).toEqual([true, true, false, false, false]);
    expect(steps[2].fill).toBeGreaterThan(0.2);
    expect(steps[2].here).toBe(true);
    expect(steps[3].note).toBe("Release 16 Dec · in 21 days");
    expect(steps[2].note).toBe("Code Freeze 17 Nov, 12:00 UTC");
    expect(steps[2].name).toBe("Verify");
    expect(lifecycle(d, "2026-11-25T00:00:00Z", "Verify", "Feature Freeze")[2].note).toBe("Feature Freeze 17 Nov, 12:00 UTC");
  });
});

describe("simulator validation sentence", () => {
  const v = {
    passed: false, tolerance: 0.2,
    releases: [
      { release: "kubernetes:v1.37", passed: false, checks: [{ name: "median review wait (days)", real: 0.125, simulated: 0.381, passed: false }] },
      { release: "kubernetes:v1.38", passed: false, checks: [
        { name: "median review wait (days)", real: 0.054, simulated: 0.243, passed: false },
        { name: "median time to merge (days)", real: 2.548, simulated: 2.427, passed: true },
      ] },
    ],
  };
  it("words the release's own replay with the stored numbers", () => {
    expect(simValidationText(v, "kubernetes:v1.38")).toBe(
      "Replay of v1.38: simulated review wait 0.24 days vs 0.05 real (fails ±20%); time to merge 2.43 days vs 2.55 real (passes).",
    );
    expect(simValidationText(v, "KAFKA:4.5.0")).toContain("Replay of v1.38");
    expect(simValidationText(null, "x")).toBeNull();
  });
});
