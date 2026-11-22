import { describe, expect, it } from "vitest";
import { releaseFromPath, releaseHref } from "@/lib/releasePath";

describe("releasePath", () => {
  it("parses release name from nested paths", () => {
    expect(releaseFromPath("/releases/v1.38")).toBe("v1.38");
    expect(releaseFromPath("/releases/v1.38/simulator")).toBe("v1.38");
    expect(releaseFromPath("/releases/v1.38/features/6395")).toBe("v1.38");
    expect(releaseFromPath("/")).toBeNull();
  });

  it("builds section hrefs", () => {
    expect(releaseHref("v1.38", "dashboard")).toBe("/releases/v1.38");
    expect(releaseHref("v1.38", "dependencies")).toBe("/releases/v1.38/dependencies");
    expect(releaseHref("v1.38", "simulator")).toBe("/releases/v1.38/simulator");
    expect(releaseHref("v1.38", "reports")).toBe("/releases/v1.38/reports");
  });
});
