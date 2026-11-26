import { describe, expect, it } from "vitest";
import { approvalNotes, bottleneckTag, bottleneckText, comingNextBlurb, decisionHref, missingRows, portfolioSummary, programSubline, stageLabel, stageLine, statusLabel, waitingVerb } from "./portfolio";

describe("portfolio display", () => {
  it("uses the contract stage names and says when the stage is unknown", () => {
    expect(stageLabel("verify")).toBe("Verify");
    expect(stageLabel("freeze")).toBe("Verify"); // older API name, during a deploy
    expect(stageLabel(null)).toBe("Stage unknown");
    expect(stageLabel("other")).toBe("other");
  });

  it("shows Planned and Live, and leaves other statuses unchanged", () => {
    expect(statusLabel("planned")).toBe("Planned");
    expect(statusLabel("live")).toBe("Live");
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
    expect(decisionHref("kubernetes", "v1.38", "review_raid")).toBe("/projects/kubernetes/releases/v1.38/raid");
    expect(waitingVerb("review_raid")).toBe("Review");
    expect(decisionHref("tpm-intelligence", "Phase 3", "classify_prs")).toBe("/lab");
    expect(decisionHref("kubernetes", "v1.38", "simulate")).toBeNull();
  });

  it("describes only the modules the API still marks planned", () => {
    const modules = [
      { module: "raid", name: "RAID tracker", status: "live" },
      { module: "readiness", name: "Release readiness", status: "planned" },
      { module: "retro", name: "Retro insights", status: "planned" },
    ];
    expect(comingNextBlurb(modules)).toBe("A go/no-go from real signals before launch and a retro that shows when each slip was first visible.");
    expect(comingNextBlurb(modules.map((item) => ({ ...item, status: "planned" })))).toBe(
      "A RAID log from the release notes, confirmed before it counts, a go/no-go from real signals before launch and a retro that shows when each slip was first visible.",
    );
  });
});

describe("portfolio rows from API dates", () => {
  const base = {
    key: "kubernetes:v1.38", project: "kubernetes", display_name: "Kubernetes", release: "v1.38", as_of: "2026-11-25T05:00:00Z",
    planning_tool: "github", code_tools: ["github"],
    dates: { cycle_start_at: "2026-08-31T00:00:00Z", enhancements_freeze_at: "2026-09-30T12:00:00Z", code_freeze_at: "2026-11-17T12:00:00Z", release_at: "2026-12-16T00:00:00Z" },
    stage: { current: "verify", stages: [], days_to_next_milestone: 21, next_milestone: { name: "release", at: "2026-12-16T00:00:00Z" } },
    scope: { features_in_release: 70, features_ever: 106 },
    bottleneck: { kind: "critical_flags", severity: "critical", headline: "28 critical flags", detail: "25 features past Code Freeze with the main PR not merged" },
    next_decision: null,
  };

  it("says where each program is, with its real dates", () => {
    expect(programSubline(base)).toBe("GitHub · release 16 Dec 2026");
    expect(stageLine(base)).toBe("Verifying · past Code Freeze (17 Nov) · release in 21 days");
    expect(stageLine({ ...base, code_freeze_label: "Feature Freeze", stage: { ...base.stage, current: "build" } })).toBe("Building · Feature Freeze 17 Nov 2026");
    expect(stageLine({ ...base, stage: { ...base.stage, current: "build" } })).toBe("Building · Code Freeze 17 Nov 2026");
    expect(stageLine({ ...base, stage: { ...base.stage, current: "plan" } })).toBe("Planning · cycle starts 31 Aug");
    expect(stageLine({ ...base, stage: { ...base.stage, current: null } })).toBe("Stage unknown");
  });

  it("shortens known bottleneck kinds and keeps the API text", () => {
    expect(bottleneckTag(base.bottleneck)).toBe("28 critical flags");
    expect(bottleneckText(base.bottleneck)).toBe("25 features past Code Freeze with the main PR not merged");
    const link = { kind: "linking_gap", severity: "warning", headline: "3 of 16 features have no linked code", detail: "13 of 16 features in the release are linked to a pull request" };
    expect(bottleneckTag(link)).toBe("Linking");
    expect(bottleneckText(link)).toBe("13 of 16 features in the release are linked to a pull request");
    expect(waitingVerb("review_link_suggestions")).toBe("Confirm");
    expect(waitingVerb("something_new")).toBe("Open");
  });
});
