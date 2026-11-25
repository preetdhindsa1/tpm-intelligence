import { describe, expect, it } from "vitest";
import { CONNECTORS, PROMISES, STEPS } from "./connect";

describe("connect page", () => {
  it("has the three steps and does not invent a connection count", () => {
    expect(STEPS.map((step) => step.title)).toEqual(["Connect", "Describe releases", "First program filling in"]);
    expect(CONNECTORS.map((item) => item.status).join(" ")).not.toMatch(/\d/);
    expect(PROMISES.map((item) => item.title)).toEqual(["Read-only", "A person approves", "Public demo privacy"]);
  });
});
