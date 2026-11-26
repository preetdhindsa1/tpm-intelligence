import { describe, expect, it } from "vitest";
import type { ReadinessDecision } from "./api-readiness";
import { UNKNOWN_REASON, criterionLabel, decisionLabel, newestDecisions, noteError, verdictLabel } from "./readiness";

const row = (at: string, decision: ReadinessDecision["decision"] = "go"): ReadinessDecision => ({
  decision, note: "Noted for the log.", decided_by: "approver", decided_at: at, facts_as_of: at,
});

describe("readiness wording", () => {
  it("names the verdict and explains unknown as no data", () => {
    expect(verdictLabel("ready")).toBe("Ready");
    expect(verdictLabel("not_ready")).toBe("Not ready");
    expect(verdictLabel("unknown")).toBe("Unknown");
    expect(criterionLabel("unknown")).toBe("Unknown");
    expect(UNKNOWN_REASON).toBe("no data to decide");
  });

  it("requires a note of 3 or more characters", () => {
    expect(noteError("")).toBe("A note needs at least 3 characters.");
    expect(noteError("  no")).toBe("A note needs at least 3 characters.");
    expect(noteError("  yes ")).toBeNull();
  });

  it("shows the decision log newest first", () => {
    const items = [row("2026-11-01T00:00:00Z", "defer"), row("2026-11-25T21:00:00Z", "no_go")];
    expect(newestDecisions(items).map((d) => d.decision)).toEqual(["no_go", "defer"]);
    expect(decisionLabel("no_go")).toBe("No go");
  });
});
