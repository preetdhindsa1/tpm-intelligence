import { describe, expect, it } from "vitest";
import { devLoginEnabled, githubEnabled } from "@/lib/auth";
import { forwardPath, signature, signedHeaders } from "@/lib/sign";

describe("signed actions (ADR-0016)", () => {
  it("matches the API's Python signature byte for byte", () => {
    // Known answers from api/auth.py signature().
    expect(signature("test-secret", "preetdhindsa1", "1795000000", "post", "/releases/v1.38/updates/7/approve?x=1", '{"note":"ok"}')).toBe(
      "a19902a6b09e37f8c278ee39a6d00cf593d79335eef8e60a72afedce231149ba",
    );
    expect(signature("test-secret", "preetdhindsa1", "1795000000", "GET", "/me", "")).toBe(
      "5211195b921a6b6648f33ac9d12b7b947b684ce85ca04770f6f9956b096db032",
    );
  });

  it("signs nothing when nobody is signed in or no secret is set", () => {
    expect(signedHeaders("s", null, "POST", "/x", "")).toEqual({});
    expect(signedHeaders(undefined, "a", "POST", "/x", "")).toEqual({});
    const h = signedHeaders("s", "a", "POST", "/x", "", 1_795_000_000_000);
    expect(h["x-tpm-user"]).toBe("a");
    expect(h["x-tpm-time"]).toBe("1795000000");
  });

  it("refuses paths that could escape the API root", () => {
    expect(forwardPath(["releases", "v1.38", "updates"], "?a=1")).toBe("/releases/v1.38/updates?a=1");
    expect(forwardPath(["..", "admin"], "")).toBeNull();
    expect(forwardPath([], "")).toBeNull();
    expect(forwardPath(["a/b"], "")).toBeNull();
  });

  it("allows the development login only in local mode", () => {
    expect(devLoginEnabled({ AUTH_DEV_LOGIN: "true", AUTH_MODE: "local" })).toBe(true);
    expect(devLoginEnabled({ AUTH_DEV_LOGIN: "true", AUTH_MODE: "required" })).toBe(false);
    expect(devLoginEnabled({ AUTH_DEV_LOGIN: "true" })).toBe(false);
    expect(githubEnabled({ AUTH_GITHUB_ID: "x" })).toBe(false);
  });
});
