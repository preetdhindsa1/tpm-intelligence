import { describe, expect, it } from "vitest";
import { DEMO_CHAPTERS, PIPELINE, STAGES, TRUST_RULES, daysBetween, fraction, freezeReplay, shortDate, teamCards, trustProof, trustTiles, verdictSummary } from "./front";
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

describe("trust by design", () => {
  it("backs each rule with data, never a stand-in", () => {
    expect(TRUST_RULES.map((r) => r.title)).toEqual(["AI never computes facts", "Every AI sentence is verified", "Suggestions stay suggestions"]);
    expect(trustProof("verified", MEASURED, [])).toBe("43 / 43 agreement with labelled claims (measured 2026-11-22).");
    const waiting = [{ kind: "review_link_suggestions", count: 101, label: "101 AI link suggestions · v1.38" }];
    expect(trustProof("suggestions", MEASURED, waiting)).toBe("101 v1.38 suggestions are waiting for review now; none of them count yet.");
    expect(trustProof("suggestions", MEASURED, [])).toContain("Link suggester precision 84.8%");
    expect(trustProof("verified", [], [])).toContain("TBD (not yet measured)");
  });

  it("counts verdicts, failures included", () => {
    const s = verdictSummary(MEASURED);
    expect(s).toMatch(/\d+ pass/);
    expect(s).toMatch(/\d+ fail/);
    const total = s.split(" · ").reduce((n, part) => n + Number(part.split(" ")[0]), 0);
    expect(total).toBe(MEASURED.length);
  });
});

describe("how it works and connected teams", () => {
  it("lists seven steps, with AI only in Explain and a human in Approve", () => {
    expect(PIPELINE.map((s) => s.title)).toEqual(["Collect", "Link", "Facts", "Forecast", "Explain", "Verify", "Approve"]);
    expect(PIPELINE.filter((s) => s.kind === "ai").map((s) => s.title)).toEqual(["Explain"]);
    expect(PIPELINE.filter((s) => s.kind === "human").map((s) => s.title)).toEqual(["Approve"]);
  });

  it("marks a team Live only when the portfolio serves it, using the API's name", () => {
    const cards = teamCards(
      [
        { project: "kubernetes", release: "v1.38", display_name: "Kubernetes" },
        { project: "tpm-intelligence", release: "Phase 3", display_name: "Program Intelligence Platform (Current Project)" },
      ],
      (p, r) => `/projects/${p}/releases/${r}`,
    );
    expect(cards.map((c) => [c.name, c.live])).toEqual([
      ["Kubernetes", true],
      ["Apache Kafka", false],
      ["Program Intelligence Platform (Current Project)", true],
      ["Your team", false],
    ]);
    expect(cards[3].href).toBe("/connect");
  });
});
