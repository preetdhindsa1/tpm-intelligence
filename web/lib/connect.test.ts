import { describe, expect, it } from "vitest";
import { CONNECTORS, PROMISES, RELEASE_FIELDS, STEPS, usedBy } from "./connect";

describe("connect page", () => {
  const programs = [
    { display_name: "Kubernetes", planning_tool: "github", code_tools: ["github"] },
    { display_name: "Apache Kafka", planning_tool: "jira", code_tools: ["github"] },
    { display_name: "Program Intelligence Platform (Current Project)", planning_tool: "github", code_tools: ["github"] },
  ];

  it("marks a connector Available only when a live program reads it", () => {
    const github = CONNECTORS.find((c) => c.id === "github")!;
    const jira = CONNECTORS.find((c) => c.id === "jira")!;
    const notes = CONNECTORS.find((c) => c.id === "notes")!;
    expect(usedBy(github, programs)).toEqual(["Kubernetes", "Apache Kafka", "Program Intelligence Platform (Current Project)"]);
    expect(usedBy(jira, programs)).toEqual(["Apache Kafka"]);
    expect(usedBy(notes, programs)).toEqual([]);
    expect(usedBy(github, [])).toEqual([]);
  });

  it("has three steps, the four release dates, and no invented counts", () => {
    expect(STEPS.map((s) => s.title)).toEqual(["Connect your tools", "Describe your releases", "See your first program"]);
    expect(RELEASE_FIELDS.map((f) => f.name)).toEqual(["Cycle start", "Enhancements Freeze", "Code Freeze", "Release"]);
    expect(CONNECTORS.map((c) => c.reads).join(" ")).not.toMatch(/\d/);
    expect(PROMISES.map((p) => p.title)).toEqual(["Read-only, least access", "Flow, not people", "You approve what leaves"]);
  });
});
