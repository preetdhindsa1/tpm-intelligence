import { describe, expect, it } from "vitest";
import { commandItems, currentId, destinations, readLast, stageOf, writeLast, type ReleaseDates } from "./model";

const V138: ReleaseDates = {
  cycle_start_at: "2026-08-31T00:00:00Z",
  code_freeze_at: "2026-11-17T12:00:00Z",
  release_at: "2026-12-16T00:00:00Z",
};

describe("shell", () => {
  it("uses the portfolio stage boundaries", () => {
    expect(stageOf(V138, new Date("2026-08-01T00:00:00Z"))).toBe("Plan");
    expect(stageOf(V138, new Date("2026-11-17T11:59:59Z"))).toBe("Build");
    expect(stageOf(V138, new Date("2026-11-17T12:00:00Z"))).toBe("Freeze");
    expect(stageOf(V138, new Date("2026-12-22T23:00:00Z"))).toBe("Launch");
    expect(stageOf(V138, new Date("2026-12-23T00:00:00Z"))).toBe("Learn");
    expect(stageOf({ ...V138, cycle_start_at: null }, new Date("2026-11-21T00:00:00Z"))).toBe("Dates not known");
  });

  it("links the five screens to the last program, or the release index", () => {
    const last = { project: "kubernetes", release: "v1.38", displayName: "Kubernetes" };
    const linked = destinations("/", last);
    expect(linked.map((d) => d.label)).toEqual(["Portfolio", "Live Cockpit", "Decision Studio", "AI-native PDLC", "Connect your tools"]);
    expect(linked.find((d) => d.id === "cockpit")?.href).toBe("/projects/kubernetes/releases/v1.38");
    expect(linked.find((d) => d.id === "pdlc")?.href).toBe("/lab");
    expect(destinations("/", null).find((d) => d.id === "studio")?.href).toBe("/releases");
    expect(currentId("/projects/kubernetes/releases/v1.38/simulate")).toBe("studio");
    expect(currentId("/projects/kubernetes/releases/v1.38")).toBe("cockpit");
    const labels = commandItems("/projects/kubernetes/releases/v1.38", null).map((i) => i.label);
    expect(labels).toContain("Link review");
  });

  it("stores the last program and drops a broken value", () => {
    const store = new Map<string, string>();
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) };
    writeLast(storage, { project: "kafka", release: "4.3.0", displayName: "Apache Kafka" });
    expect(readLast(storage)?.release).toBe("4.3.0");
    storage.setItem("pi.lastProgram", "{");
    expect(readLast(storage)).toBeNull();
  });
});
