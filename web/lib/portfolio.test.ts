import { describe, expect, it } from "vitest";
import { approvalNotes, decisionHref, missingRows, portfolioSummary, stageLabel, statusLabel } from "./portfolio";

describe("portfolio display", () => {
  it("uses the contract stage names and says when the stage is unknown", () => {
    expect(stageLabel("freeze")).toBe("Freeze");
    expect(stageLabel(null)).toBe("Stage unknown");
    expect(stageLabel("other")).toBe("other");
  });

  it("shows Planned for a planned module and leaves other statuses unchanged", () => {
    expect(statusLabel("planned")).toBe("Planned");
    expect(statusLabel("preview")).toBe("preview");
  });

  it("counts programs, planning tools, and waiting decisions from totals", () => {
    expect(portfolioSummary({ programs: 3, planning_tools: ["github", "jira"], waiting_on_you: 3 })).toBe(
      "3 programs · 2 planning tools · 3 decisions waiting on you",
    );
    expect(portfolioSummary({ programs: 1, planning_tools: ["github"], waiting_on_you: 1 })).toBe(
      "1 program · 1 planning tool · 1 decision waiting on you",
    );
  });

  it("keeps a program row when only a store could not be read", () => {
    const skipped = [
      { team: "kafka", reason: "no release yet" },
      { team: "KAFKA", reason: "link suggestions could not be read" },
      { team: "kubernetes", reason: "exec updates could not be read" },
    ];
    expect(missingRows(skipped)).toEqual([{ team: "kafka", reason: "no release yet" }]);
    expect(approvalNotes("kafka", skipped)).toEqual(["Approvals may be missing: link suggestions could not be read"]);
    expect(approvalNotes("kubernetes", skipped)).toEqual(["Approvals may be missing: exec updates could not be read"]);
  });

  it("sends each waiting kind to the page that already handles it", () => {
    expect(decisionHref("kubernetes", "v1.38", "approve_exec_update")).toBe("/projects/kubernetes/releases/v1.38/update");
    expect(decisionHref("kubernetes", "v1.38", "review_link_suggestions")).toBe("/projects/kubernetes/releases/v1.38/links");
    expect(decisionHref("tpm-intelligence", "Phase 3", "classify_prs")).toBe("/lab");
    expect(decisionHref("kubernetes", "v1.38", "simulate")).toBeNull();
  });
});
