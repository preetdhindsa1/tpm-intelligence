import { describe, expect, it } from "vitest";
import { DEMO_CHAPTERS, STAGES, daysBetween, fraction, freezeReplay, shortDate, trustTiles } from "./front";
import { MEASURED } from "./measured";
import { toolsLabel } from "./portfolio";

describe("front page facts", () => {
  it("builds the #6395 replay sentence from the main PR's real dates", () => {
    // kubernetes/kubernetes#143709: opened 2 Nov 16:44, merged 20 Nov 23:28; Code Freeze 17 Nov 12:00 UTC.
    expect(freezeReplay(6395, "2026-11-02T16:44:28Z", "2026-11-20T23:28:24Z", "2026-11-17T12:00:00Z", true)).toBe(
      "Feature #6395's main PR opened 15 days before the freeze, missed it by 3 days, and was re-added after.",
    );
    expect(freezeReplay(6395, "2026-11-02T16:44:28Z", null, "2026-11-17T12:00:00Z", true)).toBeNull();
    expect(freezeReplay(6395, "2026-11-02T16:44:28Z", "2026-11-06T00:00:00Z", "2026-11-17T12:00:00Z", false)).toBeNull();
  });

  it("counts whole days and formats short UTC dates", () => {
    expect(daysBetween("2026-11-17T12:00:00Z", "2026-11-20T23:28:24Z")).toBe(3);
    expect(daysBetween(null, "2026-11-20T23:28:24Z")).toBeNull();
    expect(shortDate("2027-02-04T00:00:00Z")).toBe("4 Feb 2027");
  });

  it("reads fractions from the measured list", () => {
    expect(fraction("21 / 26")).toEqual([21, 26]);
    expect(fraction("9 of 12")).toBeNull();
    expect(fraction("1 / 0")).toBeNull();
  });

  it("takes the four trust tiles from measured results, with the forecast flagged", () => {
    const tiles = trustTiles(MEASURED);
    expect(tiles.map((t) => t.value)).toEqual(["43 / 43", "0%", "98.6%", "9 of 12"]);
    expect(tiles[3].warn).toBe(true);
    expect(trustTiles([])).toEqual([]);
  });

  it("names tools once, planning tool first", () => {
    expect(toolsLabel({ planning_tool: "jira", code_tools: ["github"] })).toBe("Jira + GitHub");
    expect(toolsLabel({ planning_tool: "github", code_tools: ["github"] })).toBe("GitHub");
    expect(toolsLabel({})).toBe("");
  });

  it("has five stages and five chapters", () => {
    expect(STAGES.map((s) => s.stage)).toEqual(["Plan", "Build", "Freeze", "Launch", "Learn"]);
    expect(DEMO_CHAPTERS).toHaveLength(5);
  });
});
