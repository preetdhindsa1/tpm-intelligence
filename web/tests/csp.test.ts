import { describe, expect, it } from "vitest";
import { buildCsp } from "../proxy";

describe("Content-Security-Policy (#65)", () => {
  const csp = buildCsp("abc123", false);
  const directive = (name: string) => csp.split("; ").find((d) => d.startsWith(`${name} `)) ?? "";

  it("only runs scripts that carry this request's nonce", () => {
    expect(directive("script-src")).toContain("'nonce-abc123'");
    expect(directive("script-src")).not.toContain("'unsafe-inline'");
    expect(directive("script-src")).not.toContain("'unsafe-eval'"); // production
  });

  it("lets the browser reach the API for live updates and the simulator", () => {
    expect(directive("connect-src")).toMatch(/^connect-src 'self' https?:\/\//);
  });

  it("keeps GitHub sign-in working and the page unframeable", () => {
    expect(directive("form-action")).toContain("https://github.com");
    expect(directive("frame-ancestors")).toBe("frame-ancestors 'none'");
    expect(directive("object-src")).toBe("object-src 'none'");
  });

  it("allows eval only in development (React's debugging)", () => {
    expect(buildCsp("n", true)).toContain("'unsafe-eval'");
  });
});
