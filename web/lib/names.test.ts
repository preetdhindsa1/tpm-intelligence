import { describe, expect, it } from "vitest";
import { programTitle } from "./names";

describe("program names", () => {
  it("names the platform's own repo without its phase, and others with their release", () => {
    expect(programTitle("Program Intelligence Platform (Current Project)", "Phase 3", true)).toBe("Program Intelligence Platform (Current Project)");
    expect(programTitle("Kubernetes", "v1.38", false)).toBe("Kubernetes v1.38");
    expect(programTitle("Apache Kafka", "4.5.0")).toBe("Apache Kafka 4.5.0");
  });
});
