import { describe, expect, it } from "vitest";
import { suggestionCounts } from "../lib/format";

describe("suggestionCounts", () => {
  it("lists only non-zero statuses in review order, with thousands separators", () => {
    expect(suggestionCounts({ none: 1636, suggested: 104, dropped: 11, rejected: 0 })).toBe(
      "104 waiting · 1,636 no match · 11 dropped by checks",
    );
  });
  it("is empty before any run", () => {
    expect(suggestionCounts({})).toBe("");
  });
});
