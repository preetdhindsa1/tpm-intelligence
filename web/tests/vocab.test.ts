import { describe, expect, it } from "vitest";
import { featureLabel, shortTeam, vocab } from "@/lib/vocab";

describe("vocab", () => {
  it("labels GitHub features by number and Jira features by key", () => {
    expect(featureLabel({ key: "kubernetes/enhancements#6395", number: 6395 })).toBe("#6395");
    expect(featureLabel({ key: "KAFKA-20682", number: 20682 })).toBe("KAFKA-20682");
  });
  it("uses each project's words", () => {
    expect(vocab("kubernetes").teams).toBe("SIGs");
    expect(vocab("KAFKA").design).toBe("KIP");
    expect(vocab("other").team).toBe("team");
    expect(shortTeam("sig/node")).toBe("node");
  });
});
