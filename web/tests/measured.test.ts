import { describe, expect, it } from "vitest";
import { MEASURED } from "@/lib/measured";

describe("front-page measured results", () => {
  it("dates every measured number and marks unmeasured ones TBD", () => {
    for (const m of MEASURED) {
      if (m.verdict === "pending") {
        expect(m.value).toBe("TBD");
        expect(m.measured).toBe("");
      } else expect(m.measured).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });

  it("shows failures as well as passes", () => {
    expect(MEASURED.some((m) => m.verdict === "fail")).toBe(true);
  });
});
