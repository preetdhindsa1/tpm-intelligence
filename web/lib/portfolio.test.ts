import { describe, expect, it } from "vitest";
import { decisionHref, stageLabel, statusLabel } from "./portfolio";

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

  it("sends each waiting kind to the page that already handles it", () => {
    expect(decisionHref("kubernetes", "v1.38", "approve_exec_update")).toBe("/projects/kubernetes/releases/v1.38/update");
    expect(decisionHref("kubernetes", "v1.38", "review_link_suggestions")).toBe("/projects/kubernetes/releases/v1.38/links");
    expect(decisionHref("tpm-intelligence", "Phase 3", "classify_prs")).toBe("/lab");
    expect(decisionHref("kubernetes", "v1.38", "simulate")).toBeNull();
  });
});
