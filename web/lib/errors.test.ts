import { describe, expect, it } from "vitest";
import { errorDetail, isNotFound } from "./errors";

describe("API failures on a page", () => {
  it("shows the API's own failure text", () => {
    expect(errorDetail(new Error("/releases/v1.38/dependencies: HTTP 503"), "fallback")).toBe("/releases/v1.38/dependencies: HTTP 503");
    expect(errorDetail("boom", "GET /lab failed")).toBe("GET /lab failed");
    expect(errorDetail(new Error(""), "GET /lab failed")).toBe("GET /lab failed");
  });

  it("treats only a 404 as not found", () => {
    expect(isNotFound("/releases/v1.38/features/999999: HTTP 404")).toBe(true);
    expect(isNotFound("/releases/v1.38/features/6395: HTTP 500")).toBe(false);
    expect(isNotFound("fetch failed")).toBe(false);
  });
});
